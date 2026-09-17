package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;
import godot.core.Dictionary;

/**
 * Editable faction relationship matrix (PLAN.md Part D / D3) — a {@code Resource} so it can be
 * authored and tweaked in the Godot inspector and shipped as a {@code .tres} preset
 * (DefaultFactions.tres).
 *
 * <p>Storage is a flat {@code String → String} dictionary keyed by {@code "factionA>factionB"}
 * (a {@code "factionA>*"} row applies to every other faction — see {@link FactionRules}); values are one of {@link #FRIENDLY}/{@link #NEUTRAL}/{@link #HOSTILE}/
 * {@link #DESPISE}. A flat string dictionary (rather than a nested one) is both the inspector-friendly
 * shape and the one the godot-jvm registration scanner handles — same shape the codebase
 * already uses elsewhere (e.g. {@code MeshConfig.boneHitMultipliers}). Pairs are written in both
 * directions on {@link #setRelationship} and {@link #relationship} also checks the reverse, so a
 * table authored one-way still resolves.
 *
 * <p>This is data only; {@code FactionManager} owns the live table and the hostility decision, so a
 * faction pair absent from the table falls back to the legacy {@code Faction} rule there — making the
 * whole feature a drop-in over the previous hardcoded behaviour.
 */
@Script(className = "FactionTable")
public class FactionTable extends Resource {

    public static final String FRIENDLY = FactionRules.FRIENDLY;
    public static final String NEUTRAL  = FactionRules.NEUTRAL;
    public static final String HOSTILE  = FactionRules.HOSTILE;
    public static final String DESPISE  = FactionRules.DESPISE;

    /** "factionA>factionB" → relationship string. Editable in the inspector. */
    @Export
    public Dictionary<String, String> relationships = new Dictionary<>(String.class, String.class);

    private static String key(String a, String b) {
        return FactionRules.key(a, b);
    }

    /**
     * One stored row by its {@code "a>b"} key, or null. Asks {@code containsKey} first: a godot-jvm
     * {@code Dictionary.get} on a missing key is not guaranteed to be null (an untyped one returns
     * {@code kotlin.Unit}, which would read as a relationship named "kotlin.Unit").
     */
    public String row(String key) {
        if (key == null || !relationships.containsKey(key)) return null;
        Object v = relationships.get(key);
        return v != null ? v.toString() : null;
    }

    /**
     * Configured relationship between a and b — exact pair either direction, then a wildcard row
     * ({@code "civilian>*"}); null if the table is silent. The rule is {@link FactionRules#resolve}.
     */
    public String relationship(String a, String b) {
        return FactionRules.resolve(a, b, this::row);
    }

    /**
     * Set a (symmetric) relationship between two factions at runtime — mission betrayals, etc.
     *
     * <p>{@code set}, NOT {@code put}: in godot-jvm 1.0.0-rc1 {@code Dictionary.put} first calls
     * {@code get(key, null)} to return the previous value, and that pushes the {@code null} default
     * through the typed STRING converter, which throws {@code IllegalArgumentException: Failed
     * requirement}. Every runtime flip threw — including the late-join faction baseline, which a
     * client dropped as a malformed packet (found by tools/net/run_net_shot_test.sh).
     */
    public void setRelationship(String a, String b, String rel) {
        if (a == null || b == null || rel == null) return;
        relationships.set(key(a, b), rel);
        relationships.set(key(b, a), rel);
    }

    /** All stored directed relationships as {factionA, factionB, relationship} triples (for the net baseline). */
    public java.util.List<String[]> entries() {
        java.util.List<String[]> out = new java.util.ArrayList<>();
        for (java.util.Map.Entry<String, String> e : relationships.entrySet()) {
            String k = e.getKey();
            int sep = k.indexOf('>');
            if (sep <= 0 || sep >= k.length() - 1) continue;   // skip malformed keys
            out.add(new String[]{ k.substring(0, sep), k.substring(sep + 1), e.getValue() });
        }
        return out;
    }
}
