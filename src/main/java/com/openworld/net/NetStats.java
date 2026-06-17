package com.openworld.net;

import java.util.Map;
import java.util.TreeMap;

/**
 * Process-wide replication counter registry (Round 11 N1 — "fail loudly"). Every silent
 * drop/no-op path in the replication layer increments a named counter here so a "very rare"
 * desync leaves evidence even when nobody was watching the console at the moment it happened.
 * NetworkManager dumps the non-zero counters periodically.
 *
 * <p>Engine-free on purpose (no Godot types) so counting logic is unit-testable headless,
 * mirroring {@link SnapshotInterpolator}/{@link DeathLatch}. Godot's scripting callbacks run
 * single-threaded, so plain (unsynchronized) state is sufficient.
 */
public final class NetStats {

    /** Sorted so the periodic dump prints in a stable, diffable order. */
    private static final Map<String, Long> COUNTERS = new TreeMap<>();
    private static boolean dirtySinceLastDump = false;

    private NetStats() { }

    public static void increment(String key) {
        COUNTERS.merge(key, 1L, Long::sum);
        dirtySinceLastDump = true;
    }

    public static long get(String key) {
        return COUNTERS.getOrDefault(key, 0L);
    }

    /**
     * One-line summary of every non-zero counter, or an empty string when nothing changed
     * since the previous call — the caller skips printing in that case so a healthy session
     * stays log-silent. Counters are cumulative (never reset) so two dumps can be diffed.
     */
    public static String consumeDumpLine() {
        if (!dirtySinceLastDump || COUNTERS.isEmpty()) return "";
        dirtySinceLastDump = false;
        StringBuilder sb = new StringBuilder("NetStats:");
        for (Map.Entry<String, Long> e : COUNTERS.entrySet()) {
            sb.append(' ').append(e.getKey()).append('=').append(e.getValue());
        }
        return sb.toString();
    }

    /** Test hook — clears all counters and the dirty flag. */
    public static void resetForTest() {
        COUNTERS.clear();
        dirtySinceLastDump = false;
    }
}
