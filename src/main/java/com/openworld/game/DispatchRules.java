package com.openworld.game;

import com.openworld.util.DataReader;

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
    public final double footMin, footMax, carMin, carMax, arriveDist, despawnFar,
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
                  double carMax, double arriveDist, double despawnFar,
                  double seenReach, double spawnInterval, List<String> weapons) {
        this.shootAt = shootAt; this.footByStars = foot; this.carsByStars = cars; this.carCrew = crew;
        this.footMin = footMin; this.footMax = footMax; this.carMin = carMin; this.carMax = carMax;
        this.arriveDist = arriveDist;
        this.despawnFar = despawnFar; this.seenReach = seenReach; this.spawnInterval = spawnInterval;
        this.weapons = weapons;
    }

    /** Parse one block ({@code dispatch} or {@code hunters}) out of a table's text; null when the block is absent. */
    public static DispatchRules parse(String json, String block) { return read(DataReader.of(json).child(block)); }

    /** Read one block ({@code dispatch} / {@code hunters}); null for null. */
    public static DispatchRules read(DataReader m) {
        if (m == null) return null;
        DispatchRules r = new DispatchRules(m.integer("shoot_at", 0), intsOr(m, "foot_by_stars"),
                intsOr(m, "cars_by_stars"), m.integer("car_crew", 2), m.num("foot_min", 45),
                m.num("foot_max", 75), m.num("car_min", 140), m.num("car_max", 280), m.num("arrive_dist", 35),
                m.num("despawn_far", 180),
                m.num("seen_reach", 60), m.num("spawn_interval", 1.5), m.strings("weapons"));
        r.weaponsByStars = m.stringLists("weapons_by_stars");
        r.vehiclesByStars = m.stringLists("vehicles_by_stars");
        if (m.has("snipers_by_stars")) r.snipersByStars = intsOr(m, "snipers_by_stars");
        if (m.has("helis_by_stars")) r.helisByStars = intsOr(m, "helis_by_stars");
        r.ramAt = m.integer("ram_at", 0);
        if (m.has("tokens_by_stars")) r.tokensByStars = intsOr(m, "tokens_by_stars");
        if (m.has("regroup_seconds_by_stars")) r.regroupByStars = intsOr(m, "regroup_seconds_by_stars");
        r.supplyReach = m.num("supply_reach", 60.0);
        r.mergeRadius = m.num("merge_radius", 0.0);
        r.bodies = readBodies(m.items("bodies"));
        DataReader g = m.child("gun");
        if (g != null) {
            r.gunVehicles.addAll(g.strings("vehicles"));
            r.gunInterval = g.num("interval", 4.0);
            r.gunRange = g.num("range", 220.0);
            r.gunDamage = g.num("damage", 320.0);
            r.gunRadius = g.num("radius", 7.0);
        }
        return r;
    }

    private static int[] intsOr(DataReader m, String key) {
        int[] v = m.ints(key);
        return v == null || v.length == 0 ? new int[] {0} : v;
    }

    // ── BODIES (PLAN.md 1g c): who a unit IS -- which body and which uniform ──

    /** One row of a force's body table: a body (CharacterVisuals_<Body>), its uniform (character/outfits.json), a
     *  weight, the stars it is sent at (inclusive; max 0 = no upper bound), and weapons it carries besides its
     *  star row's ({@code extra_weapons}: special forces' knife, PLAN.md 1i). */
    public record BodyPick(String body, String outfit, double weight, int minStars, int maxStars,
                           List<String> extraWeapons) {
        public BodyPick(String body, String outfit, double weight, int minStars, int maxStars) {
            this(body, outfit, weight, minStars, maxStars, List.of());
        }
        boolean sentAt(int stars) { return stars >= minStars && (maxStars <= 0 || stars <= maxStars); }
    }

    /** The police's (or the shared hunters') body table; a gang's own is {@link #parseGangBodies}. Empty = the
     *  AICharacter scene's own body, as before. */
    public List<BodyPick> bodies = new ArrayList<>();

    static List<BodyPick> readBodies(List<DataReader> rows) {
        List<BodyPick> out = new ArrayList<>();
        for (DataReader r : rows) {
            String body = r.reqStr("body", null);
            String outfit = r.str("outfit", "");
            double weight = r.num("weight", 1.0);
            int min = r.integer("min_stars", 0), max = r.integer("max_stars", 0);
            List<String> extra = r.strings("extra_weapons");
            if (body == null) continue;
            out.add(new BodyPick(body, outfit, weight, min, max, List.copyOf(extra)));
        }
        return out;
    }

    /** Each gang's body table ({@code gangs.<id>.bodies} in gangs.json). */
    public static Map<String, List<BodyPick>> parseGangBodies(String json) { return readGangBodies(DataReader.of(json)); }

    public static Map<String, List<BodyPick>> readGangBodies(DataReader doc) {
        Map<String, List<BodyPick>> out = new java.util.HashMap<>();
        for (var e : doc.rows("gangs").entrySet()) out.put(e.getKey(), readBodies(e.getValue().items("bodies")));
        return out;
    }

    /** The row sent at {@code stars} for a roll in [0, 1): weighted among the rows in range; null if none is. */
    public static BodyPick pickBody(List<BodyPick> rows, int stars, double roll) {
        if (rows == null || rows.isEmpty()) return null;
        double total = 0;
        for (BodyPick b : rows) if (b.sentAt(stars)) total += Math.max(0, b.weight());
        if (total <= 0) return null;
        double t = Math.max(0, Math.min(roll, 0.999999)) * total;
        BodyPick last = null;
        for (BodyPick b : rows) {
            if (!b.sentAt(stars) || b.weight() <= 0) continue;
            last = b;
            if ((t -= b.weight()) < 0) return b;
        }
        return last;
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

    /** Attack tokens (PLAN.md 1g b2): how many of a side's units may attack one player at once; 0 = no limit. */
    public int[] tokensByStars = {0};
    /** The regroup lull (1g b3): seconds no new unit is sent after half a squad ran dry; 0 = no lull. */
    public int[] regroupByStars = {0};
    /** Players of one side within this many metres of each other are ONE incident: what is already on any of them
     *  counts toward each one's call (0 = every player is their own incident, the old rule). */
    public double mergeRadius = 0.0;
    /** How far a unit out of ammo walks back to a vehicle's spare ammunition (else it leaves the fight). */
    public double supplyReach = 60.0;

    public int tokensFor(int stars) { return at(tokensByStars, stars); }

    public int regroupFor(int stars) { return at(regroupByStars, stars); }

    /** The regroup lull is due (PLAN.md P1e step 1, WAVE ATTRITION): half the wave ({@code wave} = lost since the last
     *  lull + still fighting) is down or dry -- at least two lost, so one early casualty does not stall a response. */
    public static boolean lullDue(int lost, int wave) { return lost >= 2 && lost * 2 >= wave; }

    /**
     * Who holds an attack token this tick. {@code held[i]} = seconds unit i has held one (negative = none),
     * {@code rest[i]} = seconds it must still wait after giving one back, {@code dist[i]} = its distance to the player.
     * A holder keeps its token until {@code holdMax}; free tokens go to the nearest units that are not resting, so
     * the attackers rotate. {@code n <= 0} = everyone attacks.
     */
    public static boolean[] tokenHolders(double[] dist, double[] held, double[] rest, int n, double holdMax) {
        boolean[] out = new boolean[dist.length];
        if (n <= 0) { java.util.Arrays.fill(out, true); return out; }
        int given = 0;
        for (int i = 0; i < dist.length && given < n; i++)
            if (held[i] >= 0 && held[i] < holdMax) { out[i] = true; given++; }
        while (given < n) {
            int best = -1;
            for (int i = 0; i < dist.length; i++)
                if (!out[i] && rest[i] <= 0 && !(held[i] >= holdMax) && (best < 0 || dist[i] < dist[best])) best = i;
            if (best < 0) break;
            out[best] = true;
            given++;
        }
        return out;
    }

    public int helisFor(int stars) { return at(helisByStars, stars); }

    /** Do cars on a call ram at this many stars? */
    public boolean rams(int stars) { return ramAt > 0 && stars >= ramAt; }


    /** Does this vehicle model fire a main gun? */
    public boolean hasGun(String model) { return gunVehicles.contains(model); }

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

    /** How many new units to spawn this tick: what is missing, at most {@code perTick}. */
    public static int toSpawn(int want, int have, int perTick) {
        return Math.max(0, Math.min(perTick, want - have));
    }
}
