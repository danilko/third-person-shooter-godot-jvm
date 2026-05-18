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

import java.lang.Object;
import java.util.ArrayList;
import java.util.Collection;

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

    @RegisterProperty @Export public float springStrength       = 10000f;
    @RegisterProperty @Export public float springDamping = 4500f;
    @RegisterProperty @Export public float wheelRadius           = 0.4f;
    @RegisterProperty @Export public float restDistance          = 0.5f;
    @RegisterProperty @Export public float overExtend            = 0.3f;

    @RegisterProperty @Export public float zTraction = 0.05f;
    @RegisterProperty @Export public float zBrakeTraction = 0.25f;

    @RegisterProperty @Export public float maxSpeed           = 20.0f;
    @RegisterProperty @Export public float acceleration = 9000.0f;
    @RegisterProperty @Export public Curve accelerationCurve;
    @RegisterProperty @Export public float tireMaxTurnSpeed = 2.0f;
    @RegisterProperty @Export public float tireMaxTurnDegrees = 25.0f;

    @RegisterProperty @Export public NodePath wheelsPath           = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath       = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath cameraControllerPath = new NodePath("../CameraController");
    @RegisterProperty @Export public NodePath vehicleCamPath       = new NodePath("../CameraController/SpringArm3D/Camera3D");

    /** How quickly the camera yaw catches up to the vehicle heading (rad/s blend factor). */
    @RegisterProperty @Export public float cameraYawLagSpeed = 3.0f;


    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller controller;
    protected Health     healthNode;
    protected Character  occupant;

    private Node3D   driverSeatNode;
    private Camera3D vehicleCamera;
    private final ArrayList<VehicleWheel> wheels = new ArrayList<>();
    protected Node3D cameraControllerNode = null;


    private boolean slipping = false;
    private boolean braking = false;
    private boolean handBraking = false;
    private UserCommand cmd = new UserCommand();
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
                    w.restDistance = restDistance;
                    w.overExtend = overExtend;

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
            boolean isGrounded = false;

            // set default in case controller is null
        cmd.motor = 0;
        cmd.steering = 0;
        cmd.handbrake = false;
        cmd.brake = false;

        if(controller != null && controller.isAuthority()) {
            UserCommand currentCmd = controller.gatherInput(delta);

            if(currentCmd.reload) {
                resetOrientation();
            }
            if(currentCmd.enterExit) {
                tryExit();
            }

            cmd.motor = currentCmd.motor;
            cmd.steering = currentCmd.steering;
            cmd.handbrake = currentCmd.handbrake;
            cmd.brake = currentCmd.brake;
        }

        if(cmd.handbrake) {
            slipping = true;
            handBraking = true;
        }
        else {
            handBraking = false;
        }
        braking = cmd.brake;

        for(VehicleWheel w : wheels) {
            w.applyWheelPhysics((float) delta, (float) getPhysicsProcessDeltaTime(), cmd);
            w.applyWheelSteering((float) delta, cmd.steering);
            w.applySkidMark();

            if (w.isColliding()) {
                isGrounded = true;
            }
        }


        setCenterOfMassMode(CenterOfMassMode.CUSTOM);
        if(isGrounded) {
            setCenterOfMass(new Vector3(0f, -0.3f, 0f));
        }
        else {
            setCenterOfMass(Vector3.Companion.getDOWN().times(0.5f));
        }

        cameraControllerNode.setGlobalPosition(getGlobalPosition());

        // Lazy yaw follow — lerp camera heading toward vehicle heading so sharp
        // turns let the player see the side of the car before the camera catches up.
        float vehicleYaw = (float) getGlobalRotation().getY();
        float camYaw     = (float) cameraControllerNode.getGlobalRotation().getY();
        float laggedYaw  = (float) GD.lerpAngle(camYaw, vehicleYaw, cameraYawLagSpeed * (float) delta);
        Vector3 camRot   = cameraControllerNode.getGlobalRotation();
        camRot.setY(laggedYaw);
        cameraControllerNode.setGlobalRotation(camRot);

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
        c.setProcess(false);
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
        c.setProcess(true);
        c.setPhysicsProcess(true);
        c.setVisible(true);
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


    public boolean isSlipping() {
        return slipping;
    }

    public void setSlipping(boolean slipping) {
        this.slipping = slipping;
    }

    public ArrayList<VehicleWheel> getWheels() {
        return wheels;
    }

    public boolean isBraking() {
        return braking;
    }

    public boolean isHandbraking() {
        return handBraking;
    }
}
