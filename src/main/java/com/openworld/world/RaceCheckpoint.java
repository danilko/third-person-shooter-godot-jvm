package com.openworld.world;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.game.PlayerRegistry;
import com.openworld.character.Player;
import com.openworld.game.mission.RaceDirector;
import com.openworld.util.CollisionLayers;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Area3D;
import godot.api.BaseMaterial3D;
import godot.api.BoxMesh;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.CylinderMesh;
import godot.api.CylinderShape3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * One gate of a race route (PLAN.md 4.5 / R2) — an {@link Area3D} an artist drops on the racing
 * line, or that {@code WorldBaker} bakes from a {@code race_<raceId>_<idx>} empty.
 *
 * <p><b>It reports; it does not adjudicate.</b> Entering bodies are handed to
 * {@link RaceDirector#onCheckpointTouched}, which owns every rule that could differ between two
 * checkpoints — whose next index this is, whether the race is running, whether this peer is the
 * host. Putting any of that here would give each gate its own copy of the race's rules.
 *
 * <h3>The mask is this node's own fact</h3>
 * {@code CHARACTER | VEHICLE}, stated in {@code _ready} rather than authored, for the reason
 * {@link ZoneTrigger} states it: a seated occupant is on collision layer 0
 * ({@code CharacterDriveState.enter}), so a checkpoint watching only CHARACTER would be invisible to
 * every car in the race — which looks exactly like a gate that was never wired.
 *
 * <h3>The marker is drawn by default, and that is not a debug default</h3>
 * A race is unplayable if you cannot see the next gate: GTA draws a corona, and until there is art
 * for one this procedural ring stands in. It tints itself from the LOCAL player's progress (gold =
 * your next gate, faint blue = a later one, green = already taken), which is the whole of what a
 * racer needs to read off the world.
 */
@Script(className = "RaceCheckpoint")
public class RaceCheckpoint extends Area3D {

    public static final String GROUP = "race_checkpoint";

    /** Which circuit this gate belongs to. A race is started by this name (see {@code MissionInfo.raceId}). */
    @Export public String raceId = "";

    /** Position in the route, 0-based. The route IS these in index order; gaps are not allowed. */
    @Export public int checkpointIndex = 0;

    /** Draw the gate. On by default — see the class note; off for an authored art marker. */
    @Export public boolean showMarker = true;

    /** Marker radius in metres when this node authors no {@link CollisionShape3D} of its own. */
    @Export public float markerRadius = 9f;

    /** Marker height in metres. Tall enough to read from a car at speed. */
    @Export public float markerHeight = 12f;

    @Export public boolean debugLog = false;

    /** How many times a racer has cleared this gate this session — live state, for probes. */
    @Visible public int clearedCount = 0;

    private static final Color NEXT_COLOR  = new Color(1.0, 0.78, 0.1, 0.30);   // gold  — your next gate
    private static final Color LATER_COLOR = new Color(0.25, 0.6, 1.0, 0.13);   // blue  — a later gate
    private static final Color TAKEN_COLOR = new Color(0.1, 1.0, 0.35, 0.09);   // green — already cleared

    private StandardMaterial3D markerMat;
    private final List<Node> markerNodes = new ArrayList<>();
    private double tintTimer = 0.0;

    @Register
    @Override
    public void _ready() {
        addToGroup(new StringName(GROUP));
        setCollisionMask(CollisionLayers.CHARACTER | CollisionLayers.VEHICLE);
        // godot-jvm registers @Register methods under their snake_case names.
        connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
        if (raceId.isEmpty()) {
            GD.printErr("[RaceCheckpoint] '" + getName() + "' has no race_id — it belongs to no route");
        }
        ensureShape();
        RaceDirector dir = RaceDirector.get();
        if (dir != null) dir.registerCheckpoint(this);
        if (showMarker) buildMarker();
    }

    @Register
    @Override
    public void _exitTree() {
        RaceDirector dir = RaceDirector.get();
        if (dir != null) dir.unregisterCheckpoint(this);
        markerMat = null;
        markerNodes.clear();
    }

