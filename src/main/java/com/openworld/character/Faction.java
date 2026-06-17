package com.openworld.character;

import godot.core.Color;

/**
 * Faction identifier constants and hostility logic.
 *
 * Faction membership is stored as a plain String so new factions can be added
 * without modifying this file — just use a new string in the inspector or
 * spawner code (e.g. "partyA", "civilian").
 *
 * Future extensibility: replace the body of areHostile() with a FactionRegistry
 * lookup that reads an override table (e.g. "partyA" and "partyB" declared
 * allied). All call-sites stay unchanged.
 */
public final class Faction {

    public static final String PLAYER  = "player";
    public static final String ENEMY   = "enemy";
    public static final String NEUTRAL = "neutral";

    private Faction() {}

    /**
     * Returns true when two factions should treat each other as targets.
     * Same faction string or either being NEUTRAL => not hostile.
     */
    public static boolean areHostile(String factionA, String factionB) {
        if (factionA == null || factionB == null)                    return false;
        if (NEUTRAL.equals(factionA) || NEUTRAL.equals(factionB))   return false;
        return !factionA.equals(factionB);
    }

    /**
     * Canonical display colour for a faction string.
     * Used by kill-feed entries and character nameplates to tint name labels.
     */
    public static Color color(String faction) {
        if (PLAYER.equals(faction))  return new Color(0.45f, 0.78f, 1.00f, 1f); // cyan-blue
        if (ENEMY.equals(faction))   return new Color(1.00f, 0.35f, 0.35f, 1f); // red
        return                              new Color(0.85f, 0.85f, 0.85f, 1f); // neutral grey
    }
}
