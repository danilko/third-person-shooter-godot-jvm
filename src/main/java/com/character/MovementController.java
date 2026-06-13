package com.character;

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
  private boolean rolling = false;
  private double rollSpeed = 0.0;

  /** Downward speed (m/s) required before any fall damage is dealt. 0 disables fall damage. */
  @Export
  @RegisterProperty
  public float fallDamageThreshold = 10.0f;

  /** Damage per m/s above fallDamageThreshold on landing. */
  @Export
  @RegisterProperty
  public float fallDamageScale = 5.0f;

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

    boolean wasOnFloor = player.isOnFloor();

    // Calculate horizontal velocity
    Vector3 normDir = direction.normalized();

    if (rolling) {
      velocity.setX(rollSpeed * normDir.getX());
      velocity.setZ(rollSpeed * normDir.getZ());
    } else {
      velocity.setX(speed * normDir.getX());
      velocity.setZ(speed * normDir.getZ());
    }

    // Handle Gravity
    if (!player.isOnFloor()) {
      if (velocity.getY() >= 0) {
        velocity.setY(velocity.getY() - (jumpGravity * delta));
      } else {
        velocity.setY(velocity.getY() - (fallGravity * delta));
      }
    }

    // Apply movement using lerp
    player.setVelocity(GD.lerp(player.getVelocity(), velocity, Math.min(1.0, acceleration * delta)));
    float appliedVelocityY = (float) player.getVelocity().getY();
    player.moveAndSlide();

    // Fall damage: compare velocity just before landing to the configured threshold.
    if (fallDamageThreshold > 0 && !wasOnFloor && player.isOnFloor()
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
    if (rolling && direction.lengthSquared() > 0.001) {
      // During roll: always face movement direction, even in combat
      targetRotation = atan2(-direction.getX(), -direction.getZ()) - playerInitRotation;
    } else if (combat) {
      targetRotation = camRotation;
    } else {
      // Face movement direction (only when actually moving)
      if (direction.lengthSquared() > 0.001) {
        targetRotation = atan2(-direction.getX(), -direction.getZ()) - playerInitRotation;
      } else {
        targetRotation = meshRoot.getRotation().getY(); // hold current facing
      }
    }

    Vector3 currentRot = meshRoot.getRotation();
    double newY = GD.lerpAngle(currentRot.getY(), targetRotation, rotationSpeed * delta);

    // Update only the Y axis
    meshRoot.setRotation(new Vector3(currentRot.getX(), newY, currentRot.getZ()));

  }


  @RegisterFunction
  public void roll(RollState rollState) {
    rolling = true;
    rollSpeed = rollState.getRollSpeed();
  }

  @RegisterFunction
  public void completedRoll() {
    rolling = false;
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