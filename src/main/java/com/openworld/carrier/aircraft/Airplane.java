package com.openworld.carrier.aircraft;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleConfig;
import godot.annotation.Script;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Fixed-wing carrier stub (drivable prototype — placeholder airframe, tuning later).
 *
 * Overrides {@link #applyLocomotion} entirely (no wheels — the fuselage collider skids on
 * the runway): thrust ∝ throttle along −Z, lift ∝ forward-speed² along body-up capped near
 * 1.3× weight (take-off needs a run-up, level flight settles near weight), and simple
 * control-surface torques — steering = banked turn (roll + a little yaw), handbrake (the
 * jump key) pitches up, brake pitches down. The shared upright assist auto-levels when slow
 * (landing/taxi); at speed the assists stay out of the way so it can actually bank.
 * Seats, boost (afterburner!), authority, destruction, replication inherit from {@link Vehicle}.
 */
@Script(className = "Airplane")
public class Airplane extends Vehicle {

    @Override
    protected boolean requiresWheels() { return false; }

    @Override
    protected boolean applyLocomotion(VehicleConfig cfg, double delta) {
        updateBoost(cfg, delta);

        Vector3 forward = getGlobalBasis().getZ().times(-1);
        Vector3 bodyUp  = getGlobalBasis().getY();
        Vector3 right   = getGlobalBasis().getX();
        Vector3 linVel  = getLinearVelocity();
        float speed     = (float) linVel.length();
        float fwdSpeed  = (float) Math.max(0.0, forward.dot(linVel));

        if (cmd.motor != 0) {
            applyCentralForce(forward.times(cfg.acceleration * cmd.motor * getBoostAccelScale()));
        }

        float weight = (float) (getMass() * -getGravity().getY());
        float lift = Math.min(cfg.liftCoefficient * fwdSpeed * fwdSpeed, weight * 1.3f);
        if (lift > 0f) applyCentralForce(bodyUp.times(lift));

        // Control surfaces scale with airspeed (no authority when parked on the runway).
        float authority = (float) GD.clamp(fwdSpeed / Math.max(1e-3f, cfg.maxSpeed * 0.35f), 0.0, 1.0);
        float roll  = (float) GD.clamp(cmd.steering, -1.0, 1.0);
        float pitch = (cmd.handbrake ? 1f : 0f) - (cmd.brake ? 1f : 0f);
        if (roll != 0f) {
            applyTorque(forward.times(-roll * cfg.rollTorque * authority));
            applyTorque(bodyUp.times(roll * cfg.rudderTorque * 0.4f * authority));   // coordinated turn
        }
        if (pitch != 0f) {
            applyTorque(right.times(pitch * cfg.pitchTorque * authority));
        }

        setCenterOfMassMode(CenterOfMassMode.CUSTOM);
        setCenterOfMass(new Vector3(0f, -0.2f, 0f));
        // Upright/auto-level only when slow (taxi/landing) — free to bank at speed.
        applyStabilityAssists(cfg, speed < 8f, speed);
        return speed < 3f;   // "supported" ≈ at rest on the ground — lets the parked sleep engage
    }
}
