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

    /**
     * Extra fore/aft suspension probes (cfg.suspensionSamples - 1 of them). The wheel node
     * itself is always the centre probe; these sample the rest of the contact patch so the
     * wheel rides over edges/cracks smoothly. Empty when suspensionSamples <= 1.
     */
    private final java.util.ArrayList<RayCast3D> extraProbes = new java.util.ArrayList<>();

    /** Aggregated ground contact for the current frame, populated by {@link #sampleGround()}. */
    private boolean groundHit;
    private Vector3 groundPoint;
    private Vector3 groundNormal;

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

        buildExtraProbes();
    }

    /**
     * Spawns the additional contact-patch probe rays (cfg.suspensionSamples - 1). They are
     * RayCast3D children of this wheel — so they inherit its steer rotation and stay fore/aft
     * of the rolling direction — offset along local Z, with the same mask/exceptions as the
     * centre ray. The vehicle body is excepted so a probe never self-hits.
     */
    private void buildExtraProbes() {
        int samples = Math.max(1, cfg.suspensionSamples);
        if (samples <= 1) return;

        float spread = cfg.suspensionSampleSpread;
        Vector3 target = getTargetPosition();
        for (int i = 0; i < samples; i++) {
            // Even fore/aft distribution across [-spread, +spread]; the centre (offset 0,
            // index nearest the middle) is already covered by the wheel node itself.
            float off = (samples == 1) ? spread
                    : (-spread + 2f * spread * i / (samples - 1));
            if (Math.abs(off) < 1e-4f) continue;   // centre = the wheel node's own ray

            RayCast3D probe = new RayCast3D();
            probe.setName(new godot.core.StringName("SuspensionProbe" + i));
            probe.setEnabled(true);
            probe.setCollisionMask(getCollisionMask());
            probe.setCollideWithAreas(isCollideWithAreasEnabled());
            probe.setCollideWithBodies(isCollideWithBodiesEnabled());
            addChild(probe);
            probe.setPosition(new Vector3(0f, 0f, off));   // local +Z = backward, -Z = forward
            probe.setTargetPosition(target);
            if (vehicle != null) probe.addException(vehicle);
            extraProbes.add(probe);
        }
    }

    /**
     * Aggregates the centre ray + extra probes into a single ground contact for this frame.
     * Uses the HIGHEST contact (closest to the wheel → least sink, so the wheel rests on the
     * highest point and never drops into a crack one ray happened to straddle) and the AVERAGED
     * normal across all hits (steadier suspension/grip over bumps). Falls back to the single
     * centre ray when suspensionSamples <= 1.
     */
    private void sampleGround() {
        Vector3 origin = getGlobalPosition();
        groundHit = isColliding();
        groundPoint = groundHit ? getCollisionPoint() : null;
        Vector3 normalSum = groundHit ? getCollisionNormal() : null;
        double bestDist = groundHit ? origin.distanceTo(groundPoint) : Double.MAX_VALUE;
        int normalCount = groundHit ? 1 : 0;

        for (RayCast3D probe : extraProbes) {
            probe.forceRaycastUpdate();
            if (!probe.isColliding()) continue;
            Vector3 p = probe.getCollisionPoint();
            double d = origin.distanceTo(p);
            if (!groundHit || d < bestDist) { bestDist = d; groundPoint = p; }
            normalSum = (normalCount == 0) ? probe.getCollisionNormal()
                                           : normalSum.plus(probe.getCollisionNormal());
            normalCount++;
            groundHit = true;
        }
        groundNormal = (normalCount > 0) ? normalSum.normalized() : null;
    }

    /** True when any of this wheel's probes touched the ground this frame. */
    public boolean grounded() { return groundHit; }

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

        // Aggregate the centre ray + any extra contact-patch probes into one contact.
        sampleGround();
        if (!groundHit) return;

        double  springLen   = getGlobalPosition().distanceTo(groundPoint) - cfg.wheelRadius;
        double  compression = cfg.restDistance - springLen;

        Vector3 wheelMeshPos = wheelMesh.getPosition();
        wheelMeshPos.setY(GD.moveToward(wheelMeshPos.getY(), -springLen, 5 * getPhysicsProcessDeltaTime()));
        wheelMesh.setPosition(wheelMeshPos);

        Vector3 contact  = wheelMesh.getGlobalPosition();
        Vector3 forcePos = contact.minus(vehicle.getGlobalPosition());

        // Spring suspension force
        double springForceMag = cfg.springStrength * compression;
        Vector3 tireVelocity  = getPointVelocity(contact);
        double  dampForceMag  = cfg.springDamping * getGlobalBasis().getY().dot(tireVelocity);
        Vector3 yForce        = groundNormal.times(springForceMag - dampForceMag);

        // Motor force. speedRatio is measured in the COMMANDED direction (speed * sign(motor)),
        // so reverse tapers at maxSpeed exactly like forward. Previously a negative ratio made
        // accelRatio = 1 - ratio grow PAST 1 in reverse — reverse was uncapped and stronger than
        // forward (the "forward is much slower than backward" bug). Clamp the curve input too.
        if (isMotor && cmd.motor != 0) {
            double dirSpeed    = speed * Math.signum(cmd.motor);
            double speedRatio  = dirSpeed / cfg.maxSpeed;
            double accelRatio  = cfg.accelerationCurve != null
                    ? cfg.accelerationCurve.sampleBaked((float) GD.clamp(speedRatio, 0.0, 1.0))
                    : Math.max(0.0, 1.0 - speedRatio);
            Vector3 accelForce = forwardDir.times(cfg.acceleration * cmd.motor * accelRatio);
            vehicle.applyForce(accelForce, forcePos);
        }

        // Lateral (X) traction. Guard the slip ratio against a zero-length tire velocity — at
        // rest (e.g. the frame you enter a stationary vehicle) the division is 0/0 = NaN, and
        // gripCurve.sampleBaked(NaN) throws the "Curve point not finite" error.
        float  steeringXSpeed = (float) getGlobalBasis().getX().dot(tireVelocity);
        float  tireSpeed      = (float) tireVelocity.length();
        gripFactor = tireSpeed > 1e-3f ? (float) GD.abs(steeringXSpeed / tireSpeed) : 0f;
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
        if (!groundHit || groundPoint == null) {
            if (skidMark.isEmitting()) skidMark.setEmitting(false);   // airborne — no marks
            return;
        }
        skidMark.setGlobalPosition(groundPoint.plus(Vector3.Companion.getUP().times(0.01)));
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
