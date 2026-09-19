package com.openworld.weapon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** Pins CS 1.6's grenade throw (W37). */
class ThrowArcTest {

    @Test
    void levelAimIsATenDegreeLobAt600UnitsPerSecond() {
        ThrowArc.Throw t = ThrowArc.fromAim(0.0);
        assertEquals(10.0, t.elevationDeg(), 1e-9);
        assertEquals(600.0 * ThrowArc.UNIT_M, t.speed(), 1e-9);
    }

    @Test
    void aimingUpThrowsHarderUntilTheCap() {
        assertTrue(ThrowArc.fromAim(20.0).speed() > ThrowArc.fromAim(0.0).speed());
        assertEquals(ThrowArc.MAX_SPEED, ThrowArc.fromAim(45.0).speed(), 1e-9);
        assertEquals(ThrowArc.MAX_SPEED, ThrowArc.fromAim(90.0).speed(), 1e-9);
    }

    @Test
    void straightUpAndDownStillMapToNinety() {
        assertEquals(90.0, ThrowArc.fromAim(90.0).elevationDeg(), 1e-9);
        assertEquals(-90.0, ThrowArc.fromAim(-90.0).elevationDeg(), 1e-9);
    }

    @Test
    void aimingDownIsASlowShortToss() {
        ThrowArc.Throw t = ThrowArc.fromAim(-30.0);
        assertTrue(t.elevationDeg() < -20.0);
        assertTrue(t.speed() < ThrowArc.fromAim(0.0).speed());
    }

    @Test
    void theLongestThrowIsAboutThirtyEightMetresWithoutDrag() {
        double best = 0.0;
        for (double a = -30.0; a <= 60.0; a += 1.0) best = Math.max(best, ThrowArc.flatRange(ThrowArc.fromAim(a), 1.4, 9.8));
        assertTrue(best > 34.0 && best < 40.0, "longest flat throw " + best + " m");
        assertTrue(ThrowArc.flatRange(ThrowArc.fromAim(0.0), 1.4, 9.8) < 14.0);
    }

    @Test
    void aBounceOffTheGroundKeepsLittleOfTheFallAndMostOfTheRoll() {
        ThrowArc.Bounce b = ThrowArc.bounce(10.0, -10.0, 0.0, 0.0, 1.0, 0.0);
        assertEquals(10.0 * 0.8, b.vx(), 1e-9);           // along the ground: only the 0.8 ground keep
        assertEquals(10.0 * 0.2 * 0.8, b.vy(), 1e-9);     // back up: restitution 0.2, then 0.8
        assertTrue(!b.rest());
    }

    @Test
    void aWallReflectsWithoutTheGroundKeep() {
        ThrowArc.Bounce b = ThrowArc.bounce(10.0, 0.0, 0.0, -1.0, 0.0, 0.0);
        assertEquals(-2.0, b.vx(), 1e-9);
    }

    @Test
    void slowOnTheGroundIsAtRest() {
        assertTrue(ThrowArc.bounce(0.3, -0.1, 0.0, 0.0, 1.0, 0.0).rest());
        assertTrue(!ThrowArc.bounce(0.3, 0.0, 0.0, -1.0, 0.0, 0.0).rest());   // a wall never rests it
    }
}
