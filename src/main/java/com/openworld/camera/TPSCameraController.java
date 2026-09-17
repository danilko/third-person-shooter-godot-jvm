package com.openworld.camera;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.*;
import godot.global.GD;
import com.openworld.character.Character;
import com.openworld.control.PlayerController;
import com.openworld.movement.character.CombatState;
import com.openworld.movement.character.MovementState;
import com.openworld.movement.character.Stance;

@Script(className = "TPSCameraController")
public class TPSCameraController extends Node3D {

  public Signal1<Double> setCamRotation = new Signal1<>(this, new StringName("set_cam_rotation"));

  @Export
  public CharacterBody3D player;

  protected int shoulderDirection = 1;

  protected Node3D yawNode;
  protected Node3D pitchNode;
  protected Node3D pivotNode;
  protected SpringArm3D springArm;
  protected Node3D proxyNode;
  protected Camera3D activeCamera;
  protected Character character;

  @Export
  public double yawSensitivity = 0.07;

  @Export
  public double pitchSensitivity = 0.07;

  /**
   * SEED for how far the view may look UP, degrees; positive is up (see {@link ControlRotation}).
   *
   * <p>Only a seed: the live limit is per stance ({@code Stance.viewPitchMax}), published into
   * {@link ControlRotation} by {@link #onSetStance}, and {@code Character._ready()} force-sets a
   * stance — so this pair is what the rig holds for the handful of frames before the first
   * {@code changed_stance} arrives, and for a rig on a body with no stances at all. It matches
   * upright so those frames are not a different camera.
   */
  @Export
  public double pitchMax = 80.0;

  /** SEED for how far the view may look DOWN, as a negative number. See {@link #pitchMax}. */
  @Export
  public double pitchMin = -80.0;

  @Export
  public double shoulderOffsetLerpSpeed = 4.0;

  @Export
  public double followLerpSpeed = 18.0;

  @Export
  public double fovTweenDuration = 0.5;

  protected ControlRotation controlRotation;

  private Vector3 positionOffset = new Vector3(0, 0.8, 0);
  private Vector3 positionOffsetTarget = new Vector3(0, 0.8, 0);

  // Camera height = stance height + combat offset. Tracked separately so onSetStance and
  // onSetCombatState can each update their part without clobbering the other (both write
  // positionOffsetTarget.Y via applyCameraHeight). Init to the default Y above.
  private double stanceCameraHeight = 0.8;
  private double combatHeightOffset = 0.0;

  private float springArmLengthTarget = 3;

  private double movementFov = 0.0;
  private double cameraFov = 0.0;
  protected boolean combat = false;

  @Export
  public double recoilRecoverySpeed = 8.0;

  private Tween tween;

  /** Last scope state the FOV tween was started for — the edge detector, not a second owner. */
  private boolean scopeApplied = false;

  /** True while the FOV currently on screen came from a scope, so zooming back out uses its pace. */
  private boolean scopeZooming = false;

  /** The scope FOV the last tween was started for, so a zoom-LEVEL change re-tweens too. */
  private double scopeFovApplied = 0.0;

  /**
   * CS's {@code zoom_sensitivity_ratio}: while a scope is raised, look input is scaled by the scoped FOV
   * over the unscoped one, so a pixel of mouse moves the picture the same distance on screen at every
   * zoom level. Without it the 7.5 deg level turns 1 px into ~6 screen px. 1 = CS's default, 0 = off
   * (the raw sensitivity at every zoom).
   */
  @Export
  public double scopedSensitivityRatio = 1.0;

