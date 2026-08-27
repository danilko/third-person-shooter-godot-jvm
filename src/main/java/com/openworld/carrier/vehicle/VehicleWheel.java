package com.openworld.carrier.vehicle;

import com.openworld.control.UserCommand;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
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
@Script(className = "VehicleWheel")
public class VehicleWheel extends RayCast3D {

    private static final float TWO_PI = (float)(2.0 * Math.PI);

    // ── Per-wheel structural exports (set in scene, NOT in VehicleConfig) ─────

    /** Optional per-wheel visual mesh override. Null = use the Vehicle's default wheel mesh. */
    @Export public PackedScene wheelScene;

    /** True when this wheel is driven by the motor. */
    @Export public boolean isMotor = false;

    /** True when this wheel turns with steering input. */
    @Export public boolean isSteer = false;

    /**
     * Tire lateral-grip curve. X = slip ratio (0=aligned, 1=pure sideways), Y = grip [0–1].
     * Rear wheels typically have a softer curve than front wheels to enable controlled drift.
     */
    @Export public Curve gripCurve;

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

    /** Suspension compression (m) from the last simulated frame; 0 when airborne. Read by the anti-roll bar. */
    private float lastCompression = 0f;

    public float getLastCompression() { return lastCompression; }

    // ── Damageable tire (shoot the TireHit collider → flat) ──────────────────
    // Per-wheel state lives HERE, never on the shared VehicleConfig resource — effective
    // radius/rest are computed, cfg is read-only.

    private float   tireHealth = Float.MAX_VALUE;
    private boolean flat       = false;

    public boolean isFlat() { return flat; }

    /** Effective rolling radius — a flat rides on the rim. */
    private float effRadius() { return flat ? cfg.wheelRadius * cfg.flatRadiusScale : cfg.wheelRadius; }

    /** Effective suspension rest distance — a flat corner sags. */
    private float effRest()   { return flat ? cfg.restDistance * cfg.flatRestScale : cfg.restDistance; }

    /**
     * Authority-side tire hit ({@code ImpactManager} routes a TireHit collider hit here
     * before the body Health). Only the simulating peer mutates flat state — a client's
     * cosmetic-only hit resolution never flattens a puppet's tire (the replicated
     * flatMask is the single source of truth and heals any drift).
     *
     * @return the reduced damage that should continue on to the vehicle body Health.
     */
    public float applyTireDamage(float damage) {
        if (cfg == null) return damage;
        if (vehicle != null && vehicle.isLocallySimulated() && !flat) {
            tireHealth -= damage;
            if (tireHealth <= 0f) setFlat(true);
        }
        return damage * cfg.tireDamagePassthrough;
    }

    /**
     * Idempotent flat application — also the puppet replication path (snapshot flatMask).
     * Visual: the wheel mesh's radius plane (its local X/Z — local Y is the cylinder's
     * width axis) squashes by flatRadiusScale; rotationally symmetric about the spin axis,
     * so the constantly-spinning mesh never shears.
     */
    public void setFlat(boolean value) {
        if (flat == value) return;
        flat = value;
        if (cfg != null && !value) tireHealth = cfg.tireMaxHealth;   // re-inflate (fresh spawn)
        if (wheelMesh != null && cfg != null) {
            float s = value ? cfg.flatRadiusScale : 1f;
            wheelMesh.setScale(new Vector3(s, 1f, s));
        }
        if (vehicle != null) vehicle.wakeUp();   // a parked car sags awake when shot flat
    }

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

