package com.openworld.carrier.vehicle;

import com.openworld.control.UserCommand;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Per-wheel physics: suspension spring, motor/steer forces, lateral grip, skid marks.
 *
 * Structural fields (wheelScene, isMotor, isSteer, gripCurve) are set in the scene.
 * Physics constants (spring, traction, wheelRadius, etc.) come from VehicleConfig via
 * setup() — no per-wheel duplication of values that belong at the vehicle-type level.
 */
@RegisterClass(className = "VehicleWheel")
public class VehicleWheel extends RayCast3D {

    private static final float TWO_PI = (float)(2.0 * Math.PI);

    // ── Per-wheel structural exports (set in scene, NOT in VehicleConfig) ─────

    /** Optional per-wheel visual mesh override. Null = use the Vehicle's default wheel mesh. */
    @RegisterProperty @Export public PackedScene wheelScene;

    /** True when this wheel is driven by the motor. */
    @RegisterProperty @Export public boolean isMotor = false;

    /** True when this wheel turns with steering input. */
    @RegisterProperty @Export public boolean isSteer = false;

    /**
     * Tire lateral-grip curve. X = slip ratio (0=aligned, 1=pure sideways), Y = grip [0–1].
     * Rear wheels typically have a softer curve than front wheels to enable controlled drift.
     */
    @RegisterProperty @Export public Curve gripCurve;

    // ── Config reference (injected by Vehicle._ready via setup()) ─────────────
    private VehicleConfig cfg;

    /** Called by Vehicle._ready() to inject the vehicle-type config. */
    public void setup(VehicleConfig vehicleConfig) {
        this.cfg = vehicleConfig;
    }

    // ── Runtime state ─────────────────────────────────────────────────────────

    private Vehicle   vehicle;
    private Node3D    wheelMesh;
    private GPUParticles3D skidMark;

    private float tireMaxTurnMinRad;
    private float tireMaxTurnMaxRad;
    private float gripFactor;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        vehicle = (Vehicle) getOwner();
        wheelMesh = (Node3D) getNode("Wheel");
        skidMark = (GPUParticles3D) getNode("SkidMark");

        // cfg is injected by Vehicle._ready() via setup() BEFORE VehicleWheel._ready()
        // fires (parent _ready runs after children). Guard against unset cfg at startup.
        if (cfg == null) cfg = vehicle.getConfig();

