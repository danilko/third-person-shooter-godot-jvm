package com.openworld.game.profile;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

/**
 * Ordered upgrade steps for the two save files (PLAN.md 1.4: CR5). A file older than the build is MIGRATED step by
 * step instead of being refused (v1 refused every other schema); a file NEWER than the build is still refused (it may
 * mean things this build cannot keep). Unknown keys ride through every step. Engine-free ({@code SaveMigrationsTest}).
 */
public final class SaveMigrations {
    private SaveMigrations() {}

    /** Step i turns version i+1 into version i+2 (index 0 = v1 -> v2). */
    public static final List<UnaryOperator<Map<String, Object>>> WORLD = List.of(
            // v1 -> v2: the save is split -- a profile file now holds what a PLAYER owns; the world document keeps its
            // keys unchanged (campaign, factions, mission, players), so the step only stamps the version
            doc -> doc);

    public static final List<UnaryOperator<Map<String, Object>>> PROFILE = List.of();

    public static final int WORLD_VERSION = WORLD.size() + 1;
    public static final int PROFILE_VERSION = PROFILE.size() + 1;

    /** The migrated copy, or null when the document is newer than this build (or has no readable version). */
    public static Map<String, Object> migrate(Map<String, Object> doc, String versionKey,
                                              List<UnaryOperator<Map<String, Object>>> steps) {
        if (doc == null) return null;
        long v = Maps.lng(doc, versionKey, -1);
        int target = steps.size() + 1;
        if (v < 1 || v > target) return null;
        Map<String, Object> out = new LinkedHashMap<>(doc);
        for (long i = v; i < target; i++) {
            out = steps.get((int) (i - 1)).apply(out);
            out.put(versionKey, i + 1);
        }
        return out;
    }
}
