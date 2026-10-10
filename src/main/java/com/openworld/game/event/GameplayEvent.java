package com.openworld.game.event;

/**
 * Something a character DID that the game's systems may answer (PLAN.md 2.0 / AR3): the one typed action ->
 * consequence stream. A seam (Health, a firearm, a shop clerk, the economy) publishes what happened and knows
 * nothing of who cares; the wanted level, the gangs, the ledger and -- from 2.1 -- activities, careers and the
 * surprise-event director subscribe ({@link GameplayEvents}). Adding a consequence is a subscriber, never another
 * call inside {@code Health.applyDamage}.
 *
 * <p>Records of plain data: engine-free, so a rule that maps an event to a consequence is unit-tested, and an
 * activity's stage graph can be driven by scripted events (CR6's test kit). A new kind of event is a new record in
 * this file's {@code permits} list.
 */
public sealed interface GameplayEvent permits GameplayEvent.Damaged, GameplayEvent.Killed, GameplayEvent.WeaponFired,
        GameplayEvent.Threatened, GameplayEvent.Theft, GameplayEvent.ZoneEntered, GameplayEvent.BalanceChanged,
        GameplayEvent.FlagChanged, GameplayEvent.ActivityOutcome {

    /** Who did it ({@link Actor#NONE} when nobody did: a balance change, a flag). */
    Actor actor();

    /** Where ({@link Spot#NOWHERE} when it has no place). */
    Spot at();

    /** Whom it was done to ({@link Actor#NONE} for an event with nobody on the receiving end). */
    default Actor target() { return Actor.NONE; }

    /** {@code target} was hurt by {@code actor} and lived. */
    record Damaged(Actor actor, Actor target, Spot at, double amount, boolean headshot, String weapon) implements GameplayEvent {}

    /** {@code target} was killed by {@code actor}. */
    record Killed(Actor actor, Actor target, Spot at, boolean headshot, String weapon) implements GameplayEvent {}

    /** {@code actor} fired a firearm (every shot). */
    record WeaponFired(Actor actor, Spot at, String weapon) implements GameplayEvent {}

    /** {@code actor} pointed a weapon at {@code target} to make them comply (a shop clerk). {@code gang}: the gang
     *  whose protection the place is under, "" none. */
    record Threatened(Actor actor, Actor target, Spot at, String gang) implements GameplayEvent {}

    /** {@code actor} took {@code amount} yen that was not theirs ({@code what}: "till"). {@code gang}: the gang whose
     *  place it was, "" none. */
    record Theft(Actor actor, Spot at, String what, long amount, String gang) implements GameplayEvent {}

    /** {@code actor} walked into a trigger zone ({@code zoneId}: the ZoneTrigger's beat id). */
    record ZoneEntered(Actor actor, Spot at, String zoneId) implements GameplayEvent {}

    /** Money moved through {@code Economy.transfer}: {@code from} / {@code to} are PLAYER ids (PersistentPlayerId),
     *  "" = the world; {@code reason} is the {@code Economy.Reason} name. */
    record BalanceChanged(String from, String to, long amount, String reason) implements GameplayEvent {
        @Override public Actor actor() { return Actor.NONE; }
        @Override public Spot at() { return Spot.NOWHERE; }
    }

    /** A WORLD flag changed in the ledger ({@code value} "" = cleared). */
    record FlagChanged(String flag, String value) implements GameplayEvent {
        @Override public Actor actor() { return Actor.NONE; }
        @Override public Spot at() { return Spot.NOWHERE; }
    }

    /** An activity run ended (PLAN.md 2.1): {@code actor} is its OWNER, {@code outcome} COMPLETED / FAILED /
     *  ABORTED, {@code variant} the outcome variant of a completed one, {@code mode} STORY / REPLAY. */
    record ActivityOutcome(Actor actor, String activityId, String instanceId, String outcome, String variant,
                           String mode) implements GameplayEvent {
        @Override public Spot at() { return Spot.NOWHERE; }
    }
}
