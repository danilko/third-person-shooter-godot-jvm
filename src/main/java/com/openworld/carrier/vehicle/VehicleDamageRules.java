package com.openworld.carrier.vehicle;

/**
 * The rules of a car that comes apart in pieces, GTA III / San Andreas style — engine-free so they can be
 * unit-tested ({@code VehicleDamageRulesTest}). {@link VehicleDamageModel} is the Godot node that applies them.
 *
 * <p>The model is SA's component model: a car is a set of NAMED parts (the dff frames {@code bonnet},
 * {@code boot}, {@code door_lf}, {@code bump_front}, … — the names {@code blender/tools/build_vehicle.py}
 * exports), and each part walks one way through four states:
 * <pre>
 *   OK ──dent──▶ DENTED ──loosen──▶ LOOSE ──break──▶ OFF
 * </pre>
 * DENTED blends the part's {@code dam} shape key in (SA swapped an {@code _ok} mesh for a {@code _dam} one; the
 * key gives the in-between for free), LOOSE lets a hinged part swing (a door flaps, a bonnet lifts, a bumper hangs
 * from one end), OFF drops it as debris. Which states a part can reach depends on its {@link Kind}: a wing only
 * dents, a windscreen cracks and then shatters, the chassis never changes state (its dents follow the car's health).
 *
 * <p><b>States only ever go up</b>, which is what makes the network part free of conflicts: the peer that simulates
 * the car (crashes) and the host (bullets) may each advance a part, and merging is a per-slot MAX
 * ({@link #merge}). The mask rides the vehicle snapshot like the flat-tyre bits do.
 */
public final class VehicleDamageRules {
    private VehicleDamageRules() {}

    public static final int OK = 0, DENTED = 1, LOOSE = 2, OFF = 3;

    public enum Kind { CHASSIS, BONNET, BOOT, BUMPER, DOOR, WING, WINDSCREEN, WHEEL, UNKNOWN }

    /**
     * The mask's slot order. APPEND-ONLY: a slot index is on the wire. 2 bits per slot, 16 slots in an int.
     * Rear doors are listed so a four-door body needs no wire change.
     */
    public static final String[] SLOTS = {
            "bonnet", "boot", "bump_front", "bump_rear", "door_lf", "door_rf", "door_lr", "door_rr",
            "wing_lf", "wing_rf", "windscreen",
            // the windows (panes), appended 2026-09-28: each door's window and the body's own glass (rear window,
            // quarter lights; on a placeholder car the whole greenhouse). The windscreen keeps its part slot.
            "win_lf", "win_rf", "win_lr", "win_rr", "win_body"};

    /** Damage points at which a part dents (starts blending its {@code dam} key), comes loose, and comes off. */
    public static final double DENT_AT = 15.0, LOOSE_AT = 55.0, OFF_AT = 110.0;
    /** A windscreen cracks early and shatters at the point a panel would only come loose. */
    public static final double GLASS_OFF_AT = 50.0;

    /**
     * A window (user 2026-09-28). ORDINARY glass (every car, {@code armor} 0) gives ONE hit of protection: the first
     * light round, a melee blow, a crash or a blast shatters it and stops there, and after that the opening lets
     * everything through. A round of at least {@link #PANE_PIERCE_AT} (a rifle, the large pistol, the revolver, the
     * sniper rifle) breaks it and carries on at full damage. A shotgun at close range puts its first pellet into the
     * glass and the rest through the hole it made.
     * ARMOURED glass (a special vehicle's {@code VehicleConfig.glassArmor} > 0) is a pool of weapon damage instead:
     * rounds stop in it until it is used up, and the round that uses it up carries on with what it had left.
     */
    public static final double PANE_PIERCE_AT = 20.0;

    public static int paneStateFor(double damage, double armor) {
        if (armor <= 0.0) return damage > 0.0 ? OFF : OK;          // ordinary glass: one hit breaks it
        if (damage >= armor) return OFF;                            // armour used up
        return damage > 0.0 ? DENTED : OK;
    }

