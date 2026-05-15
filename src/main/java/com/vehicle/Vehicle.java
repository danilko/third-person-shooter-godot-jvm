package com.vehicle;

import com.character.*;
import com.character.Character;
import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.*;
import godot.global.GD;

/**
 * Hovercraft vehicle.
 *
 * Four raycast wheels push the body upward from their corner positions so the
 * chassis floats at hoverHeight above the ground. All suspension, movement, and
 * camera work is done in _physicsProcess (no _integrateForces needed).
 *
 * Movement model:
 *   - Steering accumulates a camera yaw; the camera always looks from behind the
 *     hovercraft center along that yaw.
 *   - Throttle applies force along the camera forward direction.
 *   - Lateral velocity is cancelled every frame so the craft moves cleanly
 *     in the camera direction without drifting sideways.
 */
@RegisterClass(className = "Vehicle")
public class Vehicle extends RigidBody3D implements Controllable {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;

    /** Wheel visual scene shared across all four wheels (can be overridden per wheel). */
    @RegisterProperty @Export public PackedScene defaultWheelScene;

    /** Target hover distance from wheel position to ground (metres). */
    @RegisterProperty @Export public float hoverHeight = 0.8f;

    /** Hover spring stiffness (N/m). */
    @RegisterProperty @Export public float springStiffness = 15000f;

    /** Hover spring damper coefficient (N·s/m). */
    @RegisterProperty @Export public float springDamperStiffness = 2000f;

    /** Wheel visual radius for mesh positioning. */
    @RegisterProperty @Export public float wheelRadius = 0.35f;

    /** Engine thrust (N). */
    @RegisterProperty @Export public float enginePower = 24000f;

    /** Camera/steering turn rate (degrees/s). */
    @RegisterProperty @Export public float maxTurnAngleDegree = 90f;

    /** Longitudinal drag coefficient — resists forward/reverse velocity. */
    @RegisterProperty @Export public float dragForceFactor = 0.5f;

    /** Braking deceleration in m/s² (force = brakePower × mass). */
    @RegisterProperty @Export public float brakePower = 12f;

    /**
     * Lateral velocity cancellation fraction per physics frame: 0 = full drift, 1 = instant grip.
     * Values above 1 are clamped to 1 to prevent over-correction oscillation.
     */
    @RegisterProperty @Export public float lateralDampingFactor = 0.8f;

    @RegisterProperty @Export public NodePath wheelsPath            = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath       = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath cameraControllerPath = new NodePath("../CameraController");
    @RegisterProperty @Export public NodePath vehicleCamPath       = new NodePath("../CameraController/SpringArm3D/Camera3D");

    /** Maximum yaw rotation rate when fully misaligned (degrees/second). */
    @RegisterProperty @Export public float alignMaxDegPerSec = 120f;
    /**
     * Fraction of the yaw-rate gap closed per physics frame (0–1).
     * 1.0 = instant snap; ~0.2 = smooth ~10-frame ramp-up; ~0.5 = snappy ~5-frame ramp-up.
     */
    @RegisterProperty @Export public float alignBlend = 0.3f;

    /**
     * Extra yaw rate added on top of the tracking rate while steering (multiplier of cmd.steering).
     * 0 = no oversteer; ~0.5 = slight lead; ~1.0 = strong overshoot.
     * When steering stops the tracker corrects the overshoot naturally, giving the bounce-back.
     */
    @RegisterProperty @Export public float yawOversteerFactor = 1.5f;

    // ── Drift ─────────────────────────────────────────────────────────────────

    /** Offset angle from camFwd applied to the thrust direction when drift starts (radians). */
    @RegisterProperty @Export public float driftInitAngle = (float)(Math.PI / 4f);
    /** Fraction of normal drag during drift — lower keeps slide speed up. */
    @RegisterProperty @Export public float driftDragScale = 0.15f;
    /** Seconds to smoothly restore lateral grip after drift release. */
    @RegisterProperty @Export public float driftExitDuration = 0.35f;
    /** Speed during drift is hard-capped at getMaxSpeed() × this factor. */
    @RegisterProperty @Export public float driftSpeedCapFactor = 1.1f;

