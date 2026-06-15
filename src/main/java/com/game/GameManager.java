package com.game;

import com.character.Character;
import com.character.CharacterController;
import com.character.CharacterInfo;
import com.character.Faction;
import com.character.NetworkController;
import com.character.Player;
import com.game.net.PickupGrantPolicy;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Input;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.Callable;
import godot.core.StringName;
import godot.core.StringNames;
import godot.core.Vector3;
import godot.global.GD;

import java.util.HashSet;
import java.util.Set;

/**
 * Central game state machine — registered as an AutoLoad singleton named "GameManager".
 *
 * Responsibilities:
 *  - Track current GameState (PLAYING, PAUSED, GAME_OVER)
 *  - Respond to player death (show game-over screen, restart, quit)
 *  - Provide a single entry point for scene transitions
 *
 * AutoLoad entry (add to project.godot after running ./gradlew build):
 *   [autoload]
 *   GameManager="*res://gdj/com/game/GameManager.gdj"
 *
 * Wire EventBus.playerDied → GameManager.onPlayerDied() in the scene or in _ready().
 */
@RegisterClass(className = "GameManager")
public class GameManager extends Node {

    public enum GameState {
        PLAYING,
        PAUSED,
        GAME_OVER
    }

    private GameState currentState = GameState.PLAYING;

    /**
     * characterIds of every live, human-controlled (Player) character. GAME_OVER
     * fires only once this set empties — generalises the old "the player died"
     * single-character rule to co-op, where multiple Players can be present and
     * the session must outlive any individual one of them.
     */
    private final Set<String> alivePlayerCharacterIds = new HashSet<>();

    @RegisterFunction
    @Override
    public void _ready() {
        // Connect to EventBus once it is available as a sibling AutoLoad.
        // AutoLoads are added in order, so EventBus must be listed first in project.godot.
        Node eventBusNode = getNodeOrNull("/root/EventBus");
        if (eventBusNode instanceof EventBus) {
            EventBus bus = (EventBus) eventBusNode;
            bus.characterSpawned.connectUnsafe(Callable.createUnsafe(this, StringNames.toGodotName("onCharacterSpawned")), godot.api.Object.ConnectFlags.DEFAULT);
            bus.characterDied.connectUnsafe(Callable.createUnsafe(this, StringNames.toGodotName("onCharacterDied")), godot.api.Object.ConnectFlags.DEFAULT);
            // Note: playerDied is intentionally NOT connected here — it fires per dead
            // body. GAME_OVER is driven by the characterSpawned/characterDied "all dead"
            // tracking below, which emits EventBus.allPlayersDied for MenuManager's UI.
        }
    }

    // ── State transitions ─────────────────────────────────────────────────────

    /** Track every spawned human-controlled (Player) character for the "all dead" check. */
    @RegisterFunction
    public void onCharacterSpawned(Node node, CharacterInfo info) {
        if (node instanceof Player && info != null && !info.characterId.isEmpty()) {
            alivePlayerCharacterIds.add(info.characterId);
        }
    }

    /** GAME_OVER fires once every tracked Player character has died — not on the first. */
    @RegisterFunction
    public void onCharacterDied(CharacterInfo info) {
        if (info == null) return;
        if (alivePlayerCharacterIds.remove(info.characterId) && alivePlayerCharacterIds.isEmpty()) {
            if (currentState != GameState.PLAYING) return;
            transitionTo(GameState.GAME_OVER);
            // Surface the session-ending game-over screen ONLY now that every player is down.
            // MenuManager listens to allPlayersDied (not the per-body playerDied) so a single
            // co-op teammate's death no longer kicks the whole session — including the host,
            // which holds a Player puppet for the client — to the restart menu.
            Node busNode = getNodeOrNull("/root/EventBus");
            if (busNode instanceof EventBus bus) bus.allPlayersDied.emit();
        }
    }

    public void pauseGame() {
        if (currentState != GameState.PLAYING) return;
        transitionTo(GameState.PAUSED);
        if (getTree() != null) getTree().setPause(true);
    }

    public void resumeGame() {
        if (currentState != GameState.PAUSED) return;
        transitionTo(GameState.PLAYING);
        if (getTree() != null) getTree().setPause(false);
    }

    public void restartLevel() {
        if (getTree() != null) getTree().setPause(false);
        Input.INSTANCE.setMouseMode(Input.MouseMode.CAPTURED);
        transitionTo(GameState.PLAYING);
        // End any live network session before reloading: NetworkManager is an AutoLoad and
        // survives reloadCurrentScene, so without this a "restart" would carry a stale ENet
        // connection into the fresh scene. After leaveSession the reload comes up single-player.
        NetworkManager net = getNetworkManager();
        if (net != null) net.leaveSession();
        if (getTree() != null) getTree().reloadCurrentScene();
    }

