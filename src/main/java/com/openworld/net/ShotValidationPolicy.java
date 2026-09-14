package com.openworld.net;

/**
 * Pure host-side acceptance rules for a client's MSG_SHOT (PLAN.md N1) — extracted from the
 * engine-bound NetworkManager handler so they are unit-tested headless, the same pattern as
 * {@link PickupGrantPolicy}.
 *
 * <p>Before N1 the host checked only that the sender owned the shooter, then trusted the reported
 * origin and the post-spread direction of every pellet outright. A client now reports the
 * PRE-spread aim, the cone it used and a seed, and the host regenerates the pellets itself, so what
 * is left to judge is whether that aim and cone are plausible for the host's copy of the shooter.
 *
 * <p><b>Every tolerance here is about latency, not about exactness.</b> The host judges against its
 * own interpolated puppet — position and aim point ~50-100 ms stale, velocity (and so movement
 * spread) smoothed, and no bloom at all, because bloom only accumulates where {@code useWeapon} runs.
 * The limits exist to reject a shot nowhere near what the body could have fired (a buggy or forged
 * client), never to adjudicate a close call; a legitimate shot refused reads to the player as a dead
 * trigger, which is worse than the cheat it guards. Every refusal is counted by the caller.
 */
public final class ShotValidationPolicy {

    public enum Verdict { ACCEPT, STALE_SEQ, TOO_FAST, ORIGIN_TOO_FAR, AIM_DIVERGED, SPREAD_TOO_NARROW }

    /**
     * @param originToleranceM   client muzzle vs the host copy's muzzle. A sprinting body covers ~0.7 m
     *                           in 100 ms, plus snapshot interpolation.
     * @param aimToleranceDeg    client aim vs the host copy's replicated aim direction. The aim point
     *                           rides the 30 Hz snapshot on another channel, so a fast turn legitimately
     *                           reads tens of degrees apart for a frame or two.
     * @param spreadFloorFraction the client's cone must be at least this fraction of the host's own
     *                           estimate — the host sees base + movement + stance but never bloom, so its
     *                           estimate is a LOWER bound and a client under half of it shrank the cone.
     * @param spreadSlackDeg     absolute slack under that floor (covers a near-zero base spread).
     */
    public record Limits(double originToleranceM, double aimToleranceDeg,
                         double spreadFloorFraction, double spreadSlackDeg) {
        public static final Limits DEFAULT = new Limits(1.0, 35.0, 0.5, 0.05);
    }

    private ShotValidationPolicy() { }

    /**
     * @param shotSeq         the pull's counter from the client
     * @param lastAcceptedSeq the last counter accepted for this sender + shooter, or -1 for none
     * @param fireBudgetOk    whether the shooter's {@link RateBudget} had a token for this pull
     * @param originDistM     distance from the reported origin to the host copy's muzzle
     * @param aimAngleDeg     angle between the reported aim and the host copy's aim direction
     *                        (pass 0 when the host copy has no usable aim point)
     * @param clientSpreadDeg the full cone angle the client used
     * @param hostSpreadDeg   the host copy's own {@code getCurrentSpreadDeg()}
     */
    public static Verdict evaluate(long shotSeq, long lastAcceptedSeq, boolean fireBudgetOk,
                                   double originDistM, double aimAngleDeg,
                                   double clientSpreadDeg, double hostSpreadDeg, Limits limits) {
        // Channel 1 is reliable AND ordered, so a counter that does not advance is a replay.
        if (shotSeq <= lastAcceptedSeq) return Verdict.STALE_SEQ;
        if (!fireBudgetOk) return Verdict.TOO_FAST;
        if (!(originDistM <= limits.originToleranceM)) return Verdict.ORIGIN_TOO_FAR;   // NaN-safe
        if (!(aimAngleDeg <= limits.aimToleranceDeg)) return Verdict.AIM_DIVERGED;
        double floor = Math.max(0.0, hostSpreadDeg) * limits.spreadFloorFraction - limits.spreadSlackDeg;
        if (!(clientSpreadDeg >= floor)) return Verdict.SPREAD_TOO_NARROW;
        return Verdict.ACCEPT;
    }

    /**
     * Fire-rate budget for one shooter's weapon: a token bucket refilled at the weapon's own fire rate.
     * A plain minimum interval would refuse legitimate shots — reliable delivery bunches packets after a
     * resend, so two honest pulls 125 ms apart can arrive together — while a bucket with a small burst
     * absorbs that and still caps the sustained rate. Time is passed in, so tests need no clock.
     */
    public static final class RateBudget {
        /** Pulls that may arrive back to back. */
        public static final double BURST = 3.0;
        /** Refill headroom over the weapon's nominal rate (frame quantisation of the client's fire timer). */
        public static final double RATE_SLACK = 1.15;

        private double tokens = BURST;
        private double lastSeconds = Double.NaN;

        /** Takes one token if available, refilling at {@code shotsPerSecond * RATE_SLACK} since last call. */
        public boolean tryConsume(double nowSeconds, double shotsPerSecond) {
            if (!Double.isNaN(lastSeconds)) {
                double dt = Math.max(0.0, nowSeconds - lastSeconds);
                tokens = Math.min(BURST, tokens + dt * Math.max(0.0, shotsPerSecond) * RATE_SLACK);
            }
            lastSeconds = nowSeconds;
            if (tokens < 1.0) return false;
            tokens -= 1.0;
            return true;
        }
    }
}
