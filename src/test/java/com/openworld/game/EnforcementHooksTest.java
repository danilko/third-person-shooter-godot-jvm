package com.openworld.game;

import com.openworld.game.activity.Plan;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md P1e step 5: an activity's hold on the enforcement, for its participants only, undone at its end. */
class EnforcementHooksTest {

    final Set<String> inRun = new HashSet<>();

    @BeforeEach
    void setUp() {
        EnforcementHooks.reset();
        EnforcementHooks.participant = (inst, pid) -> inst.equals("heist@1") && inRun.contains(pid);
    }

    @AfterEach
    void tearDown() { EnforcementHooks.reset(); }

    static Plan.Enforcement hooks(java.util.function.Consumer<Plan> declare) {
        Plan p = new Plan();
        declare.accept(p);
        return p.enforcement();
    }

    @Test
    void onlyParticipantsAreHeldAndOnlyWhileItRuns() {
        EnforcementHooks.register("heist@1", hooks(p -> p.wantedAtLeast(2).noDispatch("gang_a").squad("gang_b", 3)));
        inRun.add("host");
        assertEquals(2, EnforcementHooks.wanted("host", 0));
        assertEquals(0, EnforcementHooks.wanted("guest", 0), "a player outside the run is untouched");
        assertTrue(EnforcementHooks.noDispatch("host", "gang_a"));
        assertFalse(EnforcementHooks.noDispatch("host", "police"));
        assertEquals(Map.of("gang_b", 3), EnforcementHooks.squads("host"));
        EnforcementHooks.release("heist@1");
        assertEquals(0, EnforcementHooks.wanted("host", 0));
        assertFalse(EnforcementHooks.noDispatch("host", "gang_a"));
        assertTrue(EnforcementHooks.squads("host").isEmpty());
    }

    @Test
    void setAndClearAreOnceThenLockHolds() {
        EnforcementHooks.register("heist@1", hooks(p -> p.wantedSet(3).wantedLock()));
        inRun.add("host");
        assertEquals(3, EnforcementHooks.wanted("host", 0), "set as the run first sees them");
        assertEquals(3, EnforcementHooks.wanted("host", 5), "then locked there: a new crime does not raise it");
        assertEquals(3, EnforcementHooks.wanted("host", 1), "nor does the drain lower it");
    }

    @Test
    void atMostCapsAndNoDispatchAllKeepsEverySideAway() {
        EnforcementHooks.register("heist@1", hooks(p -> p.wantedAtMost(1).noDispatch()));
        inRun.add("host");
        assertEquals(1, EnforcementHooks.wanted("host", 4));
        assertTrue(EnforcementHooks.noDispatch("host", "police"));
        assertTrue(EnforcementHooks.noDispatch("host", "gang_b"));
    }

    @Test
    void aRunWithNoHooksRegistersNothing() {
        EnforcementHooks.register("heist@1", new Plan().enforcement());
        assertFalse(EnforcementHooks.any());
    }
}
