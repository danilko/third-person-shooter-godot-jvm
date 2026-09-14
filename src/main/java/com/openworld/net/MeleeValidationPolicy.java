package com.openworld.net;

/**
 * Pure host-side acceptance rules for a client's MSG_MELEE (PLAN.md N2) — engine-free and unit-tested, the
 * same shape as {@link ShotValidationPolicy}, whose latency reasoning applies unchanged: the host judges
 * against its interpolated, pose-less puppet, so every limit exists to refuse a swing nowhere near what the
 * body could have done (a buggy or forged client), never to adjudicate a close call.
 *
 * <p>Before N2 a client resolved its own swing and relayed the FINAL damage number, and the host checked
 * only that the fields were well-formed. Now the client reports the swing's inputs — where it started (the
 * chest), where it was aimed, which step of the chain — and the host runs the sweep itself.
 */
public final class MeleeValidationPolicy {

    public enum Verdict { ACCEPT, STALE_SEQ, TOO_FAST, ORIGIN_TOO_FAR, AIM_DIVERGED, BAD_STEP }

    /**
     * @param originToleranceM how far OUTSIDE the host copy's body volume the reported chest may be.
     * @param aimToleranceDeg  reported aim vs the host copy's replicated aim direction.
     */
    public record Limits(double originToleranceM, double aimToleranceDeg) {
        public static final Limits DEFAULT = new Limits(ShotValidationPolicy.Limits.DEFAULT.originToleranceM(),
                ShotValidationPolicy.Limits.DEFAULT.aimToleranceDeg());
    }

    private MeleeValidationPolicy() { }

    /**
     * @param swingSeq        the swing's counter from the client (shared with its shots — monotonic either way)
     * @param lastAcceptedSeq the last accepted melee counter for this sender + attacker, or -1
     * @param budgetOk        whether the attacker's swing {@link ShotValidationPolicy.RateBudget} had a token
     * @param originOutsideM  metres the reported chest lies outside the host copy's body volume
     * @param aimAngleDeg     angle between the reported aim and the host copy's aim direction (0 when unusable)
     * @param stepIndex       the step of the weapon's chain the client swung
     * @param stepCount       how many steps the host copy's weapon has
     */
    public static Verdict evaluate(long swingSeq, long lastAcceptedSeq, boolean budgetOk, double originOutsideM,
                                   double aimAngleDeg, int stepIndex, int stepCount, Limits limits) {
        if (swingSeq <= lastAcceptedSeq) return Verdict.STALE_SEQ;
        if (stepIndex < 0 || stepIndex >= Math.max(1, stepCount)) return Verdict.BAD_STEP;
        if (!budgetOk) return Verdict.TOO_FAST;
        if (!(originOutsideM <= limits.originToleranceM())) return Verdict.ORIGIN_TOO_FAR;   // NaN-safe
        if (!(aimAngleDeg <= limits.aimToleranceDeg())) return Verdict.AIM_DIVERGED;
        return Verdict.ACCEPT;
    }

    /**
     * Swings per second a weapon's budget refills at: one per its SHORTEST step (windup + active + recovery),
     * floored so a zero-length step cannot make the budget infinite.
     */
    public static double swingsPerSecond(double shortestStepSeconds) {
        return 1.0 / Math.max(0.1, shortestStepSeconds);
    }
}
