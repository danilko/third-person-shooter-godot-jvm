package com.openworld.game.profile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.openworld.util.MiniJson;
import java.util.Map;
import org.junit.jupiter.api.Test;

class PlayerProfileTest {
    @Test
    @SuppressWarnings("unchecked")
    void roundTripsThroughJsonKeepingUnknownKeys() {
        PlayerProfile p = new PlayerProfile("pid-1");
        p.balance = -1200;
        p.debts.add(new PlayerProfile.Debt("loan_shark", 50_000, 1_800_000_000L));
        p.career.base = "police";
        p.career.recordByCareer.computeIfAbsent("police", k -> new java.util.LinkedHashMap<>()).put("rank", 3L);
        p.career.overrideJournal.add("activity#7");
        p.campaign.flags.put("met_kaito", "true");
        p.campaign.achieved.add("m01_konbini:clean");
        p.campaign.phase = "POST_ENDING";
        VehicleInstanceData v = new VehicleInstanceData();
        v.instanceId = "car-1";
        v.model = "res://x/SPC1.tscn";
        v.paint = "#ff0000";
        v.upgrades.put("nos", 2L);
        v.condition = 0.4;
        v.garageId = "safehouse";
        p.vehicles.add(v);
        p.unlocks.add("shop:ASR1");
        Map<String, Object> m = p.toMap();
        m.put("from_a_newer_build", 42.0);
        String json = MiniJson.write(m);
        PlayerProfile q = PlayerProfile.fromMap((Map<String, Object>) MiniJson.parse(json));
        assertEquals("pid-1", q.playerId);
        assertEquals(-1200, q.balance);
        assertEquals(new PlayerProfile.Debt("loan_shark", 50_000, 1_800_000_000L), q.debts.get(0));
        assertEquals("police", q.career.base);
        assertEquals(3L, q.career.record("police", "rank"));
        assertEquals("activity#7", q.career.overrideJournal.get(0));
        assertEquals("true", q.campaign.flags.get("met_kaito"));
        assertTrue(q.campaign.achieved.contains("m01_konbini:clean"));
        assertEquals("POST_ENDING", q.campaign.phase);
        VehicleInstanceData w = q.vehicle("car-1");
        assertEquals(2L, w.upgrade("nos"));
        assertEquals(0.4, w.condition, 1e-9);
        assertEquals("safehouse", w.garageId);
        assertTrue(q.unlocks.contains("shop:ASR1"));
        assertEquals(42.0, ((Number) q.toMap().get("from_a_newer_build")).doubleValue());
        assertEquals(1200 + 50_000, q.totalDebt());
        assertEquals(json, MiniJson.write(q.toMap()));
    }

    @Test
    void copyFromReplacesAndBumpsTheRevision() {
        PlayerProfile a = new PlayerProfile("a");
        a.balance = 10;
        PlayerProfile b = new PlayerProfile("b");
        b.balance = 99;
        b.unlocks.add("x");
        long r = a.revision();
        a.copyFrom(b);
        assertEquals(99, a.balance);
        assertTrue(a.unlocks.contains("x"));
        assertTrue(a.revision() > r);
    }
}
