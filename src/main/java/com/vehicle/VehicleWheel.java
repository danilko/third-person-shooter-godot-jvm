package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
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
public class VehicleWheel extends RayCast3D {

    private static final float TWO_PI = (float)(2.0 * Math.PI);

    // ── Inspector exports ─────────────────────────────────────────────────────

    /** Visual scene for this wheel. Null = use Vehicle.defaultWheelScene. */
    @RegisterProperty @Export public PackedScene wheelScene;

    /** Override visual radius (metres); 0 = use Vehicle.wheelRadius. */
    @RegisterProperty @Export public float wheelRadius = 0.4f;

    /** Enables steering rotation on this wheel. */
    @RegisterProperty @Export public boolean isFrontWheel = false;


    @RegisterProperty @Export public float springStrength = 100.0f;
    @RegisterProperty @Export public float springDamping = 2.0f;
    @RegisterProperty @Export public float restDistance = 0.5f;
    @RegisterProperty @Export public float overExtend = 0.2f;


    // ── Runtime state ─────────────────────────────────────────────────────────

    private Vehicle   vehicle;
    private Node3D wheelMesh;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        vehicle = (Vehicle) getOwner().getNode("Vehicle");
        wheelMesh = (Node3D) getNode("Wheel");
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Called by Vehicle._ready() — configures the ray length from hoverHeight.
     */
    public void setVehicle(Vehicle v) {
        vehicle = v;
    }


    private Vector3 getPointVelocity(Vector3 point) {
        return vehicle.getLinearVelocity().plus(vehicle.getAngularVelocity().cross(point.minus(vehicle.getGlobalPosition())));
    }

    /**
     * Applies an upward spring+damper force to the vehicle at this wheel's position.
     * Called from Vehicle._physicsProcess each frame.
     * Returns true when the wheel is within hoverHeight of the ground.
     */
    public void applyWheelSuspension(float delta) {
        if (vehicle == null) {return;}

        if (!isColliding()) {return;}
        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(restDistance + wheelRadius + overExtend));
        setTargetPosition(targetPosition);

        Vector3 contact    = getCollisionPoint();
        Vector3 springUpDir = getGlobalTransform().getBasis().getY().normalized();
        double  springLen    = getGlobalPosition().distanceTo(contact) - wheelRadius;
        double compression =  restDistance - springLen;

        Vector3 wheelMeshPositiontion = wheelMesh.getPosition();
        wheelMeshPositiontion.setY(-springLen);
        wheelMesh.setPosition(wheelMeshPositiontion);

        double springForceMagnitude = springStrength * compression;

        // damping force
        Vector3 worldVelocity = getPointVelocity(contact);
        double relativeVelocity = springUpDir.dot(worldVelocity);
        double springDampForceMagnitude = springDamping * relativeVelocity;

        Vector3 springForce = springUpDir.times(springForceMagnitude - springDampForceMagnitude);
        Vector3 forcePosOffset = contact.minus(vehicle.getGlobalPosition());

        vehicle.applyForce(springForce, forcePosOffset);
    }
}
