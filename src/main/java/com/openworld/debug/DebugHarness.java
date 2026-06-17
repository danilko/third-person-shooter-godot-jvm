package com.openworld.debug;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.game.mission.MissionInfo;
import com.openworld.game.mission.MissionManager;
import com.openworld.game.mission.MissionObjectiveType;
import com.openworld.net.NetworkManager;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.InputEvent;
import godot.api.InputEventKey;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.Key;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.UUID;
import com.openworld.character.Player;

/**
 * Throwaway Pre-C1 debug/test harness (PLAN.md "Pre-C1 — Debug/test harness").
 *
 * World.tscn already carries the right test population for C — a Player ("player"
 * faction), three "enemy" AICharacters (E1-E3), and two "player"-faction escort
 * AICharacters (P1/P2) — so this harness drives mission/HUD code against the live
 * scene rather than a separate empty room.
 *
 * F9  — registers a bare ELIMINATE_ALL MissionInfo and starts it directly via
 *       MissionManager.startMission(), bypassing F1's (not-yet-built) unlock-graph
 *       gating, exactly as the harness spec calls for.
 * F10 — spawnTestAI(5, ENEMY): drops five "enemy" AICharacter instances into the
 *       Characters container, for D1/D2-style population testing later.
 * F11 — spawnTestAI(1, PLAYER): drops one "player"-faction ally AICharacter, e.g.
 *       to test escort/squad behaviour against the F10 hostiles.
 * F6  — NetworkManager.hostServer(DEBUG_PORT): starts an ENet server for LAN testing
 *       (PLAN.md Part G). F7 — joinServer("127.0.0.1", DEBUG_PORT): connects as a
 *       client to a host on the same machine. Edit DEBUG_HOST for a real LAN peer.
 * Every AI spawned by either binding is equipped with an AR4 rifle (see
 * equipDebugRifle) so it fights at range instead of relying on its bare fists.
 *
 * Delete this class once F1's real debug console (PLAN.md Pre-F1 prerequisite)
 * lands — it supersedes this one-off tool.
 */
@RegisterClass(className = "DebugHarness")
public class DebugHarness extends Node {

    private static final String AI_SCENE_PATH =
            "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final String RIFLE_SCENE_PATH =
            "res://src/main/resources/com/openworld/weapon/AR4.tscn";
    private static final StringName CHARACTERS_GROUP = new StringName("characters");

    private static final int DEBUG_PORT = 7777;
    private static final String DEBUG_HOST = "127.0.0.1";

    @RegisterFunction
    @Override
    public void _input(InputEvent event) {
        if (!(event instanceof InputEventKey iek) || !iek.isPressed() || iek.isEcho()) return;

        if (iek.getKeycode() == Key.F9) {
            if (canSpawnLocally()) startDebugMission();
        } else if (iek.getKeycode() == Key.F10) {
            if (canSpawnLocally()) spawnTestAI(5, Faction.ENEMY, "Debug Spawn");
        } else if (iek.getKeycode() == Key.F11) {
            if (canSpawnLocally()) spawnTestAI(1, Faction.PLAYER, "Debug Ally");
        } else if (iek.getKeycode() == Key.F6) {
            hostDebugServer();
        } else if (iek.getKeycode() == Key.F7) {
            joinDebugServer();
        }
    }

    /**
     * F9/F10/F11 instantiate bodies directly into the local "characters" group —
     * fine in single-player/host (where the server is the local process and
     * announceSpawnIfHosting replicates them), but on a network client they would
     * create local-only, non-replicated bodies the server never learns about:
     * exactly the "AI moves on host only, spawn position differs" desync the
     * "server is the sole spawn authority" principle (NETWORK_REWRITE_PLAN.md
     * Phase 7 — handleSpawnMessage's isServer() guard) exists to prevent.
     */
    private boolean canSpawnLocally() {
        Node managerNode = getNodeOrNull("/root/NetworkManager");
        if (managerNode instanceof NetworkManager manager && manager.isNetworked() && !manager.isServer()) {
            GD.print("DebugHarness: ignoring local spawn/mission key — only the host may author world population while networked");
            return false;
        }
        return true;
    }

    private void hostDebugServer() {
        Node managerNode = getNodeOrNull("/root/NetworkManager");
        if (managerNode instanceof NetworkManager manager) {
            manager.hostServer(DEBUG_PORT);
        }
    }

    private void joinDebugServer() {
        Node managerNode = getNodeOrNull("/root/NetworkManager");
        if (managerNode instanceof NetworkManager manager) {
            manager.joinServer(DEBUG_HOST, DEBUG_PORT);
        }
    }

