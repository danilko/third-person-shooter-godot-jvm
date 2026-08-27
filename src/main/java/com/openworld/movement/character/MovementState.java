package com.openworld.movement.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

@Script(className = "MovementState")
public class MovementState extends Resource {

  public int getId() {
    return id;
  }

  /** Setter half of the exported {@code id} property. */
  public void setId(int value) {
    this.id = value;
  }

  public float getMovementSpeed() {
    return movementSpeed;
  }

  /** Setter half of the exported {@code movementSpeed} property. */
  public void setMovementSpeed(float value) {
    this.movementSpeed = value;
  }

  public float getAcceleration() {
    return acceleration;
  }

  /** Setter half of the exported {@code acceleration} property. */
  public void setAcceleration(float value) {
    this.acceleration = value;
  }

  public float getCameraFov() {
    return cameraFov;
  }

  /** Setter half of the exported {@code cameraFov} property. */
  public void setCameraFov(float value) {
    this.cameraFov = value;
  }

  public float getAnimationSpeed() {
    return animationSpeed;
  }

  /** Setter half of the exported {@code animationSpeed} property. */
  public void setAnimationSpeed(float value) {
    this.animationSpeed = value;
  }

  public float getNoiseLevel() {
    return noiseLevel;
  }

  /** Setter half of the exported {@code noiseLevel} property. */
  public void setNoiseLevel(float value) {
    this.noiseLevel = value;
  }

  @Export
  public int id = 0;

  @Export
  public float movementSpeed = 0.0f;

  @Export
  public float acceleration = 6.0f;

  @Export
  public float cameraFov = 75.0f;

  @Export
  public float animationSpeed = 1.0f;

  /**
   * How loud / detectable this movement is, 0 (silent) … 1 (full footstep noise) and
   * optionally above 1 for extra-loud. Scaffolding for the planned stealth model: the
   * future audio / AI-awareness system scales footstep volume and enemy hearing range by
   * this. WALK (the Shift "stealth walk") is quiet; SPRINT (default run) is loud; IDLE
   * is near-silent. Crouch/crawl variants are quieter still. Not wired to anything yet.
   */
  @Export
  public float noiseLevel = 1.0f;

  // A default constructor is required for Godot to instantiate the Resource
  public MovementState() {
    super();
  }
}
