package com.openworld.carrier.vehicle;

import com.openworld.character.*;
import com.openworld.character.Character;
import com.openworld.world.SpatialEntityGrid;
import com.openworld.world.StimulusManager;
import com.openworld.world.manager.ExplosionManager;
import com.openworld.game.EventBus;
import com.openworld.net.NetworkManager;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.annotation.RegisterSignal;
import godot.api.*;
import godot.core.*;
import godot.global.GD;

import java.lang.Object;
import java.util.ArrayList;
import java.util.Collection;
import com.openworld.camera.VehicleCameraController;
import com.openworld.control.Controllable;
import com.openworld.control.Controller;
import com.openworld.control.PlayerController;
import com.openworld.control.UserCommand;
import com.openworld.game.GameManager;
import com.openworld.item.Pickup;
import com.openworld.net.NetworkController;
import com.openworld.net.RigidSnapshotInterpolator;
import com.openworld.net.VehicleNetworkController;
import com.openworld.net.VehicleSeatPolicy;
import com.openworld.weapon.IconRegistry;
import com.openworld.weapon.WeaponController;

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
 * All physics constants and combat/damage/wreck config live in VehicleConfig.
 * Assign a .tres preset in the inspector; leave null to use built-in DEFAULTS.
 */
@RegisterClass(className = "Vehicle")
public class Vehicle extends RigidBody3D implements Controllable, NameplateTarget {

    // ── Inspector exports ─────────────────────────────────────────────────────

    @RegisterProperty @Export public CharacterInfo characterInfo;

    /**
     * Per-vehicle-type config (suspension, power, damage, wreck, etc.).
     * Null = shared DEFAULTS singleton with the original hard-coded values.
     * Swap a different .tres preset to change vehicle archetype with zero code changes.
     */
    @RegisterProperty @Export public VehicleConfig vehicleConfig;

    // Scene-structure paths — node positions are scene-specific, not config.
    @RegisterProperty @Export public NodePath wheelsPath     = new NodePath("Wheels");
    @RegisterProperty @Export public NodePath driverSeatPath = new NodePath("DriverSeat");
    @RegisterProperty @Export public NodePath vehicleCamPath = new NodePath("ActiveCamera");

    // Damage-source names stamped onto elimination events; also the IconRegistry keys
    // each peer registers the vehicle icon under so a vehicle kill resolves its icon
    // on remote peers (kept as shared constants so the damage site and registration
    // can never drift apart).
    public static final String DAMAGE_SOURCE_COLLISION = "Vehicle";
    public static final String DAMAGE_SOURCE_EXPLOSION = "Vehicle Explosion";

    // ── Shared DEFAULTS (one instance, never mutated) ─────────────────────────
    private static final VehicleConfig DEFAULTS = new VehicleConfig();

    /** Returns the active config, falling back to DEFAULTS when none is assigned. */
    public VehicleConfig getConfig() {
        return vehicleConfig != null ? vehicleConfig : DEFAULTS;
    }

    // ── Runtime state ─────────────────────────────────────────────────────────

    protected Controller             controller;
    protected Health                 healthNode;
    protected Character              occupant;

    private Node3D                   driverSeatNode;
    private Camera3D                 vehicleCamera;
    private VehicleCameraController  camController;
    private WeaponController         vehicleWeaponController;
    private final ArrayList<VehicleWheel> wheels = new ArrayList<>();

    private boolean slipping    = false;
    private boolean braking     = false;
    private boolean handBraking = false;
    private boolean justEntered = false;
    private UserCommand cmd = new UserCommand();

    private final java.util.HashSet<Character> activeCollisions = new java.util.HashSet<>();
    /** Counts down between VEHICLE_CRASH stimulus posts so a sustained scrape alerts AI at most ~1×/s (E2). */
    private double crashStimulusCooldown = 0.0;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        if (characterInfo == null) characterInfo = new CharacterInfo();
        // Scene-path-derived id (the Pickup.pickupId pattern): peer-identical for
        // scene-placed vehicles, so every peer resolves the same vehicle without any
        // spawn replication. Runtime-spawned vehicles must have a host-stamped UUID
        // set BEFORE addChild. Round 11 N3 — this is what makes ownership migration,
        // snapshots, and damage requests resolvable for vehicles at all.
        if (characterInfo.characterId == null || characterInfo.characterId.isEmpty()) {
            characterInfo.characterId = getPath().getPath();
            if (characterInfo.characterId.length() > 64) {
                GD.printErr("[Vehicle] characterId '" + characterInfo.characterId
                        + "' exceeds the 64-char wire cap — this vehicle cannot replicate");
            }
        }
        addToGroup(new StringName("characters"), false);
        // Register in the spatial grid so AI target discovery finds vehicle occupants in O(k)
        // (PLAN.md Part D / D1). Stagger the first re-bucket like Character does.
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.register(this, getGlobalPosition());
        gridUpdateTimer = GD.randfRange(0f, (float) GRID_UPDATE_INTERVAL);
        setContactMonitor(true);
        setMaxContactsReported(8);

