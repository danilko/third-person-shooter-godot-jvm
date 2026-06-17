package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Guards the ~24.8-day int rollover of the wire {@code senderTimeMs}. Before unwrapping, a wrapped
 * (suddenly-negative) timestamp read as "stale" and froze replication; the unwrapped 64-bit timeline
 * must stay strictly monotonic with correct deltas straight through the wrap.
 */
class TimestampUnwrapperTest {

    @Test
    void monotonicAcrossNormalProgress() {
        TimestampUnwrapper u = new TimestampUnwrapper();
        assertEquals(1000L, u.unwrap(1000));
        assertEquals(1050L, u.unwrap(1050));
        assertEquals(1100L, u.unwrap(1100));
    }

    @Test
    void unwrapsAcrossTheIntRollover() {
        TimestampUnwrapper u = new TimestampUnwrapper();
        u.unwrap(Integer.MAX_VALUE - 70);                 // seed near the boundary
        long beforeWrap = u.unwrap(Integer.MAX_VALUE - 20);   // +50 ms, still positive
        int wrappedWire = (Integer.MAX_VALUE - 20) + 50;  // int addition rolls over to a negative wire value
        assertTrue(wrappedWire < 0, "precondition: the wire value actually wrapped negative");
        long afterWrap = u.unwrap(wrappedWire);
        assertTrue(afterWrap > beforeWrap,
                "timeline went backward across the wrap (before=" + beforeWrap + ", after=" + afterWrap + ")");
        assertEquals(50L, afterWrap - beforeWrap, "delta across the wrap must be the true 50 ms");
    }

    @Test
    void accumulatesManyWrapsWithoutLosingMonotonicity() {
        TimestampUnwrapper u = new TimestampUnwrapper();
        final int step = 1_000_003;   // ~1e6 ms steps, well under 2^31 so each delta stays wrap-safe
        int wire = 0;
        long prev = u.unwrap(wire);
        // Cross several full int periods; the unwrapped timeline must advance by exactly `step` every
        // call, never stepping backward when the raw int wire rolls over.
        for (int i = 0; i < 10_000; i++) {
            wire += step;            // int addition wraps naturally
            long now = u.unwrap(wire);
            assertEquals(step, now - prev, "every step must advance exactly `step` ms");
            prev = now;
        }
        assertTrue(prev > (long) Integer.MAX_VALUE * 2, "timeline did not climb past two int periods");
    }
}
