package com.openworld.game;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class WantedRulesTest {

    static WantedRules rules() throws Exception {
        return WantedRules.parse(Files.readString(Path.of("src/main/resources/com/openworld/game/crimes.json")));
    }

    @Test
    void theShippedTableParsesAndEveryRowIsUsable() throws Exception {
        WantedRules r = rules();
        assertEquals(WantedRules.MAX_STARS, r.starsAt.length);
        for (int i = 1; i < r.starsAt.length; i++) assertTrue(r.starsAt[i] > r.starsAt[i - 1], "thresholds rise");
        for (String id : new String[] {"gunfire", "assault", "murder", "assault_police", "kill_police",
                "car_theft", "train_attack", "bank_attack", "attack_vip", "threaten_clerk", "rob_store"}) {
            assertNotNull(r.crimes.get(id), id);
            assertTrue(r.crimes.get(id).heat() > 0, id);
        }
    }

    @Test
    void heatGivesStarsAndAFloorSetsThemAtOnce() throws Exception {
        WantedRules r = rules();
        WantedRules.State s = new WantedRules.State();
        assertEquals(0, r.starsFor(s.heat));
        assertTrue(r.report(s, "kill_police", false, 0.0));
        assertEquals(3, r.starsFor(s.heat));
        WantedRules.State t = new WantedRules.State();
        r.report(t, "train_attack", false, 0.0);
        assertEquals(4, r.starsFor(t.heat));
        assertEquals(WantedRules.MAX_STARS, r.starsFor(1e9));
    }

    @Test
    void aWitnessedCrimeNeedsAWitness() throws Exception {
        WantedRules r = rules();
        WantedRules.State s = new WantedRules.State();
        assertFalse(r.report(s, "murder", false, 0.0));
        assertEquals(0.0, s.heat);
        assertTrue(r.report(s, "murder", true, 0.0));
        assertTrue(r.starsFor(s.heat) >= 2);
        assertFalse(r.report(s, "no_such_crime", true, 0.0));
    }

    @Test
    void heatHoldsThroughTheCalmPeriodThenDrainsToZero() throws Exception {
        WantedRules r = rules();
        WantedRules.State s = new WantedRules.State();
        r.report(s, "assault_police", false, 0.0);
        double h = s.heat;
        int stars = r.starsFor(h);
        double calm = r.calmSeconds + r.calmPerStar * stars;
        double t = 0.0;
        while (t < calm - 0.5) { t += 0.1; r.tick(s, t, 0.1); }
        assertEquals(h, s.heat, 1e-9, "no decay during the calm");
        for (int i = 0; i < 10000 && s.heat > 0; i++) { t += 0.1; r.tick(s, t, 0.1); }
        assertEquals(0.0, s.heat, 1e-9);
        // a new crime re-arms the calm
        r.report(s, "assault_police", false, t);
        r.tick(s, t + 1.0, 1.0);
        assertEquals(Math.max(r.crimes.get("assault_police").heat(), r.heatFor(2)), s.heat, 1e-9);
    }

    @Test
    void aRobberyIsLethalUntilTheHeatIsGone() throws Exception {
        WantedRules r = rules();
        WantedRules.State s = new WantedRules.State();
        r.report(s, "threaten_clerk", false, 0.0);
        assertFalse(s.lethal, "a threat alone is not lethal");
        r.report(s, "rob_store", false, 1.0);
        assertTrue(s.lethal);
        assertTrue(r.starsFor(s.heat) >= 2);
        double t = 1.0;
        for (int i = 0; i < 100000 && s.heat > 0; i++) { t += 0.1; r.tick(s, t, 0.1); }
        assertFalse(s.lethal, "the record clears with the heat");
        assertNull(r.crimes.get("rob_gray"), "police treat every store robbery the same; a gray area adds GANG heat");
    }
}
