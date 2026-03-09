package com.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;
import godot.annotation.Export;

@RegisterClass(className = "JumpState")
public class JumpState extends Resource {

  public String getAnimationName() {
    return animationName;
  }

  public double getJumpHeight() {
    return jumpHeight;
  }

  public double getApexDuration() {
    return apexDuration;
  }

  @Export
  @RegisterProperty
  public String animationName = "";

  @Export
  @RegisterProperty
  public double jumpHeight = 4.0;

  @Export
  @RegisterProperty
  public double apexDuration = 0.5;

  // Default constructor is required for Godot to instantiate the Resource
  public JumpState() {
    super();
  }
}