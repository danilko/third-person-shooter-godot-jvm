package com.openworld.ai;

import com.openworld.character.AICharacter;
import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.MovementType;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node3D;
import godot.core.PackedVector3Array;
import godot.core.Vector3;

/**
 * The cheapest believable pedestrian brain (PLAN.md 3.6 perf, "walkers on the sidewalk"): walks a footway polyline
 * (`world/IslandSidewalks.json`, derived by `tools/island_buildings.py` from the same road solve that places the
 * buildings) at a walking pace, turns round at either end, and does nothing else -- no NavigationAgent3D, no
 * perception, no target scan. That is the GTA ambient-pedestrian split: a crowd follows authored paths, and only a
 * body that has been disturbed is handed a full brain (not built yet: a walker that is shot today just keeps
 * walking until it dies).
 *
 * <p>Steering is a direction to a point {@link #lookAheadM} further along the path from the body's own projection
 * on it, so a walker pushed off the line (by another body, a car) walks back onto it rather than to a waypoint it
 * already passed. World-space direction, as the AI movement frame is.
 */
@Script(className = "SidewalkWalkerController")
public class SidewalkWalkerController extends Controller {

    /** The footway, world frame. At least two points. */
    @Visible public PackedVector3Array path = new PackedVector3Array();
    /** Current arc position along the path (m) and walking direction (+1 / -1). */
    @Visible public double along = 0.0;
    @Visible public int dir = 1;
    @Visible public double lookAheadM = 3.0;
    /** Metres walked -- probe readout. */
    @Visible public double walked = 0.0;
    /** Times this walker gave up on a blocked direction and turned round -- probe readout. */
    @Visible public int stalls = 0;
    /** Control knobs (probe_walker_pass.gd): false = the pre-2026-09-27 rules, each on its own. */
    @Visible public boolean passLeft = true;
    @Visible public boolean projectOnPath = true;
    /** Ticks this walker stepped aside for someone ahead -- probe readout. */
    @Visible public int sidesteps = 0;

    /**
     * The unstick rule (PLAN.md 3.18a). `along` advances by the step the body ACTUALLY took, so a walker held by
     * anything solid never advances, never reaches the end of its path and never turns round -- it is pinned
     * there for the rest of the session. The footway itself is kept clear of street furniture by derivation
     * (`island_buildings.ped_walk_offset`), which is the fix; this is the recovery for everything that rule
     * cannot see -- a parked car on the pavement, a player standing in a doorway, another walker.
     *
     * <p>Turning round rather than stepping around is deliberate: it is what a pedestrian meeting a blocked
     * passage does, it costs two doubles and a compare, and it cannot fail. Stepping around wants a navmesh,
     * which is exactly the cost this tier exists to avoid.
     */
    public static final double STALL_SECONDS = 1.5;
    public static final double STALL_PROGRESS_M = 0.25;

    private double stallTimer = 0.0;
    private double stallMark = 0.0;

    /** A walking pace (m/s) for the glide, and how far above the footway line the body's origin rides. */
    public static final double GLIDE_SPEED = 1.4;
    public static final double GLIDE_LIFT = 0.02;

    private double[] cum = new double[0];
    private Vector3 lastPos = null;
    private long tick = 0;

    /** Set the path and start at arc position {@code start} walking {@code direction}. */
    @Register
    public void setup(PackedVector3Array points, double start, int direction) {
        path = points;
        int n = points.getSize();
        cum = new double[n];
        for (int i = 1; i < n; i++) cum[i] = cum[i - 1] + points.get(i).distanceTo(points.get(i - 1));
        along = Math.max(0.0, Math.min(start, length()));
        dir = direction >= 0 ? 1 : -1;
    }

    public double length() { return cum.length == 0 ? 0.0 : cum[cum.length - 1]; }

    /** The point at arc position s. */
    @Register
    public Vector3 pointAt(double s) {
        int n = cum.length;
        if (n == 0) return Vector3.Companion.getZERO();
        if (s <= 0) return path.get(0);
        if (s >= cum[n - 1]) return path.get(n - 1);
        int lo = 0, hi = n - 1;
        while (hi - lo > 1) {
            int mid = (lo + hi) >>> 1;
            if (cum[mid] <= s) lo = mid; else hi = mid;
        }
        double seg = cum[hi] - cum[lo];
        double f = seg < 1e-9 ? 0.0 : (s - cum[lo]) / seg;
        return path.get(lo).lerp(path.get(hi), f);
    }

