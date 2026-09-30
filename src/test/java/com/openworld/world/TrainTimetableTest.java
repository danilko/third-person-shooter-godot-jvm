package com.openworld.world;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class TrainTimetableTest {

    private static final double[] STOPS = {50.0, 900.0, 2000.0};
    private static final double[] CAPS = {22.0, 16.0};

    @Test
    void itStopsAtEveryPlatformBothWaysWithItsDoorsOpen() {
        TrainTimetable tt = new TrainTimetable(STOPS, CAPS);
        boolean[] out = new boolean[3], back = new boolean[3];
        int lastDir = 1;
        for (double t = 0; t < 2 * tt.period(); t += 0.5) {
            TrainTimetable.State s = tt.at(t);
            if (!s.dwell()) {
                lastDir = s.dir();
                continue;
            }
            int k = -1;
            for (int i = 0; i < STOPS.length; i++) if (Math.abs(s.s() - STOPS[i]) < 1e-6) k = i;
            assertTrue(k >= 0, "a dwell off a platform at s " + s.s());
            assertEquals(0.0, s.v(), 1e-9);
            if (lastDir > 0) out[k] = true; else back[k] = true;
        }
        assertTrue(out[0] && out[1] && out[2], "out: every stop");
        assertTrue(back[1] && back[0], "back: every stop");
    }

    @Test
    void itNeverExceedsTheLegsCapAndIsContinuous() {
        TrainTimetable tt = new TrainTimetable(STOPS, CAPS);
        TrainTimetable.State prev = tt.at(0.0);
        for (double t = 0.1; t < 2 * tt.period(); t += 0.1) {
            TrainTimetable.State s = tt.at(t);
            assertTrue(Math.abs(s.v()) <= 22.0 + 1e-6);
            assertTrue(Math.abs(s.s() - prev.s()) <= 22.0 * 0.1 + 1e-6, "jump at t " + t);
            prev = s;
        }
    }

    @Test
    void aRunCoversItsDistanceInItsTime() {
        for (double d : new double[]{30.0, 400.0, 1500.0}) {
            double rt = TrainTimetable.runTime(d, 20.0);
            assertEquals(d, TrainTimetable.runDistance(d, 20.0, rt), 1e-6);
            assertEquals(0.0, TrainTimetable.runDistance(d, 20.0, 0.0), 1e-9);
            assertEquals(d / 2.0, TrainTimetable.runDistance(d, 20.0, rt / 2.0), 1e-6);   // symmetric (ACCEL == DECEL)
        }
    }

    @Test
    void aCrossingClosesAheadOfTheTrainAndOpensBehindIt() {
        TrainTimetable tt = new TrainTimetable(STOPS, CAPS);
        double c = 1400.0;                       // between stop 1 and 2
        boolean sawOpen = false, sawClosed = false;
        for (double t = 0; t < tt.period(); t += 0.5) {
            TrainTimetable.State s = tt.at(t);
            boolean closed = tt.crossingClosed(c, t, 80.0, 150.0, 10.0, 8.0);
            double gap = Math.abs(c - s.s());
            if (gap <= 50.0) assertTrue(closed, "the train is ON the crossing at t " + t);
            if (gap > 40.0 + 150.0 + 1.0) assertFalse(closed, "closed with the train " + gap + " m away");
            sawOpen |= !closed;
            sawClosed |= closed;
        }
        assertTrue(sawOpen && sawClosed);
    }
}
