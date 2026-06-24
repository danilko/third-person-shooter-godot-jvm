package com.openworld.game;

import godot.core.Vector3;

import java.util.HashMap;
import java.util.Map;

/**
 * Process-global registry of active GPS waypoints, keyed by {@code characterId} (PLAN.md I5). One entry
 * per player that has a waypoint set; the minimap, full map, and the world-space GPS arrow all read it,
 * and {@code NetworkManager.handleWaypointMessage} writes remote players' entries into it (the local
 * player writes its own via {@link com.openworld.character.Player#setWaypoint}).
 *
 * <p>Plain static like {@link PlayerRegistry} — not a node — so any subsystem reaches it without tree
 * plumbing. {@link Vector3} is a value type (no Godot-object leak; see CLAUDE.md "Known Quirks"), but
 * {@link #clearAll} is still called from {@code GameManager._exitTree} for hygiene + a clean restart.
 */
public final class WaypointStore {

    private static final Map<String, Vector3> WAYPOINTS = new HashMap<>();

    private WaypointStore() { }

    /** Set (or replace) the waypoint for a character. */
    public static void set(String characterId, Vector3 pos) {
        if (characterId == null || characterId.isEmpty() || pos == null) return;
        WAYPOINTS.put(characterId, pos);
    }

    /** Clear a character's waypoint (no-op if none). */
    public static void clear(String characterId) {
        if (characterId != null) WAYPOINTS.remove(characterId);
    }

    /** The waypoint for a character, or null if none set. */
    public static Vector3 get(String characterId) {
        return characterId != null ? WAYPOINTS.get(characterId) : null;
    }

    /** A snapshot copy of all live waypoints (safe to iterate while the map mutates). */
    public static Map<String, Vector3> entries() {
        return new HashMap<>(WAYPOINTS);
    }

    /** Drop every waypoint (scene restart / shutdown hygiene). */
    public static void clearAll() {
        WAYPOINTS.clear();
    }
}
