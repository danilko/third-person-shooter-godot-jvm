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
}
