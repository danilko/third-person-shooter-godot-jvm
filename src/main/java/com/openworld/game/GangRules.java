package com.openworld.game;

import com.openworld.util.MiniJson;

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

    @SuppressWarnings("unchecked")
    public static GangRules parse(String json) {
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(json);
        List<Object> at = (List<Object>) doc.get("stars_at");
        double[] starsAt = new double[at.size()];
        for (int i = 0; i < starsAt.length; i++) starsAt[i] = num(at.get(i));
        Map<String, Double> crimes = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : ((Map<String, Object>) doc.get("crimes")).entrySet())
            crimes.put(e.getKey(), num(((Map<String, Object>) e.getValue()).get("heat")));
        Map<String, Gang> gangs = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : ((Map<String, Object>) doc.get("gangs")).entrySet()) {
            Map<String, Object> g = (Map<String, Object>) e.getValue();
            gangs.put(e.getKey(), new Gang(e.getKey(), String.valueOf(g.getOrDefault("name", e.getKey())),
                    String.valueOf(g.getOrDefault("name_ja", "")), (int) num(g.getOrDefault("fee_per_star", 50000))));
        }
        return new GangRules(starsAt, (int) num(doc.getOrDefault("attack_at", 1)), (int) num(doc.getOrDefault("chase_at", 3)),
                (int) num(doc.getOrDefault("pay_at", 2)), num(doc.getOrDefault("calm_seconds", 30.0)),
                num(doc.getOrDefault("decay_per_second", 4.0)), crimes, gangs);
    }

    private static double num(Object o) {
        return o instanceof Number n ? n.doubleValue() : 0.0;
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

    /** The donation that clears a gang's heat (yen; 0 when there is nothing to pay). */
    public int fee(String gang, State s) {
        Gang g = gangs.get(gang);
        int stars = starsFor(s.heat);
        return g == null || stars == 0 ? 0 : g.feePerStar() * stars;
    }

    public boolean attacks(State s) { return starsFor(s.heat) >= attackAt; }

    public boolean chases(State s) { return starsFor(s.heat) >= chaseAt; }
}
