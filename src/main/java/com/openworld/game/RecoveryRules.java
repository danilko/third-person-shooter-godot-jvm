package com.openworld.game;

import com.openworld.util.MiniJson;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Where a player who goes down WAKES, and what it costs (user, 2026-10-06; game.RespawnSystem). Engine-free, so it is
 * unit-tested ({@code RecoveryRulesTest}).
 *
 * <ul>
 *   <li><b>拉致 ABDUCTED</b> when the player has ANY standing against a gang: taken to one of that gang's places,
 *   held by guards; pay the ransom ({@code ransom_per_star} x that gang's stars, the highest cost) or escape.</li>
 *   <li><b>逮捕 ARRESTED</b> when the police want the player -- a death included: jail, and (hospital + police per
 *   star) x the stars.</li>
 *   <li><b>入院 HOSPITALIZED</b> otherwise: the nearest hospital, the hospital fee.</li>
 * </ul>
 * A gang outranks the police: they got to the player first (the user's order). An arrest the police MAKE is always an
 * arrest.
 */
public final class RecoveryRules {

    public enum Outcome { HOSPITALIZED, ARRESTED, ABDUCTED }

    public final int hospital, policePerStar, ransomPerStar, guards;
    public final double escapeStart, escapeFree;
    public final List<String> guardWeapons;

    public RecoveryRules(int hospital, int policePerStar, int ransomPerStar, int guards, double escapeStart,
                         double escapeFree, List<String> guardWeapons) {
        this.hospital = hospital; this.policePerStar = policePerStar; this.ransomPerStar = ransomPerStar;
        this.guards = guards; this.escapeStart = escapeStart; this.escapeFree = escapeFree;
        this.guardWeapons = guardWeapons;
    }

    /** From crimes.json's text ({@code fees}) and gangs.json's ({@code abduction}); either may be null. */
    @SuppressWarnings("unchecked")
    public static RecoveryRules parse(String crimesJson, String gangsJson) {
        Map<String, Object> fees = crimesJson == null ? Map.of()
                : ((Map<String, Object>) MiniJson.parse(crimesJson)).get("fees") instanceof Map<?, ?> m
                        ? (Map<String, Object>) m : Map.of();
        Map<String, Object> ab = gangsJson == null ? Map.of()
                : ((Map<String, Object>) MiniJson.parse(gangsJson)).get("abduction") instanceof Map<?, ?> m2
                        ? (Map<String, Object>) m2 : Map.of();
        List<String> w = new ArrayList<>();
        if (ab.get("guard_weapons") instanceof List<?> l) for (Object o : l) w.add(String.valueOf(o));
        return new RecoveryRules((int) num(fees, "hospital", 5000), (int) num(fees, "police_per_star", 10000),
                (int) num(ab, "ransom_per_star", 100000), (int) num(ab, "guards", 3), num(ab, "escape_start", 15.0),
                num(ab, "escape_free", 90.0), w);
    }

    private static double num(Map<String, Object> m, String k, double dflt) {
        return m.get(k) instanceof Number n ? n.doubleValue() : dflt;
    }

    /** Where a player who went DOWN (died) wakes. */
    public static Outcome onDown(int gangStars, int policeStars) {
        if (gangStars > 0) return Outcome.ABDUCTED;
        if (policeStars > 0) return Outcome.ARRESTED;
        return Outcome.HOSPITALIZED;
    }

    /** The bill for waking up: the hospital fee, or (hospital + police per star) x stars. An abduction's ransom is
     *  not taken here -- it is the price of leaving ({@link #ransom}). */
    public int fee(Outcome o, int policeStars) {
        return switch (o) {
            case HOSPITALIZED -> hospital;
            case ARRESTED -> (hospital + policePerStar) * Math.max(1, policeStars);
            case ABDUCTED -> 0;
        };
    }

    /** The ransom a gang asks at these stars. */
    public int ransom(int gangStars) { return ransomPerStar * Math.max(1, gangStars); }

    /** What is taken from {@code cash} for a bill: all of it if it is not enough, never below 0. */
    public static int charge(int cash, int bill) { return Math.max(0, Math.min(cash, bill)); }
}
