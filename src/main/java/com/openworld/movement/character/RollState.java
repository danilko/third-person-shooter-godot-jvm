package com.openworld.movement.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.CollisionShape3D;
import godot.api.RayCast3D;
import godot.api.Resource;

@Script(className = "RollState")
public class RollState extends Resource {

  @Export
  public String animationName = "";

  @Export
  public double rollSpeed = 8.0;

  @Export
  public double rollDuration = 0.7;

  // Default constructor is required for Godot to instantiate the Resource
  public RollState() {
    super();
  }

  public String getAnimationName() {
    return animationName;
  }

  /** Setter half of the exported {@code animationName} property. */
  public void setAnimationName(String value) {
    this.animationName = value;
  }

  public double getRollSpeed() {
    return rollSpeed;
  }

  /** Setter half of the exported {@code rollSpeed} property. */
  public void setRollSpeed(double value) {
    this.rollSpeed = value;
  }

  public double getRollDuration() {
    return rollDuration;
  }

  /** Setter half of the exported {@code rollDuration} property. */
  public void setRollDuration(double value) {
    this.rollDuration = value;
  }
}
