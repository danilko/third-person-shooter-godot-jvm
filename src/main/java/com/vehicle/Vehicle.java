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
 * Arcade vehicle — physics inspired by the Parking Garage Rally Circuit talk.
 *
 * Three core concepts, now reflected directly in the scene-node structure:
 *
 *  1. Camera drives, car follows (Mario Kart theory)
 *     vehicleYaw accumulates steering input each frame. desiredForward is derived
 *     from vehicleYaw. CameraController (sibling Node3D, NOT a child of the physics
 *     body) is written each frame: global position = vehicle pos + yaw-rotated offset,
 *     rotation Y = vehicleYaw only. Roll and pitch from suspension are excluded.
 *
 *  2. Physics body tracks full heading (moveFwd)
 *     The RigidBody3D's Y angular velocity = steering rate + drift-angle rate each frame,
 *     so the body always faces moveFwd (desiredForward + drift offset). VehicleWheel
 *     positions (children of the body) therefore align with the visual chassis corners
 *     including during drift, so suspension raycasts fire from the correct corners.
 *     X/Z angular velocity is capped to prevent flipping from wall collisions.
 *
 *  3. BodyMesh provides visual lean only
 *     BodyMesh (Node3D, parent of Chassis mesh + CollisionShape3D) keeps local Y = 0 —
 *     the body already faces moveFwd. BodyMesh only applies X (nose-down pitch) and
 *     Z (sideways roll) for the cornering lean effect.
 *
 * Physics split:
 *   _integrateForces → suspension only via state.applyForce() (same-step).
 *   _physicsProcess  → all driving via body.applyXxx() (next-step queue).
 */
@RegisterClass(className = "Vehicle")
public class Vehicle extends RigidBody3D implements Controllable {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;

    /**
     * Wheel visual scene applied to every wheel that does not have its own
     * wheelScene set. Build one scene in the editor with the correct scale,
     * rotation, and pivot for the imported asset; assign it here to share it
     * across all four wheels without repeating the same setting per wheel.
     * Per-wheel overrides still work: leave this null and set wheelScene on
     * individual VehicleWheel nodes, or mix both for front/rear differences.
     */
    @RegisterProperty @Export public PackedScene defaultWheelScene;

    /** Engine thrust in Newtons (force = throttle × enginePower × 2). */
    @RegisterProperty @Export public float enginePower = 10000f;

    /**
     * How fast CameraController rotates per second (degrees/s).
     * This is the steering rate of the "camera direction" the player controls.
     */
    @RegisterProperty @Export public float maxTurnAngleDegree = 90f;

    /**
     * BodyMesh spring response — how quickly the chassis mesh rotates to face
     * the target direction each frame.
     * Factor applied per second: newAngle = currentAngle + diff × min(1, response × delta).
     * 6 = very snappy (nearly instant). 3 = visible lag / floaty feel.
     */
    @RegisterProperty @Export public float turnSpringResponse = 3f;

    /**
     * Max chassis visual offset from desiredForward during normal driving (degrees).
     * Proportional to steering input: full steer = this angle; release = springs to 0.
     */
    @RegisterProperty @Export public float normalBodyAngle = 10f;

    /**
     * Max chassis visual offset from desiredForward during drift (degrees).
     * Same direct-proportional logic as normalBodyAngle but larger.
     */
    @RegisterProperty @Export public float maxDriftAngle = 35f;

    /** How fast the chassis visual offset springs toward its target each second. */
    @RegisterProperty @Export public float driftAngleLerpSpeed = 6f;

    /**
     * Camera turn rate while drifting (degrees/s). Higher than maxTurnAngleDegree
     * so the handle can swing wider during a drift.
     */
    @RegisterProperty @Export public float driftTurnRateDegree = 150f;

    /**
     * Visual roll angle (radians) applied to BodyMesh per rad/s of yaw rate.
     * Leans the chassis mesh into corners without touching the physics body.
     * 0 = no lean. 0.10–0.20 = subtle. 0.25+ = aggressive.
     * Builds up quickly when steering, decays slowly when released.
     */
    @RegisterProperty @Export public float visualLeanFactor = 0.15f;

    /** Lateral correction strength (relative to movement direction). 6 = strong grip. */
    @RegisterProperty @Export public float lateralForceFactor = 6f;

