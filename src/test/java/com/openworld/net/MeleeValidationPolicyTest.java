package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.openworld.net.MeleeValidationPolicy.Limits;
import com.openworld.net.MeleeValidationPolicy.Verdict;
import org.junit.jupiter.api.Test;

class MeleeValidationPolicyTest {

    private static Verdict eval(long seq, long last, boolean budget, double origin, double aim, int step, int steps) {
        return MeleeValidationPolicy.evaluate(seq, last, budget, origin, aim, step, steps, Limits.DEFAULT);
    }

    @Test
    void anHonestSwingIsAccepted() {
        assertEquals(Verdict.ACCEPT, eval(7, 6, true, 0.2, 10, 1, 2));
        assertEquals(Verdict.ACCEPT, eval(0, -1, true, 0.0, 0.0, 0, 1));
    }

    @Test
    void replaysBadStepsAndBurstsAreRefused() {
        assertEquals(Verdict.STALE_SEQ, eval(6, 6, true, 0, 0, 0, 2));
        assertEquals(Verdict.BAD_STEP, eval(7, 6, true, 0, 0, 2, 2));
        assertEquals(Verdict.BAD_STEP, eval(7, 6, true, 0, 0, -1, 2));
        assertEquals(Verdict.TOO_FAST, eval(7, 6, false, 0, 0, 0, 2));
    }

    @Test
    void originAndAimMustBeNearTheHostCopy() {
        assertEquals(Verdict.ORIGIN_TOO_FAR, eval(7, 6, true, 3.0, 0, 0, 2));
        assertEquals(Verdict.ORIGIN_TOO_FAR, eval(7, 6, true, Double.NaN, 0, 0, 2));
        assertEquals(Verdict.AIM_DIVERGED, eval(7, 6, true, 0, 90, 0, 2));
    }

    @Test
    void theSwingRateIsTheShortestStep() {
        assertEquals(2.0, MeleeValidationPolicy.swingsPerSecond(0.5), 1e-9);
        assertEquals(10.0, MeleeValidationPolicy.swingsPerSecond(0.0), 1e-9);   // floored, never infinite
    }
}
