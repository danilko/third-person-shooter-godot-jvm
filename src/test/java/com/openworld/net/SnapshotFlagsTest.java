package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Guards the snapshot flags word — the u16 that carries combat, stance, weapon slot, movement type
 * and (since the melee chain) which attack step a swing was.
 *
 * <p>These fields share one integer by shift and mask, and a new field laid over an existing one
 * does not fail: it silently returns a plausible wrong stance or weapon slot on every remote
 * character. The packing is a pure function of ints precisely so it can be swept here, engine-free,
 * in the ordinary build — the codec around it needs Godot's {@code StreamPeerBuffer} and cannot be.
 *
 * <p>The complementary constraint lives elsewhere and cannot be checked from here:
 * {@code NetworkManager.SNAPSHOT_ENTRY_FIXED_BYTES} must equal the bytes
 * {@code NetMessageCodec.putSnapshotEntry} writes, or MTU chunking mis-sizes every frame. Carrying
 * the step in these spare bits is what keeps that number from having to move at all.
 */
class SnapshotFlagsTest {

    /** Every field survives every combination of the others — the collision test. */
    @Test
    void everyFieldRoundTripsIndependently() {
        for (int stance = 0; stance <= 0b111; stance++) {
            for (int slot = 0; slot <= 0b111; slot++) {
                for (int move = 0; move <= 0b11; move++) {
                    for (int step = 0; step <= 0b111; step++) {
                        for (int c = 0; c <= 1; c++) {
                            boolean combat = c == 1;
                            int flags = NetMessageCodec.packSnapshotFlags(combat, stance, slot, move, step);
                            String at = "stance=" + stance + " slot=" + slot + " move=" + move
                                    + " step=" + step + " combat=" + combat;
                            assertEquals(combat, NetMessageCodec.unpackCombat(flags), at);
                            assertEquals(stance, NetMessageCodec.unpackStance(flags), at);
                            assertEquals(slot, NetMessageCodec.unpackActiveSlot(flags), at);
                            assertEquals(move, NetMessageCodec.unpackMovementType(flags), at);
                            assertEquals(step, NetMessageCodec.unpackFireStep(flags), at);
                        }
                    }
                }
            }
        }
    }

    /** The word really is 16 bits wide — it is sent with put16, so a 17th bit would be dropped. */
    @Test
    void packedWordFitsInU16() {
        int widest = NetMessageCodec.packSnapshotFlags(true, 0b111, 0b111, 0b11, 0b111);
        assertTrue(widest <= 0xFFFF, "flags word overflowed u16: " + Integer.toBinaryString(widest));
        // 12 bits used (combat 1 + stance 3 + slot 3 + move 2 + step 3); four still spare.
        assertEquals(0b0000111111111111, widest, "unexpected bit layout: " + Integer.toBinaryString(widest));
    }

    /** Out-of-range values are masked, never allowed to bleed into a neighbouring field. */
    @Test
    void oversizedValuesCannotCorruptNeighbours() {
        int flags = NetMessageCodec.packSnapshotFlags(false, 99, 0, 0, 0);
        assertEquals(0, NetMessageCodec.unpackActiveSlot(flags), "stance overflowed into the weapon slot");
        assertEquals(0, NetMessageCodec.unpackMovementType(flags), "stance overflowed into movement type");
        assertEquals(0, NetMessageCodec.unpackFireStep(flags), "stance overflowed into the attack step");

        flags = NetMessageCodec.packSnapshotFlags(false, 0, 0, 0, 99);
        assertEquals(0, NetMessageCodec.unpackStance(flags), "step overflowed into the stance");
        assertEquals(0, NetMessageCodec.unpackActiveSlot(flags), "step overflowed into the weapon slot");
        assertTrue(NetMessageCodec.packSnapshotFlags(false, 0, 0, 0, 99) <= 0xFFFF, "step overflowed the word");
    }
}