    // ── Roll ──────────────────────────────────────────────────────────────────

    /** Peak lean angle when steering is fully applied (degrees). */
    @RegisterProperty @Export public float rollAngleDeg = 10f;
    /** Roll spring stiffness — how forcefully the body leans in and snaps back (N·m/rad). */
    @RegisterProperty @Export public float rollSpring = 10000f;
    /**
     * Roll damping. Below critical (~5200 for default mass) gives a slight overshoot bounce;
     * above critical gives a smooth settled lean with no bounce.
     */
    @RegisterProperty @Export public float rollDamp = 3000f;


    // ── Camera constants ──────────────────────────────────────────────────────

    private static final float CAM_HEIGHT       = 2.5f;
    private static final float CAM_DISTANCE     = 7.0f;

    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller controller;
    protected Health     healthNode;
    protected Character  occupant;
    private boolean      justEntered = false;

    private Node3D   driverSeatNode;
    private Camera3D vehicleCamera;
    private Node     wheels               = null;
    protected Node3D   cameraControllerNode = null;

    private boolean drifting      = false;
    private int     driftSign     = 0;    // +1 = left drift, -1 = right drift
    private float   driftOffset   = 0f;  // radians [toRad(5), toRad(45)]: offset of effectiveFwd from camFwd
    private float   exitDampTimer  = 0f;                        // counts down for smooth lateral grip restore on exit
    private Vector3 exitTargetFwd  = new Vector3(0f, 0f, -1f); // last effectiveFwd at drift release, for yaw blend
    private Vector3 exitVelRight   = new Vector3(1f, 0f, 0f);  // right-perp of ACTUAL velocity at release, lateral ref

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        if (characterInfo == null) characterInfo = new CharacterInfo();
        addToGroup(new StringName("characters"), false);

        Node h = getNodeOrNull("Health");
        if (h instanceof Health hn) healthNode = hn;

        wheels = getNodeOrNull("Wheels");
        if (wheels != null) {
            int count = 0;
            for (Node child : wheels.getChildren()) {
                if (child instanceof VehicleWheel w) {
                    w.setVehicle(this);
                    w.applyDefaultScene(defaultWheelScene);
                    count++;
                }
            }
            GD.print("[Vehicle] _ready: " + count + " wheel(s) initialised");
        } else {
            GD.printErr("[Vehicle] Wheels node missing — hover disabled!");
        }

        Node seat = getNodeOrNull(driverSeatPath.getPath());
        if (seat instanceof Node3D n) driverSeatNode = n;

        Node cam = getNodeOrNull(vehicleCamPath.getPath());
        if (cam instanceof Camera3D c) vehicleCamera = c;

