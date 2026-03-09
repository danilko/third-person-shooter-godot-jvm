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

  // A default constructor is required for Godot to instantiate the Resource
  public MovementState() {
    super();
  }
}