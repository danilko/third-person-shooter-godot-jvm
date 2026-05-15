package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.RayCast3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Per-wheel hover spring for the hovercraft vehicle.
 *
 * Each wheel fires a raycast downward. When the ground is within hoverHeight,
 * an upward spring+damper force is applied to the Vehicle RigidBody3D at the
 * wheel's offset from the body center — the torque from the four corners keeps
 * the chassis level without any explicit angular constraint.
 *
 * Forces are applied via Vehicle.applyForce() (queued for next integration step),
 * which is correct for a hovercraft where one-frame precision is not critical.
 *
 * Scene setup: add a RayCast3D child named "Ray"; the target length is set
 * automatically by setVehicle(). Optionally set wheelScene for a rolling visual.
 */
@RegisterClass(className = "VehicleWheel")
public class VehicleWheel extends Node3D {

    private static final float TWO_PI = (float)(2.0 * Math.PI);

    // ── Inspector exports ─────────────────────────────────────────────────────

    /** Visual scene for this wheel. Null = use Vehicle.defaultWheelScene. */
    @RegisterProperty @Export public PackedScene wheelScene;

    /** Override visual radius (metres); 0 = use Vehicle.wheelRadius. */
    @RegisterProperty @Export public float wheelVisualRadius = 0f;

    /** Enables steering rotation on this wheel. */
    @RegisterProperty @Export public boolean isFrontWheel = false;

    /** Max steering angle for front wheels (degrees). */
    @RegisterProperty @Export public float maxSteerAngleDeg = 30f;

    // ── Runtime state ─────────────────────────────────────────────────────────

    private Vehicle   vehicle;
    private RayCast3D ray;
    private Node3D    meshPivot;
    private float     spinAngle = 0f;

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
     * Called by Vehicle._ready() — configures the ray length from hoverHeight.
     */
    public void setVehicle(Vehicle v) {
        vehicle = v;
        if (ray != null && v != null) {
            ray.addException(v);
            // 4× hoverHeight so the ray reaches the ground from typical spawn heights.
            // e.g. body at y=3m → wheel at y=2.7m → ray reaches y=-0.5m ✓
            ray.setTargetPosition(new Vector3(0f, -(v.hoverHeight * 4.0f), 0f));
        }
        GD.print("[VehicleWheel] " + getName() + " setVehicle OK, ray=" + (ray != null));
    }

    /**
     * Supplies the shared wheel scene when this wheel has none of its own.
     */
    public void applyDefaultScene(PackedScene defaultScene) {
        if (wheelScene != null || defaultScene == null) return;
        wheelScene = defaultScene;
        buildMeshPivot();
    }

    /**
     * Applies an upward spring+damper force to the vehicle at this wheel's position.
     * Called from Vehicle._physicsProcess each frame.
     * Returns true when the wheel is within hoverHeight of the ground.
     */
    public boolean applyHoverForce(float delta, Vehicle vehicle) {
        if (ray == null || vehicle == null) return false;

        ray.forceRaycastUpdate();

        if (!ray.isColliding()) {
            positionMesh(vehicle.hoverHeight);
            return false;
        }

        Vector3 wheelPos    = getGlobalPosition();
        Vector3 hitPoint    = ray.getCollisionPoint();
        float   distance    = (float) wheelPos.distanceTo(hitPoint);
        float   compression = vehicle.hoverHeight - distance;

        positionMesh(Math.max(0f, distance - vehicle.wheelRadius));

        if (compression <= 0f) return false;

        // Spring: proportional to how much the wheel is below its hover target.
        float springForce = vehicle.springStiffness * compression;

        // Damper: vertical velocity of this point on the body (linear + rotational).
        Vector3 bodyOrigin = vehicle.getGlobalPosition();
        Vector3 offset     = wheelPos.minus(bodyOrigin);
        Vector3 pointVel   = vehicle.getLinearVelocity()
            .plus(vehicle.getAngularVelocity().cross(offset));
        float   vertVel    = (float) pointVel.dot(new Vector3(0f, 1f, 0f));
        float   damperForce = vehicle.springDamperStiffness * vertVel;

        float total = Math.max(0f, springForce - damperForce);
        vehicle.applyForce(new Vector3(0f, total, 0f), offset);
        return true;
    }

    /**
     * Updates wheel spin and steering rotation each physics frame.
     * @param forwardSpeed  vehicle speed along heading (m/s, signed)
     * @param steering      raw input in [-1, 1]
     */
    public void updateVisual(float delta, float forwardSpeed, float steering) {
        if (meshPivot == null || vehicle == null) return;

        float vr = effectiveVisualRadius();
        spinAngle += (forwardSpeed / vr) * delta;
        if      (spinAngle >  TWO_PI) spinAngle -= TWO_PI;
        else if (spinAngle < -TWO_PI) spinAngle += TWO_PI;

        float steerRad = isFrontWheel ? (float) Math.toRadians(steering * maxSteerAngleDeg) : 0f;
        meshPivot.setRotation(new Vector3(spinAngle, steerRad, 0f));
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private void buildMeshPivot() {
        if (wheelScene == null || meshPivot != null) return;
        meshPivot = new Node3D();
        meshPivot.addChild(wheelScene.instantiate());
        addChild(meshPivot);
    }

    private float effectiveVisualRadius() {
        return (wheelVisualRadius > 0f && vehicle != null)
                ? wheelVisualRadius
                : (vehicle != null ? vehicle.wheelRadius : 0.35f);
    }

    private void positionMesh(float dropOffset) {
        if (meshPivot == null) return;
        meshPivot.setPosition(new Vector3(0f, -dropOffset, 0f));
    }
}
