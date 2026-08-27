package com.openworld.movement.character;

import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.RayCast3D;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.core.VariantArray;
import godot.core.Vector3;
import godot.global.GD;

@Script
public class Stance extends Node {

  // --- Movement States ---
  @Export
  public MovementState idleState;

  @Export
  public MovementState walkState;

  @Export
  public MovementState sprintState;

  // --- Camera Data ---
  @Export
  public double cameraHeight = 1.3;

  // --- Animation ---

  /**
   * Optional override for the AnimationTree stance key. When empty (default) the stance's
   * Godot node name drives the {@code StanceTransition} request and {@code …MovementBlend}
   * path. Set this to reuse another stance's animation states — e.g. the SWIM stance sets
   * {@code "Crawl"} as a placeholder until a dedicated swim AnimationTree state exists (I1).
   */
  @Export
  public String animationStanceKey = "";

  // --- Aim / IK ---

  /** Local offset added to WeaponIKTarget's base position for this stance. */
  @Export
  public Vector3 weaponIKOffset = new Vector3(0, 0, 0);

  /**
   * Max rotation angle (degrees) allowed for the spine LookAtModifier3D in this stance.
   * Set to 0 to disable the spine aim modifier entirely for stances where it produces artefacts.
   */
  @Export
  public float spineAimMaxAngle = 60.0f;

  // --- Collision ---
  @Export
  public CollisionShape3D collider;

  @Export
  public RayCast3D colRaycast;

  /**
   * Stances that require more vertical clearance than this one (i.e. taller stances).
   *
   * When {@code colRaycast} detects a ceiling obstruction, all stances listed here
   * are also considered blocked — preventing the character from standing up into a
   * surface even if they are not the direct target of the transition.
   *
   * Example: Crawl.higherStances = [Crouch, Upright].  When crawling under a low
   * ceiling, neither Crouch nor Upright can be entered until the ceiling clears.
   *
   * Inspector: assign the sibling Stance nodes that are blocked by this stance's ceiling raycast.
   *
   * Typed to {@code Node} (not {@code Stance}) deliberately: a typed {@code Array[Stance]}
   * export hint holds a strong reference to the {@code Stance.gdj} GdjScript that is never
   * released, leaving it "in use at exit" (the long-standing shutdown leak). {@code Node} is a
   * built-in class (no script resource), so the hint references nothing to leak — and Stance
   * IS a Node, so assigning sibling stances still works. {@link #isBlocked} narrows back.
   */
  @Export
  public VariantArray<Node> higherStances = new VariantArray<>(Node.class);

  /**
   * Returns true if this stance's space is obstructed (ceiling too low).
   * Also returns true if any of the {@link #higherStances} are themselves blocked,
   * preventing an upward transition that would collide.
   */
  @Register
  public boolean isBlocked() {
    if (colRaycast != null && colRaycast.isColliding()) return true;
    for (Node taller : higherStances) {
      if (taller instanceof Stance s && s.isBlocked()) return true;
    }
    return false;
  }

  public MovementState getIdleState() {
    return idleState;
  }

  public void setIdleState(MovementState idleState) {
    this.idleState = idleState;
  }

  public MovementState getWalkState() {
    return walkState;
  }

  public void setWalkState(MovementState walkState) {
    this.walkState = walkState;
  }


  public MovementState getSprintState() {
    return sprintState;
  }

  public void setSprintState(MovementState sprintState) {
    this.sprintState = sprintState;
  }

  public String getAnimationStanceKey() { return animationStanceKey; }
  public void setAnimationStanceKey(String v) { this.animationStanceKey = v; }

  public double getCameraHeight() { return cameraHeight; }
  public void setCameraHeight(double v) { this.cameraHeight = v; }

  public Vector3 getWeaponIKOffset() { return weaponIKOffset; }
  public void setWeaponIKOffset(Vector3 v) { this.weaponIKOffset = v; }

  public float getSpineAimMaxAngle() { return spineAimMaxAngle; }
  public void setSpineAimMaxAngle(float v) { this.spineAimMaxAngle = v; }

  public CollisionShape3D getCollider() {
    return collider;
  }

  public void setCollider(CollisionShape3D collider) {
    this.collider = collider;
  }

  public RayCast3D getColRaycast() {
    return colRaycast;
  }

  public void setColRaycast(RayCast3D colRaycast) {
    this.colRaycast = colRaycast;
  }

  public VariantArray<Node> getHigherStances() {
    return higherStances;
  }

  public void setHigherStances(VariantArray<Node> higherStances) {
    this.higherStances = higherStances;
  }

  public MovementState getMovementState(MovementType type) {
    switch (type) {
      case IDLE:   return idleState;
      case WALK:   return walkState;
      case SPRINT: return sprintState;
      default:
        return idleState;
    }
  }
}