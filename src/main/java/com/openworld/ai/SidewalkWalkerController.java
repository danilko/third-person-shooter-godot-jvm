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

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();
        cmd.tick = ++tick;
        cmd.movementType = MovementType.IDLE;
        cmd.movementDirection = Vector3.Companion.getZERO();
        if (!(getParent() instanceof Node3D body) || cum.length < 2) return cmd;
        if (gliding()) {
            double L = length();
            along += dir * GLIDE_SPEED * delta;
            walked += GLIDE_SPEED * delta;
            if (along >= L - 0.5) { along = L - 0.5; dir = -1; }
            if (along <= 0.5) { along = 0.5; dir = 1; }
            Vector3 p = pointAt(along);
            body.setGlobalPosition(new Vector3(p.getX(), p.getY() + GLIDE_LIFT, p.getZ()));
            lastPos = null;
            stallTimer = 0.0;
            return cmd;
        }
        Vector3 pos = body.getGlobalPosition();
        if (lastPos != null) {
            double step = Math.hypot(pos.getX() - lastPos.getX(), pos.getZ() - lastPos.getZ());
            walked += step;
            along += dir * step;
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
        double L = length();
        if (along >= L - 0.5) { along = L - 0.5; dir = -1; }
        if (along <= 0.5) { along = 0.5; dir = 1; }
        Vector3 target = pointAt(along + dir * lookAheadM);
        double dx = target.getX() - pos.getX();
        double dz = target.getZ() - pos.getZ();
        double d = Math.hypot(dx, dz);
        if (d < 1e-3) return cmd;
        cmd.movementDirection = new Vector3(dx / d, 0.0, dz / d);
        cmd.movementType = MovementType.WALK;
        return cmd;
    }
}
