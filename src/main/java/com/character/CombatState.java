package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;

@RegisterClass(className = "CombatState")
public class CombatState extends Resource {

  @Export
  @RegisterProperty
  public boolean combat = false;

  @Export
  @RegisterProperty
  public double speedFactor = 1.0f;

  @Export
  @RegisterProperty
  public double accelerationFactor = 1.0f;

  @Export
  @RegisterProperty
  public double cameraDistance = 2.0f;

  @Export
  @RegisterProperty
  public double cameraShoulderOffset = 0.1f;

  /**
   * Vertical camera adjustment applied ON TOP of the current stance's camera height while in
   * this combat state. An OFFSET (not an absolute height) so it composes with stances —
   * crouch-aim stays lower than stand-aim. Negative lowers the camera toward the gun line for
   * a tight over-the-shoulder aim (RE4/PUBG style); 0 leaves the stance height unchanged.
   */
  @Export
  @RegisterProperty
  public double cameraHeightOffset = 0.0f;

  @Export
  @RegisterProperty
  public double cameraFov = 70.0f;


  // Default constructor is required for Godot to instantiate the Resource
  public CombatState() {
    super();
  }

  public boolean isCombat() {
    return combat;
  }

  public double getSpeedFactor() {
    return speedFactor;
  }

  public double getAccelerationFactor() {
    return accelerationFactor;
  }
}