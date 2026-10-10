package com.openworld.game.data;

import com.openworld.util.DataReader;
import com.openworld.util.DataTable;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** PLAN.md 2.0: every declared table loads from the source tree with NO problem (unknown key, wrong type, missing). */
class DataTablesTest {

    @BeforeAll
    static void readFromTheSourceTree() {
        DataTable.setSource(DataTable.DISK);
        DataTable.setLog((t, m) -> { });
    }

    @Test
    void everyTableIsDeclaredAndClean() {
        assertNotNull(Tables.CRIMES.get());
        List<String> names = new ArrayList<>();
        for (DataTable<?> t : Tables.all()) names.add(t.name);
        assertEquals(List.of("crimes", "gangs", "economy", "supplies", "ammo_supply", "traffic", "outfits"), names);
        assertEquals(List.of(), DataTable.validateAll());
    }

    @Test
    void theTypedValuesAreTheFilesValues() {
        assertEquals(5, Tables.CRIMES.get().wanted().starsAt.length);
        assertEquals(1, Tables.CRIMES.get().dispatch().shootAt);
        assertTrue(Tables.GANGS.get().rules().gangs.containsKey("gang_a"));
        assertFalse(Tables.GANGS.get().bodies().get("gang_a").isEmpty());
        assertEquals(4, Tables.GANGS.get().hangout().count() > 0 ? 4 : 0, "a hangout has members");
        assertEquals(5000, Tables.recovery().hospital);
        assertTrue(Tables.recovery().ransomPerStar > 0);
        assertTrue(Tables.ECONOMY.get().startingCash > 0);
        assertTrue(Tables.SUPPLIES.get().containsKey("onigiri"));
        assertTrue(Tables.AMMO_SUPPLY.get().stockByVehicle().get("POC1") > 0);
        assertTrue(Tables.OUTFITS.get().containsKey("police"));
    }

    /** The control: the same parser on a table with a typo reports it (so the clean result above means something). */
    @Test
    void aTypoInATableIsCaught() {
        DataTable<Tables.Crimes> bad = DataTable.detached("crimes_typo", "mem://crimes_typo",
                d -> new Tables.Crimes(com.openworld.game.WantedRules.read(d), null, null), () -> null);
        DataTable.setSource(p -> p.startsWith("mem://")
                ? "{\"stars_at\":[1],\"crimes\":{\"gunfire\":{\"heat\":\"10\",\"min_star\":1}},\"calm_second\":3}"
                : DataTable.DISK.read(p));
        try {
            assertEquals(List.of("crimes.gunfire.heat: expected a number, found a string", "calm_second: unknown key",
                    "crimes.gunfire.min_star: unknown key"), bad.problems());
        } finally {
            DataTable.setSource(DataTable.DISK);
        }
    }

    @Test
    void aMissingFileGivesTheFallbackAndSaysSo() {
        DataTable<String> none = DataTable.detached("none", "res://no/such/table.json", DataReader::path, () -> "fallback");
        assertEquals("fallback", none.get());
        assertEquals(1, none.problems().size());
    }

    @Test
    void reloadTellsTheListeners() {
        int[] told = {0};
        Runnable r = () -> told[0]++;
        Tables.ECONOMY.onReload(r);
        int v = Tables.ECONOMY.version();
        Tables.ECONOMY.reload();
        Tables.ECONOMY.offReload(r);
        assertEquals(1, told[0]);
        assertTrue(Tables.ECONOMY.version() > v);
    }
}
