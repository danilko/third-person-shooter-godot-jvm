package com.openworld.game.event;

import com.openworld.character.Faction;

import java.util.function.Predicate;

/**
 * Which crime an event IS (PLAN.md 2.0 / AR3) -- the pure half of the wanted level's and the gangs' subscribers, so
 * it is unit-tested ({@code CrimeMapTest}). The ids are rows of {@code crimes.json} / {@code gangs.json}; what a
 * crime costs stays in those tables ({@code WantedRules}, {@code GangRules}).
 */
public final class CrimeMap {
    private CrimeMap() {}

    /** A gang crime: against which gang, which row. */
    public record GangCrime(String gang, String crimeId) {}

    /** The police crime a hit on {@code target} is ("" none): police and civilians only, never a player. */
    public static String forHit(Actor target, boolean killed) {
        if (target == null || target.isPlayer()) return "";
        String f = target.faction();
        if (Faction.POLICE.equals(f)) return killed ? "kill_police" : "assault_police";
        if (Faction.NEUTRAL.equals(f) || Faction.CIVILIAN.equals(f)) return killed ? "murder" : "assault";
        return "";
    }

    /** The police crime {@code e} is when a PLAYER did it; "" when it is none (or nobody's, or an AI's). */
    public static String police(GameplayEvent e) {
        if (e == null || !e.actor().isPlayer()) return "";
        if (e instanceof GameplayEvent.Damaged d) return forHit(d.target(), false);
        if (e instanceof GameplayEvent.Killed k) return forHit(k.target(), true);
        if (e instanceof GameplayEvent.WeaponFired) return "gunfire";
        if (e instanceof GameplayEvent.Threatened) return "threaten_clerk";
        if (e instanceof GameplayEvent.Theft) return "rob_store";
        if (e instanceof GameplayEvent.Trespassed) return "trespass";
        return "";
    }

    /** The gang crime {@code e} is when a PLAYER did it, or null. {@code isGang}: is this faction a gang. */
    public static GangCrime gang(GameplayEvent e, Predicate<String> isGang) {
        if (e == null || !e.actor().isPlayer()) return null;
        if (e instanceof GameplayEvent.Damaged d) return member(d.target(), "hit_member", isGang);
        if (e instanceof GameplayEvent.Killed k) return member(k.target(), "kill_member", isGang);
        if (e instanceof GameplayEvent.Threatened t && isGang.test(t.gang())) return new GangCrime(t.gang(), "threaten_clerk");
        if (e instanceof GameplayEvent.Theft t && isGang.test(t.gang())) return new GangCrime(t.gang(), "rob_gray");
        return null;
    }

    private static GangCrime member(Actor target, String crime, Predicate<String> isGang) {
        if (target == null || target.isPlayer() || !isGang.test(target.faction())) return null;
        return new GangCrime(target.faction(), crime);
    }
}
