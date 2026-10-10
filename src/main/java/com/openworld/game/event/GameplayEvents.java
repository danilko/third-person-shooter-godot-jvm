package com.openworld.game.event;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;

/**
 * The bus {@link GameplayEvent}s go through (PLAN.md 2.0 / AR3). AUTHORITY ONLY: consequences are decided where
 * damage is -- single player or the host -- so {@link #publish} on a co-op client drops the event (a client's own
 * shot runs the fire path too). {@code EventBus} stays what it was: untyped Godot signals for the UI.
 *
 * <p><b>Order.</b> Subscribers are heard by {@link Phase}, whatever order they subscribed in:
 * ACTIVITY (an activity's rules: they may {@link Ruling#sanction} the act -- an officer shooting during an arrest is
 * no crime -- or {@link Ruling#veto} it) -> CAREER -> ECONOMY -> WANTED -> GANG -> LEDGER -> DIRECTOR (surprise
 * events) -> OBSERVER (probes, logs). Within a phase, in subscription order. A veto ends the event there: no later
 * phase hears it. A sanction is advice the later phases follow (wanted / gang do not count a sanctioned act).
 *
 * <p><b>Re-entrancy.</b> An event published by a subscriber is queued and delivered after the current one has been
 * heard by everyone, so every subscriber sees events in one order.
 *
 * <p>Engine-free and static (one stream per process); {@link #reset} empties it (engine teardown, each unit test).
 */
public final class GameplayEvents {
    private GameplayEvents() {}

    public enum Phase { ACTIVITY, CAREER, ECONOMY, WANTED, GANG, LEDGER, DIRECTOR, OBSERVER }

    /** What the earlier phases decided about one event. */
    public static final class Ruling {
        private String sanctionedBy = "", vetoedBy = "", sandboxedBy = "";

        /** The act is lawful in its context: consequence systems do not count it. {@code by}: who says so. */
        public void sanction(String by) { if (sanctionedBy.isEmpty()) sanctionedBy = by == null || by.isEmpty() ? "?" : by; }

        /** Nobody after this phase hears the event. */
        public void veto(String by) { if (vetoedBy.isEmpty()) vetoedBy = by == null || by.isEmpty() ? "?" : by; }

        /** It happened inside a sandbox (a mission REPLAY, CR7): nothing persistent -- the ledger, a profile's story
         *  -- records it. Heat earned in it is ordinary and stays. */
        public void sandbox(String by) { if (sandboxedBy.isEmpty()) sandboxedBy = by == null || by.isEmpty() ? "?" : by; }

        public boolean sandboxed() { return !sandboxedBy.isEmpty(); }
        public boolean sanctioned() { return !sanctionedBy.isEmpty(); }
        public boolean vetoed() { return !vetoedBy.isEmpty(); }
        public String sanctionedBy() { return sanctionedBy; }
        public String vetoedBy() { return vetoedBy; }
    }

    public interface Subscriber { void on(GameplayEvent event, Ruling ruling); }

    private static final Map<Phase, List<Subscriber>> SUBS = new EnumMap<>(Phase.class);
    private static final ArrayDeque<GameplayEvent> QUEUE = new ArrayDeque<>();
    private static BooleanSupplier authority = () -> true;
    private static BiConsumer<Subscriber, RuntimeException> onError =
            (s, e) -> System.err.println("GameplayEvents: a subscriber threw " + e);
    private static boolean dispatching;
    private static long published, dropped, vetoed;

    /** Who decides consequences on this machine (the engine installs "not a co-op client"). */
    public static synchronized void setAuthority(BooleanSupplier a) { authority = a == null ? () -> true : a; }

    public static synchronized void setErrorLog(BiConsumer<Subscriber, RuntimeException> l) { if (l != null) onError = l; }

    public static synchronized void subscribe(Phase phase, Subscriber s) {
        if (phase == null || s == null) return;
        List<Subscriber> l = SUBS.computeIfAbsent(phase, k -> new ArrayList<>());
        if (!l.contains(s)) l.add(s);
    }

    public static synchronized void unsubscribe(Subscriber s) {
        for (List<Subscriber> l : SUBS.values()) l.remove(s);
    }

    /**
     * Tell everyone {@code e} happened. Returns the ruling it ended with; null when it was not delivered now -- this
     * machine is not the authority (dropped), or it was published from inside a subscriber (queued, delivered next).
     */
    public static Ruling publish(GameplayEvent e) {
        if (e == null) return null;
        synchronized (GameplayEvents.class) {
            if (!authority.getAsBoolean()) {
                dropped++;
                return null;
            }
            if (dispatching) {
                QUEUE.add(e);
                return null;
            }
            dispatching = true;
        }
        try {
            Ruling first = deliver(e);
            for (;;) {
                GameplayEvent next;
                synchronized (GameplayEvents.class) { next = QUEUE.poll(); }
                if (next == null) break;
                deliver(next);
            }
            return first;
        } finally {
            synchronized (GameplayEvents.class) { dispatching = false; }
        }
    }

    private static Ruling deliver(GameplayEvent e) {
        Ruling r = new Ruling();
        synchronized (GameplayEvents.class) { published++; }
        for (Phase p : Phase.values()) {
            List<Subscriber> l;
            synchronized (GameplayEvents.class) {
                List<Subscriber> have = SUBS.get(p);
                if (have == null || have.isEmpty()) continue;
                l = List.copyOf(have);
            }
            for (Subscriber s : l) {
                try {
                    s.on(e, r);
                } catch (RuntimeException ex) {
                    onError.accept(s, ex);
                }
            }
            if (r.vetoed()) {
                synchronized (GameplayEvents.class) { vetoed++; }
                break;
            }
        }
        return r;
    }

    /** Forget every subscriber and counter (engine teardown; the start of a unit test). */
    public static synchronized void reset() {
        SUBS.clear();
        QUEUE.clear();
        authority = () -> true;
        dispatching = false;
        published = dropped = vetoed = 0;
    }

    public static synchronized long publishedCount() { return published; }
    public static synchronized long droppedCount() { return dropped; }
    public static synchronized long vetoedCount() { return vetoed; }
    public static synchronized int subscriberCount() {
        int n = 0;
        for (List<Subscriber> l : SUBS.values()) n += l.size();
        return n;
    }
}
