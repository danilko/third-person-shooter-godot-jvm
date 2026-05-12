package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.PhysicsDirectBodyState3D;
import godot.api.RayCast3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Per-wheel raycast suspension — applies spring + damper force to the Vehicle.
 *
 * Wheels sit under a "Wheels" container that is a direct child of Vehicle.
 * Vehicle._ready() calls setVehicle(this) then applyDefaultScene(scene) on each
 * wheel, guaranteeing both are set before any physics tick.
 *
 * Forces are applied via PhysicsDirectBodyState3D.applyForce() so they take
 * effect in the CURRENT integration step. Using body.applyForce() inside
 * _integrateForces queues for the next step, which delays suspension by one
 * frame and makes the spring numerically unstable.
 *
 * Scene setup: add a RayCast3D child named "Ray". Target position is
 * overridden by setVehicle() based on the Vehicle's maxSpringLength.
 *
 * Wheel visual: assign wheelScene (or set defaultWheelScene on the Vehicle).
 * Build the scene with the correct local transform for the imported asset —
 * code never touches the instantiated scene's own transform.
 */
@RegisterClass(className = "VehicleWheel")
public class VehicleWheel extends Node3D {

    private static final float MAX_SPRING_VEL  = 8f;
    private static final float TWO_PI          = (float)(2.0 * Math.PI);

    // ── Inspector exports ─────────────────────────────────────────────────────

    /**
     * Scene for this wheel's visual. If null, Vehicle.defaultWheelScene is used.
     * The scene is instantiated under a Node3D pivot — set scale, rotation, and
     * pivot offset in the scene; code never modifies the instantiated transform.
     */
    @RegisterProperty @Export public PackedScene wheelScene;

    /**
     * Visual radius of the wheel (metres). Used to position the axle so the
     * wheel bottom sits on the ground: axle_Y = hit_point_Y + wheelVisualRadius.
     * 0 = inherit vehicle.wheelRadius (fine when physics and visual radii match).
     */
    @RegisterProperty @Export public float wheelVisualRadius = 0f;

    /** Mark front wheels to enable steering Y rotation. */
    @RegisterProperty @Export public boolean isFrontWheel = false;

    /** Max steering angle for front wheels (degrees). */
    @RegisterProperty @Export public float maxSteerAngleDeg = 30f;

    // ── Runtime state ─────────────────────────────────────────────────────────

