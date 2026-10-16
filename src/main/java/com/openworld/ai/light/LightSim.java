package com.openworld.ai.light;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The light combatant tier's BRAIN and body, engine-free (PLAN.md 2.3 / F8; docs/game-systems.md "The light combatant
 * tier and the AI blackboard"). Plain doubles, no Godot types, so {@code LightSimTest} runs it without an engine; the
 * node ({@link LightCombatants}) feeds it the targets and the players each tick, answers its path and ground
 * questions through {@link Ground}, and draws what it leaves in each {@link Agent}.
 *
 * <p>A few fields a body: a state, a goal, a path, hit points. <b>It never deals damage</b> -- only a full body
 * hurts anyone -- so nothing here aims, traces or rolls a hit. What it decides is where to stand and when it is
 * worth a full body ({@link Agent#wantsPromotion}); the node spends the budget.
 */
public final class LightSim {

    public static final int IDLE = 0, ADVANCE = 1, HOLD = 2, ATTACK = 3, DEAD = 4, PROMOTED = 5, GONE = 6;
    public static final int MELEE = 0, RANGED = 1;
    public static final int HUMAN = 0, ZOMBIE = 1;

    /** The questions only the engine can answer: a nav path and the ground under a point. */
    public interface Ground {
        /** Path corners (x, y, z triples) from one point to another, or null / empty when there is none. */
        double[] path(double fx, double fy, double fz, double tx, double ty, double tz);
        /** The nearest walkable point to (x, y, z) as {x, y, z}, or null when the engine has no nav map. */
        double[] snap(double x, double y, double z);
    }

    /** The tuning, one object per sim (the node copies its exports in). */
    public static final class Params {
        /** A player this close (m) wants it promoted: it can be bumped, looked at closely, swung at. */
        public double promoteDistance = 15.0;
        /** A ranged one holding with a clear line this close (m) to its target wants to be a real shooter. */
        public double engageDistance = 40.0;
        /** How far short of its target a ranged one without a hold point stops (m). */
        public double standoff = 25.0;
        /** A melee one whose promotion was refused waits on this ring round its target (m) instead of swinging. */
        public double holdBackRing = 6.0;
        /** Melee reach (m): inside it a light one plays its swing (cosmetic). */
        public double reach = 1.4;
        /** Run speed (m/s) of a human / a zombie; walk speed when it has no target. */
        public double runSpeed = 4.2, zombieSpeed = 1.6, walkSpeed = 1.4;
        /** Re-path every this many seconds, or when the goal moved further than {@link #repathMove} (m). */
        public double repathSeconds = 1.5, repathMove = 3.0;
        /** Path requests a tick, over the whole tier (round-robin). */
        public int pathsPerTick = 4;
        /** Ground snaps a tick, over the whole tier (round-robin), and only for a body separation PUSHED off its path
         *  line (path corners are on the nav mesh already). Measured on the island (walk_station, 80 bodies): a nav
         *  closest-point query is ~0.3 ms there, and 12 a tick were 3.4 of the tier's 3.9 ms -- the tick crossed
         *  16.7 ms and the frame doubled. */
        public int snapsPerTick = 2;
        /** A separation push faster than this (m/s) marks a body for a snap. */
        public double snapPush = 0.5;
        /** Bodies keep this far apart (m), and the push that keeps them so (m/s per m of overlap). */
        public double separation = 0.8, separationPush = 6.0;
        /** Seconds a corpse lies before it is removed. */
        public double corpseSeconds = 20.0;
        /** Seconds a refused promotion waits before asking again. */
        public double refusedSeconds = 2.0;
        /** Turn rate (rad/s). */
        public double turnRate = 8.0;
        /** THINK GROUPS (user, 2026-10-16: "update one pool per round"): a body re-decides its goal and state only on
         *  every Nth tick, the tier split into N staggered groups; it MOVES every tick, so nothing stutters. 4 at 60 Hz
         *  is a 67 ms reaction, under what a player reads at the 15 m+ this tier is drawn. 1 = everyone every tick. */
        public int thinkGroups = 4;
    }

    /** One light combatant. Public fields: the node reads them to draw and to promote. */
    public static final class Agent {
        public final int id;
        public int kind = MELEE, style = HUMAN;
        public int state = IDLE;
        public double x, y, z, yaw;
        public double hp = 100.0;
        /** Seconds in the current state (the clip's start: a death or a swing plays from its first frame). */
        public double stateTime;
        // orders (from the blackboard; the node copies them in)
        public boolean hasHold;
        public double holdX, holdY, holdZ, leash;
        // the target, as the node resolved it this tick
        public boolean hasTarget;
        public double tx, ty, tz;
        // derived each tick
        public double goalX, goalY, goalZ;
        public double nearestPlayer = Double.MAX_VALUE;
        /** It asks for a full body this tick (the node decides, nearest first, under its budget). */
        public boolean wantsPromotion;
        /** Seconds until it may ask again after a refusal (0 = may ask). */
        public double refused;
        /** The node says a ranged one has a clear line to its target (it ray-tests the candidates). */
        public boolean lineOfSight;
        // the path
        double[] path;
        int pathAt;
        double repathIn;
        double pathGoalX = Double.NaN, pathGoalZ;
        double vx, vz;
        long thoughtTick = -1;
        boolean pushed;
        Agent(int id) { this.id = id; }
        public boolean alive() { return state != DEAD && state != GONE && state != PROMOTED; }
    }

    public final Params params;
    private final Ground ground;
    private final List<Agent> agents = new ArrayList<>();
    private int nextId = 1;
    private int pathCursor = 0, snapCursor = 0;
    private long tick = 0;
    /** Readout: think() calls, lifetime (the think groups' effect). */
    public long thinks;
    private double[] px = new double[0], pz = new double[0];
    private int np = 0;
    /** Readouts: path and snap requests made, lifetime. */
    public int pathsAsked, snapsAsked;

    public LightSim(Params params, Ground ground) {
        this.params = params != null ? params : new Params();
        this.ground = ground;
    }

    public Agent add(int kind, double x, double y, double z, double hp) {
        Agent a = new Agent(nextId++);
        a.kind = kind;
        a.x = x; a.y = y; a.z = z;
        a.hp = hp;
        a.repathIn = (agents.size() % 8) * 0.1;   // stagger the first paths
        agents.add(a);
        return a;
    }

    public List<Agent> agents() { return agents; }

    public Agent byId(int id) {
        for (Agent a : agents) if (a.id == id) return a;
        return null;
    }

    public int aliveCount() {
        int n = 0;
        for (Agent a : agents) if (a.alive()) n++;
        return n;
    }

    /** The players' plan positions this tick (promotion is measured to the nearest). */
    public void setPlayers(double[] xs, double[] zs, int n) { px = xs; pz = zs; np = n; }

    /** Drop the agents that are GONE (a corpse that lay its time, a promoted one whose body died). */
    public void sweep() { agents.removeIf(a -> a.state == GONE); }

    /** A bullet or a blast reached it. Returns true when that killed it (it dies IN the tier: no promotion). */
    public boolean hit(Agent a, double damage) {
        if (a == null || !a.alive()) return false;
        a.hp -= damage;
        if (a.hp <= 0.0) {
            a.hp = 0.0;
            enter(a, DEAD);
            return true;
        }
        return false;
    }

    /** A full body stands in for it now: it is not drawn or stepped until {@link #demote}. */
    public void promoted(Agent a) {
        if (a == null) return;
        enter(a, PROMOTED);
        a.wantsPromotion = false;
        a.path = null;
    }

    /** The node could not promote it (the budget is full): it waits {@link Params#refusedSeconds} before asking again,
     *  and a melee one holds back on the ring meanwhile. */
    public void refused(Agent a) { if (a != null) a.refused = params.refusedSeconds; }

    /** Its full body went back to the tier, standing here with these hit points. */
    public void demote(Agent a, double x, double y, double z, double hp) {
        if (a == null) return;
        a.x = x; a.y = y; a.z = z;
        a.hp = hp;
        a.path = null;
        a.repathIn = 0;
        enter(a, IDLE);
    }

    /** Its full body died: the light one is gone too. */
    public void lost(Agent a) { if (a != null) enter(a, GONE); }

    private static void enter(Agent a, int state) {
        if (a.state == state) return;
        a.state = state;
        a.stateTime = 0.0;
    }

    // ── the tick ────────────────────────────────────────────────────────────────────────────────

    public void step(double dt) {
        int pathsLeft = params.pathsPerTick;
        int n = agents.size();
        // paths: round-robin from where the last tick stopped, so nobody starves at 80 bodies
        for (int k = 0; k < n && pathsLeft > 0; k++) {
            Agent a = agents.get((pathCursor + k) % n);
            if (!a.alive()) continue;
            if (needsPath(a)) {
                repath(a);
                pathsLeft--;
                if (pathsLeft == 0) pathCursor = (pathCursor + k + 1) % Math.max(1, n);
            }
        }
        Map<Long, List<Agent>> grid = bucket();
        for (Agent a : agents) {
            a.stateTime += dt;
            if (a.refused > 0) a.refused = Math.max(0.0, a.refused - dt);
            switch (a.state) {
                case DEAD -> {
                    if (a.stateTime >= params.corpseSeconds) enter(a, GONE);
                    continue;
                }
                case PROMOTED, GONE -> { continue; }
                default -> { }
            }
            a.repathIn -= dt;
            a.nearestPlayer = nearestPlayer(a.x, a.z);
            // a body that never thought yet thinks now, whatever its group (a fresh spawn must not stand a tick)
            if (a.thoughtTick < 0 || params.thinkGroups <= 1 || (a.id + tick) % params.thinkGroups == 0) {
                think(a);
                a.thoughtTick = tick;
                thinks++;
            }
            move(a, dt, grid);
        }
        snapSome();
        tick++;
    }

    /** Decide the goal and the state. */
    private void think(Agent a) {
        a.wantsPromotion = false;
        if (!a.hasTarget) {
            a.lineOfSight = false;
            if (a.hasHold) setGoal(a, a.holdX, a.holdY, a.holdZ);
            else setGoal(a, a.x, a.y, a.z);
            double d = plan(a.x, a.z, a.goalX, a.goalZ);
            enterIf(a, d > 1.0 ? ADVANCE : IDLE);
            if (a.nearestPlayer < params.promoteDistance && a.refused <= 0) a.wantsPromotion = true;
            return;
        }
        double dt = plan(a.x, a.z, a.tx, a.tz);
        if (a.kind == RANGED) {
            double gx, gy, gz;
            if (a.hasHold) { gx = a.holdX; gy = a.holdY; gz = a.holdZ; }
            else if (dt <= params.standoff) { gx = a.x; gy = a.y; gz = a.z; }
            else {
                double k = (dt - params.standoff) / dt;
                gx = a.x + (a.tx - a.x) * k; gy = a.y + (a.ty - a.y) * k; gz = a.z + (a.tz - a.z) * k;
            }
            setGoal(a, gx, gy, gz);
            boolean there = plan(a.x, a.z, gx, gz) <= 1.0;
            enterIf(a, there ? HOLD : ADVANCE);
            boolean shooter = a.state == HOLD && a.lineOfSight && dt <= params.engageDistance;
            if ((a.nearestPlayer < params.promoteDistance || shooter) && a.refused <= 0) a.wantsPromotion = true;
        } else {
            // melee: straight for the target, inside the leash; a refused one waits on the ring
            double gx = a.tx, gy = a.ty, gz = a.tz;
            if (a.hasHold && a.leash > 0) {
                double hx = gx - a.holdX, hz = gz - a.holdZ, hl = Math.sqrt(hx * hx + hz * hz);
                if (hl > a.leash) { gx = a.holdX + hx * a.leash / hl; gz = a.holdZ + hz * a.leash / hl; gy = a.holdY; }
            }
            if (a.refused > 0 && dt < params.holdBackRing + 0.5) {
                // stand where it is if it is on or outside the ring, else step back out to it
                if (dt < params.holdBackRing - 0.5 && dt > 1e-3) {
                    double k = params.holdBackRing / dt;
                    gx = a.tx + (a.x - a.tx) * k; gz = a.tz + (a.z - a.tz) * k; gy = a.y;
                } else { gx = a.x; gy = a.y; gz = a.z; }
                setGoal(a, gx, gy, gz);
                enterIf(a, plan(a.x, a.z, gx, gz) > 0.5 ? ADVANCE : HOLD);
            } else {
                setGoal(a, gx, gy, gz);
                enterIf(a, dt <= params.reach ? ATTACK : ADVANCE);
            }
            if (a.nearestPlayer < params.promoteDistance && a.refused <= 0) a.wantsPromotion = true;
        }
    }

    private static void enterIf(Agent a, int s) { if (a.state != s) enter(a, s); }

    private static void setGoal(Agent a, double x, double y, double z) { a.goalX = x; a.goalY = y; a.goalZ = z; }

    private boolean needsPath(Agent a) {
        if (a.state != ADVANCE) return false;
        if (a.path == null || a.repathIn <= 0) return true;
        return Double.isNaN(a.pathGoalX) || plan(a.pathGoalX, a.pathGoalZ, a.goalX, a.goalZ) > params.repathMove;
    }

    private void repath(Agent a) {
        a.repathIn = params.repathSeconds;
        a.pathGoalX = a.goalX;
        a.pathGoalZ = a.goalZ;
        pathsAsked++;
        double[] p = ground != null ? ground.path(a.x, a.y, a.z, a.goalX, a.goalY, a.goalZ) : null;
        a.path = p != null && p.length >= 3 ? p : null;
        a.pathAt = 0;
    }

    /** Where it steers now: the next path corner it has not reached, else the goal. */
    private double[] waypoint(Agent a) {
        if (a.path != null) {
            int corners = a.path.length / 3;
            while (a.pathAt < corners) {
                double cx = a.path[a.pathAt * 3], cz = a.path[a.pathAt * 3 + 2];
                if (plan(a.x, a.z, cx, cz) > 0.6 || a.pathAt == corners - 1) break;
                a.pathAt++;
            }
            if (a.pathAt < corners) {
                int i = a.pathAt * 3;
                return new double[] { a.path[i], a.path[i + 1], a.path[i + 2] };
            }
        }
        return new double[] { a.goalX, a.goalY, a.goalZ };
    }

    private void move(Agent a, double dt, Map<Long, List<Agent>> grid) {
        double speed = 0.0;
        double fx = a.tx, fz = a.tz;   // what it faces when it does not move
        boolean face = a.hasTarget;
        if (a.state == ADVANCE) {
            speed = !a.hasTarget ? params.walkSpeed : a.style == ZOMBIE ? params.zombieSpeed : params.runSpeed;
        }
        double vx = 0, vz = 0;
        double[] w = null;
        if (speed > 0) {
            w = waypoint(a);
            double dx = w[0] - a.x, dz = w[2] - a.z, d = Math.sqrt(dx * dx + dz * dz);
            if (d > 1e-4) {
                double s = Math.min(speed, d / Math.max(dt, 1e-4));
                vx = dx / d * s;
                vz = dz / d * s;
            }
        }
        // separation: push out of every neighbour closer than `separation` (2 m grid)
        double sx = 0, sz = 0;
        for (int gx = -1; gx <= 1; gx++) {
            for (int gz = -1; gz <= 1; gz++) {
                List<Agent> cell = grid.get(key(cellOf(a.x) + gx, cellOf(a.z) + gz));
                if (cell == null) continue;
                for (Agent b : cell) {
                    if (b == a) continue;
                    double dx = a.x - b.x, dz = a.z - b.z, d = Math.sqrt(dx * dx + dz * dz);
                    if (d >= params.separation) continue;
                    if (d < 1e-4) { dx = (a.id % 7) - 3; dz = (a.id % 5) - 2; d = Math.max(1e-4, Math.sqrt(dx * dx + dz * dz)); }
                    double over = params.separation - Math.min(d, params.separation);
                    sx += dx / d * over * params.separationPush;
                    sz += dz / d * over * params.separationPush;
                }
            }
        }
        vx += sx;
        vz += sz;
        if (sx * sx + sz * sz > params.snapPush * params.snapPush) a.pushed = true;
        a.vx = vx;
        a.vz = vz;
        double nx = a.x + vx * dt, nz = a.z + vz * dt;
        // height: along the segment to the waypoint (both ends are on the nav mesh)
        if (w != null) {
            double before = plan(a.x, a.z, w[0], w[2]);
            double after = plan(nx, nz, w[0], w[2]);
            if (before > 1e-4) a.y += (w[1] - a.y) * Math.max(0.0, Math.min(1.0, (before - after) / before));
        }
        a.x = nx;
        a.z = nz;
        // facing: its travel when it runs, its target when it holds or swings
        double want;
        if (speed > 0 && vx * vx + vz * vz > 0.04) want = Math.atan2(-vx, -vz);
        else if (face) want = Math.atan2(-(fx - a.x), -(fz - a.z));
        else want = a.yaw;
        a.yaw = turn(a.yaw, want, params.turnRate * dt);
    }

    private void snapSome() {
        if (ground == null) return;
        int n = agents.size();
        int left = Math.min(params.snapsPerTick, n);
        for (int k = 0; k < n && left > 0; k++) {
            Agent a = agents.get((snapCursor + k) % n);
            if (!a.alive() || !a.pushed) continue;
            a.pushed = false;
            left--;
            snapsAsked++;
            double[] s = ground.snap(a.x, a.y, a.z);
            if (s == null) continue;
            a.x = s[0]; a.y = s[1]; a.z = s[2];
        }
        snapCursor = n == 0 ? 0 : (snapCursor + 1) % n;
    }

    private double nearestPlayer(double x, double z) {
        double best = Double.MAX_VALUE;
        for (int i = 0; i < np; i++) best = Math.min(best, plan(x, z, px[i], pz[i]));
        return best;
    }

    private Map<Long, List<Agent>> bucket() {
        Map<Long, List<Agent>> g = new HashMap<>();
        for (Agent a : agents) {
            if (!a.alive()) continue;
            g.computeIfAbsent(key(cellOf(a.x), cellOf(a.z)), k -> new ArrayList<>(4)).add(a);
        }
        return g;
    }

    private static int cellOf(double v) { return (int) Math.floor(v / 2.0); }

    private static long key(int cx, int cz) { return ((long) cx << 32) ^ (cz & 0xffffffffL); }

    public static double plan(double ax, double az, double bx, double bz) {
        double dx = ax - bx, dz = az - bz;
        return Math.sqrt(dx * dx + dz * dz);
    }

    static double turn(double from, double to, double max) {
        double d = to - from;
        while (d > Math.PI) d -= 2 * Math.PI;
        while (d < -Math.PI) d += 2 * Math.PI;
        if (Math.abs(d) <= max) return to;
        return from + Math.signum(d) * max;
    }
}