    public void loadLevel(String scenePath) {
        transitionTo(GameState.PLAYING);
        if (getTree() != null) getTree().changeSceneToFile(scenePath);
    }

    // ── Getters ───────────────────────────────────────────────────────────────

    public GameState getCurrentState() {
        return currentState;
    }

    public boolean isPlaying() {
        return currentState == GameState.PLAYING;
    }

    // ── Bot-fill / L4D controller swap (Phase 4, Step 5) ─────────────────────

    /**
     * Called when the owning player disconnects.
     * Replaces whatever controller is currently driving the body (ServerProxyController
     * when networked, PlayerController in single-player) with a CharacterController
     * (AI bot) so the game continues without a human driver. Goes through
     * attachController — not a name-keyed lookup — so Character's cached `controller`
     * field stays correct regardless of which controller type is actually attached.
     */
    public void onPlayerLeft(Player body) {
        body.attachController(new CharacterController());
        GD.print("GameManager: player left — bot attached to " + body.getName());
    }

    /**
     * Called when a player reconnects or takes control of a body.
     * Removes the AI CharacterController and reattaches a PlayerController so
     * the human drives the body again.
     */
    public void onPlayerJoined(Player body) {
        // Ownership-based authority: the remote client OWNS its own body and simulates it
        // locally, reporting its state upstream. On the host this body is a puppet driven by
        // those reports — a NetworkController (interpolated from MSG_SNAPSHOT), exactly like
        // every other non-owned body. The host never re-simulates it, which is what removes
        // the dual-simulation teleporting. (Health stays host-authoritative — see
        // NetworkController.receiveSnapshot's applyHealth gate.)
        body.attachController(new NetworkController());
        GD.print("GameManager: player joined — NetworkController (puppet) attached to " + body.getName());
    }

    // ── Network join/rejoin (Part G — Step 6) ────────────────────────────────
    //
    // peerConnected/peerDisconnected fire too early to act on — peerId is reassigned
    // by ENet on every (re)connection, so it can't key session state across disconnects.
    // The real join/rejoin decision happens in onPeerIdentified, once the client reports
    // its PersistentPlayerId via NetworkManager.identifyPeer. That id *becomes* the
    // body's CharacterInfo.characterId on first join — which is what makes "matching
    // characterId-owner" on rejoin meaningful: the same human always owns the same
    // characterId across relaunches, so PlayerSession.characterId doubles as the
    // rejoin key without adding a redundant field.

    private static final String PLAYER_SCENE_PATH = "res://src/main/resources/com/character/Player.tscn";
    private static final String AI_SCENE_PATH = "res://src/main/resources/com/character/AICharacter.tscn";
    private static final StringName CHARACTERS_GROUP = new StringName("characters");

    /** Server-side: a peer connected at the transport level. Real handling waits for identifyPeer. */
    public void onPeerConnected(int peerId) {
        GD.print("GameManager: peer connected — " + peerId);
    }

    /** Server-side: a peer disconnected — mark its session offline and bot-fill its body. */
    public void onPeerDisconnected(int peerId) {
        GD.print("GameManager: peer disconnected — " + peerId);
        MissionManager missions = getMissionManager();
        if (missions == null) return;

        PlayerSession session = missions.getSession(peerId);
        if (session == null) return;
        session.isConnected = false;

        Player body = findPlayerByCharacterId(session.characterId);
        if (body != null) onPlayerLeft(body);
    }

