package com.openworld.game;

import com.openworld.util.DataReader;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * FINITE FORCES, HELD PER STATION (PLAN.md P1e step 3; user 2026-10-15: "simplify that entire pool for now -- at
 * each station"). Every police station, koban, gang place and military reserve in the places record holds its OWN
 * count of bodies, by the data in {@code game/forces.json}; a unit is DRAWN from the nearest station of its tier that
 * still has one, a unit that leaves the fight alive goes BACK to its station, a dead one is gone until that station
 * regenerates (one body every {@code regen_seconds}). There is no island-wide total.
 *
 * <p>A side's TIERS (police: police -> special forces -> military; a gang: one) form its ladder: at N stars the side
 * draws from the highest tier sent at N; an empty tier escalates to the next one up; when the top is empty too
 * nothing is sent and the side has a "no units available" breather ({@code empty_lull_seconds}) while it regenerates.
 * A side with NO stations in this world (DebugWorld has no places record) is unlimited, as before.
 *
 * <p>Engine-free ({@code ForcePoolsTest}); the dispatch owns one and feeds it the places. Session-only on the host:
 * pools are never saved (PLAN.md P1e "design rules").
 */
public final class ForcePools {

    /** One tier of a side: who it is and what each kind of place holds of it. */
    public record Tier(String id, int minStars, String outfit, Map<String, Stock> places) {}

    /** What one kind of place holds of a tier: the full count and the seconds to regenerate one body. */
    public record Stock(int pool, double regenSeconds) {}

    /** A side's ladder (tiers in escalation order), its breather when the top is empty, and whether its stations are
     *  only the places that carry its id as their {@code gang} (a gang's). */
    public record Side(String id, List<Tier> tiers, double emptyLullSeconds, boolean ownPlacesOnly) {}

    /** One station's holding of one tier. */
    public static final class Station {
        public final String side, tier, place, kind;
        public final double x, z;
        public final int max;
        final double regenSeconds;
        double stock;
        int drawn, lost, returned;

        Station(String side, String tier, String place, String kind, double x, double z, Stock s) {
            this.side = side; this.tier = tier; this.place = place; this.kind = kind; this.x = x; this.z = z;
            this.max = Math.max(0, s.pool()); this.regenSeconds = s.regenSeconds(); this.stock = max;
        }

        /** Whole bodies on hand. */
        public int available() { return (int) Math.floor(stock + 1e-9); }
        public int drawn() { return drawn; }
        public int lost() { return lost; }
    }

    /** A draw: the station it came from, and the tier (its outfit dresses the body; null = the stars' own). */
    public record Draw(Station station, Tier tier) {}

    private final Map<String, Side> sides;
    private final List<Station> stations = new ArrayList<>();

    public ForcePools(Map<String, Side> sides) { this.sides = sides; }

    /** The sides the data defines. */
    public Map<String, Side> sides() { return sides; }

    public List<Station> stations() { return stations; }

    /**
     * Give the pools this world's places: every place whose KIND a tier of a side lists becomes that tier's station
     * (a gang tier's kind {@code "*"} = any place of that gang, matched by the place's {@code gang}).
     */
    public void bind(List<PlaceRef> places) {
        stations.clear();
        for (Side s : sides.values())
            for (Tier t : s.tiers())
                for (PlaceRef p : places) {
                    if (s.ownPlacesOnly() && !s.id().equals(p.gang())) continue;   // a gang draws from its own places
                    Stock st = t.places().get(p.kind());
                    if (st == null && s.ownPlacesOnly()) st = t.places().get("*");
                    if (st != null) stations.add(new Station(s.id(), t.id(), p.name(), p.kind(), p.x(), p.z(), st));
                }
    }

    /** A place as the pools need it (from world.Places). */
    public record PlaceRef(String name, String kind, String gang, double x, double z) {}

    /** Does this side have stations in this world? Without any it is unlimited. */
    public boolean limited(String side) {
        for (Station st : stations) if (st.side.equals(side)) return true;
        return false;
    }

    /** The tier a side draws from first at these stars: the last in its ladder sent at that many (null = none). */
    int primaryTier(Side s, int stars) {
        int k = -1;
        for (int i = 0; i < s.tiers().size(); i++) if (s.tiers().get(i).minStars() <= stars) k = i;
        return k;
    }

    /**
     * Draw one body for {@code side} at {@code stars} near (x, z): the nearest station of the primary tier with a body
     * on hand, else of the next tier up, and so on. Null = the ladder is empty from the primary tier up (the caller
     * starts the side's breather). A side with no stations at all returns an UNLIMITED draw (station null).
     */
    public Draw draw(String side, int stars, double x, double z) {
        Side s = sides.get(side);
        if (s == null || !limited(side)) return new Draw(null, null);
        int first = primaryTier(s, stars);
        if (first < 0) first = 0;
        for (int i = first; i < s.tiers().size(); i++) {
            Tier t = s.tiers().get(i);
            Station best = null;
            double bd = Double.MAX_VALUE;
            for (Station st : stations) {
                if (!st.side.equals(side) || !st.tier.equals(t.id()) || st.available() < 1) continue;
                double d = Math.hypot(st.x - x, st.z - z);
                if (d < bd) { bd = d; best = st; }
            }
            if (best != null) {
                best.stock -= 1;
                best.drawn++;
                return new Draw(best, t);
            }
        }
        return null;
    }

    /** Can {@code n} bodies be drawn for this side at these stars right now (without drawing them)? */
    public boolean canDraw(String side, int stars, int n) {
        Side s = sides.get(side);
        if (s == null || !limited(side)) return true;
        int first = Math.max(0, primaryTier(s, stars)), have = 0;
        for (int i = first; i < s.tiers().size(); i++)
            for (Station st : stations)
                if (st.side.equals(side) && st.tier.equals(s.tiers().get(i).id())) have += st.available();
        return have >= n;
    }

    /** A unit drawn from {@code st} left the fight ALIVE (stood down, freed far away): it is back on hand. */
    public void giveBack(Station st) {
        if (st == null) return;
        st.stock = Math.min(st.max, st.stock + 1);
        st.returned++;
    }

    /** A unit drawn from {@code st} is down: gone until the station regenerates. */
    public void lose(Station st) {
        if (st != null) st.lost++;
    }

    /** Every station of a side spent at once (a probe's "all gone" case; regeneration starts from 0). */
    public void empty(String side) {
        for (Station st : stations) if (st.side.equals(side)) { st.drawn += st.available(); st.stock = 0; }
    }

    /** Regenerate: every station below its count gains one body per regen_seconds. */
    public void tick(double dt) {
        for (Station st : stations)
            if (st.stock < st.max && st.regenSeconds > 0) st.stock = Math.min(st.max, st.stock + dt / st.regenSeconds);
    }

    /** The breather when a side's ladder is empty (s). */
    public double emptyLull(String side) {
        Side s = sides.get(side);
        return s == null ? 0 : s.emptyLullSeconds();
    }

    /** Per side and tier: "on hand / full, drawn, lost" -- the debug console's {@code pools}. */
    public String report() {
        Map<String, int[]> sum = new LinkedHashMap<>();
        for (Station st : stations) {
            int[] a = sum.computeIfAbsent(st.side + " " + st.tier, k -> new int[5]);
            a[0] += st.available(); a[1] += st.max; a[2] += st.drawn; a[3] += st.lost; a[4]++;
        }
        StringBuilder b = new StringBuilder();
        for (var e : sum.entrySet()) {
            int[] a = e.getValue();
            b.append(b.length() > 0 ? "\n" : "").append(String.format("%-24s %3d/%-3d on hand  drawn %d  lost %d  (%d stations)",
                    e.getKey(), a[0], a[1], a[2], a[3], a[4]));
        }
        return b.length() == 0 ? "no stations in this world: every force is unlimited" : b.toString();
    }

    // ── data: game/forces.json ──

    /** Read the {@code forces} block. */
    public static Map<String, Side> read(DataReader d) {
        Map<String, Side> out = new LinkedHashMap<>();
        if (d == null) return out;
        for (Map.Entry<String, DataReader> e : d.rows("forces").entrySet()) {
            DataReader f = e.getValue();
            List<Tier> tiers = new ArrayList<>();
            for (DataReader t : f.items("tiers")) {
                Map<String, Stock> places = new LinkedHashMap<>();
                for (Map.Entry<String, DataReader> pe : t.rows("places").entrySet())
                    places.put(pe.getKey(), new Stock(pe.getValue().integer("pool", 0), pe.getValue().num("regen_seconds", 60.0)));
                tiers.add(new Tier(t.str("id", e.getKey()), t.integer("min_stars", 0), t.str("outfit", ""), places));
            }
            out.put(e.getKey(), new Side(e.getKey(), tiers, f.num("empty_lull_seconds", 75.0), f.bool("own_places_only", false)));
        }
        return out;
    }
}
