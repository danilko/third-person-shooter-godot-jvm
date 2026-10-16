package com.openworld.game;

import com.openworld.game.activity.Plan;

import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.BiPredicate;

/**
 * The RUNNING activities' holds on the enforcement (PLAN.md P1e step 5; declared on {@link Plan} -- noDispatch,
 * wanted lock / at least / at most / set / clear, squad, reserve, incident). The activity host registers a run's
 * {@link Plan.Enforcement} as it starts and removes it in {@code release}, whatever the end; the dispatch and the
 * wanted level ask here every tick. A PARTICIPANT is whoever the activity director says takes part now
 * ({@link #participant}), so a player who joins later is held too and one who leaves is let go.
 *
 * <p>Engine-free ({@code EnforcementHooksTest}); process-wide static state, one world at a time.
 */
public final class EnforcementHooks {
    private EnforcementHooks() {}

    /** Does this player take part in this run? Set by the activity runtime; a test sets its own. */
    public static BiPredicate<String, String> participant = (instanceId, playerId) -> false;

    private static final Map<String, Plan.Enforcement> active = new LinkedHashMap<>();
    /** instance|player pairs whose one-shot set / clear / lock baseline has been applied. */
    private static final Set<String> applied = new HashSet<>();
    /** The police stars each held player had when their lock began (instance|player -> stars). */
    private static final Map<String, Integer> lockedAt = new HashMap<>();

    public static void register(String instanceId, Plan.Enforcement e) {
        if (instanceId == null || e == null || !e.any()) return;
        active.put(instanceId, e);
    }

    public static void release(String instanceId) {
        active.remove(instanceId);
        applied.removeIf(k -> k.startsWith(instanceId + "|"));
        lockedAt.keySet().removeIf(k -> k.startsWith(instanceId + "|"));
    }

    public static boolean any() { return !active.isEmpty(); }

    /** Is {@code side} kept from dispatching at this player by a run they take part in? */
    public static boolean noDispatch(String playerId, String side) {
        for (Map.Entry<String, Plan.Enforcement> e : active.entrySet()) {
            Plan.Enforcement h = e.getValue();
            if ((h.noDispatchAll || h.noDispatch.contains(side)) && participant.test(e.getKey(), playerId)) return true;
        }
        return false;
    }

    /** The forces hunting this player because of a run (side -> stars; the highest when two runs ask). */
    public static Map<String, Integer> squads(String playerId) {
        Map<String, Integer> out = new LinkedHashMap<>();
        for (Map.Entry<String, Plan.Enforcement> e : active.entrySet())
            if (!e.getValue().squads.isEmpty() && participant.test(e.getKey(), playerId))
                for (Map.Entry<String, Integer> s : e.getValue().squads.entrySet()) out.merge(s.getKey(), s.getValue(), Math::max);
        return out;
    }

    /**
     * The police stars this player must have now, given what they have: the one-shot set / clear the first time a
     * run sees them, then lock, at least and at most. Returns {@code stars} unchanged when no run holds them.
     */
    public static int wanted(String playerId, int stars) {
        int out = stars;
        for (Map.Entry<String, Plan.Enforcement> e : active.entrySet()) {
            Plan.Enforcement h = e.getValue();
            if (!participant.test(e.getKey(), playerId)) continue;
            String key = e.getKey() + "|" + playerId;
            if (applied.add(key)) {
                if (h.wantedClear) out = 0;
                if (h.wantedSet >= 0) out = h.wantedSet;
                if (h.wantedLock) lockedAt.put(key, out);
            }
            if (h.wantedLock && lockedAt.containsKey(key)) out = lockedAt.get(key);
            if (h.wantedAtLeast >= 0) out = Math.max(out, h.wantedAtLeast);
            if (h.wantedAtMost >= 0) out = Math.min(out, h.wantedAtMost);
        }
        return out;
    }

    /** Every run's reserves, by run (the dispatch takes them from the stations). */
    public static Map<String, Map<String, Integer>> reserves() {
        Map<String, Map<String, Integer>> out = new LinkedHashMap<>();
        for (Map.Entry<String, Plan.Enforcement> e : active.entrySet())
            if (!e.getValue().reserves.isEmpty()) out.put(e.getKey(), e.getValue().reserves);
        return out;
    }

    /** Clear everything (a new session; tests). */
    public static void reset() {
        active.clear();
        applied.clear();
        lockedAt.clear();
    }
}
