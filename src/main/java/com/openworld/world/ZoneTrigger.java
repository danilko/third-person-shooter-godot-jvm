package com.openworld.world;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.game.mission.MissionDirector;
import com.openworld.game.mission.MissionInfo;
import com.openworld.game.mission.MissionManager;
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
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.SphereMesh;
import godot.api.SphereShape3D;
import godot.api.StandardMaterial3D;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * The caller {@code MissionDirector.triggerBeat} was missing (PLAN.md Part F / F3): an authored
 * volume in the world that fires a story beat when the right body walks (or drives) into it —
 * mission start zones, objective markers, ambush triggers, cutscene entry points.
 *
 * <p><b>It does exactly one thing: it calls {@link MissionDirector#triggerBeat}.</b> What the beat
 * DOES is a Java handler registered by id on the director (beats are methods, not a scripting
 * language), so a trigger can never become a second place where story logic lives. A beat with no
 * handler still emits {@code EventBus.missionBeatTriggered}, so an authored volume is useful to
 * dialogue and HUD before any Java exists for it.
 *
 * <h3>"Has this already fired" is the DIRECTOR's answer, not a flag on this node</h3>
 * {@link #oneShot} consults {@code MissionDirector.beatFireCount(beatId)} rather than a local
 * boolean, and that is load-bearing rather than tidy: a trigger authored inside a streamed zone's
 * geometry is <i>freed and re-instanced</i> every time the player walks away and back, so a local
 * flag re-arms an ambush on every pass with nothing to see. The director's fired-beat log is
 * campaign state and outlives the node; {@code resetCampaign()} re-arms every trigger with it, which
 * is the same answer for the same reason.
 *
 * <h3>Every peer fires its own</h3>
 * The trigger is symmetric: it fires wherever a qualifying body enters, so a client's copy fires as
 * the client's copy of that body arrives. That matches the director's rule that a beat script runs
 * on both peers without knowing which it is — a beat whose EFFECT is host-authoritative (spawning a
 * squad) is gated inside its handler, exactly as {@code commandCharacter} already is. Putting a
 * "host only" flag on the volume would move that decision into the scene, away from the handler that
 * is the only thing that knows the answer.
 *
 * <h3>The mask is not authored</h3>
 * A ZoneTrigger detects characters and the carriers they ride, full stop, so {@code _ready} states
 * {@code CHARACTER | VEHICLE} itself. A seated occupant is on collision layer 0
 * ({@code CharacterDriveState.enter}), so without the VEHICLE half a player who DRIVES to the
 * mission marker trips nothing — and an area whose mask silently excludes the thing it is watching
 * for looks exactly like a trigger that was never wired.
 */
@Script(className = "ZoneTrigger")
public class ZoneTrigger extends Area3D {

	public static final String TRIGGER_GROUP = "zone_trigger";

	/** The story beat this volume fires. A trigger with no beat id is inert (and says so). */
	@Export public String beatId = "";

	/** Fire at most once per campaign — asked of the director's fired-beat log, see the class note. */
	@Export public boolean oneShot = true;

	/** Only fire while this mission is the active one ("" = any time). */
	@Export public String requiredMissionId = "";

	/** Only fire once this beat has fired ("" = no prerequisite) — objective markers in sequence. */
	@Export public String requiresBeat = "";

	/**
	 * Which body trips it: "" = any {@link Player} (the spec's case), otherwise the character whose
	 * {@code characterId} this is — an escortee reaching the drop-off is the other common trigger.
	 */
	@Export public String requiredCharacterId = "";

	/** Draw the volume at runtime so it can be walked into (debug aid, as {@code ZoneMarker} does). */
	@Export public boolean showDebugVolume = false;

	/** Print every entry and every refusal, with its reason. */
	@Export public boolean debugLog = false;

	/** How many times this volume has fired its beat — live state, for probes. */
	@Visible public int triggerCount = 0;

	/**
	 * CONTROL KNOB, always on. Off, {@link #oneShot} is a node-local flag instead of the director's
	 * fired-beat log — the implementation this class refuses, and the one a re-streamed zone re-arms.
	 * It exists so the gate can measure the difference rather than assert it in prose.
	 */
	@Visible public boolean campaignOneShot = true;

	/**
	 * CONTROL KNOB, always on. Off, the mask is {@code CHARACTER} alone, so a player who DRIVES in
	 * trips nothing — a seated occupant is on no collision layer.
	 */
	@Visible public boolean carrierAware = true;

	private static final Color ARMED_COLOR = new Color(1.0, 0.85, 0.0, 0.14);  // yellow — armed
	private static final Color FIRED_COLOR = new Color(0.1, 1.0, 0.3, 0.10);   // green  — spent

	private boolean firedLocally = false;

	private StandardMaterial3D volumeMat;
	private final List<Node> debugVisualNodes = new ArrayList<>();

	@Register
	@Override
	public void _ready() {
		addToGroup(new StringName(TRIGGER_GROUP));
		// See the class note: the mask is this node's own fact, never the scene's.
		setCollisionMask(carrierAware
				? CollisionLayers.CHARACTER | CollisionLayers.VEHICLE
				: CollisionLayers.CHARACTER);
		// godot-jvm registers @Register methods under their snake_case names.
		connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
		if (beatId.isEmpty()) {
			GD.printErr("[ZoneTrigger] '" + getName() + "' has no beat_id — it can never fire");
		}
		if (showDebugVolume) buildDebugVisuals();
		refreshDebugColor();
	}

	@Register
	@Override
	public void _exitTree() {
		volumeMat = null;
		debugVisualNodes.clear();
	}

	@Register
	public void onBodyEntered(Node3D body) {
		if (beatId.isEmpty()) return;
		Character c = resolveTripper(body);
		if (c == null) return;
		String refusal = refusalFor(c);
		if (refusal != null) {
			if (debugLog) GD.print("[ZoneTrigger] " + getName() + ": " + c.getName() + " — " + refusal);
			return;
		}
		fire(c);
	}

	/** Fire the beat regardless of who entered — the console/probe entry point. */
	@Register
	public boolean fireNow() {
		if (beatId.isEmpty()) return false;
		return fire(null);
	}

	private boolean fire(Character by) {
		MissionDirector dir = MissionDirector.get();
		if (dir == null) return false;
		triggerCount++;
		firedLocally = true;
		dir.triggerBeat(beatId);
		refreshDebugColor();
		if (debugLog) {
			GD.print("[ZoneTrigger] " + getName() + " fired '" + beatId + "'"
					+ (by == null ? "" : " (" + by.getName() + ")"));
		}
		return true;
	}

	/** Why this character does not trip the volume, or null when it does. */
	private String refusalFor(Character c) {
		MissionDirector dir = MissionDirector.get();
		if (dir == null) return "no MissionDirector";
		if (!requiredCharacterId.isEmpty()) {
			String id = c.characterInfo == null ? "" : c.characterInfo.characterId;
			if (!requiredCharacterId.equals(id)) return "not " + requiredCharacterId;
		} else if (!(c instanceof Player)) {
			return "not a player";
		}
		if (oneShot && (campaignOneShot ? dir.beatFireCount(beatId) > 0 : firedLocally)) {
			return "one-shot, '" + beatId + "' already fired";
		}
		if (!requiresBeat.isEmpty() && dir.beatFireCount(requiresBeat) == 0) {
			return "waiting on beat '" + requiresBeat + "'";
		}
		if (!requiredMissionId.isEmpty() && !requiredMissionId.equals(activeMissionId())) {
			return "mission '" + requiredMissionId + "' is not active";
		}
		return null;
	}

	/** True when this volume would fire for this character right now — probe/console readout. */
	@Register
	public boolean wouldFireFor(Node3D body) {
		Character c = resolveTripper(body);
		return c != null && !beatId.isEmpty() && refusalFor(c) == null;
	}

	/** Why the last-asked body would be refused, or "" — probe/console readout. */
	@Register
	public String refusalNow(Node3D body) {
		Character c = resolveTripper(body);
		if (c == null) return "not a character";
		String r = refusalFor(c);
		return r == null ? "" : r;
	}

	private String activeMissionId() {
		Node n = getNodeOrNull("/root/MissionManager");
		if (!(n instanceof MissionManager mm) || !mm.isActive()) return "";
		MissionInfo info = mm.getActiveMission();
		return info == null || info.missionId == null ? "" : info.missionId;
	}

	/**
	 * The character an entering body stands for: the body itself, a ragdoll bone's owner, or — for a
	 * carrier — whichever seated occupant qualifies. A driven car is how a player reaches most of
	 * this world, and its occupants are off every collision layer while seated.
	 */
	private Character resolveTripper(Node3D body) {
		if (body instanceof Character c) return c;
		if (body instanceof Vehicle v) {
			for (int seat = 0; seat < v.getSeatCount(); seat++) {
				Character rider = v.getSeatOccupant(seat);
				if (rider == null || !GD.isInstanceValid(rider)) continue;
				if (refusalFor(rider) == null) return rider;
			}
			return null;
		}
		Node owner = body == null ? null : body.getOwner();
		return (owner instanceof Character c) ? c : null;
	}

	// ── Debug volume ──────────────────────────────────────────────────────────

	private void refreshDebugColor() {
		if (volumeMat == null) return;
		MissionDirector dir = MissionDirector.get();
		boolean spent = oneShot && (campaignOneShot
				? (dir != null && dir.beatFireCount(beatId) > 0)
				: firedLocally);
		volumeMat.setAlbedo(spent ? FIRED_COLOR : ARMED_COLOR);
	}

	private void buildDebugVisuals() {
		volumeMat = new StandardMaterial3D();
		volumeMat.setTransparency(BaseMaterial3D.Transparency.ALPHA);
		volumeMat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
		volumeMat.setCullMode(BaseMaterial3D.CullMode.DISABLED);
		volumeMat.setAlbedo(ARMED_COLOR);
		for (Node child : getChildren()) {
			if (!(child instanceof CollisionShape3D cs)) continue;
			MeshInstance3D inst = new MeshInstance3D();
			if (cs.getShape() instanceof BoxShape3D box) {
				BoxMesh mesh = new BoxMesh();
				mesh.setSize(box.getSize());
				inst.setMesh(mesh);
			} else if (cs.getShape() instanceof SphereShape3D sphere) {
				SphereMesh mesh = new SphereMesh();
				mesh.setRadius(sphere.getRadius());
				mesh.setHeight(sphere.getRadius() * 2f);
				inst.setMesh(mesh);
			} else {
				continue;   // a hand-authored convex/concave volume draws itself well enough in-editor
			}
			inst.setMaterialOverride(volumeMat);
			inst.setTransform(cs.getTransform());
			addChild(inst);
			debugVisualNodes.add(inst);
		}
	}
}
