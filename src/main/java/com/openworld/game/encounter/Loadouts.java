package com.openworld.game.encounter;

import com.openworld.util.DataReader;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * {@code character/loadouts.json} (PLAN.md 2.2 / 1j): what a PLACED AI carries and wears -- an Encounter's members and
 * the guards at a building's {@code MARK_spawn} markers. Engine-free ({@code LoadoutsTest}); read through
 * {@code Tables.LOADOUTS}.
 */
public final class Loadouts {

    /** One loadout: whose body rows and faction ({@code side}, "" = the caller's), the uniform, ONE weighted weapon
     *  and the extras every body gets. */
    public record Loadout(String id, String side, String outfit, List<String> weapons, double[] weights, List<String> extra) {
        /** The weapon for a body whose stable roll is {@code r} in [0, 1); "" when the loadout has none. */
        public String weapon(double r) {
            if (weapons.isEmpty()) return "";
            double total = 0;
            for (double w : weights) total += Math.max(0, w);
            if (total <= 0) return weapons.get((int) (Math.min(Math.max(r, 0), Math.nextDown(1.0)) * weapons.size()));
            double target = Math.min(Math.max(r, 0), Math.nextDown(1.0)) * total, acc = 0;
            for (int i = 0; i < weapons.size(); i++) {
                acc += Math.max(0, weights[i]);
                if (target < acc) return weapons.get(i);
            }
            return weapons.get(weapons.size() - 1);
        }

        /** The faction a body of this loadout belongs to: its side, else {@code fallback}. */
        public String sideOr(String fallback) { return side == null || side.isEmpty() ? fallback : side; }
    }

    /** SiteGuards' rules: spawn within {@code near}, take away past {@code far}, per-building and island caps. */
    public record SiteRules(double near, double far, int perBuilding, int cap) {
        public static final SiteRules DEFAULT = new SiteRules(60.0, 100.0, 4, 12);
    }

    /** Defaults for an Encounter's exports left at 0: spawn / despawn distances and the cap over ALL encounters. */
    public record EncounterRules(double spawnNear, double despawnFar, int cap) {
        public static final EncounterRules DEFAULT = new EncounterRules(90.0, 150.0, 24);
    }

    public final Map<String, Loadout> loadouts = new LinkedHashMap<>();
    /** A marker's {@code team} prop -> its default loadout id. */
    public final Map<String, String> teams = new LinkedHashMap<>();
    public SiteRules site = SiteRules.DEFAULT;
    public EncounterRules encounter = EncounterRules.DEFAULT;

    /** A loadout by id, else null. */
    public Loadout get(String id) { return id == null ? null : loadouts.get(id); }

    /** The loadout a marker of {@code team} gets when it names none; null = that team is not a guard. */
    public Loadout forTeam(String team) { return team == null ? null : get(teams.get(team)); }

    public static Loadouts parse(String json) { return read(DataReader.of(json)); }

    public static Loadouts read(DataReader d) {
        Loadouts out = new Loadouts();
        for (Map.Entry<String, DataReader> e : d.rows("loadouts").entrySet()) {
            DataReader r = e.getValue();
            List<String> ids = new ArrayList<>();
            List<Double> ws = new ArrayList<>();
            DataReader w = r.child("weapons");
            if (w != null) for (String k : w.keys()) {
                ids.add(k);
                ws.add(w.num(k, 1.0));
            }
            double[] weights = new double[ws.size()];
            for (int i = 0; i < weights.length; i++) weights[i] = ws.get(i);
            out.loadouts.put(e.getKey(), new Loadout(e.getKey(), r.str("side", ""), r.str("outfit", ""),
                    List.copyOf(ids), weights, List.copyOf(r.strings("extra"))));
        }
        DataReader t = d.child("teams");
        if (t != null) for (String k : t.keys()) {
            String id = t.str(k, "");
            if (!out.loadouts.containsKey(id)) t.problem(k, "names no loadout: " + id);
            out.teams.put(k, id);
        }
        DataReader s = d.child("site_guards");
        if (s != null) out.site = new SiteRules(s.num("near", SiteRules.DEFAULT.near()), s.num("far", SiteRules.DEFAULT.far()),
                s.integer("per_building", SiteRules.DEFAULT.perBuilding()), s.integer("cap", SiteRules.DEFAULT.cap()));
        DataReader en = d.child("encounter");
        if (en != null) out.encounter = new EncounterRules(en.num("spawn_near", EncounterRules.DEFAULT.spawnNear()),
                en.num("despawn_far", EncounterRules.DEFAULT.despawnFar()), en.integer("cap", EncounterRules.DEFAULT.cap()));
        return out;
    }

    /** A stable roll in [0, 1) from a string (a marker's path, a body's id): the same body gets the same weapon on
     *  every peer and in every run. */
    public static double roll(String key) {
        long h = 1125899906842597L;
        if (key != null) for (int i = 0; i < key.length(); i++) h = 31 * h + key.charAt(i);
        // murmur3's full fmix64: one round left keys that differ in their last character ("#0", "#1") within 0.3 %
        // of each other, so a whole crew rolled the same weapon
        h ^= (h >>> 33);
        h *= 0xff51afd7ed558ccdL;
        h ^= (h >>> 33);
        h *= 0xc4ceb9fe1a85ec53L;
        h ^= (h >>> 33);
        return (h >>> 11) * 0x1.0p-53;
    }
}
