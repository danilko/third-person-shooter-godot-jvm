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

    @org.junit.jupiter.api.Test
    void policeEscalateWithTheStars() throws Exception {
        DispatchRules r = DispatchRules.parse(read("crimes.json"), "dispatch");
        org.junit.jupiter.api.Assertions.assertTrue(r.weaponsFor(1).contains("PIS1"));
        org.junit.jupiter.api.Assertions.assertTrue(r.weaponsFor(6).contains("ATL1"), "rockets at the top");
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(6).contains("TNK1"), "a tank at 6 stars");
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(5).contains("LTK1"), "a light tank at 5 stars");
        org.junit.jupiter.api.Assertions.assertFalse(r.vehiclesFor(3).contains("ARV1"), "no armour at 3 stars");
        org.junit.jupiter.api.Assertions.assertFalse(r.rams(3));
        org.junit.jupiter.api.Assertions.assertTrue(r.rams(4));
        org.junit.jupiter.api.Assertions.assertTrue(r.breaches(3));
        org.junit.jupiter.api.Assertions.assertFalse(r.breaches(2));
        org.junit.jupiter.api.Assertions.assertEquals(0, r.snipersFor(3));
        org.junit.jupiter.api.Assertions.assertTrue(r.snipersFor(5) > 0);
        org.junit.jupiter.api.Assertions.assertTrue(r.helisFor(5) > 0);
        org.junit.jupiter.api.Assertions.assertTrue(r.hasGun("TNK1") && !r.hasGun("POC1"));
        // past the table's end the last row holds
        org.junit.jupiter.api.Assertions.assertEquals(r.vehiclesFor(6), r.vehiclesFor(9));
    }

    @org.junit.jupiter.api.Test
    void gangsEscalateToo() throws Exception {
        DispatchRules r = DispatchRules.parse(read("gangs.json"), "hunters");
        org.junit.jupiter.api.Assertions.assertTrue(r.rams(4) && r.breaches(3));
        org.junit.jupiter.api.Assertions.assertTrue(r.vehiclesFor(5).isEmpty(), "gangs drive civilian cars");
    }
}
