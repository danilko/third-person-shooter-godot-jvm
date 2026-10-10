package com.openworld.game.profile;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CareerStateTest {

    @Test
    void aTemporaryCareerIsEffectiveAndItsStrikesAreDiscarded() {
        CareerState c = new CareerState();
        c.base = "courier";
        assertEquals("courier", c.effective());
        assertTrue(c.count("strikes", 1));
        assertTrue(c.push("act#1", "police", false));
        assertFalse(c.push("act#1", "police", false), "one override per activity instance");
        assertEquals("police", c.effective());
        assertFalse(c.count("strikes", 2), "TEMP: onto the scratch record");
        assertEquals(2, c.effectiveCount("strikes"));
        assertEquals(0, c.record("police", "strikes"));
        assertTrue(c.pop("act#1"));
        assertEquals("courier", c.effective());
        assertEquals(1, c.effectiveCount("strikes"));
        assertEquals(0, c.record("police", "strikes"), "the scratch record went with the override");
    }

    @Test
    void aRealRoutingLandsOnTheRealRecord() {
        CareerState c = new CareerState();
        c.base = "courier";
        c.push("act#2", "police", true);
        assertTrue(c.count("exposed", 1));
        c.pop("act#2");
        assertEquals(1, c.record("police", "exposed"));
    }

    @Test
    void overridesStackAndPopOutOfOrder() {
        CareerState c = new CareerState();
        c.base = "courier";
        c.push("a", "police", false);
        c.push("b", "paramedic", false);
        assertEquals("paramedic", c.effective());
        c.pop("a");
        assertEquals("paramedic", c.effective());
        c.pop("b");
        assertEquals("courier", c.effective());
    }

    /** A crash or a save taken mid-mission: the journal comes back, the activity does not. */
    @Test
    void aLoadPopsOverridesWhoseActivityIsNotRunning() {
        PlayerProfile p = new PlayerProfile("p1");
        p.career.base = "courier";
        p.career.push("gone", "police", false);
        p.career.push("running", "paramedic", false);
        PlayerProfile back = PlayerProfile.fromMap(p.toMap());
        assertEquals("paramedic", back.career.effective(), "the journal is saved");
        assertEquals(1, back.career.reconcile(Set.of("running")::contains));
        assertEquals("paramedic", back.career.effective());
        assertEquals(1, back.career.reconcile(id -> false));
        assertEquals("courier", back.career.effective());
    }
}
