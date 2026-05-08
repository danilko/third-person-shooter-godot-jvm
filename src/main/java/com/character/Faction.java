package com.character;

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
}
