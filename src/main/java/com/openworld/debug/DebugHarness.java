package com.openworld.debug;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.character.Health;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.game.mission.MissionInfo;
import com.openworld.game.mission.MissionManager;
import com.openworld.game.mission.MissionObjectiveType;
import com.openworld.net.NetworkManager;
import com.openworld.game.PlayerRegistry;
import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.world.RaceCheckpoint;
import com.openworld.world.SpawnConfig;
import com.openworld.world.VehicleRoute;
import com.openworld.world.Zone;
import com.openworld.world.ZoneManager;
import com.openworld.world.ZoneMarker;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BoxShape3D;
import godot.api.CollisionObject3D;
import godot.api.CollisionShape3D;
import godot.api.ConcavePolygonShape3D;
import godot.api.InputEvent;
import godot.api.InputEventKey;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.Shape3D;
import godot.core.Key;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.UUID;
import com.openworld.character.Player;
import godot.api.OS;

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
 * F8  — postDebugGunshot(): drops a "player"-faction GUNSHOT stimulus ~35 m in front of the
 *       player so the zone's "enemy" AI investigate the noise (PLAN.md E2 perception test).
 * Ctrl+F9 — the BUG-REPORT line (PLAN.md 3.26): postal code, region, position, facing, streaming zone, nearest
 *       road lane -- printed to the log AND copied to the clipboard, so "it happened here" is one paste
 *       ({@code postal 12-7-5} / {@code tp x y z} in the console go back there).
 * Shift+F9 — dumpCollisionInventory(): prints every CollisionObject3D + CollisionShape3D in the
 *       tree (path, global pos, layer/mask, shape type/size) — the "what is solid here" answer
 *       when hunting an unexpected collision layer. Headless: launch with `-- --dump-collision`
 *       to auto-dump ~3 s after scene ready.
 * F4  — spawnOnAllRoutes(): drops one AI vehicle on every VehicleRoute in the scene (PLAN.md I3) —
 *       the one-keypress test for an authored road layout (e.g. a district piece's seam routes).
 *       Headless: launch with `-- --spawn-all-routes` to auto-fire it ~3 s after scene ready.
 * Shift+F5 — reloadNearestZone(): hot-reloads the district the player is standing in, bypassing
 *       the resource cache — rebake with tools/build_piece.sh, press, see the change in place
 *       (plain F5 stays bakeWorld).
 * Shift+F3 — cycle the debug HUD (PerfDebugOverlay): FPS corner -> perf panel + frame-time graph ->
 *       + live game state (player, weapon, aim, network) -> off. Console: `hud 0-3`.
 * F3  — toggleRouteOverlay(): 3D line-draw of every registered VehicleRoute (driven path, colored
 *       turn connectors, DESPAWN crosses) + IntersectionZone boxes — see RouteDebugOverlay.
 * F6  — NetworkManager.hostServer(DEBUG_PORT): starts an ENet server for LAN testing
 *       (PLAN.md Part G). F7 — joinServer("127.0.0.1", DEBUG_PORT): connects as a
 *       client to a host on the same machine. Edit DEBUG_HOST for a real LAN peer.
 * F1  — teleportToNextZone(): jumps the local player to the next registered
 *       ZoneMarker (cycles through every district at world scale), so testing
 *       across districts doesn't require walking/driving the whole map.
 * F2  — dropWeaponHere(): spawns an ASR1 pickup at the player's feet — the companion to F1
 *       for testing weapon pickup flow in whichever district you've just teleported to.
 * Every AI spawned by either binding is equipped with an ASR1 rifle (see
 * equipDebugRifle) so it fights at range instead of relying on its bare fists.
 *
 * Delete this class once F1's real debug console (PLAN.md Pre-F1 prerequisite)
 * lands — it supersedes this one-off tool.
 */
@Script(className = "DebugHarness")
public class DebugHarness extends Node {

    private static final String AI_SCENE_PATH =
            "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final String RIFLE_SCENE_PATH =
            "res://src/main/resources/com/openworld/weapon/ASR1.tscn";
    private static final String VEHICLE_SCENE_PATH = com.openworld.carrier.vehicle.VehicleModels.DEFAULT_SCENE;
    private static final StringName CHARACTERS_GROUP = new StringName("characters");

    private static final int DEBUG_PORT = 7777;
    private static final String DEBUG_HOST = "127.0.0.1";

    /** F1 teleport-cycle position in the sorted zoneId list — persists across presses, wraps around. */
    private int teleportZoneIndex = -1;

    /** Shift+F3 perf HUD — lazily constructed as a child of this harness, toggled by visibility. */
    private PerfDebugOverlay perfOverlay;

    /** F3 route/junction 3D debug-draw — lazily constructed, toggled by visibility. */
    private RouteDebugOverlay routeOverlay;

    /** Backtick command line — lazily constructed, toggled open/closed. */
    private DebugConsole console;

    private void bugReport() {
        for (com.openworld.character.Player p : com.openworld.game.PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || !p.isLocallyOwnedPlayer()) continue;
            String line = com.openworld.world.PostalReport.line(this, p.getGlobalPosition());
            GD.print("BUG REPORT: " + line);
            godot.api.DisplayServer.clipboardSet(line);
            return;
        }
    }

    @Register
    @Override
    public void _input(InputEvent event) {
        if (!(event instanceof InputEventKey iek) || !iek.isPressed() || iek.isEcho()) return;

        if (iek.getKeycode() == Key.F9) {
            // Ctrl+F9 = the bug-report line (PLAN.md 3.26); Shift+F9 = collision inventory dump; F9 = debug mission.
            if (iek.isCtrlPressed()) bugReport();
            else if (iek.isShiftPressed()) dumpCollisionInventory();
            else if (canSpawnLocally()) startDebugMission();
        } else if (iek.getKeycode() == Key.F10) {
            // Shift+F10 = motorcycle stub walk-test; plain F10 = enemy AI spawn.
            if (iek.isShiftPressed()) spawnDebugCarrier(
                    "res://src/main/resources/com/openworld/vehicle/Motorcycle.tscn", "Motorcycle");
            else if (canSpawnLocally()) spawnTestAI(5, Faction.ENEMY, "Debug Spawn");
        } else if (iek.getKeycode() == Key.F11) {
            // Shift+F11 = boat stub walk-test (drop it near water); plain F11 = ally AI.
            if (iek.isShiftPressed()) spawnDebugCarrier(
                    "res://src/main/resources/com/openworld/vehicle/Boat.tscn", "Boat");
            else if (canSpawnLocally()) spawnTestAI(1, Faction.PLAYER, "Debug Ally");
        } else if (iek.getKeycode() == Key.F6) {
            hostDebugServer();
        } else if (iek.getKeycode() == Key.F7) {
            joinDebugServer();
        } else if (iek.getKeycode() == Key.F12) {
            // Shift+F12 = airplane stub walk-test; plain F12 = debug streaming zone.
            if (iek.isShiftPressed()) spawnDebugCarrier(
                    "res://src/main/resources/com/openworld/vehicle/Airplane.tscn", "Airplane");
            else spawnDebugZone();
        } else if (iek.getKeycode() == Key.F8) {
            postDebugGunshot();
        } else if (iek.getKeycode() == Key.F4) {
            // Shift+F4 = drop a debug race circuit in front of the player and start it;
            // plain F4 = spawn ambient traffic on every route.
            if (iek.isShiftPressed()) startDebugRace();
            else if (canSpawnLocally()) spawnOnAllRoutes();
        } else if (iek.getKeycode() == Key.F5) {
            if (iek.isShiftPressed()) reloadNearestZone(); else bakeWorld();
        } else if (iek.getKeycode() == Key.F3) {
            if (iek.isShiftPressed()) togglePerfOverlay(); else toggleRouteOverlay();
        } else if (iek.getKeycode() == Key.F1) {
            teleportToNextZone();
        } else if (iek.getKeycode() == Key.QUOTELEFT) {
            toggleConsole();
        } else if (iek.getKeycode() == Key.F2) {
            // Shift+F2 = toggle the world edge's debug planes (wall red, warning band yellow).
            if (iek.isShiftPressed()) toggleBoundsVolume(); else dropWeaponHere();
        }
    }

    /**
     * Backtick — the in-game command line (PLAN.md 4.2 / F1). Lazily built like the perf overlay, so
     * it needs no scene wiring and is there in every scene that has a harness. It is what makes a
     * story beat iterable inside one session: {@code move boss_01 0 0 0} instead of a recompile.
     */
    private void toggleConsole() {
        if (console == null || !GD.isInstanceValid(console)) {
            console = new DebugConsole();
            addChild(console);
        }
        console.toggle();
    }

    /** Shift+F2 — show/hide {@code WorldBounds}' wall and warning-band planes (PLAN.md P0 0.6). */
    private void toggleBoundsVolume() {
        com.openworld.world.WorldBounds wb = com.openworld.world.WorldBounds.get();
        if (wb == null) { GD.print("DebugHarness: no WorldBounds in this scene"); return; }
        wb.setShowDebugVolume(!wb.showDebugVolume);
        GD.print("DebugHarness: world bounds debug volume " + (wb.showDebugVolume ? "on" : "off"));
    }

    /**
     * F5 — bake the Blender-authored world source into a native {@code .tscn} (PLAN.md I6a). Converts
     * named empties (lane_/spawn_/zone_/water_/intersection_) into gameplay nodes and saves. Swap the
     * source path for the imported {@code .blend} once authored; {@code WorldSource.tscn} is the test stand-in.
     */
    private void bakeWorld() {
        com.openworld.world.WorldBaker.bakeScene(this,
                "res://src/main/resources/com/openworld/world/WorldSource.tscn",
                "res://src/main/resources/com/openworld/world/World_baked.tscn");
    }

    /**
     * Shift+F5 — hot-reload the district the player is standing in: after an external
     * {@code tools/build_piece.sh} rebake, re-streams the zone from disk (cache-bypassing) so the
     * change shows up without restarting the game. See {@link ZoneManager#reloadZone}.
     */
    /**
     * Shift+F3 — cycle the debug HUD: off → FPS corner → perf panel + frame graph → + game state → off
     * ({@link PerfDebugOverlay}). Lazily built (a CanvasLayer renders from anywhere in the tree, so no scene wiring
     * is needed — available in every DebugHarness scene); the first press shows the FPS corner.
     */
    private void togglePerfOverlay() {
        hud().cycle();
        GD.print("DebugHarness: debug HUD level " + perfOverlay.levelNow());
    }

    /** The debug HUD, built on first use at level 0. Also the console's {@code hud} command. */
    PerfDebugOverlay hud() {
        if (perfOverlay == null || !GD.isInstanceValid(perfOverlay)) {
            perfOverlay = new PerfDebugOverlay();
            addChild(perfOverlay);
            perfOverlay.setLevel(0);
        }
        return perfOverlay;
    }

    /** F3 — toggle the route/junction 3D debug-draw. Parented to this harness (a plain Node, so
     * the overlay's identity transform stays world-space — route points are global coords). */
    private void toggleRouteOverlay() {
        if (routeOverlay == null || !GD.isInstanceValid(routeOverlay)) {
            routeOverlay = new RouteDebugOverlay();
            addChild(routeOverlay);
            GD.print("DebugHarness: route overlay ON");
            return;
        }
        routeOverlay.setVisible(!routeOverlay.isVisible());
        GD.print("DebugHarness: route overlay " + (routeOverlay.isVisible() ? "ON" : "OFF"));
    }

    private void reloadNearestZone() {
        ZoneManager mgr = ZoneManager.get();
        if (mgr == null) { GD.print("DebugHarness: no ZoneManager — nothing to reload"); return; }
        ZoneMarker marker = mgr.getNearestMarker();
        if (marker == null) { GD.print("DebugHarness: no registered zone markers — nothing to reload"); return; }
        if (mgr.reloadZone(marker)) {
            GD.print("DebugHarness: hot-reloading zone '" + marker.zone.zoneId + "'");
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
     * Shift+F4 — the R2 verify's "author a 4-checkpoint loop in the test town and start it", without
     * authoring anything: four {@link RaceCheckpoint} gates in a square around the nearest player,
     * then a one-lap RACE mission over them. The gates are ordinary nodes, so what this exercises is
     * the shipped path ({@code MissionManager.startMission} → {@code RaceDirector}), not a shortcut.
     */
    private void startDebugRace() {
        Node managerNode = getNodeOrNull("/root/MissionManager");
        if (!(managerNode instanceof MissionManager manager)) {
            GD.print("DebugHarness: MissionManager autoload not found");
            return;
        }
        Node3D anchor = null;
        for (com.openworld.character.Player p : PlayerRegistry.getPlayers()) {
            if (p != null && GD.isInstanceValid(p)) { anchor = p; break; }
        }
        if (anchor == null) { GD.print("DebugHarness: no player to build a race around"); return; }
        Node parent = getParent() == null ? this : getParent();
        Vector3 at = anchor.getGlobalPosition();

        // Clear a previous debug circuit so a second press does not stack gates on top of the first.
        if (getTree() != null) {
            for (Node n : getTree().getNodesInGroup(new StringName(RaceCheckpoint.GROUP))) {
                if (n instanceof RaceCheckpoint cp && DEBUG_RACE_ID.equals(cp.raceId)) cp.queueFree();
            }
        }
        float r = 60f;
        Vector3[] offsets = {
                new Vector3(0f, 0f, -r), new Vector3(r, 0f, -r),
                new Vector3(r, 0f, r),   new Vector3(0f, 0f, r) };
        for (int i = 0; i < offsets.length; i++) {
            RaceCheckpoint cp = new RaceCheckpoint();
            cp.setName(new StringName("DebugRaceCheckpoint_" + i));
            cp.raceId = DEBUG_RACE_ID;
            cp.checkpointIndex = i;
            parent.addChild(cp);
            cp.setGlobalPosition(at.plus(offsets[i]));
        }

        MissionInfo info = new MissionInfo();
        info.missionId = "debug_race";
        info.objectiveType = MissionObjectiveType.RACE;
        info.raceId = DEBUG_RACE_ID;
        info.raceLaps = 1;
        info.playerFactions.add(Faction.PLAYER);
        info.possibleOutcomeVariants.add("WON");
        info.possibleOutcomeVariants.add("FINISHED");
        GD.print("DebugHarness: starting debug race (Shift+F4) — 4 gates, 1 lap");
        manager.startMission(info);
    }

    private static final String DEBUG_RACE_ID = "debug_race";

    /**
     * Drops `count` fresh AICharacter instances of the given faction into the Characters
     * container, each equipped with an ASR1 rifle (see {@link #equipDebugRifle}) so they
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
            ai.setGlobalPosition(jitteredSpawnPosition());

            equipDebugRifle(ai, container);
            announceSpawnIfHosting(ai);
        }

        GD.print("DebugHarness: spawned " + count + " '" + faction + "' test AI");
    }

    /**
     * Loads a fresh ASR1 rifle instance, drops it into `container` (a WeaponItem must
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

    /**
     * F12 — drops a placeholder {@link ZoneMarker} ~60 m in front of the player (PLAN.md
     * Part E / E1). Its zone (built in code so no .tres is needed) streams in five "enemy" AIs
     * when a player walks within loadRadius (40 m) and streams them back out beyond unloadRadius
     * (70 m). Walk toward the marker to load, away to unload — the E1 verify step.
     */
    private void spawnDebugZone() {
        if (getTree() == null) return;
        Node scene = getTree().getCurrentScene();
        if (scene == null) { GD.print("DebugHarness: no current scene for debug zone"); return; }

        Vector3 anchor = new Vector3(0f, 0.9f, 0f);
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) {
                Vector3 pp = p.getGlobalPosition();
                anchor = new Vector3((float) pp.getX(), (float) pp.getY(), (float) pp.getZ() - 60f);
                break;
            }
        }

        SpawnConfig cfg = new SpawnConfig();
        cfg.faction = Faction.ENEMY;
        cfg.count = 5;

        Zone zone = new Zone();
        zone.zoneId = "debug_zone";
        zone.loadRadius = 40f;
        zone.unloadRadius = 70f;
        zone.size = new Vector3(20f, 4f, 20f);
        zone.spawnConfigs.add(cfg);

        ZoneMarker marker = new ZoneMarker();
        marker.zone = zone;
        scene.addChild(marker);
        marker.setGlobalPosition(anchor);
        GD.print("DebugHarness: placed debug ZoneMarker at " + anchor
                + " (walk within 40 m to stream AI in, beyond 70 m to stream out)");
    }

    /**
     * Shift+F10/F11/F12 — drops a carrier stub (Motorcycle/Boat/Airplane) ~8 m in front of the
     * nearest player for a walk-test. Identity is stamped BEFORE addChild (fresh CharacterInfo —
     * the shared-sub-resource rule), same as every runtime vehicle spawn path.
     */
    private void spawnDebugCarrier(String scenePath, String label) {
        if (!canSpawnLocally() || getTree() == null) return;
        Node scene = getTree().getCurrentScene();
        if (scene == null) return;

        Vector3 anchor = new Vector3(0f, 2f, -8f);
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) {
                Vector3 fwd = p.getGlobalBasis().getZ().times(-1);
                anchor = p.getGlobalPosition().plus(fwd.times(8f)).plus(new Vector3(0f, 1.5f, 0f));
                break;
            }
        }

        godot.api.Resource res = godot.api.ResourceLoader.INSTANCE.load(scenePath, "",
                godot.api.ResourceLoader.CacheMode.REUSE);
        if (!(res instanceof godot.api.PackedScene packed)) {
            GD.printErr("DebugHarness: cannot load carrier scene " + scenePath);
            return;
        }
        Node node = packed.instantiate();
        if (!(node instanceof com.openworld.carrier.vehicle.Vehicle v)) {
            GD.printErr("DebugHarness: " + scenePath + " is not a Vehicle scene");
            if (node != null) node.queueFree();
            return;
        }
        CharacterInfo info = new CharacterInfo();
        info.characterId = java.util.UUID.randomUUID().toString();
        info.displayName = label;
        v.characterInfo = info;
        scene.addChild(v);
        v.setGlobalPosition(anchor);
        GD.print("DebugHarness: spawned debug " + label + " at " + anchor);
    }

    /**
     * F8 — drops a synthetic "player"-faction GUNSHOT stimulus ~35 m in front of the player (PLAN.md
     * E2), so the zone's "enemy" AI (hostile to "player") investigate a spot away from you — making the
     * "walk toward the noise" behaviour obvious rather than blending into them chasing you. Walk-test:
     * enter the debug zone to spawn enemies, break their line of sight, press F8 — they should path to
     * the noise 35 m off. (Live shots post the same stimulus via FirearmItem.useWeapon; AI that already
     * see you engage by vision regardless.)
     */
    private void postDebugGunshot() {
        com.openworld.world.StimulusManager sm = com.openworld.world.StimulusManager.get();
        if (sm == null) { GD.print("DebugHarness: StimulusManager autoload not found"); return; }
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) {
                Vector3 fwd = p.getGlobalTransform().getBasis().getColumn(2); // player's +Z (back)
                Vector3 origin = p.getGlobalPosition().minus(fwd.times(35f)); // 35 m in front (-Z)
                sm.post(com.openworld.world.StimulusManager.Type.GUNSHOT, origin, 200f, null, Faction.PLAYER);
                GD.print("DebugHarness: posted debug GUNSHOT (faction player) at " + origin);
                return;
            }
        }
        GD.print("DebugHarness: no player found for debug gunshot");
    }

    /**
     * F1 — teleports the local player to the next registered {@link ZoneMarker}, cycling
     * through every district at world scale (sorted by {@code zoneId} for a stable, predictable
     * order — {@link ZoneManager#getMarkers()} is registration order, which isn't). The same
     * registry the I5 minimap already reads, so no new bookkeeping — every district's marker is
     * permanently registered (part of the always-loaded master), regardless of whether that
     * district's own geometry is currently streamed in. A few metres above the marker so the
     * player doesn't spawn inside the ground; physics settles the rest on landing.
     */
    private void teleportToNextZone() {
        ZoneManager mgr = ZoneManager.get();
        if (mgr == null) { GD.print("DebugHarness: ZoneManager autoload not found"); return; }

        java.util.List<ZoneMarker> markers = new java.util.ArrayList<>(mgr.getMarkers());
        if (markers.isEmpty()) { GD.print("DebugHarness: no registered zone markers to teleport to"); return; }
        markers.sort(java.util.Comparator.comparing(m -> m.zone != null ? m.zone.zoneId : ""));

        Player player = null;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) { player = p; break; }
        }
        if (player == null) { GD.print("DebugHarness: no player found to teleport (F1)"); return; }

        teleportZoneIndex = (teleportZoneIndex + 1) % markers.size();
        ZoneMarker target = markers.get(teleportZoneIndex);
        Vector3 pos = target.getGlobalPosition();
        player.setGlobalPosition(new Vector3((float) pos.getX(), (float) pos.getY() + 3f, (float) pos.getZ()));
        GD.print("DebugHarness: teleported to zone '" + (target.zone != null ? target.zone.zoneId : "?")
                + "' (" + (teleportZoneIndex + 1) + "/" + markers.size() + ")");
    }

    // ── Headless auto-walk (run with `-- --auto-walk` cmdline user args) ─────────────────────

    /** Metres per second the auto-walk drags the player (highway pace — crosses a 504 m
     *  district in ~20 s, so a several-minute headless smoke exercises multiple zone
     *  stream-in/stream-out cycles plus the traffic maintenance around each). */
    private static final float AUTO_WALK_SPEED = 25f;
    /** XZ arrival slack before advancing to the next marker. */
    private static final float AUTO_WALK_ARRIVE = 25f;
    /** Tour altitude above each marker — high enough to clear every building, because the player's
     *  own MovementController still runs move_and_slide each frame: at street level a wall collision
     *  cancels the drag and the tour jams against the first facade it meets. Also high enough that
     *  ground AI stay in the PASSIVE LOD band (3D distance > {@code LOD_ACTIVE_DIST} 80 m — the old
     *  50 m altitude put the flyover inside it, and city AI shot the tour player down; a dead body
     *  ignores the drag, silently stalling the rest of the run). Zone streaming measures XZ only,
     *  so altitude doesn't distort the test. */
    private static final float AUTO_WALK_ALTITUDE = 120f;

    private boolean autoWalk = false;
    private int autoWalkIndex = 0;
    /** Accumulator for the 5 s auto-walk progress heartbeat (headless log breadcrumb). */
    private double autoWalkLogTimer = 0.0;
    /** Countdown to the {@code --dump-collision} auto-dump (0 = inactive). Delayed ~3 s past
     *  {@code _ready} so AutoLoads + the host scene's own content are fully in-tree. */
    private double dumpCollisionDelay = 0.0;
    /** Countdown to the {@code --spawn-all-routes} auto-F4 (0 = inactive). Same ~3 s settle as
     *  the collision dump so every VehicleRoute has registered before the sweep. */
    private double spawnRoutesDelay = 0.0;

    /** Optional zoneId substring from {@code --auto-walk=<filter>} — the tour starts at the first
     * matching marker (targeted headless verification of one district) instead of index 0. */
    private String autoWalkStartFilter = null;

    /**
     * Headless walk-test driver: launched with {@code -- --auto-walk} (Godot user args), drags the
     * local player through every registered {@link ZoneMarker} in {@code zoneId} order at
     * {@link #AUTO_WALK_SPEED}. This makes a {@code --headless} smoke actually exercise streaming —
     * without it the input-less player stands still forever and only its spawn district ever loads,
     * so streaming/traffic regressions (which show up on zone crossings) never reproduce in CI-style
     * runs. Same marker registry + sort as F1's {@link #teleportToNextZone}, but continuous movement
     * instead of a jump — crossings, hysteresis, and mid-stream cancels all get hit.
     */
    @Register
    @Override
    public void _ready() {
        for (String arg : OS.getCmdlineUserArgs()) {
            if ("--auto-walk".equals(arg)) { autoWalk = true; }
            else if (arg.startsWith("--auto-walk=")) {
                autoWalk = true;
                autoWalkStartFilter = arg.substring("--auto-walk=".length());
            }
            else if ("--dump-collision".equals(arg)) { dumpCollisionDelay = 3.0; }
            else if ("--spawn-all-routes".equals(arg)) { spawnRoutesDelay = 3.0; }
            else if ("--net=host".equals(arg)) { netAction = "host"; netDelay = 2.0; }
            else if ("--net=join".equals(arg)) { netAction = "join"; netDelay = 2.0; }
            else if ("--net-diag".equals(arg)) { NetworkManager.NET_DEBUG_VEHICLES = true; }
            else if (arg.startsWith("--hold-action=")) { holdAction = arg.substring("--hold-action=".length()); }
            else if ("--coop-test".equals(arg)) { coopTest = true; }
            else if (arg.startsWith("--car-test=")) { carTest = arg.substring("--car-test=".length()); }
            else if (arg.startsWith("--car-role=")) { carRole = arg.substring("--car-role=".length()); }
            else if (arg.startsWith("--car-peers=")) { carPeers = Integer.parseInt(arg.substring("--car-peers=".length())); }
            else if ("--car-test-control".equals(arg)) { com.openworld.carrier.vehicle.Vehicle.pushRemoteCars = false; }
            else if ("--crowd-dump".equals(arg)) { crowdDump = true; }
            else if ("--car-trace".equals(arg)) { com.openworld.net.VehicleNetworkController.TRACE = true; }
        }
        setPhysicsProcess(autoWalk || dumpCollisionDelay > 0.0 || spawnRoutesDelay > 0.0 || netDelay > 0.0 || holdAction != null
                || coopTest || carTest != null);
        if (autoWalk) GD.print("DebugHarness: auto-walk enabled — touring every zone marker in zoneId order"
                + (autoWalkStartFilter != null ? ", starting at first match of '" + autoWalkStartFilter + "'" : ""));
    }

    /** {@code -- --net=host|join}: press F6/F7 ~2 s after ready (headless co-op runs, PLAN.md P0 0.5). */
    private String netAction = null;
    private double netDelay = 0.0;
    /** {@code -- --hold-action=<action>}: hold an input action from 6 s after ready (a real walk, not the auto-walk drag). */
    private String holdAction = null;
    private double holdDelay = 6.0;

    /**
     * {@code -- --coop-test} (tools/net/run_net_debugworld.sh phase "coop", 2026-10-06): a CLIENT buys a weapon at a
     * real ShopCounter (MSG_SHOP_REQUEST -> MSG_SHOP_GRANT), then dies by self damage and must be respawned by the
     * host; both peers print the time of day. Every step prints a "[coop]" line the script parses.
     */
    private boolean coopTest = false;
    private double coopT = 0.0;
    private int coopStep = 0;
    private String coopItem = "";

    private Player localPlayer() {
        for (Player p : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(p) && p.isLocalOwnedPlayer()) return p;
        return null;
    }

    /**
     * {@code -- --crowd-dump} (tools/net/run_net_crowd.sh, PLAN.md 1c): after 50 s, each time the SHARED clock crosses a
     * multiple of 10 s (four times), print every light ped of every crowd -- host and client then name the same
     * instant, and the script compares them ped by ped.
     */
    private boolean crowdDump = false;
    private double crowdT = 0.0;
    private long crowdBucket = Long.MIN_VALUE;
    private int crowdDumps = 0;

    private void crowdDumpTick(double delta) {
        crowdT += delta;
        if (crowdT < 50.0 || crowdDumps >= 4) return;
        java.util.List<com.openworld.world.PedCrowd> crowds = new java.util.ArrayList<>();
        collectCrowds(getTree().getRoot(), crowds);
        if (crowds.isEmpty()) return;
        double clock = crowds.get(0).clockNow();
        long b = (long) Math.floor(clock / 10.0);
        if (crowdBucket == Long.MIN_VALUE) { crowdBucket = b; return; }
        if (b == crowdBucket) return;
        crowdBucket = b;
        crowdDumps++;
        for (com.openworld.world.PedCrowd c : crowds)
            GD.print("[crowd] bucket=" + b + " clock=" + String.format(java.util.Locale.ROOT, "%.3f", clock)
                    + " zone=" + c.zoneIdNow() + " peds=" + c.dumpNow());
    }

    private static void collectCrowds(Node n, java.util.List<com.openworld.world.PedCrowd> out) {
        if (n instanceof com.openworld.world.PedCrowd c) { out.add(c); return; }
        for (Node k : n.getChildren()) collectCrowds(k, out);
    }

    private java.util.Set<String> coopHostCarried = new java.util.HashSet<>();
    private double coopHostSeenAt = -1;
    private boolean coopHostBought = false;
    private boolean coopStarsSet, coopStarsCleared;
    private int coopStarsMax;
    private double coopDamageAt;

    /** Client: every catalog weapon any shop sells that the HOST's puppet here carries. */
    private java.util.Set<String> hostPuppetCarries() {
        java.util.Set<String> out = new java.util.HashSet<>();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || p.isLocalOwnedPlayer()) continue;
            for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.item.ShopCounter.GROUP)))
                if (n instanceof com.openworld.item.ShopCounter c)
                    for (String id : c.items()) if (com.openworld.item.WeaponGrant.carries(p, id)) out.add(id);
        }
        return out;
    }

    private void coopTick(double delta) {
        coopT += delta;
        NetworkManager net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
        boolean client = net != null && net.isNetworked() && !net.isServer();
        Player me = localPlayer();
        // a mission running BEFORE the client joins (PLAN.md 1b): the joiner must be told by the baseline
        if (!client && !coopMissionStarted && coopT >= 1.0
                && getNodeOrNull("/root/MissionManager") instanceof com.openworld.game.mission.MissionManager mm) {
            coopMissionStarted = true;
            // this phase tests co-op, not combat (PLAN.md 0.41, 2026-10-10): DebugWorld's "enemy" patrol shot the idle
            // host dead ~40 m from the spawn in ~1 run in 6 (and the respawned client once), failing the mission and
            // the purchase. Campaign layer: it survives the zone streaming and replicates to the joiner.
            if (getNodeOrNull("/root/FactionManager") instanceof com.openworld.character.FactionManager fm)
                fm.setCampaignRelationship(com.openworld.character.Faction.PLAYER, com.openworld.character.Faction.ENEMY,
                        com.openworld.character.FactionRules.NEUTRAL);
            var info = new com.openworld.game.mission.MissionInfo();
            info.missionId = "coop_baseline_test";
            info.objectiveType = com.openworld.game.mission.MissionObjectiveType.SCRIPTED;
            mm.startMission(info);
        }
        if (client && !coopMissionSeen && coopT >= 12.0
                && getNodeOrNull("/root/MissionManager") instanceof com.openworld.game.mission.MissionManager mm) {
            coopMissionSeen = true;
            GD.print("[coop] mission on join active=" + mm.missionActiveNow() + " id=" + mm.activeMissionIdNow());
        }
        if (coopStep == 0 && coopT >= 14.0) {
            coopStep = 1;
            if (client && me != null) {
                com.openworld.item.ShopCounter best = null;
                double d0 = Double.MAX_VALUE;
                for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.item.ShopCounter.GROUP))) {
                    if (n instanceof com.openworld.item.ShopCounter c) {
                        double d = c.getGlobalPosition().distanceTo(me.getGlobalPosition());
                        if (d < d0) { d0 = d; best = c; }
                    }
                }
                if (best != null) {
                    for (String id : best.items()) {
                        if (!com.openworld.item.WeaponGrant.carries(me, id) && !com.openworld.item.ShopCounter.isSupply(id)) { coopItem = id; break; }
                    }
                    me.setGlobalPosition(best.getGlobalPosition().plus(new godot.core.Vector3(0, 0.1, 0)));
                    me.setVelocity(new godot.core.Vector3());
                    GD.print("[coop] at counter " + best.getPath() + " item=" + coopItem);
                } else GD.print("[coop] no shop counter");
            }
            if (!client) {
                // shops charge since F3 (PLAN.md 1.4): the fixture pays for both purchases -- the host's own profile and
                // every joined player's session copy (which MSG_PROFILE carries back to its owner)
                com.openworld.game.profile.Economy.transfer(null, com.openworld.game.profile.Profiles.local(), 20000,
                        com.openworld.game.profile.Economy.Reason.GRANT);
                for (com.openworld.game.profile.PlayerProfile rp : com.openworld.game.profile.Profiles.remotes().values())
                    com.openworld.game.profile.Economy.transfer(null, rp, 20000, com.openworld.game.profile.Economy.Reason.GRANT);
                GD.print("[coop] funded " + (1 + com.openworld.game.profile.Profiles.remotes().size()) + " profile(s)");
            }
            if (!client && me != null) {
                // the HOST buys too (PLAN.md 1c: a host purchase took seconds to reach the client): the first weapon its
                // nearest counter sells that it does not carry
                com.openworld.item.ShopCounter best = null;
                double d0 = Double.MAX_VALUE;
                for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.item.ShopCounter.GROUP))) {
                    if (n instanceof com.openworld.item.ShopCounter c) {
                        double d = c.getGlobalPosition().distanceTo(me.getGlobalPosition());
                        if (d < d0) { d0 = d; best = c; }
                    }
                }
                if (best != null) {
                    for (String id : best.items())
                        if (!com.openworld.item.WeaponGrant.carries(me, id) && !com.openworld.item.ShopCounter.isSupply(id)) { coopItem = id; break; }
                    me.setGlobalPosition(best.getGlobalPosition().plus(new godot.core.Vector3(0.6, 0.1, 0)));
                    me.setVelocity(new godot.core.Vector3());
                }
            }
            if (client) coopHostCarried = hostPuppetCarries();
        }
        if (coopStep >= 1 && client && coopHostSeenAt < 0) {
            java.util.Set<String> now = hostPuppetCarries();
            now.removeAll(coopHostCarried);
            if (!now.isEmpty()) {
                coopHostSeenAt = coopT;
                GD.print("[coop] host puppet carries " + now + " unix_ms=" + (long) (godot.api.Time.INSTANCE.getUnixTimeFromSystem() * 1000.0));
            }
        }
        if (!client && !coopHostBought && coopT >= 26.0 && me != null && !coopItem.isEmpty()) {
            // the client starts ~6 s after the host: buying at 26 s puts it well after the client's "before" look
            coopHostBought = true;
            for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.item.ShopCounter.GROUP))) {
                if (n instanceof com.openworld.item.ShopCounter c && c.holds(me.getGlobalPosition(), 1.0)) {
                    c.buy(me, coopItem);
                    GD.print("[coop] host buy " + coopItem + " unix_ms=" + (long) (godot.api.Time.INSTANCE.getUnixTimeFromSystem() * 1000.0));
                    break;
                }
            }
        }
        if (coopStep == 1 && coopT >= 16.5) {
            coopStep = 2;
            if (client && me != null && !coopItem.isEmpty()) {
                for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.item.ShopCounter.GROUP))) {
                    if (n instanceof com.openworld.item.ShopCounter c && c.holds(me.getGlobalPosition(), 1.0)) {
                        c.buy(me, coopItem);
                        GD.print("[coop] buy " + coopItem);
                        break;
                    }
                }
            }
        }
        if (coopStep == 2 && coopT >= 19.5) {
            coopStep = 3;
            if (client && me != null) GD.print("[coop] carries " + coopItem + "=" + com.openworld.item.WeaponGrant.carries(me, coopItem));
            GD.print("[coop] clock hours=" + com.openworld.world.GameTime.hours(getTree())
                    + " unix_ms=" + (long) (godot.api.Time.INSTANCE.getUnixTimeFromSystem() * 1000.0)
                    + " hps=" + com.openworld.world.GameTime.hoursPerSecond(getTree()));
        }
        // stars replication (2026-10-08): the host gives every remote player 2 stars for 4 s; the client (whose clock
        // runs behind the host's by however late it joined) watches its HUD and only sends its self-damage once it saw
        // the stars come AND go -- a wanted player who goes down would wake ARRESTED, not HOSPITALIZED
        var ws = com.openworld.game.WantedSystem.get();
        if (!client && !coopStarsSet && coopT >= 19.6 && ws != null) {
            coopStarsSet = true;
            for (Player p : PlayerRegistry.getPlayers())
                if (p != me && p.getCharacterInfo() != null) ws.setStars(p.getCharacterInfo().characterId, 2, false);
            GD.print("[coop] host set remote stars 2");
        }
        if (!client && coopStarsSet && !coopStarsCleared && coopT >= 23.6 && ws != null) {
            coopStarsCleared = true;
            for (Player p : PlayerRegistry.getPlayers())
                if (p != me && p.getCharacterInfo() != null) ws.clear(p.getCharacterInfo().characterId);
            GD.print("[coop] host cleared remote stars");
        }
        int hud = client && me != null && ws != null && me.getCharacterInfo() != null
                ? ws.hudOf(me.getCharacterInfo().characterId).stars() : 0;
        if (client && hud > coopStarsMax) coopStarsMax = hud;
        if (coopStep == 3 && coopT >= 21.5 && (!client || (coopStarsMax > 0 && hud == 0) || coopT >= 40.0)) {
            coopStep = 4;
            coopDamageAt = coopT;
            if (client) GD.print("[coop] client hud stars=" + coopStarsMax + " cleared=" + (hud == 0));
            if (client && me != null && me.getNodeOrNull("Health") instanceof com.openworld.character.Health h) {
                // a request is capped at 500 (DamageRequestPolicy); send enough to empty the bar
                int n = (int) Math.ceil(h.maxHealth / 400.0) + 1;
                for (int i = 0; i < n; i++) h.takeDamage(null, 400f, "fall");
                GD.print("[coop] self damage sent x" + n);
            }
        }
        // the respawn: wait for the host to wake the client (the card time varies with load), give up after 25 s
        if (coopStep == 4 && coopT >= coopDamageAt + 6.0
                && (!client || (me != null && me.isAlive()) || coopT >= coopDamageAt + 25.0)) {
            coopStep = 5;
            var rs = com.openworld.game.RespawnSystem.get();
            if (client) GD.print("[coop] respawn alive=" + (me != null && me.isAlive()) + " owned=" + (me != null)
                    + " pos=" + (me != null ? me.getGlobalPosition() : "-") + " respawns=" + (rs != null ? rs.respawnsNow() : -1)
                    + " card=" + (rs != null ? rs.cardTextNow() : ""));
            else {
                GD.print("[coop] host players=" + PlayerRegistry.getPlayers().size());
                for (Node n : getTree().getNodesInGroup(new StringName("characters")))
                    if (n instanceof com.openworld.carrier.vehicle.Vehicle v
                            && !v.isInGroup(new StringName(com.openworld.carrier.vehicle.Vehicle.STREAMED_GROUP)))
                        GD.print("[coop] car " + v.getName() + " at " + v.getGlobalPosition());
            }
            coopSeatAt = coopT;
        }
        // die seated (PLAN.md 1i, 2026-10-08): the respawned client goes to the parked car, takes a seat through the
        // host's seat request, dies there; the host must unseat the corpse before the respawn, on BOTH peers.
        // It GLIDES there at a plausible speed (PLAN 0.38, 2026-10-09): a hand teleport is an implausible upstream
        // move, which the host clamps and walks at the speed cap along the straight line -- through the parked row,
        // flinging the car it stepped into, or arriving after the seat request (TOO_FAR / DEAD, ~4 runs in 8).
        if (coopStep == 5 && coopT >= coopSeatAt + 1.0) {
            coopStep = 6;
            com.openworld.carrier.vehicle.Vehicle car = coopCar();
            if (client && me != null && car != null) {
                // the car's side facing the player: the path never crosses the car
                Vector3 side = car.getGlobalTransform().getBasis().getColumn(0).normalized();
                if (side.dot(me.getGlobalPosition().minus(car.getGlobalPosition())) < 0) side = side.times(-1.0);
                coopGlideTo = car.getGlobalPosition().plus(side.times(2.6)).plus(new Vector3(0, 0.3, 0));
                GD.print("[coop] beside car " + car.getName());
            } else if (client) { GD.print("[coop] no car (me=" + (me != null) + ")");
            }
        }
        if (coopGlideTo != null && me != null) {
            Vector3 to = coopGlideTo.minus(me.getGlobalPosition());
            // m per physics frame (18 m/s): the host's clamp window can be as short as ~2 m when physics catches up and
            // runs two steps inside one sender interval (0.6 m/frame tripped it once in 6 runs)
            double step = 0.3;
            me.setGlobalPosition(to.length() <= step ? coopGlideTo : me.getGlobalPosition().plus(to.normalized().times(step)));
            me.setVelocity(new Vector3());
            if (me.movementControllerNow() != null) me.movementControllerNow().clearMotion();
            if (to.length() <= step) { coopGlideTo = null; coopArrivedAt = coopT; }
        }
        // ask for the seat like a player pressing the key again: every 1 s until seated (the host must have seen the
        // client arrive), at most 5 tries
        if (coopStep == 6 && coopArrivedAt >= 0 && coopT >= coopArrivedAt + 0.5 && coopT >= coopNextAsk) {
            com.openworld.carrier.vehicle.Vehicle car = coopCar();
            boolean seated = me != null && me.currentVehicleNode != null;
            if (client && me != null && car != null && !seated && coopAsks < 5) {
                car.requestEnter(me);
                coopAsks++;
                coopNextAsk = coopT + 1.0;
            } else {
                coopStep = 7;
            }
        }
        if (!client && coopStep == 6) coopStep = 7;
        if (coopStep == 7) {
            coopStep = 8;
            coopSeatedAt = coopT;
            if (client && me != null) {
                GD.print("[coop] seated=" + (me.currentVehicleNode != null) + " asks=" + coopAsks + " hud=" + coopHud());
                if (me.getNodeOrNull("Health") instanceof com.openworld.character.Health h) {
                    int n = (int) Math.ceil(h.maxHealth / 400.0) + 1;
                    for (int i = 0; i < n; i++) h.takeDamage(null, 400f, "fall");
                }
            }
        }
        if (coopStep == 8 && coopT >= (client ? coopSeatedAt + 12.5 : coopSeatAt + 22.0)) {
            coopStep = 9;
            // riders = Players seated in ANY car (the client's car on the client, every car on the host)
            int riders = 0;
            for (Node n : getTree().getNodesInGroup(new StringName("characters")))
                if (n instanceof com.openworld.carrier.vehicle.Vehicle v)
                    for (int i = 0; i < v.getSeatCount(); i++) if (v.getSeatOccupant(i) instanceof Player) riders++;
            if (client) GD.print("[coop] seated respawn alive=" + (me != null && me.isAlive()) + " owned=" + (me != null)
                    + " inCar=" + (me != null && me.currentVehicleNode != null) + " riders=" + riders + " hud=" + coopHud());
            else GD.print("[coop] host car riders=" + riders);
            if (!client)
                for (Node n : getTree().getNodesInGroup(new StringName("characters")))
                    if (n instanceof com.openworld.carrier.vehicle.Vehicle v
                            && !v.isInGroup(new StringName(com.openworld.carrier.vehicle.Vehicle.STREAMED_GROUP)))
                        GD.print("[coop] end car " + v.getName() + " at " + v.getGlobalPosition());
        }
    }


    /**
     * {@code -- --car-test=<driver>:<obstacle>} (tools/net/run_net_car_test.sh, user 2026-10-11: "co-op vehicle the
     * guest / host should be able to interact with each other"): {@code driver} = guest | host takes a wheel through
     * the seat request and holds the throttle; the OTHER peer's player is the obstacle -- {@code ped} stands 1.8 m
     * ahead of the sports car's nose (the car driven, 4 s); {@code seated} sits in the kei truck 10 m ahead of the
     * police car (the car driven, 2.5 s); {@code parked} leaves that truck empty (the host simulates it). Both peers print a "[cartest]" line every 0.25 s the script compares.
     * Three players: a second joiner runs with {@code --car-role=guest2}, every peer with {@code --car-peers=3}, and
     * the case names who sits in the truck -- {@code guest:seated:guest2} is a client into a client, which only the
     * host's relay carries. The peer that is neither is a bystander: it only prints what it sees.
     */
    private String carTest = null;
    private String carRole = "guest";
    private int carPeers = 2;
    private double carT = 0.0, carReadyAt = -1, carSeatedAt = -1, carDriveAt = -1, carNextAsk = 0, carNextPrint = 0;
    private Vector3 carGlideTo;
    private double carGlideSince = -1;
    private boolean carGlided, carDone, carNeutral;

    private com.openworld.carrier.vehicle.Vehicle carKet, carSpc, carPoc;

    /** The scene-placed car parked at {@code (-395, z)}: by PLACE, since a client's copy is re-supplied under another name. */
    private com.openworld.carrier.vehicle.Vehicle carParkedAt(double z) {
        for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof com.openworld.carrier.vehicle.Vehicle v) || v.isQueuedForDeletion()
                    || v.isInGroup(new StringName(com.openworld.carrier.vehicle.Vehicle.STREAMED_GROUP))) continue;
            Vector3 p = v.getGlobalPosition();
            if (Math.abs(p.getX() + 395.0) < 1.5 && Math.abs(p.getZ() - z) < 1.5) return v;
        }
        return null;
    }

    private void carTestTick(double delta) {
        carT += delta;
        NetworkManager net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
        if (net == null || !net.isNetworked()) return;
        boolean client = !net.isServer();
        // DebugWorld's "enemy" patrol must not shoot the stand (the same reason as the coop phase), from before the join
        if (!client && !carNeutral && getNodeOrNull("/root/FactionManager") instanceof com.openworld.character.FactionManager fm) {
            carNeutral = true;
            fm.setCampaignRelationship(com.openworld.character.Faction.PLAYER, com.openworld.character.Faction.ENEMY,
                    com.openworld.character.FactionRules.NEUTRAL);
        }
        Player me = localPlayer();
        if (carKet == null || !GD.isInstanceValid(carKet)) carKet = carParkedAt(50.0);
        if (carSpc == null || !GD.isInstanceValid(carSpc)) carSpc = carParkedAt(40.0);
        if (carPoc == null || !GD.isInstanceValid(carPoc)) carPoc = carParkedAt(60.0);
        com.openworld.carrier.vehicle.Vehicle ket = carKet, spc = carSpc, poc = carPoc;
        if (me == null || ket == null || spc == null || poc == null || PlayerRegistry.getPlayers().size() < carPeers) {
            if (carT >= carNextPrint) {
                carNextPrint = carT + 5.0;
                GD.print("[cartest] waiting me=" + (me != null) + " truck=" + (ket != null) + " sports=" + (spc != null)
                        + " police=" + (poc != null) + " players=" + PlayerRegistry.getPlayers().size());
            }
            return;
        }
        String[] parts = carTest.split(":");
        String role = client ? carRole : "host";
        boolean driver = role.equals(parts[0]);
        String obstacle = parts.length > 1 ? parts[1] : "ped";
        // who stands in the way / sits in the truck: named, or the other one of host and guest
        boolean sitter = role.equals(parts.length > 2 ? parts[2] : "guest".equals(parts[0]) ? "host" : "guest");
        if (carReadyAt < 0) {
            carReadyAt = carT + 3.0;
        }
        if (carT < carReadyAt) return;
        // the ped case drives the sports car (nothing ahead of it); the car cases drive the police car INTO the truck
        com.openworld.carrier.vehicle.Vehicle drive = "ped".equals(obstacle) ? spc : poc;
        com.openworld.carrier.vehicle.Vehicle mine = driver ? drive : sitter && "seated".equals(obstacle) ? ket : null;
        if (!carGlided) {
            carGlided = true;
            if (mine != null) {
                carGlideTo = mine.getGlobalPosition().plus(new Vector3(2.6, 0.3, 0));
            } else if (sitter && "ped".equals(obstacle)) {
                carGlideTo = spc.getGlobalPosition().plus(new Vector3(0, 0.3, -4.0));
            }
        }
        if (carGlideTo != null) {
            // OVER whatever stands on the way (a passer-by or a car on the line pushed the body back out every step:
            // it hung there for the whole run, 1 join in 3), 4 m above its mark, then down onto it
            Vector3 at = me.getGlobalPosition();
            Vector3 to = new Vector3(carGlideTo.getX() - at.getX(), 0, carGlideTo.getZ() - at.getZ());
            double step = 0.3;
            me.setGlobalPosition(to.length() <= step ? carGlideTo
                    : new Vector3(at.getX(), carGlideTo.getY() + 4.0, at.getZ()).plus(to.normalized().times(step)));
            me.setVelocity(new Vector3());
            if (me.movementControllerNow() != null) me.movementControllerNow().clearMotion();
            if (to.length() <= step) { carGlideTo = null; carNextAsk = carT + 0.5; }
            // a body that will not be moved to its mark: say what it is, the script retries the case once
            if (carGlideSince < 0) carGlideSince = carT;
            if (carT >= carGlideSince + 8.0 && carT >= carNextPrint) {
                carNextPrint = carT + 4.0;
                int locals = 0;
                for (Player q : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(q) && q.isLocalOwnedPlayer()) locals++;
                GD.print("[cartest] STUCK at " + at + " to " + carGlideTo + " alive=" + me.isAlive() + " locals=" + locals
                        + " physics=" + me.isPhysicsProcessing() + " ctrl=" + (me.getController() == null ? "none" : me.getController().getClass().getSimpleName())
                        + " queued=" + me.isQueuedForDeletion() + " id=" + me.getCharacterInfo().characterId
                        + " owner=" + me.getCharacterInfo().ownerPeerId + " floor=" + me.isOnFloor() + " paused=" + getTree().isPaused());
            }
            return;
        }
        if (mine != null && me.currentVehicleNode == null && carSeatedAt < 0 && carT >= carNextAsk) {
            mine.requestEnter(me);
            carNextAsk = carT + 1.0;
        }
        if (mine != null && me.currentVehicleNode != null && carSeatedAt < 0) {
            carSeatedAt = carT;
            GD.print("[cartest] seated in " + mine.getName() + " sim=" + mine.isLocallySimulated());
        }
        long ms = (long) (godot.api.Time.INSTANCE.getUnixTimeFromSystem() * 1000.0);
        if (driver && carSeatedAt >= 0 && carDriveAt < 0 && carT >= carSeatedAt + 8.0) {
            carDriveAt = carT;
            godot.api.Input.actionPress(new StringName("throttle"));
            GD.print("[cartest] drive start unix_ms=" + ms);
        }
        if (driver && carDriveAt >= 0 && !carDone && carT >= carDriveAt + ("ped".equals(obstacle) ? 4.0 : 2.5)) {
            carDone = true;
            godot.api.Input.actionRelease(new StringName("throttle"));
            GD.print("[cartest] drive end unix_ms=" + ms);
        }
        if (carT >= carNextPrint) {
            carNextPrint = carT + 0.25;
            StringBuilder sb = new StringBuilder("[cartest] unix_ms=" + ms);
            for (com.openworld.carrier.vehicle.Vehicle v : new com.openworld.carrier.vehicle.Vehicle[] {ket, spc, poc}) {
                Vector3 p = v.getGlobalPosition();
                sb.append(String.format(java.util.Locale.ROOT, " %s=(%.2f,%.2f,%.2f) yaw=%.1f", v == ket ? "ket" : v == spc ? "spc" : "poc",
                        p.getX(), p.getY(), p.getZ(), Math.toDegrees(v.getGlobalRotation().getY())));
            }
            for (Player p : PlayerRegistry.getPlayers()) {
                if (!GD.isInstanceValid(p)) continue;
                Vector3 q = p.getGlobalPosition();
                float hp = p.getNodeOrNull("Health") instanceof com.openworld.character.Health h ? h.getCurrentHealth() : -1f;
                sb.append(String.format(java.util.Locale.ROOT, " %s=(%.2f,%.2f,%.2f) hp=%.0f car=%s",
                        p.getCharacterInfo().ownerPeerId == 1 ? "hostp" : "guestp", q.getX(), q.getY(), q.getZ(), hp,
                        p.currentVehicleNode != null));
            }
            sb.append(" kmask=" + ket.getPartMask() + " pmask=" + poc.getPartMask());
            GD.print(sb.toString());
        }
    }

    private Vector3 coopGlideTo;
    private double coopArrivedAt = -1, coopNextAsk, coopSeatedAt = 1e9;
    private int coopAsks;
    private double coopSeatAt = 1e9;
    private boolean coopMissionStarted, coopMissionSeen;
    private com.openworld.carrier.vehicle.Vehicle coopCarRef;

    private com.openworld.carrier.vehicle.Vehicle coopCar() {
        if (coopCarRef != null && GD.isInstanceValid(coopCarRef)) return coopCarRef;
        Player me = localPlayer();
        if (me == null) return null;
        double best = 1e18;
        for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof com.openworld.carrier.vehicle.Vehicle v) || v.getOccupant() != null || !v.hasFreeSeat()) continue;
            if (v.isInGroup(new StringName(com.openworld.carrier.vehicle.Vehicle.STREAMED_GROUP))) continue;
            double d = v.getGlobalPosition().distanceTo(me.getGlobalPosition());
            if (d < best) { best = d; coopCarRef = v; }
        }
        return coopCarRef;
    }

    private String coopHud() {
        Node h = getTree().getRoot().findChild("HUDManager", true, false);
        return h instanceof com.openworld.ui.HUDManager hm ? hm.situationNow() : "?";
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (coopTest) coopTick(delta);
        if (carTest != null) carTestTick(delta);
        if (crowdDump) crowdDumpTick(delta);
        if (holdAction != null) {
            holdDelay -= delta;
            if (holdDelay <= 0.0) godot.api.Input.actionPress(new StringName(holdAction));
        }
        if (netDelay > 0.0) {
            netDelay -= delta;
            if (netDelay <= 0.0) {
                if ("host".equals(netAction)) hostDebugServer(); else joinDebugServer();
            }
        }
        if (dumpCollisionDelay > 0.0) {
            dumpCollisionDelay -= delta;
            if (dumpCollisionDelay <= 0.0) {
                dumpCollisionInventory();
                if (!autoWalk && spawnRoutesDelay <= 0.0) setPhysicsProcess(false);
            }
        }
        if (spawnRoutesDelay > 0.0) {
            spawnRoutesDelay -= delta;
            if (spawnRoutesDelay <= 0.0) {
                if (canSpawnLocally()) spawnOnAllRoutes();
                if (!autoWalk && dumpCollisionDelay <= 0.0) setPhysicsProcess(false);
            }
        }
        if (!autoWalk) return;
        ZoneManager mgr = ZoneManager.get();
        if (mgr == null) return;
        java.util.List<ZoneMarker> markers = new java.util.ArrayList<>(mgr.getMarkers());
        if (markers.isEmpty()) return;
        markers.sort(java.util.Comparator.comparing(m -> m.zone != null ? m.zone.zoneId : ""));

        Player player = null;
        for (Player p : PlayerRegistry.getPlayers()) {
            // The LOCAL player: on a networked client the registry also holds the host's puppet.
            if (GD.isInstanceValid(p) && p.isLocalOwnedPlayer()) { player = p; break; }
        }
        if (player == null) return;

        if (autoWalkStartFilter != null) {
            for (int i = 0; i < markers.size(); i++) {
                ZoneMarker m = markers.get(i);
                if (m.zone != null && m.zone.zoneId.contains(autoWalkStartFilter)) { autoWalkIndex = i; break; }
            }
            autoWalkStartFilter = null;
        }
        autoWalkIndex %= markers.size();
        ZoneMarker target = markers.get(autoWalkIndex);
        Vector3 tp = target.getGlobalPosition();
        Vector3 pp = player.getGlobalPosition();
        double dx = tp.getX() - pp.getX(), dz = tp.getZ() - pp.getZ();
        double dist = Math.sqrt(dx * dx + dz * dz);
        autoWalkLogTimer += delta;
        if (autoWalkLogTimer >= 5.0) {
            autoWalkLogTimer = 0.0;
            GD.print(String.format("DebugHarness: auto-walk at (%.0f, %.0f, %.0f) -> '%s' dist %.0f m",
                    pp.getX(), pp.getY(), pp.getZ(),
                    target.zone != null ? target.zone.zoneId : "?", dist));
        }
        if (dist < AUTO_WALK_ARRIVE) {
            GD.print("DebugHarness: auto-walk reached '" + (target.zone != null ? target.zone.zoneId : "?")
                    + "' (" + (autoWalkIndex + 1) + "/" + markers.size() + ")");
            autoWalkIndex = (autoWalkIndex + 1) % markers.size();
            return;
        }
        // Keep the tour driver unkillable: the altitude keeps AI passive, but stray damage
        // (explosions, vehicle hits) would otherwise kill the player and stall the whole run.
        if (player.getNodeOrNull(new NodePath("Health")) instanceof Health h && !h.isDead()) {
            h.resetFull();
        }
        double step = Math.min(AUTO_WALK_SPEED * delta, dist);
        // Drag the transform directly (not synthesized input) — streaming and traffic upkeep only
        // read the player's XZ position. Y is re-pinned every tick (gravity pulls between sets).
        float y = (float) (tp.getY() + AUTO_WALK_ALTITUDE);
        player.setGlobalPosition(new Vector3((float) (pp.getX() + dx / dist * step), y,
                (float) (pp.getZ() + dz / dist * step)));
    }

    /**
     * Shift+F9 / {@code --dump-collision} — full collision inventory of the live scene tree:
     * one line per {@link CollisionObject3D} (concrete type, node path, global position,
     * collision layer/mask) and one per {@link CollisionShape3D} (shape type + size/face count).
     * The "what is solid here, and on which layer" answer when hunting an unexpected collision
     * surface — grep the output by position or by name. Diagnostic print volume is the point;
     * it runs only on explicit request.
     */
    private void dumpCollisionInventory() {
        Node root = getTree() != null ? getTree().getRoot() : null;
        if (root == null) { GD.print("DebugHarness: no scene tree for collision dump"); return; }
        int[] counts = new int[2];   // [0] collision objects, [1] shapes
        GD.print("DebugHarness: ── collision inventory ──");
        dumpCollisionRecursive(root, counts);
        GD.print("DebugHarness: ── collision inventory done — " + counts[0]
                + " collision objects, " + counts[1] + " shapes ──");
    }

    private void dumpCollisionRecursive(Node node, int[] counts) {
        if (node instanceof CollisionObject3D co) {
            counts[0]++;
            Vector3 pos = co.isInsideTree() ? co.getGlobalPosition() : Vector3.Companion.getZERO();
            GD.print(String.format("  [%s] %s  pos=(%.1f, %.1f, %.1f)  layer=%d mask=%d",
                    co.getClass().getSimpleName(), co.getPath().getPath(),
                    pos.getX(), pos.getY(), pos.getZ(),
                    co.getCollisionLayer(), co.getCollisionMask()));
        } else if (node instanceof CollisionShape3D cs) {
            counts[1]++;
            Shape3D shape = cs.getShape();
            String desc = shape == null ? "<no shape>" : shape.getClass().getSimpleName();
            if (shape instanceof BoxShape3D box) desc += " size=" + box.getSize();
            else if (shape instanceof ConcavePolygonShape3D poly)
                desc += " faces=" + (poly.getFaces().getSize() / 3);
            GD.print("      shape " + cs.getPath().getPath() + " -> " + desc);
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            Node child = node.getChild(i);
            if (child != null) dumpCollisionRecursive(child, counts);
        }
    }

    /**
     * F2 — drops an ASR1 pickup at the local player's feet: the companion to F1's teleport for
     * testing weapon pickup flow in whichever district you've just jumped to. Same instantiate
     * pattern as {@link #equipDebugRifle} but left as a free-standing world pickup (no
     * {@code requestEquip} call) rather than equipped onto a character.
     */
    private void dropWeaponHere() {
        Player player = null;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) { player = p; break; }
        }
        if (player == null) { GD.print("DebugHarness: no player found to drop a weapon near (F2)"); return; }

        Node container = getNodeOrNull(new NodePath("../Characters"));
        if (container == null) { GD.print("DebugHarness: Characters container not found"); return; }

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
        rifle.setGlobalPosition(player.getGlobalPosition());
        GD.print("DebugHarness: dropped ASR1 pickup at " + player.getGlobalPosition());
    }

    /**
     * F4 — drops one AI vehicle on every {@link VehicleRoute} in the scene. The fastest way to test an
     * authored road layout (any baked district piece or the full world): each lane/route gets a car
     * driving its direction.
     */
    private void spawnOnAllRoutes() {
        if (getTree() == null) return;
        Node scene = getTree().getCurrentScene();
        if (scene == null) { GD.print("DebugHarness: no current scene for traffic"); return; }

        java.util.List<com.openworld.world.Lane> routes = new java.util.ArrayList<>();
        collectRoutes(scene, routes);
        if (routes.isEmpty()) { GD.print("DebugHarness: no Lane nodes found (F4)"); return; }

        Object loaded = GD.load(VEHICLE_SCENE_PATH);
        if (!(loaded instanceof PackedScene vehicleScene)) {
            GD.print("DebugHarness: failed to load " + VEHICLE_SCENE_PATH);
            return;
        }

        // Track placed spawn points so two routes sharing a start (e.g. a through lane + a turn lane)
        // don't drop cars on top of each other — overlapping rigid bodies shove apart sideways.
        java.util.List<Vector3> placed = new java.util.ArrayList<>();
        int spawned = 0;
        for (com.openworld.world.Lane route : routes) {
            if (spawnVehicleOnRoute(vehicleScene, scene, route, spawned, placed)) spawned++;
        }
        GD.print("DebugHarness: spawned " + spawned + " AI vehicles across "
                + routes.size() + " routes (F4)");
    }

    /**
     * Every {@link com.openworld.world.Lane} in the subtree — NOT every {@link VehicleRoute}.
     *
     * {@code Lane} exists precisely so a scene can mix a hand-authored marker route with a
     * Blender-computed {@code PathLaneRoute}, and {@code VehicleAIController.setRoute} has always
     * taken the interface. F4 was the straggler that still asked for the concrete class, so on a
     * piece baked from a {@code .lanekit.json} — which emits {@code PathLaneRoute} exclusively —
     * it reported "no routes found" over a world with 160 lanes in it. That is the whole road
     * network of the island rebuild's base piece.
     */
    private void collectRoutes(Node node, java.util.List<com.openworld.world.Lane> out) {
        if (node instanceof com.openworld.world.Lane r) out.add(r);
        for (Node child : node.getChildren()) collectRoutes(child, out);
    }

    /** Spawns one AI vehicle near the route's first waypoint, facing the second, bound to that route.
     *  If the spot is occupied (a shared lane start), it is nudged back along the lane so cars queue
     *  instead of overlapping. */
    private boolean spawnVehicleOnRoute(PackedScene vehicleScene, Node scene,
                                        com.openworld.world.Lane route,
                                        int idx, java.util.List<Vector3> placed) {
        // THE DRIVEN PATH, not the raw centreline. `pointAtLength` is the one thing both lane
        // representations agree on and it is what the car will actually follow — a `VehicleRoute`'s
        // `waypoints()` are its unsmoothed, un-offset markers, so a car used to be dropped on the
        // centreline of a lane it then drove offset from.
        double total = route.total();
        if (total < 1.0) return false;
        Vector3 a = route.pointAtLength(0.0);
        Vector3 b = route.pointAtLength(Math.min(6.0, total * 0.5));
        if (a == null || b == null) return false;
        // Unit direction of travel (XZ) and its reverse for back-offsetting.
        double dx = b.getX() - a.getX(), dz = b.getZ() - a.getZ();
        double len = Math.sqrt(dx * dx + dz * dz);
        if (len < 1e-3) return false;
        double ux = dx / len, uz = dz / len;

        // Start at the first marker; back off 7 m at a time until clear of already-placed cars.
        double sx = a.getX(), sz = a.getZ();
        for (int guard = 0; guard < 8 && tooClose(placed, sx, sz, 5.0); guard++) {
            sx -= ux * 7.0; sz -= uz * 7.0;
        }
        Vector3 spawnPos = new Vector3((float) sx, (float) a.getY() + 0.6f, (float) sz);
        placed.add(spawnPos);

        Node inst = vehicleScene.instantiate();
        if (!(inst instanceof Vehicle v)) { if (inst != null) inst.queueFree(); return false; }

        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = "Traffic " + (idx + 1);
        info.faction = Faction.NEUTRAL;
        v.characterInfo = info;

        scene.addChild(v);
        v.setGlobalPosition(spawnPos);
        // Face along the lane so it does not start driving backwards (Node3D.lookAt aims local -Z).
        v.lookAt(new Vector3((float) (sx + ux), (float) spawnPos.getY(), (float) (sz + uz)),
                 Vector3.Companion.getUP());

        VehicleAIController ctrl = new VehicleAIController();
        v.attachController(ctrl);
        ctrl.setRoute(route);
        return true;
    }

    private boolean tooClose(java.util.List<Vector3> placed, double x, double z, double minDist) {
        double m2 = minDist * minDist;
        for (Vector3 p : placed) {
            double dx = p.getX() - x, dz = p.getZ() - z;
            if (dx * dx + dz * dz < m2) return true;
        }
        return false;
    }

    /**
     * F10/F11's spawn position: jittered around the scene's {@code PlayerSpawn} marker when
     * present (the same convention {@code GameManager.spawnPlayerBody} uses), else the legacy
     * origin-relative box — so scenes without the marker (predating it) keep behaving exactly
     * as before.
     */
    private Vector3 jitteredSpawnPosition() {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        Node marker = scene != null ? scene.getNodeOrNull("PlayerSpawn") : null;
        if (marker instanceof Node3D anchor) {
            Vector3 pos = anchor.getGlobalPosition();
            return new Vector3(
                    (float) pos.getX() + GD.randfRange(-4.0f, 4.0f),
                    (float) pos.getY(),
                    (float) pos.getZ() + GD.randfRange(-4.0f, 4.0f));
        }
        return new Vector3(
                GD.randfRange(-12.0f, 18.0f),
                0.9f,
                GD.randfRange(-12.0f, 8.0f));
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
