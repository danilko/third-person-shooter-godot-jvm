package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;

/**
 * Concrete ground vehicle (car / tank) with top-speed clamping.
 *
 * Overrides getThrottleInput() to zero the throttle once the vehicle reaches
 * maxSpeed (forward) or maxSpeed × reverseSpeedFactor (reverse).
 * All suspension, steering, drift, and force physics are inherited from Vehicle.
 */
@RegisterClass(className = "GroundVehicle")
public class GroundVehicle extends Vehicle {

    /** Forward top speed in m/s (~100 km/h at 28). */
    @RegisterProperty @Export public float maxSpeed = 28.0f;

    /**
     * Reverse top speed as a fraction of maxSpeed (0–1).
     * At 0.4 and maxSpeed 28, reverse is capped at ≈11 m/s.
     */
    @RegisterProperty @Export public float reverseSpeedFactor = 0.4f;

    @Override
    protected float getThrottleInput(float raw) {
        // Cap on the signed forward component (velocity projected onto desiredForward)
        // rather than total speed. On a slope, vertical velocity would otherwise add
        // to total speed and falsely cut the throttle while the vehicle is still
        // below maxSpeed in the travel direction.
        float fwdSpd = (float) getLinearVelocity().dot(desiredForward);
        if (raw > 0f && fwdSpd >  maxSpeed)                    return 0f;
        if (raw < 0f && fwdSpd < -maxSpeed * reverseSpeedFactor) return 0f;
        return raw;
    }
}
