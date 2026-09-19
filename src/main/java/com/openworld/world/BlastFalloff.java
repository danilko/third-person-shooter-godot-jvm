package com.openworld.world;

/**
 * Engine-free blast arithmetic for {@code ExplosionManager} ({@code BlastFalloffTest}).
 *
 * <p>Damage falls off QUADRATICALLY with distance, to zero at the radius — the inverse-square shape of a
 * real blast, and what every explosion here has always used. The distance is to the target's nearest
 * SURFACE, not its origin: a car is 4 m long, so a rocket on its bumper is 2 m from its centre, and
 * measuring to the centre turned a direct hit into 64% damage.
 */
public final class BlastFalloff {
    private BlastFalloff() {}

    /** Damage at {@code distance} m from a blast of {@code maxDamage} over {@code radius} m. */
    public static float damage(float maxDamage, float radius, double distance) {
        if (radius <= 0f || distance >= radius) return 0f;
        double t = 1.0 - Math.max(0.0, distance) / radius;
        return (float) (maxDamage * t * t);
    }

    /** 0..1 strength at {@code distance} (1 at the centre), for the push. */
    public static float strength(float radius, double distance) {
        if (radius <= 0f || distance >= radius) return 0f;
        return (float) (1.0 - Math.max(0.0, distance) / radius);
    }

    /** Distance from point p to the axis-aligned box [min, max]; 0 inside it. All in the box's frame. */
    public static double distanceToBox(double px, double py, double pz,
                                       double minX, double minY, double minZ,
                                       double maxX, double maxY, double maxZ) {
        double dx = Math.max(Math.max(minX - px, 0.0), px - maxX);
        double dy = Math.max(Math.max(minY - py, 0.0), py - maxY);
        double dz = Math.max(Math.max(minZ - pz, 0.0), pz - maxZ);
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }
}
