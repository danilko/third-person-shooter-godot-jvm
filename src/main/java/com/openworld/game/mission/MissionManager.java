package com.openworld.game.mission;

import com.openworld.character.Character;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Object;
import godot.api.Texture2D;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.StringNames;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.net.NetworkManager;
import com.openworld.net.session.PlayerSession;

/**
 * Mission lifecycle + faction-scoped objective tracking — registered as an AutoLoad
 * singleton named "MissionManager".
 *
 * AutoLoad entry (add to project.godot after running ./gradlew build):
 *   [autoload]
 *   MissionManager="*res://src/main/java/com/openworld/game/mission/MissionManager.java"
 *
 * Only ELIMINATE_ALL has real tracking today: at startMission() the manager counts
 * living "characters" group members per hostile faction (any faction not listed in
 * MissionInfo.playerFactions), then listens to EventBus.characterEliminated and
 * decrements per victim faction. When every tracked faction reaches zero the
 * mission completes in favour of the first playerFaction.
 *
 * Gating which mission may start (the unlock-graph) is MissionDirector's job (F1).
 * This class — and the debug harness — call startMission() directly.
 */
@Script(className = "MissionManager")
public class MissionManager extends Node {

    private static final StringName CHARACTERS_GROUP = new StringName("characters");

    private MissionInfo activeMission;
    private boolean active = false;
    private final Map<String, Integer> remainingByFaction = new HashMap<>();

    /**
     * Server-side join/rejoin registry (Part G — Step 5), keyed by peer id.
     * Populated/depopulated by GameManager's peerConnected/peerDisconnected
     * handlers (Step 6); NetworkManager resolves characterId → Character via
     * the "characters" group, so this never needs to cache live Node references.
     */
    public final Map<Integer, PlayerSession> activeSessions = new HashMap<>();

    public void registerSession(PlayerSession session) {
        activeSessions.put(session.peerId, session);
    }

    public PlayerSession getSession(int peerId) {
        return activeSessions.get(peerId);
    }

    public void removeSession(int peerId) {
        activeSessions.remove(peerId);
    }

    /** Finds a CONNECTED session owning the given characterId — a second live instance of one install. */
    public PlayerSession findConnectedSessionByCharacterId(String characterId) {
        for (PlayerSession session : activeSessions.values()) {
            if (session.isConnected && characterId.equals(session.characterId)) return session;
        }
        return null;
    }

    /** Finds a disconnected session owning the given characterId — the rejoin lookup Step 6 needs. */
    public PlayerSession findDisconnectedSessionByCharacterId(String characterId) {
        for (PlayerSession session : activeSessions.values()) {
            if (!session.isConnected && characterId.equals(session.characterId)) return session;
        }
        return null;
    }

