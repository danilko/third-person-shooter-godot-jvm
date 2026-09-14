package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.openworld.net.ShotValidationPolicy.Limits;
import com.openworld.net.ShotValidationPolicy.RateBudget;
import com.openworld.net.ShotValidationPolicy.Verdict;
import org.junit.jupiter.api.Test;

class ShotValidationPolicyTest {

    private static Verdict eval(long seq, long last, boolean budget, double origin, double aim,
                                double clientSpread, double hostSpread) {
        return ShotValidationPolicy.evaluate(seq, last, budget, origin, aim, clientSpread, hostSpread, Limits.DEFAULT);
    }

    @Test
    void anHonestShotIsAccepted() {
        assertEquals(Verdict.ACCEPT, eval(5, 4, true, 0.3, 4.0, 1.2, 1.0));
        assertEquals(Verdict.ACCEPT, eval(0, -1, true, 0.0, 0.0, 0.0, 0.0));   // first shot, zero-spread weapon
    }

    @Test
    void aReplayedOrOutOfOrderCounterIsStale() {
        assertEquals(Verdict.STALE_SEQ, eval(4, 4, true, 0, 0, 1, 1));
        assertEquals(Verdict.STALE_SEQ, eval(3, 4, true, 0, 0, 1, 1));
    }

    @Test
    void anEmptyBudgetIsTooFast() {
        assertEquals(Verdict.TOO_FAST, eval(5, 4, false, 0, 0, 1, 1));
    }

    @Test
    void originAndAimMustBeNearTheHostCopy() {
        assertEquals(Verdict.ORIGIN_TOO_FAR, eval(5, 4, true, 1.5, 0, 1, 1));
        assertEquals(Verdict.ORIGIN_TOO_FAR, eval(5, 4, true, Double.NaN, 0, 1, 1));
        assertEquals(Verdict.AIM_DIVERGED, eval(5, 4, true, 0.2, 60, 1, 1));
        assertEquals(Verdict.AIM_DIVERGED, eval(5, 4, true, 0.2, Double.NaN, 1, 1));
    }

    @Test
    void theClientMayNotShrinkTheCone() {
        // Host estimate 2.0 deg (never includes bloom, so it is a floor): half of it minus slack is 0.95.
        assertEquals(Verdict.SPREAD_TOO_NARROW, eval(5, 4, true, 0, 0, 0.5, 2.0));
        assertEquals(Verdict.ACCEPT, eval(5, 4, true, 0, 0, 0.96, 2.0));
        // A client wider than the host (bloom the host cannot see) is always fine.
        assertEquals(Verdict.ACCEPT, eval(5, 4, true, 0, 0, 6.0, 2.0));
        assertEquals(Verdict.SPREAD_TOO_NARROW, eval(5, 4, true, 0, 0, Double.NaN, 2.0));
    }

    @Test
    void theBudgetAbsorbsABurstButCapsTheRate() {
        RateBudget b = new RateBudget();
        // Three pulls bunched into one arrival (a reliable resend) are fine; a fourth is not.
        assertTrue(b.tryConsume(0.0, 8));
        assertTrue(b.tryConsume(0.0, 8));
        assertTrue(b.tryConsume(0.0, 8));
        assertFalse(b.tryConsume(0.0, 8));
        // Sustained honest fire at the weapon's rate (8/s) never runs dry.
        RateBudget honest = new RateBudget();
        int refused = 0;
        for (int i = 0; i < 400; i++) if (!honest.tryConsume(i / 8.0, 8)) refused++;
        assertEquals(0, refused);
        // Twice the rate is refused about half the time once the burst is spent.
        RateBudget cheat = new RateBudget();
        int ok = 0;
        for (int i = 0; i < 400; i++) if (cheat.tryConsume(i / 16.0, 8)) ok++;
        assertTrue(ok < 400 * 0.62 && ok > 400 * 0.5, "accepted " + ok);
    }
}
