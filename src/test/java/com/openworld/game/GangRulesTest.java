package com.openworld.game;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class GangRulesTest {

    static GangRules rules() throws Exception {
        return GangRules.parse(Files.readString(Path.of("src/main/resources/com/openworld/game/gangs.json")));
    }

    @Test
    void theShippedTableParses() throws Exception {
        GangRules r = rules();
        assertTrue(r.gangs.containsKey("gang_a"));
        assertTrue(r.attackAt <= r.payAt && r.payAt <= r.chaseAt, "attack, then pay-only, then chase");
        for (String c : new String[] {"hit_member", "kill_member", "threaten_clerk", "rob_gray"}) assertNotNull(r.crimes.get(c), c);
    }

    @Test
    void lowHeatAttacksAndDrainsHighHeatHoldsUntilPaid() throws Exception {
        GangRules r = rules();
        GangRules.State s = new GangRules.State();
        r.report(s, "hit_member", 0.0);
        assertTrue(r.attacks(s), "one hit on a member: they attack on sight");
        double t = 0.0;
        for (int i = 0; i < 100000 && s.heat > 0; i++) { t += 0.1; r.tick(s, t, 0.1); }
        assertEquals(0.0, s.heat, 1e-9, "below the pay threshold it drains");
        r.report(s, "rob_gray", t);
        assertTrue(r.starsFor(s.heat) >= r.payAt);
        double h = s.heat;
        for (int i = 0; i < 100000; i++) { t += 0.1; r.tick(s, t, 0.1); }
        assertEquals(h, s.heat, 1e-9, "at or above the pay threshold it never drains");
        assertEquals(r.gangs.get("gang_a").feePerStar() * r.starsFor(s.heat), r.fee("gang_a", s));
        assertTrue(r.chases(s) == (r.starsFor(s.heat) >= r.chaseAt));
    }
}
