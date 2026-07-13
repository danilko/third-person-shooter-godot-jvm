package com.openworld.util;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;

import org.junit.jupiter.api.Test;

/**
 * Guards the traffic junction turn choice (roads-v2 Phase 1): {@code VehicleRoute.pickNextRoute}
 * picking among baked straight-biased {@code next_weights}, and the straightness-biased
 * {@code LaneGraph} fallback. The bugs this protects against: a malformed bake making a turn
 * unreachable (or throwing at spawn time), and the weighting silently degrading to uniform so
 * most cars turn off the arterial instead of flowing straight through.
 */
class WeightedPickTest {

    @Test
    void respectsBucketBoundaries() {
        float[] w = {0.6f, 0.2f, 0.2f};
        assertEquals(0, WeightedPick.pick(3, w, 0.0));
        assertEquals(0, WeightedPick.pick(3, w, 0.59));
        assertEquals(1, WeightedPick.pick(3, w, 0.61));
        assertEquals(1, WeightedPick.pick(3, w, 0.79));
        assertEquals(2, WeightedPick.pick(3, w, 0.81));
        assertEquals(2, WeightedPick.pick(3, w, 0.999999));
    }

    @Test
    void unnormalizedWeightsStillProportional() {
        // Weights need not sum to 1 (the LaneGraph fallback feeds raw straightness scores).
        float[] w = {6f, 2f, 2f};
        assertEquals(0, WeightedPick.pick(3, w, 0.5));
        assertEquals(1, WeightedPick.pick(3, w, 0.7));
        assertEquals(2, WeightedPick.pick(3, w, 0.9));
    }

    @Test
    void degradesToUniformNeverUnreachable() {
        // null / wrong length / all-zero weights = uniform — a candidate must never vanish
        // because its bake is missing or malformed.
        assertEquals(1, WeightedPick.pick(3, null, 0.5));
        assertEquals(2, WeightedPick.pick(3, new float[]{1f, 1f}, 0.9));
        assertEquals(0, WeightedPick.pick(3, new float[]{0f, 0f, 0f}, 0.1));
        // negative entries clamp to 0 (skipped), not to "steal" probability
        assertEquals(1, WeightedPick.pick(2, new float[]{-5f, 1f}, 0.0));
    }

    @Test
    void edgeDrawsStayInRange() {
        assertEquals(-1, WeightedPick.pick(0, null, 0.5));
        assertEquals(0, WeightedPick.pick(1, null, 0.999));
        // r at/over 1.0 (defensive) must clamp into the last bucket, not overflow
        assertEquals(2, WeightedPick.pick(3, null, 1.0));
        assertEquals(2, WeightedPick.pick(3, new float[]{1f, 1f, 1f}, 1.0));
        for (int n = 1; n <= 5; n++) {
            for (double r = 0.0; r < 1.0; r += 0.01) {
                int i = WeightedPick.pick(n, new float[]{1f, 2f, 3f, 4f, 5f}, r);
                // wrong-length weights → uniform; either way in range
                assertTrue(i >= 0 && i < n, "pick(" + n + ", …, " + r + ") = " + i);
            }
        }
    }

    @Test
    void distributionTracksWeights() {
        // Statistical sanity on the straight-bias: 0.6/0.2/0.2 over many deterministic draws.
        float[] w = {0.6f, 0.2f, 0.2f};
        int[] hits = new int[3];
        Random rng = new Random(42);
        int n = 100_000;
        for (int i = 0; i < n; i++) hits[WeightedPick.pick(3, w, rng.nextDouble())]++;
        assertTrue(Math.abs(hits[0] / (double) n - 0.6) < 0.01, "straight share " + hits[0]);
        assertTrue(Math.abs(hits[1] / (double) n - 0.2) < 0.01, "left share " + hits[1]);
        assertTrue(Math.abs(hits[2] / (double) n - 0.2) < 0.01, "right share " + hits[2]);
    }

    @Test
    void parseWeightsRoundTripAndRejection() {
        float[] w = WeightedPick.parseWeights("0.600,0.200,0.200");
        assertEquals(3, w.length);
        assertEquals(0.6f, w[0], 1e-6);
        assertNull(WeightedPick.parseWeights(null));
        assertNull(WeightedPick.parseWeights(""));
        assertNull(WeightedPick.parseWeights("  "));
        assertNull(WeightedPick.parseWeights("0.5,abc,0.5"));   // malformed → uniform, no throw
        assertEquals(2, WeightedPick.parseWeights(" 1 , 2 ").length);
    }
}