  @Register
  @Override
  public void _ready() {
    yawNode   = (Node3D)      getNode(new NodePath("Yaw"));
    pitchNode = (Node3D)      getNode(new NodePath("Yaw/Pitch"));
    pivotNode = (Node3D)      getNode(new NodePath("Yaw/Pitch/Pivot"));
    springArm = (SpringArm3D) getNode(new NodePath("Yaw/Pitch/Pivot/SpringArm"));
    proxyNode = (Node3D)      getNode(new NodePath("Yaw/Pitch/Pivot/SpringArm/Proxy"));
    if (player != null) {
      springArm.addExcludedObject(player.getRid());
    }


    // Re-resolve the export before reading a single Java field off it. `player` is serialized as
    // node_paths and godot-jvm can hand back a SECOND JVM wrapper for that engine
    // object -- same instance id, different Java object, every Java field at its default. Engine
    // calls work on either (which is why springArm.addExcludedObject above is fine on the raw
    // export), Java state does not, and which exports are affected depends on resolution order and
    // can only be measured. Everything below IS Java state: `controlRotation` is an object
    // identity shared with the FPS rig and MovementController, `isFpsMode` decides which rig owns
    // the camera, and `headMeshes` decides whether the character has a face. See CLAUDE.md,
    // "SOLVED: the player's ~90 degree body rotation".
    Node resolved = player == null ? null : getNodeOrNull(player.getPath());
    if (resolved instanceof Character c) {
      character    = c;
      activeCamera = c.activeCamera;
      controlRotation = c.controlRotation;
      controlRotation.pitchMin = pitchMin;
      controlRotation.pitchMax = pitchMax;
    } else {
      controlRotation = new ControlRotation();
    }

    setAsTopLevel(true);
  }

  /**
   * Returns the look-input delta for this frame as (deltaYawDeg, deltaPitchDeg).
   * Subclasses provide the input source: mouse for the player, AI facing for enemies.
   */
  protected Vector2 gatherLookInput(double delta) {
    return Vector2.Companion.getZERO();
  }

  // NOTE: there is deliberately no getCurrentYaw() here any more, and since AIM_PLAN.md W3 there is
  // nothing for it to return that a caller cannot read directly: the rig's world basis is stated
  // every frame in _physicsProcess, so `yawNode.rotation.y` — the value `set_cam_rotation` emits —
  // IS the world view yaw, and `controlRotation.yaw` is the same number in degrees. It used to be a
  // LOCAL yaw under a frozen parent frame, which is what made a caller add the body's yaw back and
  // hope it had not moved. PlayerController still reads ActiveCamera's own world basis (see its
  // movement block): that is the one node EVERY mode writes — TPS, FPS and the vehicle seat — so it
  // stays the right owner for "which way is the human looking" even now that the rig agrees with it.

  public void changeShoulderDirection() {
    shoulderDirection = shoulderDirection * -1;
    positionOffsetTarget.setX(-positionOffsetTarget.getX());
    setCameraFov();
  }

