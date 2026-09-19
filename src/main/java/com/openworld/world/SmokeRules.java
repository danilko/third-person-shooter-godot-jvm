package com.openworld.world;

/**
 * The shape of a smoke grenade's cloud over its life, and whether it blocks a line of sight, engine-free
 * (SmokeRulesTest). The cloud is a sphere centred {@link #CENTRE_LIFT} above where the grenade went off:
 * it grows to full size over {@code growSeconds}, holds, and shrinks away over the last {@code fadeSeconds}.
 * A sight line is blocked when it passes through the sphere's core ({@link #CORE_FRACTION} of the radius);
 * the thin edge of the drawn smoke is see-through, and treating it as a wall would let an AI lose a target it
 * can plainly see.
 */
public final class SmokeRules {

    public static final double CENTRE_LIFT = 1.2;
    public static final double CORE_FRACTION = 0.85;

    private SmokeRules() { }

    /** The cloud's radius at {@code age} seconds. */
    public static double radiusAt(double age, double radius, double growSeconds, double lifeSeconds, double fadeSeconds) {
        if (age < 0 || age >= lifeSeconds) return 0.0;
        double grow = growSeconds <= 0 ? 1.0 : Math.min(1.0, age / growSeconds);
        double left = lifeSeconds - age;
        double fade = fadeSeconds <= 0 ? 1.0 : Math.min(1.0, left / fadeSeconds);
        return radius * Math.min(grow, fade);
    }

    /** Does the segment a -> b pass within {@code r} of centre c? */
    public static boolean segmentHitsSphere(double ax, double ay, double az, double bx, double by, double bz,
                                            double cx, double cy, double cz, double r) {
        if (r <= 0) return false;
        double dx = bx - ax, dy = by - ay, dz = bz - az;
        double len2 = dx * dx + dy * dy + dz * dz;
        double t = len2 < 1e-12 ? 0.0 : ((cx - ax) * dx + (cy - ay) * dy + (cz - az) * dz) / len2;
        t = Math.max(0.0, Math.min(1.0, t));
        double px = ax + dx * t - cx, py = ay + dy * t - cy, pz = az + dz * t - cz;
        return px * px + py * py + pz * pz <= r * r;
    }
}
