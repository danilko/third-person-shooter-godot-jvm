package com.openworld.character;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class FactionRulesTest {

    private static Map<String, String> table(String... rows) {
        Map<String, String> m = new HashMap<>();
        for (int i = 0; i < rows.length; i += 2) m.put(rows[i], rows[i + 1]);
        return m;
    }

    @Test
    void emptyTableUsesInherentDefault() {
        Map<String, String> t = table();
        assertTrue(FactionRules.areHostile("player", "enemy", t::get));
        assertFalse(FactionRules.areHostile("police", "police", t::get));
        assertFalse(FactionRules.areHostile("neutral", "enemy", t::get));
        assertFalse(FactionRules.areHostile(null, "enemy", t::get));
    }

    @Test
    void exactPairWinsEitherDirection() {
        Map<String, String> t = table("police>player", "NEUTRAL");
        assertFalse(FactionRules.areHostile("police", "player", t::get));
        assertFalse(FactionRules.areHostile("player", "police", t::get));
        assertTrue(FactionRules.areHostile("police", "gang_a", t::get));
    }

    @Test
    void neutralFactionOverridesTable() {
        Map<String, String> t = table("neutral>player", "HOSTILE");
        assertFalse(FactionRules.areHostile("neutral", "player", t::get));
    }

    @Test
    void wildcardCoversEveryOtherFaction() {
        Map<String, String> t = table("civilian>*", "NEUTRAL");
        assertFalse(FactionRules.areHostile("civilian", "player", t::get));
        assertFalse(FactionRules.areHostile("gang_b", "civilian", t::get));
        assertFalse(FactionRules.areHostile("civilian", "a_faction_added_later", t::get));
        assertTrue(FactionRules.areHostile("gang_b", "player", t::get));
        // Reverse spelling of the row means the same.
        Map<String, String> r = table("*>civilian", "NEUTRAL");
        assertFalse(FactionRules.areHostile("player", "civilian", r::get));
    }

    @Test
    void exactPairBeatsWildcard() {
        Map<String, String> t = table("civilian>*", "NEUTRAL", "civilian>gang_a", "DESPISE");
        assertTrue(FactionRules.areHostile("gang_a", "civilian", t::get));
        assertFalse(FactionRules.areHostile("police", "civilian", t::get));
    }

    @Test
    void wildcardNeverTurnsAFactionOnItself() {
        Map<String, String> t = table("gang_a>*", "HOSTILE");
        assertFalse(FactionRules.areHostile("gang_a", "gang_a", t::get));
        assertTrue(FactionRules.areHostile("gang_a", "police", t::get));
    }

    @Test
    void conflictingWildcardsTakeTheLessHostile() {
        Map<String, String> t = table("civilian>*", "NEUTRAL", "maniac>*", "DESPISE");
        assertEquals("NEUTRAL", FactionRules.resolve("maniac", "civilian", t::get));
        assertFalse(FactionRules.areHostile("maniac", "civilian", t::get));
        assertTrue(FactionRules.areHostile("maniac", "player", t::get));
    }
}