    @Register
    @Override
    public void _ready() {
        vehicle = (Vehicle) getOwner();
        wheelMesh = (Node3D) getNode("Wheel");
        skidMark = (GPUParticles3D) getNode("SkidMark");

        // cfg is injected by Vehicle._ready() via setup() BEFORE VehicleWheel._ready()
        // fires (parent _ready runs after children). Guard against unset cfg at startup.
        if (cfg == null) cfg = vehicle.getConfig();
        tireHealth = cfg.tireMaxHealth;

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
        // Landing lead: extend the ray by ~2 ticks of fall distance so a hard landing is
        // detected BEFORE the ray origin ends up under the surface — a fast fall covers
        // more than the whole suspension window per 60 Hz tick, after which the ray starts
        // underground and never sees the ground again (the intermittent high-speed floor
        // clip). Target is set before the forced update so the lead applies this tick.
        float fallSpeed = (float) Math.max(0.0, -vehicle.getLinearVelocity().getY());
        float fallLead  = fallSpeed * physDelta * 2f;
        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(effRest() + effRadius() + cfg.overExtend + fallLead));
        setTargetPosition(targetPosition);
        forceRaycastUpdate();

        // Rotate wheel visuals
        Vector3 forwardDir = getGlobalBasis().getZ().times(-1);
        double speed = forwardDir.dot(vehicle.getLinearVelocity());
        wheelMesh.rotateX((float)((-speed * physDelta) / effRadius()));

        // Aggregate the centre ray + any extra contact-patch probes into one contact.
        sampleGround();
        if (!groundHit) { lastCompression = 0f; return; }

        double  springLen   = getGlobalPosition().distanceTo(groundPoint) - effRadius();
        // A hit past the normal suspension window is only reachable via the fall lead:
        // no spring force there (negative compression would be suction yanking the car
        // DOWN); the damping term below still pre-brakes the fall, upward only.
        boolean leadZoneHit = springLen > effRest() + cfg.overExtend;
        double  compression = leadZoneHit ? 0.0 : effRest() - springLen;
        lastCompression = (float) compression;

        // Mesh never dangles past the normal window while the lead ray reaches further.
        double displayLen = Math.min(springLen, effRest() + cfg.overExtend);
        Vector3 wheelMeshPos = wheelMesh.getPosition();
        wheelMeshPos.setY(GD.moveToward(wheelMeshPos.getY(), -displayLen, 5 * getPhysicsProcessDeltaTime()));
        wheelMesh.setPosition(wheelMeshPos);

        Vector3 contact  = wheelMesh.getGlobalPosition();
        Vector3 forcePos = contact.minus(vehicle.getGlobalPosition());

        // Spring suspension force
        double springForceMag = cfg.springStrength * compression;
        Vector3 tireVelocity  = getPointVelocity(contact);
        double  dampForceMag  = cfg.springDamping * getGlobalBasis().getY().dot(tireVelocity);
        if (leadZoneHit && dampForceMag > 0.0) dampForceMag = 0.0;   // never pull toward ground
        Vector3 yForce        = groundNormal.times(springForceMag - dampForceMag);

