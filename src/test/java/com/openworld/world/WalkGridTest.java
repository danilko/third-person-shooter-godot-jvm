package com.openworld.world;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class WalkGridTest {

    /** 10 x 10 cells of 1 m; a wall along x = 5 with one gap at z = 9. */
    private static WalkGrid walled(boolean gap) {
        int n = 10;
        byte[] bits = new byte[(n * n + 7) / 8];
        for (int z = 0; z < n; z++) {
            if (gap && z == 9) continue;
            int k = 5 * n + z;
            bits[k >> 3] |= (byte) (1 << (7 - (k & 7)));
        }
        return new WalkGrid(0, 0, n, 1.0, bits);
    }

    @Test
    void walksRoundTheWallThroughItsGap() {
        WalkGrid g = walled(true);
        assertTrue(g.occupied(5, 0));
        assertFalse(g.occupied(5, 9));
        List<double[]> way = g.path(1.5, 1.5, 8.5, 1.5);
        assertNotNull(way);
        boolean viaGap = false;
        for (double[] p : way) if (p[1] > 8.0) viaGap = true;
        assertTrue(viaGap, "the walk goes through the gap at z 9");
        double[] last = way.get(way.size() - 1);
        assertEquals(8.5, last[0], 1e-9);
        assertTrue(WalkGrid.length(1.5, 1.5, way) > 14.0, "round the wall, not through it");
    }

    @Test
    void noWalkWhenTheWallIsClosed() {
        assertNull(walled(false).path(1.5, 1.5, 8.5, 1.5));
    }

    @Test
    void aStraightWalkIsOneLeg() {
        List<double[]> way = walled(true).path(1.5, 1.5, 1.5, 8.5);
        assertEquals(1, way.size(), "string-pulled to the goal");
    }
}
