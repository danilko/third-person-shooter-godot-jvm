package com.openworld.game;

import com.openworld.character.Faction;
import com.openworld.character.FactionManager;
import com.openworld.character.FactionTable;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * Makes a set of factions HOSTILE to players (both directions) and gives each back its previous relation when it
 * leaves the set -- the one owner of "turn on the player for a while", shared by the police ({@link WantedSystem})
 * and the gangs ({@link GangSystem}). Call {@link #apply} periodically: a mission or region layer rebuilding the
 * faction table discards runtime flips, and this puts them back. Faction relations are per faction, so in co-op one
 * player's standing turns a faction on the player faction as a whole (accepted).
 */
final class FactionFlips {

    private final Map<String, String> before = new HashMap<>();

    void apply(FactionManager fm, Set<String> want) {
        if (fm == null) return;
        for (String f : want) {
            if (!before.containsKey(f)) before.put(f, fm.relationship(f, Faction.PLAYER));
            if (!fm.areHostile(f, Faction.PLAYER)) {
                fm.setRelationship(f, Faction.PLAYER, FactionTable.HOSTILE);
                fm.setRelationship(Faction.PLAYER, f, FactionTable.HOSTILE);
            }
        }
        for (String f : new ArrayList<>(before.keySet())) {
            if (want.contains(f)) continue;
            String prev = before.remove(f);
            // no entry before = the inherent default (two different factions: HOSTILE); leave it NEUTRAL instead
            String back = prev == null || prev.isEmpty() ? FactionTable.NEUTRAL : prev;
            fm.setRelationship(f, Faction.PLAYER, back);
            fm.setRelationship(Faction.PLAYER, f, back);
        }
    }
}
