package com.openworld.world;

import com.openworld.character.Character;
import com.openworld.game.EventBus;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Area3D;
import godot.api.Input;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Callable;
import godot.core.MethodCallable;
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
@Script(className = "Door")
public class Door extends Breakable {

    /** "ROTATE" (hinged) or "SLIDE" (pocket). */
    @Export public String openMode = "ROTATE";

    /** Swing angle in degrees for ROTATE mode (about local +Y). */
    @Export public float openAngleDeg = 90.0f;

    /** Local-space displacement when fully open in SLIDE mode. */
    @Export public Vector3 slideOffset = new Vector3(0, 0, 1.0);

    /** Open/close easing speed (fraction per second). */
    @Export public float openSpeed = 4.0f;

    /** AUTO: the sensor's occupancy drives open/close. {@code false} = MANUAL (player E-toggle / script). */
    @Export public boolean autoOpen = true;

    /** Area3D (a sibling/child path) used as the proximity/occupancy trigger. See class doc for sizing. */
    @Export public NodePath sensorPath = new NodePath();

    /** While true the door cannot open (authored initial state — consistent on every peer). */
    @Export public boolean locked = false;

    /** {@link #tryUnlock(String)} releases the lock when {@code key} matches (blank = no key required). */
    @Export public String unlockKeyId = "";

    /**
     * If set, the door auto-unlocks when THAT mission id completes; {@code "*"} means any mission completes.
     * BLANK MEANS NEVER (changed 2026-09-19): blank used to mean "any mission", which was harmless while a door was
     * hand-placed and is not now that every building in the city ships with locked doors -- the first mission
     * completed would have unlocked every door in the world, and a mission that re-locks its own shop at the end
     * (KonbiniMission) had its re-lock undone by its own completion event.
     */
    @Export public String unlockMissionId = "";

    /** A door ignores damage unless this is set; then it can be forced open (gated by {@code breakMinDamage}). */
    @Export public boolean breakable = false;

    /**
     * A hinged door swings AWAY from whoever opens it (PLAN.md 3.18g, user-reported: "with the current detection
     * the character is already close when the door opens, and then gets pushed out").
     *
     * <p>The sensor is a volume around the doorway, so it fires while the body is still walking up to the leaf --
     * which is what makes an automatic door feel automatic, and is exactly why a leaf that always swings the same
     * way meets somebody half the time. A real two-way door (自在戸, and every shop door with a push plate) opens
     * whichever way it is pushed, so the leaf turns away from the side the opener is standing on. The sign is
     * taken ONCE, at the moment the door starts to open, from the opener's position in the door's own frame, so
     * it can never flip mid-swing.
     *
     * <p>Off, the leaf always swings by {@code +openAngleDeg} -- the old behaviour, and the gate's control.
     */
    @Export public boolean swingBothWays = true;

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
    /** Which side of the closed leaf the last body to reach the sensor stands on: +1 = local +Z, -1 = -Z. */
    private double openerSide = -1.0;
    /** Which way the leaf is currently set to swing (+1 = +openAngleDeg). Probe readout. */
    @Visible public double swingSign = 1.0;

    @Register
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
                MethodCallable.createUnsafe(this, "on_mission_completed"));
        setPhysicsProcess(true); // doors tick every frame for the open/close easing
    }

    private void bindSensor() {
        if (sensorPath == null || sensorPath.isEmpty()) return;
        Node n = getNodeOrNull(sensorPath);
        if (!(n instanceof Area3D a)) return;
        sensor = a;
        sensor.connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_sensor_body_entered"));
        sensor.connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_sensor_body_exited"));
        // Seed counts from anything already overlapping (e.g. a body spawned inside the zone).
        for (Node3D b : sensor.getOverlappingBodies()) {
            if (!isCharacterBody(b)) continue;
            sensorOccupants++;
            if (isLocalPlayerBody(b)) localPlayerInSensor = true;
        }
        if (localPlayerInSensor && !autoOpen) emitPrompt(true);
    }

    @Register
    public void onSensorBodyEntered(Node3D body) {
        if (!isCharacterBody(body)) return;
        sensorOccupants++;
        noteOpenerSide(body);
        if (isLocalPlayerBody(body)) { localPlayerInSensor = true; if (!autoOpen) emitPrompt(true); }
    }

    /**
     * Record which side of the leaf a body reaching the sensor is on. The leaf spans the node's local -X and
     * stands in the local XY plane, so its normal is local +Z and the body's own local Z IS the side.
     */
    private void noteOpenerSide(Node3D body) {
        Vector3 local = getGlobalTransform().affineInverse().times(body.getGlobalPosition());
        if (Math.abs(local.getZ()) > 1e-3) openerSide = local.getZ() > 0 ? 1.0 : -1.0;
    }

    @Register
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

    /** Getter half of the exported {@code locked} property (see {@link #setLocked(boolean)}). */
    public boolean isLocked() {
        return locked;
    }

    /** Lock or unlock. Locking also shuts the door. */
    @Register
    public void setLocked(boolean value) {
        locked = value;
        if (locked) open = false;
        if (!autoOpen && localPlayerInSensor) emitPrompt(true); // refresh "Locked" / "Door (E)" text
    }

    /** Release the lock if {@code key} matches {@link #unlockKeyId} (or no key is required). */
    @Register
    public void tryUnlock(String key) {
        if (!locked) return;
        if (unlockKeyId == null || unlockKeyId.isEmpty() || unlockKeyId.equals(key)) setLocked(false);
    }

    /** Auto-unlock on a matching mission completion (rides the already-replicated EventBus signal). */
    @Register
    public void onMissionCompleted(String missionId, String winningFaction, String outcomeVariant) {
        if (!locked) return;
        if (unlockMissionId == null || unlockMissionId.isEmpty()) return;   // blank = never
        if ("*".equals(unlockMissionId) || unlockMissionId.equals(missionId)) setLocked(false);
    }

    // ── Manual control (story beats, scripts, or the E key in MANUAL mode) ───────

    @Register public void openDoor()   { if (!locked) open = true; }
    @Register public void closeDoor()  { open = false; }
    @Register public void toggleDoor() { open = !locked && !open; }

    /** Doors ignore damage unless {@link #breakable}; then they fall back to {@link Breakable} damage. */
    @Override
    public void applyDamage(float amount, Vector3 attackerPos) {
        if (!breakable) return;
        super.applyDamage(amount, attackerPos); // Breakable also gates on breakMinDamage
    }

    @Register
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
        if (target > 0.0f && progress == 0.0f && !isSlide()) {
            // the sign is taken once, while the door is still shut: away from the side the opener stands on
            swingSign = swingBothWays ? -openerSide : 1.0;
            openYaw = closedYaw + swingSign * Math.toRadians(openAngleDeg);
        }
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
