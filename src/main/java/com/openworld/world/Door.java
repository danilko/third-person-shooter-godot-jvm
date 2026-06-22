package com.openworld.world;

import com.openworld.character.Character;
import com.openworld.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Area3D;
import godot.api.Input;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;

/**
 * An openable doorway leaf (PLAN.md I2). Extends {@link Breakable}, so a door is both <b>openable</b>
 * (it swings or slides aside) and optionally <b>destructible</b> (forced open by destroying it).
 *
 * <p><b>Open style</b> ({@link #openMode}): {@code "ROTATE"} swings about the node's local +Y by
 * {@link #openAngleDeg} (place the node at the hinge edge, offset the leaf to one side); {@code "SLIDE"}
 * translates by {@link #slideOffset}.
 *
 * <p><b>Trigger — sensor only (no radius).</b> Assign {@link #sensorPath} to an Area3D whose
 * {@code collision_mask} is the character layer (2). In <b>AUTO</b> mode ({@link #autoOpen} true) the door
 * is open while a character occupies that sensor and closes when it empties — so size the sensor as a
 * <i>band straddling the doorway</i> (a metre or two each side), NOT the whole room, or it stays open while
 * anyone is anywhere inside. In <b>MANUAL</b> mode ({@code autoOpen = false}) the sensor only marks the
 * local player as "near"; the player presses the {@code interact} key (E) to toggle it (HUD prompt via
 * {@code EventBus.pickupInteractChanged}, mirroring {@code Pickup.requireInteract}). Scripts/story can also
 * drive it with {@link #openDoor()}/{@link #closeDoor()}/{@link #toggleDoor()}.
 *
 * <p><b>Lock.</b> A {@link #locked} door cannot open by any normal path. Release it with
 * {@link #setLocked(boolean)} / {@link #tryUnlock(String)} (a "key" is just any caller — no inventory
 * exists yet; {@link #unlockKeyId} blank = no key needed), or set {@link #unlockMissionId} to auto-unlock
 * when that mission completes (rides {@code EventBus.missionCompleted}, which already replicates to every
 * peer, so the unlock is consistent across co-op with no extra networking). A hard mission gate is simply
 * {@code locked = true, breakable = false}; there is no separate "mission mode".
 *
 * <p><b>Force entry.</b> A locked door can still be broken open <i>if</i> {@link #breakable}; the inherited
 * {@link Breakable#breakMinDamage} gate means weak hits (fists / light melee) bounce while bullets /
 * explosions / heavy melee destroy it. Breaking works regardless of {@code locked}.
 *
 * <p><b>Networking:</b> the open/close animation is local per-peer (each peer opens for its own nearby
 * bodies). Lock state stays consistent via the authored initial value + the replicated mission-unlock +
 * the inherited host-authoritative break/restore replication.
 */
@RegisterClass(className = "Door")
public class Door extends Breakable {

    /** "ROTATE" (hinged) or "SLIDE" (pocket). */
    @Export @RegisterProperty public String openMode = "ROTATE";

    /** Swing angle in degrees for ROTATE mode (about local +Y). */
    @Export @RegisterProperty public float openAngleDeg = 90.0f;

    /** Local-space displacement when fully open in SLIDE mode. */
    @Export @RegisterProperty public Vector3 slideOffset = new Vector3(0, 0, 1.0);

    /** Open/close easing speed (fraction per second). */
    @Export @RegisterProperty public float openSpeed = 4.0f;

    /** AUTO: the sensor's occupancy drives open/close. {@code false} = MANUAL (player E-toggle / script). */
    @Export @RegisterProperty public boolean autoOpen = true;

    /** Area3D (a sibling/child path) used as the proximity/occupancy trigger. See class doc for sizing. */
    @Export @RegisterProperty public NodePath sensorPath = new NodePath();

    /** While true the door cannot open (authored initial state — consistent on every peer). */
    @Export @RegisterProperty public boolean locked = false;

    /** {@link #tryUnlock(String)} releases the lock when {@code key} matches (blank = no key required). */
    @Export @RegisterProperty public String unlockKeyId = "";

    /** If set, the door auto-unlocks when this mission id completes (blank = any mission completion). */
    @Export @RegisterProperty public String unlockMissionId = "";

    /** A door ignores damage unless this is set; then it can be forced open (gated by {@code breakMinDamage}). */
    @Export @RegisterProperty public boolean breakable = false;

    private Vector3 closedPos;
    private Vector3 openPos;
    private double closedYaw;
    private double openYaw;
    private float progress;     // 0 = closed, 1 = open
    private boolean open;

    private Area3D sensor;
    private int sensorOccupants;          // any character — drives AUTO open
    private boolean localPlayerInSensor;  // local player — drives MANUAL prompt + E
    private EventBus eventBus;

    @RegisterFunction
    @Override
    public void _ready() {
        super._ready(); // Breakable: group registration, breakableId fallback, currentHealth, physics off
        closedPos = getPosition();
        closedYaw = getRotation().getY();
        if (isSlide()) {
            openPos = closedPos.plus(slideOffset);
            openYaw = closedYaw;
        } else {
            openPos = closedPos;
            openYaw = closedYaw + Math.toRadians(openAngleDeg);
        }
        bindSensor();
        EventBus bus = getEventBus();
        if (bus != null) bus.connect(new StringName("mission_completed"),
                Callable.createUnsafe(this, new StringName("on_mission_completed")));
        setPhysicsProcess(true); // doors tick every frame for the open/close easing
    }

