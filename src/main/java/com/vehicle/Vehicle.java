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
 *
 * Weapon modes (set weaponModeIndex in the inspector):
 *   0 = NONE            — no shooting while occupied
 *   1 = PASSENGER_WEAPON — occupant fires their own weapon via vehicle camera aim
 *   2 = VEHICLE_WEAPON  — vehicle's own FirearmItem fires; occupant weapon disabled
 */
@RegisterClass(className = "Vehicle")
public class Vehicle extends RigidBody3D implements Controllable {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;

    @RegisterProperty @Export public float springStrength       = 10000f;
    @RegisterProperty @Export public float springDamping        = 4500f;
    @RegisterProperty @Export public float wheelRadius          = 0.4f;
    @RegisterProperty @Export public float restDistance         = 0.5f;
    @RegisterProperty @Export public float overExtend           = 0.3f;

    @RegisterProperty @Export public float zTraction            = 0.05f;
    @RegisterProperty @Export public float zBrakeTraction       = 0.25f;

    @RegisterProperty @Export public float maxSpeed             = 20.0f;
    @RegisterProperty @Export public float acceleration         = 9000.0f;
    @RegisterProperty @Export public Curve accelerationCurve;
    @RegisterProperty @Export public float tireMaxTurnSpeed     = 2.0f;
    @RegisterProperty @Export public float tireMaxTurnDegrees   = 25.0f;

    @RegisterProperty @Export public NodePath wheelsPath        = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath    = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath vehicleCamPath    = new NodePath("ActiveCamera");

    /**
     * Weapon mode: 0 = NONE, 1 = PASSENGER_WEAPON, 2 = VEHICLE_WEAPON.
     * Set in the inspector for each vehicle type.  Default is PASSENGER_WEAPON (1)
     * so a car/boat works immediately without inspector changes.
     */
    @RegisterProperty @Export public int weaponModeIndex = 1;

    /** Path to the RayCast3D under the vehicle camera used for passenger aiming. */
    @RegisterProperty @Export public NodePath vehicleAimRayPath =
            new NodePath("ActiveCamera/AimRay");

    /** Path to the vehicle-owned weapon node (for VEHICLE_WEAPON mode). */
    @RegisterProperty @Export public NodePath vehicleWeaponPath =
            new NodePath("VehicleWeaponMount/WeaponItem");

    /** Minimum vehicle speed (m/s) needed to deal collision damage to characters. 0 disables it. */
    @RegisterProperty @Export public float vehicleCollisionMinSpeed = 5.0f;

    /** Damage per m/s above vehicleCollisionMinSpeed on collision. */
    @RegisterProperty @Export public float vehicleCollisionDamageScale = 100.0f;

    /** Damage dealt to the occupant when the vehicle is destroyed. */
    @RegisterProperty @Export public float vehicleExplosionOccupantDamage = 50.0f;

    /** Optional icon shown in the kill feed when this vehicle deals collision damage. */
    @RegisterProperty @Export public Texture2D vehicleIcon;

    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller             controller;
    protected Health                 healthNode;
    protected Character              occupant;

    private Node3D                   driverSeatNode;
    private Camera3D                 vehicleCamera;
    private VehicleCameraController  camController;
    private WeaponItem               vehicleWeaponItem;
    private final ArrayList<VehicleWheel> wheels = new ArrayList<>();

    private boolean slipping    = false;
    private boolean braking     = false;
    private boolean handBraking = false;
    private boolean justEntered = false;
    private UserCommand cmd = new UserCommand();

    // Characters currently touching the vehicle body — used to detect new contacts each frame.
    private final java.util.HashSet<Character> activeCollisions = new java.util.HashSet<>();

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        if (characterInfo == null) characterInfo = new CharacterInfo();
        addToGroup(new StringName("characters"), false);
        setContactMonitor(true);
        setMaxContactsReported(8);

