package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class LagCompensationTest {

    @Test
    void rewindIsTheViewsAgeCappedAndNeverIntoTheFuture() {
        assertEquals(120, LagCompensation.rewindMs(10_120, 10_000, 200));
        assertEquals(200, LagCompensation.rewindMs(10_900, 10_000, 200));   // a forged old view buys only the cap
        assertEquals(0, LagCompensation.rewindMs(10_000, 10_050, 200));     // a view ahead of the host
    }

    @Test
    void rewindSurvivesTheClockWrap() {
        int now = Integer.MIN_VALUE + 40;           // just wrapped
        int view = Integer.MAX_VALUE - 59;          // 100 ms earlier, before the wrap
        assertEquals(100, LagCompensation.rewindMs(now, view, 200));
    }

    @Test
    void historyInterpolatesBetweenSamplesAndClampsAtTheEnds() {
        LagCompensation.History h = new LagCompensation.History(8);
        assertNull(h.at(0));
        h.record(1000, 0, 0, 0);
        h.record(1016, 1.6, 0, 0);
        h.record(1033, 3.3, 0, 0);
        assertEquals(0.8, h.at(1008).x(), 1e-9);
        assertEquals(3.3, h.at(1100).x(), 1e-9);   // newer than the newest
        assertEquals(0.0, h.at(900).x(), 1e-9);    // older than the oldest
        assertEquals(1.6, h.at(1016).x(), 1e-9);
    }

    @Test
    void theRingKeepsOnlyTheNewestSamples() {
        LagCompensation.History h = new LagCompensation.History(4);
        for (int i = 0; i < 10; i++) h.record(i * 10, i, 0, 0);
        assertEquals(4, h.size());
        assertEquals(6.0, h.at(0).x(), 1e-9);      // the oldest kept is t=60
        assertEquals(7.5, h.at(75).x(), 1e-9);
    }

    @Test
    void aRepeatedTimeReplacesTheNewestSample() {
        LagCompensation.History h = new LagCompensation.History(4);
        h.record(100, 1, 0, 0);
        h.record(100, 2, 0, 0);
        assertEquals(1, h.size());
        assertEquals(2.0, h.at(100).x(), 1e-9);
    }

    @Test
    void distanceToTheShotSegment() {
        Vec3 from = new Vec3(0, 0, 0), aim = new Vec3(0, 0, -1);
        assertEquals(2.0, LagCompensation.distanceToSegment(new Vec3(2, 0, -10), from, aim, 50), 1e-9);
        assertEquals(5.0, LagCompensation.distanceToSegment(new Vec3(0, 0, -55), from, aim, 50), 1e-9);
        assertEquals(3.0, LagCompensation.distanceToSegment(new Vec3(0, 0, 3), from, aim, 50), 1e-9);
    }
}
