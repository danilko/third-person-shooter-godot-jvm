package com.openworld.game.profile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;
import org.junit.jupiter.api.Test;

class SaveMigrationsTest {
    @Test
    void aV1WorldIsMigratedNotRefusedAndKeepsItsKeys() {
        Map<String, Object> v1 = new LinkedHashMap<>();
        v1.put("schema", 1.0);
        v1.put("campaign", Map.of("completed", List.of("m01")));
        Map<String, Object> out = SaveMigrations.migrate(v1, "schema", SaveMigrations.WORLD);
        assertEquals((long) SaveMigrations.WORLD_VERSION, ((Number) out.get("schema")).longValue());
        assertEquals(v1.get("campaign"), out.get("campaign"));
    }

    @Test
    void stepsRunInOrderAndANewerFileIsRefused() {
        List<UnaryOperator<Map<String, Object>>> steps = List.of(
                d -> { d.put("trail", "a"); return d; },
                d -> { d.put("trail", d.get("trail") + "b"); return d; });
        Map<String, Object> doc = new LinkedHashMap<>(Map.of("v", 1.0));
        Map<String, Object> out = SaveMigrations.migrate(doc, "v", steps);
        assertEquals("ab", out.get("trail"));
        assertEquals(3L, ((Number) out.get("v")).longValue());
        assertNull(SaveMigrations.migrate(new LinkedHashMap<>(Map.of("v", 4.0)), "v", steps));
        assertNull(SaveMigrations.migrate(new LinkedHashMap<>(Map.of()), "v", steps));
    }

    @Test
    void aV1ProfileHoldsATenthInDollars() {
        Map<String, Object> debt = new java.util.LinkedHashMap<>();
        debt.put("lender", "gang_a"); debt.put("principal", 50004L); debt.put("due_at", 7L);
        Map<String, Object> small = new java.util.LinkedHashMap<>();
        small.put("lender", "bank"); small.put("principal", 3L);
        Map<String, Object> doc = new java.util.LinkedHashMap<>();
        doc.put("version", 1L); doc.put("balance", -15005L); doc.put("debts", java.util.List.of(debt, small));
        doc.put("something_new", "kept");
        Map<String, Object> out = SaveMigrations.migrate(doc, "version", SaveMigrations.PROFILE);
        assertEquals((long) SaveMigrations.PROFILE_VERSION, ((Number) out.get("version")).longValue());
        PlayerProfile p = PlayerProfile.fromMap(out);
        assertEquals(-1500L, p.balance);                       // -1500.5 rounds half up
        assertEquals(5000L, p.debts.get(0).principal());
        assertEquals(7L, p.debts.get(0).dueAtUnix());
        assertEquals(1L, p.debts.get(1).principal(), "a debt never rounds to nothing");
        assertEquals("kept", out.get("something_new"));
        // a v2 profile is left alone
        Map<String, Object> v2 = new java.util.LinkedHashMap<>(p.toMap());
        assertEquals(-1500L, PlayerProfile.fromMap(SaveMigrations.migrate(v2, "version", SaveMigrations.PROFILE)).balance);
    }
}
