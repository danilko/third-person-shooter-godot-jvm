package com.openworld.util;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.function.ToDoubleFunction;

/**
 * Engine-free "how far can a car drive from here" over a directed lane graph (PLAN.md 0.4).
 *
 * <p>{@code ZoneManager.findRoute} round-robins ambient spawns over every lane matching a prefix.
 * It used to take them in NAME order, which is not CHAIN order: road-generator names a direction's
 * lanes {@code Lane_pF0_nF0}, {@code _1}, {@code _10}, {@code _11}, {@code _2} …, so the round-robin
 * happily dropped a car on a terminal lane that has no successor, and the car drove one segment,
 * finished and was reclaimed. {@link #orderForSpawn} ranks candidates by their downstream reach
 * instead, so the first spawn indices land where a car can actually keep driving.
 *
 * <p>Generic over the lane type, with successors and length passed in, so the ranking is unit-tested
 * without the engine (same convention as {@link WeightedPick}); the caller supplies the SAME
 * successor rule the AI follows at a lane end, so "reach" means what a car will really do.
 */
public final class LaneReach {

    private LaneReach() {}

    /**
     * Longest drivable distance starting at the head of each lane in {@code start}: the lane's own
     * length plus the best successor's reach. A lane from which a CYCLE is reachable can be driven
     * forever and reads {@link Double#POSITIVE_INFINITY}. Memoised across the whole call, so the
     * cost is one pass over the reachable subgraph however many candidates share it.
     */
    public static <T> Map<T, Double> reach(List<T> start, Function<T, List<T>> successors,
                                           ToDoubleFunction<T> length) {
        Map<T, Double> memo = new IdentityHashMap<>();
        Map<T, Boolean> onPath = new IdentityHashMap<>();
        for (T t : start) visit(t, successors, length, memo, onPath);
        return memo;
    }

    private static <T> double visit(T lane, Function<T, List<T>> successors, ToDoubleFunction<T> length,
                                    Map<T, Double> memo, Map<T, Boolean> onPath) {
        Double known = memo.get(lane);
        if (known != null) return known;
        // A lane still on the current path is an ancestor: the edge back to it closes a cycle, and
        // every lane on the path from it down to here can circulate on that cycle indefinitely.
        if (onPath.containsKey(lane)) return Double.POSITIVE_INFINITY;
        onPath.put(lane, Boolean.TRUE);
        double best = 0.0;
        List<T> next = successors.apply(lane);
        if (next != null) {
            for (T s : next) {
                if (s == null) continue;
                best = Math.max(best, visit(s, successors, length, memo, onPath));
                if (best == Double.POSITIVE_INFINITY) break;
            }
        }
        onPath.remove(lane);
        double r = Math.max(0.0, length.applyAsDouble(lane)) + best;
        memo.put(lane, r);
        return r;
    }

    /**
     * The lanes a round-robin spawn should rotate through. When any candidate reaches at least
     * {@code enough}, exactly those, in their incoming (name) order — so a fleet spreads over every
     * long-enough lane and never lands on a short one. When none does, every candidate, longest
     * reach first (a small network still gets traffic, on its best lanes first). The input list is
     * not modified.
     *
     * <p>Filtering, not just ordering, is the point: the spawn index rotates, so an ordering alone
     * only delays a short lane's turn — measured on DebugWorld, 9 of 22 cars were set down on lanes
     * that ran out within 160 m once the index had walked the whole list.
     */
    public static <T> List<T> orderForSpawn(List<T> candidates, Function<T, List<T>> successors,
                                            ToDoubleFunction<T> length, double enough) {
        Map<T, Double> r = reach(candidates, successors, length);
        List<T> longEnough = new ArrayList<>();
        for (T t : candidates) if (r.getOrDefault(t, 0.0) >= enough) longEnough.add(t);
        if (!longEnough.isEmpty()) return longEnough;
        List<T> out = new ArrayList<>(candidates);
        out.sort(Comparator.comparingDouble((T t) -> -r.getOrDefault(t, 0.0)));
        return out;
    }
}
