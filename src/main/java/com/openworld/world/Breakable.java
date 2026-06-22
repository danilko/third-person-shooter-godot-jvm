package com.openworld.world;

import com.openworld.net.NetworkManager;
import com.openworld.world.manager.ParticleManager;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.StringName;
import godot.core.StringNames;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A destructible piece of world geometry — breakable glass, a flimsy wall panel, a fence (PLAN.md I2).
 *
 * <p><b>Why this and not a portal/interior load.</b> I2 buildings are ordinary collision geometry
 * placed in the open world (the PUBG / modern-GTA model), not a separate interior cell — so you can
 * shoot in/out through windows and AI can path in/out through doors with no special code. A
 * {@code Breakable} is the one genuinely-new mechanic that layers on top of that: a window or wall
 * panel that takes bullet/explosion damage and, once destroyed, stops blocking — its collider is
 * disabled so movement, line-of-sight, and gunfire pass through the hole.
 *
 * <p>It extends {@link HittableBody} so it already resolves a {@link SurfaceType} for impact particles
 * (set {@code surfaceType} to e.g. {@code STONE}/{@code WOOD}; "GLASS" can be added to
 * {@link SurfaceType} later). {@link com.openworld.world.manager.ImpactManager} routes bullet damage
 * here exactly as it already routes detonation to {@code Detonatable} — see {@code processHit}.
 *
 * <p><b>Authority &amp; replication.</b> Damage accumulation is host-authoritative: a non-server peer
 * never breaks from its own predicted bullets ({@link #applyDamage} early-returns there). When the
 * host breaks one it rides the existing reliable world-event seam
 * ({@code GameManager.WORLD_EVENT_BREAKABLE} via {@link NetworkManager#broadcastWorldEvent}), keyed by
 * {@link #breakableId}; clients apply it cosmetically through {@code GameManager.applyBreakableState},
 * and a late-joiner catches up via {@code NetworkManager.sendBaselineBreakables}. Set a stable
 * {@code breakableId} in the editor for anything networked (the node-path fallback is fine only for
 * single-player or strictly-identical scene layouts).
 *
 * <p><b>Scene convention</b> (see {@code Breakable.tscn}): this node is the {@code StaticBody3D}. On
 * break it disables every child {@link CollisionShape3D}, hides any child named {@code "IntactVisual"},
 * and shows any child named {@code "BrokenVisual"} (optional shattered mesh). Restore reverses it.
 */
@RegisterClass(className = "Breakable")
public class Breakable extends HittableBody {

	public static final String BREAKABLE_GROUP = "breakable";

	/** Stable id used as the replication key. Set this in the editor for networked scenes. */
	@Export @RegisterProperty public String breakableId = "";

	/** Hit points; depleted by {@link #applyDamage}. */
	@Export @RegisterProperty public float health = 30.0f;

	/** Seconds after breaking before it auto-restores (0 = never — restore via story/mission instead). Host-authoritative. */
	@Export @RegisterProperty public float restoreDelay = 0.0f;

	/** Emit a debris particle burst (this body's {@code surfaceType}) when it breaks. */
	@Export @RegisterProperty public boolean spawnDebris = true;

	/**
	 * Minimum single-hit damage that counts toward breaking. Hits below this are ignored entirely, so a
	 * tougher pane/door shrugs off weak attacks (fists / light melee) and only yields to real firepower
	 * (bullets, explosions, heavy melee). Default {@code 0} = any damage applies (current behaviour).
	 */
	@Export @RegisterProperty public float breakMinDamage = 0.0f;

	private float currentHealth;
	private boolean broken;
	private double restoreTimer;
	private ParticleManager particleManager;

	@RegisterFunction
	@Override
	public void _ready() {
		addToGroup(new StringName(BREAKABLE_GROUP));
		if (breakableId == null || breakableId.isEmpty()) breakableId = getPath().getPath();
		currentHealth = health;
		setPhysicsProcess(false); // only ticks while a restore is scheduled
	}

	/**
	 * Authority-side damage from {@link com.openworld.world.manager.ImpactManager#processHit}. Accumulates
	 * toward the break threshold; a non-server peer ignores it (the host owns the break and replicates it).
	 */
	public void applyDamage(float amount, Vector3 attackerPos) {
		if (broken) return;
		if (amount < breakMinDamage) return; // too weak to count (fists / light melee bounce off)
		NetworkManager net = networkManager();
		if (net != null && net.isNetworked() && !net.isServer()) return;
		currentHealth -= amount;
		if (currentHealth <= 0.0f) breakNow(true);
	}

	/**
	 * Break it now. {@code broadcast} true on the authority (also replicates over the world-event seam);
	 * false when applying a host-confirmed break on a client. Idempotent.
	 */
	public void breakNow(boolean broadcast) {
		if (broken) return;
		broken = true;
		// Toggling collision must happen outside the physics query flush (ImpactManager runs mid-physics).
		callDeferred(StringNames.toGodotName("applyBrokenVisual"));
		if (spawnDebris) emitDebris();
		if (restoreDelay > 0.0f) { restoreTimer = restoreDelay; setPhysicsProcess(true); }
		if (broadcast) broadcastState(1.0f);
	}

	/**
	 * Restore it to intact. {@code broadcast} true on the authority. Resets health. Idempotent.
	 */
	public void restore(boolean broadcast) {
		if (!broken) return;
		broken = false;
		currentHealth = health;
		restoreTimer = 0.0;
		setPhysicsProcess(false);
		callDeferred(StringNames.toGodotName("applyIntactVisual"));
		if (broadcast) broadcastState(0.0f);
	}

	/** True if currently broken (collider disabled / hole open). */
	public boolean isBroken() { return broken; }

	@RegisterFunction
	@Override
	public void _physicsProcess(double delta) {
		if (restoreTimer <= 0.0) return; // only set while a restore is pending on the authority
		restoreTimer -= delta;
		if (restoreTimer <= 0.0) restore(true);
	}

	// ── Visual / collision toggling (deferred — safe outside the physics query flush) ─────────────

	@RegisterFunction
	public void applyBrokenVisual() { setIntactState(false); }

	@RegisterFunction
	public void applyIntactVisual() { setIntactState(true); }

	private void setIntactState(boolean intact) {
		for (Node child : getChildren()) {
			if (child instanceof CollisionShape3D cs) {
				cs.setDisabled(!intact);
			} else if (child instanceof Node3D vis) {
				// "BrokenVisual" is the optional shattered look shown only while broken; every other
				// child node (the intact mesh — a MeshInstance3D, a CSGBox3D, whatever it is named) is
				// hidden on break and shown again on restore. Hiding by type rather than by the single
				// name "IntactVisual" so any visual under the body disappears with the hole.
				if ("BrokenVisual".equals(vis.getName().toString())) vis.setVisible(!intact);
				else vis.setVisible(intact);
			}
		}
	}

	// ── Helpers ───────────────────────────────────────────────────────────────────────────────────

	private void emitDebris() {
		ParticleManager pm = getParticleManager();
		if (pm != null) pm.spawn(getSurfaceType(), getGlobalPosition());
	}

	private ParticleManager getParticleManager() {
		if (particleManager == null && getTree() != null) {
			Node found = getTree().getFirstNodeInGroup("particle_manager");
			if (found instanceof ParticleManager pm) particleManager = pm;
		}
		return particleManager;
	}

	private void broadcastState(float brokenValue) {
		NetworkManager net = networkManager();
		if (net != null) net.broadcastWorldEvent(
				com.openworld.game.GameManager.WORLD_EVENT_BREAKABLE, breakableId, brokenValue);
	}

	private NetworkManager networkManager() {
		Node n = getNodeOrNull("/root/NetworkManager");
		return n instanceof NetworkManager net ? net : null;
	}
}
