package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;
import godot.core.Dictionary;

/**
 * Editable faction relationship matrix (PLAN.md Part D / D3) — a {@code Resource} so it can be
 * authored and tweaked in the Godot inspector and shipped as a {@code .tres} preset
 * (DefaultFactions.tres).
 *
 * <p>Storage is a flat {@code String → String} dictionary keyed by {@code "factionA>factionB"}
 * (see {@link #key}); values are one of {@link #FRIENDLY}/{@link #NEUTRAL}/{@link #HOSTILE}/
 * {@link #DESPISE}. A flat string dictionary (rather than a nested one) is both the inspector-friendly
 * shape and the one the godot-kotlin-jvm registration scanner handles — same shape the codebase
 * already uses elsewhere (e.g. {@code MeshConfig.boneHitMultipliers}). Pairs are written in both
 * directions on {@link #setRelationship} and {@link #relationship} also checks the reverse, so a
 * table authored one-way still resolves.
 *
 * <p>This is data only; {@code FactionManager} owns the live table and the hostility decision, so a
 * faction pair absent from the table falls back to the legacy {@code Faction} rule there — making the
 * whole feature a drop-in over the previous hardcoded behaviour.
 */
@RegisterClass(className = "FactionTable")
public class FactionTable extends Resource {

    public static final String FRIENDLY = "FRIENDLY";
    public static final String NEUTRAL  = "NEUTRAL";
    public static final String HOSTILE  = "HOSTILE";
    public static final String DESPISE  = "DESPISE";

    /** "factionA>factionB" → relationship string. Editable in the inspector. */
    @Export @RegisterProperty
    public Dictionary<String, String> relationships = new Dictionary<>(String.class, String.class);

    /** Composite key for an ordered faction pair. */
    private static String key(String a, String b) {
        return a + ">" + b;
    }

    /** Configured relationship for the ordered pair (a, b), checking the reverse too; null if unset. */
    public String relationship(String a, String b) {
        if (a == null || b == null) return null;
        Object direct = relationships.get(key(a, b));
        if (direct != null) return direct.toString();
        Object reverse = relationships.get(key(b, a));
        return reverse != null ? reverse.toString() : null;
    }

    /** Set a (symmetric) relationship between two factions at runtime — mission betrayals, etc. */
    public void setRelationship(String a, String b, String rel) {
        if (a == null || b == null || rel == null) return;
        relationships.put(key(a, b), rel);
        relationships.put(key(b, a), rel);
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
