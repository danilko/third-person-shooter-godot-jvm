package com.openworld.game.activity;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Where a run can be picked up again (CR5): the activity, the checkpoint STAGE it last entered and its blackboard as
 * it was on entering. A failed run is retried from it; kept in the owner's profile, a save taken mid-mission resumes
 * from it. It restarts a STAGE -- AI bodies are respawned by the world, not restored.
 */
public record ActivityCheckpoint(String activityId, String stageId, Activity.Mode mode, Map<String, Object> board) {

    public ActivityCheckpoint {
        board = board == null ? Map.of() : new LinkedHashMap<>(board);
    }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("activity", activityId);
        m.put("stage", stageId);
        m.put("mode", mode.name());
        m.put("board", new LinkedHashMap<>(board));
        return m;
    }

    @SuppressWarnings("unchecked")
    public static ActivityCheckpoint fromMap(Map<String, Object> m) {
        if (m == null || !(m.get("activity") instanceof String a) || a.isEmpty() || !(m.get("stage") instanceof String s)) return null;
        Activity.Mode mode = "REPLAY".equals(m.get("mode")) ? Activity.Mode.REPLAY : Activity.Mode.STORY;
        return new ActivityCheckpoint(a, s, mode, m.get("board") instanceof Map<?, ?> b ? (Map<String, Object>) b : Map.of());
    }
}
