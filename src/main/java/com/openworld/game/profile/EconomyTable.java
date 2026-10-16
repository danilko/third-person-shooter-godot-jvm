package com.openworld.game.profile;

import com.openworld.util.DataReader;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * THE economy table (PLAN.md 1.4 / F3), {@code game/economy.json}: what things cost and what play pays. Sinks here are
 * the shop prices (weapons, a refill of one already carried, supplies per unit); the bills stay where they were
 * authored (crimes.json / gangs.json via RecoveryRules). Sources here are mission and race rewards; robbery is each
 * clerk's till. Parsing is engine-free ({@code EconomyTableTest}); {@link #get} reads the res:// file once.
 */
public final class EconomyTable {
    public static final String PATH = "res://src/main/resources/com/openworld/game/economy.json";

    public long startingCash;
    public double refillFraction = 0.2;
    public final Map<String, Long> weapons = new LinkedHashMap<>();
    public final Map<String, Long> suppliesPerUnit = new LinkedHashMap<>();
    /** Owned things (item.Gadgets), bought once: the flashlight. */
    public final Map<String, Long> gadgets = new LinkedHashMap<>();
    public long missionDefault;
    public final Map<String, Long> missions = new LinkedHashMap<>();
    public final List<Long> raceByPlace = new ArrayList<>();
    private final Set<String> unpricedLogged = new LinkedHashSet<>();

    /** The game's table (an empty one -- everything free -- when the file is missing or unreadable). */
    public static EconomyTable get() { return com.openworld.game.data.Tables.ECONOMY.get(); }

    public static EconomyTable parse(String json) { return read(DataReader.of(json)); }

    public static EconomyTable read(DataReader d) {
        EconomyTable t = new EconomyTable();
        t.startingCash = d.lng("starting_cash", 0);
        t.refillFraction = Math.max(0.0, d.num("refill_fraction", 0.2));
        readLongs(d.child("weapons"), t.weapons);
        readLongs(d.child("supplies_per_unit"), t.suppliesPerUnit);
        readLongs(d.child("gadgets"), t.gadgets);
        DataReader r = d.child("rewards");
        if (r != null) {
            t.missionDefault = r.lng("mission_default", 0);
            readLongs(r.child("missions"), t.missions);
            t.raceByPlace.addAll(r.longs("race_by_place"));
        }
        return t;
    }

    private static void readLongs(DataReader m, Map<String, Long> out) {
        if (m == null) return;
        for (String k : m.keys()) out.put(k, m.lng(k, 0));
    }

    /** A weapon's price; {@code carried} = a refill of one already in the inventory. Null = not priced (free). */
    public Long weaponPrice(String id, boolean carried) {
        Long p = weapons.get(id);
        if (p == null) return null;
        return carried ? roundTo10(p * refillFraction) : p;
    }

    /** The price of {@code units} of a supply. Null = not priced (free). */
    public Long supplyPrice(String id, long units) {
        Long u = suppliesPerUnit.get(id);
        return u == null ? null : u * Math.max(0, units);
    }

    /** A gadget's price. Null = not priced (free). */
    public Long gadgetPrice(String id) { return gadgets.get(id); }

    public long missionReward(String missionId) {
        Long v = missionId == null ? null : missions.get(missionId);
        return v != null ? v : missionDefault;
    }

    /** The prize for finishing at {@code place} (1-based); 0 past the table. */
    public long racePrize(int place) {
        return place >= 1 && place <= raceByPlace.size() ? raceByPlace.get(place - 1) : 0;
    }

    /** True the first time an id is found unpriced (so the caller logs it once). */
    public boolean firstUnpriced(String id) { return unpricedLogged.add(id); }

    private static long roundTo10(double v) { return Math.round(v / 10.0) * 10L; }
}
