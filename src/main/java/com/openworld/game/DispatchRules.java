package com.openworld.game;

import com.openworld.util.MiniJson;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * How many enforcement units a standing calls for, and the arrest clock (game.EnforcementDispatch; PLAN.md W5).
 * Engine-free, so it is unit-tested ({@code DispatchRulesTest}). One instance per dispatching side: the police (the
 * {@code dispatch} block of {@code game/crimes.json}) and the gangs (the {@code hunters} block of
 * {@code game/gangs.json}, where every unit shoots).
 */
public final class DispatchRules {

    public final int shootAt;
    public final int[] footByStars, carsByStars;
    public final int carCrew;
    public final double footMin, footMax, carMin, carMax, arriveDist, arrestReach, arrestSeconds, despawnFar,
            seenReach, spawnInterval;
    /** Gang hunters' weapons (empty for police: WantedSystem.policeWeaponsFor decides). */
    public final List<String> weapons;

    DispatchRules(int shootAt, int[] foot, int[] cars, int crew, double footMin, double footMax, double carMin,
                  double carMax, double arriveDist, double arrestReach, double arrestSeconds, double despawnFar,
                  double seenReach, double spawnInterval, List<String> weapons) {
        this.shootAt = shootAt; this.footByStars = foot; this.carsByStars = cars; this.carCrew = crew;
        this.footMin = footMin; this.footMax = footMax; this.carMin = carMin; this.carMax = carMax;
        this.arriveDist = arriveDist; this.arrestReach = arrestReach; this.arrestSeconds = arrestSeconds;
        this.despawnFar = despawnFar; this.seenReach = seenReach; this.spawnInterval = spawnInterval;
        this.weapons = weapons;
    }

    /** Parse one block ({@code dispatch} or {@code hunters}) out of a table's text; null when the block is absent. */
    @SuppressWarnings("unchecked")
    public static DispatchRules parse(String json, String block) {
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(json);
        if (!(doc.get(block) instanceof Map<?, ?> m0)) return null;
        Map<String, Object> m = (Map<String, Object>) m0;
        List<String> w = new ArrayList<>();
        if (m.get("weapons") instanceof List<?> l) for (Object o : l) w.add(String.valueOf(o));
        return new DispatchRules((int) num(m, "shoot_at", 0), ints(m.get("foot_by_stars")),
                ints(m.get("cars_by_stars")), (int) num(m, "car_crew", 2), num(m, "foot_min", 45),
                num(m, "foot_max", 75), num(m, "car_min", 140), num(m, "car_max", 280), num(m, "arrive_dist", 35),
                num(m, "arrest_reach", 2.2), num(m, "arrest_seconds", 1.5), num(m, "despawn_far", 180),
                num(m, "seen_reach", 60), num(m, "spawn_interval", 1.5), w);
    }

    private static double num(Map<String, Object> m, String k, double dflt) {
        return m.get(k) instanceof Number n ? n.doubleValue() : dflt;
    }

    private static int[] ints(Object o) {
        if (!(o instanceof List<?> l)) return new int[] {0};
        int[] out = new int[l.size()];
        for (int i = 0; i < out.length; i++) out[i] = l.get(i) instanceof Number n ? n.intValue() : 0;
        return out;
    }

    private static int at(int[] a, int stars) {
        if (stars <= 0 || a.length == 0) return 0;
        return a[Math.min(stars, a.length - 1)];
    }

    /** Officers on foot (crews of cars that have arrived count as foot) wanted at this many stars. */
    public int footFor(int stars) { return at(footByStars, stars); }

    /** Cars on their way wanted at this many stars. */
    public int carsFor(int stars) { return at(carsByStars, stars); }

    /** Do units shoot? A side with no shoot_at (gangs: 0) always does; police from shoot_at stars or once lethal. */
    public boolean shoots(int stars, boolean lethal) { return lethal || stars >= shootAt; }

    /**
     * The arrest clock: it runs while an officer is within reach of the player, and is reset by anything that breaks
     * the moment (no officer in reach, the player in a car, shooting allowed). Returns the new clock; the arrest
     * happens when it reaches {@link #arrestSeconds}.
     */
    public double arrestClock(double clock, boolean officerInReach, boolean arrestable, double dt) {
        return officerInReach && arrestable ? clock + dt : 0.0;
    }

    /** How many new units to spawn this tick: what is missing, at most {@code perTick}. */
    public static int toSpawn(int want, int have, int perTick) {
        return Math.max(0, Math.min(perTick, want - have));
    }
}
