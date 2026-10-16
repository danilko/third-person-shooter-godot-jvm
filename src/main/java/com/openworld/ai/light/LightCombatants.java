package com.openworld.ai.light;

import com.openworld.ai.AIBlackboard;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.game.EnforcementDispatch;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.data.Tables;
import com.openworld.game.encounter.Loadouts;
import com.openworld.net.NetworkManager;
import com.openworld.util.CollisionLayers;
import com.openworld.world.SpatialEntityGrid;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.NavigationServer3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicsRayQueryParameters3D;
import godot.core.PackedVector3Array;
import godot.core.RID;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The LIGHT COMBATANT tier (PLAN.md 2.3 / F8; docs/game-systems.md "The light combatant tier and the AI
 * blackboard"): hostile bodies with no nodes at all -- plain Java state stepped by {@link LightSim}, drawn by the
 * crowd's vertex-animation shader, one {@code MultiMesh} per (body, outfit) and per (body, weapon). They approach,
 * take positions, hold back and aim, but <b>never deal damage</b>: the nearest of them, the ranged ones with a clear
 * line, and the ones hit by a non-lethal bullet are PROMOTED to full {@link AICharacter}s under {@link #fullBudget},
 * carrying their {@link AIBlackboard}, hit points and look; a promoted body that has been calm and far for a while is
 * demoted back. One node per world, made on first use ({@link #ensure}); the host simulates, clients draw what it
 * sends (MSG_LIGHT_BATCH).
 */
@Script(className = "LightCombatants")
public class LightCombatants extends Node3D {

    // ── tuning (probe-settable; a density level writes cap / fullBudget) ──
    /** Most light combatants at once (the tier refuses a spawn past it). */
    @Visible public int cap = 80;   // the World density level's light_cap when one is applied
    /** Full bodies promoted FROM this tier at once. */
    @Visible public int fullBudget = 8;   // the level's light_full_budget when one is applied
    /** A non-lethal hit promotes at once, the budget ignored, up to budget + this. */
    @Visible public int hitCeilingExtra = 4;
    /** A promoted body is demoted after this long with no target (s), unhurt for {@link #demoteUnhurtSeconds}, and
     *  beyond {@link #demoteDistance} of every player. */
    @Visible public double demoteCalmSeconds = 10.0, demoteUnhurtSeconds = 20.0, demoteDistance = 40.0;
    /** How far a light combatant looks for a target (m). */
    @Visible public double detectRange = 80.0;
    /** Not drawn beyond this from the camera (m). */
    @Visible public double drawDistance = 250.0;
    /** Line-of-sight tests a tick (the ranged shooters' promotion question). */
    @Visible public int sightTestsPerTick = 2;
    /** Off = the control: every light spawn is made a full body at once (probe_light_tier --control). */
    @Visible public boolean lightTier = true;

    /** Off = the measuring control: the tier simulates but draws nothing (attributes its GPU cost). */
    @Visible public boolean drawBodies = true;

    /** Lifetime readouts. */
    @Visible public int promotedTotal, demotedTotal, killedInTier, refusedTotal;

    private static final double RETARGET_SECONDS = 0.5;

    /** One light combatant's engine-side half (the sim holds the rest). */
    static final class Extra {
        final LightSim.Agent a;
        final AIBlackboard bb;
        final LightLooks.Body body;
        final LightLooks.WeaponLook weapon;
        final double phase;
        Character target;
        double retargetIn;
        AICharacter full;
        double calm;
        // a client's copy: where the host last said it is (drawn smoothed toward it)
        double netX, netY, netZ, netYaw;
        boolean seen;
        Extra(LightSim.Agent a, AIBlackboard bb, LightLooks.Body body, LightLooks.WeaponLook weapon, double phase) {
            this.a = a; this.bb = bb; this.body = body; this.weapon = weapon; this.phase = phase;
        }
    }

    final LightSim sim;
    final Map<Integer, Extra> extras = new HashMap<>();
    private final Map<String, LightLooks.Layer> layers = new HashMap<>();
    private final java.util.Random rng = new java.util.Random(0x11647);
    private int sightCursor = 0;
    private RID navMap;

    private static LightCombatants instance;

    /** The host's World density level's numbers (QualitySettings.applyDensity; -1 = not applied: the exports' own). */
    private static int densityCap = -1, densityBudget = -1;

    /** QualitySettings: the host's level (game/density.json light_cap / light_full_budget), now and for a tier made later. */
    public static void applyDensity(int lightCap, int fullBudget) {
        densityCap = lightCap;
        densityBudget = fullBudget;
        LightCombatants t = get();
        if (t != null) { t.cap = lightCap; t.fullBudget = fullBudget; }
    }

    public LightCombatants() {
        if (densityCap >= 0) cap = densityCap;
        if (densityBudget >= 0) fullBudget = densityBudget;
        sim = new LightSim(new LightSim.Params(), new LightSim.Ground() {
            @Override public double[] path(double fx, double fy, double fz, double tx, double ty, double tz) { return navPath(fx, fy, fz, tx, ty, tz); }
            @Override public double[] snap(double x, double y, double z) { return navSnap(x, y, z); }
        });
    }

    /** The world's tier, or null when none was made yet. */
    public static LightCombatants get() { return instance != null && GD.isInstanceValid(instance) ? instance : null; }

    /** The world's tier, made under the current scene on first use. */
    public static LightCombatants ensure(Node ctx) {
        LightCombatants t = get();
        if (t != null) return t;
        if (ctx == null || ctx.getTree() == null || ctx.getTree().getCurrentScene() == null) return null;
        t = new LightCombatants();
        t.setName(new StringName("LightCombatants"));
        ctx.getTree().getCurrentScene().addChild(t);
        return t;
    }

    @Register
    @Override
    public void _ready() { instance = this; }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        reportLoad(0);
        extras.clear();
    }

    /** The tuning the sim reads (probes set it). */
    public LightSim.Params params() { return sim.params; }

    // ── spawning ────────────────────────────────────────────────────────────────────────────────

    /**
     * A light combatant at {@code at}, under these orders. The blackboard's LOOK is completed here if it is empty
     * (a body rolled for its side, the loadout's weapon), so the full body it may become wears the same. Returns its
     * id, or 0 when the tier is full (or the control spawned a full body instead: see {@link #lightTier}).
     */
    public int spawn(AIBlackboard bb, Vector3 at, double hp, int style) {
        if (bb == null || at == null) return 0;
        if (!authoritative()) return 0;
        if (sim.aliveCount() + promotedNow() >= cap) return 0;
        Loadouts lo = Tables.LOADOUTS.get();
        Loadouts.Loadout l = lo != null ? lo.get(bb.loadout) : null;
        if (bb.side.isEmpty()) bb.side = l != null ? l.sideOr(bb.faction) : bb.faction;
        if (bb.faction.isEmpty()) bb.faction = bb.side;
        EnforcementDispatch ed = EnforcementDispatch.get();
        if (bb.body.isEmpty() && ed != null) {
            String[] look = ed.lookFor(bb.side);
            bb.body = look[0];
            if (bb.outfit.isEmpty()) bb.outfit = look[1];
        }
        if (bb.outfit.isEmpty() && l != null && l.outfit() != null) bb.outfit = l.outfit();
        if (bb.weapon.isEmpty() && l != null) bb.weapon = l.weapon(rng.nextDouble());
        LightLooks.Body body = LightLooks.body(bb.body, rng.nextDouble());
        if (body == null) return 0;
        bb.body = body.name;
        LightLooks.WeaponLook w = LightLooks.weapons().get(bb.weapon);
        if (!lightTier) {
            // the control: the same member as a full body, now
            AICharacter ai = ed != null ? ed.spawnPlacedAs(bb, l, at, "") : null;
            if (ai != null) ai.blackboard = bb;
            return 0;
        }
        LightSim.Agent a = sim.add(w != null && w.ranged() ? LightSim.RANGED : LightSim.MELEE,
                at.getX(), at.getY(), at.getZ(), hp);
        a.style = style;
        if (bb.holdPoint != null) {
            a.hasHold = true;
            a.holdX = bb.holdPoint.getX(); a.holdY = bb.holdPoint.getY(); a.holdZ = bb.holdPoint.getZ();
            a.leash = bb.holdLeash;
        }
        a.yaw = rng.nextDouble() * Math.PI * 2;
        Extra e = new Extra(a, bb, body, w, rng.nextDouble() * 10.0);
        e.retargetIn = 0.0;
        extras.put(a.id, e);
        return a.id;
    }

    // ── the tick ────────────────────────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (!authoritative()) { clientTick(delta); draw(); return; }
        if (extras.isEmpty()) { draw(); sendBatch(delta); return; }
        long t0 = System.nanoTime();
        try { tickHost(delta); } finally { tickNanos += System.nanoTime() - t0; ticks++; }
    }

    /** Readouts: time spent in the tier's own tick, in its nav path / snap requests, ticks (statsNow's ms columns). */
    private long tickNanos, pathNanos, snapNanos, ticks;

    private void tickHost(double delta) {
        List<Player> players = PlayerRegistry.getPlayers();
        double[] px = new double[players.size()], pz = new double[players.size()];
        int np = 0;
        for (Player p : players) {
            if (!GD.isInstanceValid(p)) continue;
            Vector3 q = p.getGlobalPosition();
            px[np] = q.getX(); pz[np] = q.getZ(); np++;
        }
        sim.setPlayers(px, pz, np);
        for (Extra e : extras.values()) {
            if (!e.a.alive()) continue;
            e.retargetIn -= delta;
            if (e.retargetIn <= 0 || (e.target != null && (!GD.isInstanceValid(e.target) || !e.target.isAlive()))) {
                e.target = findTarget(e);
                e.retargetIn = RETARGET_SECONDS + (e.a.id % 5) * 0.05;
            }
            if (e.target != null && GD.isInstanceValid(e.target)) {
                Vector3 t = e.target.getGlobalPosition();
                e.a.hasTarget = true; e.a.tx = t.getX(); e.a.ty = t.getY(); e.a.tz = t.getZ();
            } else {
                e.a.hasTarget = false;
                e.target = null;
            }
        }
        sightTests();
        sim.step(delta);
        promoteOne();
        watchPromoted(delta, px, pz, np);
        sweep();
        draw();
        sendBatch(delta);
        reportLoad(promotedNow());
    }

    /** The full bodies it stands up are COMBAT load: the ambient crowd and traffic make room for them (ZoneManager's
     *  balancing, PLAN.md 2.3 step 8). */
    private void reportLoad(int bodies) {
        if (getNodeOrNull("/root/ZoneManager") instanceof com.openworld.world.ZoneManager zm) zm.setCombatLoad("light", bodies);
    }

    /** The nearest hostile character within {@link #detectRange} (a pinned one first). */
    private Character findTarget(Extra e) {
        Vector3 here = new Vector3(e.a.x, e.a.y, e.a.z);
        List<Node> found = new ArrayList<>();
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) grid.queryRadius(here, (float) detectRange, found);
        else for (Player p : PlayerRegistry.getPlayers()) found.add(p);
        Character best = null;
        double bestD = Double.MAX_VALUE;
        for (Node n : found) {
            if (!(n instanceof Character c) || !GD.isInstanceValid(c) || !c.isAlive()) continue;
            String id = c.characterInfo != null ? c.characterInfo.characterId : "";
            if (!e.bb.pinnedTarget.isEmpty() && e.bb.pinnedTarget.equals(id)) return c;
            if (!hostile(e.bb, c)) continue;
            double d = c.getGlobalPosition().distanceTo(here);
            if (d < bestD && d <= detectRange) { bestD = d; best = c; }
        }
        return best;
    }

    static boolean hostile(AIBlackboard bb, Character c) {
        if (bb.huntsPlayers && c instanceof Player) return true;
        String tf = c.characterInfo != null && c.characterInfo.faction != null ? c.characterInfo.faction : "";
        return Faction.areHostile(bb.faction, tf) && com.openworld.game.Hostility.mayTarget(bb.faction, c);
    }

    /** Ray-test a few ranged holders a tick: does it see its target? (the shooters' promotion question) */
    private void sightTests() {
        List<Extra> holders = new ArrayList<>();
        for (Extra e : extras.values())
            if (e.a.alive() && e.a.kind == LightSim.RANGED && e.a.state == LightSim.HOLD && e.target != null) holders.add(e);
        if (holders.isEmpty() || getWorld3d() == null) return;
        var space = getWorld3d().getDirectSpaceState();
        for (int k = 0; k < Math.min(sightTestsPerTick, holders.size()); k++) {
            Extra e = holders.get((sightCursor + k) % holders.size());
            Vector3 from = new Vector3(e.a.x, e.a.y + 1.5, e.a.z);
            Vector3 to = e.target.getGlobalPosition().plus(new Vector3(0, 1.2, 0));
            var q = PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD,
                    new godot.core.VariantArray<>(RID.class));
            e.a.lineOfSight = space.intersectRay(q).isEmpty();
        }
        sightCursor += sightTestsPerTick;
    }

    /** One promotion a tick, the most pressing first, under the budget. */
    private void promoteOne() {
        Extra pick = null;
        double pickD = Double.MAX_VALUE;
        for (Extra e : extras.values()) {
            if (!e.a.wantsPromotion || !e.a.alive()) continue;
            double d = Math.min(e.a.nearestPlayer, e.a.hasTarget ? LightSim.plan(e.a.x, e.a.z, e.a.tx, e.a.tz) : Double.MAX_VALUE);
            if (d < pickD) { pickD = d; pick = e; }
        }
        if (pick == null) return;
        if (promotedNow() >= effectiveBudget() || promote(pick) == null) {
            sim.refused(pick.a);
            refusedTotal++;
        }
    }

    /** The budget after the enforcement balancing: the dispatch's live bodies share the same frame. */
    int effectiveBudget() { return fullBudget; }

    /** A full body for this light combatant now; null when it could not be made. */
    AICharacter promote(Extra e) {
        EnforcementDispatch ed = EnforcementDispatch.get();
        if (ed == null) return null;
        Loadouts lo = Tables.LOADOUTS.get();
        AICharacter ai = ed.spawnPlacedAs(e.bb, lo != null ? lo.get(e.bb.loadout) : null,
                new Vector3(e.a.x, e.a.y, e.a.z), "light:" + e.a.id);
        if (ai == null) return null;
        ai.blackboard = e.bb;
        if (ai.healthNode != null && e.a.hp < ai.healthNode.maxHealth) ai.healthNode.applyReplicatedHealth((float) e.a.hp);
        sim.promoted(e.a);
        e.full = ai;
        e.calm = 0;
        promotedTotal++;
        return ai;
    }

    /** Promoted bodies: a dead one takes its light one with it; a calm, far, unhurt one goes back to the tier. */
    private void watchPromoted(double delta, double[] px, double[] pz, int np) {
        for (Extra e : extras.values()) {
            if (e.full == null) continue;
            if (!GD.isInstanceValid(e.full) || e.full.isDead()) { sim.lost(e.a); e.full = null; continue; }
            // calm = nothing to fight within reach: no target, or one it is still "chasing" from past detect range (a
            // full AI keeps its target for a while after losing it -- measured: one hunted a player 260 m away)
            Character t = e.full.getTarget();
            boolean idle = t == null || !GD.isInstanceValid(t)
                    || t.getGlobalPosition().distanceTo(e.full.getGlobalPosition()) > detectRange;
            e.calm = idle ? e.calm + delta : 0.0;
            if (e.calm < demoteCalmSeconds) continue;
            if (e.full.healthNode != null && e.full.healthNode.hurtWithin(demoteUnhurtSeconds)) continue;
            Vector3 at = e.full.getGlobalPosition();
            double near = Double.MAX_VALUE;
            for (int i = 0; i < np; i++) near = Math.min(near, LightSim.plan(at.getX(), at.getZ(), px[i], pz[i]));
            if (near <= demoteDistance) continue;
            double hp = e.full.healthNode != null ? e.full.healthNode.getCurrentHealth() : e.a.hp;
            sim.demote(e.a, at.getX(), at.getY(), at.getZ(), hp);
            e.a.yaw = e.full.getGlobalRotation().getY();
            despawn(e.full);
            e.full = null;
            demotedTotal++;
        }
    }

    private void despawn(AICharacter ai) {
        if (ai.weaponController != null) ai.weaponController.silenceAudio();
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && ai.getCharacterInfo() != null)
            net.announceDespawn(ai.getCharacterInfo().characterId);
        ai.queueFree();
    }

    private void sweep() {
        boolean any = false;
        for (Extra e : extras.values()) if (e.a.state == LightSim.GONE) { any = true; break; }
        if (!any) return;
        extras.values().removeIf(e -> e.a.state == LightSim.GONE);
        sim.sweep();
    }

    /** Full bodies standing in for light ones now. */
    public int promotedNow() {
        int n = 0;
        for (Extra e : extras.values()) if (e.full != null && GD.isInstanceValid(e.full) && !e.full.isDead()) n++;
        return n;
    }

    // ── drawing ─────────────────────────────────────────────────────────────────────────────────

    private void draw() {
        for (LightLooks.Layer l : layers.values()) l.count = 0;
        if (!drawBodies) { for (LightLooks.Layer l : layers.values()) l.upload(); return; }
        var cam = getViewport() != null ? getViewport().getCamera3d() : null;
        Vector3 eye = cam != null ? cam.getGlobalPosition() : null;
        for (Extra e : extras.values()) {
            LightSim.Agent a = e.a;
            if (a.state == LightSim.PROMOTED || a.state == LightSim.GONE) continue;
            if (eye != null && drawDistance > 0 && LightSim.plan(a.x, a.z, eye.getX(), eye.getZ()) > drawDistance) continue;
            float[] c = clip(e);
            LightLooks.write(layer(e.body, "b|" + e.bb.outfit, null), a.x, a.y, a.z, a.yaw, c[0], c[1], c[2], c[3]);
            if (e.weapon != null && a.state != LightSim.DEAD)
                LightLooks.write(layer(e.body, "w|" + e.weapon.id(), e.weapon), a.x, a.y, a.z, a.yaw, c[0], c[1], c[2], c[3]);
        }
        for (LightLooks.Layer l : layers.values()) l.upload();
    }

    private LightLooks.Layer layer(LightLooks.Body b, String key, LightLooks.WeaponLook w) {
        String k = b.name + "|" + key;
        LightLooks.Layer l = layers.get(k);
        if (l == null) {
            l = w == null ? LightLooks.bodyLayer(this, b, key.substring(2)) : LightLooks.weaponLayer(this, b, w);
            layers.put(k, l);
        }
        return l;
    }

    /** The clip a light combatant shows: {row, frames, start, fps} for the shader. */
    private float[] clip(Extra e) {
        LightSim.Agent a = e.a;
        LightLooks.Body b = e.body;
        boolean z = a.style == LightSim.ZOMBIE;
        boolean rifle = e.weapon != null && e.weapon.ranged() && !"pistol".equals(e.weapon.archetype());
        LightLooks.Clip c;
        switch (a.state) {
            case LightSim.DEAD -> {
                c = b.clip("death", "idle");
                int f = Math.min(c.frames() - 1, (int) Math.floor(a.stateTime * c.fps()));
                return new float[] { c.row() + f, 1f, 0f, 0f };     // one frame at a time, held on the last
            }
            case LightSim.ATTACK -> c = b.clip(z ? "zombie_attack" : "attack", "idle");
            case LightSim.HOLD -> c = a.kind == LightSim.RANGED ? b.clip(rifle ? "aim_rifle" : "aim_pistol", "idle")
                    : b.clip(z ? "zombie_idle" : "idle", "idle");
            case LightSim.ADVANCE -> c = z ? b.clip("zombie_walk", "walk")
                    : !a.hasTarget ? b.clip("walk", "walk") : rifle ? b.clip("run_rifle", "run") : b.clip("jog", "run");
            default -> c = b.clip(z ? "zombie_idle" : "idle", "walk");
        }
        return new float[] { c.row(), c.frames(), (float) e.phase, (float) c.fps() };
    }

    // ── shot at, swung at, blasted (a light combatant has no collider: the weapons ask the tier) ──────────

    /** A light combatant a ray reached: where, how far along it, and how far up its body (0 feet .. 1 crown). */
    public record LightHit(LightCombatants tier, int id, double distance, Vector3 point, double heightFraction) { }

    private static final double BODY_RADIUS = 0.3;

    /** The nearest live, unpromoted light combatant the ray from {@code origin} along unit {@code dir} enters
     *  within {@code maxDist}; null = none. Authoritative peer only (a client's shot is resolved by the host). */
    public static LightHit shoot(Vector3 origin, Vector3 dir, double maxDist) { return shoot(origin, dir, maxDist, null); }

    /**
     * As {@link #shoot(Vector3, Vector3, double)} for a shot by {@code shooter}: an AI's bullet passes through the
     * light bodies of every faction it is not hostile to. The light reserve behind a firing line is cosmetic, and the
     * firing line's own rounds promoting it (measured: bench_light_tier filled the hit ceiling with friendly fire) is
     * exactly the cost the tier exists to avoid. A player's shot hits anyone.
     */
    public static LightHit shoot(Vector3 origin, Vector3 dir, double maxDist, Node shooter) {
        LightCombatants t = get();
        if (t == null || t.extras.isEmpty() || !t.authoritative()) return null;
        String sf = shooter instanceof Character c && !(shooter instanceof Player) && c.characterInfo != null
                ? c.characterInfo.faction : null;
        LightHit best = null;
        for (Extra e : t.extras.values()) {
            LightSim.Agent a = e.a;
            if (!a.alive()) continue;
            if (sf != null && !Faction.areHostile(sf, e.bb.faction)) continue;
            double d = com.openworld.world.CrowdShot.rayBody(origin.getX(), origin.getY(), origin.getZ(),
                    dir.getX(), dir.getY(), dir.getZ(), a.x, a.y, a.z, e.body.height, BODY_RADIUS);
            if (d < 0 || d > maxDist || (best != null && d >= best.distance())) continue;
            Vector3 p = origin.plus(dir.times(d));
            best = new LightHit(t, a.id, d, p, Math.max(0.0, Math.min(1.0, (p.getY() - a.y) / e.body.height)));
        }
        return best;
    }

    /**
     * {@code damage} reached light combatant {@code id}. LETHAL: it dies in the tier (its death clip; no promotion to
     * make a ragdoll for one frame -- a spray into a horde never stacks promotions) and null is returned. Not lethal:
     * it is promoted at once, the budget ignored up to budget + {@link #hitCeilingExtra}, and its body is returned
     * for the caller to land the damage on (the hit marker, the reaction); over the ceiling it takes the damage in the
     * tier and null is returned.
     */
    public AICharacter hitOrPromote(int id, double damage) {
        Extra e = extras.get(id);
        if (e == null || !e.a.alive()) return null;
        if (damage >= e.a.hp) {
            sim.hit(e.a, damage);
            killedInTier++;
            return null;
        }
        if (promotedNow() < effectiveBudget() + hitCeilingExtra) {
            AICharacter ai = promote(e);
            if (ai != null) return ai;
        }
        sim.hit(e.a, damage);
        return null;
    }

    /** Damage {@code id} in the tier only (a blast's share, a body over the ceiling). True = that killed it. */
    public boolean damageInTier(int id, double damage) {
        Extra e = extras.get(id);
        boolean dead = e != null && sim.hit(e.a, damage);
        if (dead) killedInTier++;
        return dead;
    }

    /**
     * Promote, now and over the budget (to the ceiling), the light combatants within {@code radius} of the segment
     * a-b (a swing's reach; a car's path), nearest first, at most {@code max}; returns their bodies for the damage.
     */
    public static List<AICharacter> promoteNear(Vector3 a, Vector3 b, double radius, int max) {
        LightCombatants t = get();
        List<AICharacter> out = new ArrayList<>();
        if (t == null || t.extras.isEmpty() || !t.authoritative()) return out;
        List<Object[]> found = new ArrayList<>();
        for (Extra e : t.extras.values()) {
            if (!e.a.alive()) continue;
            double d = com.openworld.world.CrowdShot.segmentToBody(a.getX(), a.getY(), a.getZ(), b.getX(), b.getY(), b.getZ(),
                    e.a.x, e.a.y, e.a.z, e.body.height);
            if (d <= radius + BODY_RADIUS) found.add(new Object[] { e, d });
        }
        found.sort((x, y) -> Double.compare((double) x[1], (double) y[1]));
        for (Object[] o : found) {
            if (out.size() >= max || t.promotedNow() >= t.effectiveBudget() + t.hitCeilingExtra) break;
            AICharacter ai = t.promote((Extra) o[0]);
            if (ai != null) out.add(ai);
        }
        return out;
    }

    /**
     * A blast: the nearest few in {@code radius} are promoted (ExplosionManager then damages and throws them like
     * anyone), every other light combatant in it takes its share IN THE TIER (linear fall-off, the blast's own rule).
     */
    public static void blast(Vector3 center, double radius, double maxDamage) {
        LightCombatants t = get();
        if (t == null || t.extras.isEmpty() || !t.authoritative()) return;
        promoteNear(center, center, radius, 4);
        for (Extra e : t.extras.values()) {
            if (!e.a.alive()) continue;
            double d = new Vector3(e.a.x, e.a.y + 0.9, e.a.z).distanceTo(center);
            if (d > radius) continue;
            t.damageInTier(e.a.id, maxDamage * (1.0 - d / radius));
        }
    }

    // ── probe / console readouts ───────────────────────────────────────────────────────────────

    /** Light combatants alive in the tier now (not promoted, not dead). */
    @Register
    public int lightNow() { return sim.aliveCount(); }

    /** Live members an owner placed: light ones plus the full bodies standing in for them. */
    public int liveOwnedBy(String owner) {
        int n = 0;
        for (Extra e : extras.values()) {
            if (!owner.equals(e.bb.owner)) continue;
            if (e.a.alive() || (e.full != null && GD.isInstanceValid(e.full) && !e.full.isDead())) n++;
        }
        return n;
    }

    /** One member's state: 0 = gone or dead, 1 = alive in the tier, 2 = a full body alive in its place. */
    public int statusOf(int id) {
        Extra e = extras.get(id);
        if (e == null) return 0;
        if (e.full != null && GD.isInstanceValid(e.full) && !e.full.isDead()) return 2;
        return e.a.alive() ? 1 : 0;
    }

    /** Where one member stands (its full body's position when promoted), or null. */
    public Vector3 positionOf(int id) {
        Extra e = extras.get(id);
        if (e == null) return null;
        if (e.full != null && GD.isInstanceValid(e.full)) return e.full.getGlobalPosition();
        return new Vector3(e.a.x, e.a.y, e.a.z);
    }

    /** Take one member away (light, or the full body standing in for it). */
    public void release(int id) {
        Extra e = extras.get(id);
        if (e == null) return;
        if (e.full != null && GD.isInstanceValid(e.full) && !e.full.isDead()) despawn(e.full);
        e.full = null;
        sim.lost(e.a);
        sweep();
    }

    /** Take away everything an owner placed: its light members and the full bodies standing in for them. */
    public void releaseOwnedBy(String owner) {
        for (Extra e : extras.values()) {
            if (!owner.equals(e.bb.owner)) continue;
            if (e.full != null && GD.isInstanceValid(e.full) && !e.full.isDead()) despawn(e.full);
            e.full = null;
            sim.lost(e.a);
        }
        sweep();
    }

    /** "light,promoted,dead,promotedTotal,demotedTotal,killedInTier,refusedTotal,paths,thinks,tick ms,path ms,snap ms"
     *  (the last three: mean per tick since the tier was made). */
    @Register
    public String statsNow() {
        int dead = 0;
        for (Extra e : extras.values()) if (e.a.state == LightSim.DEAD) dead++;
        double per = Math.max(1, ticks) * 1e6;
        return sim.aliveCount() + "," + promotedNow() + "," + dead + "," + promotedTotal + "," + demotedTotal + ","
                + killedInTier + "," + refusedTotal + "," + sim.pathsAsked + "," + sim.thinks
                + String.format(java.util.Locale.ROOT, ",%.3f,%.3f,%.3f", tickNanos / per, pathNanos / per, snapNanos / per);
    }

    /** Probe: spawn {@code n} hunters of {@code loadout} in a ring of {@code radius} round {@code center}, hostile to
     *  every player. Returns how many the tier took. */
    @Register
    public int hordeNow(Vector3 center, int n, double radius, String faction, String loadout, boolean zombie) {
        int made = 0;
        for (int i = 0; i < n; i++) {
            double ang = Math.PI * 2 * i / Math.max(1, n);
            double r = radius * (0.85 + 0.3 * rng.nextDouble());
            Vector3 at = new Vector3(center.getX() + Math.cos(ang) * r, center.getY(), center.getZ() + Math.sin(ang) * r);
            double[] s = navSnap(at.getX(), at.getY(), at.getZ());
            if (s != null) at = new Vector3(s[0], s[1], s[2]);
            AIBlackboard bb = new AIBlackboard();
            bb.huntsPlayers = true;
            bb.faction = faction;
            bb.loadout = loadout;
            bb.owner = "horde";
            if (spawn(bb, at, 100.0, zombie ? LightSim.ZOMBIE : LightSim.HUMAN) > 0) made++;
        }
        return made;
    }

    /** Probe: "id;state;x;y;z;hp;promoted" per light combatant, '|'-joined. The id is the tier's key -- on a client the
     *  HOST's id (its own LightSim numbers the agents locally), so two peers' dumps compare body by body. */
    @Register
    public String dumpNow() {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<Integer, Extra> m : extras.entrySet()) {
            Extra e = m.getValue();
            if (sb.length() > 0) sb.append('|');
            sb.append(m.getKey()).append(';').append(e.a.state).append(';').append(String.format("%.2f;%.2f;%.2f;%.0f", e.a.x, e.a.y, e.a.z, e.a.hp))
                    .append(';').append(e.full != null ? 1 : 0);
        }
        return sb.toString();
    }

    /** Probe: why each promoted body is (not) demoted -- "id;target;calm;hurt;state" per body, '|'-joined. */
    @Register
    public String promotedReadoutNow() {
        StringBuilder sb = new StringBuilder();
        for (Extra e : extras.values()) {
            if (e.full == null || !GD.isInstanceValid(e.full)) continue;
            if (sb.length() > 0) sb.append('|');
            Character t = e.full.getTarget();
            sb.append(e.a.id).append(';').append(t == null ? "-" : t.getName().toString()).append(';')
                    .append(String.format("%.1f", e.calm)).append(';')
                    .append(e.full.healthNode != null && e.full.healthNode.hurtWithin(demoteUnhurtSeconds)).append(';')
                    .append(e.full.isDead() ? "dead" : "alive");
        }
        return sb.toString();
    }

    /** Probe: kill or wound one the way a bullet would (returns 2 = promoted, 1 = died in the tier, 0 = neither). */
    @Register
    public int hitNow(int id, double damage) {
        Extra e = extras.get(id);
        if (e == null) return 0;
        AICharacter ai = hitOrPromote(id, damage);
        if (ai != null) {
            if (ai.healthNode != null) ai.healthNode.applyReplicatedHealth((float) Math.max(1.0, e.a.hp - damage));
            return 2;
        }
        return e.a.state == LightSim.DEAD ? 1 : 0;
    }

    /** Probe: the point a ray finds on a light body ({@link #shoot}), or (0, -10000, 0). Nothing is damaged. */
    @Register
    public Vector3 shootProbeNow(Vector3 origin, Vector3 dir, double range) {
        LightHit h = shoot(origin, dir.normalized(), range);
        return h != null ? h.point() : new Vector3(0, -10000, 0);
    }

    /** Probe: remove every light combatant and free their full bodies. */
    @Register
    public void clearNow() {
        for (Extra e : extras.values()) if (e.full != null && GD.isInstanceValid(e.full)) despawn(e.full);
        for (Extra e : extras.values()) sim.lost(e.a);
        extras.clear();
        sim.sweep();
    }

    /** Probe: set the tuning in one call. */
    @Register
    public void tuneNow(int capN, int budget, double promoteDistance, int thinkGroups, boolean light) {
        cap = capN;
        fullBudget = budget;
        sim.params.promoteDistance = promoteDistance;
        sim.params.thinkGroups = thinkGroups;
        lightTier = light;
    }

    // ── co-op: the host simulates, sends MSG_LIGHT_BATCH at sendHz; a client draws it ────────────────

    /** Light batches a second the host sends (the whole visible tier each: ~11 bytes a body). */
    @Visible public double sendHz = 10.0;
    private double sendIn = 0.0;
    /** Readouts: batches sent (host) / applied (client). */
    @Visible public int batchesSent, batchesApplied;

    private void sendBatch(double delta) {
        sendIn -= delta;
        if (sendIn > 0) return;
        sendIn = 1.0 / Math.max(1.0, sendHz);
        if (!(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) || !net.isNetworked() || !net.isServer()) return;
        List<String> looks = new ArrayList<>();
        Map<String, Integer> lookIx = new HashMap<>();
        List<LightBatch.Entry> entries = new ArrayList<>();
        for (Extra e : extras.values()) {
            LightSim.Agent a = e.a;
            if (a.state == LightSim.PROMOTED || a.state == LightSim.GONE) continue;
            String look = e.body.name + "|" + e.bb.outfit + "|" + (e.weapon != null ? e.weapon.id() : "");
            Integer ix = lookIx.get(look);
            if (ix == null) {
                if (looks.size() >= 255) continue;
                ix = looks.size();
                looks.add(look);
                lookIx.put(look, ix);
            }
            entries.add(new LightBatch.Entry(a.id & 0xffff, ix, a.x, a.y, a.z, a.yaw, a.state, a.kind == LightSim.RANGED,
                    a.style == LightSim.ZOMBIE, a.hasTarget));
        }
        net.broadcastLightBatch(LightBatch.encode(looks, entries));
        batchesSent++;
    }

    /** Client: the host's tier as it is now. A body missing from it is gone (promoted -- its full body replicates --
     *  or removed). */
    public void applyBatch(byte[] body) {
        if (authoritative()) return;
        List<String> looks = new ArrayList<>();
        List<LightBatch.Entry> entries = LightBatch.decode(body, looks);
        java.util.Set<Integer> live = new java.util.HashSet<>();
        for (LightBatch.Entry n : entries) {
            live.add(n.id());
            Extra e = extras.get(n.id());
            if (e == null) {
                String[] lk = looks.get(n.look()).split("\\|", -1);
                LightLooks.Body b = LightLooks.body(lk.length > 0 ? lk[0] : "", 0.0);
                if (b == null) continue;
                AIBlackboard bb = new AIBlackboard();
                bb.body = b.name;
                bb.outfit = lk.length > 1 ? lk[1] : "";
                bb.weapon = lk.length > 2 ? lk[2] : "";
                LightSim.Agent a = sim.add(n.ranged() ? LightSim.RANGED : LightSim.MELEE, n.x(), n.y(), n.z(), 100.0);
                a.yaw = n.yaw();
                e = new Extra(a, bb, b, LightLooks.weapons().get(bb.weapon), (n.id() % 97) * 0.103);
                extras.put(n.id(), e);
            }
            e.a.style = n.zombie() ? LightSim.ZOMBIE : LightSim.HUMAN;
            e.a.hasTarget = n.hasTarget();
            if (e.a.state != n.state()) { e.a.state = n.state(); e.a.stateTime = 0.0; }
            e.netX = n.x(); e.netY = n.y(); e.netZ = n.z(); e.netYaw = n.yaw();
            if (!e.seen) { e.a.x = n.x(); e.a.y = n.y(); e.a.z = n.z(); e.a.yaw = n.yaw(); e.seen = true; }
        }
        for (Map.Entry<Integer, Extra> m : extras.entrySet()) if (!live.contains(m.getKey())) sim.lost(m.getValue().a);
        extras.entrySet().removeIf(m -> !live.contains(m.getKey()));
        sim.sweep();
        batchesApplied++;
    }

    /** Client: ease every body toward where the host last put it (10 Hz updates drawn at the frame rate). */
    private void clientTick(double delta) {
        double k = Math.min(1.0, delta * 12.0);
        for (Extra e : extras.values()) {
            LightSim.Agent a = e.a;
            a.stateTime += delta;
            if (!e.seen) continue;
            double dx = e.netX - a.x, dz = e.netZ - a.z;
            if (dx * dx + dz * dz > 25.0) { a.x = e.netX; a.y = e.netY; a.z = e.netZ; }
            else { a.x += dx * k; a.y += (e.netY - a.y) * k; a.z += dz * k; }
            a.yaw = LightSim.turn(a.yaw, e.netYaw, 10.0 * delta);
        }
    }

    // ── the engine's answers to the sim ─────────────────────────────────────────────────────────

    private double[] navPath(double fx, double fy, double fz, double tx, double ty, double tz) {
        long t0 = System.nanoTime();
        try { return navPathTimed(fx, fy, fz, tx, ty, tz); } finally { pathNanos += System.nanoTime() - t0; }
    }

    private double[] navPathTimed(double fx, double fy, double fz, double tx, double ty, double tz) {
        RID map = navMap();
        if (map == null) return new double[] { fx, fy, fz, tx, ty, tz };
        PackedVector3Array p = NavigationServer3D.INSTANCE.mapGetPath(map, new Vector3(fx, fy, fz), new Vector3(tx, ty, tz), true, 1L);
        if (p == null || p.getSize() == 0) return new double[] { fx, fy, fz, tx, ty, tz };
        double[] out = new double[p.getSize() * 3];
        for (int i = 0; i < p.getSize(); i++) {
            Vector3 v = p.get(i);
            out[i * 3] = v.getX(); out[i * 3 + 1] = v.getY(); out[i * 3 + 2] = v.getZ();
        }
        return out;
    }

    private double[] navSnap(double x, double y, double z) {
        long t0 = System.nanoTime();
        try { return navSnapTimed(x, y, z); } finally { snapNanos += System.nanoTime() - t0; }
    }

    /**
     * The ground under a body that separation pushed: a physics ray straight down (microseconds). NOT the nav map's
     * closest point -- measured on the island (walk_station) that query costs ~0.6 ms, and the tier spent 3.4 ms a tick
     * on it; the path corners are on the nav mesh, and following them pulls a pushed body back onto its line.
     */
    private double[] navSnapTimed(double x, double y, double z) {
        if (getWorld3d() == null) return null;
        var q = PhysicsRayQueryParameters3D.create(new Vector3(x, y + 1.5, z), new Vector3(x, y - 3.0, z),
                CollisionLayers.WORLD, new godot.core.VariantArray<>(RID.class));
        var hit = getWorld3d().getDirectSpaceState().intersectRay(q);
        if (hit.isEmpty() || !(hit.get("position") instanceof Vector3 p)) return null;
        return new double[] { x, p.getY(), z };
    }

    private RID navMap() {
        if (navMap == null && getWorld3d() != null) navMap = getWorld3d().getNavigationMap();
        return navMap;
    }

    /** True where this peer decides what exists: single player, or the host. */
    boolean authoritative() {
        Node n = getNodeOrNull("/root/NetworkManager");
        NetworkManager net = n instanceof NetworkManager m ? m : null;
        return net == null || !net.isNetworked() || net.isServer();
    }
}
