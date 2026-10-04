package com.openworld.item;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SupplyCatalogTest {

    static Map<String, SupplyCatalog.Supply> table() throws Exception {
        return SupplyCatalog.parse(Files.readString(Path.of("src/main/resources/com/openworld/item/supplies.json")));
    }

    @Test
    void everyKindIsSoldAndEveryRowHeals() throws Exception {
        var t = table();
        for (String kind : new String[] {"food", "medical", "strange"})
            assertTrue(t.values().stream().anyMatch(s -> s.kind().equals(kind)), kind);
        for (var s : t.values()) {
            assertTrue(s.heal() > 0, s.id());
            assertTrue(s.max() > 0, s.id());
        }
    }

    @Test
    void theSmallestThatHealsItAllIsUsedElseTheBiggest() throws Exception {
        var t = table();
        Map<String, Integer> carried = new LinkedHashMap<>();
        carried.put("med_kit", 1);
        carried.put("onigiri", 2);
        carried.put("bandage", 1);
        assertEquals("onigiri", SupplyCatalog.best(carried, t, 12f));
        assertEquals("bandage", SupplyCatalog.best(carried, t, 20f));
        assertEquals("med_kit", SupplyCatalog.best(carried, t, 90f));
        assertEquals("med_kit", SupplyCatalog.best(carried, t, 500f));
        carried.put("med_kit", 0);
        assertEquals("bandage", SupplyCatalog.best(carried, t, 500f));
        assertNull(SupplyCatalog.best(new LinkedHashMap<>(), t, 10f));
    }

    @Test
    void stockIdsNeverCollideWithWeaponIds() throws Exception {
        String catalog = Files.readString(Path.of("src/main/resources/com/openworld/weapon/weapon_catalog.json"));
        for (String id : table().keySet()) assertFalse(catalog.contains("\"" + id + "\""), id);
    }
}
