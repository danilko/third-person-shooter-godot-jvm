package com.openworld.game;

import com.openworld.util.DataReader;

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
    public static RecoveryRules parse(String crimesJson, String gangsJson) {
        return read(crimesJson == null ? null : DataReader.of(crimesJson).child("fees"),
                gangsJson == null ? null : DataReader.of(gangsJson).child("abduction"));
    }

    /** From crimes.json's {@code fees} block and gangs.json's {@code abduction} block; either may be null. */
    public static RecoveryRules read(DataReader fees, DataReader abduction) {
        DataReader f = fees != null ? fees : DataReader.of("{}");
        DataReader ab = abduction != null ? abduction : DataReader.of("{}");
        return new RecoveryRules(f.integer("hospital", 5000), f.integer("police_per_star", 10000),
                ab.integer("ransom_per_star", 100000), ab.integer("guards", 3), ab.num("escape_start", 15.0),
                ab.num("escape_free", 90.0), ab.strings("guard_weapons"));
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

    // A bill is taken WHOLE now and may leave the balance negative -- what the player owes (PLAN.md 1.4, CR4):
    // game.profile.Economy.bill. The old "never more than there is" charge is gone with the cash field.
}
