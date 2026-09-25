package com.openworld.world;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.AnimationPlayer;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.ResourceLoader;
import godot.core.PackedVector3Array;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * The FAR tier of the ambient crowd (PLAN.md 3.6d): a lightweight pedestrian is a SCRIPT-FREE scene -- a skinned
 * mesh, a skeleton and an {@code AnimationPlayer}, nothing else -- whose transform this ONE node writes, so the
 * crowd costs no per-body JVM callback at all. It is the GTA pedestrian LOD: far peds are a moving picture, and a
 * ped near a player is PROMOTED to a real {@code AICharacter} (shootable, collidable, perceiving) by
 * {@link ZoneManager}, which owns every body that can be interacted with.
 *
 * <p><b>Why a new tier rather than more LOD on the body.</b> D2 already skips an AI's FSM and its AnimationTree
 * writes past 80 m, and a sidewalk walker beyond that GLIDES (its controller moves it directly and
 * MovementController stands down). Measured on {@code probe_city_perf.gd --crowd}, a glided walker still cost
 * ~0.06 ms per physics tick -- because what is left is not its behaviour, it is that a {@code Character} body is
 * ~10 JVM-scripted nodes and the engine calls into the JVM for each of them, every tick, forever. No flag on
 * those nodes removes that. Only having no scripted nodes does.
 *
 * <p><b>It is LOCAL to each peer and is never replicated</b>, the rule 3.11b set for the knocked-down poles:
 * cosmetic state costs no bandwidth. Each peer walks its own crowd from its own RNG, so two peers see different
 * ambient people 100 m away -- which nobody can tell, because nothing 100 m away can be interacted with. What IS
 * interactive is the promoted body, and that is a host-authoritative {@code AICharacter} spawn on the wire
 * already. <b>Accepted divergence:</b> a client does not promote (only the host may spawn an AI), so inside
 * {@link #promoteDistance} of the local player a client simply HIDES its own light peds and shows the host's
 * replicated walkers instead. At the boundary the two populations are not the same people.
 */
@Script(className = "PedCrowd")
public class PedCrowd extends Node3D {

	/**
	 * The script-free body every light ped instances: no MeshConfig and no modifiers.
	 *
	 * <p>It is the <b>LOD</b> body ({@code blender/tools/build_ped_body.py}), not the playable one. At the
	 * nearest distance this tier is ever drawn -- {@link #promoteDistance}, 80 m -- a 1.65 m body is ~14 px tall
	 * on a 1080p screen, so what costs anything is DRAW CALLS: the playable body is 3 {@code MeshInstance3D} but
	 * <b>17 surfaces with 17 materials</b>, i.e. ~17 draws per light ped with ~100 of them in range downtown.
	 * The LOD body is ONE surface over one atlas (and 2 clips instead of 173, so 2.0 MB against 48.8). It is
	 * built FROM the shipped export and clones that body's own material, so it can never drift from what the
	 * player sees -- gate {@code tools/godot/probe_ped_body.gd}.
	 */
	public static final String PED_SCENE = "res://assets/characters/shino/shino_ped.tscn";
	private static final StringName WALK_CLIP = new StringName("upright_walk_forward");
	private static final StringName RUN_CLIP = new StringName("upright_sprint_forward");

	/** A walking pace (m/s). The same number {@code SidewalkWalkerController} glides at, so a promotion does not
	 *  visibly change speed. */
	@Visible public double speed = 1.4;
	/** How far above the footway line a ped's origin rides. */
	@Visible public double lift = 0.02;
	/**
	 * Within this of a player a light ped is PROMOTED to a full body (host / single player) or HIDDEN (client).
	 * It is D2's own ACTIVE boundary, deliberately: "is a player near" already has one owner and one number.
	 */
	@Visible public double promoteDistance = 80.0;
	/** A full walker beyond this is handed back to the crowd. The gap is hysteresis, the Zone load/unload rule:
	 *  one threshold makes a body that stands on it promote and demote every tick. */
	@Visible public double demoteDistance = 100.0;
	/** Beyond this a ped's AnimationPlayer is stopped: a frozen skeleton still skins, but costs no animation
	 *  tick, and a walk cycle is not readable at this range. */
	@Visible public double animateDistance = 60.0;
	/**
	 * How far a light ped is DRAWN (R9 follow-up, measured 2026-09-22 with probe_walk_perf.gd at the station: the light
	 * crowd was ~1 100 of its ~4 000 draw calls, p50 13.3 ms with it against 6.9 without). A light ped is never nearer
	 * than {@link #promoteDistance} (closer ones are real bodies), so it draws WITHOUT shadows and fades out at this
	 * distance: a 1.6 m figure is ~10 px tall at 180 m. Set once per ped on its meshes (engine-side culling, no
	 * per-frame cost). 0 = drawn to the zone's edge with shadows (the control).
	 */
	@Visible public double drawDistance = 180.0;
	/** Peds are advanced in this many groups, one group per physics frame, each moved by the whole group's worth
	 *  of time. A ped is a straight-line walker, so the coarser step is invisible and the per-frame cost is
	 *  divided by it. */
	@Visible public int updateGroups = 4;
	/** Off = the control: every ped updated every frame with its animation running. */
	@Visible public boolean staggerUpdates = true;

	/**
	 * The light tier REACTS (PLAN.md 3.32): a ped that hears a gunshot or an explosion within {@link #panicRange}
	 * (and inside the stimulus's own audible radius), or that a player is AIMING at from beyond the promote ring
	 * (a scope), runs AWAY along its own footway for {@link #panicSeconds} and then walks again. It is the whole
	 * of "the majority is startled and flees" and it costs no promotion: no body, no script, no physics -- one
	 * clip change and a timer per ped. What a light ped cannot do (fight back, be carjacked, ragdoll) is what a
	 * promotion is for. Off = the control: the crowd ignores everything.
	 */
	@Visible public boolean reactions = true;
	/** How far a light ped hears trouble, capped by each stimulus's own radius. */
	@Visible public double panicRange = 120.0;
	/** How long a startled ped runs before it calms down (a new scare restarts it). */
	@Visible public double panicSeconds = 8.0;
	/** A fleeing ped's pace (m/s), a run, and its walk cycle is replaced by {@code upright_sprint_forward}. */
	@Visible public double fleeSpeed = 4.5;
	/** A ped within this of a player's aim point, while that player is in combat, counts as aimed at. */
	@Visible public double aimedAtRadius = 2.0;

	/** Metres walked by the whole crowd -- a probe readout, so "are they actually moving" is measurable. */
	@Visible public double walkedTotal = 0.0;

	/** One light pedestrian. Plain Java: no Godot object but the body node and its path, both value-ish. */
	private static final class Ped {
		Node3D body;
		AnimationPlayer anim;
		PackedVector3Array path;
		double[] cum;
		double along;
		int dir;
		boolean animating = true;
		boolean hidden = false;
		/** Seconds of panic left (0 = calm). */
		double flee = 0.0;
		/** Where the scare came from (world), so the ped keeps running away from it. */
		Vector3 threat;
		boolean running = false;
	}

	private final List<Ped> peds = new ArrayList<>();
	private PackedScene pedScene;
	private int group = 0;
	/** The newest stimulus timestamp this crowd has already reacted to. */
	private double heardUpTo = -1.0;
	private int scaresTotal = 0;

	/** Set by {@link ZoneManager} so a promotion can be handed back to the one owner of AI spawning. */
	private ZoneManager owner;
	private Object ownerZone;

	@Register
	@Override
	public void _ready() {
		setProcessPriority(0);
	}

	/** ZoneManager tells the crowd who to call back for a promotion; null = decorative only (a probe stand). */
	public void bind(ZoneManager manager, Object zoneKey) {
		this.owner = manager;
		this.ownerZone = zoneKey;
	}

	public Object zoneKey() { return ownerZone; }

	/** Add one ped walking {@code path} from arc position {@code along} in {@code dir} (+1 / -1). */
	@Register
	public void addPed(PackedVector3Array path, double along, int dir) {
		if (path.getSize() < 2) return;
		if (pedScene == null) {
			pedScene = (PackedScene) ResourceLoader.INSTANCE.load(PED_SCENE, "", ResourceLoader.CacheMode.REUSE);
			if (pedScene == null) { GD.pushError("PedCrowd: cannot load " + PED_SCENE); return; }
		}
		Node n = pedScene.instantiate();
		if (!(n instanceof Node3D body)) { if (n != null) n.queueFree(); return; }
		Ped p = new Ped();
		p.body = body;
		p.path = path;
		p.cum = new double[path.getSize()];
		for (int i = 1; i < p.cum.length; i++) {
			p.cum[i] = p.cum[i - 1] + path.get(i).distanceTo(path.get(i - 1));
		}
		p.along = Math.max(0.5, Math.min(along, Math.max(0.5, length(p) - 0.5)));
		p.dir = dir >= 0 ? 1 : -1;
		addChild(body);
		if (drawDistance > 0.0) {
			for (Node g : body.findChildren("*", "GeometryInstance3D", true, false)) {
				if (!(g instanceof godot.api.GeometryInstance3D gi)) continue;
				gi.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
				gi.setVisibilityRangeEnd((float) drawDistance);
				gi.setVisibilityRangeEndMargin(20.0f);
				gi.setVisibilityRangeFadeMode(godot.api.GeometryInstance3D.VisibilityRangeFadeMode.SELF);
			}
		}
		p.anim = body.getNodeOrNull("AnimationPlayer") instanceof AnimationPlayer ap ? ap : null;
		if (p.anim != null) {
			// Every ped starts the same clip at its OWN offset, or a crowd marches in step.
			p.anim.play(WALK_CLIP, -1.0, 1.0f, false);
			double len = p.anim.currentAnimationLengthProperty();
			if (len > 0.0) p.anim.seek(GD.randfRange(0.0f, (float) len), true, false);
		}
		place(p);
		peds.add(p);
	}

	@Register public int pedCount() { return peds.size(); }

	/** How many peds are drawn right now (a client hides the ring a host would have promoted). */
	@Register
	public int visiblePedCount() {
		int n = 0;
		for (Ped p : peds) if (!p.hidden) n++;
		return n;
	}

	@Register public double walkedTotalNow() { return walkedTotal; }

	/** How many peds are running from something right now (a probe readout). */
	@Register
	public int fleeingNow() {
		int n = 0;
		for (Ped p : peds) if (p.flee > 0.0) n++;
		return n;
	}

	/** Scares taken since the crowd was built (each ped counts once per scare). */
	@Register public int scaresNow() { return scaresTotal; }

	/** Remove and free every ped (zone unload). */
	@Register
	public void clearPeds() {
		for (Ped p : peds) {
			if (GD.isInstanceValid(p.body)) { removeChild(p.body); p.body.queueFree(); }
		}
		peds.clear();
	}

	@Register
	@Override
	public void _exitTree() {
		clearPeds();
	}

	@Register
	@Override
	public void _physicsProcess(double delta) {
		if (peds.isEmpty()) return;
		int groups = staggerUpdates ? Math.max(1, updateGroups) : 1;
		double step = delta * groups;
		List<Player> players = PlayerRegistry.getPlayers();
		boolean canPromote = owner != null && authoritative();
		// Promotions are collected and applied AFTER the walk: removing from `peds` mid-loop shifts every
		// later ped into a different group, so the stagger would silently stop being a partition.
		List<Ped> promoted = null;
		if (reactions) hear();
		List<Vector3> aims = reactions ? aimPoints(players) : null;
		for (int i = group; i < peds.size(); i += groups) {
			Ped p = peds.get(i);
			if (!GD.isInstanceValid(p.body)) continue;
			if (aims != null && !aims.isEmpty()) {
				Vector3 here = pointAt(p, p.along);
				for (Vector3 a : aims) {
					if (here.distanceTo(a) <= aimedAtRadius + 1.0) { scare(p, a); break; }
				}
			}
			if (p.flee > 0.0) p.flee = Math.max(0.0, p.flee - step);
			advance(p, step);
			double d = nearestPlayerDist(p, players);
			if (d < promoteDistance) {
				if (canPromote) {
					// Hand the body over: the crowd never spawns an AICharacter itself, because every
					// interactive body in the world is ZoneManager's to pool, arm and announce. A refusal
					// (zone gone, pool empty) is not an error: the ped simply keeps walking.
					if (owner.promoteSidewalkPed(ownerZone, p.path, p.along, p.dir)) {
						if (promoted == null) promoted = new ArrayList<>();
						promoted.add(p);
						continue;
					}
				} else if (!p.hidden) {
					p.hidden = true;
					p.body.setVisible(false);
				}
			} else if (p.hidden) {
				p.hidden = false;
				p.body.setVisible(true);
			}
			boolean wantAnim = !p.hidden && d < animateDistance;
			boolean wantRun = p.flee > 0.0;
			if (p.anim != null && (wantAnim != p.animating || (wantAnim && wantRun != p.running))) {
				p.animating = wantAnim;
				p.running = wantRun;
				if (wantAnim) p.anim.play(wantRun ? RUN_CLIP : WALK_CLIP, 0.2, 1.0f, false); else p.anim.pause();
			}
			place(p);
		}
		if (promoted != null) {
			for (Ped p : promoted) {
				if (GD.isInstanceValid(p.body)) { removeChild(p.body); p.body.queueFree(); }
			}
			peds.removeAll(promoted);
		}
		group = (group + 1) % groups;
	}

	/** True where this peer decides what exists: single player, or the host. */
	private boolean authoritative() {
		Node n = getNodeOrNull("/root/NetworkManager");
		NetworkManager net = n instanceof NetworkManager m ? m : null;
		return net == null || !net.isNetworked() || net.isServer();
	}

	private double length(Ped p) { return p.cum.length == 0 ? 0.0 : p.cum[p.cum.length - 1]; }

	/** React to every stimulus newer than the last frame's: each ped in range starts (or restarts) running. */
	private void hear() {
		StimulusManager sm = StimulusManager.get();
		if (sm == null) return;
		double newest = heardUpTo;
		for (StimulusManager.Stimulus st : sm.getStimuli()) {
			if (st.timestamp <= heardUpTo) continue;
			newest = Math.max(newest, st.timestamp);
			if (st.type != StimulusManager.Type.GUNSHOT && st.type != StimulusManager.Type.EXPLOSION) continue;
			double r = Math.min(panicRange, st.radius);
			for (Ped p : peds) {
				if (pointAt(p, p.along).distanceTo(st.origin) <= r) scare(p, st.origin);
			}
		}
		heardUpTo = newest;
	}

	/** Where each player in combat is aiming (their aim marker), beyond the promote ring only by construction:
	 *  a nearer ped is a real body that reacts through its own brain. */
	private List<Vector3> aimPoints(List<Player> players) {
		List<Vector3> out = new ArrayList<>();
		for (Player pl : players) {
			if (!GD.isInstanceValid(pl) || !pl.isCombat()) continue;
			out.add(pl.getAimTargetPosition());
		}
		return out;
	}

	/** Start (or restart) a ped's panic, heading along its footway AWAY from {@code from}. */
	private void scare(Ped p, Vector3 from) {
		if (p.flee <= 0.0) scaresTotal++;
		p.flee = panicSeconds;
		p.threat = from;
		double a = pointAt(p, p.along + 1.0).distanceTo(from);
		double b = pointAt(p, p.along - 1.0).distanceTo(from);
		p.dir = a >= b ? 1 : -1;
	}

	private void advance(Ped p, double dt) {
		double moved = (p.flee > 0.0 ? fleeSpeed : speed) * dt;
		p.along += p.dir * moved;
		walkedTotal += moved;
		double L = length(p);
		if (p.along >= L - 0.5) { p.along = Math.max(0.5, L - 0.5); p.dir = -1; }
		if (p.along <= 0.5) { p.along = 0.5; p.dir = 1; }
	}

	/** ONE engine write per ped per update: position and facing in a single transform. */
	private void place(Ped p) {
		Vector3 here = pointAt(p, p.along);
		Vector3 ahead = pointAt(p, p.along + p.dir * 1.0);
		double dx = ahead.getX() - here.getX();
		double dz = ahead.getZ() - here.getZ();
		double yaw = (Math.abs(dx) + Math.abs(dz) < 1e-6) ? 0.0 : Math.atan2(-dx, -dz);
		p.body.setGlobalPosition(new Vector3(here.getX(), here.getY() + lift, here.getZ()));
		p.body.setGlobalRotation(new Vector3(0.0, yaw, 0.0));
	}

	private Vector3 pointAt(Ped p, double s) {
		int n = p.cum.length;
		if (n == 0) return Vector3.Companion.getZERO();
		if (s <= 0) return p.path.get(0);
		if (s >= p.cum[n - 1]) return p.path.get(n - 1);
		int lo = 0, hi = n - 1;
		while (hi - lo > 1) {
			int mid = (lo + hi) >>> 1;
			if (p.cum[mid] <= s) lo = mid; else hi = mid;
		}
		double seg = p.cum[hi] - p.cum[lo];
		double f = seg < 1e-9 ? 0.0 : (s - p.cum[lo]) / seg;
		return p.path.get(lo).lerp(p.path.get(hi), f);
	}

	private double nearestPlayerDist(Ped p, List<Player> players) {
		if (players.isEmpty()) return Double.MAX_VALUE;
		Vector3 here = pointAt(p, p.along);
		double best = Double.MAX_VALUE;
		for (Player pl : players) {
			if (!GD.isInstanceValid(pl)) continue;
			Vector3 q = pl.getGlobalPosition();
			double dx = q.getX() - here.getX();
			double dz = q.getZ() - here.getZ();
			double d = Math.sqrt(dx * dx + dz * dz);
			if (d < best) best = d;
		}
		return best;
	}
}
