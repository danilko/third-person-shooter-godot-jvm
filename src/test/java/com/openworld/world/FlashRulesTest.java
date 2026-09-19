package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlashRulesTest {
    @Test
    void fullStrengthCloseAndLookingAtIt() {
        assertEquals(1.0, FlashRules.strength(2.0, 20.0, 1.0), 1e-9);
        assertEquals(5.0, FlashRules.seconds(FlashRules.strength(0.0, 20.0, 1.0), 5.0), 1e-9);
    }

    @Test
    void fallsToNothingAtTheRadius() {
        assertEquals(0.0, FlashRules.strength(20.0, 20.0, 1.0), 1e-9);
        assertEquals(0.0, FlashRules.strength(25.0, 20.0, 1.0), 1e-9);
        double mid = FlashRules.strength(13.0, 20.0, 1.0);          // halfway through the fall-off band
        assertEquals(0.5, mid, 1e-9);
    }

    @Test
    void lookingAwayCutsItButNotToNothing() {
        double facing = FlashRules.strength(3.0, 20.0, 1.0);
        double side = FlashRules.strength(3.0, 20.0, 0.0);
        double behind = FlashRules.strength(3.0, 20.0, -1.0);
        assertTrue(facing > side && side > behind);
        assertEquals(FlashRules.BEHIND_FACTOR, behind, 1e-9);
    }

    @Test
    void aBarelyReachingFlashDoesNothing() {
        assertEquals(0.0, FlashRules.strength(19.9, 20.0, -1.0), 1e-9);
    }
}
