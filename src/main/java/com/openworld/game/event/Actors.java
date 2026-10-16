package com.openworld.game.event;

import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import godot.core.Vector3;

/** The engine side of {@link Actor} / {@link Spot}: what a body, an id or a position is in an event. */
public final class Actors {
    private Actors() {}

    public static Actor of(Character c) {
        if (c == null) return Actor.NONE;
        CharacterInfo i = c.getCharacterInfo();
        if (i == null) return new Actor("", "", c instanceof Player ? Actor.Kind.PLAYER : Actor.Kind.AI, "", "");
        // a STORY character's id is authored and stable (AICharacter.storyCharacter); everyone else's is a UUID
        String story = c instanceof com.openworld.character.AICharacter a && a.storyCharacter ? i.characterId : "";
        return new Actor(i.characterId, i.faction, c instanceof Player ? Actor.Kind.PLAYER : Actor.Kind.AI,
                i.displayName, story);
    }

    /** An attacker known only by id (damage carries the id, not the body): a live player's body if it is one, else an
     *  AI of unknown faction; {@link Actor#NONE} for no id (the world: a fall, a fire). */
    public static Actor byId(String characterId, String name) { return byId(characterId, name, ""); }

    /** {@link #byId} with the faction the hit itself carries (PLAN.md P1e step 6: an AI attacker had an EMPTY faction,
     *  so a gang-on-gang attack could not be read). */
    public static Actor byId(String characterId, String name, String faction) {
        if (characterId == null || characterId.isEmpty()) return Actor.NONE;
        for (Player p : PlayerRegistry.getPlayers())
            if (p.getCharacterInfo() != null && characterId.equals(p.getCharacterInfo().characterId)) return of(p);
        return new Actor(characterId, faction == null ? "" : faction, Actor.Kind.AI, name, "");
    }

    public static Spot at(Vector3 p) { return p == null ? Spot.NOWHERE : new Spot(p.getX(), p.getY(), p.getZ()); }

    public static Vector3 vec(Spot s) { return new Vector3(s.x(), s.y(), s.z()); }
}
