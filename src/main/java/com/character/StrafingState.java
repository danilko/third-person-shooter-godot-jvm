package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;

@RegisterClass(className = "StrafingState")
public class StrafingState extends Resource {

  @Export
  @RegisterProperty
  public boolean strafing = false;

  @Export
  @RegisterProperty
  public float movementSpeedFactor = 1.0f;

  @Export
  @RegisterProperty
  public float strafingMovementAccelerationFactor = 1.0f;


  // Default constructor is required for Godot to instantiate the Resource
  public StrafingState() {
    super();
  }

  public boolean isStrafing() {
    return strafing;
  }

  public float getMovementSpeedFactor() {
    return movementSpeedFactor;
  }

  public float getStrafingMovementAccelerationFactor() {
    return strafingMovementAccelerationFactor;
  }
}