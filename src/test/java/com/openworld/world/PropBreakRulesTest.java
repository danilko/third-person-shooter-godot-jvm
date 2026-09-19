package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** The knock-down pole rules (PLAN.md 3.11). */
class PropBreakRulesTest {

    private static final double DT = 1.0 / 60.0;

    @Test
    void aPoleJustAheadOfTheBumperIsReached() {
        // car 1.2 m half-width, 2.3 m half-length, moving +Z at 15 m/s; pole 2.6 m ahead on the centreline
        assertTrue(PropBreakRules.reachesPole(0.0, 2.6, 1.2, 2.3, 0.18, 0.0, 15.0, DT));
        // 10 m ahead is not reached this step
        assertFalse(PropBreakRules.reachesPole(0.0, 10.0, 1.2, 2.3, 0.18, 0.0, 15.0, DT));
    }

    @Test
    void aPoleBesideTheCarIsNotReached() {
        assertFalse(PropBreakRules.reachesPole(2.5, 0.5, 1.2, 2.3, 0.18, 0.0, 15.0, DT));
        // but a car sliding SIDEWAYS into it is
        assertTrue(PropBreakRules.reachesPole(1.6, 0.0, 1.2, 2.3, 0.18, 12.0, 0.0, DT));
    }

    @Test
    void aPoleBehindTheMotionIsNotReached() {
        // pole at the rear bumper while driving forward: moving away from it
        assertFalse(PropBreakRules.reachesPole(0.0, -2.5, 1.2, 2.3, 0.18, 0.0, 15.0, DT));
        // reversing into it is
        assertTrue(PropBreakRules.reachesPole(0.0, -2.5, 1.2, 2.3, 0.18, 0.0, -6.0, DT));
        // standing still reaches nothing
        assertFalse(PropBreakRules.reachesPole(0.0, 2.4, 1.2, 2.3, 0.18, 0.0, 0.0, DT));
    }

    @Test
    void theReachGrowsWithSpeed() {
        // 3.5 m ahead: out of reach at 10 m/s, in reach at 40 m/s
        assertFalse(PropBreakRules.reachesPole(0.0, 3.2, 1.2, 2.3, 0.18, 0.0, 10.0, DT));
        assertTrue(PropBreakRules.reachesPole(0.0, 3.2, 1.2, 2.3, 0.18, 0.0, 40.0, DT));
    }

    @Test
    void breakSpeedIsAThreshold() {
        assertTrue(PropBreakRules.breaks(15.0, 5.0));
        assertTrue(PropBreakRules.breaks(5.0, 5.0));
        assertFalse(PropBreakRules.breaks(3.0, 5.0));
        assertFalse(PropBreakRules.breaks(50.0, 0.0), "a break speed of 0 means unbreakable");
    }

    @Test
    void aHeavierPoleCostsMoreSpeed() {
        double lamp = PropBreakRules.keepFraction(1200, 250);
        double signal = PropBreakRules.keepFraction(1200, 450);
        assertEquals(1200.0 / 1450.0, lamp, 1e-12);
        assertTrue(signal < lamp);
        assertTrue(lamp >= 0.7 && signal >= 0.7, "a car keeps at least 70 % through either pole");
        assertEquals(1.0, PropBreakRules.keepFraction(1200, 0), 1e-12);
        // the pole takes exactly the momentum the car lost
        double v = 15.0;
        assertEquals(1200 * v * (1 - lamp), PropBreakRules.poleImpulseScale(1200, 250) * v, 1e-9);
    }

    @Test
    void aViewerSeesInsideItsConeAndRange() {
        double[] cam = {0, 2, 0};
        double[] fwd = {0, 0, -1};
        double half = Math.toRadians(40);
        assertTrue(PropBreakRules.sees(cam, fwd, half, new double[]{0, 2, -30}, 80));
        assertFalse(PropBreakRules.sees(cam, fwd, half, new double[]{0, 2, 30}, 80), "behind the camera");
        assertFalse(PropBreakRules.sees(cam, fwd, half, new double[]{0, 2, -100}, 80), "past the hide distance");
        assertTrue(PropBreakRules.sees(cam, null, half, new double[]{0, 2, 30}, 80), "unknown facing sees all round");
    }

    @Test
    void itComesBackOnlyWhenTimeIsUpUnseenAndClear() {
        assertTrue(PropBreakRules.mayRestore(61, 60, false, false));
        assertFalse(PropBreakRules.mayRestore(59, 60, false, false));
        assertFalse(PropBreakRules.mayRestore(61, 60, true, false));
        assertFalse(PropBreakRules.mayRestore(61, 60, false, true));
    }
}