    /**
     * Lateral grip reduction at full steering input (0–1).
     * 0 = full grip always (no sliding on turns).
     * 0.5 = grip drops to 50% of lateralForceFactor at full steer.
     * 1.0 = zero grip at full steer (identical to drift sliding).
     */
    @RegisterProperty @Export public float turnSlideReduction = 0.4f;

    /** Lateral correction during drift. 0.3 = noticeable slide without runaway. */
    @RegisterProperty @Export public float driftLateralFactor = 0.3f;

    /**
     * Max degrees by which counter-steering reduces the locked drift angle.
     * At full counter-steer the drift angle becomes (maxDriftAngle − maxDriftReduction).
     * 0 = counter-steer has no effect; maxDriftAngle = counter-steer cancels drift entirely.
     */
    @RegisterProperty @Export public float maxDriftReduction = 10f;

    /** Hard cap on lateral speed (m/s) during drift. 10–14 = strong visible slip. */
    @RegisterProperty @Export public float maxDriftLateralSpeed = 12f;

    /** Longitudinal drag coefficient. */
    @RegisterProperty @Export public float dragForceFactor = 0.3f;

    /** Braking deceleration in m/s² (force = brakePower × mass). */
    @RegisterProperty @Export public float brakePower = 12f;

    /** Minimum forward speed (m/s) before steering and BodyMesh posing activate. */
    @RegisterProperty @Export public float minSpeedForTurn = 1f;

    /** Maximum spring compression travel in metres. */
    @RegisterProperty @Export public float maxSpringLength = 0.5f;

    /**
     * Spring stiffness (N/m). Higher values pitch the nose up faster when the
     * front wheels hit a slope, helping the chassis clear the transition edge.
     * 25000 is roughly 2× the minimum needed to support vehicle weight at rest
     * with half the spring travel used — gives a firm, responsive suspension.
     */
    @RegisterProperty @Export public float springStiffness = 25000f;

    /** Spring damper coefficient (N·s/m). Scale with springStiffness to prevent bounce. */
    @RegisterProperty @Export public float springDamperStiffness = 4000f;

    /** Wheel radius in metres. */
    @RegisterProperty @Export public float wheelRadius = 0.35f;

    @RegisterProperty @Export public NodePath wheelsPath            = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath       = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath cameraControllerPath = new NodePath("../CameraController");
    @RegisterProperty @Export public NodePath vehicleCamPath       = new NodePath("../CameraController/SpringArm3D/Camera3D");

    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller controller;
    protected Health     healthNode;
    protected Character  occupant;
    // True for the one physics frame in which tryEnter() was called.
    // Prevents Vehicle._physicsProcess — running later in the same frame —
    // from reading the still-true isActionJustPressed("interact") and
    // immediately calling tryExit().
    private boolean justEntered = false;

    private Node3D   driverSeatNode;
    private Camera3D vehicleCamera;
    private Node     wheels               = null;

    // Scene nodes that implement the "camera drives, car poses" concept.
    private Node3D   cameraControllerNode = null; // player steers this
    private Node3D   bodyMeshNode         = null; // chassis mesh + collision pivot

    // Camera offset constants — match the CameraController's original local offset.
    private static final float CAM_HEIGHT       = 2.5f;
    private static final float CAM_DISTANCE     = 7.0f;
    private static final float CAM_FOLLOW_SPEED = 12.0f;

    // Set by _integrateForces each step; gates force application in _physicsProcess.
    private boolean isOnGround = false;

    // Shared by _integrateForces and _physicsProcess — keeps both caps identical.
    private static final float MAX_TILT = 3.0f;

    // desiredForward: world-space horizontal unit vector derived from vehicleYaw each frame.
    // Protected so GroundVehicle can use it for a direction-aware throttle cap.
    protected Vector3 desiredForward = new Vector3(0f, 0f, -1f);

    // CameraController yaw (radians). Accumulated from steering input — this IS the
    // "handle" direction. desiredForward is derived from it each frame.
    private float vehicleYaw     = 0f;

    // Total body yaw rate (rad/s) = steering rate + drift-angle rate. Written each
    // frame; consumed by _integrateForces to drive the body's Y angular velocity so
    // the body faces moveFwd (desiredForward + drift offset) at all times.
    private float vehicleYawRate = 0f;

