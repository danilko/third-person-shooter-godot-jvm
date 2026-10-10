package com.openworld.game.activity;

import com.openworld.game.event.GameplayEvent;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import java.util.function.Predicate;

/**
 * One stage of an {@link Activity}: what happens on entering it, and the TRIGGERS that are live while it is the
 * current one. A trigger's reaction usually ends the stage -- {@code a.go(..)}, {@code a.complete(..)},
 * {@code a.fail(..)} -- and the first such request in a step wins.
 *
 * <ul>
 *   <li>{@link #on} -- a {@link GameplayEvent} of a type, matching a predicate (a kill, a zone entered, a theft);</li>
 *   <li>{@link #after} -- a time since the stage was entered, once;</li>
 *   <li>{@link #when} -- a condition of the world, asked every step (LEVEL-triggered: it reacts every step it
 *       holds, so its reaction should leave the stage);</li>
 *   <li>{@link #tick} -- anything else, every step.</li>
 * </ul>
 */
public final class Stage {

    record EventTrigger<E extends GameplayEvent>(Class<E> type, Predicate<? super E> match,
                                                 BiConsumer<ActivityInstance, ? super E> react) {
        @SuppressWarnings("unchecked")
        boolean offer(ActivityInstance a, GameplayEvent e) {
            if (!type.isInstance(e) || !match.test((E) e)) return false;
            react.accept(a, (E) e);
            return true;
        }
    }

    record Timer(double seconds, Consumer<ActivityInstance> react) {}

    record Condition(String name, Predicate<ActivityInstance> holds, Consumer<ActivityInstance> react) {}

    public final String id;
    boolean checkpoint;
    String speaker = "", line = "", marker = "";
    Consumer<ActivityInstance> enter, exit;
    BiConsumer<ActivityInstance, Double> tick;
    final List<EventTrigger<?>> events = new ArrayList<>();
    final List<Timer> timers = new ArrayList<>();
    final List<Condition> conditions = new ArrayList<>();

    Stage(String id) { this.id = id; }

    /**
     * A failed run may be RETRIED from here, and a save taken later resumes here (CR5). A checkpoint restarts the
     * STAGE: its {@link #enter} must set up everything the stage needs (the earlier stages' did not run).
     */
    public Stage checkpoint() { checkpoint = true; return this; }

    /** The objective, told by a speaker on entering the stage (a short subtitle, then gone -- the minimal HUD). */
    public Stage objective(String speaker, String line) {
        this.speaker = speaker == null ? "" : speaker;
        this.line = line == null ? "" : line;
        return this;
    }

    /** What the world marks while this stage runs: a cast member's id or a marker id ("" = nothing). */
    public Stage marker(String what) { marker = what == null ? "" : what; return this; }

    public Stage enter(Consumer<ActivityInstance> c) { enter = c; return this; }

    public Stage exit(Consumer<ActivityInstance> c) { exit = c; return this; }

    public <E extends GameplayEvent> Stage on(Class<E> type, Predicate<? super E> match,
                                              BiConsumer<ActivityInstance, ? super E> react) {
        events.add(new EventTrigger<>(type, match, react));
        return this;
    }

    public Stage after(double seconds, Consumer<ActivityInstance> react) {
        timers.add(new Timer(seconds, react));
        return this;
    }

    public Stage when(String name, Predicate<ActivityInstance> holds, Consumer<ActivityInstance> react) {
        conditions.add(new Condition(name, holds, react));
        return this;
    }

    public Stage tick(BiConsumer<ActivityInstance, Double> c) { tick = c; return this; }

    public boolean isCheckpoint() { return checkpoint; }
}
