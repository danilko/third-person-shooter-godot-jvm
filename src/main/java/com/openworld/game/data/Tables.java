package com.openworld.game.data;

import com.openworld.character.OutfitTable;
import com.openworld.game.DispatchRules;
import com.openworld.game.GangRules;
import com.openworld.game.RecoveryRules;
import com.openworld.game.WantedRules;
import com.openworld.game.profile.EconomyTable;
import com.openworld.item.SupplyCatalog;
import com.openworld.util.DataReader;
import com.openworld.util.DataTable;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * THE list of the game's data tables (PLAN.md 2.0). Each file is declared once here with the typed value it parses
 * to; a system asks {@code Tables.CRIMES.get()} instead of reading and walking the JSON itself. Engine-free:
 * {@code DataTablesTest} loads every one from the source tree and fails on an unknown key, a wrong type or a missing
 * required value, so a typo in a table is caught by {@code ./gradlew test}, not in play.
 *
 * <p>A new table = one {@code define} here + its parser taking a {@link DataReader}. Not here (yet): the generated
 * {@code weapon/weapon_catalog.json} (its generator owns its shape) and the baked world records (places, street
 * names, sidewalks), which are build outputs, not tuning.
 */
public final class Tables {
    private Tables() {}

    private static final String ROOT = "res://src/main/resources/com/openworld/";

    /** crimes.json: the wanted rules, the police dispatch and the recovery fees. */
    public record Crimes(WantedRules wanted, DispatchRules dispatch, DataReader fees) {}

    /** gangs.json: the gang rules, the hunters' dispatch, each gang's bodies, the hangouts and the abduction. */
    public record Gangs(GangRules rules, DispatchRules hunters, Map<String, List<DispatchRules.BodyPick>> bodies,
                        Hangout hangout, DataReader abduction) {}

    /** gangs.json {@code hangout}: members standing about each gang place (game.GangHangouts). */
    public record Hangout(int count, double near, double far, double ringMin, double ringMax, double patrolRadius,
                          List<String> weapons) {
        public static final Hangout DEFAULT = new Hangout(4, 70.0, 110.0, 3.0, 8.0, 6.0, List.of("PIS1"));

        static Hangout read(DataReader h) {
            if (h == null) return DEFAULT;
            double[] ring = h.nums("ring");
            List<String> w = h.strings("weapons");
            return new Hangout(h.integer("count", DEFAULT.count), h.num("near", DEFAULT.near), h.num("far", DEFAULT.far),
                    ring != null && ring.length == 2 ? ring[0] : DEFAULT.ringMin,
                    ring != null && ring.length == 2 ? ring[1] : DEFAULT.ringMax,
                    h.num("patrol_radius", DEFAULT.patrolRadius), w.isEmpty() ? DEFAULT.weapons : List.copyOf(w));
        }
    }

    /** item/ammo_supply.json: which vehicles carry spare ammunition, and how it is used. */
    public record AmmoSupplies(double reach, double restockSeconds, Map<String, Integer> stockByVehicle) {
        static AmmoSupplies read(DataReader d) {
            Map<String, Integer> stock = new HashMap<>();
            for (Map.Entry<String, DataReader> e : d.rows("vehicles").entrySet())
                stock.put(e.getKey(), e.getValue().integer("stock", 0));
            return new AmmoSupplies(d.num("reach", 2.2), d.num("restock_seconds", 2.0), stock);
        }
    }

    public static final DataTable<Crimes> CRIMES = DataTable.define("crimes", ROOT + "game/crimes.json",
            d -> new Crimes(WantedRules.read(d), DispatchRules.read(d.child("dispatch")), fees(d)), () -> null);

    public static final DataTable<Gangs> GANGS = DataTable.define("gangs", ROOT + "game/gangs.json",
            d -> new Gangs(GangRules.read(d), DispatchRules.read(d.child("hunters")), DispatchRules.readGangBodies(d),
                    Hangout.read(d.child("hangout")), abduction(d)), () -> null);

    public static final DataTable<EconomyTable> ECONOMY = DataTable.define("economy", ROOT + "game/economy.json",
            EconomyTable::read, EconomyTable::new);

    public static final DataTable<Map<String, SupplyCatalog.Supply>> SUPPLIES = DataTable.define("supplies",
            ROOT + "item/supplies.json", SupplyCatalog::read, LinkedHashMap::new);

    public static final DataTable<AmmoSupplies> AMMO_SUPPLY = DataTable.define("ammo_supply",
            ROOT + "item/ammo_supply.json", AmmoSupplies::read, () -> new AmmoSupplies(2.2, 2.0, Map.of()));

    public static final DataTable<Map<com.openworld.game.WorldDensity, com.openworld.game.WorldDensity.Row>> DENSITY =
            DataTable.define("density", ROOT + "game/density.json", com.openworld.game.WorldDensity::read, Map::of);

    public static final DataTable<com.openworld.world.TrafficMix> TRAFFIC = DataTable.define("traffic",
            ROOT + "game/traffic.json",
            d -> com.openworld.world.TrafficMix.read(d, id -> com.openworld.carrier.vehicle.VehicleModels.sceneOfId(id) != null),
            () -> new com.openworld.world.TrafficMix(com.openworld.world.TrafficMix.EMPTY, Map.of()));

    public static final DataTable<Map<String, Map<String, Object>>> OUTFITS = DataTable.define("outfits",
            ROOT + "character/outfits.json", OutfitTable::read, HashMap::new);

    // The recovery rules are read out of TWO files; each block is read while its own file loads, so the unknown-key
    // check of that file covers it.
    private static DataReader fees(DataReader crimes) {
        DataReader f = crimes.child("fees");
        RecoveryRules.read(f, null);
        return f;
    }

    private static DataReader abduction(DataReader gangs) {
        DataReader a = gangs.child("abduction");
        RecoveryRules.read(null, a);
        return a;
    }

    /** What waking up costs (crimes.json {@code fees} + gangs.json {@code abduction}); defaults for a missing file. */
    public static RecoveryRules recovery() {
        Crimes c = CRIMES.get();
        Gangs g = GANGS.get();
        return RecoveryRules.read(c == null ? null : c.fees(), g == null ? null : g.abduction());
    }

    /** Touch every table so {@link DataTable#all} lists them (a static field is only declared once its class runs). */
    public static List<DataTable<?>> all() { return DataTable.all(); }
}
