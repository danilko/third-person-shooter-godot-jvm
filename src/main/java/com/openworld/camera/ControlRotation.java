package com.openworld.camera;

import com.openworld.character.Character;

/**
 * Canonical view direction for a character — equivalent to Unreal's AController::ControlRotation.
 * Owned by Character; all camera modes (TPS, FPS) read from this, none own it.
 *
 * pitchMin / pitchMax are populated by CameraController._ready() from its @Export values so
 * FPSCameraController can clamp pitch without referencing the TPS camera directly.
 */
public class ControlRotation {
    public double yaw         = 0.0;
    public double pitch       = 0.0;
    public double recoilPitch = 0.0;
    public double recoilYaw   = 0.0;
    public double pitchMin    = -55.0;
    public double pitchMax    =  75.0;
}
