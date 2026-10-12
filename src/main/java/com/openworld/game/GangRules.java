package com.openworld.game;

import com.openworld.util.DataReader;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Gang heat's rules (PLAN.md W5, user 2026-10-03) -- engine-free, unit-tested ({@code GangRulesTest}), over the DATA
 * file {@code game/gangs.json}. Independent of the police ({@link WantedRules}): a gang remembers, so its heat is not
 * cleared by a hospitalisation or an arrest; below {@code payAt} stars it drains after a calm period, at or above it
 * only a "donation" ({@link #fee}) clears it.
 */
public final class GangRules {

    public record Gang(String id, String name, String nameJa, int feePerStar) {}

    public final double[] starsAt;
    public final int attackAt, chaseAt, payAt;
    public final double calmSeconds, decayPerSecond;
    public final Map<String, Double> crimes;
    public final Map<String, Gang> gangs;

    private GangRules(double[] starsAt, int attackAt, int chaseAt, int payAt, double calmSeconds, double decayPerSecond,
                      Map<String, Double> crimes, Map<String, Gang> gangs) {
        this.starsAt = starsAt;
        this.attackAt = attackAt;
        this.chaseAt = chaseAt;
        this.payAt = payAt;
        this.calmSeconds = calmSeconds;
        this.decayPerSecond = decayPerSecond;
        this.crimes = crimes;
        this.gangs = gangs;
    }

    public static GangRules parse(String json) { return read(DataReader.of(json)); }

    /** Read the gang rules out of gangs.json (its {@code hunters}, {@code hangout}, {@code abduction} and each
     *  gang's {@code bodies} are others'). */
    public static GangRules read(DataReader doc) {
        double[] starsAt = doc.nums("stars_at");
        if (starsAt == null) starsAt = new double[0];
        Map<String, Double> crimes = new LinkedHashMap<>();
        for (Map.Entry<String, DataReader> e : doc.rows("crimes").entrySet())
            crimes.put(e.getKey(), e.getValue().reqNum("heat", 0.0));
        Map<String, Gang> gangs = new LinkedHashMap<>();
        for (Map.Entry<String, DataReader> e : doc.rows("gangs").entrySet()) {
            DataReader g = e.getValue();
            gangs.put(e.getKey(), new Gang(e.getKey(), g.str("name", e.getKey()), g.str("name_ja", ""),
                    g.integer("fee_per_star", 50000)));
        }
        return new GangRules(starsAt, doc.integer("attack_at", 1), doc.integer("chase_at", 3),
                doc.integer("pay_at", 2), doc.num("calm_seconds", 30.0), doc.num("decay_per_second", 4.0), crimes, gangs);
    }

    public int starsFor(double heat) {
        int s = 0;
        for (double t : starsAt) if (heat >= t) s++;
        return Math.min(WantedRules.MAX_STARS, s);
    }

    /** One player's standing with one gang. */
    public static final class State {
        public double heat;
        public double lastCrimeAt = Double.NEGATIVE_INFINITY;
    }

    /** Apply a gang crime at {@code now}; false for an unknown crime. */
    public boolean report(State s, String crimeId, double now) {
        Double h = crimes.get(crimeId);
        if (h == null) return false;
        s.heat += h;
        s.lastCrimeAt = now;
        return true;
    }

    /** Drain below {@code payAt} stars once calm; at or above it the heat holds until paid. */
    public void tick(State s, double now, double dt) {
        if (s.heat <= 0.0 || starsFor(s.heat) >= payAt || now - s.lastCrimeAt < calmSeconds) return;
        s.heat = Math.max(0.0, s.heat - decayPerSecond * dt);
    }

    /** The donation that clears a gang's heat (dollars; 0 when there is nothing to pay). */
    public int fee(String gang, State s) {
        Gang g = gangs.get(gang);
        int stars = starsFor(s.heat);
        return g == null || stars == 0 ? 0 : g.feePerStar() * stars;
    }

    public boolean attacks(State s) { return starsFor(s.heat) >= attackAt; }

    public boolean chases(State s) { return starsFor(s.heat) >= chaseAt; }
}
