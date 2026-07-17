package com.openworld.carrier.motorcycle;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleConfig;
import godot.annotation.RegisterClass;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Two-wheel carrier stub (drivable prototype — placeholder mesh, tuning later).
 *
 * Reuses the whole raycast-wheel pipeline from {@link Vehicle} with a 2-wheel scene
 * (front steer, rear motor). The one motorcycle-specific behaviour is LEAN: the
 * keep-upright assist's target axis ({@link #desiredUpAxis()}) tilts into the turn —
 * roll = steer fraction × {@code motorcycleLeanDegrees} × speed — so a single strong
 * {@code uprightTorque} (set high in the scene's config preset) both holds the bike
 * upright at rest and banks it through corners. Parked sleep freezes it standing.
 */
@RegisterClass(className = "Motorcycle")
public class Motorcycle extends Vehicle {

    @Override
    protected Vector3 desiredUpAxis() {
        VehicleConfig cfg = getConfig();
        float maxRad = (float) GD.degToRad(Math.max(1e-3f, cfg.tireMaxTurnDegrees));
        float steerFraction = (float) GD.clamp(getCurrentSteerAngle() / maxRad, -1.0, 1.0);
        float speedRatio = (float) GD.clamp(
                getLinearVelocity().length() / Math.max(1e-3f, cfg.maxSpeed), 0.0, 1.0);
        double lean = GD.degToRad(cfg.motorcycleLeanDegrees) * steerFraction * speedRatio;
        if (Math.abs(lean) < 1e-4) return Vector3.Companion.getUP();
        // Tilt world-up about the travel direction: steering left leans left into the turn.
        Vector3 forward = getGlobalBasis().getZ().times(-1).normalized();
        return Vector3.Companion.getUP().rotated(forward, lean).normalized();
    }
}