    private void bindSensor() {
        if (sensorPath == null || sensorPath.isEmpty()) return;
        Node n = getNodeOrNull(sensorPath);
        if (!(n instanceof Area3D a)) return;
        sensor = a;
        sensor.connect(new StringName("body_entered"), Callable.createUnsafe(this, new StringName("on_sensor_body_entered")));
        sensor.connect(new StringName("body_exited"), Callable.createUnsafe(this, new StringName("on_sensor_body_exited")));
        // Seed counts from anything already overlapping (e.g. a body spawned inside the zone).
        for (Node3D b : sensor.getOverlappingBodies()) {
            if (!isCharacterBody(b)) continue;
            sensorOccupants++;
            if (isLocalPlayerBody(b)) localPlayerInSensor = true;
        }
        if (localPlayerInSensor && !autoOpen) emitPrompt(true);
    }

    @RegisterFunction
    public void onSensorBodyEntered(Node3D body) {
        if (!isCharacterBody(body)) return;
        sensorOccupants++;
        if (isLocalPlayerBody(body)) { localPlayerInSensor = true; if (!autoOpen) emitPrompt(true); }
    }

    @RegisterFunction
    public void onSensorBodyExited(Node3D body) {
        if (!isCharacterBody(body)) return;
        sensorOccupants = Math.max(0, sensorOccupants - 1);
        if (isLocalPlayerBody(body)) { localPlayerInSensor = false; if (!autoOpen) emitPrompt(false); }
    }

    private boolean isCharacterBody(Node3D body) {
        return body instanceof Character || body.getOwner() instanceof Character;
    }

    private boolean isLocalPlayerBody(Node3D body) {
        Character c = (body instanceof Character ch) ? ch
                : (body.getOwner() instanceof Character ch2 ? ch2 : null);
        return c != null && c.isLocalOwnedPlayer();
    }

    private boolean isSlide() { return "SLIDE".equalsIgnoreCase(openMode); }

    // ── Lock / unlock ───────────────────────────────────────────────────────────

    /** Lock or unlock. Locking also shuts the door. */
    @RegisterFunction
    public void setLocked(boolean value) {
        locked = value;
        if (locked) open = false;
        if (!autoOpen && localPlayerInSensor) emitPrompt(true); // refresh "Locked" / "Door (E)" text
    }

    /** Release the lock if {@code key} matches {@link #unlockKeyId} (or no key is required). */
    @RegisterFunction
    public void tryUnlock(String key) {
        if (!locked) return;
        if (unlockKeyId == null || unlockKeyId.isEmpty() || unlockKeyId.equals(key)) setLocked(false);
    }

    /** Auto-unlock on a matching mission completion (rides the already-replicated EventBus signal). */
    @RegisterFunction
    public void onMissionCompleted(String missionId, String winningFaction, String outcomeVariant) {
        if (!locked) return;
        if (unlockMissionId == null || unlockMissionId.isEmpty() || unlockMissionId.equals(missionId)) setLocked(false);
    }

    // ── Manual control (story beats, scripts, or the E key in MANUAL mode) ───────

    @RegisterFunction public void openDoor()   { if (!locked) open = true; }
    @RegisterFunction public void closeDoor()  { open = false; }
    @RegisterFunction public void toggleDoor() { open = !locked && !open; }

    /** Doors ignore damage unless {@link #breakable}; then they fall back to {@link Breakable} damage. */
    @Override
    public void applyDamage(float amount, Vector3 attackerPos) {
        if (!breakable) return;
        super.applyDamage(amount, attackerPos); // Breakable also gates on breakMinDamage
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        super._physicsProcess(delta); // Breakable restore-timer (no-op unless a restore is pending)
        if (isBroken()) return;       // a broken-down door no longer swings

        if (locked) {
            open = false;
        } else if (autoOpen) {
            open = sensorOccupants > 0;
        } else if (localPlayerInSensor && Input.INSTANCE.isActionJustPressed("interact", false)) {
            open = !open; // manual E toggle
        }

        float target = open ? 1.0f : 0.0f;
        if (progress != target) {
            float step = (float) (openSpeed * delta);
            if (target > progress) progress = Math.min(target, progress + step);
            else progress = Math.max(target, progress - step);
            applyOpening();
        }
    }

    private void applyOpening() {
        if (isSlide()) {
            setPosition(closedPos.lerp(openPos, progress));
        } else {
            Vector3 r = getRotation();
            double yaw = closedYaw + (openYaw - closedYaw) * progress;
            setRotation(new Vector3(r.getX(), yaw, r.getZ()));
        }
    }

    /** Breakable.restore disables physics processing; a door must keep ticking after a story restore. */
    @Override
    public void restore(boolean broadcast) {
        super.restore(broadcast);
        setPhysicsProcess(true);
    }

    // ── HUD prompt (manual doors) ────────────────────────────────────────────────

    private void emitPrompt(boolean inRange) {
        EventBus bus = getEventBus();
        if (bus == null) return;
        bus.pickupInteractChanged.emit(inRange, inRange ? (locked ? "Locked" : "Door (E)") : "");
    }

    private EventBus getEventBus() {
        if (eventBus == null) {
            Node n = getNodeOrNull("/root/EventBus");
            if (n instanceof EventBus eb) eventBus = eb;
        }
        return eventBus;
    }
}
