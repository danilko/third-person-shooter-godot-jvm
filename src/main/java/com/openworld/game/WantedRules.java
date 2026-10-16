package com.openworld.game;

import com.openworld.util.DataReader;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The wanted level's rules (PLAN.md W5) -- engine-free, so they are unit-tested ({@code WantedRulesTest}).
 *
 * <p>A crime adds HEAT; heat decides the STARS (0-5, WantedRules.MAX_STARS -- police and gangs alike) through {@code starsAt}, and a crime may also set a floor of
 * stars at once (killing a policeman is three stars whatever the heat). After a CALM period with no new crime
 * ({@code calmSeconds + calmPerStar * stars}) the heat drains at {@code decayPerSecond}; the floor drains with it.
 * The table is DATA ({@code game/crimes.json}): a new crime is one row there plus one report call at its seam.
 */
public final class WantedRules {

    public static final int MAX_STARS = 5;

    /** One row of the crime table. */
    public record Crime(String id, double heat, int minStars, boolean witness, boolean lethal) {}

    public final double[] starsAt;
    public final double calmSeconds, calmPerStar, decayPerSecond, witnessRadius;
    public final Map<String, Crime> crimes;
    /** A WITNESSED crime by a player who is not wanted yet reaches the police only after the witness has called it
     *  in -- this long -- and only if the witness is still alive then (PLAN.md P1e step 4); 0 = at once. */
    public double callInSeconds = 0.0;
    /** What responding police carry: ordinary, and once the player is lethal-wanted (heavy). */
    public List<String> normalWeapons = List.of(), lethalWeapons = List.of();

    public WantedRules(double[] starsAt, double calmSeconds, double calmPerStar, double decayPerSecond,
                       double witnessRadius, Map<String, Crime> crimes) {
        this.starsAt = starsAt;
        this.calmSeconds = calmSeconds;
        this.calmPerStar = calmPerStar;
        this.decayPerSecond = decayPerSecond;
        this.witnessRadius = witnessRadius;
        this.crimes = crimes;
    }

    /** Parse {@code crimes.json}'s text. */
    public static WantedRules parse(String json) { return read(DataReader.of(json)); }

    /** Read the wanted rules out of crimes.json (its {@code dispatch} and {@code fees} blocks are others'). */
    public static WantedRules read(DataReader doc) {
        double[] starsAt = doc.nums("stars_at");
        if (starsAt == null) starsAt = new double[0];
        Map<String, Crime> crimes = new HashMap<>();
        for (Map.Entry<String, DataReader> e : doc.rows("crimes").entrySet()) {
            DataReader r = e.getValue();
            crimes.put(e.getKey(), new Crime(e.getKey(), r.reqNum("heat", 0.0), r.integer("min_stars", 0),
                    r.bool("witness", false), r.bool("lethal", false)));
        }
        WantedRules w = new WantedRules(starsAt, doc.num("calm_seconds", 12.0), doc.num("calm_per_star", 6.0),
                doc.num("decay_per_second", 18.0), doc.num("witness_radius", 45.0), crimes);
        w.callInSeconds = doc.num("call_in_seconds", 0.0);
        DataReader pw = doc.child("police_weapons");
        if (pw != null) {
            w.normalWeapons = pw.strings("normal");
            w.lethalWeapons = pw.strings("lethal");
        }
        return w;
    }

    /** Stars for a heat (0..MAX_STARS). */
    public int starsFor(double heat) {
        int s = 0;
        for (double t : starsAt) if (heat >= t) s++;
        return Math.min(MAX_STARS, s);
    }

    /** The heat at which a star count begins (so a floor of stars can be expressed as heat). */
    public double heatFor(int stars) {
        if (stars <= 0) return 0.0;
        return starsAt[Math.min(stars, starsAt.length) - 1];
    }

    /** One player's wanted state. Mutable, owned by the authoritative peer. */
    public static final class State {
        public double heat;
        public double lastCrimeAt = Double.NEGATIVE_INFINITY;
        /** Police last had the player in sight (game.EnforcementDispatch): the calm clock runs from the later. */
        public double lastSeenAt = Double.NEGATIVE_INFINITY;
        /** A lethal crime is on the record: police shoot on sight, no arrest -- until the heat is gone. */
        public boolean lethal;

        public void clear() {
            heat = 0.0;
            lastCrimeAt = Double.NEGATIVE_INFINITY;
            lastSeenAt = Double.NEGATIVE_INFINITY;
            lethal = false;
        }
    }

    /**
     * Apply a crime at time {@code now}. Returns false (nothing happens) for an unknown crime, or for one that needs
     * a witness when there was none.
     */
    public boolean report(State s, String crimeId, boolean witnessed, double now) {
        Crime c = crimes.get(crimeId);
        if (c == null || (c.witness() && !witnessed)) return false;
        s.heat = Math.max(s.heat + c.heat(), heatFor(c.minStars()));
        s.lastCrimeAt = now;
        if (c.lethal()) s.lethal = true;
        return true;
    }

    /** Police can see the player: the heat does not start draining until they have lost them for the calm period. */
    public void seen(State s, double now) { if (s.heat > 0.0) s.lastSeenAt = now; }

    /** Set the stars outright (a probe, a mission script): the heat at the start of that star. */
    public void setStars(State s, int stars, boolean lethal, double now) {
        s.heat = heatFor(Math.max(0, Math.min(MAX_STARS, stars)));
        s.lastCrimeAt = now;
        s.lethal = lethal && s.heat > 0.0;
    }

    /** Advance the state to {@code now} after {@code dt} seconds: heat drains once the calm period is over. */
    public void tick(State s, double now, double dt) {
        if (s.heat <= 0.0) return;
        double calm = calmSeconds + calmPerStar * starsFor(s.heat);
        if (now - Math.max(s.lastCrimeAt, s.lastSeenAt) < calm) return;
        s.heat = Math.max(0.0, s.heat - decayPerSecond * dt);
        if (s.heat <= 0.0) s.lethal = false;
    }
}