        tireMaxTurnMinRad = (float) GD.degToRad(-cfg.tireMaxTurnDegrees);
        tireMaxTurnMaxRad = (float) GD.degToRad(cfg.tireMaxTurnDegrees);

        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(cfg.restDistance + cfg.wheelRadius + cfg.overExtend));
        setTargetPosition(targetPosition);
    }

    private Vector3 getPointVelocity(Vector3 point) {
        return vehicle.getLinearVelocity().plus(
                vehicle.getAngularVelocity().cross(point.minus(vehicle.getGlobalPosition())));
    }

    public void applyWheelPhysics(float delta, float physDelta, UserCommand cmd) {
        forceRaycastUpdate();
        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(cfg.restDistance + cfg.wheelRadius + cfg.overExtend));
        setTargetPosition(targetPosition);

        // Rotate wheel visuals
        Vector3 forwardDir = getGlobalBasis().getZ().times(-1);
        double speed = forwardDir.dot(vehicle.getLinearVelocity());
        wheelMesh.rotateX((float)((-speed * physDelta) / cfg.wheelRadius));

        if (!isColliding()) return;

        Vector3 contact     = getCollisionPoint();
        double  springLen   = getGlobalPosition().distanceTo(contact) - cfg.wheelRadius;
        double  compression = cfg.restDistance - springLen;

        Vector3 wheelMeshPos = wheelMesh.getPosition();
        wheelMeshPos.setY(GD.moveToward(wheelMeshPos.getY(), -springLen, 5 * getPhysicsProcessDeltaTime()));
        wheelMesh.setPosition(wheelMeshPos);

        contact = wheelMesh.getGlobalPosition();
        Vector3 forcePos = contact.minus(vehicle.getGlobalPosition());

        // Spring suspension force
        double springForceMag = cfg.springStrength * compression;
        Vector3 tireVelocity  = getPointVelocity(contact);
        double  dampForceMag  = cfg.springDamping * getGlobalBasis().getY().dot(tireVelocity);
        Vector3 yForce        = getCollisionNormal().times(springForceMag - dampForceMag);

        // Motor force
        if (isMotor && cmd.motor != 0) {
            double speedRatio  = speed / cfg.maxSpeed;
            double accelRatio  = cfg.accelerationCurve != null
                    ? cfg.accelerationCurve.sampleBaked((float) speedRatio)
                    : Math.max(0.0, 1.0 - speedRatio);
            Vector3 accelForce = forwardDir.times(cfg.acceleration * cmd.motor * accelRatio);
            vehicle.applyForce(accelForce, forcePos);
        }

        // Lateral (X) traction
        float  steeringXSpeed = (float) getGlobalBasis().getX().dot(tireVelocity);
        gripFactor = (float) GD.abs(steeringXSpeed / tireVelocity.length());
        double xTraction = gripCurve != null ? gripCurve.sampleBaked(gripFactor) : 1.0;

        if (cmd.handbrake && gripFactor < 0.2f) vehicle.setSlipping(false);
        if (cmd.handbrake)          xTraction = 0.01;
        else if (vehicle.isSlipping()) xTraction = 0.1;

        double gravity = -vehicle.getGravity().getY();
        Vector3 xForce = getGlobalBasis().getX().times(
                -steeringXSpeed * xTraction * (vehicle.getMass() * gravity / 4.0));

        // Longitudinal (Z) friction
        double forwardSpeed = forwardDir.dot(tireVelocity);
        float  zFriction    = cfg.zTraction;
        if (vehicle.isBraking()) {
            zFriction = cfg.zBrakeTraction;
        } else if (Math.abs(cmd.motor) < 0.01f && Math.abs(forwardSpeed) < 0.5f) {
            zFriction = cfg.zBrakeTraction;  // parking friction on slopes
        }

        Vector3 zForce = vehicle.getGlobalBasis().getZ().times(
                forwardSpeed * zFriction * (vehicle.getMass() * gravity / vehicle.getWheels().size()));

        vehicle.applyForce(xForce, forcePos);
        vehicle.applyForce(yForce, forcePos);
        vehicle.applyForce(zForce, forcePos);
    }

    public void applySkidMark() {
        skidMark.setGlobalPosition(getCollisionPoint().plus(Vector3.Companion.getUP().times(0.01)));
        skidMark.lookAt(skidMark.getGlobalPosition().plus(vehicle.getGlobalBasis().getZ()));

        if (!vehicle.isHandbraking() && gripFactor < 0.2f) {
            vehicle.setSlipping(false);
            skidMark.setEmitting(false);
        }
        if (vehicle.isHandbraking() && !skidMark.isEmitting()) {
            skidMark.setEmitting(true);
        }
    }

    public void applyWheelSuspension(float delta) {
        if (vehicle == null || !isColliding()) return;

        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(cfg.restDistance + cfg.wheelRadius + cfg.overExtend));
        setTargetPosition(targetPosition);

        Vector3 contact     = getCollisionPoint();
        Vector3 springUpDir = getGlobalTransform().getBasis().getY().normalized();
        double  springLen   = getGlobalPosition().distanceTo(contact) - cfg.wheelRadius;
        double  compression = cfg.restDistance - springLen;

        Vector3 wheelMeshPos = wheelMesh.getPosition();
        wheelMeshPos.setY(-springLen);
        wheelMesh.setPosition(wheelMeshPos);

        double springForceMag = cfg.springStrength * compression;
        Vector3 worldVelocity = getPointVelocity(contact);
        double  relVelocity   = springUpDir.dot(worldVelocity);
        double  dampForceMag  = cfg.springDamping * relVelocity;
        Vector3 springForce   = getCollisionNormal().times(springForceMag - dampForceMag);

        vehicle.applyForce(springForce, contact.minus(vehicle.getGlobalPosition()));
    }

    public void applyWheelAcceleration(float physDelta, float motor) {
        Vector3 forwardDir = getGlobalBasis().getZ().times(-1);
        double velocity    = forwardDir.dot(vehicle.getLinearVelocity());
        wheelMesh.rotateX((float)((-velocity * physDelta) / cfg.wheelRadius));

        if (!isColliding()) return;

        Vector3 contact   = getCollisionPoint();
        Vector3 forcePos  = contact.minus(vehicle.getGlobalPosition());

        if (isMotor && motor != 0) {
            double speedRatio = velocity / cfg.maxSpeed;
            double accelRatio = cfg.accelerationCurve != null
                    ? cfg.accelerationCurve.sampleBaked((float) speedRatio)
                    : Math.max(0.0, 1.0 - speedRatio);
            Vector3 forceVec = forwardDir.times(cfg.acceleration * motor * accelRatio);
            vehicle.applyForce(forceVec, forcePos);
        }
    }

    /**
     * Visual-only replay for replicated puppet vehicles (Round 11 N3) — no forces (puppets
     * are frozen; the body transform comes from the interpolator), but every visible wheel
     * behaviour mirrors the authority:
     *
     *   steer:      ease the wheel's Y rotation to the REPLICATED actual angle (not the
     *               raw input — re-integrating an input rate would drift from the
     *               authority's pose)
     *   spin:       same mesh-spin math as applyWheelPhysics, from replicated speed
     *   suspension: raycast still works on a frozen body — settle the mesh to the live
     *               spring length so wheels hug the ground instead of floating at rest
     *   skid marks: emit while the authority reports handbrake/slip and this wheel touches
     */
    public void applyPuppetVisuals(float delta, float steerAngle, float forwardSpeed, boolean skidding) {
        if (wheelMesh == null || cfg == null) return;

        if (isSteer) {
            Vector3 rotation = getRotation();
            float target = (float) GD.clamp(steerAngle, tireMaxTurnMinRad, tireMaxTurnMaxRad);
            rotation.setY((float) GD.moveToward(rotation.getY(), target, cfg.tireMaxTurnSpeed * delta));
            setRotation(rotation);
        }

        wheelMesh.rotateX((-forwardSpeed * delta) / cfg.wheelRadius);

        forceRaycastUpdate();
        if (isColliding()) {
            double springLen = getGlobalPosition().distanceTo(getCollisionPoint()) - cfg.wheelRadius;
            Vector3 wheelMeshPos = wheelMesh.getPosition();
            wheelMeshPos.setY(GD.moveToward(wheelMeshPos.getY(), -springLen, 5 * delta));
            wheelMesh.setPosition(wheelMeshPos);

            if (skidMark != null) {
                skidMark.setGlobalPosition(getCollisionPoint().plus(Vector3.Companion.getUP().times(0.01)));
                skidMark.lookAt(skidMark.getGlobalPosition().plus(vehicle.getGlobalBasis().getZ()));
                if (skidding != skidMark.isEmitting()) skidMark.setEmitting(skidding);
            }
        } else if (skidMark != null && skidMark.isEmitting()) {
            skidMark.setEmitting(false);
        }
    }

    public void applyWheelSteering(float delta, float steering) {
        if (!isSteer) return;
        Vector3 rotation = getRotation();
        if (steering != 0) {
            float rotY = (float) GD.clamp(rotation.getY() + steering * delta,
                                          tireMaxTurnMinRad, tireMaxTurnMaxRad);
            rotation.setY(rotY);
        } else {
            rotation.setY((float) GD.moveToward(rotation.getY(), 0, cfg.tireMaxTurnSpeed * delta));
        }
        setRotation(rotation);
    }

    public void applyWheelTraction(boolean handbrake) {
        if (!isColliding()) return;

        Vector3 steerSideDir      = getGlobalBasis().getX();
        Vector3 tireVelocity      = getPointVelocity(wheelMesh.getGlobalPosition());
        float   steeringXVelocity = (float) steerSideDir.dot(tireVelocity);
        float   gf                = (float) GD.abs(steeringXVelocity / tireVelocity.length());
        double  xTraction         = gripCurve != null ? gripCurve.sampleBaked(gf) : 1.0;

        skidMark.setGlobalPosition(getCollisionPoint().plus(Vector3.Companion.getUP().times(0.01)));
        skidMark.lookAt(skidMark.getGlobalPosition().plus(vehicle.getGlobalBasis().getZ()));

        boolean isSlipping = true;
        if (!handbrake && gf < 0.2f) {
            isSlipping = false;
            skidMark.setEmitting(false);
        }
        if (handbrake) {
            xTraction = 0.01;
            if (!skidMark.isEmitting()) skidMark.setEmitting(true);
        } else if (isSlipping) {
            xTraction = 0.1;
        }

        double gravity  = -vehicle.getGravity().getY();
        Vector3 xForce  = steerSideDir.times(-steeringXVelocity * xTraction * (vehicle.getMass() * gravity / 4.0));
        float  fwdSpeed = (float) -getGlobalBasis().getZ().dot(tireVelocity);
        Vector3 zForce  = vehicle.getGlobalBasis().getZ().times(fwdSpeed * cfg.zTraction * (vehicle.getMass() * gravity / 4.0));

        Vector3 forcePos = getGlobalPosition().minus(vehicle.getGlobalPosition());
        vehicle.applyForce(xForce, forcePos);
        vehicle.applyForce(zForce, forcePos);
    }
}
