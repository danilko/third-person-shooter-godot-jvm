package com.openworld.util;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

/** Pins which short windows the precise hitbox pass asks (PLAN.md P0 0.4). */
class RayWindowsTest {

    private static final double[] O = {0, 0, 0};
    private static final double[] X = {1, 0, 0};

    @Test
    void aFarBodyOnTheLineGetsAWindowAroundIt() {
        List<double[]> w = RayWindows.windows(O, X, 1000, List.of(new double[] {250, 1, 0}));
        assertEquals(1, w.size());
        assertEquals(245.5, w.get(0)[0], 1e-9);
        assertEquals(254.5, w.get(0)[1], 1e-9);
    }

    @Test
    void nearBodiesOffLineBodiesAndBodiesPastTheHitAreSkipped() {
        List<double[]> w = RayWindows.windows(O, X, 300, List.of(
            new double[] {10, 0, 0},    // the long ray is precise this close
            new double[] {150, 4, 0},   // more than REACH off the line
            new double[] {-50, 0, 0},   // behind the origin
            new double[] {310, 0, 0})); // beyond what the long ray reached
        assertTrue(w.isEmpty());
    }

    @Test
    void aWindowIsClippedToTheLongRaysHit() {
        List<double[]> w = RayWindows.windows(O, X, 251, List.of(new double[] {250, 0, 0}));
        assertEquals(251, w.get(0)[1], 1e-9);
    }

    @Test
    void neighboursCoalesceButACrowdDoesNotBecomeOneLongQuery() {
        List<double[]> w = RayWindows.windows(O, X, 1000, List.of(
            new double[] {100, 0, 0}, new double[] {102, 0, 0},
            new double[] {110, 0, 0}, new double[] {118, 0, 0}, new double[] {126, 0, 0}));
        for (double[] win : w) assertTrue(win[1] - win[0] <= RayWindows.MAX_WINDOW + 1e-9);
        assertEquals(95.5, w.get(0)[0], 1e-9);
        assertEquals(106.5, w.get(0)[1], 1e-9); // 100 and 102 share one window
        for (int i = 1; i < w.size(); i++) assertTrue(w.get(i)[0] >= w.get(i - 1)[0]);
    }
}
