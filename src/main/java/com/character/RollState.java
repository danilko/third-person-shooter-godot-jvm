package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.CollisionShape3D;
import godot.api.RayCast3D;
import godot.api.Resource;

@RegisterClass(className = "RollState")
public class RollState extends Resource {

  @Export
  @RegisterProperty
  public String animationName = "";

  @Export
  @RegisterProperty
  public double rollSpeed = 8.0;

  @Export
  @RegisterProperty
  public double rollDuration = 0.7;

  // Default constructor is required for Godot to instantiate the Resource
  public RollState() {
    super();
  }

  public String getAnimationName() {
    return animationName;
  }

  public double getRollSpeed() {
    return rollSpeed;
  }

  public double getRollDuration() {
    return rollDuration;
  }
}