    @Register
    @Override
    public void _ready() {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.characterEliminated.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onCharacterEliminated"),
                    Object.ConnectFlags.DEFAULT);
        }
    }

    // ── Lifecycle entry points ────────────────────────────────────────────────

    /**
     * Begin tracking the given mission's objective. Bypasses unlock-graph gating —
     * callers (debug harness today, MissionDirector in F1) decide when this may run.
     */
    public void startMission(MissionInfo info) {
        activeMission = info;
        active = info != null;
        remainingByFaction.clear();
        if (info == null) {
            applyMissionFactions(null);
            return;
        }
        // Before counting: the objective's "hostile" factions are the ones THIS mission's table makes hostile.
        applyMissionFactions(info.factionTable);

        if (MissionObjectiveType.ELIMINATE_ALL.equals(info.objectiveType)) {
            countHostilesByFaction(info);
        }

        GD.print("MissionManager: started '" + info.missionId + "' (" + info.objectiveType
                + "), tracking " + remainingByFaction);

        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.missionStarted.emit(info.missionId, info.objectiveType);
        }
        broadcastWorldEvent(GameManager.WORLD_EVENT_MISSION_STARTED, info.missionId,
                java.util.List.of(info.objectiveType == null ? "" : info.objectiveType,
                        factionTablePath(info)));
    }

    /** Marks the active mission complete and emits EventBus.missionCompleted. */
    public void completeMission(String winningFaction, String outcomeVariant) {
        if (!active || activeMission == null) return;
        String missionId = activeMission.missionId;
        active = false;
        applyMissionFactions(null);
        GD.print("MissionManager: '" + missionId + "' complete — winner=" + winningFaction
                + " variant=" + outcomeVariant);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.missionCompleted.emit(missionId, winningFaction, outcomeVariant);
        }
        broadcastWorldEvent(GameManager.WORLD_EVENT_MISSION_COMPLETED, missionId,
                java.util.List.of(winningFaction == null ? "" : winningFaction,
                        outcomeVariant == null ? "" : outcomeVariant));
    }

    /** Marks the active mission failed and emits EventBus.missionFailed. */
    public void failMission(String reason) {
        if (!active || activeMission == null) return;
        String missionId = activeMission.missionId;
        active = false;
        applyMissionFactions(null);
        GD.print("MissionManager: '" + missionId + "' failed — " + reason);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.missionFailed.emit(missionId, reason);
        }
        broadcastWorldEvent(GameManager.WORLD_EVENT_MISSION_FAILED, missionId,
                java.util.List.of(reason == null ? "" : reason));
    }

    /** Host → all: mirror a mission lifecycle change to clients via the world-event seam. No-op off the host / single-player. */
    private void broadcastWorldEvent(int eventType, String missionId, java.util.List<String> args) {
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof NetworkManager net) net.broadcastWorldEvent(eventType, missionId, 0f, args);
    }

    /** Push (or clear, with null) the mission layer of {@code FactionManager}. */
    private void applyMissionFactions(com.openworld.character.FactionTable table) {
        Node fmNode = getNodeOrNull("/root/FactionManager");
        if (fmNode instanceof com.openworld.character.FactionManager fm) fm.applyMissionTable(table);
    }

    /**
     * The mission table's resource path for the client mirror, "" when there is none. A table built in
     * code has no path and cannot be mirrored; hostility is only ever decided on the host (AI targeting),
     * so a client missing it loses nothing today.
     */
    private static String factionTablePath(MissionInfo info) {
        if (info.factionTable == null) return "";
        String path = info.factionTable.getPath();
        return path == null || path.contains("::") ? "" : path;   // a sub-resource ("x.tres::id") has no loadable path
    }

    /** Start a mission from a {@code MissionInfo} {@code .tres} path (probe/debug entry point). */
    @Register
    public boolean startMissionFromPath(String path) {
        if (!(GD.load(path) instanceof MissionInfo info)) return false;
        startMission(info);
        return true;
    }

    /** {@link #completeMission} for GDScript probes. */
    @Register
    public void completeMissionNow(String winningFaction, String outcomeVariant) {
        completeMission(winningFaction, outcomeVariant);
    }

    public MissionInfo getActiveMission() { return activeMission; }
    public boolean isActive() { return active; }

    /** Probe/console readouts. Question-named so godot-jvm does not read them as bean accessors. */
    @Register
    public boolean missionActiveNow() { return active; }

    @Register
    public String activeMissionIdNow() { return active && activeMission != null ? activeMission.missionId : ""; }

    // ── EventBus listener ─────────────────────────────────────────────────────

    @Register
    public void onCharacterEliminated(String attackerName, String attackerFaction,
                                       String victimName, String victimFaction,
                                       String weaponName, Texture2D weaponIcon,
                                       boolean headshot) {
        if (!active || activeMission == null) return;
        if (!MissionObjectiveType.ELIMINATE_ALL.equals(activeMission.objectiveType)) return;

        Integer remaining = remainingByFaction.get(victimFaction);
        if (remaining == null) return;
        remaining = Math.max(0, remaining - 1);
        remainingByFaction.put(victimFaction, remaining);

        if (allHostilesEliminated()) {
            String winningFaction = activeMission.playerFactions.isEmpty()
                    ? "" : activeMission.playerFactions.get(0);
            completeMission(winningFaction, "ELIMINATED");
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void countHostilesByFaction(MissionInfo info) {
        if (getTree() == null) return;
        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (!(node instanceof Character c) || c.characterInfo == null) continue;
            String faction = c.characterInfo.faction;
            if (faction == null || faction.isEmpty()) continue;
            if (info.playerFactions.contains(faction)) continue;
            remainingByFaction.merge(faction, 1, Integer::sum);
        }
    }

    private boolean allHostilesEliminated() {
        for (int remaining : remainingByFaction.values()) {
            if (remaining > 0) return false;
        }
        return !remainingByFaction.isEmpty();
    }
}
