package com.vehicle;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicsDirectBodyState3D;
import godot.api.RayCast3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Per-wheel raycast suspension — applies spring + damper force to the Vehicle.
 *
 * Wheels sit under a "Wheels" container that is a direct child of Vehicle.
 * Vehicle._ready() calls setVehicle(this) on each wheel after finding the
 * container, guaranteeing the reference is set before any physics tick.
 *
 * Forces are applied via PhysicsDirectBodyState3D.applyForce() so they take
 * effect in the CURRENT integration step. Using body.applyForce() inside
 * _integrateForces queues for the next step, which delays suspension by one
 * frame and makes the spring numerically unstable.
 *
 * Scene setup: add a RayCast3D child named "Ray". Target position is
 * overridden by setVehicle() based on the Vehicle's maxSpringLength.
 */
@RegisterClass(className = "VehicleWheel")
public class VehicleWheel extends Node3D {

    // Hard cap on damper velocity (m/s). Without this, a wheel transitioning from
    // fully extended to fully compressed in one frame produces 15-20 m/s, giving a
    // single-wheel damper force of 60-80 kN that sends the vehicle into unrecoverable
    // spin after hard landings.
    private static final float MAX_SPRING_VEL = 8f;

    private float     lastSpringLength = -1f;  // -1 = uninitialized; maxSpringLength when airborne
    private Vehicle   vehicle;
    private RayCast3D ray;

    @RegisterFunction
    @Override
    public void _ready() {
        Node r = getNodeOrNull("Ray");
        if (r instanceof RayCast3D rc) ray = rc;
    }

    /**
     * Called by Vehicle._ready() after the wheel container is located.
     * Configures the ray exception and target length from Vehicle exports.
     */
    public void setVehicle(Vehicle v) {
        vehicle = v;
        if (ray != null && v != null) {
            ray.addException(v);
            ray.setTargetPosition(new Vector3(0f, -(v.maxSpringLength * 1.5f), 0f));
        }
        GD.print("[VehicleWheel] " + getName() + " setVehicle OK, ray=" + (ray != null));
    }

    /**
     * Fires the ray and applies spring + damper suspension force through the
     * physics state so it is effective in the current integration step.
     * Returns true if the wheel is in contact with the ground this tick.
     */
    public boolean applySuspension(float delta, PhysicsDirectBodyState3D state) {
        if (ray == null || vehicle == null) return false;

        ray.forceRaycastUpdate();
        if (!ray.isColliding()) {
            // Reset to fully extended so the first frame of landing does not compute
            // a spurious high damper velocity from the pre-jump compressed value.
            lastSpringLength = vehicle.maxSpringLength;
            return false;
        }

        Vector3 collisionPoint = ray.getCollisionPoint();
        float   distance       = (float) collisionPoint.distanceTo(getGlobalPosition());

        float springLength = Math.max(0f,
            Math.min(vehicle.maxSpringLength, distance - vehicle.wheelRadius));

        // Seed on very first contact so the initial damper force is zero.
        if (lastSpringLength < 0f) lastSpringLength = springLength;

        // Clamp damper velocity to prevent force explosion on hard landings.
        float springVelocity = (lastSpringLength - springLength) / delta;
        springVelocity = Math.max(-MAX_SPRING_VEL, Math.min(MAX_SPRING_VEL, springVelocity));

        float springForce = vehicle.springStiffness * (vehicle.maxSpringLength - springLength);
        float damperForce = vehicle.springDamperStiffness * springVelocity;

        Vector3 suspensionDir = getGlobalTransform().getBasis().getColumn(1); // local +Y
        Vector3 force         = suspensionDir.times(springForce + damperForce);

        Vector3 bodyOrigin = state.getTransform().getOrigin();
        Vector3 forceOffset = new Vector3(
            collisionPoint.getX() - bodyOrigin.getX(),
            collisionPoint.getY() + vehicle.wheelRadius - bodyOrigin.getY(),
            collisionPoint.getZ() - bodyOrigin.getZ());

        state.applyForce(force, forceOffset);

        lastSpringLength = springLength;
        return true;
    }
}