    private float     lastSpringLength = -1f;
    private Vehicle   vehicle;
    private RayCast3D ray;
    private Node3D    meshPivot;   // spring position + steer/spin rotation
    private float     spinAngle   = 0f;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        Node r = getNodeOrNull("Ray");
        if (r instanceof RayCast3D rc) ray = rc;
        buildMeshPivot();
    }

    // ── Public API ────────────────────────────────────────────────────────────

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
     * Called by Vehicle._ready() to supply a shared scene when this wheel's own
     * wheelScene export is null. No-op if the wheel already has a scene assigned.
     */
    public void applyDefaultScene(PackedScene defaultScene) {
        if (wheelScene != null || defaultScene == null) return;
        wheelScene = defaultScene;
        buildMeshPivot();
    }

    /**
     * Updates wheel visuals each physics frame.
     * Called by Vehicle._physicsProcess after applyDriving so desiredForward is current.
     *
     * @param delta        physics step seconds
     * @param forwardSpeed vehicle speed projected onto heading (m/s, signed)
     * @param steering     raw steering input in [-1, 1]
     */
    public void updateVisual(float delta, float forwardSpeed, float steering) {
        if (meshPivot == null || vehicle == null) return;

        float vr = effectiveVisualRadius();

        // Spin: accumulate angle, normalise to avoid float precision loss over time.
        spinAngle += (forwardSpeed / vr) * delta;
        if      (spinAngle >  TWO_PI) spinAngle -= TWO_PI;
        else if (spinAngle < -TWO_PI) spinAngle += TWO_PI;

        // Steer: front wheels only, direct mapping to degrees.
        float steerRad = isFrontWheel
                ? (float) Math.toRadians(steering * maxSteerAngleDeg)
                : 0f;

        // Godot YXZ Euler order: Y (steer) applied first, then X (spin around
        // the steered axle) — physically correct for a steerable rolling wheel.
        meshPivot.setRotation(new Vector3(spinAngle, steerRad, 0f));
    }

    // ── Suspension ────────────────────────────────────────────────────────────

    /**
     * Fires the ray and applies spring + damper suspension force through the
     * physics state so it is effective in the current integration step.
     * Returns true if the wheel is in contact with the ground this tick.
     */
    public boolean applySuspension(float delta, PhysicsDirectBodyState3D state) {
        if (ray == null || vehicle == null) return false;

        ray.forceRaycastUpdate();
        if (!ray.isColliding()) {
            lastSpringLength = vehicle.maxSpringLength;
            positionMesh(vehicle.maxSpringLength);
            return false;
        }

        // Reject wall/ceiling contacts (normal upward component < 0.3 ≈ 72° from
        // horizontal) to prevent spurious lateral suspension forces and the
        // lastSpringLength = 0 → damper spike cycle on wall bounces.
        if ((float) ray.getCollisionNormal().dot(new Vector3(0f, 1f, 0f)) < 0.3f) {
            lastSpringLength = vehicle.maxSpringLength;
            return false;
        }

        Vector3 collisionPoint = ray.getCollisionPoint();
        float   distance       = (float) collisionPoint.distanceTo(getGlobalPosition());

        float springLength = Math.max(0f,
            Math.min(vehicle.maxSpringLength, distance - vehicle.wheelRadius));

        if (lastSpringLength < 0f) lastSpringLength = springLength;

        float springVelocity = (lastSpringLength - springLength) / delta;
        springVelocity = Math.max(-MAX_SPRING_VEL, Math.min(MAX_SPRING_VEL, springVelocity));

        float springForce = vehicle.springStiffness * (vehicle.maxSpringLength - springLength);
        float damperForce = vehicle.springDamperStiffness * springVelocity;

        Vector3 suspensionDir = getGlobalTransform().getBasis().getColumn(1);
        Vector3 force         = suspensionDir.times(springForce + damperForce);

        Vector3 bodyOrigin = state.getTransform().getOrigin();
        Vector3 forceOffset = new Vector3(
            collisionPoint.getX() - bodyOrigin.getX(),
            collisionPoint.getY() + vehicle.wheelRadius - bodyOrigin.getY(),
            collisionPoint.getZ() - bodyOrigin.getZ());

        state.applyForce(force, forceOffset);

        lastSpringLength = springLength;
        positionMesh(springLength);
        return true;
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private void buildMeshPivot() {
        if (wheelScene == null || meshPivot != null) return;
        meshPivot = new Node3D();
        Node sceneRoot = wheelScene.instantiate();
        meshPivot.addChild(sceneRoot);
        addChild(meshPivot);
    }

    /**
     * Returns wheelVisualRadius when explicitly set; falls back to vehicle.wheelRadius.
     * Allows the visual wheel to differ in size from the physics capsule without
     * requiring a matching vehicle.wheelRadius change.
     */
    private float effectiveVisualRadius() {
        return (wheelVisualRadius > 0f && vehicle != null)
                ? wheelVisualRadius
                : (vehicle != null ? vehicle.wheelRadius : 0.35f);
    }

    /**
     * Positions the mesh pivot so the wheel visual sits correctly on the ground.
     *
     * In wheel-local space the attachment point is Y = 0 (top of suspension).
     * The ray hit point is at Y = -(springLength + physicsRadius).
     * The wheel axle (centre of visual) should be visualRadius above the hit point:
     *   axleY = -(springLength + physicsRadius) + visualRadius
     * When physicsRadius == visualRadius this reduces to the simpler -springLength.
     */
    private void positionMesh(float springLength) {
        if (meshPivot == null || vehicle == null) return;
        float axleY = -(springLength + vehicle.wheelRadius) + effectiveVisualRadius();
        meshPivot.setPosition(new Vector3(0f, axleY, 0f));
    }
}