        Node h = getNodeOrNull("Health");
        if (h instanceof Health hn) {
            healthNode = hn;
            healthNode.died.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onVehicleDestruction")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        VehicleConfig cfg = getConfig();
        // Register the vehicle's kill-feed icon under the same damage-source keys it
        // stamps onto eliminations, so a vehicle kill resolves its icon on every peer
        // (the registry is local-only; textures never cross the wire — see IconRegistry).
        if (cfg.vehicleIcon != null) {
            com.openworld.weapon.IconRegistry.register(DAMAGE_SOURCE_COLLISION, cfg.vehicleIcon);
            com.openworld.weapon.IconRegistry.register(DAMAGE_SOURCE_EXPLOSION, cfg.vehicleIcon);
        }
        Node wheelsNode = getNodeOrNull("Wheels");
        if (wheelsNode != null) {
            for (Node child : wheelsNode.getChildren()) {
                if (child instanceof VehicleWheel w) {
                    w.setup(cfg);
                    wheels.add(w);
                }
            }
        } else {
            GD.printErr("[Vehicle] Wheels node missing — hover disabled!");
        }

        Node seat = getNodeOrNull(driverSeatPath.getPath());
        if (seat instanceof Node3D n) driverSeatNode = n;

        Node cam = getNodeOrNull(vehicleCamPath.getPath());
        if (cam instanceof Camera3D c) vehicleCamera = c;

        Node camCtrl = getNodeOrNull("CameraController");
        if (camCtrl instanceof VehicleCameraController vcc) camController = vcc;

        Node wc = getNodeOrNull("WeaponController");
        if (wc instanceof WeaponController vwc) vehicleWeaponController = vwc;

        for (Node child : getChildren()) {
            if (child instanceof Controller c) { controller = c; break; }
        }
    }

    // ── Replication authority (Round 11 N3) ───────────────────────────────────

