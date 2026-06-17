package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Guards the "fail loudly" counter registry (Round 11 N1). The behaviour that matters:
 * counters are cumulative (two dumps are diffable), and the dump line is empty when nothing
 * changed so a healthy session stays log-silent instead of printing a heartbeat every 10 s.
 */
class NetStatsTest {

    @BeforeEach
    void reset() {
        NetStats.resetForTest();
    }

    @Test
    void countsAccumulateAcrossDumps() {
        NetStats.increment("shot_slot_mismatch");
        NetStats.increment("shot_slot_mismatch");
        assertEquals(2, NetStats.get("shot_slot_mismatch"));
        assertTrue(NetStats.consumeDumpLine().contains("shot_slot_mismatch=2"));
        NetStats.increment("shot_slot_mismatch");
        assertEquals(3, NetStats.get("shot_slot_mismatch"), "dump must not reset counters");
    }

    @Test
    void dumpIsEmptyWhenNothingChanged() {
        assertEquals("", NetStats.consumeDumpLine(), "no counters yet → silent");
        NetStats.increment("drop_malformed");
        assertTrue(NetStats.consumeDumpLine().contains("drop_malformed=1"));
        assertEquals("", NetStats.consumeDumpLine(), "no change since last dump → silent");
    }

    @Test
    void dumpListsCountersInStableSortedOrder() {
        NetStats.increment("b_counter");
        NetStats.increment("a_counter");
        String line = NetStats.consumeDumpLine();
        assertTrue(line.indexOf("a_counter") < line.indexOf("b_counter"),
                "sorted output keeps successive dumps diffable");
    }
}
