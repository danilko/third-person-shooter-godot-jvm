package com.openworld.game.activity;

import com.openworld.game.event.GameplayEvent;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiPredicate;
import java.util.function.Predicate;

/**
 * An {@link Activity}'s rules, live in EVERY stage (PLAN.md 2.1): what fails it, which acts are lawful inside it, and
 * what an act costs a participant's career. The event rules are heard in {@code GameplayEvents.Phase.ACTIVITY},
 * before the wanted level and the gangs, and answer through the event's {@code Ruling}.
 */
public final class RuleSet {

    record FailWhen(String reason, Predicate<ActivityInstance> holds) {}

    record FailOn(String reason, BiPredicate<ActivityInstance, GameplayEvent> match) {}

    enum Verdict { SANCTION, VETO }

    record Judge(Verdict verdict, BiPredicate<ActivityInstance, GameplayEvent> match) {}

    record Penalty(String counter, long n, BiPredicate<ActivityInstance, GameplayEvent> match) {}

    String allDownReason = "";
    final List<FailWhen> failWhen = new ArrayList<>();
    final List<FailOn> failOn = new ArrayList<>();
    final List<Judge> judges = new ArrayList<>();
    final List<Penalty> penalties = new ArrayList<>();

    /** It fails when every participant is down at once. */
    public RuleSet failWhenAllDown(String reason) { allDownReason = reason; return this; }

    /** It fails while this holds (asked every step). */
    public RuleSet failWhen(String reason, Predicate<ActivityInstance> holds) {
        failWhen.add(new FailWhen(reason, holds));
        return this;
    }

    /** It fails on this event -- whoever did it: an outsider robbing the shop a participant is clerking. */
    public RuleSet failOn(String reason, BiPredicate<ActivityInstance, GameplayEvent> match) {
        failOn.add(new FailOn(reason, match));
        return this;
    }

    /** A matching act is LAWFUL here: the wanted level and the gangs do not count it (an officer shooting during
     *  an arrest). Write the predicate over participants: {@code (a, e) -> a.isParticipant(e.actor().id())}. */
    public RuleSet sanction(BiPredicate<ActivityInstance, GameplayEvent> match) {
        judges.add(new Judge(Verdict.SANCTION, match));
        return this;
    }

    /** A matching act is annulled: no later phase hears it. */
    public RuleSet veto(BiPredicate<ActivityInstance, GameplayEvent> match) {
        judges.add(new Judge(Verdict.VETO, match));
        return this;
    }

    /**
     * A matching act BY A PARTICIPANT adds {@code n} to a counter of their effective career ("strikes"). Where it
     * lands is the temporary career's routing: the scratch record (TEMP, discarded at the end) or the real one.
     */
    public RuleSet penalty(String counter, long n, BiPredicate<ActivityInstance, GameplayEvent> match) {
        penalties.add(new Penalty(counter, n, match));
        return this;
    }
}
