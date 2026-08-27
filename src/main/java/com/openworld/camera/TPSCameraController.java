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

  @Export
  public double pitchMax = 75.0;

  @Export
  public double pitchMin = -55.0;

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


    if (player instanceof Character c) {
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

  /** Camera yaw in radians — read by PlayerController to rotate WASD input to world-space each tick. */
  public double getCurrentYaw() {
    return yawNode != null ? yawNode.getRotation().getY() : 0.0;
  }

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

    // TPS positioning: smooth shoulder-offset follow.
    positionOffset = positionOffset.lerp(positionOffsetTarget, shoulderOffsetLerpSpeed * delta);
    Vector3 playerBase = player.getGlobalPosition().plus(new Vector3(0, positionOffset.getY(), 0));
    Vector3 yawRight   = yawNode.getGlobalTransform().getBasis().getX();
    Vector3 targetPos  = playerBase.plus(yawRight.times(positionOffset.getX()));
    float followSpeedWeight = combat ? 1.0f : (float) (followLerpSpeed * delta);
    setGlobalPosition(getGlobalPosition().lerp(targetPos, followSpeedWeight));
    springArm.setLength(GD.lerp(springArm.getLength(), springArmLengthTarget, followSpeedWeight));

    // Clamp clean mouse-intent pitch
    controlRotation.pitch = GD.clamp(controlRotation.pitch, pitchMin, pitchMax);

    // Decay recoil offsets toward zero each frame
    controlRotation.recoilPitch = GD.lerp(controlRotation.recoilPitch, 0.0, recoilRecoverySpeed * delta);
    controlRotation.recoilYaw   = GD.lerp(controlRotation.recoilYaw,   0.0, recoilRecoverySpeed * delta);

    Vector3 yawRot = yawNode.getRotationDegrees();
    yawRot.setY(controlRotation.yaw + controlRotation.recoilYaw);
    yawNode.setRotationDegrees(yawRot);

    Vector3 pitchRot = pitchNode.getRotationDegrees();
    pitchRot.setX(GD.clamp(controlRotation.pitch + controlRotation.recoilPitch, pitchMin, pitchMax));
    pitchNode.setRotationDegrees(pitchRot);

    setCamRotation.emit(yawNode.getRotation().getY());

    // Write this frame's TPS view transform to the shared ActiveCamera when in TPS mode.
    // The Proxy is a child of SpringArm; Godot's SpringArm3D C++ positions it at
    // (0, 0, -current_spring_length) in local space each physics step, correctly
    // handling collision shortening. Reading its global transform is always exact.
    if (activeCamera != null && (character == null || !character.isFpsMode)) {
        activeCamera.setGlobalTransform(proxyNode.getGlobalTransform());
    }
  }

  /** Adds a per-shot kick (degrees) that decays back to zero at recoilRecoverySpeed. */
  public void applyRecoil(double pitchKick, double yawKick) {
    // TPS: double-180°Y cancellation makes positive pitch = look down, so subtract to kick up.
    controlRotation.recoilPitch -= pitchKick;
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

    tween = createTween();
    tween.tweenProperty(activeCamera, "fov", targetFov, fovTweenDuration)
         .setTrans(Tween.TransitionType.SINE)
         .setEase(Tween.EaseType.OUT);
  }

  @Register
  public void onSetStance(Stance stance) {
    stanceCameraHeight = stance.getCameraHeight();
    applyCameraHeight();
  }

  /** Combine the stance base height with the combat-state offset into the camera's Y target. */
  private void applyCameraHeight() {
    positionOffsetTarget.setY(stanceCameraHeight + combatHeightOffset);
  }
}
