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
  public double combatSpeedFactor = 1.0f;

  @Export
  @RegisterProperty
  public double combatAccelerationFactor = 1.0f;


  // Default constructor is required for Godot to instantiate the Resource
  public CombatState() {
    super();
  }

  public boolean isCombat() {
    return combat;
  }

  public double getCombatSpeedFactor() {
    return combatSpeedFactor;
  }

  public double getCombatAccelerationFactor() {
    return combatAccelerationFactor;
  }
}