package com.openworld.camera;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Pins the scope sway's rules (PLAN.md 2.7 piece 2): no drift unless scoped with a swaying weapon,
 * the drift bounded by the amplitude, a held breath that steadies it and runs out, a winded penalty
 * that is worse than never holding, and a hold that needs a fresh press.
 */
class ScopeSwayTest {

    private static final double DT = 1.0 / 60.0;
    private static final double AMP = 0.5;

    /** Peak |yaw| and |pitch| over a window of {@code seconds}. */
    private static double[] peaks(ScopeSway s, double seconds, boolean scoped, boolean hold, double steadiness) {
        double py = 0, pp = 0;
        for (int i = 0; i < (int) (seconds / DT); i++) {
            s.tick(DT, scoped, hold, AMP, steadiness);
            py = Math.max(py, Math.abs(s.yaw()));
            pp = Math.max(pp, Math.abs(s.pitch()));
        }
        return new double[] {py, pp};
    }

    private static void run(ScopeSway s, double seconds, boolean scoped, boolean hold) {
        for (int i = 0; i < (int) (seconds / DT); i++) s.tick(DT, scoped, hold, AMP, 1.0);
    }

    @Test
    void noDriftUnlessScoped() {
        ScopeSway s = new ScopeSway();
        double[] p = peaks(s, 10, false, false, 1.0);
        assertEquals(0.0, p[0], 0.0);
        assertEquals(0.0, p[1], 0.0);
    }

    @Test
    void noDriftForAWeaponThatDoesNotSway() {
        ScopeSway s = new ScopeSway();
        for (int i = 0; i < 600; i++) {
            s.tick(DT, true, false, 0.0, 1.0);
            assertEquals(0.0, s.yaw(), 0.0);
        }
    }

    @Test
    void scopedDriftIsBoundedByTheAmplitudeAndReachesMostOfIt() {
        ScopeSway s = new ScopeSway();
        run(s, 1, true, false);
        double[] p = peaks(s, 20, true, false, 1.0);
        assertTrue(p[0] <= AMP + 1e-9, "yaw " + p[0]);
        assertTrue(p[1] <= 0.7 * AMP + 1e-9, "pitch " + p[1]);
        assertTrue(p[0] > 0.8 * AMP, "yaw only reached " + p[0]);
    }

    @Test
    void theScopeComingUpStartsFromRest() {
        ScopeSway s = new ScopeSway();
        run(s, 3, false, false);
        s.tick(DT, true, false, AMP, 1.0);
        // One tick of easing is 1 - e^(-FOLLOW_RATE / 60) ~ 8% of the level, so a first step bigger
        // than that is the level being switched rather than eased.
        double oneTick = 1.0 - Math.exp(-ScopeSway.FOLLOW_RATE * DT);
        assertTrue(Math.abs(s.yaw()) <= oneTick * AMP + 1e-9, "first scoped tick jumped to " + s.yaw());
    }

    @Test
    void holdingBreathSteadiesItAndSpendsTheReserve() {
        ScopeSway s = new ScopeSway();
        run(s, 2, true, false);
        double open = peaks(s, 8, true, false, 1.0)[0];
        s.tick(DT, true, true, AMP, 1.0);
        assertTrue(s.holding());
        run(s, 0.8, true, true);
        double held = peaks(s, 2.5, true, true, 1.0)[0];
        assertTrue(held < 0.2 * open, "held " + held + " vs open " + open);
        assertTrue(s.breath() < 0.25, "breath " + s.breath());
    }

    @Test
    void holdingTooLongWindsTheShooterWorseThanNeverHolding() {
        ScopeSway s = new ScopeSway();
        run(s, 2, true, false);
        double open = peaks(s, 8, true, false, 1.0)[0];
        s.tick(DT, true, true, AMP, 1.0);
        run(s, s.holdSeconds + 0.1, true, true);
        assertTrue(s.winded());
        assertFalse(s.holding());
        double winded = peaks(s, 2.0, true, true, 1.0)[0];
        assertTrue(winded > 1.2 * open, "winded " + winded + " vs open " + open);
    }

    @Test
    void aHoldNeedsAFreshPressAfterTheWindedSpell() {
        ScopeSway s = new ScopeSway();
        s.tick(DT, true, true, AMP, 1.0);
        run(s, s.holdSeconds + 0.1, true, true);
        assertTrue(s.winded());
        // Key still down through the whole recovery: no second hold starts by itself.
        run(s, s.recoverSeconds, true, true);
        assertFalse(s.winded());
        assertFalse(s.holding());
        // Release and press again: now it holds.
        s.tick(DT, true, false, AMP, 1.0);
        s.tick(DT, true, true, AMP, 1.0);
        assertTrue(s.holding());
    }

    @Test
    void theReserveRefillsWhenNotHolding() {
        ScopeSway s = new ScopeSway();
        s.tick(DT, true, true, AMP, 1.0);
        run(s, 2.0, true, true);
        double spent = s.breath();
        run(s, s.recoverSeconds, false, false);
        assertTrue(spent < 0.6);
        assertEquals(1.0, s.breath(), 1e-9);
    }

    @Test
    void aKeyAlreadyHeldWhenTheScopeComesUpIsNotAPress() {
        ScopeSway s = new ScopeSway();
        s.observeInput(true);               // held while unscoped (a skipped, at-rest tick)
        s.tick(DT, true, true, AMP, 1.0);   // the scope comes up with the key still down
        assertFalse(s.holding());
        s.tick(DT, true, false, AMP, 1.0);
        s.tick(DT, true, true, AMP, 1.0);
        assertTrue(s.holding());
    }

    @Test
    void unscopingEndsAHold() {
        ScopeSway s = new ScopeSway();
        s.tick(DT, true, true, AMP, 1.0);
        assertTrue(s.holding());
        s.tick(DT, false, true, AMP, 1.0);
        assertFalse(s.holding());
    }

    @Test
    void steadinessScalesTheDrift() {
        ScopeSway a = new ScopeSway();
        ScopeSway b = new ScopeSway();
        double pa = peaks(a, 12, true, false, 1.0)[0];
        double pb = peaks(b, 12, true, false, 0.35)[0];
        assertEquals(0.35, pb / pa, 1e-6);
    }
}