    /** F10/F11 spawn AI locally on whichever instance presses the key — when that instance is hosting, propagate the new body to connected clients via MSG_SPAWN (Phase 7's "live AI spawn propagates" verification). */
    private void announceSpawnIfHosting(Character character) {
        Node managerNode = getNodeOrNull("/root/NetworkManager");
        if (managerNode instanceof NetworkManager manager && manager.isNetworked() && manager.isServer()) {
            manager.announceSpawn(character);
        }
    }

    /**
     * Builds a bare ELIMINATE_ALL mission targeting "enemy"-faction characters and
     * starts it. World.tscn's pre-placed "enemy" AI population varies as the scene
     * is edited, so this spawns a few first whenever none are present — otherwise
     * MissionManager would track zero hostiles and the mission could never complete.
     */
    private void startDebugMission() {
        Node managerNode = getNodeOrNull("/root/MissionManager");
        if (!(managerNode instanceof MissionManager manager)) {
            GD.print("DebugHarness: MissionManager autoload not found");
            return;
        }

        if (countLivingByFaction(Faction.ENEMY) == 0) {
            GD.print("DebugHarness: no living 'enemy' characters found — spawning 3 before starting mission");
            spawnTestAI(3, Faction.ENEMY, "Debug Spawn");
        }

        MissionInfo info = new MissionInfo();
        info.missionId = "debug_eliminate_enemy";
        info.objectiveType = MissionObjectiveType.ELIMINATE_ALL;
        info.playerFactions.add(Faction.PLAYER);
        info.possibleOutcomeVariants.add("ELIMINATED");

        GD.print("DebugHarness: starting debug mission '" + info.missionId + "' (F9)");
        manager.startMission(info);
    }

    /**
     * Drops `count` fresh AICharacter instances of the given faction into the Characters
     * container, each equipped with an AR4 rifle (see {@link #equipDebugRifle}) so they
     * fight at range instead of standing around with only their fists.
     */
    private void spawnTestAI(int count, String faction, String displayPrefix) {
        Node container = getNodeOrNull(new NodePath("../Characters"));
        if (container == null) {
            GD.print("DebugHarness: Characters container not found");
            return;
        }

        Object loadedAi = GD.load(AI_SCENE_PATH);
        if (!(loadedAi instanceof PackedScene aiScene)) {
            GD.print("DebugHarness: failed to load " + AI_SCENE_PATH);
            return;
        }

        for (int i = 0; i < count; i++) {
            Node instance = aiScene.instantiate();
            if (!(instance instanceof AICharacter ai)) {
                instance.queueFree();
                continue;
            }

            CharacterInfo info = new CharacterInfo();
            info.characterId = UUID.randomUUID().toString();
            info.displayName = displayPrefix + " " + (i + 1);
            info.faction = faction;
            ai.characterInfo = info;

            container.addChild(ai);
            ai.setGlobalPosition(new Vector3(
                    GD.randfRange(-12.0f, 18.0f),
                    0.9f,
                    GD.randfRange(-12.0f, 8.0f)));

            equipDebugRifle(ai, container);
            announceSpawnIfHosting(ai);
        }

        GD.print("DebugHarness: spawned " + count + " '" + faction + "' test AI");
    }

    /**
     * Loads a fresh AR4 rifle instance, drops it into `container` (a WeaponItem must
     * already be inside the tree before WeaponController can reparent it onto the
     * character), and queues it for equip — same deferred path WeaponPickup uses
     * (WeaponController.requestEquip → equipWeapon in the next idle frame), so the
     * RigidBody3D reparent never happens inside this physics-context input callback.
     */
    private void equipDebugRifle(AICharacter ai, Node container) {
        Node wcNode = ai.getNodeOrNull(new NodePath("WeaponController"));
        if (!(wcNode instanceof WeaponController wc)) {
            GD.print("DebugHarness: " + ai.getName() + " has no WeaponController — skipping rifle equip");
            return;
        }

        Object loadedRifle = GD.load(RIFLE_SCENE_PATH);
        if (!(loadedRifle instanceof PackedScene rifleScene)) {
            GD.print("DebugHarness: failed to load " + RIFLE_SCENE_PATH);
            return;
        }

        Node instance = rifleScene.instantiate();
        if (!(instance instanceof WeaponItem rifle)) {
            instance.queueFree();
            return;
        }

        container.addChild(rifle);
        rifle.setGlobalPosition(ai.getGlobalPosition());
        wc.requestEquip(rifle);
    }

    /** Counts living "characters"-group members whose CharacterInfo.faction matches. */
    private int countLivingByFaction(String faction) {
        if (getTree() == null) return 0;
        int count = 0;
        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (node instanceof Character c && c.isAlive()
                    && c.characterInfo != null && faction.equals(c.characterInfo.faction)) {
                count++;
            }
        }
        return count;
    }
}
