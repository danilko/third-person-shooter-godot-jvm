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

    @Test
    void aDestroyedSetComesBackAtTheNextPlatformAfterTheGap() {
        TrainTimetable tt = new TrainTimetable(STOPS, CAPS);
        for (double t = 0; t < 2 * tt.period(); t += 7.3) {
            double back = tt.nextDwellStart(t, 30.0);
            assertTrue(back >= t + 30.0 - 1e-9, "comes back no sooner than the gap");
            TrainTimetable.State s = tt.at(back + 0.01);
            assertTrue(s.dwell(), "it reappears standing at a platform");
            assertTrue(tt.stopAt(back) >= 0);
            // and it is the FIRST such dwell: no dwell starts between the gap and it
            assertTrue(back - (t + 30.0) <= tt.period(), "within one cycle");
        }
    }

    @Test
    void theNextCallIsTheStopAheadAndBoardsListTrainsOutOfAStation() {
        TrainTimetable tt = new TrainTimetable(STOPS, CAPS);
        for (double t = 0; t < tt.period(); t += 3.1) {
            TrainTimetable.Call c = tt.nextCall(t);
            TrainTimetable.State s = tt.at(t);
            if (s.dwell()) {
                assertEquals(s.stop(), c.stop(), "standing at a stop, the call is that stop");
                assertTrue(c.arrive() <= t && t < c.depart());
            } else {
                assertTrue(c.arrive() > t, "running, the call is ahead");
                assertEquals(s.dir() > 0 ? 1 : -1, Integer.signum((int) Math.signum(STOPS[c.stop()] - s.s())));
            }
        }
        // the middle stop is called at both ways in a cycle; a terminus sends every train back
        java.util.List<TrainTimetable.Call> mid = tt.calls(0, 1, 4);
        assertTrue(mid.stream().anyMatch(c -> c.dir() > 0) && mid.stream().anyMatch(c -> c.dir() < 0));
        for (TrainTimetable.Call c : tt.calls(0, 2, 3)) assertEquals(-1, c.dir());
        assertEquals(2, tt.terminalFor(1));
        assertEquals(0, tt.terminalFor(-1));
    }

    @Test
    void aCircuitRunsOutOnOneTrackAndBackOnTheOtherTurningMidStop() {
        double[][] st = {{50.0, 900.0, 2000.0}, {60.0, 1100.0, 1990.0}};
        double[][] caps = {{22.0, 16.0}, {16.0, 22.0}};
        TrainTimetable tt = TrainTimetable.circuit(st, caps);
        boolean[][] seen = new boolean[2][3];
        int swaps = 0;
        TrainTimetable.State prev = tt.at(0.0);
        for (double t = 0; t <= tt.period() + 0.5; t += 0.25) {      // past the end: the second change is at the wrap
            TrainTimetable.State s = tt.at(t);
            assertTrue(s.v() >= 0.0, "a circuit always runs forward along its track");
            if (s.dwell()) seen[s.track()][s.stop()] = true;
            if (s.track() != prev.track()) {
                swaps++;
                // the change is made standing still, at a terminus: the last stop of one track, the first of the next
                assertTrue(prev.dwell() && s.dwell(), "the track changes only mid-stop");
                assertEquals(st[prev.track()].length - 1, prev.stop());
                assertEquals(0, s.stop());
            }
            prev = s;
        }
        for (boolean[] tr : seen) for (boolean b : tr) assertTrue(b, "every stop of both tracks is called at");
        assertEquals(2, swaps, "one change at each terminus");
        // the terminus is ONE call (arrive on track 0, leave on track 1) and the train goes to track 1's far end
        for (TrainTimetable.Call c : tt.calls(0.0, 0, 2, 2)) {
            assertEquals(1, tt.departureTrack(c));
            assertEquals(TrainTimetable.TERMINAL_DWELL, c.depart() - c.arrive(), 1e-6);
            assertEquals(2, tt.destinationStop(new TrainTimetable.Call(c.arrive(), c.depart(), 0, 1, 1)));
        }
        // a crossing on track 1 is never closed while the set is out on track 0, away from it
        for (double t = 0; t < tt.period(); t += 1.0) {
            TrainTimetable.State s = tt.at(t);
            if (s.track() == 0 && !s.dwell()) assertTrue(!tt.crossingClosed(1, 500.0, t, 80.0, 150.0, 10.0, 8.0));
        }
    }
}