  @Register
  @Override
  public void _physicsProcess(double delta) {
    Vector2 lookDelta = gatherLookInput(delta);
    controlRotation.yaw   += lookDelta.getX();
    controlRotation.pitch += lookDelta.getY();

    // The rig's world basis is stated OUTRIGHT, every frame, and that is the whole of W3's step 1.
    // `setAsTopLevel(true)` detaches this node from the body but PRESERVES its global transform at
    // the instant it is called, so without this line the rig's parent frame is frozen at whatever
    // the body's yaw happened to be when `_ready()` ran — and `controlRotation.yaw` is then a LOCAL
    // yaw under that frame, not a world direction. Every bug in AIM_PLAN.md's "why the current
    // shape keeps producing these bugs" list came from something reading it as though it were one:
    // `PlayerController` had to add the body's yaw back (and broke the moment a body was rotated
    // after `add_child()`), and `MovementController.aimYaw()`'s fallback returned it raw and put the
    // player 90 degrees off. Identity here plus the flips removed from the scene means
    // `controlRotation` IS the world view rotation, so nothing downstream needs a compensation term.
    // It must be set BEFORE the positioning block, which reads `yawNode`'s global basis.
    setGlobalRotation(Vector3.Companion.getZERO());

    // TPS positioning: smooth shoulder-offset follow.
    positionOffset = positionOffset.lerp(positionOffsetTarget, shoulderOffsetLerpSpeed * delta);
    Vector3 playerBase = player.getGlobalPosition().plus(new Vector3(0, positionOffset.getY(), 0));
    Vector3 yawRight   = yawNode.getGlobalTransform().getBasis().getX();
    Vector3 targetPos  = playerBase.plus(yawRight.times(positionOffset.getX()));
    float followSpeedWeight = combat ? 1.0f : (float) (followLerpSpeed * delta);
    setGlobalPosition(getGlobalPosition().lerp(targetPos, followSpeedWeight));
    springArm.setLength(GD.lerp(springArm.getLength(), springArmLengthTarget, followSpeedWeight));

    // Clamp clean mouse-intent pitch against the LIVE limits, which the STANCE owns
    // (onSetStance writes them into ControlRotation). pitchMin/pitchMax above are only this rig's
    // seed, used until the first changed_stance arrives; reading them here instead would ignore
    // the stance and put the elevation limit in two places.
    controlRotation.pitch =
        GD.clamp(controlRotation.pitch, controlRotation.pitchMin, controlRotation.pitchMax);

    // Decay recoil offsets toward zero each frame
    controlRotation.recoilPitch = GD.lerp(controlRotation.recoilPitch, 0.0, recoilRecoverySpeed * delta);
    controlRotation.recoilYaw   = GD.lerp(controlRotation.recoilYaw,   0.0, recoilRecoverySpeed * delta);

    // The scope's drift is the same kind of thing as recoil — an offset on the view that never touches
    // the mouse intent — so it is advanced here, beside the recoil decay, and added the same way.
    if (character != null) character.tickScopeSway(delta);

    Vector3 yawRot = yawNode.getRotationDegrees();
    yawRot.setY(controlRotation.yaw + controlRotation.recoilYaw + controlRotation.swayYaw);
    yawNode.setRotationDegrees(yawRot);

    Vector3 pitchRot = pitchNode.getRotationDegrees();
    pitchRot.setX(GD.clamp(controlRotation.pitch + controlRotation.recoilPitch + controlRotation.swayPitch,
                           controlRotation.pitchMin, controlRotation.pitchMax));
    pitchNode.setRotationDegrees(pitchRot);

    setCamRotation.emit(yawNode.getRotation().getY());

    // Write this frame's TPS view transform to the shared ActiveCamera when in TPS mode.
    // The Proxy is a child of SpringArm; Godot's SpringArm3D C++ positions it at
    // (0, 0, -current_spring_length) in local space each physics step, correctly
    // handling collision shortening. Reading its global transform is always exact.
    // ...and not while the carrier owns this driver's view: the camera it would write is not the one
    // on screen, and `AimTarget` hangs off it, so writing it moves the very node
    // `Character.applySeatedAimTarget` is placing in world space each frame. See the longer note in
    // FPSCameraController._physicsProcess — there the same seam is an outright feedback loop.
    if (activeCamera != null && (character == null || !character.isFirstPersonView())
            && (character == null || !character.carrierOwnsView())) {
        activeCamera.setGlobalTransform(proxyNode.getGlobalTransform());
    }

    // The scope's FOV rides the same one owner as every other FOV here (setCameraFov). Only the
    // TRANSITION is edge-driven: a tween is a one-shot, so it is started when the derived scope
    // state changes and never per frame. This node processes in every mode and is the base class of
    // both the player's rig and the AI's, so an AI that never scopes simply never sees an edge.
    boolean scopedNow = character != null && character.isScoped();
    double scopeFov = scopedNow && character.weaponController != null
            ? character.weaponController.scopedFovDegrees() : 0.0;
    if (scopedNow != scopeApplied || scopeFov != scopeFovApplied) {
      scopeApplied = scopedNow;
      scopeFovApplied = scopeFov;
      setCameraFov();
    }

    // Head visibility is DERIVED from the live view, every frame, rather than latched at the
    // moment the view is toggled. Latching it is what left the head missing in a vehicle: the
    // player toggled FPS on foot, `setHeadVisible(false)` ran once, and nothing on the way into
    // the seat ever put it back. This node processes in every mode -- it is not the Character,
    // whose _physicsProcess the driver seat switches off -- so it is the one place that always
    // gets a frame. refreshHeadVisibility() only touches the meshes when the answer changes.
    if (character != null) character.refreshHeadVisibility();
  }