    /**
     * Server-side: a client reported its stable PersistentPlayerId. Either restores
     * control of an existing (disconnected) body — rejoin — or registers a fresh
     * session and spawns a new one — first join.
     */
    public void onPeerIdentified(int peerId, String persistentPlayerId) {
        MissionManager missions = getMissionManager();
        if (missions == null) return;

        NetworkManager net = getNetworkManager();

        PlayerSession session = missions.findDisconnectedSessionByCharacterId(persistentPlayerId);
        if (session != null) {
            int previousPeerId = session.peerId;
            session.peerId = peerId;
            session.isConnected = true;
            missions.removeSession(previousPeerId);
            missions.registerSession(session);

            Player body = findPlayerByCharacterId(persistentPlayerId);
            if (body != null) {
                if (body.characterInfo != null) body.characterInfo.ownerPeerId = peerId;
                onPlayerJoined(body);
                GD.print("GameManager: peer " + peerId + " rejoined as " + persistentPlayerId);
            }
            // Baseline batch covers the rejoining body too (it's already in "characters") —
            // the rejoining client otherwise has no local copy of the world to resume into.
            // Pickups after spawns: the holder bodies must exist before their pickup events.
            if (net != null) {
                net.sendBaselineSpawns(peerId);
                net.sendBaselinePickups(peerId);
                // Inventories last: bodies exist and pickup events have applied, so the
                // manifests only have to cover what events never carried (Round 11 N2).
                net.sendBaselineInventories(peerId);
                // Occupied vehicles after spawns — the seated body must exist first (N3).
                net.sendBaselineVehicleOccupancy(peerId);
            }
            return;
        }

        missions.registerSession(new PlayerSession(peerId, persistentPlayerId, Faction.PLAYER));
        // Baseline first — it can never include the about-to-be-created body (not yet in
        // "characters"), so spawnPlayerBody's own announceSpawn is what tells the new
        // peer about itself, with no risk of a duplicate baseline entry. Pickups after
        // spawns: the holder bodies must exist on the joiner before their pickup events.
        if (net != null) {
            net.sendBaselineSpawns(peerId);
            net.sendBaselinePickups(peerId);
            net.sendBaselineInventories(peerId);   // after spawns + pickups — see rejoin branch
            net.sendBaselineVehicleOccupancy(peerId);   // occupied vehicles after spawns (N3)
        }
        spawnPlayerBody(peerId, persistentPlayerId);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private MissionManager getMissionManager() {
        Node node = getNodeOrNull("/root/MissionManager");
        return node instanceof MissionManager manager ? manager : null;
    }

    private NetworkManager getNetworkManager() {
        Node node = getNodeOrNull("/root/NetworkManager");
        return node instanceof NetworkManager net ? net : null;
    }

    private Node resolveCharactersContainer() {
        if (getTree() == null) return null;
        Node scene = getTree().getCurrentScene();
        return scene != null ? scene.getNodeOrNull("Characters") : null;
    }

    private Character findCharacterById(String characterId) {
        if (getTree() == null) return null;
        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (node instanceof Character c && c.characterInfo != null
                    && characterId.equals(c.characterInfo.characterId)) {
                return c;
            }
        }
        return null;
    }

    private Player findPlayerByCharacterId(String characterId) {
        return findCharacterById(characterId) instanceof Player p ? p : null;
    }

    /** Resolves a pickupId to its live Pickup via the "pickups" group — mirrors findCharacterById. */
    private com.environment.Pickup findPickupById(String pickupId) {
        if (getTree() == null) return null;
        for (Node node : getTree().getNodesInGroup(new StringName(com.environment.Pickup.PICKUPS_GROUP))) {
            if (node instanceof com.environment.Pickup p && pickupId.equals(p.pickupId)) return p;
        }
        return null;
    }

    // ── Host-arbitrated pickups (Phase D — see NETWORK_REWRITE_PLAN.md) ───────

    /**
     * Generous grant radius: the host validates a request against its interpolated (50-100 ms
     * stale) puppet position, so this only rejects requests for items nowhere near the body —
     * a close race is decided by arrival order (first REQUEST wins via ALREADY_TAKEN).
     */
    private static final double PICKUP_GRANT_TOLERANCE_METERS = 4.0;

    /**
     * Host-side arbitration for a client's MSG_PICKUP_REQUEST: evaluate via the unit-tested
     * {@link PickupGrantPolicy}, and on GRANT collect on the host's copy (the requester's puppet
     * equips it) then broadcast MSG_PICKUP_TAKEN to every client — including the requester, whose
     * own collect happens only on that echo (it never collects optimistically).
     */
    public void processPickupRequest(int senderPeerId, String pickupId, String characterId) {
        com.environment.Pickup pickup = findPickupById(pickupId);
        Character character = findCharacterById(characterId);
        boolean senderOwns = character != null && character.characterInfo != null
                && character.characterInfo.ownerPeerId == senderPeerId;
        double distance = (pickup != null && character != null)
                ? pickup.getGlobalPosition().distanceTo(character.getGlobalPosition())
                : Double.NaN;

        PickupGrantPolicy.Verdict verdict = PickupGrantPolicy.evaluate(
                pickup != null, pickup != null && pickup.isTaken(),
                character != null, senderOwns, distance, PICKUP_GRANT_TOLERANCE_METERS);
        if (verdict != PickupGrantPolicy.Verdict.GRANT) {
            GD.print("GameManager: denied pickup request from peer " + senderPeerId
                    + " for '" + pickupId + "' — " + verdict
                    + (pickup != null
                            ? " [taken=" + pickup.isTaken() + " at " + pickup.getPath().getPath()
                                    + " distance=" + distance + "]"
                            : " [no pickup with that id in 'pickups' group]"));
            return;
        }
        GD.print("GameManager: granted pickup '" + pickupId + "' to " + characterId
                + " (peer " + senderPeerId + ", distance=" + distance + ")");

        // Capture the item state BEFORE collecting (a throwable merge can free the node and
        // its magazine field is consumed into the stack). Resolve the collect FIRST — now
        // synchronous — then broadcast only if the host actually consumed it. Broadcasting
        // before resolution was the divergence: if the equip bounced the item back to the
        // world (slot-displacement guard), every client still deleted it from their world.
        int magazine = pickup.getReplicatedMagazine();
        int reserve = pickup.getReplicatedReserve();
        pickup.applyReplicatedPickup(character, magazine, reserve);
        NetworkManager net = getNetworkManager();
        if (net != null && pickup.isTaken()) {
            net.broadcastPickupTaken(pickupId, characterId, magazine, reserve);
        }
    }