        Node h = getNodeOrNull("Health");
        if (h instanceof Health hn) {
            healthNode = hn;
            healthNode.died.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onVehicleDestruction")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        Node wheelsNode = getNodeOrNull("Wheels");
        if (wheelsNode != null) {
            for (Node child : wheelsNode.getChildren()) {
                if (child instanceof VehicleWheel w) {
                    w.springStrength = springStrength;
                    w.springDamping  = springDamping;
                    w.wheelRadius    = wheelRadius;
                    w.restDistance   = restDistance;
                    w.overExtend     = overExtend;
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

        // "CameraController" is the VehicleCameraController node.
        // "ActiveCamera" is a sibling Camera3D — these look up DIFFERENT nodes.
        Node camCtrl = getNodeOrNull("CameraController");
        if (camCtrl instanceof VehicleCameraController vcc) camController = vcc;

        // Cache vehicle weapon for VEHICLE_WEAPON mode and inject the vehicle AimRay.
        Node vw = getNodeOrNull(vehicleWeaponPath.getPath());
        if (vw instanceof WeaponItem wi) {
            vehicleWeaponItem = wi;
            if (wi instanceof FirearmItem fi && getWeaponMode() == VehicleWeaponMode.VEHICLE_WEAPON) {
                Node aimRayNode = getNodeOrNull(vehicleAimRayPath.getPath());
                RayCast3D vRay = aimRayNode instanceof RayCast3D r ? r : null;
                fi.setup(null, vRay, null, null);
            }
        }

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }
    }

    // ── Physics ───────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        boolean isGrounded = false;

        cmd.motor     = 0;
        cmd.steering  = 0;
        cmd.handbrake = false;
        cmd.brake     = false;
        cmd.fire      = false;
        cmd.reload    = false;

        if (controller != null && controller.isAuthority()) {
            UserCommand currentCmd = controller.gatherInput(delta);

            // R key: flip-right reset only when the occupant is NOT using it to reload.
            if (currentCmd.resetVehicle && getWeaponMode() != VehicleWeaponMode.PASSENGER_WEAPON) {
                resetOrientation();
            }
            // Guard: skip exit on the same frame tryEnter ran. isActionJustPressed
            // stays true for the whole physics frame, so if Vehicle._physicsProcess
            // runs after Player._physicsProcess in the same frame (possible with
            // multiple characters in the scene), the interact press that triggered
            // entry would immediately call tryExit without this flag.
            if (currentCmd.enterExit && !justEntered) {
                tryExit();
            }
            justEntered = false;

            cmd.motor     = currentCmd.motor;
            cmd.steering  = currentCmd.steering;
            cmd.handbrake = currentCmd.handbrake;
            cmd.brake     = currentCmd.brake;
            cmd.fire      = currentCmd.fire;
            cmd.reload    = currentCmd.reload;
        }

        if (cmd.handbrake) {
            slipping    = true;
            handBraking = true;
        } else {
            handBraking = false;
        }
        braking = cmd.brake;

        for (VehicleWheel w : wheels) {
            w.applyWheelPhysics((float) delta, (float) getPhysicsProcessDeltaTime(), cmd);
            w.applyWheelSteering((float) delta, cmd.steering);
            w.applySkidMark();
            if (w.isColliding()) isGrounded = true;
        }

        setCenterOfMassMode(CenterOfMassMode.CUSTOM);
        if (isGrounded) {
            setCenterOfMass(new Vector3(0f, -0.3f, 0f));
        } else {
            setCenterOfMass(Vector3.Companion.getDOWN().times(0.5f));
        }

        // Keep occupant hitbox pinned to the driver seat each frame (position only).
        // Rotation was aligned once in tryEnter; exitDriveState restores pre-entry rotation.
        if (occupant != null && driverSeatNode != null) {
            occupant.setGlobalPosition(driverSeatNode.getGlobalPosition());
        }

        // Relay weapon commands to occupant based on weapon mode.
        if (occupant != null) {
            VehicleWeaponMode mode = getWeaponMode();
            if (mode == VehicleWeaponMode.PASSENGER_WEAPON) {
                Vector3 aimTarget = camController != null
                        ? camController.getAimTarget()
                        : occupant.getGlobalPosition().plus(new Vector3(0f, 0f, -20f));
                occupant.applyPassengerWeaponInput(cmd.fire, cmd.reload, aimTarget);
            } else if (mode == VehicleWeaponMode.VEHICLE_WEAPON && vehicleWeaponItem != null) {
                if (cmd.fire) vehicleWeaponItem.useWeapon();
                else          vehicleWeaponItem.stopUseWeapon();
            }
        }

    }

    // ── Utilities ─────────────────────────────────────────────────────────────

    /**
     * Detects new character contacts and applies one-time speed-proportional damage.
     * PhysicsDirectBodyState3D.getContactColliderObject is the correct API for iterating
     * contacts on a RigidBody3D — the equivalent getter does not exist on the body itself.
     * Requires contact_monitor=true and max_contacts_reported>0 (set in _ready).
     */
    @RegisterFunction
    @Override
    public void _integrateForces(PhysicsDirectBodyState3D state) {
        if (vehicleCollisionMinSpeed <= 0) return;

        int count = state.getContactCount();
        java.util.HashSet<Character> currentContacts = new java.util.HashSet<>();

        for (int i = 0; i < count; i++) {
            // getContactColliderObject returns godot.api.Object; widened to java.lang.Object here.
            Object obj = state.getContactColliderObject(i);
            Character character = null;
            if (obj instanceof Character c) {
                character = c;
            } else if (obj instanceof Node3D n3d) {
                Node owner = n3d.getOwner();
                if (owner instanceof Character c) character = c;
            }
            if (character == null || character == occupant || !character.isAlive()) continue;
            currentContacts.add(character);
        }

        float speed = (float) GD.abs(getGlobalBasis().getZ().dot(getLinearVelocity()));
        if (speed >= vehicleCollisionMinSpeed) {
            for (Character character : currentContacts) {
                if (!activeCollisions.contains(character)) {
                    applyVehicleCollisionDamage(character, speed);
                }
            }
        }

        activeCollisions.clear();
        activeCollisions.addAll(currentContacts);
    }

    private void applyVehicleCollisionDamage(Character character, float speed) {
        float damage = (speed - vehicleCollisionMinSpeed) * vehicleCollisionDamageScale;
        Node healthNode = character.getNodeOrNull("Health");
        if (!(healthNode instanceof Health health)) return;

        String attackerName    = (occupant != null) ? occupant.getCharacterInfo().displayName: "";
        String attackerFaction = (characterInfo != null) ? characterInfo.faction     : "";
        health.takeDamage(null, damage, "Vehicle", vehicleIcon, attackerName, attackerFaction);

        // Knockback in the direction the vehicle is travelling.
        Vector3 knockbackDir = getLinearVelocity().normalized();
        character.applyHitImpulse(null, knockbackDir, damage);
    }

    /** Returns the typed weapon mode from the inspector int. */
    public VehicleWeaponMode getWeaponMode() {
        VehicleWeaponMode[] values = VehicleWeaponMode.values();
        int idx = Math.max(0, Math.min(weaponModeIndex, values.length - 1));
        return values[idx];
    }

    private void resetOrientation() {
        setLinearVelocity(new Vector3(0f, 0f, 0f));
        setAngularVelocity(new Vector3(0f, 0f, 0f));
        setRotation(new Vector3(0f, 0f, 0f));
        Vector3 p = getGlobalPosition();
        setGlobalPosition(new Vector3((float) p.getX(), (float) p.getY() + 7f, (float) p.getZ()));
    }

    // ── Controllable ──────────────────────────────────────────────────────────

    @Override public void applyCommand(UserCommand cmd, double delta) { }
    @Override public CharacterInfo getCharacterInfo()                 { return characterInfo; }

    // ── Enter / Exit ──────────────────────────────────────────────────────────

    public void tryEnter(Character c) {
        if (occupant != null) return;
        occupant    = c;
        justEntered = true;

        VehicleWeaponMode mode = getWeaponMode();

        // Character handles collision, stance, combat state, and physics disabling.
        c.enterDriveState(mode);
        // Align character body to vehicle heading once — exitDriveState restores the pre-entry rotation.
        c.setGlobalRotation(new Vector3(0f, (float) getGlobalRotation().getY(), 0f));

        Controller ctrl = c.detachController();
        if (ctrl != null) attachController(ctrl);

        // For PASSENGER_WEAPON: swap the character's AimRay to the vehicle camera ray.
        if (mode == VehicleWeaponMode.PASSENGER_WEAPON) {
            Node aimRayNode = getNodeOrNull(vehicleAimRayPath.getPath());
            if (aimRayNode instanceof RayCast3D vRay) {
                Node wc = c.getNodeOrNull("WeaponController");
                if (wc instanceof WeaponController wcn) wcn.overrideAimRay(vRay);
            }
        }

        if (camController != null) camController.setPassengerAimMode(mode == VehicleWeaponMode.PASSENGER_WEAPON);
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

        // Restore AimRay before re-enabling character physics.
        if (getWeaponMode() == VehicleWeaponMode.PASSENGER_WEAPON) {
            Node wc = c.getNodeOrNull("WeaponController");
            if (wc instanceof WeaponController wcn) wcn.restoreAimRay();
        }

        Vector3 right   = getGlobalTransform().getBasis().getColumn(0);
        Vector3 exitPos = getGlobalPosition()
                .minus(right.times(1.5f)).plus(new Vector3(0f, 0.8f, 0f));
        c.setGlobalPosition(exitPos);

        // exitDriveState restores the character body rotation saved on entry.
        c.exitDriveState();

        Controller ctrl = detachController();
        if (ctrl != null) c.attachController(ctrl);

        if (camController != null) camController.setPassengerAimMode(false);
        c.makeCameraActive();
        // Mark the exiting character as already-known so the next _integrateForces call does
        // not treat them as a new contact and apply spurious collision damage on exit.
        activeCollisions.add(c);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.vehicleExited.emit(c.characterInfo);
    }

    /**
     * Called when the vehicle's Health node reaches zero.
     *
     * Ejects the occupant first (restoring their physics and stance) so that the
     * exitDriveState / makeCameraActive chain runs on a live vehicle scene, then
     * applies explosion damage to the ejected character, and finally removes the
     * vehicle from the scene tree.
     *
     * Ordering matters: tryExit() must come before queueFree() so that reparenting
     * the controller and querying global transforms still work on the intact vehicle.
     * Damage is applied after ejection so that if the blast kills the character,
     * enableRagdoll() fires on a fully-restored CharacterBody3D (not mid-drive-state).
     */
    @RegisterFunction
    public void onVehicleDestruction() {
        if (occupant != null) {
            Character ejected = occupant;
            tryExit();
            if (ejected.isAlive()) {
                Node occHealth = ejected.getNodeOrNull("Health");
                if (occHealth instanceof Health health) {
                    String attackerName    = (characterInfo != null) ? characterInfo.displayName : getName().toString();
                    String attackerFaction = (characterInfo != null) ? characterInfo.faction     : "";
                    health.takeDamage(null, vehicleExplosionOccupantDamage, "Vehicle Explosion",
                            null, attackerName, attackerFaction);
                }
            }
        }
        queueFree();
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

    public boolean isSlipping()     { return slipping; }
    public void setSlipping(boolean slipping) { this.slipping = slipping; }
    public ArrayList<VehicleWheel> getWheels() { return wheels; }
    public boolean isBraking()      { return braking; }
    public boolean isHandbraking()  { return handBraking; }
}
