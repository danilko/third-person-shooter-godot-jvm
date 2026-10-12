package com.openworld.game.profile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class EconomyTableTest {
    @Test
    void theShippedTableParsesAndPricesEveryShopRow() throws Exception {
        EconomyTable t = EconomyTable.parse(Files.readString(Path.of("src/main/resources/com/openworld/game/economy.json")));
        assertTrue(t.startingCash > 0);
        assertEquals(2500L, t.weaponPrice("ASR1", false));
        assertEquals(500L, t.weaponPrice("ASR1", true));     // a refill at 20 %
        assertEquals(45L, t.supplyPrice("onigiri", 3));
        assertNull(t.weaponPrice("NOPE", false));
        assertEquals(1500L, t.missionReward("m01_konbini"));
        assertEquals(t.missionDefault, t.missionReward("unknown_mission"));
        assertEquals(800L, t.racePrize(1));
        assertEquals(0L, t.racePrize(9));
        // every weapon the catalog ships (bar the fist) has a price, so no shop row is accidentally free
        String catalog = Files.readString(Path.of("src/main/resources/com/openworld/weapon/weapon_catalog.json"));
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("\"id\"\\s*:\\s*\"(\\w+)\"").matcher(catalog);
        while (m.find()) {
            if (m.group(1).equals("Fist")) continue;
            assertTrue(t.weapons.containsKey(m.group(1)), "no price for " + m.group(1));
        }
        String supplies = Files.readString(Path.of("src/main/resources/com/openworld/item/supplies.json"));
        java.util.Map<String, Object> s = Maps.map(Maps.map(com.openworld.util.MiniJson.parse(supplies)).get("supplies"));
        for (String id : s.keySet()) assertTrue(t.suppliesPerUnit.containsKey(id), "no price for supply " + id);
    }
}
