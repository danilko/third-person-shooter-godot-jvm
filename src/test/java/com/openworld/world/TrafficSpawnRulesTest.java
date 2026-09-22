package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrafficSpawnRulesTest {
    private static boolean r(double x, double z, double vx, double vz) {
        return TrafficSpawnRules.refuses(x, z, 0, 0, vx, vz, 80, 6);
    }

    @Test
    void nothingIsBornCloseWhateverTheSpeed() {
        assertTrue(r(0, -50, 0, 0));
        assertTrue(r(60, 0, 0, 0));
        assertFalse(r(0, -100, 0, 0));            // standing still: 100 m away is fine
    }

    @Test
    void aFastDriverMeetsNothingNewAhead() {
        // 40 m/s north (-Z): the corridor runs 40*6 + 80 = 320 m ahead
        assertTrue(r(0, -150, 0, -40));
        assertTrue(r(0, -300, 0, -40));
        assertTrue(r(60, -200, 0, -40));          // a side street entering ahead
        assertFalse(r(0, -330, 0, -40));          // past the lead
        assertFalse(r(0, 150, 0, -40));           // behind
        assertFalse(r(250, -100, 0, -40));        // well off to the side
    }

    @Test
    void aSlowPlayerOnlyKeepsTheMinimum() {
        assertFalse(r(0, -120, 0, -2));           // walking: no corridor
        assertTrue(r(0, -120, 0, -10));           // 10 m/s: 60 + 80 = 140 m ahead is refused
        assertFalse(r(0, -150, 0, -10));
    }
}
