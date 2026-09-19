package com.openworld.world;

/**
 * How hard a flashbang blinds someone, engine-free (FlashRulesTest). CS's model: you must have a clear line from
 * the flash to your eyes (the caller's ray), the effect falls off with distance, and looking away cuts it but
 * never to nothing (the flash fills the room, not only your view).
 *
 * <pre>
 * strength = distanceFactor x facingFactor                           0..1
 * distanceFactor = 1 inside FULL_FRACTION of the radius, then linear to 0 at the radius
 * facingFactor   = 1 looking straight at it, BEHIND_FACTOR with it straight behind you, cosine-eased between
 * seconds        = maxSeconds x strength   (0 below MIN_STRENGTH: a flash that barely reaches does nothing)
 * </pre>
 */
public final class FlashRules {

    /** Inside this fraction of the radius the distance costs nothing. */
    public static final double FULL_FRACTION = 0.3;
    /** What is left with the flash directly behind you. */
    public static final double BEHIND_FACTOR = 0.25;
    /** Below this, nothing happens. */
    public static final double MIN_STRENGTH = 0.05;

    private FlashRules() { }

    /**
     * @param distance  metres from the flash to the eyes
     * @param radius    the flash's reach, metres
     * @param cosFacing cosine of the angle between where the eyes look and the direction to the flash
     */
    public static double strength(double distance, double radius, double cosFacing) {
        if (radius <= 0 || distance >= radius) return 0.0;
        double full = radius * FULL_FRACTION;
        double d = distance <= full ? 1.0 : 1.0 - (distance - full) / (radius - full);
        double c = Math.max(-1.0, Math.min(1.0, cosFacing));
        double f = BEHIND_FACTOR + (1.0 - BEHIND_FACTOR) * (c + 1.0) * 0.5;
        double s = Math.max(0.0, Math.min(1.0, d * f));
        return s < MIN_STRENGTH ? 0.0 : s;
    }

    public static double seconds(double strength, double maxSeconds) {
        return Math.max(0.0, strength) * maxSeconds;
    }
}
