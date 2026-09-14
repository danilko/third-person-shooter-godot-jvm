package com.openworld.weapon;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Guards N1's deterministic spread. The property the protocol rests on is the first test: the host
 * regenerates a client's pellets from the seed, so the same inputs must give bit-identical
 * directions. The rest pin the cone itself — nothing outside the half-angle, zero spread is exact,
 * the disk is filled uniformly (not bunched at the centre or the rim), and distinct pulls differ.
 */
class SpreadPatternTest {

    private static double angleDeg(double[] a, double[] b) {
        double dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
        return Math.toDegrees(Math.acos(Math.max(-1, Math.min(1, dot))));
    }

    @Test
    void sameInputsGiveTheSamePellets() {
        long seed = SpreadPattern.seedFor("7f3c-player", 1234);
        for (int p = 0; p < 8; p++) {
            assertArrayEquals(SpreadPattern.direction(0.3, -0.1, -1, 4.0, seed, p),
                    SpreadPattern.direction(0.3, -0.1, -1, 4.0, SpreadPattern.seedFor("7f3c-player", 1234), p), 0.0);
        }
    }

    @Test
    void zeroSpreadIsTheAimExactly() {
        double[] d = SpreadPattern.direction(0, 0, -2, 0.0, 99, 3);
        assertArrayEquals(new double[] {0, 0, -1}, d, 0.0);
    }

    @Test
    void everyPelletStaysInsideTheCone() {
        double[] aim = {0.6, 0.0, -0.8};
        for (long shot = 0; shot < 200; shot++) {
            long seed = SpreadPattern.seedFor("a", shot);
            for (int p = 0; p < 8; p++) {
                double[] d = SpreadPattern.direction(aim[0], aim[1], aim[2], 3.0, seed, p);
                assertEquals(1.0, Math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]), 1e-12);
                assertTrue(angleDeg(aim, d) <= 3.0 + 1e-9);
            }
        }
    }

    @Test
    void theDiskIsFilledUniformly() {
        // Uniform on a disk of radius R: mean r^2 = R^2 / 2, and half the samples inside R / sqrt(2).
        double half = 5.0;
        int n = 20000, inner = 0;
        double sumR2 = 0;
        double[] aim = {0, 0, -1};
        for (int i = 0; i < n; i++) {
            double r = angleDeg(aim, SpreadPattern.direction(0, 0, -1, half, SpreadPattern.seedFor("u", i), 0));
            sumR2 += r * r;
            if (r < half / Math.sqrt(2)) inner++;
        }
        assertEquals(half * half / 2, sumR2 / n, 0.3);
        assertEquals(0.5, inner / (double) n, 0.02);
    }

    @Test
    void pelletsAndPullsDiffer() {
        long seed = SpreadPattern.seedFor("x", 1);
        assertNotEquals(SpreadPattern.direction(0, 0, -1, 4, seed, 0)[0], SpreadPattern.direction(0, 0, -1, 4, seed, 1)[0]);
        assertNotEquals(SpreadPattern.direction(0, 0, -1, 4, seed, 0)[0],
                SpreadPattern.direction(0, 0, -1, 4, SpreadPattern.seedFor("x", 2), 0)[0]);
        assertNotEquals(SpreadPattern.seedFor("x", 1), SpreadPattern.seedFor("y", 1));
    }

    @Test
    void aVerticalShotStillSpreads() {
        double[] d = SpreadPattern.direction(0, 1, 0, 4.0, 5, 0);
        double a = angleDeg(new double[] {0, 1, 0}, d);
        assertTrue(a > 0 && a <= 4.0 + 1e-9);
    }
}