    @Register
    @Override
    public void _process(double delta) {
        if (markerMat == null) return;
        tintTimer -= delta;
        if (tintTimer > 0.0) return;
        tintTimer = 0.25;      // the local player's progress changes at gate frequency, not frame frequency
        refreshTint();
    }

    /**
     * A shape is authored on a hand-placed gate and is NOT on a baked one, so this node states a
     * default rather than failing silently — an {@code Area3D} with no shape detects nothing and
     * says nothing about it.
     */
    private void ensureShape() {
        for (Node child : getChildren()) if (child instanceof CollisionShape3D) return;
        CollisionShape3D cs = new CollisionShape3D();
        CylinderShape3D cyl = new CylinderShape3D();
        cyl.setRadius(markerRadius);
        cyl.setHeight(markerHeight);
        cs.setShape(cyl);
        addChild(cs);
    }

    @Register
    public void onBodyEntered(Node3D body) {
        RaceDirector dir = RaceDirector.get();
        if (dir == null) return;
        for (Character c : occupantsOf(body)) {
            if (dir.onCheckpointTouched(this, c)) {
                clearedCount++;
                if (debugLog) GD.print("[RaceCheckpoint] " + getName() + " cleared by " + c.getName());
                refreshTint();
            }
        }
    }

    /**
     * Every racer this body stands for: the character itself, a ragdoll bone's owner, or — for a
     * carrier — every seated occupant. All of them, not just the driver: who is enrolled is the
     * director's answer, and a passenger who is a racer has as much claim to the gate they were
     * carried through as the driver does.
     */
    private List<Character> occupantsOf(Node3D body) {
        List<Character> out = new ArrayList<>(2);
        if (body instanceof Character c) { out.add(c); return out; }
        if (body instanceof Vehicle v) {
            for (int seat = 0; seat < v.getSeatCount(); seat++) {
                Character rider = v.getSeatOccupant(seat);
                if (rider != null && GD.isInstanceValid(rider)) out.add(rider);
            }
            return out;
        }
        Node owner = body == null ? null : body.getOwner();
        if (owner instanceof Character c) out.add(c);
        return out;
    }

    // ── Marker ────────────────────────────────────────────────────────────────

    private void refreshTint() {
        if (markerMat == null) return;
        RaceDirector dir = RaceDirector.get();
        String localId = localRacerId();
        if (dir == null || localId.isEmpty() || !dir.isRacer(localId)) {
            markerMat.setAlbedo(LATER_COLOR);
            return;
        }
        if (dir.isNextFor(this, localId)) markerMat.setAlbedo(NEXT_COLOR);
        else if (checkpointIndex < dir.racerNextIndex(localId)) markerMat.setAlbedo(TAKEN_COLOR);
        else markerMat.setAlbedo(LATER_COLOR);
    }

    /** The locally-owned player's characterId, or "" — the gate is tinted for the person driving. */
    private static String localRacerId() {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p != null && GD.isInstanceValid(p) && p.isLocalOwnedPlayer() && p.characterInfo != null) {
                return p.characterInfo.characterId;
            }
        }
        return "";
    }

    private void buildMarker() {
        markerMat = new StandardMaterial3D();
        markerMat.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        markerMat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        markerMat.setCullMode(BaseMaterial3D.CullMode.DISABLED);
        markerMat.setAlbedo(LATER_COLOR);
        for (Node child : getChildren()) {
            if (!(child instanceof CollisionShape3D cs)) continue;
            MeshInstance3D inst = new MeshInstance3D();
            if (cs.getShape() instanceof CylinderShape3D cyl) {
                CylinderMesh mesh = new CylinderMesh();
                mesh.setTopRadius(cyl.getRadius());
                mesh.setBottomRadius(cyl.getRadius());
                mesh.setHeight(cyl.getHeight());
                inst.setMesh(mesh);
            } else if (cs.getShape() instanceof BoxShape3D box) {
                BoxMesh mesh = new BoxMesh();
                mesh.setSize(box.getSize());
                inst.setMesh(mesh);
            } else {
                continue;
            }
            inst.setMaterialOverride(markerMat);
            inst.setTransform(cs.getTransform());
            addChild(inst);
            markerNodes.add(inst);
        }
        refreshTint();
    }
}
