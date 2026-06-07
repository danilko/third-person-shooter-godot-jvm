package com.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.InputEventMouseMotion;
import godot.core.Vector2;

@RegisterClass(className = "PlayerCameraController")
public class PlayerCameraController extends TPSCameraController {

  // Accumulated raw pixel deltas from all mouse-motion events since last physics step.
  // Using _input + getRelative() (the same pattern as VehicleCameraController) captures
  // every mouse event between physics frames; getLastMouseVelocity()*delta only reads
  // the last event velocity and drops all intermediate events.
  private double pendingYaw   = 0;
  private double pendingPitch = 0;

  @RegisterFunction
  @Override
  public void _ready() {
    super._ready();
    Input.setMouseMode(Input.MouseMode.CAPTURED);
    if (activeCamera != null) activeCamera.makeCurrent();
  }

  @RegisterFunction
  @Override
  public void _input(InputEvent event) {
    if (event instanceof InputEventMouseMotion mm) {
      pendingYaw   -= mm.getRelative().getX() * yawSensitivity;
      pendingPitch += mm.getRelative().getY() * pitchSensitivity;
    }
  }

  @Override
  protected Vector2 gatherLookInput(double delta) {
    boolean isFps = player instanceof Character c && c.isFpsMode;

    if (Input.isActionJustPressed("shoulder", false) && !isFps) {
      changeShoulderDirection();
    }

    if (Input.isActionJustPressed("view", false)) {
      if (player instanceof Character c) c.setCameraMode(!c.isFpsMode);
    }

    double dy = pendingYaw;
    double dp = pendingPitch;
    pendingYaw   = 0;
    pendingPitch = 0;
    return new Vector2((float) dy, (float) dp);
  }
}
