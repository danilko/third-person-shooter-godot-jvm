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
    void stockIdsNeverCollideWithWeaponIds() throws Exception {
        String catalog = Files.readString(Path.of("src/main/resources/com/openworld/weapon/weapon_catalog.json"));
        for (String id : table().keySet()) assertFalse(catalog.contains("\"" + id + "\""), id);
    }

    @Test
    void everyKindHasAnIconAndTheSharedSceneExists() throws Exception {
        assertTrue(Files.exists(Path.of("src/main/resources/com/openworld/weapon/Supply.tscn")), "weapon/Supply.tscn");
        for (var s : table().values())
            assertTrue(Files.exists(Path.of("assets/ui/weapons/supply_" + s.kind() + ".png")), s.id() + ": supply_" + s.kind() + ".png");
    }
}
