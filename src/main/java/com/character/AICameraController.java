package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

@RegisterClass(className = "AICameraController")
public class AICameraController extends TPSCameraController {

  // World-space aim target; null = fall back to body-facing direction.
  private Vector3 aimTarget = null;

  /**
   * Maximum camera rotation speed in degrees per second.
   * Caps how fast the AI can swing its aim, making it look like it's actually tracking
   * rather than teleporting. Does not affect shot accuracy — snapAimRay() handles that.
   * Lower values make the AI feel slower to react visually; 0 = unlimited (old behaviour).
   */
  @Export
  @RegisterProperty
  public float aimTrackingDegreesPerSec = 90.0f;

  @RegisterFunction
  @Override
  public void _ready() {
    super._ready();
    // No explicit clearCurrent() here: activeCamera is still null at this point
    // (this _ready() runs bottom-up, before Character._ready() resolves it — see
    // TPSCameraController.setCameraFov's comment), so the call was always a no-op.
    // Character.activateCameraIfOwned() (deferred from Character._ready()) is the
    // single place that claims the viewport — an AI body that's never local simply
    // never calls makeCurrent() for itself, so it never needs to relinquish anything.
  }

  public void setAimTarget(Vector3 worldTarget) { this.aimTarget = worldTarget; }
  public void clearAimTarget()                  { this.aimTarget = null; }

  /**
   * When an aim target is set, drives Yaw/Pitch toward that world position so the
   * AimRay converges on the target across frames.
   *
   * Camera forward = (cos(p)*sin(y), -sin(p), cos(p)*cos(y)).
   * Inverting: targetYaw = atan2(dx, dz), targetPitch = -atan2(dy, hDist).
   *
   * Without an aim target, falls back to tracking the character body's facing direction.
   */
  @Override
  protected Vector2 gatherLookInput(double delta) {
    if (aimTarget != null) {
      Vector3 myPos = getGlobalPosition();
      double  dx    = aimTarget.getX() - myPos.getX();
      double  dy    = aimTarget.getY() - myPos.getY();
      double  dz    = aimTarget.getZ() - myPos.getZ();
      double  hDist = Math.sqrt(dx * dx + dz * dz);

      double targetYawDeg   = Math.toDegrees(Math.atan2(-dx, -dz));
      double targetPitchDeg = (hDist > 0.01) ? -Math.toDegrees(Math.atan2(dy, hDist)) : 0.0;

      double deltaYaw   = GD.wrapf(targetYawDeg - controlRotation.yaw,  -180.0, 180.0);
      double deltaPitch = targetPitchDeg - controlRotation.pitch;

      // Clamp rotation speed so the camera tracks at a finite rate rather than snapping.
      if (aimTrackingDegreesPerSec > 0f) {
        double cap = aimTrackingDegreesPerSec * delta;
        deltaYaw   = GD.clamp(deltaYaw,   -cap, cap);
        deltaPitch = GD.clamp(deltaPitch, -cap, cap);
      }

      return new Vector2((float) deltaYaw, (float) deltaPitch);
    }

    // Default: track character body facing, pitch returns level.
    // Both deltas are clamped exactly like the aim-target branch above — otherwise
    // losing/clearing the aim target (combat → patrol, target killed, LoS lost)
    // makes the camera snap instantly to the body's facing/level pitch in one frame.
    double characterYawDeg = Math.toDegrees(player.getRotation().getY());
    double targetYaw       = -characterYawDeg;
    double deltaYaw        = GD.wrapf(targetYaw - controlRotation.yaw, -180.0, 180.0);
    double deltaPitch      = -controlRotation.pitch;

    if (aimTrackingDegreesPerSec > 0f) {
      double cap = aimTrackingDegreesPerSec * delta;
      deltaYaw   = GD.clamp(deltaYaw,   -cap, cap);
      deltaPitch = GD.clamp(deltaPitch, -cap, cap);
    }

    return new Vector2((float) deltaYaw, (float) deltaPitch);
  }
}
