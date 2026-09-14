package com.openworld.util;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

/**
 * Guards ambient-traffic spawn ordering (PLAN.md 0.4). The bug: {@code ZoneManager.findRoute}
 * round-robined lanes in name order, so a car landed on a lane with no successor, drove one
 * segment and was reclaimed. The fixture is DebugWorld's forward direction as road-generator
 * publishes it — names sort {@code _1, _10, _11, _2 …} while the chain runs
 * {@code nF0 → _11 → _10 → _9 → _6 → _5 → _4 (end)}, plus a lane {@code _7} that ends at once.
 */
class LaneReachTest {

    private static final Map<String, List<String>> NEXT = new HashMap<>();
    private static final Map<String, Double> LEN = new HashMap<>();

    private static void lane(String name, double len, String... next) {
        LEN.put(name, len);
        NEXT.put(name, List.of(next));
    }

    static {
        lane("nF0", 30, "_11");
        lane("_1", 28, "nF0");
        lane("_10", 73, "_9");
        lane("_11", 129, "_10");
        lane("_4", 24);
        lane("_5", 18, "_4");
        lane("_6", 76, "_5");
        lane("_7", 89);
        lane("_9", 90, "_6");
    }

    private static List<String> order(List<String> candidates, double enough) {
        return LaneReach.orderForSpawn(candidates, n -> NEXT.getOrDefault(n, List.of()),
                n -> LEN.getOrDefault(n, 0.0), enough);
    }

    @Test
    void sumsTheLongestChain() {
        Map<String, Double> r = LaneReach.reach(List.of("_1", "_7"),
                n -> NEXT.getOrDefault(n, List.of()), n -> LEN.get(n));
        assertEquals(28 + 30 + 129 + 73 + 90 + 76 + 18 + 24, r.get("_1"), 1e-9);
        assertEquals(89, r.get("_7"), 1e-9);
    }

    @Test
    void onlyLongEnoughLanesAreOffered() {
        // Name order would rotate a car onto "_7" (89 m, no successor) or "_4" (24 m). Reaches here:
        // nF0 440, _1 468, _11 410, _10 281, _9 208, _6 118, _7 89, _5 42, _4 24.
        List<String> names = List.of("nF0", "_1", "_10", "_11", "_4", "_5", "_6", "_7", "_9");
        assertEquals(List.of("nF0", "_1", "_11"), order(names, 350));
        assertEquals(List.of("nF0", "_1", "_10", "_11", "_9"), order(names, 200));
    }

    @Test
    void withNothingLongEnoughTheBestComeFirst() {
        assertEquals(List.of("_10", "_9", "_6", "_7", "_5", "_4"),
                order(List.of("_4", "_5", "_6", "_7", "_9", "_10"), 1000));
    }

    @Test
    void aCycleIsForever() {
        Map<String, List<String>> ring = Map.of("a", List.of("b"), "b", List.of("c"), "c", List.of("a"),
                "spur", List.of("a"), "dead", List.of());
        Map<String, Double> r = LaneReach.reach(List.of("spur", "dead", "b"),
                n -> ring.getOrDefault(n, List.of()), n -> 10.0);
        assertEquals(Double.POSITIVE_INFINITY, r.get("spur"));
        assertEquals(Double.POSITIVE_INFINITY, r.get("a"));
        assertEquals(Double.POSITIVE_INFINITY, r.get("b"));
        assertEquals(Double.POSITIVE_INFINITY, r.get("c"));
        assertEquals(10.0, r.get("dead"));
    }

    @Test
    void selfLoopAndMissingSuccessorsDoNotThrow() {
        Map<String, Double> r = LaneReach.reach(List.of("self", "nulls"),
                n -> n.equals("self") ? List.of("self") : null, n -> 5.0);
        assertEquals(Double.POSITIVE_INFINITY, r.get("self"));
        assertEquals(5.0, r.get("nulls"));
    }
}
