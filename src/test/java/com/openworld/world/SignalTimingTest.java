package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SignalTimingTest {
    static final double G = 22, Y = 3, R = 2;

    @Test
    void twoGroupsTakeTurnsWithAYellowAndAnAllRed() {
        assertEquals(SignalTiming.GREEN, SignalTiming.vehicle(2, 0, 0.0, G, Y, R));
        assertEquals(SignalTiming.RED, SignalTiming.vehicle(2, 1, 0.0, G, Y, R));
        assertEquals(SignalTiming.YELLOW, SignalTiming.vehicle(2, 0, 23.0, G, Y, R));
        // the all-red clearance: nobody has a green
        assertEquals(SignalTiming.RED, SignalTiming.vehicle(2, 0, 26.0, G, Y, R));
        assertEquals(SignalTiming.RED, SignalTiming.vehicle(2, 1, 26.0, G, Y, R));
        assertEquals(SignalTiming.GREEN, SignalTiming.vehicle(2, 1, 27.5, G, Y, R));
        // the cycle wraps, negative clocks too
        assertEquals(SignalTiming.GREEN, SignalTiming.vehicle(2, 0, 54.0 * 3, G, Y, R));
        assertEquals(SignalTiming.GREEN, SignalTiming.vehicle(2, 1, -10.0, G, Y, R));
    }

    @Test
    void neverTwoGreensAtOnce() {
        for (int groups = 1; groups <= 4; groups++)
            for (double t = 0; t < 400; t += 0.37) {
                int greens = 0;
                for (int g = 0; g < groups; g++)
                    if (SignalTiming.vehicle(groups, g, t, G, Y, R) != SignalTiming.RED) greens++;
                assertTrue(greens <= 1, "groups " + groups + " t " + t);
            }
    }

    @Test
    void aCrosswalkWalksOnlyWhileItsRoadIsRedAndTheOtherGreen() {
        // group 1's crosswalk walks during group 0's green, flashes its last 4 s, and stops for the yellow
        assertEquals(SignalTiming.WALK, SignalTiming.pedestrian(2, 1, 1.0, G, Y, R));
        assertEquals(SignalTiming.FLASH, SignalTiming.pedestrian(2, 1, 19.0, G, Y, R));
        assertEquals(SignalTiming.STOP, SignalTiming.pedestrian(2, 1, 23.0, G, Y, R));
        assertEquals(SignalTiming.STOP, SignalTiming.pedestrian(2, 0, 1.0, G, Y, R));
        for (double t = 0; t < 200; t += 0.29)
            for (int g = 0; g < 2; g++)
                if (SignalTiming.pedestrian(2, g, t, G, Y, R) != SignalTiming.STOP)
                    assertEquals(SignalTiming.RED, SignalTiming.vehicle(2, g, t, G, Y, R), "walk across a moving road");
    }

    @Test
    void theOffsetIsStableAndInsideTheCycle() {
        double c = SignalTiming.cycle(2, G, Y, R);
        double a = SignalTiming.offset("j003a5678", c);
        assertEquals(a, SignalTiming.offset("j003a5678", c));
        assertTrue(a >= 0 && a < c);
    }
}
