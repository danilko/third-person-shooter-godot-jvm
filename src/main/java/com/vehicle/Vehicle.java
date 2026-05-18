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

import java.util.ArrayList;

/**
 * Arcade-drift vehicle — hybrid steering + bounded-impulse grip.
 *
 * Two distinct control modes:
 *
 *   NORMAL:  direct vehicle steering, camera auto-follows vehicle heading.
 *            Lateral grip pulls velocity toward heading (bounded impulse, stable).
 *
 *   DRIFT:   camera auto-rotates at fixed rate in drift direction (same as original).
 *            Vehicle yaw-aligns to (camFwd + driftAngle offset).
 *            Left/right steering adjusts the drift arc angle [5°–45°].
 *            Low grip lets velocity diverge from heading — the gap IS the slide.
 *            The camera sweeping ahead while the car body lags behind creates the
 *            visible "car sideways" effect without any camera-velocity blend tricks.
 *
 * Lateral grip in both modes uses a BOUNDED IMPULSE:
 *   correction = clamp(-lateralSlip, -gripAccel×dt, +gripAccel×dt)
 *   applyImpulse(vehRight × correction × mass)
 * This is frame-rate independent and never produces the runaway 200 kN+ forces
 * from the old (-slip/dt)×mass×damp formula.
 */
@RegisterClass(className = "Vehicle")
public class Vehicle extends RigidBody3D implements Controllable {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;
    @RegisterProperty @Export public PackedScene    defaultWheelScene;

    @RegisterProperty @Export public float springStrength       = 15000f;
    /**
     * Hover spring damper (N·s/m). Critical damping ≈ 4243 for this vehicle mass/spring.
     * The old default (2000) was severely underdamped — the spring overshot on slope
     * transitions, briefly disconnecting wheels from ground and killing thrust.
     * 4500 = slight overdamping: smooth approach, no bounce, no slope speed drop.
     */
    @RegisterProperty @Export public float springDamping = 4500f;
    @RegisterProperty @Export public float wheelRadius           = 0.4f;
    /** Engine thrust (N). */
    @RegisterProperty @Export public float enginePower           = 24000f;

    /** Camera / steering rotation rate used for camera auto-rotation during drift (degrees/s). */
    @RegisterProperty @Export public float maxTurnAngleDegree    = 90f;

    /**
     * Fraction of steer rate lost at max speed (0 = constant, 0.5 = halved at top speed).
     * Only applies during normal (non-drift) direct steering.
     */
    @RegisterProperty @Export public float steerSpeedSensitivity = 0.5f;

    /** Angular velocity lerp blend toward target per frame (0–1). ~0.3 = smooth ramp. */
    @RegisterProperty @Export public float alignBlend            = 0.3f;

    /**
     * Max yaw tracking rate used for yaw-alignment during drift (degrees/s).
     * Vehicle rotates up to this rate to align with effectiveFwd.
     */
    @RegisterProperty @Export public float alignMaxDegPerSec     = 120f;

    @RegisterProperty @Export public float dragForceFactor       = 0.5f;
    @RegisterProperty @Export public float brakePower            = 12f;

    @RegisterProperty @Export public NodePath wheelsPath           = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath       = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath cameraControllerPath = new NodePath("../CameraController");
    @RegisterProperty @Export public NodePath vehicleCamPath       = new NodePath("../CameraController/SpringArm3D/Camera3D");

    // ── Grip ──────────────────────────────────────────────────────────────────

    /**
     * Max lateral deceleration at full grip (m/s²).
     * At 60 fps: 120 → up to 2 m/s lateral correction per frame.
     */
    @RegisterProperty @Export public float normalGripAccel  = 120f;

    /**
     * Max lateral deceleration while drifting (m/s²).
     * At 60 fps: 8 → 0.13 m/s correction per frame → 5 m/s slide lasts ~38 frames.
     */
    @RegisterProperty @Export public float driftGripAccel   = 8f;

    /** Seconds to restore full grip after drift release. */
    @RegisterProperty @Export public float driftExitDuration = 0.35f;

    // ── Drift ─────────────────────────────────────────────────────────────────