    /**
     * True while the body is beyond the ACTIVE AI tier (> 80 m from every player): it then GLIDES -- this controller
     * moves it along the footway directly and {@code MovementController} skips it, so a distant pedestrian costs no
     * move_and_slide. Measured (probe_city_perf.gd --crowd): 150 walkers added ~18 ms per physics tick, ~12 ms of it
     * MovementController's slide and step-up shape tests against the city's colliders, for bodies mostly 80-300 m
     * away. The path IS the footway at footway height, so a glide cannot leave the pavement; a body that comes back
     * into range simply resumes walking from where it is.
     */
    public boolean gliding() {
        return getParent() instanceof AICharacter ai && ai.getLodLevel() != AILodLevel.ACTIVE;
    }

    // ── Scared: the same rule as the light crowd (world.PedCrowd), so a promotion does not change who runs ──
    /** How far a walker hears trouble (capped by each stimulus's own radius), how long it runs. */
    public static final double PANIC_RANGE = 120.0;
    public static final double PANIC_SECONDS = 8.0;
    private static final double HEAR_INTERVAL = 0.25;
    /** Seconds of running left (0 = calm) -- probe readout. */
    @Visible public double flee = 0.0;
    private double hearTimer = 0.0;
    /** Heard by IDENTITY (PedCrowd.hear: the stimulus clock can repeat a timestamp across physics ticks). */
    private final java.util.Set<com.openworld.world.StimulusManager.Stimulus> heard =
            java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<>());

    /** A gunshot, an explosion or a weapon drawn nearby: run along the footway, away from it. */
    private void hear(Node3D body, double delta) {
        hearTimer -= delta;
        if (hearTimer > 0.0) return;
        hearTimer = HEAR_INTERVAL;
        com.openworld.world.StimulusManager sm = com.openworld.world.StimulusManager.get();
        if (sm == null) return;
        Vector3 here = body.getGlobalPosition();
        java.util.List<com.openworld.world.StimulusManager.Stimulus> live = sm.getStimuli();
        for (com.openworld.world.StimulusManager.Stimulus st : live) {
            if (!heard.add(st)) continue;
            if (st.source == body) continue;
            if (st.type != com.openworld.world.StimulusManager.Type.GUNSHOT
                    && st.type != com.openworld.world.StimulusManager.Type.EXPLOSION
                    && st.type != com.openworld.world.StimulusManager.Type.WEAPON_DRAWN) continue;
            if (here.distanceTo(st.origin) > Math.min(PANIC_RANGE, st.radius)) continue;
            flee = PANIC_SECONDS;
            double a = pointAt(along + 1.0).distanceTo(st.origin);
            double b = pointAt(along - 1.0).distanceTo(st.origin);
            dir = a >= b ? 1 : -1;
        }
        if (heard.size() > 64) heard.retainAll(new java.util.HashSet<>(live));
    }

    /** How far either side of the current arc position the per-tick projection looks. */
    public static final double PROJECT_WINDOW_M = 6.0;

    /** The arc position on the path nearest {@code pos} (plan distance), searched within +-window of {@code near}. */
    public double project(Vector3 pos, double near, double window) {
        int n = cum.length;
        if (n < 2) return near;
        double lo = Math.max(0.0, near - window), hi = Math.min(length(), near + window);
        double best = near, bestD = Double.MAX_VALUE;
        for (int i = 0; i < n - 1; i++) {
            if (cum[i + 1] < lo || cum[i] > hi) continue;
            Vector3 a = path.get(i), b = path.get(i + 1);
            double sx = b.getX() - a.getX(), sz = b.getZ() - a.getZ();
            double l2 = sx * sx + sz * sz;
            double t = l2 < 1e-9 ? 0.0 : ((pos.getX() - a.getX()) * sx + (pos.getZ() - a.getZ()) * sz) / l2;
            t = Math.max(0.0, Math.min(1.0, t));
            double s = cum[i] + t * (cum[i + 1] - cum[i]);
            if (s < lo || s > hi) continue;
            double qx = a.getX() + sx * t - pos.getX(), qz = a.getZ() + sz * t - pos.getZ();
            double d = qx * qx + qz * qz;
            if (d < bestD) { bestD = d; best = s; }
        }
        return best;
    }

    /** How far a walker steps aside to pass someone coming the other way, and how near "ahead" is. */
    public static final double SIDESTEP_M = 1.2;
    public static final double AHEAD_M = 2.0;
    private final java.util.List<godot.api.Node> nearBuf = new java.util.ArrayList<>();

    /** True when another body stands within AHEAD_M in front of this walker's heading (dx, dz). */
    private boolean bodyAhead(Node3D self, Vector3 pos, double dx, double dz) {
        com.openworld.world.SpatialEntityGrid grid = com.openworld.world.SpatialEntityGrid.get();
        if (grid == null) return false;
        double l = Math.hypot(dx, dz);
        if (l < 1e-6) return false;
        nearBuf.clear();
        grid.queryRadius(pos, (float) AHEAD_M, nearBuf);
        for (godot.api.Node n : nearBuf) {
            if (n == self || !(n instanceof Node3D o) || !godot.global.GD.isInstanceValid(o)) continue;
            Vector3 q = o.getGlobalPosition();
            double ox = q.getX() - pos.getX(), oz = q.getZ() - pos.getZ();
            double fwd = (ox * dx + oz * dz) / l;
            double side = Math.abs(ox * dz - oz * dx) / l;
            if (fwd > 0.1 && fwd < AHEAD_M && side < 0.8) return true;
        }
        return false;
    }

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();
        cmd.tick = ++tick;
        cmd.movementType = MovementType.IDLE;
        cmd.movementDirection = Vector3.Companion.getZERO();
        if (!(getParent() instanceof Node3D body) || cum.length < 2) return cmd;
        hear(body, delta);
        if (flee > 0.0) flee = Math.max(0.0, flee - delta);
        if (gliding()) {
            double L = length();
            double pace = flee > 0.0 ? 4.5 : GLIDE_SPEED;   // PedCrowd.fleeSpeed
            along += dir * pace * delta;
            walked += pace * delta;
            if (along >= L - 0.5) { along = L - 0.5; dir = -1; }
            if (along <= 0.5) { along = 0.5; dir = 1; }
            Vector3 p = pointAt(along);
            body.setGlobalPosition(new Vector3(p.getX(), p.getY() + GLIDE_LIFT, p.getZ()));
            // Face the way it glides: MovementController (which turns the mesh) is skipped while gliding, so a
            // glided body kept whatever facing it had and slid sideways or backwards down the footway.
            Vector3 a = pointAt(along + dir * 1.0);
            double fx = a.getX() - p.getX(), fz = a.getZ() - p.getZ();
            if (Math.abs(fx) + Math.abs(fz) > 1e-4 && body instanceof com.openworld.character.Character ch) {
                ch.applyReplicatedFacing((float) Math.atan2(-fx, -fz));
            }
            lastPos = null;
            stallTimer = 0.0;
            return cmd;
        }
        Vector3 pos = body.getGlobalPosition();
        if (lastPos != null) {
            // PROGRESS is the step projected on the footway, signed -- never the distance moved. Two bodies
            // pushing against each other jitter sideways a centimetre a tick, and counting that as progress
            // along `dir` added up to more than STALL_PROGRESS_M in STALL_SECONDS, so neither ever turned
            // round and they stood face to face for good (zb2).
            double mx = pos.getX() - lastPos.getX(), mz = pos.getZ() - lastPos.getZ();
            walked += Math.hypot(mx, mz);
            Vector3 t0 = pointAt(along - 0.5), t1 = pointAt(along + 0.5);
            double tx = t1.getX() - t0.getX(), tz = t1.getZ() - t0.getZ();
            double tl = Math.hypot(tx, tz);
            along += tl < 1e-6 ? 0.0 : (mx * tx + mz * tz) / tl;
        } else {
            stallMark = along;
            stallTimer = 0.0;
        }
        lastPos = pos;
        stallTimer += delta;
        if (stallTimer >= STALL_SECONDS) {
            if (Math.abs(along - stallMark) < STALL_PROGRESS_M) {
                dir = -dir;
                stalls++;
            }
            stallMark = along;
            stallTimer = 0.0;
        }
        // `along` is the body's own PROJECTION on the footway, as the class doc says steering is: re-read it
        // every tick near where it was. Integrated alone it drifted from the body (a push, a car, jostling),
        // and the look-ahead point then ran round a block corner while the body beelined to it -- straight
        // across the street, sprinting when scared (user walk-test, 2026-09-27).
        if (projectOnPath) along = project(pos, along, PROJECT_WINDOW_M);
        double L = length();
        if (along >= L - 0.5) { along = L - 0.5; dir = -1; }
        if (along <= 0.5) { along = 0.5; dir = 1; }
        Vector3 target = pointAt(along + dir * lookAheadM);
        double dx = target.getX() - pos.getX();
        double dz = target.getZ() - pos.getZ();
        // Someone right ahead: pass them on the LEFT (Japan keeps left), as two people on a pavement do,
        // instead of walking into them until the stall rule turns one round.
        if (passLeft && bodyAhead(body, pos, dx, dz)) {
            double l = Math.hypot(dx, dz);
            if (l > 1e-6) {
                // left of a heading (dx, dz) in Godot's Y-up frame is (dz, -dx): facing -Z, left is -X
                double lx = dz / l, lz = -dx / l;
                dx += lx * SIDESTEP_M;
                dz += lz * SIDESTEP_M;
                sidesteps++;
            }
        }
        double d = Math.hypot(dx, dz);
        if (d < 1e-3) return cmd;
        cmd.movementDirection = new Vector3(dx / d, 0.0, dz / d);
        cmd.movementType = flee > 0.0 ? MovementType.SPRINT : MovementType.WALK;
        return cmd;
    }
}
