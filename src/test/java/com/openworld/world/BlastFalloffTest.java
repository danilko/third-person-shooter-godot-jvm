package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BlastFalloffTest {
    @Test
    void quadraticToZeroAtTheRadius() {
        assertEquals(300f, BlastFalloff.damage(300f, 7f, 0.0), 1e-4);
        assertEquals(75f, BlastFalloff.damage(300f, 7f, 3.5), 1e-4);
        assertEquals(0f, BlastFalloff.damage(300f, 7f, 7.0), 1e-6);
        assertEquals(0f, BlastFalloff.damage(300f, 7f, 20.0), 1e-6);
        assertEquals(0f, BlastFalloff.damage(300f, 0f, 0.0), 1e-6);
    }

    @Test
    void distanceIsToTheSurfaceAndZeroInside() {
        // a 2 x 1 x 4 box about the origin (a car): a blast on the bumper is ON it, not 2 m from it
        assertEquals(0.0, BlastFalloff.distanceToBox(0, 0, 2, -1, -0.5, -2, 1, 0.5, 2), 1e-9);
        assertEquals(0.0, BlastFalloff.distanceToBox(0.3, 0, 0, -1, -0.5, -2, 1, 0.5, 2), 1e-9);
        assertEquals(1.0, BlastFalloff.distanceToBox(0, 0, 3, -1, -0.5, -2, 1, 0.5, 2), 1e-9);
        assertEquals(Math.sqrt(2), BlastFalloff.distanceToBox(2, 1.5, 0, -1, -0.5, -2, 1, 0.5, 2), 1e-9);
    }
}
