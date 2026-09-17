package com.openworld.character;

import godot.core.Color;

/**
 * Faction identifier constants and hostility logic.
 *
 * Faction membership is stored as a plain String so new factions can be added
 * without modifying this file — just use a new string in the inspector or
 * spawner code (e.g. "partyA", "civilian").
 *
 * Extensibility (PLAN.md Part D / D3): hostility is owned entirely by the {@link FactionManager}
 * AutoLoad. {@code areHostile()} is a thin delegate to it — the actual rule (relationship table +
 * inherent NEUTRAL/same/different defaults) lives in one place there, so there is no duplicated
 * "legacy" logic to keep in sync. {@code FactionManager} is an AutoLoad, so its registry is always
 * present before any character runs; with no registry (e.g. an engine-free unit test) two factions
 * are simply treated as non-hostile.
 */
public final class Faction {

    public static final String PLAYER  = "player";
    public static final String ENEMY   = "enemy";
    public static final String NEUTRAL = "neutral";

    // The open-world cast (PLAN.md F2, OpenWorldFactions.tres). Plain strings like the three above:
    // a faction needs no constant to work, these exist so spawners and presets spell them one way.
    public static final String POLICE   = "police";
    public static final String GANG_A   = "gang_a";
    public static final String GANG_B   = "gang_b";
    public static final String CIVILIAN = "civilian";

    /** Set by FactionManager._ready(); null only when no faction system is loaded (engine-free tests). */
    private static FactionManager registry;

    private Faction() {}

    /** Wire the live relationship authority. Called from {@code FactionManager._ready()}. */
    public static void setRegistry(FactionManager manager) { registry = manager; }

    /** Drop the back-reference on shutdown (only if it is still the one that registered). */
    public static void clearRegistry(FactionManager manager) {
        if (registry == manager) registry = null;
    }

    /**
     * Returns true when two factions should treat each other as targets. Delegates wholly to the
     * {@link FactionManager} authority; with no registry loaded, nothing is hostile.
     */
    public static boolean areHostile(String factionA, String factionB) {
        return registry != null && registry.areHostile(factionA, factionB);
    }

    /**
     * Canonical display colour for a faction string.
     * Used by kill-feed entries and character nameplates to tint name labels.
     */
    public static Color color(String faction) {
        if (PLAYER.equals(faction))  return new Color(0.45f, 0.78f, 1.00f, 1f); // cyan-blue
        if (ENEMY.equals(faction))   return new Color(1.00f, 0.35f, 0.35f, 1f); // red
        if (POLICE.equals(faction))  return new Color(1.00f, 0.82f, 0.30f, 1f); // amber
        if (GANG_A.equals(faction))  return new Color(0.90f, 0.40f, 0.90f, 1f); // magenta
        if (GANG_B.equals(faction))  return new Color(0.45f, 0.90f, 0.45f, 1f); // green
        return                              new Color(0.85f, 0.85f, 0.85f, 1f); // neutral grey
    }
}
