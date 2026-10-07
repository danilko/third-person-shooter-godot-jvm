package com.openworld.game;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DispatchRulesTest {

    private static String read(String name) throws Exception {
        return Files.readString(Path.of("src/main/resources/com/openworld/game/" + name));
    }

    @Test
    void policeUnitsGrowWithStarsAndShootFromTheThreshold() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        assertNotNull(r);
        assertEquals(0, r.footFor(0));
        assertEquals(0, r.carsFor(0));
        for (int s = 1; s < 6; s++) {
            assertTrue(r.footFor(s + 1) >= r.footFor(s), "foot units never shrink with stars");
            assertTrue(r.carsFor(s + 1) >= r.carsFor(s), "cars never shrink with stars");
        }
        assertTrue(r.footFor(1) > 0, "one star sends someone");
        assertFalse(r.shoots(1, false), "one star is an arrest");
        assertTrue(r.shoots(1, true), "lethal-wanted is shot at any stars");
        assertTrue(r.shoots(r.shootAt, false));
        assertEquals(r.footFor(6), r.footFor(9), "past the table the last row holds");
    }

    @Test
    void gangHuntersAlwaysShootAndOnlyFromChaseAt() throws Exception {
        DispatchRules g = DispatchRules.parse(read("gangs.json"), "hunters");
        assertNotNull(g);
        assertTrue(g.shoots(1, false));
        assertEquals(0, g.footFor(2), "below chase_at nobody hunts");
        assertTrue(g.footFor(3) > 0);
        assertFalse(g.weapons.isEmpty());
    }

    @Test
    void theArrestClockNeedsAnUnbrokenMoment() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        double c = 0;
        for (int i = 0; i < 10; i++) c = r.arrestClock(c, true, true, 0.1);
        assertEquals(1.0, c, 1e-9);
        assertEquals(0.0, r.arrestClock(c, false, true, 0.1), "the officer stepped away");
        assertEquals(0.0, r.arrestClock(c, true, false, 0.1), "the player got into a car");
    }

    @Test
    void spawningFillsTheGapAFewAtATime() {
        assertEquals(2, DispatchRules.toSpawn(8, 0, 2));
        assertEquals(1, DispatchRules.toSpawn(8, 7, 2));
        assertEquals(0, DispatchRules.toSpawn(3, 5, 2));
    }
}
