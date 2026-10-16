package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Player;

/**
 * PER-TARGET HOSTILITY (PLAN.md P1e step 4; the reviewer's correction: "WantedSystem.applyHostility flips the WHOLE
 * police faction hostile when any player is at shoot_at: an innocent co-op partner gets shot"). Faction relations are
 * per faction, so the flips stay ({@link FactionFlips}: they wake the FSM's targeting at all), and this narrows them:
 * a faction that is hostile to players ONLY BECAUSE of a flip may target a player only when THAT player's own standing
 * calls for it -- police: their stars reach shoot_at, or they are lethal-wanted; a gang: their standing with it is at
 * attack_at, or they are its escaping captive. Hostility from the faction table itself (a mission's own table, the
 * inherent rule) is never narrowed.
 *
 * <p>Asked by {@code AICharacter}'s target scan for every player candidate. {@link #enabled} off = the old rule (the
 * control).
 */
public final class Hostility {
    private Hostility() {}

    /** Off = the control: one player's standing turns the faction on every player. */
    public static boolean enabled = true;

    /** May an AI of {@code faction} target {@code target}? Only players are ever narrowed. */
    public static boolean mayTarget(String faction, Character target) {
        if (!enabled || !(target instanceof Player p) || p.getCharacterInfo() == null || faction == null) return true;
        String id = p.getCharacterInfo().characterId;
        WantedSystem ws = WantedSystem.get();
        if (Faction.POLICE.equals(faction)) return ws == null || !ws.flippedHostile(faction) || ws.policeShoot(id);
        GangSystem gs = GangSystem.get();
        if (gs != null && gs.isGang(faction)) return !gs.flippedHostile(faction) || gs.attacksPlayer(faction, id);
        return true;
    }
}
