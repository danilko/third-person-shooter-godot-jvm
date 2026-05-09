package com.vehicle;

import com.character.UserCommand;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;

/**
 * Concrete ground vehicle (car / tank) with speed-cap physics.
 *
 * Extends VehicleBody with two tunable limits:
 *   maxSpeed         — clamps forward engine force once the vehicle reaches this speed
 *   reverseSpeedFactor — reverse top speed as a fraction of maxSpeed
 *
 * All other tuning (engineForce, brakeStrength, maxSteerAngle) is inherited
 * and set per-instance in the editor.
 *
 * Add VehicleWheel3D children in the scene and configure each wheel's
 * use_as_traction / use_as_steering flags to complete the vehicle setup.
 */
@RegisterClass(className = "GroundVehicle")
public class GroundVehicle extends VehicleBody {

    /** Forward top speed in m/s — engine force is zeroed above this. */
    @RegisterProperty @Export public float maxSpeed = 28.0f;

    /**
     * Reverse top speed as a fraction of maxSpeed (0–1).
     * At 0.4 and maxSpeed 28, reverse is capped at ≈11 m/s.
     */
    @RegisterProperty @Export public float reverseSpeedFactor = 0.4f;

    @Override
    public void applyCommand(UserCommand cmd, double delta) {
        float speedSq    = (float) getLinearVelocity().lengthSquared();
        float maxFwd     = maxSpeed;
        float maxRev     = maxSpeed * reverseSpeedFactor;

        UserCommand capped = cmd.copy();

        if (capped.throttle > 0f && speedSq > maxFwd * maxFwd) {
            capped.throttle = 0f;
        } else if (capped.throttle < 0f && speedSq > maxRev * maxRev) {
            capped.throttle = 0f;
        }

        super.applyCommand(capped, delta);
    }
}
