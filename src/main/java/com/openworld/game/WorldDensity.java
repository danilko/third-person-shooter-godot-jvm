package com.openworld.game;

/**
 * WORLD DENSITY (user, 2026-10-10: "a setting for more crowd vehicles / peds / AI attackers, in case every player's
 * system is high end"): how much the HOST simulates. It is one value per session, the host's -- the bodies it adds
 * are replicated, collidable and shootable, so every peer plays the same street and the same fight whatever its own
 * hardware (PLAN.md H3: host-decided, never scaled per machine). A client's own choice only matters when it hosts.
 *
 * <p>NORMAL is the measured Steam Deck baseline. The steps up were measured on the development PC (probe_walk_perf,
 * 2026-10-10, walk_downtown physics ms p50 / frame p95): 10 cars 6.2 / 18.1, 16 cars 9.3 / 18.1, 22 cars 13.9 / 19.6
 * -- a car is a physics body AND a seated driver, so ULTRA wants a desktop CPU.
 */
public enum WorldDensity {
    /** The Steam Deck baseline. */
    NORMAL("Normal", 10, 8, 6, 0),
    HIGH("High", 16, 12, 8, 1),
    ULTRA("Ultra", 22, 16, 10, 2);

    public final String label;
    /** ZoneManager.trafficBudget: simulated ambient cars. */
    public final int trafficBudget;
    /** ZoneManager.walkerBudget / fighterBudget: crowd peds promoted to full bodies, and how many may fight. */
    public final int walkerBudget, fighterBudget;
    /** Added to the dispatch's attack tokens at every star level that has a limit (units attacking at once). */
    public final int attackTokenBonus;

    WorldDensity(String label, int trafficBudget, int walkerBudget, int fighterBudget, int attackTokenBonus) {
        this.label = label;
        this.trafficBudget = trafficBudget;
        this.walkerBudget = walkerBudget;
        this.fighterBudget = fighterBudget;
        this.attackTokenBonus = attackTokenBonus;
    }

    public static WorldDensity of(String name) {
        for (WorldDensity d : values()) if (d.name().equalsIgnoreCase(name)) return d;
        return NORMAL;
    }
}