    /**
     * The damage a round carries through a window that has taken {@code taken} so far (it is still standing): 0 means
     * the glass stopped it.
     */
    public static double carriedThrough(double taken, double armor, double round) {
        if (armor <= 0.0) return round >= PANE_PIERCE_AT ? round : 0.0;
        double left = Math.max(0.0, armor - taken);
        return Math.max(0.0, round - left);
    }

    /** Crash points at a window that shatter it, on top of its armour: the point a door would come loose. */
    public static final double PANE_CRASH_AT = LOOSE_AT;

    /** The mask slot of the window in a part: a door's own window, the body's glass, or the windscreen's slot. */
    public static int paneSlotOf(String partName) {
        if (partName == null) return -1;
        if (partName.startsWith("door_")) return slotOf("win_" + partName.substring(5));
        if (partName.equals("chassis")) return slotOf("win_body");
        if (partName.equals("windscreen")) return slotOf("windscreen");
        return -1;
    }

    /**
     * Where a ray from {@code o} along {@code d} meets the triangle (a, b, c): the distance along the ray, or -1.
     * Both faces count (Möller–Trumbore, no culling): a bullet meets a window from either side.
     */
    public static double rayTriangle(double[] o, double[] d, double[] a, double[] b, double[] c) {
        double[] e1 = {b[0] - a[0], b[1] - a[1], b[2] - a[2]};
        double[] e2 = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
        double[] pv = cross(d, e2);
        double det = dot(e1, pv);
        if (Math.abs(det) < 1e-12) return -1;
        double inv = 1.0 / det;
        double[] tv = {o[0] - a[0], o[1] - a[1], o[2] - a[2]};
        double u = dot(tv, pv) * inv;
        if (u < 0 || u > 1) return -1;
        double[] qv = cross(tv, e1);
        double v = dot(d, qv) * inv;
        if (v < 0 || u + v > 1) return -1;
        double t = dot(e2, qv) * inv;
        return t >= 0 ? t : -1;
    }

    /** Distance along a ray (local frame) at which it leaves the box {@code min}/{@code max}; 0 if it misses. */
    public static double boxExit(double[] o, double[] d, double[] min, double[] max) {
        double tNear = -1e18, tFar = 1e18;
        for (int k = 0; k < 3; k++) {
            if (Math.abs(d[k]) < 1e-12) {
                if (o[k] < min[k] || o[k] > max[k]) return 0.0;
                continue;
            }
            double t1 = (min[k] - o[k]) / d[k], t2 = (max[k] - o[k]) / d[k];
            tNear = Math.max(tNear, Math.min(t1, t2));
            tFar = Math.min(tFar, Math.max(t1, t2));
        }
        return tFar >= Math.max(tNear, 0.0) ? tFar : 0.0;
    }

    /** Below this change of velocity (m/s) a contact is a scrape, not a crash: no part damage. */
    public static final double MIN_IMPACT_DV = 2.5;
    /** Damage points per m/s of change of velocity above {@link #MIN_IMPACT_DV}, at the point of impact. */
    public static final double IMPACT_POINTS_PER_DV = 14.0;
    /** A part further than this (m) from the impact point takes nothing from it; nearer, a linear share. */
    public static final double IMPACT_RADIUS = 0.9;

    public static Kind kindOf(String name) {
        if (name == null) return Kind.UNKNOWN;
        if (name.equals("chassis")) return Kind.CHASSIS;
        if (name.equals("bonnet")) return Kind.BONNET;
        if (name.equals("boot")) return Kind.BOOT;
        if (name.startsWith("bump_")) return Kind.BUMPER;
        if (name.startsWith("door_")) return Kind.DOOR;
        if (name.startsWith("wing_")) return Kind.WING;
        if (name.equals("windscreen")) return Kind.WINDSCREEN;
        if (name.startsWith("wheel_")) return Kind.WHEEL;
        return Kind.UNKNOWN;
    }

