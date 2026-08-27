package com.openworld.movement.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

@Script(className = "JumpState")
public class JumpState extends Resource {

  public String getAnimationName() {
    return animationName;
  }

  /** Setter half of the exported {@code animationName} property. */
  public void setAnimationName(String value) {
    this.animationName = value;
  }

  public double getJumpHeight() {
    return jumpHeight;
  }

  /** Setter half of the exported {@code jumpHeight} property. */
  public void setJumpHeight(double value) {
    this.jumpHeight = value;
  }

  public double getApexDuration() {
    return apexDuration;
  }

  /** Setter half of the exported {@code apexDuration} property. */
  public void setApexDuration(double value) {
    this.apexDuration = value;
  }

  @Export
  public String animationName = "";

  @Export
  public double jumpHeight = 4.0;

  @Export
  public double apexDuration = 0.5;

  // Default constructor is required for Godot to instantiate the Resource
  public JumpState() {
    super();
  }
}
