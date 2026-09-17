package com.openworld.character;

import java.util.function.Function;

/**
 * THE hostility rule, engine-free (PLAN.md F2). {@link FactionManager#areHostile} and
 * {@link FactionTable#relationship} both answer through here, so the rule has one owner and a unit
 * test ({@code FactionRulesTest}) without a running engine.
 *
 * <p>A table is read through a key lookup ({@code "a>b"} → relationship or null), in this order:
 * <ol>
 *   <li>{@code "neutral"} is never hostile;</li>
 *   <li>an EXACT pair, either direction;</li>
 *   <li>a WILDCARD row, {@code "a>*"} or {@code "*>a"}: "a toward every OTHER faction". It is what
 *       lets a preset say "civilians are neutral to everyone" without listing every faction and
 *       going stale the day one is added. It never applies to a faction and itself (a gang
 *       declared hostile to everyone is not hostile to its own members). When both sides carry
 *       one and they disagree, the LESS hostile wins, so a civilian stays out of a fight that a
 *       hostile-to-all faction would otherwise pull it into;</li>
 *   <li>otherwise the inherent default: same faction allied, different factions hostile.</li>
 * </ol>
 */
public final class FactionRules {

    public static final String FRIENDLY = "FRIENDLY";
    public static final String NEUTRAL  = "NEUTRAL";
    public static final String HOSTILE  = "HOSTILE";
    public static final String DESPISE  = "DESPISE";

    /** The "every other faction" side of a wildcard row. */
    public static final String ANY = "*";

    /** Faction name that is never hostile (mirrors {@code Faction.NEUTRAL}). */
    public static final String NEUTRAL_FACTION = "neutral";

    private FactionRules() {}

    /** Composite key for an ordered faction pair. */
    public static String key(String a, String b) {
        return a + ">" + b;
    }

    /** The configured relationship between a and b (exact pair, then wildcard), or null if the table is silent. */
    public static String resolve(String a, String b, Function<String, String> lookup) {
        if (a == null || b == null || lookup == null) return null;
        String exact = firstNonNull(lookup.apply(key(a, b)), lookup.apply(key(b, a)));
        if (exact != null) return exact;
        if (a.equals(b)) return null;
        String wa = wildcard(a, lookup);
        String wb = wildcard(b, lookup);
        if (wa != null && wb != null) return rank(wa) <= rank(wb) ? wa : wb;
        return wa != null ? wa : wb;
    }

    /** True when two factions should treat each other as targets. */
    public static boolean areHostile(String a, String b, Function<String, String> lookup) {
        if (a == null || b == null) return false;
        if (NEUTRAL_FACTION.equals(a) || NEUTRAL_FACTION.equals(b)) return false;
        String rel = resolve(a, b, lookup);
        if (rel != null) return HOSTILE.equals(rel) || DESPISE.equals(rel);
        return !a.equals(b);
    }

    private static String wildcard(String faction, Function<String, String> lookup) {
        return firstNonNull(lookup.apply(key(faction, ANY)), lookup.apply(key(ANY, faction)));
    }

    /** How hostile a relationship is; an unknown string ranks as NEUTRAL. */
    static int rank(String rel) {
        if (FRIENDLY.equals(rel)) return 0;
        if (HOSTILE.equals(rel))  return 2;
        if (DESPISE.equals(rel))  return 3;
        return 1;
    }

    private static String firstNonNull(String x, String y) {
        return x != null ? x : y;
    }
}