    // Drift / turn state
    private boolean isDrifting        = false;
    private float   driftDirection    = 1f;   // +1 = right, -1 = left — locked at drift entry
    private float   currentDriftAngle = 0f;   // current chassis visual offset (degrees, signed)
    private float   driftBoosterTimer = 0f;   // seconds of banked boost available on drift exit
    private float   currentRollVisual = 0f;   // lerped BodyMesh Z-roll for cornering lean (radians)

    // Lateral factor lerped to avoid ABS-clip on drift exit
    private float currentLatFactor = 6f;      // initialised in _ready to lateralForceFactor

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
            GD.printErr("[Vehicle] Wheels node missing — suspension disabled!");
        }

        Node seat = getNodeOrNull(driverSeatPath.getPath());
        if (seat instanceof Node3D n) driverSeatNode = n;

        Node cam = getNodeOrNull(vehicleCamPath.getPath());
        if (cam instanceof Camera3D c) vehicleCamera = c;

        Node cc = getNodeOrNull(cameraControllerPath.getPath());
        if (cc instanceof Node3D n) cameraControllerNode = n;
        else GD.printErr("[Vehicle] CameraController node missing at " + cameraControllerPath.getPath());

        Node bm = getNodeOrNull("BodyMesh");
        if (bm instanceof Node3D n) bodyMeshNode = n;
        else GD.printErr("[Vehicle] BodyMesh node missing — chassis won't pose!");

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }

        currentLatFactor = lateralForceFactor;

        // Low chassis friction: wheel grip comes from raycast suspension forces, not
        // from the body's PhysicsMaterial. Setting body friction low lets the chassis
        // slide over slope faces and ledge lips instead of catching on them.
        PhysicsMaterial mat = new PhysicsMaterial();
        mat.setFriction(0.1f);
        mat.setBounce(0.0f);
        setPhysicsMaterialOverride(mat);

        // Seed desiredForward and vehicleYaw from body facing so the camera
        // rig starts correctly aligned without a one-frame lerp artifact.
        Vector3 bFwd = getGlobalTransform().getBasis().getColumn(2).times(-1f);
        Vector3 flat = new Vector3(bFwd.getX(), 0f, bFwd.getZ());
        if ((float) flat.length() > 0.001f) desiredForward = flat.normalized();
        vehicleYaw = (float) Math.atan2(-desiredForward.getX(), -desiredForward.getZ());

        if (cameraControllerNode != null) {
            cameraControllerNode.setGlobalPosition(
                getGlobalPosition()
                    .plus(new Vector3(0f, CAM_HEIGHT, 0f))
                    .plus(desiredForward.times(-CAM_DISTANCE)));
            cameraControllerNode.setRotation(new Vector3(0f, vehicleYaw, 0f));
        }
    }

    // ── _integrateForces — suspension only ────────────────────────────────────

    @RegisterFunction
    @Override
    public void _integrateForces(PhysicsDirectBodyState3D state) {
        if (wheels == null) return;

        // Cap pitch/roll in-step (state.setAngularVelocity takes effect immediately,
        // unlike Node.setAngularVelocity which queues for the next step).
        // A wall collision can inject large X/Z angular velocity during this step;
        // capping it here ensures the suspension rays fire from a near-level body
        // rather than waiting one extra step for the _physicsProcess cap to kick in.
        // isOnGround here is the previous frame's value — the suspension loop below
        // will overwrite it. Using the previous-frame value is intentional: it mirrors
        // exactly what _physicsProcess sees and keeps both caps in sync.
        Vector3 av = state.getAngularVelocity();
        float avX = (float) Math.max(-MAX_TILT, Math.min(MAX_TILT, av.getX()));
        float avZ = (float) Math.max(-MAX_TILT, Math.min(MAX_TILT, av.getZ()));
        float avY = isOnGround ? vehicleYawRate : 0f;
        state.setAngularVelocity(new Vector3(avX, avY, avZ));

        float delta = (float) state.getStep();
        isOnGround = false;
        for (Node child : wheels.getChildren()) {
            if (child instanceof VehicleWheel w && w.applySuspension(delta, state)) {
                isOnGround = true;
            }
        }
    }

    // ── _physicsProcess — driving ─────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (controller == null || !controller.isAuthority()) return;
        // Consume the just-entered flag before reading any input so the same
        // isActionJustPressed("interact") that triggered tryEnter() this frame
        // cannot also trigger tryExit() in the same frame.
        boolean enteredThisFrame = justEntered;
        justEntered = false;
        UserCommand cmd = controller.gatherInput(delta);
        if (cmd.enterExit && occupant != null && !enteredThisFrame) { tryExit(); return; }
        if (cmd.resetVehicle)                                       { resetOrientation(); return; }
        applyDriving(cmd, (float) delta);
        updateWheelVisuals((float) delta, cmd.steering);
    }

    /** Overrideable so subclasses can cap throttle (e.g. GroundVehicle). */
    protected void applyDriving(UserCommand cmd, float delta) {
        final Vector3 worldUp = new Vector3(0f, 1f, 0f);
        float speed = (float) getLinearVelocity().length();

        // ── 1. Drift entry/exit ───────────────────────────────────────────
        // Track last non-zero steering so neutral-entry drift has a default direction.
        if (!isDrifting && Math.abs(cmd.steering) > 0.05f)
            driftDirection = Math.signum(cmd.steering);

        if (cmd.drift && !isDrifting) {
            isDrifting = true;
            driftBoosterTimer = 0f;
            // Lock direction from current steer; fall back to last non-zero (default right).
            if (Math.abs(cmd.steering) > 0.05f)
                driftDirection = Math.signum(cmd.steering);
            // Neutral entry: driftDirection keeps its last non-zero value (or 1 if never steered).
        } else if (!cmd.drift) {
            isDrifting = false;
        }

        // ── 2. Rotate the handle (CameraController = vehicleYaw) ─────────
        // Drift mode allows faster handle rotation so the car can swing wider.
        // Camera moves with the handle immediately — it IS the steering reference.
        // speedScale uses total speed so steering slows correctly at high speed
        // regardless of which world direction the vehicle is facing.
        float turnRateRad = (float) Math.toRadians(isDrifting ? driftTurnRateDegree : maxTurnAngleDegree);
        float speedScale  = Math.max(0.35f, 1f - speed / 60f);

        // Flip steer direction when reversing so steering feels natural in reverse gear,
        // matching normal vehicle behaviour (handle turns opposite direction to travel).
        float travelFwd = (float) getLinearVelocity().dot(desiredForward); // prev-frame forward
        float steerSign = travelFwd < -0.5f ? -1f : 1f;

        // Steering only accumulates on the ground. In air, steerSign depends on
        // the projection of velocity onto desiredForward; as vehicleYaw rotates that
        // projection flips sign, which inverts steerSign and oscillates vehicleYaw
        // at the camera rate — the "horizontal shatter" effect.
        float steerDelta = 0f;
        if (isOnGround && speed >= minSpeedForTurn) {
            steerDelta  = steerSign * cmd.steering * turnRateRad * speedScale;
            vehicleYaw += steerDelta * delta;
        }
        vehicleYawRate = steerDelta; // steering rate only — drift rate is added below

        // Normalize to [-π, π] to prevent float precision loss after many full rotations.
        while (vehicleYaw >  (float) Math.PI) vehicleYaw -= (float)(2.0 * Math.PI);
        while (vehicleYaw < -(float) Math.PI) vehicleYaw += (float)(2.0 * Math.PI);

        desiredForward = new Vector3(-(float) Math.sin(vehicleYaw), 0f, -(float) Math.cos(vehicleYaw));

        // CameraController follows vehicleYaw directly — camera IS the handle.
        if (cameraControllerNode != null) {
            Vector3 targetPos = getGlobalPosition()
                .plus(new Vector3(0f, CAM_HEIGHT, 0f))
                .plus(desiredForward.times(-CAM_DISTANCE));
            Vector3 smoothedPos = cameraControllerNode.getGlobalPosition()
                .lerp(targetPos, Math.min(1f, CAM_FOLLOW_SPEED * delta));
            cameraControllerNode.setGlobalPosition(smoothedPos);
            cameraControllerNode.setRotation(new Vector3(0f, vehicleYaw, 0f));
        }

        // ── 4. Chassis visual offset (computed before body yaw so the drift rate ──
        // is included in the body's Y angular velocity this same frame, keeping
        // wheel positions aligned with the visual chassis corners during drift).
        float prevDriftAngle = currentDriftAngle;
        float targetOffset;
        if (isDrifting) {
            float withDrift  = cmd.steering * driftDirection;   // +1 = same dir, -1 = counter
            float driftAngle = withDrift >= 0f
                ? maxDriftAngle
                : maxDriftAngle - maxDriftReduction * Math.min(1f, Math.abs(withDrift));
            targetOffset = driftDirection * driftAngle;
        } else {
            targetOffset = cmd.steering * normalBodyAngle;
        }
        currentDriftAngle += (targetOffset - currentDriftAngle) * Math.min(1f, driftAngleLerpSpeed * delta);
        float driftAngleRateRad = (float) Math.toRadians(currentDriftAngle - prevDriftAngle) / delta;

        // ── 3. Physics body: drive Y at total yaw rate (steering + drift); cap X/Z ──
        // Adding the drift-angle rate makes the body face moveFwd so wheel positions
        // (children of the body) align with the visual chassis including during drift.
        vehicleYawRate += driftAngleRateRad;
        Vector3 av  = getAngularVelocity();
        float   avX = (float) Math.max(-MAX_TILT, Math.min(MAX_TILT, av.getX()));
        float   avZ = (float) Math.max(-MAX_TILT, Math.min(MAX_TILT, av.getZ()));
        float   avY = isOnGround ? vehicleYawRate : 0f;
        setAngularVelocity(new Vector3(avX, avY, avZ));

        if (!isOnGround) return;

        // ── 5. Visual direction = desiredForward + chassis offset ─────────
        float   offsetRad = (float) Math.toRadians(currentDriftAngle);
        Vector3 moveFwd   = desiredForward.rotated(worldUp, offsetRad);

        // ── 5b. Slope-aware force directions ─────────────────────────────
        // The body's local +Y tilts with the terrain via suspension.
        // Projecting desiredForward / moveFwd onto this plane gives directions
        // that follow the slope surface — horizontal forces alone cannot climb.
        Vector3 vehicleUp = getGlobalTransform().getBasis().getColumn(1);
        if ((float) vehicleUp.length() < 0.001f) vehicleUp = new Vector3(0f, 1f, 0f);
        else vehicleUp = vehicleUp.normalized();
        Vector3 surfaceFwd     = projectOntoPlane(desiredForward, vehicleUp);
        Vector3 surfaceMoveFwd = projectOntoPlane(moveFwd,        vehicleUp);

        // ── 6. Pose BodyMesh ──────────────────────────────────────────────
        // Y = 0: the RigidBody3D tracks moveFwd directly (steering + drift rate),
        // so BodyMesh needs no additional yaw. Only X (nose-down pitch) and
        // Z (sideways roll) are applied for the cornering lean effect.
        // (Godot: negative X rotation = rotate +Y toward +Z = nose goes down.)
        {
            float targetRoll = vehicleYawRate * visualLeanFactor;
            float rollLerp   = Math.abs(targetRoll) >= Math.abs(currentRollVisual) ? 8f : 2f;
            currentRollVisual += (targetRoll - currentRollVisual) * Math.min(1f, rollLerp * delta);
        }

        if (bodyMeshNode != null) {
            bodyMeshNode.setRotation(new Vector3(
                -Math.abs(currentRollVisual) * 0.4f,
                0f,
                currentRollVisual));
        }

        // ── 7. Throttle and drag along surfaceFwd ────────────────────────
        // Forces follow the slope surface so the vehicle can climb.
        float throttle  = getThrottleInput(cmd.throttle);
        float desFwdSpd = (float) getLinearVelocity().dot(surfaceFwd);
        applyCentralForce(surfaceFwd.times(throttle * enginePower * 2f));
        applyCentralForce(surfaceFwd.times(-desFwdSpd * getMass() * dragForceFactor));

        // ── 8. Lateral correction ─────────────────────────────────────────
        // Non-drift: correct relative to moveFwd (the small lean angle) — gives
        //   grip that naturally accounts for the turn lean.
        // Drift: correct relative to surfaceFwd (camera direction) instead of the
        //   35°-offset surfaceMoveFwd. Using the offset during drift makes the
        //   correction force fight the throttle force, causing bumpiness. Using
        //   the camera direction gives clean perpendicular sliding.
        Vector3 moveRight = (isDrifting ? surfaceFwd : surfaceMoveFwd).cross(vehicleUp);
        float   latSpeed  = (float) getLinearVelocity().dot(moveRight);

        if (isDrifting) {
            currentLatFactor = driftLateralFactor;
        } else {
            // Reduce lateral grip proportionally to steer input so turning causes visible
            // sideslip. At full steer, grip drops to lateralForceFactor*(1-turnSlideReduction).
            // turnSlideReduction=0 = grippy always; 1.0 = fully slidey at max steer.
            float steerStrength = Math.abs(cmd.steering);
            float targetLat = lateralForceFactor * (1f - steerStrength * turnSlideReduction);
            currentLatFactor += (targetLat - currentLatFactor) * Math.min(1f, 8f * delta);
        }

        if (isDrifting && Math.abs(latSpeed) > maxDriftLateralSpeed) {
            float excess = Math.abs(latSpeed) - maxDriftLateralSpeed;
            applyCentralImpulse(moveRight.times(-(float) Math.copySign(excess, latSpeed) * getMass()));
            latSpeed = (float) Math.copySign(maxDriftLateralSpeed, latSpeed);
        }
        applyCentralImpulse(moveRight.times(-latSpeed * getMass() * currentLatFactor * delta));

        // ── 9. Braking ────────────────────────────────────────────────────
        if (cmd.handbrake && speed > 0.5f)
            applyCentralForce(getLinearVelocity().normalized().times(-brakePower * getMass()));

        // ── 10. Drift exit boost along surfaceFwd ─────────────────────────
        if (isDrifting) {
            driftBoosterTimer = Math.min(driftBoosterTimer + delta, 3f);
        } else if (driftBoosterTimer > 0f) {
            driftBoosterTimer -= delta;
            applyCentralForce(surfaceFwd.times(getMass() * 4f));
        }

    }

    /**
     * Flip the vehicle upright and lift it off the ground so the suspension
     * raycasts start from a clean airborne state on the next physics tick.
     *
     * Heading (vehicleYaw) is preserved so the vehicle faces the same direction.
     * All velocities are zeroed; drift and visual lean state are cleared.
     * Lifting by maxSpringLength * 2 + 1 m guarantees every wheel ray reports
     * "not colliding" next frame, which resets lastSpringLength to maxSpringLength
     * and prevents a carry-over damper spike when the vehicle lands.
     */
    private void resetOrientation() {
        setLinearVelocity(new Vector3(0f, 0f, 0f));
        setAngularVelocity(new Vector3(0f, 0f, 0f));
        vehicleYawRate    = 0f;
        isDrifting        = false;
        currentDriftAngle = 0f;
        driftBoosterTimer = 0f;
        currentRollVisual = 0f;
        currentLatFactor  = lateralForceFactor;

        setRotation(new Vector3(0f, vehicleYaw, 0f));
        Vector3 pos = getGlobalPosition();
        setGlobalPosition(new Vector3(pos.getX(), pos.getY() + maxSpringLength * 2f + 1.0f, pos.getZ()));
    }

    /**
     * Updates spin and steer rotation on every wheel each physics frame.
     * Called after applyDriving so desiredForward is already current.
     * forwardSpeed is signed: positive = forward, negative = reverse.
     */
    private void updateWheelVisuals(float delta, float steering) {
        if (wheels == null) return;
        float forwardSpeed = (float) getLinearVelocity().dot(desiredForward);
        for (Node child : wheels.getChildren()) {
            if (child instanceof VehicleWheel w)
                w.updateVisual(delta, forwardSpeed, steering);
        }
    }

    /** Subclass hook to cap raw throttle (e.g. GroundVehicle speed limit). */
    protected float getThrottleInput(float raw) { return raw; }

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
        // Resolve through ragdoll bones — body may be a PhysicalBone3D whose owner
        // is the Character, same pattern as Pickup.resolveCharacter().
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

    // ── Internal ─────────────────────────────────────────────────────────────

    /** Projects v onto the plane defined by normal, returns normalised result.
     *  Falls back to v unchanged when the projection is near-zero (e.g. v is
     *  parallel to normal, which can happen on a near-vertical wall). */
    private Vector3 projectOntoPlane(Vector3 v, Vector3 normal) {
        Vector3 projected = v.minus(normal.times((float) normal.dot(v)));
        float len = (float) projected.length();
        return len < 0.001f ? v : projected.times(1f / len);
    }

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }
}