    public static int slotOf(String name) {
        for (int i = 0; i < SLOTS.length; i++) if (SLOTS[i].equals(name)) return i;
        return -1;
    }

    /** The state a part of this kind is in after {@code damage} points. */
    public static int stateFor(Kind kind, double damage) {
        switch (kind) {
            case CHASSIS, WHEEL, UNKNOWN: return OK;
            case WING: return damage >= DENT_AT ? DENTED : OK;
            case WINDSCREEN:
                if (damage >= GLASS_OFF_AT) return OFF;
                return damage >= DENT_AT ? DENTED : OK;
            default:
                if (damage >= OFF_AT) return OFF;
                if (damage >= LOOSE_AT) return LOOSE;
                return damage >= DENT_AT ? DENTED : OK;
        }
    }

    /** The damage points that put a part of this kind exactly into {@code state} (for a replicated state). */
    public static double damageFor(Kind kind, int state) {
        if (state >= OFF) return kind == Kind.WINDSCREEN ? GLASS_OFF_AT : OFF_AT;
        if (state == LOOSE) return LOOSE_AT;
        if (state == DENTED) return DENT_AT;
        return 0.0;
    }

    /** The {@code dam} shape key weight for a part: 0 until it dents, full by the time it would come loose. */
    public static double dentWeight(double damage) {
        if (damage <= 0.0) return 0.0;
        return Math.min(1.0, 0.25 + 0.75 * damage / LOOSE_AT) * (damage >= DENT_AT ? 1.0 : damage / DENT_AT);
    }

    /** The chassis' {@code dam} weight from the car's health fraction: dents begin once a tenth is gone. */
    public static double chassisWeight(double healthFraction) {
        return clamp((0.9 - healthFraction) / 0.8, 0.0, 1.0);
    }

    // ── the state mask ───────────────────────────────────────────────────────────────────────────────

    public static int stateAt(int mask, int slot) {
        return slot < 0 || slot >= 16 ? OK : (mask >>> (slot * 2)) & 3;
    }

    public static int withState(int mask, int slot, int state) {
        if (slot < 0 || slot >= 16) return mask;
        int shift = slot * 2;
        return (mask & ~(3 << shift)) | ((state & 3) << shift);
    }

    /** Per-slot MAX of two masks: a part is as broken as the most broken report of it says. */
    public static int merge(int a, int b) {
        int out = 0;
        for (int s = 0; s < 16; s++) out = withState(out, s, Math.max(stateAt(a, s), stateAt(b, s)));
        return out;
    }

    // ── impact attribution ───────────────────────────────────────────────────────────────────────────

    /** The longest one crash window may run (physics steps, 0.25 s at 60 Hz) before it is scored and a new one starts. */
    public static final int MAX_CRASH_STEPS = 15;

    /**
     * How hard a crash was: the contact impulses summed over its steps, never more than the car's real change of
     * velocity across them. The impulse sum alone is not a crash measure: a car held against an obstacle (a planter,
     * a wall, a car in front) under throttle gets a fresh contact impulse EVERY step - its engine being pushed back -
     * and those add up without limit while the car does not change speed at all. Measured, a 10 m/s bump into a kerb
     * planter scored 33 m/s (184 hp of a 500 hp car) because the driver kept the throttle on. The velocity change is
     * the physical answer; the impulse sum stays as the upper bound so the engine and gravity inside the window are
     * never counted as a crash either.
     */
    public static double crashDeltaV(double impulseSum, double vStartX, double vStartY, double vStartZ,
                                     double vEndX, double vEndY, double vEndZ) {
        double dx = vEndX - vStartX, dy = vEndY - vStartY, dz = vEndZ - vStartZ;
        return Math.min(impulseSum, Math.sqrt(dx * dx + dy * dy + dz * dz));
    }