        Node cc = getNodeOrNull(cameraControllerPath.getPath());
        if (cc instanceof Node3D n) cameraControllerNode = n;
        else GD.printErr("[Vehicle] CameraController node missing at " + cameraControllerPath.getPath());

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }
    }

    // ── Physics ───────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (controller == null || !controller.isAuthority()) return;

        boolean enteredThisFrame = justEntered;
        justEntered = false;
        UserCommand cmd = controller.gatherInput(delta);
        if (cmd.enterExit && occupant != null && !enteredThisFrame) { tryExit(); return; }
        if (cmd.resetVehicle)                                       { resetOrientation(); return; }

        float dt = (float) delta;

        // ── 1. Hover: push upward at each wheel corner ────────────────────
        boolean anyOnGround = false;
        if (wheels != null) {
            for (Node child : wheels.getChildren()) {
                if (child instanceof VehicleWheel w && w.applyHoverForce(dt, this))
                    anyOnGround = true;
            }
        }

        if (cameraControllerNode == null) { return; }

        // ── 1. Camera follows the hovercraft center ───────────────────────
        cameraControllerNode.setGlobalPosition(getGlobalPosition());

        // ── 2. Steering camera yaw ────────────────────────────
        // During drift: auto-rotate camera at max turn rate in the drift direction.
        //   steer input does NOT rotate the camera — it only adjusts driftOffset below.
        // During normal driving: invert when reversing so rear goes in the steered direction.
        Vector3 vel = getLinearVelocity();
        if (vel.length() > 0) {
            if (drifting) {
                // Auto-rotate at max steer rate in the drift direction.
                float autoSteer = driftSign * (float) Math.toRadians(maxTurnAngleDegree);
                cameraControllerNode.rotateY(autoSteer * dt);
            } else {
                // Invert only when reversing (throttle < 0) so rear goes in steer direction.
                float steerSign = cmd.throttle < 0 ? -1f : 1f;
                cameraControllerNode.rotateY(cmd.steering * steerSign * dt);
            }
        }

        // During drift the front wheels turn into the drift direction, proportional to driftOffset.
        // driftOffset is last frame's value (one-frame lag), imperceptible visually.
        // driftOffset range [toRad(5), toRad(45)]; divide by PI/4 (max) to get [0,1] normalised.
        float visualSteer = drifting
            ? driftSign * (float)(driftOffset / (Math.PI / 4))
            : cmd.steering;
        updateWheelVisuals(dt, visualSteer);

        if (!anyOnGround) return;

        // ── 4. Movement (only when hovering over ground) ──────────────────

        // Flatten camera forward to horizontal so yaw-only steering stays level.
        Vector3 camFwdRaw = cameraControllerNode.getGlobalTransform().getBasis().getZ();
        Vector3 camFwd    = new Vector3((float)camFwdRaw.getX(), 0f, (float)camFwdRaw.getZ()).normalized().times(-1);
        Vector3 camRight  = cameraControllerNode.getGlobalTransform().getBasis().getX().normalized();

        // getBasis().getZ() = local +Z = backward; negate once to get actual 3D forward.
        Vector3 vehFwdRaw  = getGlobalTransform().getBasis().getZ();
        Vector3 vehFwd     = vehFwdRaw.times(-1);  // pitch-aware forward, reused for throttle
        Vector3 vehFwdFlat = new Vector3((float)vehFwd.getX(), 0f, (float)vehFwd.getZ()).normalized();

        float fwdSpeed = (float) vel.dot(camFwd);

        // ── Drift state machine ───────────────────────────────────────────────
        // Camera auto-rotates in drift direction; steer only controls driftOffset (0–90°).
        // effectiveFwd = camFwd rotated by (driftSign × driftOffset) around world Y.
        // Same-direction steer → offset grows (more perpendicular thrust → tighter circle).
        // Opposite steer       → offset shrinks (thrust more aligned with camFwd → wider circle).
        if (!drifting) {
            if (cmd.handbrake && Math.abs(cmd.steering) > 0.01f && fwdSpeed > 0.5f) {
                drifting    = true;
                driftSign   = cmd.steering > 0 ? 1 : -1;
                driftOffset = driftInitAngle;
            }
        } else {
            if (!cmd.handbrake) {
                // exitTargetFwd: last effectiveFwd (drift direction) captured BEFORE driftOffset
                // is reset. Used as the yaw alignment start-point for the smooth blend to camFwd.
                Vector3 exitFwdRaw = camFwd.rotated(Vector3.Companion.getUP(), driftSign * driftOffset);
                exitTargetFwd = new Vector3(
                    (float)exitFwdRaw.getX(), 0f, (float)exitFwdRaw.getZ()).normalized();

                // exitVelRight: right-perp of ACTUAL velocity (not effectiveFwd).
                // The vehicle's real velocity can differ from effectiveFwd (inertia + centripetal
                // projection). Using actual vel ensures lateralRef ⊥ vel → dot = 0 → no speed loss.
                Vector3 velFlat = new Vector3((float)vel.getX(), 0f, (float)vel.getZ());
                if (velFlat.length() > 0.1f)
                    exitVelRight = velFlat.normalized().cross(Vector3.Companion.getUP()).normalized();

                drifting      = false;
                driftSign     = 0;
                driftOffset   = 0f;
                exitDampTimer = driftExitDuration;
            } else {
                // Same-direction steer → offset grows; opposite → shrinks. Clamped [5°, 45°].
                driftOffset += driftSign * cmd.steering * dt;
                driftOffset  = (float) Math.max(Math.toRadians(5), Math.min(Math.toRadians(45), driftOffset));
            }
        }

        // effectiveFwd: camFwd rotated by driftSign * driftOffset degrees around world Y.
        // When not drifting (driftOffset = 0) this is just camFwd.
        final Vector3 effectiveFwd;
        if (drifting && driftOffset > 0f) {
            effectiveFwd = camFwd.rotated(Vector3.Companion.getUP(), driftSign * driftOffset).normalized();
        } else {
            effectiveFwd = camFwd;
        }

        // Lateral velocity cancellation.
        // During drift: 0 (vehicle slides freely).
        // After drift release: smoothly ramp back in over driftExitDuration so there is no
        // sudden speed loss when the player lets go of the drift button.
        // Normal: full lateralDampingFactor.
        float dampFraction;
        if (drifting) {
            dampFraction = 0f;
        } else if (exitDampTimer > 0f) {
            exitDampTimer = Math.max(0f, exitDampTimer - dt);
            float t = 1f - exitDampTimer / driftExitDuration;
            dampFraction = (float) GD.clamp(t * lateralDampingFactor, 0.0, 1.0);
        } else {
            dampFraction = (float) GD.clamp(lateralDampingFactor, 0.0, 1.0);
        }
        // During exitDampTimer use the velocity-relative right captured at drift release,
        // not camRight. After a long drift camRight can be 180° rotated and would project
        // directly onto the vehicle's velocity, cancelling all speed. exitVelRight is
        // perpendicular to the actual travel direction so only genuine new lateral drift is damped.
        Vector3 lateralRef        = (exitDampTimer > 0f) ? exitVelRight : camRight;
        float currentLateralSpeed = (float) lateralRef.dot(vel);
        applyCentralForce(lateralRef.times((-currentLateralSpeed / dt) * getMass() * dampFraction));

        // Yaw alignment target: during exitDampTimer, lerp from the last drift direction
        // (exitTargetFwd) toward camFwd so the vehicle body rotates smoothly instead of snapping.
        // t goes 0→1 over driftExitDuration; at t=1 target == camFwd, normal driving resumes.
        final Vector3 yawTarget;
        if (exitDampTimer > 0f && driftExitDuration > 0f) {
            float t = 1f - exitDampTimer / driftExitDuration;
            yawTarget = exitTargetFwd.lerp(camFwd, t).normalized();
        } else {
            yawTarget = effectiveFwd; // = driftFwd while drifting, = camFwd in normal driving
        }

        // Yaw alignment: track yawTarget (blended during exit, effectiveFwd otherwise).
        // Oversteer boost is disabled during drift — the drift angle itself drives steering.
        double  angleOffset   = vehFwdFlat.signedAngleTo(yawTarget, Vector3.Companion.getUP());
        float   maxYawRad     = (float) Math.toRadians(alignMaxDegPerSec);
        float   trackingRate  = (float) GD.clamp(angleOffset * (maxYawRad / Math.toRadians(20.0)), -maxYawRad, maxYawRad);
        float   oversteer     = drifting ? 0f : cmd.steering * yawOversteerFactor;
        float   desiredYawRate = trackingRate + oversteer;
        Vector3 angVel        = getAngularVelocity();
        angVel.setY(GD.lerp(angVel.getY(), (double) desiredYawRate, (double) alignBlend));
        setAngularVelocity(angVel);

        // Body roll spring. During drift, lean is based on the drift offset magnitude.
        // driftOffset is in radians [0, π/4]; divide by π/4 to normalise to [0, 1].
        float rollInput = drifting ? -driftSign * (float)(driftOffset / (Math.PI / 4)) : -cmd.steering;
        float   targetRollRad = rollInput * (float) Math.toRadians(rollAngleDeg);
        Vector3 rollAxis      = getGlobalTransform().getBasis().getZ().normalized();
        double  currentRoll   = getGlobalTransform().getBasis().getY().signedAngleTo(Vector3.Companion.getUP(), rollAxis);
        double  rollAngVel    = getAngularVelocity().dot(rollAxis);
        double  rollTorque    = ((targetRollRad - currentRoll) * rollSpring) - (rollAngVel * rollDamp);
        applyTorque(rollAxis.times(rollTorque));

        // Throttle.
        // During drift: push along effectiveFwd (camFwd + offset) to create the arc.
        // When the camera has rotated far, effectiveFwd can oppose velocity. Rather than
        // switching fully to the velocity direction (which breaks the circle), project
        // effectiveFwd onto the hemisphere facing the velocity: strip the opposing component
        // and keep only the centripetal/steering part. Speed is maintained by low drag + speed cap.
        float   throttle = getThrottleInput(cmd.throttle);
        Vector3 thrustDir;
        if (drifting) {
            Vector3 baseDir = new Vector3(
                (float) effectiveFwd.getX(),
                (float) vehFwd.getY(),
                (float) effectiveFwd.getZ()
            ).normalized();
            if (vel.length() > 0.1f) {
                Vector3 velNorm   = vel.normalized();
                float   alignment = (float) velNorm.dot(baseDir);
                if (alignment < 0f) {
                    // Remove the opposing component; keep the centripetal steering component.
                    Vector3 centripetal = baseDir.minus(velNorm.times(alignment));
                    thrustDir = centripetal.length() > 0.01f ? centripetal.normalized() : velNorm;
                } else {
                    thrustDir = baseDir;
                }
            } else {
                thrustDir = baseDir;
            }
        } else {
            thrustDir = vehFwd;
        }
        applyCentralForce(thrustDir.times(throttle * enginePower));

        // Slope gravity compensation: counteract the gravitational component along the slope so
        // the vehicle maintains the same effective forward thrust as on flat ground.
        // vehFwd.Y == sin(pitch_angle) (unit vector), so mass × 9.8 × vehFwd.Y == the gravity
        // force opposing uphill motion. Applied only when going uphill (vehFwd.Y > 0) and
        // throttle is pressed; downhill gravity is left to act naturally as a speed bonus.
        float slopeComp = getMass() * 9.8f * Math.max(0f, (float) vehFwd.getY());
        if (slopeComp > 0.1f && throttle > 0f)
            applyCentralForce(vehFwd.times(slopeComp));

        // Drag.
        // During drift: velocity-based drag at reduced scale so the slide maintains speed.
        //   Also applies a hard speed cap via impulse each frame to prevent runaway acceleration.
        // Normal: camFwd-based drag limits top speed along the camera direction.
        if (drifting) {
            float speed = (float) vel.length();
            if (speed > 0.01f)
                applyCentralForce(vel.normalized().times(-speed * getMass() * dragForceFactor * driftDragScale));
            float maxDriftSpeed = getMaxSpeed() * driftSpeedCapFactor;
            if (speed > maxDriftSpeed)
                applyImpulse(vel.normalized().times(-(speed - maxDriftSpeed) * getMass()));
        } else {
            applyCentralForce(camFwd.times(-fwdSpeed * getMass() * dragForceFactor));
        }

        // Braking suppressed during drift (handbrake is the drift trigger).
        if (cmd.handbrake && !drifting && (float) vel.length() > 0.5f)
            applyCentralForce(vel.normalized().times(-brakePower * getMass()));
    }

    /** Subclass hook — override to cap throttle at a speed limit. */
    protected float getThrottleInput(float raw) { return raw; }

    /** Maximum speed (m/s) used for the drift boost cap. Override in subclasses with a real limit. */
    protected float getMaxSpeed() { return Float.MAX_VALUE; }

    private void resetOrientation() {
        setLinearVelocity(new Vector3(0f, 0f, 0f));
        setAngularVelocity(new Vector3(0f, 0f, 0f));
        setRotation(new Vector3(0f, 0f, 0f));
        Vector3 pos = getGlobalPosition();
        setGlobalPosition(new Vector3(pos.getX(), pos.getY() + hoverHeight * 2f + 1.0f, pos.getZ()));
    }

    private void updateWheelVisuals(float delta, float steering) {
        if (wheels == null) return;
        float forwardSpeed = (float) getLinearVelocity().dot(cameraControllerNode.getGlobalTransform().getBasis().getZ().times(-1));
        for (Node child : wheels.getChildren()) {
            if (child instanceof VehicleWheel w)
                w.updateVisual(delta, forwardSpeed, steering);
        }
    }

    // ── Controllable ──────────────────────────────────────────────────────────

    @Override public void applyCommand(UserCommand cmd, double delta) { }
    @Override public CharacterInfo getCharacterInfo() { return characterInfo; }

    // ── Enter / Exit ──────────────────────────────────────────────────────────

    public void tryEnter(Character c) {
        if (occupant != null) return;
        occupant = c;
        Controller ctrl = c.detachController();
        if (ctrl != null) attachController(ctrl);
        c.setVisible(false);
        c.setPhysicsProcess(false);
        Node mc = c.getNodeOrNull("MovementController");
        if (mc != null) mc.setPhysicsProcess(false);
        if (vehicleCamera != null) vehicleCamera.makeCurrent();
        justEntered = true;
        emitEnterPrompt(false);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.vehicleEntered.emit(this, c.characterInfo);
        GD.print("[Vehicle] " + c.getName() + " entered");
    }

    public void tryExit() {
        if (occupant == null) return;
        Character c = occupant;
        occupant = null;
        Vector3 right   = getGlobalTransform().getBasis().getColumn(0);
        Vector3 exitPos = getGlobalPosition()
            .minus(right.times(1.5f)).plus(new Vector3(0f, 0.8f, 0f));
        c.setGlobalPosition(exitPos);
        c.setVisible(true);
        c.setPhysicsProcess(true);
        Node mc = c.getNodeOrNull("MovementController");
        if (mc != null) mc.setPhysicsProcess(true);
        Controller ctrl = detachController();
        if (ctrl != null) c.attachController(ctrl);
        c.makeCameraActive();
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.vehicleExited.emit(c.characterInfo);
    }

    // ── EntranceArea signals ──────────────────────────────────────────────────

    @RegisterFunction
    public void onEntranceBodyEntered(Node3D body) {
        Character c = resolveCharacter(body);
        if (c == null || occupant != null) return;
        if (c instanceof Player p) {
            p.nearbyVehicle = this;
            emitEnterPrompt(true);
        }
    }

    @RegisterFunction
    public void onEntranceBodyExited(Node3D body) {
        Character c = resolveCharacter(body);
        if (c == null) return;
        if (c instanceof Player p) {
            p.nearbyVehicle = null;
            emitEnterPrompt(false);
        }
    }

    private Character resolveCharacter(Node3D body) {
        if (body instanceof Character c) return c;
        Node owner = body.getOwner();
        if (owner instanceof Character c) return c;
        return null;
    }

    private void emitEnterPrompt(boolean inRange) {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus)
            bus.pickupInteractChanged.emit(inRange, inRange ? "Enter vehicle" : "");
    }

    // ── Controller hot-swap ───────────────────────────────────────────────────

    public Controller detachController() {
        if (controller == null) return null;
        Controller ctrl = controller;
        removeChild(ctrl);
        controller = null;
        return ctrl;
    }

    public void attachController(Controller ctrl) {
        if (controller != null) removeChild(controller);
        controller = ctrl;
        addChild(ctrl);
    }

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }
}
