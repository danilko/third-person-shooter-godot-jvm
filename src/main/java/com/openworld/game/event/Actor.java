package com.openworld.game.event;

/**
 * Who did something, or whom it was done to, in a {@link GameplayEvent} -- plain data, so the rules that read events
 * are engine-free and unit-tested. {@code id} is the body's characterId; {@code storyId} is that same id when the body is
 * a STORY character (its id is authored and stable, {@code AICharacter.storyCharacter}) and "" for everyone else:
 * the key the {@code WorldLedger} remembers a dead one by.
 */
public record Actor(String id, String faction, Kind kind, String name, String storyId) {

    public enum Kind { NONE, PLAYER, AI }

    /** Nobody: the world itself, or an unknown attacker. */
    public static final Actor NONE = new Actor("", "", Kind.NONE, "", "");

    public Actor {
        id = id == null ? "" : id;
        faction = faction == null ? "" : faction;
        kind = kind == null ? Kind.NONE : kind;
        name = name == null ? "" : name;
        storyId = storyId == null ? "" : storyId;
    }

    public static Actor player(String id, String faction) { return new Actor(id, faction, Kind.PLAYER, "", ""); }

    public static Actor ai(String id, String faction) { return new Actor(id, faction, Kind.AI, "", ""); }

    public boolean isPlayer() { return kind == Kind.PLAYER; }

    public boolean isNone() { return kind == Kind.NONE; }
}
