package com.openworld.weapon;

/**
 * THE one owner of a firearm's cone (PLAN.md 2.8 item 3). Engine-free, so every rule is unit-tested
 * ({@code AccuracyTest}); {@link FirearmItem} feeds it the live inputs, and the shot, the crosshair and
 * the host's N1 floor all read the same answers, so none of them can drift from the others.
 *
 * <p>The cone, in degrees (full angle):
 * <pre>
 *   (spread + bloom + movementPenalty(speed, maxSpeed)) x posture x (aimed ? 1 : hipfire)
 * </pre>
 *
 * <p><b>The standing threshold</b> is the CS rule: below {@code standingFraction} of the holder's
 * current max speed (0.34 by default — CS:GO/CS2 treat a weapon as fully accurate under 34% of its max
 * speed) movement costs nothing, and above it the penalty ramps linearly to the full
 * {@code perMps x maxSpeed} at max speed, continuing at {@code perMps x speed} beyond it (a slide, a
 * fall). Expressed as a FRACTION so it scales with anything that lowers the max — a scoped slowdown
 * lowers the threshold with it. Before this, the cone grew {@value #MOVEMENT_SPREAD_PER_MPS} deg per
 * m/s from zero, so the slide after releasing a key, or 0.7 m/s of steering jitter on a slope, widened
 * a "pinpoint" scoped shot (probe_sniper_live: every miss was a moving or just-stopped shot).
 *
 * <p>Speed is HORIZONTAL: a body standing on a slope carries a vertical velocity from the floor snap
 * that is not movement, and a falling body already pays the airborne multiplier.
 */
public final class Accuracy {

    private Accuracy() {}

    /** Degrees of cone per m/s of horizontal speed at the top of the ramp. */
    public static final double MOVEMENT_SPREAD_PER_MPS = 0.03;

    /** CS: fully accurate below 34% of the holder's max speed. */
    public static final double DEFAULT_STANDING_FRACTION = 0.34;

    /** Reference speed (m/s, about a sprint) that defines the top of the crosshair envelope. */
    public static final double CROSSHAIR_REF_SPEED = 6.0;

    public static final double CROUCH_MULT = 0.7;
    public static final double CRAWL_MULT = 0.5;
    public static final double AIRBORNE_MULT = 2.0;
    /** Treading water is unstable — shooting from the surface is less accurate than on land. */
    public static final double SWIM_MULT = 1.8;

    /** How the holder is supported. SWIM is its own case: a swimmer is off the floor but not airborne. */
    public enum Posture { UPRIGHT, CROUCH, CRAWL, SWIM, AIRBORNE }

    /** The weapon's accuracy numbers. {@code hipfireMultiplier} 1 = no penalty for not aiming. */
    public record Tuning(double spread, double bloomPerShot, double bloomDecaySpeed, double bloomMax,
                         double standingFraction, double hipfireMultiplier) {}

    public static double postureMultiplier(Posture posture) {
        return switch (posture) {
            case CROUCH -> CROUCH_MULT;
            case CRAWL -> CRAWL_MULT;
            case SWIM -> SWIM_MULT;
            case AIRBORNE -> AIRBORNE_MULT;
            default -> 1.0;
        };
    }

    /**
     * Degrees added by movement. {@code maxSpeed <= 0} (unknown holder) means no threshold: the plain
     * linear term.
     */
    public static double movementPenalty(double speed, double maxSpeed, double standingFraction) {
        if (speed <= 0.0) return 0.0;
        if (maxSpeed <= 0.0) return MOVEMENT_SPREAD_PER_MPS * speed;
        if (speed >= maxSpeed) return MOVEMENT_SPREAD_PER_MPS * speed;
        double threshold = Math.max(0.0, Math.min(1.0, standingFraction)) * maxSpeed;
        if (speed <= threshold) return 0.0;
        if (threshold >= maxSpeed) return 0.0;
        return MOVEMENT_SPREAD_PER_MPS * maxSpeed * (speed - threshold) / (maxSpeed - threshold);
    }

    /** The live cone, degrees. */
    public static double cone(Tuning t, double bloom, double speed, double maxSpeed, Posture posture,
                              boolean aimed) {
        double c = (t.spread() + Math.max(0.0, bloom) + movementPenalty(speed, maxSpeed, t.standingFraction()))
                * postureMultiplier(posture);
        return aimed ? c : c * Math.max(1.0, t.hipfireMultiplier());
    }

    /**
     * The narrowest cone the weapon can have in a stance — base spread x posture, no movement, no bloom,
     * no airborne and no hipfire (PLAN.md N1). The host validates a client's reported cone against this:
     * a host puppet is never on the floor and cannot see the client's aim state, and a floor that included
     * either would refuse an honest shot. AIRBORNE is treated as UPRIGHT here for that reason.
     */
    public static double minimum(Tuning t, Posture posture) {
        Posture p = posture == Posture.AIRBORNE ? Posture.UPRIGHT : posture;
        return t.spread() * postureMultiplier(p);
    }

    /**
     * 0..1 opening of the reticle: the cone over this weapon's worst realistic on-ground cone (full bloom,
     * a sprint, upright, aimed), so every weapon shares one pixel range. Airborne and hipfire clamp to 1.
     */
    public static double crosshairFraction(Tuning t, double cone) {
        double worst = t.spread() + t.bloomMax() + CROSSHAIR_REF_SPEED * MOVEMENT_SPREAD_PER_MPS;
        if (worst <= 0.0) return 0.0;
        return Math.max(0.0, Math.min(1.0, cone / worst));
    }

    /** Bloom after {@code dt} seconds of decay. */
    public static double decayBloom(double bloom, Tuning t, double dt) {
        return Math.max(0.0, bloom - t.bloomDecaySpeed() * dt);
    }

    /** Bloom after a shot: what THIS shot does to the NEXT one (W31 — never to itself). */
    public static double bloomAfterShot(double bloom, Tuning t) {
        return Math.min(bloom + t.bloomPerShot(), t.bloomMax());
    }
}