    /** Crash damage points at the point of impact for a change of velocity {@code deltaV} (m/s). */
    public static double impactPoints(double deltaV) {
        return Math.max(0.0, deltaV - MIN_IMPACT_DV) * IMPACT_POINTS_PER_DV;
    }

    /**
     * The fraction of an impact's points a part takes: 1 when the impact point is inside the part's box
     * ({@code min}/{@code max}, vehicle-local), falling linearly to 0 at {@link #IMPACT_RADIUS} outside it.
     */
    public static double share(double[] min, double[] max, double[] p) {
        double d2 = 0.0;
        for (int k = 0; k < 3; k++) {
            double d = p[k] < min[k] ? min[k] - p[k] : (p[k] > max[k] ? p[k] - max[k] : 0.0);
            d2 += d * d;
        }
        return Math.max(0.0, 1.0 - Math.sqrt(d2) / IMPACT_RADIUS);
    }

    // ── the hinge ────────────────────────────────────────────────────────────────────────────────────

    /** How far a loose part of this kind swings open, in radians. */
    public static double maxOpen(Kind kind) {
        switch (kind) {
            case DOOR: return Math.toRadians(70);
            case BONNET: return Math.toRadians(60);
            case BOOT: return Math.toRadians(65);
            case BUMPER: return Math.toRadians(28);
            default: return 0.0;
        }
    }

    /**
     * The hinge axis of a part, vehicle-local, chosen so a POSITIVE angle opens it: a door's free edge swings
     * OUTWARD, a bonnet's or boot's free edge LIFTS, a bumper's free end DROPS. {@code lever} runs from the hinge
     * to the part's centre; {@code centreX} is the part's centre across the car (its side). Vehicle frame is
     * Godot's: +X right, +Y up, -Z forward. Returns null for a part that does not swing.
     */
    public static double[] openAxis(Kind kind, double[] lever, double centreX) {
        double[] axis, want;
        switch (kind) {
            case DOOR:   axis = new double[]{0, 1, 0}; want = new double[]{Math.signum(centreX), 0, 0}; break;
            case BONNET:
            case BOOT:   axis = new double[]{1, 0, 0}; want = new double[]{0, 1, 0}; break;
            case BUMPER: axis = new double[]{0, 0, 1}; want = new double[]{0, -1, 0}; break;
            default: return null;
        }
        double[] swing = cross(axis, lever);
        if (dot(swing, want) < 0) for (int k = 0; k < 3; k++) axis[k] = -axis[k];
        return axis;
    }

    /**
     * Angular acceleration (rad/s²) about {@code axis} of a part treated as a point mass at {@code lever} from its
     * hinge, under the specific force {@code force} (m/s², vehicle-local: gravity minus the car's own acceleration,
     * plus air). Positive opens it.
     */
    public static double hingeAccel(double[] axis, double[] lever, double[] force) {
        double l2 = dot(lever, lever);
        if (l2 < 1e-6) return 0.0;
        return dot(cross(lever, force), axis) / l2;
    }

    /**
     * One step of a free hinge: {@code {angle, velocity}} integrated under {@code accel} with viscous damping,
     * held between shut (0) and {@code max}. Hitting a stop bounces back at {@code restitution} — a loose door
     * slams, it does not stick.
     */
    public static double[] stepHinge(double angle, double velocity, double accel, double damping,
                                     double max, double restitution, double dt) {
        velocity += (accel - damping * velocity) * dt;
        angle += velocity * dt;
        if (angle < 0.0) { angle = 0.0; if (velocity < 0) velocity = -velocity * restitution; }
        if (angle > max) { angle = max; if (velocity > 0) velocity = -velocity * restitution; }
        return new double[]{angle, velocity};
    }

    // ── small vector helpers ─────────────────────────────────────────────────────────────────────────

    static double dot(double[] a, double[] b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

    static double[] cross(double[] a, double[] b) {
        return new double[]{a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
    }

    static double clamp(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }
}
