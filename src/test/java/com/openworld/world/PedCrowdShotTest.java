package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** A shot against a light crowd ped: an upright cylinder 0.28 m wide, 1.62 m tall (CrowdShot.rayBody). */
class PedCrowdShotTest {

    static double hit(double oy, double dx, double dy, double dz, double fx, double fz) {
        double n = Math.sqrt(dx * dx + dy * dy + dz * dz);
        return CrowdShot.rayBody(0, oy, 0, dx / n, dy / n, dz / n, fx, 0, fz, 1.62, 0.28);
    }

    @Test
    void aLevelShotAtTheChestEntersAtTheSurface() {
        assertEquals(49.72, hit(1.2, 0, 0, -1, 0, -50), 1e-6);
    }

    @Test
    void aShotHalfAMetreBesideMisses() {
        assertTrue(hit(1.2, 0, 0, -1, 0.5, -50) < 0);
    }

    @Test
    void aShotOverTheHeadOrUnderTheFeetMisses() {
        assertTrue(hit(2.0, 0, 0, -1, 0, -50) < 0);
        assertTrue(hit(-0.5, 0, 0, -1, 0, -50) < 0);
    }

    @Test
    void aBodyBehindTheShooterIsNotHit() {
        assertTrue(hit(1.2, 0, 0, 1, 0, -50) < 0);
    }

    @Test
    void aShotFromAboveComesInThroughTheHead() {
        // from 10 m up, 20 m away, aimed at the feet: it crosses the top of the body before the side
        double t = hit(10.0, 0, -10, -20, 0, -20);
        assertTrue(t > 0 && t < Math.sqrt(10 * 10 + 20 * 20), "t=" + t);
    }
}
