package com.openworld.game;

import com.openworld.util.MiniJson;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The wanted level's rules (PLAN.md W5) -- engine-free, so they are unit-tested ({@code WantedRulesTest}).
 *
 * <p>A crime adds HEAT; heat decides the STARS (0-6) through {@code starsAt}, and a crime may also set a floor of
 * stars at once (killing a policeman is three stars whatever the heat). After a CALM period with no new crime
 * ({@code calmSeconds + calmPerStar * stars}) the heat drains at {@code decayPerSecond}; the floor drains with it.
 * The table is DATA ({@code game/crimes.json}): a new crime is one row there plus one report call at its seam.
 */
public final class WantedRules {

    public static final int MAX_STARS = 6;

    /** One row of the crime table. */
    public record Crime(String id, double heat, int minStars, boolean witness, boolean lethal) {}

    public final double[] starsAt;
    public final double calmSeconds, calmPerStar, decayPerSecond, witnessRadius;
    public final Map<String, Crime> crimes;
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
    @SuppressWarnings("unchecked")
    public static WantedRules parse(String json) {
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(json);
        List<Object> at = (List<Object>) doc.get("stars_at");
        double[] starsAt = new double[at.size()];
        for (int i = 0; i < starsAt.length; i++) starsAt[i] = num(at.get(i));
        Map<String, Crime> crimes = new HashMap<>();
        Map<String, Object> rows = (Map<String, Object>) doc.get("crimes");
        for (Map.Entry<String, Object> e : rows.entrySet()) {
            Map<String, Object> r = (Map<String, Object>) e.getValue();
            crimes.put(e.getKey(), new Crime(e.getKey(), num(r.get("heat")),
                    (int) num(r.getOrDefault("min_stars", 0)), Boolean.TRUE.equals(r.get("witness")),
                    Boolean.TRUE.equals(r.get("lethal"))));
        }
        WantedRules w = new WantedRules(starsAt, num(doc.getOrDefault("calm_seconds", 12.0)),
                num(doc.getOrDefault("calm_per_star", 6.0)), num(doc.getOrDefault("decay_per_second", 18.0)),
                num(doc.getOrDefault("witness_radius", 45.0)), crimes);
        if (doc.get("police_weapons") instanceof Map<?, ?> pw) {
            w.normalWeapons = strings(pw.get("normal"));
            w.lethalWeapons = strings(pw.get("lethal"));
        }
        return w;
    }

    private static List<String> strings(Object o) {
        List<String> out = new java.util.ArrayList<>();
        if (o instanceof List<?> l) for (Object x : l) out.add(String.valueOf(x));
        return out;
    }

    private static double num(Object o) {
        return o instanceof Number n ? n.doubleValue() : 0.0;
    }

    /** Stars for a heat (0..6). */
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
        /** A lethal crime is on the record: police shoot on sight, no arrest -- until the heat is gone. */
        public boolean lethal;

        public void clear() {
            heat = 0.0;
            lastCrimeAt = Double.NEGATIVE_INFINITY;
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

    /** Advance the state to {@code now} after {@code dt} seconds: heat drains once the calm period is over. */
    public void tick(State s, double now, double dt) {
        if (s.heat <= 0.0) return;
        double calm = calmSeconds + calmPerStar * starsFor(s.heat);
        if (now - s.lastCrimeAt < calm) return;
        s.heat = Math.max(0.0, s.heat - decayPerSecond * dt);
        if (s.heat <= 0.0) s.lethal = false;
    }
}