    /**
     * Initial thrust-angle offset from camFwd when drift starts (radians).
     * π/4 = 45°.  Steering adjusts this angle between 5° and 45° during drift.
     */
    @RegisterProperty @Export public float driftInitAngle  = (float)(Math.PI / 4f);

    /** Drag fraction during drift (lower = faster slide). */
    @RegisterProperty @Export public float driftDragScale  = 0.15f;

    /** Hard speed cap during drift = getMaxSpeed() × this. */
    @RegisterProperty @Export public float driftSpeedCapFactor = 1.1f;

    // ── Natural oversteer ─────────────────────────────────────────────────────

    /** Speed (m/s) above which full steering can trigger natural traction loss (~50 km/h). */
    @RegisterProperty @Export public float naturalDriftSpeed     = 14f;

    /** Steering magnitude [0–1] required for natural oversteer. */
    @RegisterProperty @Export public float naturalDriftThreshold = 0.75f;

    // ── Camera (normal mode) ──────────────────────────────────────────────────

    /**
     * Proportional-controller gain for camera following vehicle heading (normal mode).
     * Higher = snaps quickly; lower = cinematic lag.
     */
    @RegisterProperty @Export public float camFollowSpeed = 6f;

    // ── Roll ──────────────────────────────────────────────────────────────────

    @RegisterProperty @Export public float rollAngleDeg = 10f;
    @RegisterProperty @Export public float rollSpring   = 10000f;
    @RegisterProperty @Export public float rollDamp     = 3000f;


    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller controller;
    protected Health     healthNode;
    protected Character  occupant;

    private Node3D   driverSeatNode;
    private Camera3D vehicleCamera;
    private ArrayList<VehicleWheel> wheels = new ArrayList<>();
    protected Node3D cameraControllerNode = null;


    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        if (characterInfo == null) characterInfo = new CharacterInfo();
        addToGroup(new StringName("characters"), false);

        Node h = getNodeOrNull("Health");
        if (h instanceof Health hn) healthNode = hn;

        Node wheelsNode = getNodeOrNull("Wheels");
        if (wheelsNode != null) {
            for (Node child : wheelsNode.getChildren()) {
                if (child instanceof VehicleWheel w) {
                    w.springStrength = springStrength;
                    w.springDamping = springDamping;
                    w.wheelRadius = wheelRadius;

                    wheels.add(w);
                }
            }
            GD.print("[Vehicle] _ready: " + wheels.size() + " wheel(s) initialised");
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
            for(VehicleWheel w : wheels) {
                w.applyWheelSuspension((float) delta);
            }

            if(controller == null || controller.isAuthority()) return;

        UserCommand cmd = controller.gatherInput(delta);


    }


    // ── Utilities ─────────────────────────────────────────────────────────────

    private void resetOrientation() {
        setLinearVelocity(new Vector3(0f, 0f, 0f));
        setAngularVelocity(new Vector3(0f, 0f, 0f));
        setRotation(new Vector3(0f, 0f, 0f));
        Vector3 p = getGlobalPosition();
        setGlobalPosition(new Vector3((float)p.getX(), (float)p.getY() + 6f + 1f, (float)p.getZ()));
    }


    // ── Controllable ──────────────────────────────────────────────────────────

    @Override public void applyCommand(UserCommand cmd, double delta) { }
    @Override public CharacterInfo getCharacterInfo()                 { return characterInfo; }

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
        if (c instanceof Player p) { p.nearbyVehicle = this; emitEnterPrompt(true); }
    }

    @RegisterFunction
    public void onEntranceBodyExited(Node3D body) {
        Character c = resolveCharacter(body);
        if (c == null) return;
        if (c instanceof Player p) { p.nearbyVehicle = null; emitEnterPrompt(false); }
    }

    private Character resolveCharacter(Node3D body) {
        if (body instanceof Character c) return c;
        Node owner = body.getOwner();
        return owner instanceof Character c ? c : null;
    }

    private void emitEnterPrompt(boolean inRange) {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus)
            bus.pickupInteractChanged.emit(inRange, inRange ? "Enter vehicle" : "");
    }

    // ── Controller hot-swap ───────────────────────────────────────────────────

    public Controller detachController() {
        if (controller == null) return null;
        Controller c = controller;
        removeChild(c);
        controller = null;
        return c;
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
