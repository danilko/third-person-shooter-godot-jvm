package com.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.*;
import godot.annotation.Export;
import godot.annotation.RegisterProperty;
import godot.core.*;
import godot.global.GD;
import java.util.HashMap;
import java.util.Map;

@RegisterClass(className = "AnimationController")
public class AnimationController extends Node {

  @RegisterProperty
  @Export
  public AnimationTree animationTree;

  @RegisterProperty
  @Export
  public CharacterBody3D player;

  @RegisterProperty
  @Export
  public TwoBoneIK3D aimIk;

  @RegisterProperty
  @Export
  public LookAtModifier3D aimSpineModifier;

  @RegisterProperty
  @Export
  public Marker3D weaponIKTarget;

  /** Base weapon hold position in camera-local space (upright, no stance offset). */
  @Export
  @RegisterProperty
  public Vector3 weaponIKBasePosition = new Vector3(0.1f, -0.15f, -0.5f);

  @Export
  @RegisterProperty
  public double animationBlendDuration = 0.25;

  @Export
  @RegisterProperty
  public double animationSpeedDuration = 0.7;

  @Export
  @RegisterProperty
  public double floorBlendSpeed = 10.0;

  /**
   * When true the incoming movementDirection is world-space (AI). The blend rotates it
   * into camera-local space so strafe animations play relative to the facing direction.
   */
  @Export
  @RegisterProperty
  public boolean worldSpaceMovement = false;

  // NodePath for the animation speed parameter never changes — build it once.
  private static final NodePath ANIM_SPEED_PATH = new NodePath("parameters/MovementAnimSpeed/scale");

  private double camRotation = 0.0;
  private double onFloorBlend = 1.0;
  private double onFloorBlendTarget = 1.0;
  private Tween tween;
  private String currentStanceName = "Upright";
  private Stance currentStance = null;
  private boolean combat = false;
  private Vector2 movementDirection = new Vector2();
  private Vector2 animationDirection = new Vector2();
  private MovementState currentMovementState = null;
  // Cached NodePaths for per-stance blend parameters — populated lazily (one allocation per stance).
  private final Map<String, NodePath> blendPathCache = new HashMap<>();


  @RegisterFunction
  @Override
  public void _physicsProcess(double delta) {
    if (player == null || animationTree == null) return;
    // Skip entirely for LOD-frozen AIs — they hold their last pose with zero JVM bridge cost.
    if (player instanceof AICharacter ai && ai.isLodFrozen()) return;

    onFloorBlendTarget = player.isOnFloor() ? 1.0 : 0.0;
    double newBlend = GD.lerp(onFloorBlend, onFloorBlendTarget, floorBlendSpeed * delta);
    // Only write to the AnimationTree when the value actually changes — eliminates
    // ~1,920 unconditional JVM bridge calls/sec for 32 grounded AIs at 60 Hz.
    if (Math.abs(newBlend - onFloorBlend) > 0.001) {
      onFloorBlend = newBlend;
      animationTree.set("parameters/OnFloorBlend/blend_amount", onFloorBlend);
    } else {
      onFloorBlend = newBlend;
    }
  }

  @RegisterFunction
  public void jump(JumpState jumpState) {
    if (animationTree == null) return;
    // Do not kill the movement blend tween — the jump OneShot plays on top of the
    // movement blend, so we want the blend to continue smoothly while airborne.
    String path = "parameters/" + jumpState.getAnimationName() + "/request";
    animationTree.set(path, AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @RegisterFunction
  public void roll(RollState rollState) {
    if (animationTree == null) return;
    // Same reasoning as jump: the roll OneShot is independent of movement blending.
    String path = "parameters/" + rollState.getAnimationName() + "/request";
    animationTree.set(path, AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @RegisterFunction
  public void onSetMovementState(MovementState movementState) {
    currentMovementState = movementState;
    updateAnimationBlend(movementState);
  }

  /**
   * Story/cutscene hook: forces WeaponBlend to 0 (no weapon pose) or restores it to 1.
   * Not called during normal slot switching — all weapons including fist use WeaponBlend = 1.
   */
  public void setHolster(boolean holster) {
    if (animationTree == null) return;
    animationTree.set("parameters/WeaponBlend/blend_position", holster ? 0 : 1);
  }

  public void onWeaponEquip(int animationWeaponIndex) {
    animationTree.set("parameters/WeaponAim/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponHold/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponChangeAnimation/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponChange/request", AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @RegisterFunction
  public void onWeaponReload() {
    animationTree.set("parameters/Reload/request", AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @RegisterFunction
  public void onSetStance(Stance stance) {
    if (animationTree == null) return;

    animationTree.set("parameters/StanceTransition/transition_request", stance.getName().toString());
    this.currentStanceName = stance.getName().toString();
    this.currentStance = stance;

    updateAimModifiers();
  }

  @RegisterFunction
  public void onSetCombatState(CombatState combatState) {
    if (animationTree == null) return;
    combat = combatState.isCombat();
    animationTree.set("parameters/CombatTransition/transition_request", combat ? "Combat" : "NoCombat");
    animationTree.set("parameters/NeckFront/blend_amount", combat ? 1 : 0);
    if (aimIk != null) aimIk.setActive(combat);
    updateAimModifiers();
  }

  private void updateAimModifiers() {
    if (currentStance == null) return;
    if (weaponIKTarget != null) {
      weaponIKTarget.setPosition(weaponIKBasePosition.plus(currentStance.getWeaponIKOffset()));
    }
    // Enable spine modifier only in combat and when the stance permits it (angle > 0).
    if (aimSpineModifier != null) {
      aimSpineModifier.setActive(combat && currentStance.getSpineAimMaxAngle() > 0);
    }
  }

  @RegisterFunction
  public void onSetCamRotation(double newCamRotation) {
    camRotation = newCamRotation;
  }

  @RegisterFunction
  public void onSetMovementDirection(Vector3 movementDirection) {
    double dx = movementDirection.getX();
    double dz = movementDirection.getZ();
    if (worldSpaceMovement && combat) {
      // Rotate world-space direction into camera-local space so the strafe blend
      // plays relative to the mesh facing direction rather than world axes.
      double cos = Math.cos(-camRotation), sin = Math.sin(-camRotation);
      double lx = dx * cos - dz * sin;
      double lz = dx * sin + dz * cos;
      dx = lx;
      dz = lz;
    }
    this.movementDirection.setX(dx == 0 ? 0 : dx > 0 ? 1 : -1);
    this.movementDirection.setY(dz == 0 ? 0 : dz > 0 ? 1 : -1);

    updateAnimationBlend(currentMovementState);
  }


  private void updateAnimationBlend(MovementState movementState) {
    if (animationTree == null || currentMovementState == null) return;

    if (tween != null && tween.isValid()) tween.kill();
    tween = createTween();

    if (combat) {
      int id = Math.min(movementState.getId(), 1);
      // The animation is opposite of the direction calculation
      animationDirection.setX(id * movementDirection.getX() * -1);
      animationDirection.setY(id * movementDirection.getY());
    } else {
      animationDirection.setX(0.0f);
      animationDirection.setY(movementState.getId());
    }

    NodePath blendPath = blendPathCache.computeIfAbsent(currentStanceName,
        name -> new NodePath("parameters/" + name + "MovementBlend/blend_position"));
    tween.tweenProperty(animationTree, blendPath, animationDirection, animationBlendDuration);
    tween.parallel().tweenProperty(animationTree, ANIM_SPEED_PATH, movementState.animationSpeed, animationSpeedDuration);
  }
}