package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Vector3;
import godot.global.GD;

import static godot.api.Input.INSTANCE;

/**
 * Follow camera for a vehicle.
 *
 * Position (all modes)
 * ─────────────────────
 * Uses the original world-space "fromTarget" approach: each tick the camera
 * maintains its current world-space offset from the vehicle, clamped to
 * [minDistance, maxDistance] at a fixed height.  This gives the natural
 * "floaty drag" through turns and acceleration with no explicit yaw-follow
 * parameters to tune.
 *
 * Orientation
 * ────────────
 *   Follow mode (no occupant, or occupant not pressing aim/fire):
 *     lookAtFromPosition toward the vehicle centre every tick.
 *     If the occupant was aiming, yaw/pitch bleed back toward the vehicle
 *     heading at aimRecoverySpeed so the next aim starts from a sensible
 *     direction.
 *
 *   Aim mode (PASSENGER_WEAPON occupant holding aim or fire):
 *     Camera orientation = mouse-driven yaw/pitch.  The AimRay (child of
 *     Camera3D) shoots along the look direction for weapon use.
 *
 * Racing mode: set weaponModeIndex = 0 (NONE) on the Vehicle.
 *   passengerAimMode never activates → camera always follows.
 */
@RegisterClass(className = "VehicleCameraController")
public class VehicleCameraController extends Node3D {

    @RegisterProperty @Export public float minDistance       = 4.0f;
    @RegisterProperty @Export public float maxDistance       = 8.0f;
    @RegisterProperty @Export public float height            = 3.0f;
    /** How fast yaw/pitch recover toward vehicle heading when aim/fire is released. */
    @RegisterProperty @Export public float aimRecoverySpeed  = 3.0f;
    @RegisterProperty @Export public float cameraSensitivity = 0.001f;
    @RegisterProperty @Export public float minPitch          = -1.2f;
    @RegisterProperty @Export public float maxPitch          =  0.2f;

    private static final float DEFAULT_PITCH = -0.3f;

    private Node3D    target;
    private Camera3D  camera3D;
    private RayCast3D aimRay;

    private boolean passengerAimMode = false;
    private float   yaw   = 0f;
    private float   pitch = DEFAULT_PITCH;

    @RegisterFunction
    @Override
    public void _ready() {
        target   = (Node3D) getOwner();
        camera3D = (Camera3D) getNode("Camera3D");
        aimRay   = (RayCast3D) getNodeOrNull("Camera3D/AimRay");
        // Decouple from the vehicle's RigidBody3D so physics angular jitter
        // never propagates to the camera.
        setAsTopLevel(true);
    }

    // ── Public API ────────────────────────────────────────────────────────────

    public void setPassengerAimMode(boolean enabled) {
        passengerAimMode = enabled;
        if (enabled) {
            // Seed aim yaw/pitch from the camera's current look direction so
            // there is no jump when aim mode first activates.
            Vector3 rot = camera3D.getGlobalRotation();
            yaw   = (float) rot.getY();
            pitch = (float) rot.getX();
        } else {
            pitch = DEFAULT_PITCH;
        }
    }

    /**
     * World-space point the AimRay is hitting.
     * Used by Vehicle to relay the aim target to the occupant's weapon.
     */
    public Vector3 getAimTarget() {
        if (aimRay == null) return target.getGlobalPosition();
        if (aimRay.isColliding()) return aimRay.getCollisionPoint();
        return camera3D.toGlobal(aimRay.getTargetPosition());
    }

    // ── Input ─────────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _input(InputEvent event) {
        if (!passengerAimMode || !camera3D.isCurrent()) return;
        if (event instanceof InputEventMouseMotion m) {
            // Only rotate while the player is actively aiming or firing.
            if (!isAimingOrFiring()) return;
            yaw   -= (float) m.getRelative().getX() * cameraSensitivity;
            pitch -= (float) m.getRelative().getY() * cameraSensitivity;
            pitch  = (float) GD.clamp(pitch, minPitch, maxPitch);
            getViewport().setInputAsHandled();
        }
    }

    // ── Physics ───────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        Vector3 vehiclePos = target.getGlobalPosition();
        float   vehicleYaw = (float) target.getGlobalRotation().getY();

        // ── Position: world-space distance clamping ──────────────────────────
        // Camera maintains its current world-space offset from the vehicle,
        // clamped to [minDistance, maxDistance] at a fixed height.  No explicit
        // yaw-follow parameter needed — the vehicle driving forward naturally
        // pulls the camera back into position, giving the organic drag-through-
        // turns feel of the original follow-cam.
        Vector3 fromTarget = camera3D.getGlobalPosition().minus(vehiclePos);
        float len = (float) fromTarget.length();
        if (len < 0.001f) {
            // Camera exactly at vehicle centre — push it back along world +Z.
            fromTarget = new Vector3(0f, 0f, minDistance);
        } else if (len < minDistance) {
            fromTarget = fromTarget.normalized().times(minDistance);
        } else if (len > maxDistance) {
            fromTarget = fromTarget.normalized().times(maxDistance);
        }
        fromTarget.setY(height);
        camera3D.setGlobalPosition(vehiclePos.plus(fromTarget));

        // ── Orientation ──────────────────────────────────────────────────────
        if (passengerAimMode && isAimingOrFiring()) {
            // Active aim: camera looks where the player is pointing.
            camera3D.setGlobalRotation(new Vector3(pitch, yaw, 0f));
        } else {
            // Follow / recovery: always look at the vehicle centre.
            if (passengerAimMode) {
                // Bleed aim angles back toward vehicle heading while the player
                // is not shooting, so the next aim starts from a sensible angle.
                yaw   = (float) GD.lerpAngle(yaw,   vehicleYaw,   aimRecoverySpeed * delta);
                pitch = (float) GD.lerp(pitch, (double) DEFAULT_PITCH, aimRecoverySpeed * delta);
            }
            Vector3 lookDir = camera3D.getGlobalPosition()
                    .directionTo(vehiclePos).abs().minus(Vector3.Companion.getUP());
            if (!lookDir.isZeroApprox()) {
                camera3D.lookAtFromPosition(
                        camera3D.getGlobalPosition(), vehiclePos, Vector3.Companion.getUP());
            }
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private boolean isAimingOrFiring() {
        return INSTANCE.isActionPressed("aim",  false)
            || INSTANCE.isActionPressed("fire", false);
    }
}
