package com.openworld.movement.character;

import godot.api.CharacterBody3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.core.Vector3;
import godot.global.GD;
import static java.lang.Math.atan2;
import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.control.Controller;
import com.openworld.control.PlayerController;
import com.openworld.control.UserCommand;
import com.openworld.net.NetworkController;

@RegisterClass(className = "MovementController")
public class MovementController extends Node {

  @Export
  @RegisterProperty
  public CharacterBody3D player = null;

  @Export
  @RegisterProperty
  public Node3D meshRoot = null;

  @Export
  @RegisterProperty
  public double rotationSpeed = 8.0;

  @Export
  @RegisterProperty
  public double fallGravity = 45.0;

  private double jumpGravity = fallGravity;
  private Vector3 direction = new Vector3();
  private Vector3 velocity = new Vector3();
  private double acceleration = 0.0;
  private double speed = 0.0;
  /**
   * When true the incoming movementDirection is already in world space (Enemy/AI).
   * When false it is in camera-relative input space and is rotated by camRotation (Player).
   */
  @Export
  @RegisterProperty
  public boolean worldSpaceMovement = false;

  private double camRotation = 0.0;
  private double playerInitRotation = 0.0;
  private boolean combat = false;
  private double combatSpeedFactor = 1.0;
  private double combatAccelerationFactor = 1.0;

  // ── Air strafe (CS/Source-style) ────────────────────────────────────────────
  /** Air acceleration constant — higher gives faster strafe speed-gain. */
  @Export
  @RegisterProperty
  public double airAccelerate = 80.0;

  /**
   * Per-tick wish-speed cap that makes air-strafing gain speed: only the velocity
   * component below this cap (projected onto the wish direction) can be added in air,
   * so turning the mouse while strafing curves and accelerates momentum instead of
   * snapping to {@code speed·dir}. Small by design (Quake's classic ~30 ups ≈ 0.8 m/s).
   */
  @Export
  @RegisterProperty
  public double airSpeedCap = 0.8;

  /** Downward speed (m/s) required before any fall damage is dealt. 0 disables fall damage. */
  @Export
  @RegisterProperty
  public float fallDamageThreshold = 10.0f;

  /** Damage per m/s above fallDamageThreshold on landing. */
  @Export
  @RegisterProperty
  public float fallDamageScale = 5.0f;

  /** Swim tunables (buoyancy / reduced gravity / vertical clamp) — used while {@link #swimming}. */
  @Export
  @RegisterProperty
  public SwimState swimState = null;

  /** True while the body is in a water volume (set by Character.setInWater → setSwimming). */
  private boolean swimming = false;
  /** World-space Y of the water surface the body floats toward while swimming. */
  private double waterSurfaceY = 0.0;
  /** Per-tick vertical swim intent: +1 ascend, -1 dive, 0 hold (let buoyancy settle to surface). */
  private double swimVertical = 0.0;

  @RegisterFunction
  public void setSwimming(boolean value, double surfaceY) {
    swimming = value;
    if (value) waterSurfaceY = surfaceY;
    else swimVertical = 0.0;
  }

  @RegisterFunction
  public void setSwimVertical(double value) {
    swimVertical = value;
  }

  @RegisterFunction
  @Override
  public void _ready() {
    if (player != null) {
      playerInitRotation = player.getRotation().getY();
    }
  }