    /** Client-side MSG_PICKUP_TAKEN apply — mirror the collect on this peer's copies. Idempotent. */
    public void applyReplicatedPickup(String pickupId, String characterId, int magazine, int reserve) {
        com.environment.Pickup pickup = findPickupById(pickupId);
        Character character = findCharacterById(characterId);
        if (pickup == null || character == null) {
            GD.print("GameManager: PICKUP_TAKEN apply failed for '" + pickupId + "' → " + characterId
                    + (pickup == null ? " [pickup not found by id]" : "")
                    + (character == null ? " [character not found by id]" : ""));
            return;
        }
        if (pickup.isTaken()) {
            GD.print("GameManager: PICKUP_TAKEN no-op for '" + pickupId + "' — already taken locally");
            return;
        }
        pickup.applyReplicatedPickup(character, magazine, reserve);
    }

    /**
     * MSG_WEAPON_DROPPED apply (Phase E): take the weapon out of the character's slot and return
     * it to the world at the originator's position/impulse, adopting the event's newPickupId so
     * item identities converge across peers. When the slot is already empty — the displacement
     * race, where this peer's own replicated equip self-dropped the item an instant earlier —
     * fall back to the world item under its pre-drop id and converge it in place.
     */
    public void applyReplicatedDrop(String characterId, int slot, String oldPickupId, String newPickupId,
            Vector3 position, Vector3 impulse, int magazine, int reserve) {
        Character character = findCharacterById(characterId);
        if (character == null) return;
        Node wcNode = character.getNodeOrNull("WeaponController");
        if (wcNode instanceof com.character.WeaponController wc
                && wc.applyReplicatedDrop(slot, newPickupId, position, impulse, magazine, reserve)) {
            return;
        }
        if (findPickupById(oldPickupId) instanceof com.character.WeaponItem world && !world.isTaken()) {
            world.pickupId = newPickupId;
            world.setMagazine(magazine);
            world.setReserve(reserve);
            world.setGlobalPosition(position);
            world.setLinearVelocity(Vector3.Companion.getZERO());
            world.setAngularVelocity(Vector3.Companion.getZERO());
            world.applyCentralImpulse(impulse);
        }
    }

    // ── Host-arbitrated vehicle seats (Round 11 N3) ───────────────────────────

