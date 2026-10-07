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

    // ── ESCALATION (PLAN.md W6, user 2026-10-06: heavier units as the stars rise) ──
    /** What a unit carries at this many stars (index = stars); empty = the side's flat list. */
    public List<List<String>> weaponsByStars = new ArrayList<>();
    /** Which vehicles are sent at this many stars (catalog model ids: POC1, ARV1, LTK1, TNK1 ...); empty = the side's
     *  default (ZoneManager.spawnServiceCar's faction pick). */
    public List<List<String>> vehiclesByStars = new ArrayList<>();
    /** Snipers placed at range (SNR1, on a clear line, never closing in), and helicopters, by stars. */
    public int[] snipersByStars = {0}, helisByStars = {0};
    /** From this many stars a car on a call RAMS the player instead of stopping to unload (0 = never). */
    public int ramAt = 0;
    /** Armoured vehicles that fire a main gun (catalog model ids) and how: seconds between shells, range (m). */
    public List<String> gunVehicles = new ArrayList<>();
    public double gunInterval = 4.0, gunRange = 220.0, gunDamage = 320.0, gunRadius = 7.0;

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
        DispatchRules r = new DispatchRules((int) num(m, "shoot_at", 0), ints(m.get("foot_by_stars")),
                ints(m.get("cars_by_stars")), (int) num(m, "car_crew", 2), num(m, "foot_min", 45),
                num(m, "foot_max", 75), num(m, "car_min", 140), num(m, "car_max", 280), num(m, "arrive_dist", 35),
                num(m, "arrest_reach", 2.2), num(m, "arrest_seconds", 1.5), num(m, "despawn_far", 180),
                num(m, "seen_reach", 60), num(m, "spawn_interval", 1.5), w);
        r.weaponsByStars = lists(m.get("weapons_by_stars"));
        r.vehiclesByStars = lists(m.get("vehicles_by_stars"));
        if (m.get("snipers_by_stars") != null) r.snipersByStars = ints(m.get("snipers_by_stars"));
        if (m.get("helis_by_stars") != null) r.helisByStars = ints(m.get("helis_by_stars"));
        r.ramAt = (int) num(m, "ram_at", 0);
        if (m.get("gun") instanceof Map<?, ?> g0) {
            Map<String, Object> g = (Map<String, Object>) g0;
            if (g.get("vehicles") instanceof List<?> l) for (Object o : l) r.gunVehicles.add(String.valueOf(o));
            r.gunInterval = num(g, "interval", 4.0);
            r.gunRange = num(g, "range", 220.0);
            r.gunDamage = num(g, "damage", 320.0);
            r.gunRadius = num(g, "radius", 7.0);
        }
        return r;
    }

    private static List<List<String>> lists(Object o) {
        List<List<String>> out = new ArrayList<>();
        if (!(o instanceof List<?> l)) return out;
        for (Object row : l) {
            List<String> r = new ArrayList<>();
            if (row instanceof List<?> rl) for (Object x : rl) r.add(String.valueOf(x));
            out.add(r);
        }
        return out;
    }

    private static <T> List<T> rowAt(List<List<T>> rows, int stars) {
        if (rows.isEmpty() || stars <= 0) return List.of();
        return rows.get(Math.min(stars, rows.size() - 1));
    }

    /** Weapons a unit carries at this many stars (empty = use the side's flat list). */
    public List<String> weaponsFor(int stars) { return rowAt(weaponsByStars, stars); }

    /** Vehicle models sent at this many stars (empty = the side's default car). */
    public List<String> vehiclesFor(int stars) { return rowAt(vehiclesByStars, stars); }

    public int snipersFor(int stars) { return at(snipersByStars, stars); }

    public int helisFor(int stars) { return at(helisByStars, stars); }

    /** Do cars on a call ram at this many stars? */
    public boolean rams(int stars) { return ramAt > 0 && stars >= ramAt; }


    /** Does this vehicle model fire a main gun? */
    public boolean hasGun(String model) { return gunVehicles.contains(model); }

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