  @RegisterFunction
  @Override
  public void _physicsProcess(double delta) {
    if (player == null || meshRoot == null) return;
    // Non-authority bodies (NetworkController-driven remote peers/AI on a client) must
    // be driven *only* by replicated MSG_SNAPSHOT data — Character._physicsProcess
    // already early-returns for them (see its `!controller.isAuthority()` check), but
    // this controller runs as an independent sibling Node with its own _physicsProcess
    // and was never gated the same way. Left ungated, it called moveAndSlide() with a
    // locally-derived (always-zero `direction`/stale `combat`/`camRotation`) velocity
    // every physics tick — fighting applyReplicatedTransform's direct position writes
    // — and continuously overwrote meshRoot's rotation toward its own locally-computed
    // targetRotation, fighting applyReplicatedFacing's writes. That tug-of-war between
    // local physics and replicated state is what produced "wrong position/direction"
    // and the apparent multi-second catch-up lag (round 5 manual-test report).
    if (player instanceof Character c) {
      Controller ctrl = c.getController();
      if (ctrl != null && !ctrl.isAuthority()) return;
    }

    boolean onFloor = player.isOnFloor();
    boolean wasOnFloor = onFloor;

    Vector3 normDir = direction.normalized();
    Vector3 curVel  = player.getVelocity();

    // ── Horizontal velocity ──────────────────────────────────────────────────
    // Swimming uses the grounded smoothing branch even in deep water (isOnFloor()==false)
    // so the swimmer still accelerates toward its (capped) target speed.
    double newX, newZ;
    if (onFloor || swimming) {
      // Grounded: accelerate toward the target speed·dir with the usual smoothing.
      double targetX = speed * normDir.getX();
      double targetZ = speed * normDir.getZ();
      double t = Math.min(1.0, acceleration * delta);
      newX = GD.lerp(curVel.getX(), targetX, t);
      newZ = GD.lerp(curVel.getZ(), targetZ, t);
    } else {
      // Airborne: Source-style air strafe. Preserve existing horizontal momentum and
      // add only a capped amount along the wish direction — turning the mouse while
      // holding a strafe key curves and gains speed (CS/Quake air control).
      newX = curVel.getX();
      newZ = curVel.getZ();
      if (normDir.lengthSquared() > 0.0001) {
        double curSpeedAlongWish = newX * normDir.getX() + newZ * normDir.getZ();
        double addSpeed = airSpeedCap - curSpeedAlongWish;
        if (addSpeed > 0) {
          double accelSpeed = Math.min(airAccelerate * airSpeedCap * delta, addSpeed);
          newX += accelSpeed * normDir.getX();
          newZ += accelSpeed * normDir.getZ();
        }
      }
    }

    // ── Vertical velocity (integrated on the internal Y, direct — no lerp) ─────
    if (swimming && swimState != null) {
      // Vertical swim model. With no input a buoyancy spring drives the body toward the settle line
      // (surface − settleDepth) and holds it there, so it settles AT the water line instead of
      // popping out the top (the surface-bob flicker). Manual ascend/dive use their own (faster)
      // speeds — held jump rises at swimAscendSpeed (clearly faster than the gentle passive cap),
      // easing in near the surface so it never breaches; held crouch/crawl dives at swimDiveSpeed.
      // The stance reverts (in Character.applyInput) only when the swimmer rests on shallow ground.
      boolean combat = (player instanceof Character c) && c.isCombat();
      double settleDepth = combat ? swimState.getAimSubmersionDepth() : swimState.getSubmersionDepth();
      double targetY = waterSurfaceY - settleDepth;
      double bodyY = player.getGlobalPosition().getY();
      double passiveCap = swimState.getMaxVerticalSpeed();   // gentle auto-settle only
      double vy;
      if (swimVertical > 0.0) {
        // Held jump → ascend FAST, but ease into the settle line near the surface (don't breach).
        if (bodyY >= targetY) {
          vy = GD.clamp((targetY - bodyY) * swimState.getBuoyancy(), -passiveCap, passiveCap);
        } else {
          vy = swimState.getSwimAscendSpeed();
        }
      } else if (swimVertical < 0.0) {
        vy = -swimState.getSwimDiveSpeed();                  // held crouch/crawl → dive
      } else {
        double diff = targetY - bodyY;                       // no input → passive buoyancy settle
        vy = GD.clamp(diff * swimState.getBuoyancy(), -passiveCap, passiveCap);
        if (Math.abs(diff) < 0.05) vy = 0.0;   // deadzone — avoid micro-jitter once settled
      }
      velocity.setY(vy);
    } else {
      if (onFloor && velocity.getY() < 0) {
        velocity.setY(0);
      }
      if (!onFloor) {
        double g = velocity.getY() >= 0 ? jumpGravity : fallGravity;
        velocity.setY(velocity.getY() - g * delta);
      }
    }
    double newY = velocity.getY();

    player.setVelocity(new Vector3(newX, newY, newZ));
    float appliedVelocityY = (float) newY;
    player.moveAndSlide();

    // Fall damage: compare velocity just before landing to the configured threshold.
    // Skipped while swimming — water cushions the entry/landing.
    if (!swimming && fallDamageThreshold > 0 && !wasOnFloor && player.isOnFloor()
            && appliedVelocityY < -fallDamageThreshold) {
      float fallSpeed = -appliedVelocityY;
      float damage = (fallSpeed - fallDamageThreshold) * fallDamageScale;
      if (player instanceof Character c && c.healthNode != null) {
        String attackerName    = (c.characterInfo != null) ? c.characterInfo.displayName : "";
        String attackerFaction = (c.characterInfo != null) ? c.characterInfo.faction     : "";
        c.healthNode.takeDamage(null, damage, "Fall", null, attackerName, attackerFaction);
      }
    }

    // Handle Mesh Rotation
    // atan2(-dx, -dz) maps a world-space movement direction to the Y rotation needed
    // for a -Z-forward mesh (Godot convention).  The old formula atan2(dx, dz) was
    // correct for a +Z-forward mesh; negating both components shifts it by π, which
    // is the rotation needed to flip from +Z to -Z facing convention.
    double targetRotation;
    if (combat) {
      targetRotation = camRotation;
    } else if (direction.lengthSquared() > 0.001) {
      // Face movement direction (only when actually moving)
      targetRotation = atan2(-direction.getX(), -direction.getZ()) - playerInitRotation;
    } else {
      targetRotation = meshRoot.getRotation().getY(); // hold current facing
    }

    Vector3 currentRot = meshRoot.getRotation();
    double newMeshY = GD.lerpAngle(currentRot.getY(), targetRotation, rotationSpeed * delta);

    // Update only the Y axis
    meshRoot.setRotation(new Vector3(currentRot.getX(), newMeshY, currentRot.getZ()));

  }


  @RegisterFunction
  public void jump(JumpState jumpState) {
    velocity.setY(2.0 * jumpState.getJumpHeight() / jumpState.getApexDuration());
    jumpGravity = velocity.getY() / jumpState.getApexDuration();
  }

  @RegisterFunction
  public void onSetMovementState(MovementState movementState) {
    speed = movementState.getMovementSpeed() * combatSpeedFactor;
    acceleration = movementState.getAcceleration() * combatAccelerationFactor;
  }

  @RegisterFunction
  public void onSetCombatState(CombatState combatState) {
    combat = combatState.isCombat();
    combatSpeedFactor = combatState.getSpeedFactor();
    combatAccelerationFactor = combatState.getAccelerationFactor();
  }

  @RegisterFunction
  public void onSetMovementDirection(Vector3 movementDirection) {
    // Direction is always world-space: AI provides it directly, PlayerController
    // pre-rotates camera-relative WASD by the camera yaw before stamping the UserCommand.
    direction = movementDirection;
  }

  @RegisterFunction
  public void onSetCamRotation(double newCamRotation) {
    camRotation = newCamRotation;
  }
}