package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class FireCuePolicyTest {

    @Test
    void oneShotIsOneCue() {
        assertEquals(1, FireCuePolicy.cuesFor(true, 7, 8, FireCuePolicy.MAX_CUES));
        assertEquals(0, FireCuePolicy.cuesFor(true, 8, 8, FireCuePolicy.MAX_CUES));
    }

    @Test
    void aCollapsedBurstReplaysEachShot() {
        assertEquals(3, FireCuePolicy.cuesFor(true, 10, 13, FireCuePolicy.MAX_CUES));
    }

    @Test
    void theCounterWraps() {
        assertEquals(2, FireCuePolicy.cuesFor(true, 255, 1, FireCuePolicy.MAX_CUES));
        assertEquals(1, FireCuePolicy.cuesFor(true, 255, 0, FireCuePolicy.MAX_CUES));
    }

    @Test
    void aStallOrRejoinIsCappedAndTheFirstSnapshotPlaysNothing() {
        assertEquals(FireCuePolicy.MAX_CUES, FireCuePolicy.cuesFor(true, 0, 90, FireCuePolicy.MAX_CUES));
        assertEquals(0, FireCuePolicy.cuesFor(false, 0, 5, FireCuePolicy.MAX_CUES));
        assertEquals(1, FireCuePolicy.cuesFor(true, 0, 90, 1));   // a melee weapon replays the latest swing only
    }
}
