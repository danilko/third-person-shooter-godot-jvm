package com.openworld.weapon;

/**
 * The grenade throw: how far up and how hard, from where the thrower aims (W37, CS 1.6's rule).
 *
 * <p>Engine-free on purpose: {@code ThrowableItem}'s real throw and its trajectory preview both ask
 * this one owner, so the drawn arc and the flight cannot disagree, and the host derives the same
 * throw from the aim direction MSG_LAUNCH already carries (no new field on the wire).
 *
 * <p>CS 1.6 (HLSDK {@code CHEGrenade::ThrowGrenade}) biases the view pitch 10 degrees upward --
 * compressing the upward half of the range and stretching the downward half so straight up and straight
 * down still map to +/-90 -- and throws at {@code (90 - biasedPitch) * 6} units/s, capped at 750. So
 * aiming UP throws both higher and harder, which is where its long throws come from; aiming level is a
 * 10-degree lob at 600 u/s; aiming down is a slow toss at the feet. Units are converted at CS scale,
 * 1 unit = 2.54 cm (a 72-unit player is 1.83 m). The runner's own velocity, which CS adds, is left
 * out: a host's copy of a remote player does not carry that velocity exactly, and the host and client
 * throws would drift apart.
 */
public final class ThrowArc {

    /** One CS unit in metres. */
    public static final double UNIT_M = 0.0254;
    /** CS 1.6's upward bias on the throw pitch, degrees. */
    public static final double PITCH_BIAS_DEG = 10.0;
    /** Throw speed per degree of (90 - biased pitch): 6 u/s. */
    public static final double SPEED_PER_DEG = 6.0 * UNIT_M;
    /** CS 1.6's cap, 750 u/s = 19.05 m/s. */
    public static final double MAX_SPEED = 750.0 * UNIT_M;

    private ThrowArc() {}

    /** A throw: the launch elevation in degrees (up positive) and the speed in m/s. */
    public record Throw(double elevationDeg, double speed) {}

    /**
     * @param aimElevationDeg the aim's elevation above horizontal, degrees (up positive, -90..90)
     */
    public static Throw fromAim(double aimElevationDeg) {
        double pitchDown = -clamp(aimElevationDeg, -90.0, 90.0);          // CS pitch: negative is up
        double biased = pitchDown < 0.0
                ? -PITCH_BIAS_DEG + pitchDown * ((90.0 - PITCH_BIAS_DEG) / 90.0)
                : -PITCH_BIAS_DEG + pitchDown * ((90.0 + PITCH_BIAS_DEG) / 90.0);
        double speed = Math.min(MAX_SPEED, (90.0 - biased) * SPEED_PER_DEG);
        return new Throw(-biased, speed);
    }

    // ── The bounce: CS 1.6's MOVETYPE_BOUNCE, not rigid-body physics (W38) ─────────────────────
    //
    // A tumbling rigid box cannot be predicted, so a preview drawn for one lands right and ends
    // wrong (measured on DebugWorld: first impact within 0.26 m of the ring, detonation 3-6 m past it).
    // CS never used rigid bodies for grenades: the engine's bounce clips the velocity against the
    // surface with an overbounce of 2 - friction (friction 0.8 -> 1.2, i.e. restitution 0.2), a hit
    // on the ground keeps 0.8 of the speed, and below 20 u/s on the ground it stops.

    /** Overbounce: the normal component is removed this many times over (1 = stick, 2 = mirror). */
    public static final double OVERBOUNCE = 1.2;
    /** Speed kept by a hit on walkable ground. */
    public static final double GROUND_KEEP = 0.8;
    /** Below this speed on the ground the grenade stops, m/s (20 u/s). */
    public static final double REST_SPEED = 20.0 * UNIT_M;
    /** A surface whose normal is at least this far up is ground (CS's 0.7). */
    public static final double GROUND_NORMAL_Y = 0.7;

    /** A bounce's result: the new velocity, and whether the grenade has come to rest. */
    public record Bounce(double vx, double vy, double vz, boolean rest) {}

    /** Bounce a velocity off a surface with unit normal (nx, ny, nz). */
    public static Bounce bounce(double vx, double vy, double vz, double nx, double ny, double nz) {
        double vn = vx * nx + vy * ny + vz * nz;
        if (vn < 0.0) {
            vx -= OVERBOUNCE * vn * nx;
            vy -= OVERBOUNCE * vn * ny;
            vz -= OVERBOUNCE * vn * nz;
        }
        boolean ground = ny >= GROUND_NORMAL_Y;
        if (ground) {
            vx *= GROUND_KEEP;
            vy *= GROUND_KEEP;
            vz *= GROUND_KEEP;
        }
        boolean rest = ground && Math.sqrt(vx * vx + vy * vy + vz * vz) < REST_SPEED;
        return rest ? new Bounce(0.0, 0.0, 0.0, true) : new Bounce(vx, vy, vz, false);
    }

    /** Flat-ground range of a throw from {@code height} metres up under gravity {@code g} (no drag). */
    public static double flatRange(Throw t, double height, double g) {
        double e = Math.toRadians(t.elevationDeg());
        double vx = t.speed() * Math.cos(e);
        double vy = t.speed() * Math.sin(e);
        double time = (vy + Math.sqrt(vy * vy + 2.0 * g * height)) / g;
        return vx * time;
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