    /** Resolves a vehicleId to its live Vehicle via the "characters" group — mirrors findCharacterById. */
    private com.vehicle.Vehicle findVehicleById(String vehicleId) {
        if (getTree() == null) return null;
        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (node instanceof com.vehicle.Vehicle v && v.getCharacterInfo() != null
                    && vehicleId.equals(v.getCharacterInfo().characterId)) {
                return v;
            }
        }
        return null;
    }

    /**
     * Host-side arbitration for a MSG_VEHICLE_SEAT_REQUEST (and the host's own enter/exit,
     * which Vehicle.requestEnter/requestExit route here with senderPeerId = SERVER_PEER_ID):
     * evaluate via the unit-tested {@link com.game.net.VehicleSeatPolicy}, and on GRANT seat
     * the character on the host's copy and broadcast MSG_VEHICLE_OCCUPANCY to every client —
     * including the requester, whose own enter/exit happens only on that echo (mirrors the
     * pickup grant: no optimistic local enter to roll back).
     */
    public void processVehicleSeatRequest(int senderPeerId, String vehicleId, String characterId, boolean entering) {
        com.vehicle.Vehicle vehicle = findVehicleById(vehicleId);
        Character character = findCharacterById(characterId);
        boolean senderOwns = character != null && character.characterInfo != null
                && character.characterInfo.ownerPeerId == senderPeerId;

        com.game.net.VehicleSeatPolicy.Verdict verdict;
        if (entering) {
            double distance = (vehicle != null && character != null)
                    ? vehicle.getGlobalPosition().distanceTo(character.getGlobalPosition())
                    : Double.NaN;
            verdict = com.game.net.VehicleSeatPolicy.evaluateEnter(
                    vehicle != null, vehicle != null && vehicle.isAlive(),
                    vehicle != null && vehicle.getOccupant() != null,
                    character != null, character != null && character.isAlive(), senderOwns,
                    distance, com.game.net.VehicleSeatPolicy.ENTER_TOLERANCE_METERS);
        } else {
            verdict = com.game.net.VehicleSeatPolicy.evaluateExit(
                    vehicle != null, vehicle != null && character != null && vehicle.getOccupant() == character,
                    senderOwns);
        }
        if (verdict != com.game.net.VehicleSeatPolicy.Verdict.GRANT) {
            GD.print("GameManager: denied vehicle " + (entering ? "enter" : "exit") + " request from peer "
                    + senderPeerId + " for '" + vehicleId + "' — " + verdict);
            return;
        }
        GD.print("GameManager: granted vehicle " + (entering ? "enter" : "exit") + " '" + vehicleId
                + "' ↔ " + characterId + " (peer " + senderPeerId + ")");

        // Ownership BEFORE the seat change, so the hot-swapped controller's isAuthority()
        // reads the new owner the moment it lands on the vehicle. Exit hands locomotion
        // back to the host. The atomic occupancy broadcast carries the same owner.
        // applyAuthorityState ordering: BEFORE tryEnter (clear the puppet controller —
        // seeding velocities — ahead of the live hot-swap) but AFTER tryExit (the live
        // controller must leave the vehicle before a puppet controller can take over).
        CharacterInfo info = vehicle.getCharacterInfo();
        info.ownerPeerId = entering ? senderPeerId : NetworkManager.SERVER_PEER_ID;
        if (entering) {
            vehicle.applyAuthorityState();
            vehicle.tryEnter(character);
        } else {
            vehicle.tryExit();
            vehicle.applyAuthorityState();
        }

        NetworkManager net = getNetworkManager();
        if (net != null && net.isNetworked()) {
            net.broadcastVehicleOccupancy(info.characterId,
                    entering ? characterId : "", info.ownerPeerId, entering);
        }
    }

    /**
     * Host-side FORCED unseat — destruction/cleanup path. Deliberately bypasses
     * VehicleSeatPolicy: the policy's owner check exists to stop one peer unseating another
     * peer's driver, but a host-initiated eviction (vehicle about to be freed) is always
     * legitimate — routing it through processVehicleSeatRequest with SERVER_PEER_ID was
     * denied NOT_OWNER for client drivers, the exit never broadcast, and the driving
     * client's controller was freed inside the despawned vehicle (stuck body, then crash).
     */
    public void forceVehicleExit(com.vehicle.Vehicle vehicle) {
        if (vehicle == null || vehicle.getOccupant() == null || vehicle.getCharacterInfo() == null) return;
        CharacterInfo info = vehicle.getCharacterInfo();
        info.ownerPeerId = NetworkManager.SERVER_PEER_ID;
        vehicle.tryExit();
        vehicle.applyAuthorityState();
        NetworkManager net = getNetworkManager();
        if (net != null && net.isNetworked() && net.isServer()) {
            net.broadcastVehicleOccupancy(info.characterId, "", info.ownerPeerId, false);
        }
    }

    /**
     * Client-side MSG_VEHICLE_OCCUPANCY apply — every peer (including the requester) runs the
     * seat change locally from the host's authoritative event. Idempotent on purpose: the ~1 Hz
     * occupancy sweep re-sends current state as a self-heal backstop, so re-applying what this
     * peer already shows must be a no-op (plus ownership convergence, which is just a field write).
     */
    public void applyVehicleOccupancy(String vehicleId, String occupantCharacterId, int ownerPeerId, boolean entering) {
        com.vehicle.Vehicle vehicle = findVehicleById(vehicleId);
        if (vehicle == null || vehicle.getCharacterInfo() == null) {
            GD.print("GameManager: VEHICLE_OCCUPANCY apply failed — no vehicle '" + vehicleId + "'");
            return;
        }
        vehicle.getCharacterInfo().ownerPeerId = ownerPeerId;
        if (entering) {
            Character character = findCharacterById(occupantCharacterId);
            if (character == null) {
                // Body not spawned here yet (cross-ordering with a spawn we haven't applied) —
                // ownership still converged above; the occupancy sweep retries within ~1 s.
                GD.print("GameManager: VEHICLE_OCCUPANCY enter for unknown character "
                        + occupantCharacterId + " — waiting for spawn (sweep will retry)");
                vehicle.applyAuthorityState();
            } else if (vehicle.getOccupant() != character) {
                if (vehicle.getOccupant() != null) vehicle.tryExit();   // diverged seat — self-heal
                // Authority first (see processVehicleSeatRequest): on the requester this frees
                // the puppet controller — seeding coast velocities — before the live hot-swap.
                vehicle.applyAuthorityState();
                vehicle.tryEnter(character);
            } else {
                vehicle.applyAuthorityState();   // already seated — ownership converge only
            }
        } else {
            if (vehicle.getOccupant() != null) vehicle.tryExit();
            vehicle.applyAuthorityState();
        }
    }

    /** Instantiates a fresh Player body owned by {@code peerId}, stamped with the rejoinable characterId, and announces it to every connected peer. */
    private void spawnPlayerBody(int peerId, String characterId) {
        Node container = resolveCharactersContainer();
        if (container == null) {
            GD.print("GameManager: Characters container not found — cannot spawn player body");
            return;
        }

        Object loaded = GD.load(PLAYER_SCENE_PATH);
        if (!(loaded instanceof PackedScene playerScene)) {
            GD.print("GameManager: failed to load " + PLAYER_SCENE_PATH);
            return;
        }

        Node instance = playerScene.instantiate();
        if (!(instance instanceof Player player)) {
            instance.queueFree();
            return;
        }

        CharacterInfo info = new CharacterInfo();
        info.characterId = characterId;
        info.displayName = "Player " + peerId;
        info.faction = Faction.PLAYER;
        info.ownerPeerId = peerId;
        player.characterInfo = info;

        container.addChild(player);
        // Player.tscn ships with a live PlayerController — correct for the human at this
        // machine, wrong for a body spawned on behalf of a remote peer. Under ownership-based
        // authority the owning client simulates its own body and reports state upstream; on the
        // host this body is a NetworkController puppet driven by those reports (interpolated),
        // never re-simulated here. Health stays host-authoritative (NetworkController.receiveSnapshot
        // applyHealth gate). The owning client itself gets a live PlayerController via
        // spawnReplicatedCharacter's isAuthorityFor branch.
        player.attachController(new NetworkController());
        // Player.tscn carries no transform of its own (defaults to the scene origin) —
        // the same point World.tscn's pre-placed Player sits at. Spawning there stacks
        // the two CharacterBody3Ds, and physics shoves the new one to an arbitrary
        // overlap-resolution position (observed: airborne / inside the vehicle).
        // Randomize within the populated area, mirroring DebugHarness.spawnTestAI's
        // exact range, so joining players land somewhere sensible and distinct.
        player.setGlobalPosition(new Vector3(
                GD.randfRange(-12.0f, 18.0f),
                0.9f,
                GD.randfRange(-12.0f, 8.0f)));
        GD.print("GameManager: spawned new body for peer " + peerId + " (characterId=" + characterId + ")");

        NetworkManager net = getNetworkManager();
        if (net != null) net.announceSpawn(player);
    }

    /**
     * Client-side: instantiate a server-announced character — MSG_SPAWN's receiving
     * side (NetworkManager.handleSpawnMessage). Mirrors spawnPlayerBody's load/
     * instantiate/stamp/addChild shape, generic over the scene selector so it covers
     * both remote players and server-spawned AI (folds in the previously-approved G3
     * MultiplayerSpawner follow-up — see NETWORK_REWRITE_PLAN.md Phase 7).
     */
    public void spawnReplicatedCharacter(NetMessageCodec.DecodedSpawn spawn) {
        if (findCharacterById(spawn.characterId()) != null) return;

        Node container = resolveCharactersContainer();
        if (container == null) {
            GD.print("GameManager: Characters container not found — cannot spawn replicated character " + spawn.characterId());
            return;
        }

        String scenePath = spawn.sceneSelector() == NetMessageCodec.SCENE_PLAYER ? PLAYER_SCENE_PATH : AI_SCENE_PATH;
        Object loaded = GD.load(scenePath);
        if (!(loaded instanceof PackedScene scene)) {
            GD.print("GameManager: failed to load " + scenePath);
            return;
        }

        Node instance = scene.instantiate();
        if (!(instance instanceof Character character)) {
            instance.queueFree();
            return;
        }

        CharacterInfo info = new CharacterInfo();
        info.characterId = spawn.characterId();
        info.displayName = spawn.displayName();
        info.faction = spawn.faction();
        info.ownerPeerId = spawn.ownerPeerId();
        character.characterInfo = info;

        // addChild BEFORE attachController — mirrors spawnPlayerBody. Character._ready()
        // (which fires on addChild, never during instantiate()) is what populates the
        // cached `controller` field by scanning getChildren(); calling attachController
        // first leaves `controller` null, so its `removeChild(controller)` guard never
        // fires (the scene's original controller stays attached) and the subsequent
        // _ready() re-scan then overwrites `controller` back to that original — leaving
        // the real NetworkController orphaned and uncached. Adding the child first lets
        // attachController's swap-and-cache do its job correctly.
        container.addChild(character);
        character.setGlobalPosition(spawn.position());

        // The instantiated scene ships with a locally-driving controller
        // (PlayerController/CharacterController) — correct only for bodies *we*
        // drive (ownerPeerId == our localPeerId, e.g. the body the server just
        // spawned for us). Every other replicated body must be swapped to
        // NetworkController so it is driven solely by MSG_SNAPSHOT instead of
        // fighting a live local controller — see NetworkController's class doc.
        NetworkManager net = getNetworkManager();
        if (net == null || !net.isAuthorityFor(info)) {
            character.attachController(new NetworkController());
        }
        GD.print("GameManager: spawned replicated character " + spawn.characterId()
                + " (scene selector " + spawn.sceneSelector() + ")");
    }

    /** Client-side: remove a server-despawned entity (Character or Vehicle) — MSG_DESPAWN's receiving side (NetworkManager.handleDespawnMessage). */
    public void despawnReplicatedCharacter(String characterId) {
        if (getTree() == null) return;
        for (Node node : getTree().getNodesInGroup(CHARACTERS_GROUP)) {
            if (node instanceof com.character.Controllable c && c.getCharacterInfo() != null
                    && characterId.equals(c.getCharacterInfo().characterId)) {
                // Never free an occupied vehicle outright: if the occupancy-exit event was
                // missed/raced, the seated character's controller is a CHILD of this node and
                // would be freed with it — a permanently stuck (and crash-prone) body. tryExit
                // recovers the controller and drive state first; harmless if already vacant.
                if (node instanceof com.vehicle.Vehicle vehicle && vehicle.getOccupant() != null) {
                    vehicle.tryExit();
                }
                node.queueFree();
                return;
            }
        }
    }

    /**
     * Host-side entry point for removing a replicated entity: announce the despawn FIRST
     * (announceDespawn previously had no callers — clients kept freed entities forever),
     * then free locally. The seam Round 11 N3 vehicle destruction and any future corpse
     * cleanup go through; harmless in single-player (announce no-ops). Entity-generic —
     * {@code entity} is the Node to free, {@code info} carries the replicated id.
     */
    public void despawnAuthoritative(Node entity, CharacterInfo info) {
        if (entity == null) return;
        NetworkManager net = getNetworkManager();
        if (net != null && net.isNetworked() && net.isServer() && info != null) {
            net.announceDespawn(info.characterId);
        }
        entity.queueFree();
    }

    /** Character overload — keeps existing N2 call sites untouched. */
    public void despawnAuthoritative(Character character) {
        if (character == null) return;
        despawnAuthoritative(character, character.characterInfo);
    }

    // ── Reliable elimination + inventory reconciliation (Round 11 N2) ─────────

    /**
     * Client-side MSG_ELIMINATION apply (NetworkManager.handleEliminationMessage): force the
     * victim dead immediately (reliable path — no waiting on an unreliable health==0
     * snapshot) and re-emit the elimination on the local EventBus so the kill feed
     * (HUDManager), mission progress (MissionManager), and the all-players-dead GAME_OVER
     * tracking (onCharacterDied above) behave identically on every peer. The weaponIcon
     * Texture2D never crosses the wire — it's resolved locally by the source name from
     * IconRegistry (every peer ships the same weapon/vehicle scenes), so the client kill
     * feed shows the same icon the host does. An unregistered source resolves to null,
     * which the feed already tolerates.
     */
    public void applyReplicatedElimination(NetMessageCodec.DecodedElimination elim) {
        Character victim = findCharacterById(elim.victimCharacterId());
        NetworkManager net = getNetworkManager();
        if (victim == null) {
            com.game.net.NetStats.increment("elimination_unknown_victim");
            GD.print("GameManager: MSG_ELIMINATION for unknown victim " + elim.victimCharacterId());
        } else {
            Node healthNode = victim.getNodeOrNull("Health");
            if (healthNode instanceof com.character.Health health) health.applyReplicatedHealth(0f);
            if (victim.getController() instanceof NetworkController nc) {
                nc.forceReplicatedDeath();
            } else if (net != null && net.isAuthorityFor(victim.characterInfo)) {
                // Our own body: the host owns our health, so our death arrives here rather
                // than through Health.applyDamage → died → onDied. Player overrides
                // applyReplicatedDeath to also run the player-death UI path.
                victim.applyReplicatedDeath();
            }
        }
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            godot.api.Texture2D weaponIcon = com.character.IconRegistry.get(elim.weaponName());
            bus.characterEliminated.emit(elim.attackerName(), elim.attackerFaction(),
                    elim.victimName(), elim.victimFaction(), elim.weaponName(), weaponIcon, elim.headshot());
            if (victim != null && victim.characterInfo != null) bus.characterDied.emit(victim.characterInfo);
        }
    }

    /**
     * Client-side MSG_INVENTORY apply (NetworkManager.handleInventoryMessage): reconcile the
     * character's WeaponController toward the host's manifest. Bodies this peer owns get the
     * add-only treatment (heal a lost grant, never fight the owner's live inventory) — see
     * WeaponController.applyReplicatedInventory.
     */
    public void applyReplicatedInventory(NetMessageCodec.DecodedInventory inv) {
        Character character = findCharacterById(inv.characterId());
        if (character == null) {
            com.game.net.NetStats.increment("inventory_unknown_character");
            return;
        }
        Node wcNode = character.getNodeOrNull("WeaponController");
        if (!(wcNode instanceof com.character.WeaponController wc)) return;
        NetworkManager net = getNetworkManager();
        boolean addOnly = net != null && net.isAuthorityFor(character.characterInfo);
        wc.applyReplicatedInventory(inv.entries(), addOnly);
    }

    // ── World-state event seam (Round 8 Step 4) ───────────────────────────────
    //
    // Single client-side entry point for host-authoritative world events
    // (NetworkManager.handleWorldEventMessage → here). The host applies each change locally when it
    // occurs and broadcasts it via NetworkManager.broadcastWorldEvent; clients receive it here and
    // route by eventType to the system that owns it — the scaffold doors / mission / story / the
    // spawn director register their cases on as those features become networked. Kept deliberately
    // small (eventType + key + scalar) so adding a new networked world fact is "add a constant +
    // a case", never a new message/codec/handler.

    /** A character (key = characterId) refilled at an AmmoRefill station — host-detected, mirrored on every peer. */
    public static final int WORLD_EVENT_AMMO_REFILL = 1;

    /** A vehicle (key = vehicleId) was destroyed — every peer plays the same wreck cosmetics (Round 11 N3); the despawn follows on the same ordered channel. */
    public static final int WORLD_EVENT_VEHICLE_WRECK = 2;

    /** Mission started — key = missionId, args = [objectiveType]. Host MissionManager broadcasts; clients re-emit EventBus.missionStarted for the HUD banner. */
    public static final int WORLD_EVENT_MISSION_STARTED = 3;

    /** Mission completed — key = missionId, args = [winningFaction, outcomeVariant]. */
    public static final int WORLD_EVENT_MISSION_COMPLETED = 4;

    /** Mission failed — key = missionId, args = [reason]. */
    public static final int WORLD_EVENT_MISSION_FAILED = 5;

    /** Routes a decoded MSG_WORLD_EVENT to the owning system. Extend the switch as networked world state is added. */
    public void onWorldEvent(int eventType, String key, float value, java.util.List<String> args) {
        switch (eventType) {
            case WORLD_EVENT_AMMO_REFILL -> applyAmmoRefill(key);
            case WORLD_EVENT_VEHICLE_WRECK -> applyVehicleWreck(key);
            case WORLD_EVENT_MISSION_STARTED -> applyMissionStarted(key, args);
            case WORLD_EVENT_MISSION_COMPLETED -> applyMissionCompleted(key, args);
            case WORLD_EVENT_MISSION_FAILED -> applyMissionFailed(key, args);
            // case WORLD_EVENT_DOOR -> applyDoorState(key, value);
            default -> GD.print("GameManager: unhandled world event type " + eventType + " key=" + key);
        }
    }

    /** Safe positional read from a world-event args list — empty string for a missing index (a client must never index past a short/garbage frame). */
    private static String arg(java.util.List<String> args, int index) {
        return args != null && index < args.size() && args.get(index) != null ? args.get(index) : "";
    }

    // Mission lifecycle is host-authoritative (MissionManager runs/tracks only there). On clients we
    // re-emit the matching EventBus signal so the HUD banner and any listener behave identically to
    // the host — but we never re-run host-only tracking (countHostilesByFaction); clients are pure
    // mirrors of mission state.

    private void applyMissionStarted(String missionId, java.util.List<String> args) {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.missionStarted.emit(missionId, arg(args, 0));
    }

    private void applyMissionCompleted(String missionId, java.util.List<String> args) {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.missionCompleted.emit(missionId, arg(args, 0), arg(args, 1));
    }

    private void applyMissionFailed(String missionId, java.util.List<String> args) {
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.missionFailed.emit(missionId, arg(args, 0));
    }

    /**
     * Mirrors a host-confirmed vehicle destruction's COSMETICS on this peer (explosion VFX +
     * wreck scene — never damage: the host already applied that authoritatively and clients
     * relaying explosion damage would double-apply it). The node removal arrives separately
     * as MSG_DESPAWN right behind this event on the same ordered channel.
     */
    private void applyVehicleWreck(String vehicleId) {
        com.vehicle.Vehicle vehicle = findVehicleById(vehicleId);
        if (vehicle != null) vehicle.playWreckCosmetics();
    }

    /** Mirrors a host-confirmed ammo refill onto this peer's copy of the character. */
    private void applyAmmoRefill(String characterId) {
        Character character = findCharacterById(characterId);
        if (character == null) return;
        Node wcNode = character.getNodeOrNull("WeaponController");
        if (wcNode instanceof com.character.WeaponController wc) wc.fillWeaponAmmo();
    }

    /**
     * Client-side: the host vanished (NetworkManager.onHostLost already tore the dead session
     * down — isNetworked() is false here). Surface a recovery prompt so the player can restart
     * into single-player rather than sitting frozen against stale puppets. The restart path
     * (MenuManager.restart → restartLevel) reloads the scene into a fresh single-player world.
     */
    public void onHostLost(String reason) {
        GD.print("GameManager: host lost — " + reason);
        if (currentState == GameState.PLAYING) transitionTo(GameState.GAME_OVER);
        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) bus.connectionLost.emit(reason);
    }

    private void transitionTo(GameState next) {
        GD.print("GameManager: " + currentState + " → " + next);
        currentState = next;
    }
}
