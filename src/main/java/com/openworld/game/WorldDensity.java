package com.openworld.game;

import com.openworld.util.DataReader;

import java.util.EnumMap;
import java.util.Map;

/**
 * WORLD DENSITY (user, 2026-10-10: "a setting for more crowd vehicles / peds / AI attackers, in case every player's
 * system is high end"): how much the HOST simulates. It is one value per session, the host's -- the bodies it adds
 * are replicated, collidable and shootable, so every peer plays the same street and the same fight whatever its own
 * hardware (PLAN.md H3: host-decided, never scaled per machine). A client's own choice only matters when it hosts.
 *
 * <p>The numbers of each level are DATA ({@code game/density.json}, {@code Tables.DENSITY}), so a level is tuned in
 * one place and a performance run can be made at any of them ({@code OW_WORLD_DENSITY=HIGH}). The values below are
 * only what a missing table gives. Measured on the development PC (probe_walk_perf, 2026-10-10, walk_downtown
 * physics ms p50 / frame p95): 10 cars 6.2 / 18.1, 16 cars 9.3 / 18.1, 22 cars 13.9 / 19.6 -- a car is a physics body
 * AND a seated driver, so ULTRA wants a desktop CPU. Since 2026-10-10 late a car on rails carries NO driver
 * (ZoneManager.trafficLazyDrivers) and the levels are 20 / 26 / 32: measured the same way (physics ms a frame, p95,
 * walk / drive downtown) 12 cars with a driver each 18.8 / 19.8, and without far drivers 12 cars 13.7 / 14.9,
 * 20 cars 13.6 / 16.5, 28 cars 14.7 / 19.0.
 */
public enum WorldDensity {
    NORMAL("Normal", new Row(20, 8, 6, 0, 48, 80, 8)),
    HIGH("High", new Row(26, 12, 8, 1, 60, 120, 12)),
    ULTRA("Ultra", new Row(32, 16, 10, 2, 72, 160, 16));

    /**
     * One level's numbers: simulated ambient cars (ZoneManager.trafficBudget), crowd peds promoted to full bodies and
     * how many of them may fight (walkerBudget / fighterBudget), and the units added to the dispatch's attack tokens
     * at every star level that has a limit, and the island-wide ceiling on enforcement bodies (police, gangs,
     * responders together -- EnforcementDispatch.bodyCap; PLAN.md P1e step 2, here since 2026-10-15 so the host's
     * level decides it), and the LIGHT COMBATANT tier's size and its full-body budget (ai.light.LightCombatants
     * cap / fullBudget; PLAN.md 2.3, measured with tools/godot/bench_light_tier.gd on the Deck proxy).
     */
    public record Row(int traffic, int walkers, int fighters, int attackTokens, int bodyCap, int lightCap, int lightFullBudget) {}

    public final String label;
    private final Row builtIn;

    WorldDensity(String label, Row builtIn) {
        this.label = label;
        this.builtIn = builtIn;
    }

    public Row builtIn() { return builtIn; }

    /** This level's numbers: the table's row, else the built-in one. */
    public Row row() {
        Map<WorldDensity, Row> t = com.openworld.game.data.Tables.DENSITY.get();
        Row r = t == null ? null : t.get(this);
        return r != null ? r : builtIn;
    }

    public static WorldDensity of(String name) {
        for (WorldDensity d : values()) if (d.name().equalsIgnoreCase(name)) return d;
        return NORMAL;
    }

    /** Parse game/density.json: a level that is missing, misspelt or not positive is a problem. */
    public static Map<WorldDensity, Row> read(DataReader d) {
        Map<WorldDensity, Row> out = new EnumMap<>(WorldDensity.class);
        DataReader levels = d.child("levels");
        if (levels == null) {
            d.problem("levels", "missing");
            return out;
        }
        for (String key : levels.keys()) {
            WorldDensity level = null;
            for (WorldDensity w : values()) if (w.name().equals(key)) level = w;
            DataReader r = levels.child(key);
            if (level == null) { levels.problem(key, "not a density level"); continue; }
            if (r == null) continue;
            Row row = new Row(r.integer("traffic", level.builtIn.traffic()), r.integer("walkers", level.builtIn.walkers()),
                    r.integer("fighters", level.builtIn.fighters()), r.integer("attack_tokens", level.builtIn.attackTokens()),
                    r.integer("body_cap", level.builtIn.bodyCap()), r.integer("light_cap", level.builtIn.lightCap()),
                    r.integer("light_full_budget", level.builtIn.lightFullBudget()));
            if (row.traffic() < 1 || row.walkers() < 1 || row.fighters() < 0 || row.attackTokens() < 0 || row.bodyCap() < 0
                    || row.lightCap() < 0 || row.lightFullBudget() < 0) {
                levels.problem(key, "traffic and walkers must be at least 1, the others not negative (body_cap 0 = no cap)");
                continue;
            }
            out.put(level, row);
        }
        for (WorldDensity w : values()) if (!out.containsKey(w)) levels.problem(w.name(), "missing (the built-in numbers are used)");
        return out;
    }
}