  /**
   * The multiplier for this tick's look input — see {@link #scopedSensitivityRatio}. It reads the FOV
   * actually on screen, so it follows the zoom tween, and the bolt cycle's un-zoom, with no edge logic
   * of its own; 1 whenever no scope is raised.
   */
  protected double lookSensitivityScale() {
    if (scopedSensitivityRatio <= 0.0 || character == null || activeCamera == null || !character.isScopeRaised()) {
      return 1.0;
    }
    double unscoped = combat ? cameraFov : movementFov;
    if (unscoped <= 0.0) return 1.0;
    return Math.min(1.0, scopedSensitivityRatio * activeCamera.getFov() / unscoped);
  }

  /** Adds a per-shot kick (degrees) that decays back to zero at recoilRecoverySpeed. */
  public void applyRecoil(double pitchKick, double yawKick) {
    controlRotation.recoilPitch += pitchKick;   // positive pitch is UP, so a kick just adds
    controlRotation.recoilYaw   += yawKick;
  }

  @Register
  public void onSetCombatState(CombatState combatState) {
    combat    = combatState.isCombat();
    cameraFov = combatState.cameraFov;
    positionOffsetTarget.setX(combatState.cameraShoulderOffset * shoulderDirection);
    springArmLengthTarget = (float) combatState.cameraDistance;
    combatHeightOffset = combatState.cameraHeightOffset;
    applyCameraHeight();
    setCameraFov();
  }

  @Register
  public void onSetMovementState(MovementState movementState) {
    movementFov = movementState.getCameraFov();
    setCameraFov();
  }

  private void setCameraFov() {
    // activeCamera is assigned from character.activeCamera in _ready(), but _ready() runs
    // bottom-up: this node's _ready() fires before Character._ready() assigns activeCamera.
    // Resolve it lazily here so the first changedMovementState/changedCombatState signal
    // from Character._ready() still applies the correct FoV.
    if (activeCamera == null && character != null) activeCamera = character.activeCamera;
    if (activeCamera == null) return;

    if (tween != null && tween.isValid()) {
      tween.kill();
    }

    double targetFov = combat ? cameraFov : movementFov;
    double duration  = fovTweenDuration;

    // A scope overrides every other FOV source while it is up, and supplies its own (short)
    // transition in BOTH directions — the weapon is the DATA and this method stays the single writer
    // of the camera's FOV. `scopeApplied` is the state the edge in _physicsProcess just committed,
    // not a live read, so zooming out is driven from here too rather than from a second place.
    if (character != null && character.weaponController != null) {
      double scopedFov = character.weaponController.scopedFovDegrees();
      if (scopeApplied && scopedFov > 0.0) {
        targetFov = scopedFov;
        duration  = character.weaponController.scopeZoomSeconds();
      } else if (scopeZooming) {
        // Coming back out: the same short time, so the scope does not leave a half-second of
        // slow zoom behind it (fovTweenDuration is the combat/sprint FOV's pace, not a scope's).
        duration = character.weaponController.scopeZoomSeconds();
      }
    }
    scopeZooming = scopeApplied;

    tween = createTween();
    tween.tweenProperty(activeCamera, "fov", targetFov, duration)
         .setTrans(Tween.TransitionType.SINE)
         .setEase(Tween.EaseType.OUT);
  }

  @Register
  public void onSetStance(Stance stance) {
    stanceCameraHeight = stance.getCameraHeight();
    applyCameraHeight();

    // The stance owns the elevation limit -- see Stance.viewPitchMax for why it lives on the
    // camera and not on the aim modifiers. Published into ControlRotation so BOTH rigs read one
    // number: this one clamps below, FPSCameraController clamps from the same pair.
    controlRotation.pitchMax = stance.getViewPitchMax();
    controlRotation.pitchMin = stance.getViewPitchMin();
    // Re-clamp immediately: a stance that narrows the range (standing up -> going prone) must not
    // leave the view held one frame outside its own new limit.
    controlRotation.pitch =
        GD.clamp(controlRotation.pitch, controlRotation.pitchMin, controlRotation.pitchMax);
  }

  /** Combine the stance base height with the combat-state offset into the camera's Y target. */
  private void applyCameraHeight() {
    positionOffsetTarget.setY(stanceCameraHeight + combatHeightOffset);
  }
}
