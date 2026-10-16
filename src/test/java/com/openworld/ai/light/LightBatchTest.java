package com.openworld.ai.light;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md 2.3: MSG_LIGHT_BATCH's body round-trips, stays compact, and refuses a malformed one. */
class LightBatchTest {

    @Test void roundTripsWithinTheQuantisation() {
        List<String> looks = List.of("shino|police|PIS1", "fumiriya||");
        List<LightBatch.Entry> in = List.of(
                new LightBatch.Entry(7, 0, -2251.37, 12.34, 1999.96, 1.0, LightSim.HOLD, true, false, true),
                new LightBatch.Entry(65000, 1, 0.04, -3.0, -0.06, -2.5, LightSim.DEAD, false, true, false));
        byte[] data = LightBatch.encode(looks, in);
        List<String> lo = new ArrayList<>();
        List<LightBatch.Entry> out = LightBatch.decode(data, lo);
        assertEquals(looks, lo);
        assertEquals(2, out.size());
        for (int i = 0; i < 2; i++) {
            LightBatch.Entry a = in.get(i), b = out.get(i);
            assertEquals(a.id(), b.id());
            assertEquals(a.look(), b.look());
            assertEquals(a.x(), b.x(), 0.051);
            assertEquals(a.y(), b.y(), 0.026);
            assertEquals(a.z(), b.z(), 0.051);
            double dy = Math.abs(Math.atan2(Math.sin(a.yaw() - b.yaw()), Math.cos(a.yaw() - b.yaw())));
            assertTrue(dy <= Math.PI / 256 + 1e-9, "yaw off by " + dy);
            assertEquals(a.state(), b.state());
            assertEquals(a.ranged(), b.ranged());
            assertEquals(a.zombie(), b.zombie());
            assertEquals(a.hasTarget(), b.hasTarget());
        }
    }

    @Test void eightyBodiesFitInOneSmallMessage() {
        List<LightBatch.Entry> in = new ArrayList<>();
        for (int i = 0; i < 80; i++) in.add(new LightBatch.Entry(i, i % 3, i, 0, -i, 0, LightSim.ADVANCE, false, false, true));
        byte[] data = LightBatch.encode(List.of("shino||", "bibi||MEW1", "vita|police|PIS1"), in);
        assertTrue(data.length <= 80 * LightBatch.ENTRY_BYTES + 60, data.length + " bytes");
    }

    @Test void aTruncatedOrInconsistentBodyIsRefused() {
        byte[] data = LightBatch.encode(List.of("shino||"),
                List.of(new LightBatch.Entry(1, 0, 1, 2, 3, 0, LightSim.IDLE, false, false, false)));
        byte[] cut = java.util.Arrays.copyOf(data, data.length - 3);
        assertThrows(IllegalArgumentException.class, () -> LightBatch.decode(cut, new ArrayList<>()));
        byte[] badLook = LightBatch.encode(List.of(), List.of(new LightBatch.Entry(1, 4, 1, 2, 3, 0, 0, false, false, false)));
        assertThrows(IllegalArgumentException.class, () -> LightBatch.decode(badLook, new ArrayList<>()));
    }
}
