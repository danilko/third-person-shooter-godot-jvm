package com.openworld.world;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import com.openworld.util.MiniJson;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Camera3D;
import godot.api.FileAccess;
import godot.api.GeometryInstance3D;
import godot.api.Mesh;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.ResourceLoader;
import godot.api.Shader;
import godot.api.ShaderMaterial;
import godot.api.Texture2D;
import godot.core.AABB;
import godot.core.PackedFloat32Array;
import godot.core.PackedVector3Array;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * The FAR tier of the ambient crowd: every pedestrian no player is dealing with. A ped here is PLAIN JAVA STATE
 * -- a footway, a place on it, a pace, a clip -- and each body type is ONE {@link MultiMesh} animated in the
 * vertex shader from a baked vertex-animation texture ({@code tools/godot/bake_ped_vat.gd},
 * {@code assets/characters/crowd/ped_vat.gdshader}). So a ped costs no node, no skeleton, no AnimationPlayer and
 * no draw call of its own: the crowd is one buffer write per body type per frame.
 *
 * <p><b>Measured</b> ({@code tools/godot/bench_crowd.gd}, this PC, 2026-09-27): the previous far tier -- one
 * skinned body per ped with its own AnimationPlayer -- cost 4.8 / 18.4 / 61.2 ms a frame at 150 / 600 / 2000
 * peds, all of it CPU animation and skinning; as VAT instances 0.45 / 0.57 / 1.48 ms and one draw call. It was
 * also silently FROZEN: it stopped animating beyond 60 m and only ever existed beyond 80 m.
 *
 * <p><b>Promotion is a decision, not a ring</b> (PLAN.md 3.32). A ped becomes a full {@code AICharacter} only when
 * it must do what a light ped cannot: a player is within {@link #promoteDistance} (it can be bumped, looked at
 * closely), a player is AIMING at it, or a FIGHTER is scared. At most one promotion a frame, nearest first, and
 * {@link ZoneManager} holds the budgets -- a promotion is a few milliseconds of main-thread work (measured 3-4 ms),
 * and an uncapped ring promoted dozens in a few frames when a car drove into downtown.
 *
 * <p><b>Temperament</b>, from the ped's own hash: most FLEE from a gunshot, an explosion or a weapon being drawn,
 * some COWER where they stand, a few FIGHT back (promoted and armed by ZoneManager). Calm peds walk and now and
 * then stop to idle, use a phone or talk.
 *
 * <p><b>Local to each peer, never replicated</b> (the rule 3.11b set for cosmetic state). A client may not promote,
 * so inside {@link #promoteDistance} of its own player it HIDES its light peds and shows the host's replicated
 * walkers instead. <b>Accepted divergence:</b> a ped the host could not promote (budget full) is hidden on the
 * client and has no replicated body there.
 */
@Script(className = "PedCrowd")
public class PedCrowd extends Node3D {

	/** Where the per-body bakes are listed: every body of character_gaits.json that has a `<body>_vat.json`. */
	private static final String GAITS = "res://src/main/resources/com/openworld/character/anim/character_gaits.json";
	private static final String SHADER = "res://assets/characters/crowd/ped_vat.gdshader";
	private static final int FLOATS = 20;   // per instance: 3x4 transform, colour, custom data

	/** A walking pace (m/s). The same number {@code SidewalkWalkerController} glides at. */
	@Visible public double speed = 1.4;
	/** How far above the footway line a ped's origin rides. */
	@Visible public double lift = 0.02;
	/** Within this of a player a ped is PROMOTED (host / single player) or HIDDEN (client). */
	@Visible public double promoteDistance = 25.0;
	/** A full walker beyond this is handed back to the crowd (ZoneManager reads it). Hysteresis over promote. */
	@Visible public double demoteDistance = 40.0;
	/** How far a ped is DRAWN (culled per ped on the CPU: a MultiMesh fades as a whole). 0 = no limit. */
	@Visible public double drawDistance = 220.0;
	/** Kept for the control: false = the whole crowd walks with no stops. */
	@Visible public boolean idleStops = true;

	/** The light tier REACTS: a gunshot, an explosion or a weapon being DRAWN within {@link #panicRange} (and
	 *  inside the stimulus's own radius), or a player aiming at it. Off = the control. */
	@Visible public boolean reactions = true;
	@Visible public double panicRange = 120.0;
	@Visible public double panicSeconds = 8.0;
	/** A fleeing ped's pace (m/s): a run, on the sprint clip. */
	@Visible public double fleeSpeed = 4.5;
	/** A ped within this of a player's aim point, while that player is in combat, counts as aimed at. */
	@Visible public double aimedAtRadius = 2.0;
	/** Out of 100: how many peds cower instead of running, and how many fight back. The rest flee. */
	@Visible public int cowerPercent = 12;
	@Visible public int fightPercent = 5;

	/** Metres walked by the whole crowd -- a probe readout, so "are they actually moving" is measurable. */
	@Visible public double walkedTotal = 0.0;

	// ── the baked bodies (shared by every crowd) ──────────────────────────────────────────────────

	static final class Clip {
		final float row, frames, fps;
		Clip(double row, double frames, double fps) { this.row = (float) row; this.frames = (float) frames; this.fps = (float) fps; }
	}

	static final class Variant {
		String body;
		double weight = 1.0;
		Mesh mesh;
		ShaderMaterial material;
		Clip idle, walk, run, cower, phone, talk;
	}

	private static List<Variant> variants;
	private static int liveCrowds = 0;

	/** Every baked body, loaded once. Empty (and the crowd draws nothing) until one is baked. */
	static synchronized List<Variant> variants() {
		if (variants != null) return variants;
		variants = new ArrayList<>();
		Shader shader = ResourceLoader.INSTANCE.load(SHADER, "", ResourceLoader.CacheMode.REUSE) instanceof Shader s ? s : null;
		Object gaits = MiniJson.parse(FileAccess.getFileAsString(GAITS));
		if (shader == null || !(gaits instanceof Map<?, ?> g) || !(g.get("bodies") instanceof Map<?, ?> bodies)) {
			GD.pushError("PedCrowd: no shader or no gait table");
			return variants;
		}
		Map<?, ?> weights = g.get("crowd_weights") instanceof Map<?, ?> w ? w : Map.of();
		List<String> names = new ArrayList<>();
		for (Object k : bodies.keySet()) names.add(String.valueOf(k));
		Collections.sort(names);                       // a stable order: a ped's variant is its hash mod the count
		for (String body : names) {
			String metaPath = "res://assets/characters/" + body + "/" + body + "_vat.json";
			if (!FileAccess.fileExists(metaPath)) continue;
			if (!(MiniJson.parse(FileAccess.getFileAsString(metaPath)) instanceof Map<?, ?> m)) continue;
			Variant v = new Variant();
			v.body = body;
			if (weights.get(body) instanceof Number n) v.weight = Math.max(0.0, n.doubleValue());
			v.mesh = ResourceLoader.INSTANCE.load(String.valueOf(m.get("mesh")), "", ResourceLoader.CacheMode.REUSE) instanceof Mesh me ? me : null;
			Texture2D pos = ResourceLoader.INSTANCE.load(String.valueOf(m.get("positions")), "", ResourceLoader.CacheMode.REUSE) instanceof Texture2D t ? t : null;
			Texture2D atlas = ResourceLoader.INSTANCE.load(String.valueOf(m.get("atlas")), "", ResourceLoader.CacheMode.REUSE) instanceof Texture2D t ? t : null;
			if (v.mesh == null || pos == null || atlas == null) {
				GD.pushError("PedCrowd: " + body + "'s VAT bake is incomplete -- run tools/godot/bake_ped_vat.gd");
				continue;
			}
			v.material = new ShaderMaterial();
			v.material.setShader(shader);
			v.material.setShaderParameter("albedo_tex", atlas);
			v.material.setShaderParameter("vat_pos", pos);
			v.material.setShaderParameter("alpha_scissor", m.get("alpha_scissor") instanceof Number a ? a.doubleValue() : 0.5);
			Map<?, ?> clips = (Map<?, ?>) m.get("clips");
			v.idle = clip(clips, "idle");
			v.walk = clip(clips, "walk");
			v.run = clip(clips, "run");
			v.cower = clip(clips, "cower");
			v.phone = clip(clips, "phone");
			v.talk = clip(clips, "talk");
			if (v.walk == null) continue;
			if (v.idle == null) v.idle = v.walk;
			if (v.run == null) v.run = v.walk;
			if (v.cower == null) v.cower = v.idle;
			if (v.phone == null) v.phone = v.idle;
			if (v.talk == null) v.talk = v.idle;
			variants.add(v);
		}
		return variants;
	}

	private static Clip clip(Map<?, ?> clips, String key) {
		if (clips == null || !(clips.get(key) instanceof Map<?, ?> c)) return null;
		return new Clip(((Number) c.get("row")).doubleValue(), ((Number) c.get("frames")).doubleValue(),
				((Number) c.get("fps")).doubleValue());
	}

	// ── the peds ──────────────────────────────────────────────────────────────────────────────────

	private static final int WALK = 0, STOP = 1, FLEE = 2, COWER = 3;
	private static final int TEMPER_FLEE = 0, TEMPER_COWER = 1, TEMPER_FIGHT = 2;

	private static final class Ped {
		PackedVector3Array path;
		Vector3[] pts;
		double[] cum;
		double along;
		int dir;
		int variant;
		int slot;
		double pace;          // x speed, and x the walk clip's rate: stride and ground speed stay matched
		double scale;
		double start;         // shader time offset: every ped at its own place in its cycle
		int temper;
		int state = WALK;
		double timer;         // seconds left in STOP / FLEE / COWER, or until the next stop while walking
		Clip stopClip;
		boolean hidden;
		boolean wantsFight;
	}

	private final List<Ped> peds = new ArrayList<>();
	private final java.util.Random rng = new java.util.Random();
	private MultiMeshInstance3D[] layers = new MultiMeshInstance3D[0];
	private float[][] bufs = new float[0][];
	private int[] counts = new int[0];
	private final java.util.Set<StimulusManager.Stimulus> heard =
			java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<>());
	private int scaresTotal = 0;
	private int promotedTotal = 0;

	private ZoneManager owner;
	private Object ownerZone;

	/** Every crowd in the tree, so a shot can ask them (a crowd ped has no collider). */
	private static final List<PedCrowd> LIVE = new ArrayList<>();

	@Register
	@Override
	public void _ready() {
		LIVE.add(this);
		liveCrowds++;
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
		List<Variant> vs = variants();
		if (vs.isEmpty()) return;
		ensureLayers(vs.size());
		Ped p = new Ped();
		p.path = path;
		p.pts = new Vector3[path.getSize()];
		p.cum = new double[path.getSize()];
		for (int i = 0; i < p.pts.length; i++) p.pts[i] = path.get(i);
		for (int i = 1; i < p.cum.length; i++) p.cum[i] = p.cum[i - 1] + p.pts[i].distanceTo(p.pts[i - 1]);
		p.along = Math.max(0.5, Math.min(along, Math.max(0.5, length(p) - 0.5)));
		p.dir = dir >= 0 ? 1 : -1;
		p.variant = pickVariant(vs);
		p.pace = 0.9 + 0.2 * rng.nextDouble();
		p.scale = 0.96 + 0.08 * rng.nextDouble();
		p.start = -rng.nextDouble() * 10.0;
		int t = rng.nextInt(100);
		p.temper = t < fightPercent ? TEMPER_FIGHT : t < fightPercent + cowerPercent ? TEMPER_COWER : TEMPER_FLEE;
		p.timer = 15.0 + rng.nextDouble() * 45.0;
		p.slot = counts[p.variant]++;
		peds.add(p);
		growBuffer(p.variant);
	}

	/** A body by its crowd weight (character_gaits.json crowd_weights). */
	private int pickVariant(List<Variant> vs) {
		double total = 0.0;
		for (Variant v : vs) total += v.weight;
		double r = rng.nextDouble() * total;
		for (int i = 0; i < vs.size(); i++) {
			r -= vs.get(i).weight;
			if (r < 0.0) return i;
		}
		return vs.size() - 1;
	}

	private void ensureLayers(int n) {
		if (layers.length == n) return;
		List<Variant> vs = variants();
		layers = new MultiMeshInstance3D[n];
		bufs = new float[n][0];
		counts = new int[n];
		for (int i = 0; i < n; i++) {
			MultiMesh mm = new MultiMesh();
			mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);   // must precede instanceCount
			mm.setUseColors(true);
			mm.setUseCustomData(true);
			mm.setMesh(vs.get(i).mesh);
			MultiMeshInstance3D mmi = new MultiMeshInstance3D();
			mmi.setMultimesh(mm);
			mmi.setMaterialOverride(vs.get(i).material);
			mmi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
			mmi.setAsTopLevel(true);
			addChild(mmi);
			layers[i] = mmi;
		}
	}

	/** Grow a variant's buffer to hold its instances (doubling), re-sizing the MultiMesh with it. */
	private void growBuffer(int v) {
		if (bufs[v].length >= counts[v] * FLOATS) return;
		int cap = Math.max(8, Integer.highestOneBit(Math.max(1, counts[v] - 1)) << 1);
		float[] nb = new float[cap * FLOATS];
		System.arraycopy(bufs[v], 0, nb, 0, bufs[v].length);
		bufs[v] = nb;
		layers[v].getMultimesh().setInstanceCount(cap);
	}

	@Register public int pedCount() { return peds.size(); }

	/** How many peds are drawn right now (hidden = a client's promote ring; beyond drawDistance counts too). */
	@Register
	public int visiblePedCount() {
		int n = 0;
		for (Ped p : peds) if (!p.hidden) n++;
		return n;
	}

	/** Where every ped is (world), in order -- the probes' view of a crowd that has no nodes. */
	@Register
	public PackedVector3Array pedPositionsNow() {
		PackedVector3Array out = new PackedVector3Array();
		for (Ped p : peds) out.append(pointAt(p, p.along));
		return out;
	}

	/** The baked bodies this crowd draws, by name (a probe readout). */
	@Register
	public String bodiesNow() {
		StringBuilder sb = new StringBuilder();
		for (Variant v : variants()) sb.append(sb.length() == 0 ? "" : ",").append(v.body);
		return sb.toString();
	}

	@Register public double walkedTotalNow() { return walkedTotal; }

	/** How many peds are running from something right now (a probe readout). */
	@Register
	public int fleeingNow() {
		int n = 0;
		for (Ped p : peds) if (p.state == FLEE) n++;
		return n;
	}

	/** How many are cowering right now (a probe readout). */
	@Register
	public int coweringNow() {
		int n = 0;
		for (Ped p : peds) if (p.state == COWER) n++;
		return n;
	}

	@Register public int scaresNow() { return scaresTotal; }

	@Register public int promotedNow() { return promotedTotal; }

	/** Roll every ped's temperament again from the current shares (probes set a share after the zone spawned). */
	@Register
	public void rerollTemperNow() {
		for (Ped p : peds) {
			int t = rng.nextInt(100);
			p.temper = t < fightPercent ? TEMPER_FIGHT : t < fightPercent + cowerPercent ? TEMPER_COWER : TEMPER_FLEE;
		}
	}

	/** Remove every ped (zone unload). */
	@Register
	public void clearPeds() {
		peds.clear();
		for (int v = 0; v < layers.length; v++) {
			counts[v] = 0;
			if (GD.isInstanceValid(layers[v])) layers[v].getMultimesh().setVisibleInstanceCount(0);
		}
	}

	@Register
	@Override
	public void _exitTree() {
		clearPeds();
		LIVE.remove(this);
		liveCrowds--;
		// The baked bodies are static Godot resources: release them with the last crowd, or they are reported
		// as resources still in use at exit (IconRegistry's rule).
		if (liveCrowds <= 0) {
			liveCrowds = 0;
			synchronized (PedCrowd.class) { variants = null; }
		}
	}

	@Register
	@Override
	public void _physicsProcess(double delta) {
		tick(delta);
	}

	private void tick(double delta) {
		if (layers.length == 0) return;
		if (peds.isEmpty()) {
			// Still upload: the promotion that emptied the crowd left its last instance in the GPU buffer, and
			// returning here drew that ped for ever, animating in place beside the body it became (zb1).
			if (dirty) upload();
			return;
		}
		List<Player> players = PlayerRegistry.getPlayers();
		int np = 0;
		double[] px = new double[players.size()], pz = new double[players.size()];
		for (Player pl : players) {
			if (!GD.isInstanceValid(pl)) continue;
			Vector3 q = pl.getGlobalPosition();
			px[np] = q.getX();
			pz[np] = q.getZ();
			np++;
		}
		Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
		Vector3 eye = cam != null ? cam.getGlobalPosition() : null;
		boolean canPromote = owner != null && authoritative();
		if (reactions) hear();
		List<Vector3> aims = reactions ? aimPoints(players) : null;

		Ped promote = null;
		double promoteD = Double.MAX_VALUE;
		for (Ped p : peds) {
			Vector3 here = pointAt(p, p.along);
			if (aims != null) {
				for (Vector3 a : aims) {
					if (here.distanceTo(a) <= aimedAtRadius + 1.0) { scare(p, a); if (canPromote) p.wantsFight = true; break; }
				}
			}
			step(p, delta);
			here = pointAt(p, p.along);
			double d = nearest(here, px, pz, np);
			boolean need = d < promoteDistance || (p.wantsFight && d < panicRange);
			if (need && canPromote && d < promoteD) { promote = p; promoteD = d; }
			boolean hide = !canPromote && d < promoteDistance;
			if (!hide && drawDistance > 0.0 && eye != null && here.distanceTo(eye) > drawDistance) hide = true;
			p.hidden = hide;
			write(p, here);
		}
		// ONE promotion a frame, the nearest: a promotion is milliseconds of main-thread work.
		if (promote != null) {
			boolean fight = promote.wantsFight && promote.temper == TEMPER_FIGHT;
			if (owner.promoteSidewalkPed(ownerZone, promote.path, promote.along, promote.dir, fight,
					variants().get(promote.variant).body, panicLeft(promote))) {
				removePed(promote);
				promotedTotal++;
			} else {
				promote.wantsFight = false;        // refused (budget): it stays a ped and runs like the rest
			}
		}
		upload();
	}

	/** True when the buffers changed since the last upload outside a tick (a promotion by a shot or a blast). */
	private boolean dirty = false;

	private void upload() {
		dirty = false;
		for (int v = 0; v < layers.length; v++) {
			if (!GD.isInstanceValid(layers[v])) continue;
			MultiMesh mm = layers[v].getMultimesh();
			mm.setBuffer(new PackedFloat32Array(bufs[v]));
			mm.setVisibleInstanceCount(counts[v]);
		}
	}

	// ── Shot at from beyond the promote ring ────────────────────────────────────────────────────────

	/** A light ped a shot hit: where, and how far along the ray. */
	public record CrowdHit(PedCrowd crowd, Object ped, double distance, Vector3 point) { }

	/** A ped's body for a shot: an upright capsule this wide and this tall (x its own scale). */
	private static final double BODY_RADIUS = 0.28, BODY_HEIGHT = 1.62;

	/**
	 * The nearest light ped a ray from {@code origin} along unit {@code dir} passes through within
	 * {@code maxDist}, over every crowd -- a crowd ped has no collider, so a shot asks the crowds itself.
	 * Hidden peds (a client's promote ring) are skipped. Null = none.
	 */
	public static CrowdHit shoot(Vector3 origin, Vector3 dir, double maxDist) {
		CrowdHit best = null;
		for (PedCrowd c : LIVE) {
			if (!GD.isInstanceValid(c)) continue;
			for (Ped p : c.peds) {
				if (p.hidden) continue;
				Vector3 f = c.pointAt(p, p.along);
				double t = rayCapsule(origin, dir, f, BODY_HEIGHT * p.scale, BODY_RADIUS * p.scale);
				if (t >= 0.0 && t <= maxDist && (best == null || t < best.distance())) {
					best = new CrowdHit(c, p, t, origin.plus(dir.times(t)));
				}
			}
		}
		return best;
	}

	/**
	 * Promote the ped a shot hit, NOW (the budget is not asked: a shot has to land), and return its body for
	 * the damage. Authoritative peer only; null when this crowd cannot promote.
	 */
	public com.openworld.character.AICharacter promoteHit(CrowdHit hit) {
		if (!(hit.ped() instanceof Ped p) || owner == null || !authoritative() || !peds.contains(p)) return null;
		com.openworld.character.AICharacter ai = owner.promoteForShot(ownerZone, p.path, p.along, p.dir,
				variants().get(p.variant).body, panicLeft(p));
		if (ai != null) {
			removePed(p);
			promotedTotal++;
			if (dirty) upload();   // outside this crowd's tick: do not draw the ped beside its body for a frame
		}
		return ai;
	}

	/** Seconds of running this ped still has (0 = calm): a promotion must not change who runs. */
	private double panicLeft(Ped p) {
		return p.state == FLEE ? Math.max(0.0, p.timer) : 0.0;   // a body has no cower yet: it walks
	}

	/**
	 * Promote, NOW and whatever the budget, every light ped whose body comes within {@code radius} of the segment
	 * {@code a}-{@code b} -- a melee swing's reach, or a blast (a == b). A light ped has no collider, so a fist, a
	 * knife or a grenade could never reach it (zb1: "a pedestrian under attack does not become an AI"). At most
	 * {@code max} over every crowd, nearest first. Authoritative peer only; the bodies are returned for the damage.
	 */
	public static List<com.openworld.character.AICharacter> promoteNear(Vector3 a, Vector3 b, double radius, int max) {
		List<Object[]> found = new ArrayList<>();
		for (PedCrowd c : LIVE) {
			if (!GD.isInstanceValid(c) || c.owner == null || !c.authoritative()) continue;
			for (Ped p : c.peds) {
				if (p.hidden) continue;
				Vector3 f = c.pointAt(p, p.along);
				double d = CrowdShot.segmentToBody(a.getX(), a.getY(), a.getZ(), b.getX(), b.getY(), b.getZ(),
						f.getX(), f.getY(), f.getZ(), BODY_HEIGHT * p.scale);
				if (d <= radius + BODY_RADIUS * p.scale) found.add(new Object[] { c, p, d });
			}
		}
		found.sort((x, y) -> Double.compare((double) x[2], (double) y[2]));
		List<com.openworld.character.AICharacter> out = new ArrayList<>();
		for (Object[] o : found) {
			if (out.size() >= max) break;
			PedCrowd c = (PedCrowd) o[0];
			Ped p = (Ped) o[1];
			com.openworld.character.AICharacter ai = c.promoteHit(new CrowdHit(c, p, 0.0, c.pointAt(p, p.along)));
			if (ai != null) out.add(ai);
		}
		return out;
	}

	/** Probe readout: shoot a ray at the crowds the way FirearmItem does. Returns where the hit ped's new body
	 *  stands, or (0, -10000, 0) when nothing was hit. */
	@Register
	public Vector3 shootNow(Vector3 origin, Vector3 dir, double range) {
		CrowdHit hit = shoot(origin, dir.normalized(), range);
		com.openworld.character.AICharacter ai = hit != null ? hit.crowd().promoteHit(hit) : null;
		return ai != null ? ai.getGlobalPosition() : new Vector3(0, -10000, 0);
	}

	private static double rayCapsule(Vector3 o, Vector3 d, Vector3 foot, double height, double radius) {
		return CrowdShot.rayBody(o.getX(), o.getY(), o.getZ(), d.getX(), d.getY(), d.getZ(),
				foot.getX(), foot.getY(), foot.getZ(), height, radius);
	}

	/** Advance one ped's state and place by dt. */
	private void step(Ped p, double dt) {
		double moved = 0.0;
		switch (p.state) {
			case WALK -> {
				moved = speed * p.pace * dt;
				p.timer -= dt;
				if (idleStops && p.timer <= 0.0) {
					p.state = STOP;
					Variant v = variants().get(p.variant);
					int k = rng.nextInt(3);
					p.stopClip = k == 0 ? v.phone : k == 1 ? v.talk : v.idle;
					p.timer = 4.0 + rng.nextDouble() * 8.0;
				}
			}
			case STOP -> {
				p.timer -= dt;
				if (p.timer <= 0.0) { p.state = WALK; p.timer = 20.0 + rng.nextDouble() * 50.0; }
			}
			case FLEE -> {
				moved = fleeSpeed * dt;
				p.timer -= dt;
				if (p.timer <= 0.0) { p.state = WALK; p.timer = 20.0 + rng.nextDouble() * 50.0; p.wantsFight = false; }
			}
			case COWER -> {
				p.timer -= dt;
				if (p.timer <= 0.0) { p.state = WALK; p.timer = 20.0 + rng.nextDouble() * 50.0; p.wantsFight = false; }
			}
			default -> { }
		}
		if (moved > 0.0) {
			p.along += p.dir * moved;
			walkedTotal += moved;
			double L = length(p);
			if (p.along >= L - 0.5) { p.along = Math.max(0.5, L - 0.5); p.dir = -1; }
			if (p.along <= 0.5) { p.along = 0.5; p.dir = 1; }
		}
	}

	/** One ped's instance: transform (facing its travel), tint, and the clip it plays. */
	private void write(Ped p, Vector3 here) {
		float[] b = bufs[p.variant];
		int o = p.slot * FLOATS;
		if (p.hidden) {
			for (int i = 0; i < 12; i++) b[o + i] = 0f;   // a zero basis draws nothing
			return;
		}
		Vector3 ahead = pointAt(p, p.along + p.dir * 1.0);
		double dx = ahead.getX() - here.getX();
		double dz = ahead.getZ() - here.getZ();
		double yaw = (Math.abs(dx) + Math.abs(dz) < 1e-6) ? 0.0 : Math.atan2(-dx, -dz);
		float c = (float) (Math.cos(yaw) * p.scale), s = (float) (Math.sin(yaw) * p.scale), k = (float) p.scale;
		// row-major 3x4: [xx xy xz ox | yx yy yz oy | zx zy zz oz] for a yaw about +Y
		b[o] = c;   b[o + 1] = 0f; b[o + 2] = s;  b[o + 3] = (float) here.getX();
		b[o + 4] = 0f; b[o + 5] = k; b[o + 6] = 0f; b[o + 7] = (float) (here.getY() + lift);
		b[o + 8] = -s; b[o + 9] = 0f; b[o + 10] = c; b[o + 11] = (float) here.getZ();
		b[o + 12] = 1f; b[o + 13] = 1f; b[o + 14] = 1f; b[o + 15] = 0f;
		Variant v = variants().get(p.variant);
		Clip clip;
		float rate = 1f;
		switch (p.state) {
			case STOP -> clip = p.stopClip;
			case FLEE -> clip = v.run;
			case COWER -> clip = v.cower;
			default -> { clip = v.walk; rate = (float) p.pace; }
		}
		b[o + 16] = clip.row;
		b[o + 17] = clip.frames;
		b[o + 18] = (float) p.start;
		b[o + 19] = clip.fps * rate;
	}

	/** A promoted ped leaves the buffer: the last instance of its body type moves into its slot. */
	private void removePed(Ped p) {
		int v = p.variant;
		int last = --counts[v];
		if (p.slot != last) {
			for (Ped q : peds) {
				if (q.variant == v && q.slot == last) {
					System.arraycopy(bufs[v], last * FLOATS, bufs[v], p.slot * FLOATS, FLOATS);
					q.slot = p.slot;
					break;
				}
			}
		}
		peds.remove(p);
		dirty = true;
	}

	/** True where this peer decides what exists: single player, or the host. */
	private boolean authoritative() {
		Node n = getNodeOrNull("/root/NetworkManager");
		NetworkManager net = n instanceof NetworkManager m ? m : null;
		return net == null || !net.isNetworked() || net.isServer();
	}

	private double length(Ped p) { return p.cum.length == 0 ? 0.0 : p.cum[p.cum.length - 1]; }

	/**
	 * React to every stimulus not yet heard. By IDENTITY, not by timestamp: StimulusManager stamps with a clock
	 * that advances in _process, so when two physics ticks run in one frame a stimulus posted between them can
	 * carry the same timestamp as one already heard, and "newer than the last" would skip it.
	 */
	private void hear() {
		StimulusManager sm = StimulusManager.get();
		if (sm == null) return;
		List<StimulusManager.Stimulus> live = sm.getStimuli();
		for (StimulusManager.Stimulus st : live) {
			if (!heard.add(st)) continue;
			if (st.type != StimulusManager.Type.GUNSHOT && st.type != StimulusManager.Type.EXPLOSION
					&& st.type != StimulusManager.Type.WEAPON_DRAWN) continue;
			double r = Math.min(panicRange, st.radius);
			for (Ped p : peds) {
				if (pointAt(p, p.along).distanceTo(st.origin) <= r) scare(p, st.origin);
			}
		}
		if (heard.size() > live.size()) heard.retainAll(identity(live).keySet());   // an IdentityHashMap key set: contains() by identity
	}

	private static java.util.IdentityHashMap<StimulusManager.Stimulus, Boolean> identity(List<StimulusManager.Stimulus> l) {
		java.util.IdentityHashMap<StimulusManager.Stimulus, Boolean> m = new java.util.IdentityHashMap<>();
		for (StimulusManager.Stimulus st : l) m.put(st, Boolean.TRUE);
		return m;
	}

	/** Where each player in combat is aiming. */
	private List<Vector3> aimPoints(List<Player> players) {
		List<Vector3> out = new ArrayList<>();
		for (Player pl : players) {
			if (!GD.isInstanceValid(pl) || !pl.isCombat()) continue;
			out.add(pl.getAimTargetPosition());
		}
		return out;
	}

	/** Scared: run AWAY along the footway, or cower where it stands, or (a fighter) ask to be promoted. */
	private void scare(Ped p, Vector3 from) {
		if (p.state != FLEE && p.state != COWER) scaresTotal++;
		if (p.temper == TEMPER_COWER) {
			p.state = COWER;
		} else {
			p.state = FLEE;
			double a = pointAt(p, p.along + 1.0).distanceTo(from);
			double b = pointAt(p, p.along - 1.0).distanceTo(from);
			p.dir = a >= b ? 1 : -1;
			if (p.temper == TEMPER_FIGHT) p.wantsFight = true;
		}
		p.timer = panicSeconds;
	}

	private Vector3 pointAt(Ped p, double s) {
		int n = p.cum.length;
		if (n == 0) return Vector3.Companion.getZERO();
		if (s <= 0) return p.pts[0];
		if (s >= p.cum[n - 1]) return p.pts[n - 1];
		int lo = 0, hi = n - 1;
		while (hi - lo > 1) {
			int mid = (lo + hi) >>> 1;
			if (p.cum[mid] <= s) lo = mid; else hi = mid;
		}
		double seg = p.cum[hi] - p.cum[lo];
		double f = seg < 1e-9 ? 0.0 : (s - p.cum[lo]) / seg;
		Vector3 a = p.pts[lo], b = p.pts[hi];
		return new Vector3(a.getX() + (b.getX() - a.getX()) * f, a.getY() + (b.getY() - a.getY()) * f,
				a.getZ() + (b.getZ() - a.getZ()) * f);
	}

	private static double nearest(Vector3 here, double[] px, double[] pz, int np) {
		double best = Double.MAX_VALUE;
		for (int i = 0; i < np; i++) {
			double dx = px[i] - here.getX(), dz = pz[i] - here.getZ();
			double d = Math.sqrt(dx * dx + dz * dz);
			if (d < best) best = d;
		}
		return best;
	}
}