    /** True when this peer simulates the vehicle's physics — single-player, or this peer owns its locomotion. */
    public boolean isLocallySimulated() {
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) return true;
        return net.isAuthorityFor(characterInfo);
    }

    /**
     * Reconciles this vehicle's controller + physics mode with its current locomotion
     * authority. Idempotent — called from occupancy application on every authority flip
     * (driver enter/exit) and lazily by NetworkManager on the first received vehicle
     * snapshot (covers scene-placed vehicles on a client, which have no join hook).
     *
     * Puppet (another peer simulates): attach a {@link VehicleNetworkController} and freeze
     * the RigidBody so local physics never fights the interpolator's kinematic placement.
     * Simulated: drop the puppet controller — seeding the live body's velocities from its
     * last sample so a handed-back vehicle coasts instead of stopping dead — and unfreeze.
     */
    public void applyAuthorityState() {
        if (isLocallySimulated()) {
            if (controller instanceof VehicleNetworkController vnc) {
                com.openworld.net.RigidSnapshotInterpolator.Sample last = vnc.latestSample();
                if (last != null) {
                    setLinearVelocity(new Vector3((float) last.linearVelocity().x(),
                            (float) last.linearVelocity().y(), (float) last.linearVelocity().z()));
                    setAngularVelocity(new Vector3((float) last.angularVelocity().x(),
                            (float) last.angularVelocity().y(), (float) last.angularVelocity().z()));
                }
                detachController();
                vnc.queueFree();
            }
            // Kotlin/JVM binding gotcha: Godot 4's `freeze` property is setFreezeEnabled.
            setFreezeEnabled(false);
        } else {
            if (controller == null) {
                attachController(new VehicleNetworkController());
            } else if (!(controller instanceof VehicleNetworkController)) {
                // A live controller on a body we don't own means an occupancy/ownership
                // mis-order — freeze anyway (replication wins) and leave evidence.
                GD.printErr("[Vehicle] " + characterInfo.characterId
                        + " lost authority while holding a live controller — freezing under it");
            }
            setFreezeEnabled(true);
        }
    }

    // ── Physics ───────────────────────────────────────────────────────────────

    // ── Spatial grid bookkeeping (PLAN.md Part D / D1) ───────────────────────
    private static final double GRID_UPDATE_INTERVAL = 0.25;
    private double gridUpdateTimer = 0.0;

    /** Throttled spatial-grid re-bucket — mirrors {@code Character.updateSpatialCell}. */
    private void updateSpatialCell(double delta) {
        gridUpdateTimer -= delta;
        if (gridUpdateTimer > 0.0) return;
        gridUpdateTimer = GRID_UPDATE_INTERVAL;
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.move(this, getGlobalPosition());
    }

    /** Drop out of the spatial grid when the vehicle leaves the tree (destroyed/despawned). */
    @RegisterFunction
    @Override
    public void _exitTree() {
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.unregister(this);
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        updateSpatialCell(delta);
        boolean isGrounded = false;

        cmd.motor     = 0;
        cmd.steering  = 0;
        cmd.handbrake = false;
        cmd.brake     = false;
        cmd.fire      = false;
        cmd.reload    = false;

        if (controller != null && controller.isAuthority()) {
            UserCommand currentCmd = controller.gatherInput(delta);

            if (currentCmd.resetVehicle && getWeaponMode() != VehicleWeaponMode.PASSENGER_WEAPON) {
                resetOrientation();
            }
            if (currentCmd.enterExit && !justEntered) {
                requestExit();
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

        // Wheel forces + center-of-mass tuning only run on the simulating peer (N3):
        // puppets are frozen and placed kinematically by VehicleNetworkController, which
        // also drives their wheel visuals from the replicated steering/speed.
        if (isLocallySimulated()) {
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
        }

        if (occupant != null && driverSeatNode != null) {
            occupant.setGlobalPosition(driverSeatNode.getGlobalPosition());
            Vector3 occRot = occupant.getGlobalRotation();
            occRot.setY((float) getGlobalRotation().getY());
            occupant.setGlobalRotation(occRot);
        }

        // Weapon routing is authority-only (N3): on a puppet, the occupant's fire cues and
        // aim arrive via its own character snapshot stream — pushing the stale local vehicle
        // camera's aim target here would overwrite the replicated aim every physics tick.
        if (occupant != null && isLocallySimulated()) {
            VehicleWeaponMode mode = getWeaponMode();
            if (mode == VehicleWeaponMode.PASSENGER_WEAPON) {
                Vector3 aimTarget = camController != null
                        ? camController.getAimTarget()
                        : occupant.getGlobalPosition().plus(new Vector3(0f, 0f, -20f));
                occupant.applyPassengerWeaponInput(cmd.fire, cmd.reload, cmd.desiredWeapon, aimTarget);
            } else if (mode == VehicleWeaponMode.VEHICLE_WEAPON && vehicleWeaponController != null) {
                if (cmd.fire) vehicleWeaponController.onWeaponFire();
                else          vehicleWeaponController.onWeaponNotFire();
            }
        }
    }

    // ── Utilities ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _integrateForces(PhysicsDirectBodyState3D state) {
        // Run-over damage is resolved only where the vehicle is simulated (N3): on puppets
        // the body is frozen (no contacts to report) and damage must stay single-sourced —
        // a client-side hit relays via Health.takeDamage from the simulating peer instead.
        if (!isLocallySimulated()) return;
        VehicleConfig cfg = getConfig();
        if (cfg.vehicleCollisionMinSpeed <= 0) return;

        int count = state.getContactCount();
        java.util.HashSet<Character> currentContacts = new java.util.HashSet<>();

        for (int i = 0; i < count; i++) {
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
        if (speed >= cfg.vehicleCollisionMinSpeed) {
            for (Character character : currentContacts) {
                if (!activeCollisions.contains(character)) {
                    applyVehicleCollisionDamage(character, speed, cfg);
                }
            }
        }

        // VEHICLE_CRASH stimulus (PLAN.md E2): a fast impact against anything (wall or body) alerts
        // nearby AI. Throttled so a sustained scrape posts ~1×/s rather than every physics frame.
        crashStimulusCooldown = Math.max(0.0, crashStimulusCooldown - state.getStep());
        if (count > 0 && speed >= cfg.vehicleCollisionMinSpeed && crashStimulusCooldown <= 0.0) {
            StimulusManager sm = StimulusManager.get();
            if (sm != null) {
                String faction = (occupant != null && occupant.getCharacterInfo() != null)
                        ? occupant.getCharacterInfo().faction : "";
                sm.post(StimulusManager.Type.VEHICLE_CRASH, getGlobalPosition(),
                        CRASH_HEARING_RADIUS, this, faction);
                crashStimulusCooldown = CRASH_STIMULUS_INTERVAL;
            }
        }

        activeCollisions.clear();
        activeCollisions.addAll(currentContacts);
    }

    /** Audible range (m) of a vehicle crash to AI, and the min seconds between crash stimulus posts (E2). */
    private static final float  CRASH_HEARING_RADIUS    = 200f;
    private static final double CRASH_STIMULUS_INTERVAL = 0.75;

    private void applyVehicleCollisionDamage(Character character, float speed, VehicleConfig cfg) {
        float damage = (speed - cfg.vehicleCollisionMinSpeed) * cfg.vehicleCollisionDamageScale;
        Node healthNode = character.getNodeOrNull("Health");
        if (!(healthNode instanceof Health health)) return;

        String attackerName    = (occupant != null) ? occupant.getCharacterInfo().displayName : "";
        String attackerFaction = (characterInfo != null) ? characterInfo.faction : "";
        health.takeDamage(null, damage, DAMAGE_SOURCE_COLLISION, cfg.vehicleIcon, attackerName, attackerFaction);

        Vector3 knockbackDir = getLinearVelocity().normalized();
        character.applyHitImpulse(null, knockbackDir, damage);
    }

    /** Returns the typed weapon mode from the config int. */
    public VehicleWeaponMode getWeaponMode() {
        VehicleWeaponMode[] values = VehicleWeaponMode.values();
        int idx = Math.max(0, Math.min(getConfig().weaponModeIndex, values.length - 1));
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

    // ── NameplateTarget ─────────────────────────────────────────────────────────
    // The carrier reuses ui/Nameplate.tscn unchanged: the plate finds its sibling "Health" and
    // "WeaponController" nodes itself, so health + weapon/ammo are the CARRIER's. Only the colour
    // is carrier-specific — it follows the DRIVER's faction, neutral when not ridden or the driver
    // is down. tryEnter/tryExit (run on every peer via the host-arbitrated seat change) emit
    // nameplateChanged, so the tint re-derives on every peer with no extra net message.

    @RegisterSignal
    public final Signal0 nameplateChanged = new Signal0(this, new StringName("nameplate_changed"));

    @Override
    public String getNameplateText() {
        if (characterInfo != null && !characterInfo.displayName.isEmpty()) return characterInfo.displayName;
        return getName().toString();
    }

    @Override
    public Color getNameplateColor() {
        // Driver seat occupant determines the colour; neutral when empty or the driver is defeated.
        if (occupant != null && occupant.isAlive() && occupant.characterInfo != null) {
            return Faction.color(occupant.characterInfo.faction);
        }
        return Faction.color(Faction.NEUTRAL);
    }

    @Override
    public Signal0 getNameplateChangedSignal() { return nameplateChanged; }

    // ── Enter / Exit ──────────────────────────────────────────────────────────
    //
    // Round 11 N3: networked enter/exit is HOST-ARBITRATED. requestEnter/requestExit are
    // the intent entry points (Player input, _physicsProcess exit branch); the host
    // validates (VehicleSeatPolicy) and broadcasts MSG_VEHICLE_OCCUPANCY, and every peer —
    // including the requester — executes the seat change by running tryEnter/tryExit from
    // that event (GameManager.applyVehicleOccupancy). Locomotion authority migrates INSIDE
    // the same event (no client-originated MSG_OWNERSHIP anymore). Single-player routes
    // requestEnter/requestExit straight to tryEnter/tryExit — zero behavioural diff.

    /** Ask to seat {@code c}: direct in single-player, host-arbitrated when networked. */
    public void requestEnter(Character c) {
        if (occupant != null || c == null) return;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) {
            tryEnter(c);
            return;
        }
        String occupantId = c.characterInfo != null ? c.characterInfo.characterId : "";
        if (net.isServer()) {
            if (getNodeOrNull("/root/GameManager") instanceof com.openworld.game.GameManager gm) {
                gm.processVehicleSeatRequest(NetworkManager.SERVER_PEER_ID,
                        characterInfo.characterId, occupantId, true);
            }
        } else {
            net.requestVehicleSeat(characterInfo.characterId, occupantId, true);
        }
    }

    /** Ask to unseat the current occupant: direct in single-player, host-arbitrated when networked. */
    public void requestExit() {
        if (occupant == null) return;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) {
            tryExit();
            return;
        }
        String occupantId = occupant.characterInfo != null ? occupant.characterInfo.characterId : "";
        if (net.isServer()) {
            if (getNodeOrNull("/root/GameManager") instanceof com.openworld.game.GameManager gm) {
                gm.processVehicleSeatRequest(NetworkManager.SERVER_PEER_ID,
                        characterInfo.characterId, occupantId, false);
            }
        } else {
            net.requestVehicleSeat(characterInfo.characterId, occupantId, false);
        }
    }

    /**
     * Executes the seat change locally. Runs on EVERY peer (from the occupancy event when
     * networked), so it is puppet-aware: the controller hot-swap only happens for a live
     * (locally-driven) character — a puppet keeps its NetworkController on the character
     * (it still replicates aim/health/fire) and the vehicle keeps its VehicleNetworkController;
     * the camera only follows the LOCAL player's enter.
     */
    public void tryEnter(Character c) {
        if (occupant != null) return;
        occupant    = c;
        justEntered = true;

        VehicleWeaponMode mode = getWeaponMode();
        boolean localDriver = c.getController() instanceof PlayerController;

        c.enterDriveState(mode, this);
        c.setGlobalRotation(new Vector3(0f, (float) getGlobalRotation().getY(), 0f));

        if (!(c.getController() instanceof NetworkController)) {
            // A leftover puppet controller would be silently orphaned by attachController's
            // removeChild — applyAuthorityState normally clears it first (with velocity
            // seeding); this is the belt-and-braces for any other path.
            if (controller instanceof VehicleNetworkController vnc) {
                detachController();
                vnc.queueFree();
            }
            Controller ctrl = c.detachController();
            if (ctrl != null) attachController(ctrl);
        }

        if (mode == VehicleWeaponMode.PASSENGER_WEAPON && vehicleWeaponController != null) {
            RayCast3D vRay = vehicleWeaponController.getAimRay();
            if (vRay != null) {
                Node wc = c.getNodeOrNull("WeaponController");
                if (wc instanceof WeaponController wcn) wcn.overrideAimRay(vRay);
            }
        }

        if (localDriver) {
            if (camController != null) camController.setPassengerAimMode(mode == VehicleWeaponMode.PASSENGER_WEAPON);
            if (vehicleCamera != null) vehicleCamera.makeCurrent();
            emitEnterPrompt(false);
        }
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.vehicleEntered.emit(this, c.characterInfo);
        nameplateChanged.emit();   // re-tint the carrier plate to the new driver's faction
    }

    /** Executes the unseat locally — same puppet awareness as {@link #tryEnter}. */
    public void tryExit() {
        if (occupant == null) return;
        Character c = occupant;
        occupant = null;

        boolean localDriver = controller instanceof PlayerController;

        if (getWeaponMode() == VehicleWeaponMode.PASSENGER_WEAPON) {
            Node wc = c.getNodeOrNull("WeaponController");
            if (wc instanceof WeaponController wcn) wcn.restoreAimRay();
        }

        Vector3 right   = getGlobalTransform().getBasis().getColumn(0);
        Vector3 exitPos = getGlobalPosition()
                .minus(right.times(1.5f)).plus(new Vector3(0f, 0.8f, 0f));
        c.setGlobalPosition(exitPos);

        c.exitDriveState();

        // Only hand back what tryEnter hot-swapped in: a VehicleNetworkController stays —
        // it belongs to the vehicle's replication, not the character.
        if (!(controller instanceof VehicleNetworkController)) {
            Controller ctrl = detachController();
            if (ctrl != null) c.attachController(ctrl);
        }

        if (localDriver) {
            if (camController != null) camController.setPassengerAimMode(false);
            c.makeCameraActive();
        }
        activeCollisions.add(c);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.vehicleExited.emit(c.characterInfo);
        nameplateChanged.emit();   // seat now empty → carrier plate falls back to neutral
    }

    /**
     * Authority-side destruction (Health.died only ever fires where damage is applied —
     * applyReplicatedHealth never emits it, so a puppet can't reach this from a snapshot).
     * Ordered reliable sequence for clients, all on channel 0: occupancy-exit (inside the
     * exit grant) → WORLD_EVENT_VEHICLE_WRECK (cosmetics) → MSG_DESPAWN (node removal).
     */
    @RegisterFunction
    public void onVehicleDestruction() {
        if (occupant != null) {
            // FORCED unseat, never requestExit: the seat policy denies a host-initiated exit
            // for a client driver (NOT_OWNER), which would skip the occupancy broadcast and
            // free the driving client's controller inside the despawned vehicle. The forced
            // path bypasses the policy and broadcasts, so every peer unseats BEFORE the
            // wreck/despawn arrive on the same ordered channel.
            if (getNodeOrNull("/root/GameManager") instanceof com.openworld.game.GameManager gm) {
                gm.forceVehicleExit(this);
            }
            if (occupant != null) tryExit();   // no GameManager (tests/odd scenes) — at least free locally
        }

        VehicleConfig cfg = getConfig();
        if (cfg.explosionRadius > 0f) {
            String attackerName    = (characterInfo != null) ? characterInfo.displayName : getName().toString();
            String attackerFaction = (characterInfo != null) ? characterInfo.faction     : "";
            Node m = getTree().getFirstNodeInGroup("explosion_manager");
            if (m instanceof ExplosionManager mgr) {
                mgr.triggerExplosion(getGlobalPosition(), cfg.explosionRadius, cfg.explosionMaxDamage,
                                     cfg.explosionPushForce, attackerName, attackerFaction,
                                     DAMAGE_SOURCE_EXPLOSION, cfg.vehicleIcon, this);
            }
        }
        spawnWreckScene(cfg);

        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()
                && characterInfo != null) {
            net.broadcastWorldEvent(com.openworld.game.GameManager.WORLD_EVENT_VEHICLE_WRECK,
                    characterInfo.characterId, 0f);
        }
        if (getNodeOrNull("/root/GameManager") instanceof com.openworld.game.GameManager gm) {
            gm.despawnAuthoritative(this, characterInfo);
        } else {
            queueFree();
        }
    }

    /**
     * Client-side mirror of a host-confirmed destruction (WORLD_EVENT_VEHICLE_WRECK):
     * explosion VFX + wreck scene, NEVER damage — the host already applied that
     * authoritatively, and a client running the damage loop would relay duplicate
     * MSG_DAMAGE_REQUESTs for every body in the radius.
     */
    public void playWreckCosmetics() {
        VehicleConfig cfg = getConfig();
        if (cfg.explosionRadius > 0f) {
            Node m = getTree().getFirstNodeInGroup("explosion_manager");
            if (m instanceof ExplosionManager mgr) mgr.spawnExplosion(getGlobalPosition());
        }
        spawnWreckScene(cfg);
    }

    /** Instantiates the wreck scene at this vehicle's transform with its timed cleanup. */
    private void spawnWreckScene(VehicleConfig cfg) {
        if (cfg.wreckScene == null) return;
        Node wreck = cfg.wreckScene.instantiate();
        getTree().getCurrentScene().addChild(wreck);
        if (wreck instanceof Node3D w) w.setGlobalTransform(getGlobalTransform());
        SceneTreeTimer t = getTree().createTimer(cfg.wreckDuration, true, false, false);
        t.connect(new StringName("timeout"),
                Callable.createUnsafe(wreck, new StringName("queue_free")));
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

    /**
     * Replace the vehicle's controller, freeing the outgoing one (it has no other referent).
     * Callers retaining the old controller use {@link #detachController()} instead. Mirrors
     * Character.attachController — without the free a swapped-out controller leaks at exit.
     */
    public void attachController(Controller ctrl) {
        if (controller != null && controller != ctrl) {
            Controller old = controller;
            removeChild(old);
            old.queueFree();
        }
        controller = ctrl;
        addChild(ctrl);
    }

    public boolean isAlive() {
        return healthNode == null || !healthNode.isDead();
    }

    public Controller getController() { return controller; }

    public Character getOccupant()   { return occupant; }

    public boolean isSlipping()      { return slipping; }
    public void setSlipping(boolean s) { this.slipping = s; }
    public ArrayList<VehicleWheel> getWheels() { return wheels; }
    public boolean isBraking()       { return braking; }
    public boolean isHandbraking()   { return handBraking; }

    /**
     * The ACTUAL steer-wheel Y rotation (radians) — replicated so puppet wheels replay the
     * authority's pose exactly instead of re-integrating the raw input (N3).
     */
    public float getCurrentSteerAngle() {
        for (VehicleWheel w : wheels) {
            if (w.isSteer) return (float) w.getRotation().getY();
        }
        return 0f;
    }

    /** Current tick's motor input — replicated for puppet wheel visuals (N3). */
    public float getCurrentThrottle() { return cmd.motor; }
}
