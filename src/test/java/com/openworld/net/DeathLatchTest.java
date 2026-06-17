package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Guards the one-shot death trigger that drives the non-authority ragdoll. The bug this
 * protects against: a defeated puppet stays upright because the death never fired (or fires
 * repeatedly because the snapshot stream keeps carrying health == 0).
 */
class DeathLatchTest {

    @Test
    void firesExactlyOnceWhenHealthReachesZero() {
        DeathLatch latch = new DeathLatch();
        assertFalse(latch.update(100f), "alive health must not fire");
        assertFalse(latch.update(40f),  "still alive must not fire");
        assertTrue(latch.update(0f),    "crossing to zero must fire once");
        assertTrue(latch.isDead());
        // Subsequent zero-health snapshots (the stream keeps carrying 0) must not re-fire.
        assertFalse(latch.update(0f),  "repeated zero must not re-fire");
        assertFalse(latch.update(-5f), "negative health must not re-fire");
    }

    @Test
    void firesOnInstantLethalFirstSample() {
        DeathLatch latch = new DeathLatch();
        // First snapshot already at zero (joined late / one-shot kill before any alive sample).
        assertTrue(latch.update(0f));
        assertFalse(latch.update(0f));
    }

    @Test
    void staysLatchedEvenIfHealthLaterReadsPositive() {
        // Once dead, a stray/out-of-order snapshot with positive health must not "revive" the
        // latch — the authority owns life/death; the client never un-ragdolls from a number.
        DeathLatch latch = new DeathLatch();
        assertTrue(latch.update(0f));
        assertFalse(latch.update(100f), "must not un-latch");
        assertTrue(latch.isDead());
    }
}
