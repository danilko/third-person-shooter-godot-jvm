package com.openworld.net;

import com.openworld.ui.Feed;

/**
 * Unwraps a wrapping 32-bit millisecond timestamp (the compact {@code senderTimeMs} stamped on
 * every snapshot) into a monotonic 64-bit timeline that never wraps for any realistic uptime.
 *
 * <p>The wire keeps a 4-byte {@code int} to save bandwidth, but {@code (int) Time.getTicksMsec()}
 * wraps to negative after ~24.8 days of continuous uptime. The interpolator's ordering/stale checks
 * compare timestamps, so a wrapped (suddenly-smaller) value would look "stale" and replication would
 * freeze. This restores monotonicity on the receive side using <b>serial-number arithmetic</b>
 * (RFC 1982 / the same trick TCP uses for sequence numbers): the per-step delta {@code (int)(now -
 * last)} is computed in {@code int} so two's-complement wraparound yields the correct small signed
 * delta across the boundary, and that bounded delta is accumulated into a {@code long}. Valid as long
 * as successive samples are less than ~24 days apart — always true for a 20 Hz stream.
 *
 * <p>Engine-free (plain int/long) so the wrap behaviour is unit-testable headless, mirroring
 * {@link SnapshotInterpolator} / {@link DeathLatch}. One instance per replicated sender.
 */
public final class TimestampUnwrapper {

    private boolean started;
    private int     lastWireMs;
    private long    unwrapped;

    /**
     * Feed the next raw wire timestamp; returns the corresponding monotonic 64-bit value. The first
     * call seeds the timeline at {@code wireMs}; every later call advances it by the wrap-safe signed
     * delta from the previous raw value (so the result keeps climbing even when {@code wireMs} wraps
     * from {@link Integer#MAX_VALUE} to {@link Integer#MIN_VALUE}).
     */
    public long unwrap(int wireMs) {
        if (!started) {
            started = true;
            lastWireMs = wireMs;
            unwrapped = wireMs;
            return unwrapped;
        }
        int delta = wireMs - lastWireMs; // two's-complement subtraction: correct small delta across a wrap
        unwrapped += delta;
        lastWireMs = wireMs;
        return unwrapped;
    }
}
