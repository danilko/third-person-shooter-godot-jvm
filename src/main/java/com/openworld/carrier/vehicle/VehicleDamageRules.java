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
            "wing_lf", "wing_rf", "windscreen"};

    /** Damage points at which a part dents (starts blending its {@code dam} key), comes loose, and comes off. */
    public static final double DENT_AT = 15.0, LOOSE_AT = 55.0, OFF_AT = 110.0;
    /** A windscreen cracks early and shatters at the point a panel would only come loose. */
    public static final double GLASS_OFF_AT = 50.0;

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
