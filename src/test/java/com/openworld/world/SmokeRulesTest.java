package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SmokeRulesTest {
    @Test
    void growsHoldsAndFades() {
        assertEquals(0.0, SmokeRules.radiusAt(0.0, 5, 2, 18, 3), 1e-9);
        assertEquals(2.5, SmokeRules.radiusAt(1.0, 5, 2, 18, 3), 1e-9);
        assertEquals(5.0, SmokeRules.radiusAt(10.0, 5, 2, 18, 3), 1e-9);
        assertEquals(2.5, SmokeRules.radiusAt(16.5, 5, 2, 18, 3), 1e-9);
        assertEquals(0.0, SmokeRules.radiusAt(18.0, 5, 2, 18, 3), 1e-9);
    }

    @Test
    void aLineThroughTheCloudIsBlockedAndOnePastItIsNot() {
        assertTrue(SmokeRules.segmentHitsSphere(-10, 1, 0, 10, 1, 0, 0, 1, 0, 4));
        assertFalse(SmokeRules.segmentHitsSphere(-10, 1, 6, 10, 1, 6, 0, 1, 0, 4));
        // a segment that stops short of the cloud is not blocked by it
        assertFalse(SmokeRules.segmentHitsSphere(-10, 1, 0, -6, 1, 0, 0, 1, 0, 4));
        assertFalse(SmokeRules.segmentHitsSphere(-10, 1, 0, 10, 1, 0, 0, 1, 0, 0));
    }
}
