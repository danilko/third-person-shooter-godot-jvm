package com.character;

import godot.annotation.RegisterProperty;
import godot.api.Resource;
import godot.annotation.Export;
import godot.annotation.RegisterClass;

@RegisterClass(className = "MovementState")
public class MovementState extends Resource {

  public int getId() {
    return id;
  }

  public float getMovementSpeed() {
    return movementSpeed;
  }

  public float getAcceleration() {
    return acceleration;
  }

  public float getCameraFov() {
    return cameraFov;
  }

  public float getAnimationSpeed() {
    return animationSpeed;
  }

  public float getNoiseLevel() {
    return noiseLevel;
  }

  @Export
  @RegisterProperty
  public int id = 0;

  @Export
  @RegisterProperty
  public float movementSpeed = 0.0f;

  @Export
  @RegisterProperty
  public float acceleration = 6.0f;

  @Export
  @RegisterProperty
  public float cameraFov = 75.0f;

  @Export
  @RegisterProperty
  public float animationSpeed = 1.0f;

  /**
   * How loud / detectable this movement is, 0 (silent) … 1 (full footstep noise) and
   * optionally above 1 for extra-loud. Scaffolding for the planned stealth model: the
   * future audio / AI-awareness system scales footstep volume and enemy hearing range by
   * this. WALK (the Shift "stealth walk") is quiet; SPRINT (default run) is loud; IDLE
   * is near-silent. Crouch/crawl variants are quieter still. Not wired to anything yet.
   */
  @Export
  @RegisterProperty
  public float noiseLevel = 1.0f;

  // A default constructor is required for Godot to instantiate the Resource
  public MovementState() {
    super();
  }
}