        // Motor force. speedRatio is measured in the COMMANDED direction (speed * sign(motor)),
        // so reverse tapers at maxSpeed exactly like forward. Previously a negative ratio made
        // accelRatio = 1 - ratio grow PAST 1 in reverse — reverse was uncapped and stronger than
        // forward (the "forward is much slower than backward" bug). Clamp the curve input too.
        // Explicit governor: maxSpeed (boost ceiling while boosting) is a hard top-speed
        // cap, not merely where the curve happens to run out — so a plateau-shaped curve
        // can keep enough force to actually REACH maxSpeed without overshooting it.
        // Reverse gets its own much lower ceiling (arcade: cars back up slowly).
        double ceiling = vehicle.getBoostMaxSpeed()
                * (cmd.motor < 0f ? cfg.reverseSpeedFraction : 1f);
        if (isMotor && cmd.motor != 0 && speed * Math.signum(cmd.motor) < ceiling) {
            double dirSpeed    = speed * Math.signum(cmd.motor);
            // Boost raises the curve ceiling (higher effective maxSpeed) AND the force —
            // NOS pushes past the normal top speed instead of just reaching it faster.
            double speedRatio  = dirSpeed / ceiling;
            double accelRatio  = cfg.accelerationCurve != null
                    ? cfg.accelerationCurve.sampleBaked((float) GD.clamp(speedRatio, 0.0, 1.0))
                    : Math.max(0.0, 1.0 - speedRatio);
            double motorScale = (flat ? cfg.flatMotorScale : 1.0) * vehicle.getBoostAccelScale();
            // Launch punch: FORWARD only (signed speed clamps to ratio 0 in reverse, which
            // used to keep the boost active for the whole reverse run), fading out by
            // launchBoostEndRatio of base maxSpeed (not the boost ceiling — NOS shouldn't
            // re-arm the launch kick).
            if (cmd.motor > 0f && cfg.launchBoost > 1f && cfg.launchBoostEndRatio > 1e-3f) {
                double baseRatio = GD.clamp(speed / Math.max(1e-3f, cfg.maxSpeed), 0.0, 1.0);
                motorScale *= 1.0 + (cfg.launchBoost - 1.0)
                        * Math.max(0.0, 1.0 - baseRatio / cfg.launchBoostEndRatio);
            }
            Vector3 accelForce = forwardDir.times(cfg.acceleration * cmd.motor * accelRatio * motorScale);
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
        // Drift: uniform low grip — the car slides on all four; rotation authority comes
        // from Vehicle's steering-controlled driftYawTorque, not grip asymmetry (front
        // bite self-stalls at an equilibrium angle — it aligns against further rotation).
        if (cmd.handbrake) {
            xTraction = cfg.driftGrip;
        } else if (vehicle.isSlipping()) xTraction = 0.1;
        if (flat) xTraction *= cfg.flatGripScale;   // a flat corner slides — the handling destabilizer

        double gravity = -vehicle.getGravity().getY();
        // Friction circle: each wheel's lateral force is capped at its share of
        // maxLateralG — slip-proportional force otherwise exceeds 2 g in a hard turn
        // (10 m circles at 70 km/h), where real/arcade cars widen the arc instead.
        double latAccel = Math.abs(steeringXSpeed) * xTraction * gravity;  // demanded, m/s²
        if (cfg.maxLateralG > 0f) latAccel = Math.min(latAccel, cfg.maxLateralG * gravity);
        Vector3 xForce = getGlobalBasis().getX().times(
                -Math.signum(steeringXSpeed) * latAccel * (vehicle.getMass() / 4.0));

        // Anti-flip (GTA-style): lateral grip applied AT THE CONTACT has a roll lever arm
        // about the CoM — at speed that torque is what flips the car in a hard swerve. Lift
        // the application point toward CoM HEIGHT as speed rises (same force, no roll
        // moment), leaving parking-speed feel untouched. Spring + zForce stay at the true
        // contact. The CoM is retuned per-tick (grounded/airborne) — read it live.
        Vector3 xForcePos = forcePos;
        if (cfg.lateralForceHeightBlend > 0f) {
            float speedRatio = (float) GD.clamp(
                    vehicle.getLinearVelocity().length() / Math.max(1e-3f, cfg.maxSpeed), 0.0, 1.0);
            // Full blend by lateralBlendFullRatio, not maxSpeed — peak cornering force (and
            // its roll moment) occurs at mid speeds where steering still allows big angles.
            float blend = cfg.lateralForceHeightBlend
                    * Math.min(1f, speedRatio / Math.max(1e-3f, cfg.lateralBlendFullRatio));
            Vector3 bodyUp    = vehicle.getGlobalBasis().getY();
            Vector3 comOffset = vehicle.getGlobalBasis().xform(vehicle.getCenterOfMass());
            double  heightGap = bodyUp.dot(comOffset.minus(forcePos));
            xForcePos = forcePos.plus(bodyUp.times(heightGap * blend));
        }

        // Longitudinal (Z) friction
        double forwardSpeed = forwardDir.dot(tireVelocity);
        float  zFriction    = cfg.zTraction;
        if (vehicle.isBraking()) {
            zFriction = cfg.zBrakeTraction;
        } else if (Math.abs(cmd.motor) < 0.01f && Math.abs(forwardSpeed) < 0.5f) {
            zFriction = cfg.zBrakeTraction;  // parking friction on slopes
        }

        // Saturate the speed factor: rolling resistance is ~constant and brakes deliver a
        // fixed ~1.5 g in reality — ∝v forever made braking absurd at speed and capped top
        // speed at ~74 km/h no matter the motor. Low-speed behaviour (< saturation speed,
        // incl. parking friction) is unchanged; aero drag is the high-speed limiter now.
        double sat = Math.max(0.5f, cfg.longFrictionSaturationSpeed);
        double effForwardSpeed = GD.clamp(forwardSpeed, -sat, sat);
        Vector3 zForce = vehicle.getGlobalBasis().getZ().times(
                effForwardSpeed * zFriction * (vehicle.getMass() * gravity / vehicle.getWheels().size()));

        vehicle.applyForce(xForce, xForcePos);
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

        // Hard braking at speed lays rubber too, not just the handbrake — the arcade
        // "tires locked" readout (marks stop below ~4 m/s as the car comes to rest).
        boolean brakeSkid = vehicle.isBraking() && vehicle.getLinearVelocity().length() > 4.0;
        if (!vehicle.isHandbraking() && !brakeSkid && gripFactor < 0.2f) {
            vehicle.setSlipping(false);
            skidMark.setEmitting(false);
        }
        if ((vehicle.isHandbraking() || brakeSkid) && !skidMark.isEmitting()) {
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

        wheelMesh.rotateX((-forwardSpeed * delta) / effRadius());

        forceRaycastUpdate();
        if (isColliding()) {
            double springLen = getGlobalPosition().distanceTo(getCollisionPoint()) - effRadius();
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

    /**
     * Max steer angle available RIGHT NOW — shrinks with speed (GTA-style stability).
     * Full lock below steeringLimitStartRatio of maxSpeed, easing down to
     * steeringHighSpeedFraction of full lock at maxSpeed. Puppet visual replay keeps the
     * static limits (the replicated angle was already limited at its source).
     */
    private float effectiveMaxTurnRad() {
        float frac = cfg.steeringHighSpeedFraction;
        if (frac >= 1f) return tireMaxTurnMaxRad;
        float ratio = (float) (vehicle.getLinearVelocity().length() / Math.max(1e-3f, cfg.maxSpeed));
        float start = cfg.steeringLimitStartRatio;
        float t = (float) GD.clamp((ratio - start) / Math.max(1e-3f, 1f - start), 0.0, 1.0);
        return tireMaxTurnMaxRad * (float) GD.lerp(1f, frac, t);
    }

    public void applyWheelSteering(float delta, float steering, boolean steerToTarget) {
        if (!isSteer) return;
        float effMaxRad = effectiveMaxTurnRad();
        Vector3 rotation = getRotation();
        if (steerToTarget) {
            // AI: `steering` is a normalized TARGET angle [-1,1]; converge the wheel to it (and hold
            // it) at the steer rate. Unlike the rate model below, this settles at any intermediate
            // angle instead of winding to full lock — the cornering-wobble fix (I3b). The normalized
            // target scales by the speed-limited angle, so AI authority shrinks at speed too
            // (junctionThrottleScale already keeps AI slow where full lock matters).
            float target = (float) GD.clamp(steering, -1f, 1f) * effMaxRad;
            rotation.setY((float) GD.moveToward(rotation.getY(), target, cfg.tireMaxTurnSpeed * delta));
        } else if (steering != 0) {
            // Player: `steering` is a turn rate the wheel integrates (hold-to-turn).
            float rotY = (float) GD.clamp(rotation.getY() + steering * delta, -effMaxRad, effMaxRad);
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
