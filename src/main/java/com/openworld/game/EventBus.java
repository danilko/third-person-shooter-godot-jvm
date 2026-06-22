package com.openworld.game;

import com.openworld.character.CharacterInfo;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterSignal;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.Signal0;
import godot.core.Signal1;
import godot.core.Signal2;
import godot.core.Signal3;
import godot.core.Signal4;
import godot.core.Signal7;
import godot.core.StringName;
import godot.core.Vector3;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.mission.MissionManager;
import com.openworld.item.AmmoRefill;
import com.openworld.item.Pickup;
import com.openworld.net.NetworkManager;
import com.openworld.ui.HUDManager;
import com.openworld.ui.MenuManager;
import com.openworld.weapon.WeaponController;

/**
 * Global event bus — registered as an AutoLoad singleton named "EventBus".
 *
 * Any node in the game can reach it via:
 *   EventBus bus = (EventBus) getNode("/root/EventBus");
 *
 * Emit side:  bus.enemyKilled.emit();
 * Listen side: bus.enemyKilled.connect(this::onEnemyKilled);
 *
 * AutoLoad entry (add to project.godot after running ./gradlew build):
 *   [autoload]
 *   EventBus="*res://gdj/com/game/EventBus.gdj"
 */
@RegisterClass(className = "EventBus")
public class EventBus extends Node {

    /**
     * Emitted by Player.onDied() for EVERY Player death — including a co-op teammate's
     * (each peer holds a Player puppet for every human, so this fires once per body that
     * dies on every peer). It is therefore NOT a session-ending signal: use it only for
     * per-player effects (death cam, future respawn/spectate). The session-ending
     * game-over screen is driven by {@link #allPlayersDied} instead.
     */
    @RegisterSignal
    public final Signal0 playerDied = new Signal0(this, new StringName("player_died"));

    /**
     * Emitted by GameManager once EVERY tracked Player character has died (the co-op
     * "all players down" condition — see GameManager.onCharacterDied). This — not the
     * per-body {@link #playerDied} — is what surfaces the session-ending game-over screen,
     * so a single teammate's death no longer kicks the whole session (including the host)
     * to the restart menu.
     */
    @RegisterSignal
    public final Signal0 allPlayersDied = new Signal0(this, new StringName("all_players_died"));

    /**
     * Emitted by Player once after _ready() completes (deferred so all sibling
     * _ready() callbacks — including HUDManager — finish connecting first).
     * HUDManagers subscribe to this instead of relying on a scene-path export
     * so they work unchanged regardless of where the Player lives in the tree.
     */
    @RegisterSignal
    public final Signal1<Node> playerSpawned = new Signal1<>(this, new StringName("player_spawned"));

    /** Emitted by Enemy.onDied(). Payload: the enemy's score value. */
    @RegisterSignal
    public final Signal1<Integer> enemyKilled = new Signal1<>(this, new StringName("enemy_killed"));

    /** Emitted by Health.takeDamage() for the player character. Payload: new currentHealth. */
    @RegisterSignal
    public final Signal1<Float> playerHealthChanged = new Signal1<>(this, new StringName("player_health_changed"));

    /** Emitted by AmmoRefill.onBodyEntered(). Payload: weapon index that was refilled. */
    @RegisterSignal
    public final Signal1<Integer> ammoPickedUp = new Signal1<>(this, new StringName("ammo_picked_up"));

    /**
     * Emitted by Health when any character is eliminated.
     * Payload: attackerName, attackerFaction, victimName, victimFaction, weaponName, weaponIcon, headshot.
     */
    @RegisterSignal
    public final Signal7<String, String, String, String, String, Texture2D, Boolean> characterEliminated =
            new Signal7<>(this, new StringName("character_eliminated"));

    /**
     * Emitted by Pickup when a character enters or leaves interact range.
     * Payload: inRange, itemLabel (empty string when leaving).
     */
    @RegisterSignal
    public final Signal2<Boolean, String> pickupInteractChanged =
            new Signal2<>(this, new StringName("pickup_interact_changed"));

    /**
     * Emitted by HUDManager when the active player's ammo state changes.
     * Payload: magazine (current loaded rounds), reserve (unloaded backup rounds).
     */
    @RegisterSignal
    public final Signal2<Integer, Integer> playerAmmoChanged =
            new Signal2<>(this, new StringName("player_ammo_changed"));

    /**
     * Emitted by WeaponController when a weapon is equipped from the world.
     * Payload: characterId (picker), weaponName, weaponIcon.
     */
    @RegisterSignal
    public final Signal3<String, String, Texture2D> weaponPickedUp =
            new Signal3<>(this, new StringName("weapon_picked_up"));

    /**
     * Emitted by Vehicle.tryEnter() when a character boards a vehicle.
     * Payload: vehicle node, occupant CharacterInfo.
     * Passing CharacterInfo (data) rather than the Character node keeps signal
     * recipients decoupled from the live character object — same principle as
     * characterEliminated. Recipients filter on occupantInfo.characterId.
     */
    @RegisterSignal
    public final Signal2<Node, CharacterInfo> vehicleEntered =
            new Signal2<>(this, new StringName("vehicle_entered"));

    /**
     * Emitted by Vehicle.tryExit() when the occupant leaves the vehicle.
     * Payload: occupant CharacterInfo — same filter as vehicleEntered.
     */
    @RegisterSignal
    public final Signal1<CharacterInfo> vehicleExited =
            new Signal1<>(this, new StringName("vehicle_exited"));

    /**
     * Emitted by WeaponController when the active slot crosses the fist/weapon boundary.
     * Payload: the character node + true when a real weapon is now drawn, false when fist is active.
     * Neutral NPCs listen to this to decide when to turn hostile.
     */
    @RegisterSignal
    public final Signal2<Node, Boolean> armedStateChanged =
            new Signal2<>(this, new StringName("armed_state_changed"));

    /**
     * Emitted by MissionManager.startMission().
     * Payload: missionId, objectiveType — lets HUD show a "mission started" banner.
     */
    @RegisterSignal
    public final Signal2<String, String> missionStarted =
            new Signal2<>(this, new StringName("mission_started"));

    /**
     * Emitted by MissionManager.completeMission().
     * Payload: missionId, winningFaction, outcomeVariant.
     */
    @RegisterSignal
    public final Signal3<String, String, String> missionCompleted =
            new Signal3<>(this, new StringName("mission_completed"));

    /**
     * Emitted by MissionManager.failMission().
     * Payload: missionId, reason.
     */
    @RegisterSignal
    public final Signal2<String, String> missionFailed =
            new Signal2<>(this, new StringName("mission_failed"));

    /**
     * Emitted by Character once after _ready() completes (deferred, mirrors
     * playerSpawned). Fires for every character — player and AI alike — so
     * GameManager and HUDManager can build characterId-keyed registries instead
     * of assuming a single local player.
     * Payload: the spawned character node + its CharacterInfo.
     */
    @RegisterSignal
    public final Signal2<Node, CharacterInfo> characterSpawned =
            new Signal2<>(this, new StringName("character_spawned"));

    /**
     * Emitted by Health when its owning character dies (alongside characterEliminated).
     * Payload: the victim's CharacterInfo — recipients filter by characterId.
     */
    @RegisterSignal
    public final Signal1<CharacterInfo> characterDied =
            new Signal1<>(this, new StringName("character_died"));

    /**
     * Emitted by Health.takeDamage()/heal() for any character (not just the player).
     * Payload: CharacterInfo of the owner + the new current health.
     */
    @RegisterSignal
    public final Signal2<CharacterInfo, Float> characterHealthChanged =
            new Signal2<>(this, new StringName("character_health_changed"));

    /**
     * Emitted by WeaponController for any character (not just the player).
     * Payload: CharacterInfo of the owner + magazine + reserve.
     */
    @RegisterSignal
    public final Signal3<CharacterInfo, Integer, Integer> characterAmmoChanged =
            new Signal3<>(this, new StringName("character_ammo_changed"));

    /**
     * Emitted by Character while swimming (PLAN.md I1 — breath/oxygen) for any character.
     * Payload: CharacterInfo of the owner + current oxygen (s) + max oxygen (s). HUDManager
     * filters to the active player and re-emits {@link #playerOxygenChanged}.
     */
    @RegisterSignal
    public final Signal3<CharacterInfo, Float, Float> characterOxygenChanged =
            new Signal3<>(this, new StringName("character_oxygen_changed"));

    /**
     * Active-player oxygen, relayed by HUDManager (the swim breath meter). Payload: current
     * oxygen (s) + max oxygen (s). CharacterHUD shows the meter while submerged, hides it at full.
     */
    @RegisterSignal
    public final Signal2<Float, Float> playerOxygenChanged =
            new Signal2<>(this, new StringName("player_oxygen_changed"));

    /**
     * Emitted by GameManager.onHostLost() on a client whose host vanished
     * (NetworkManager detected it via DISCONNECT or the no-packet watchdog).
     * Payload: a short human-readable reason. MenuManager surfaces the recovery
     * prompt (restart / quit) — the session has already been torn down by then.
     */
    @RegisterSignal
    public final Signal1<String> connectionLost =
            new Signal1<>(this, new StringName("connection_lost"));

    /**
     * Emitted when a character takes damage that has a known world-space source — drives the HUD
     * damage-direction indicator. Payload: victim CharacterInfo + the attacker's world position.
     * Emitted authority/single-player side from {@code Health.applyDamage}, and on a networked
     * client from {@code NetworkManager.handleDamageBroadcastMessage} (attacker resolved by id).
     * HUDManager filters to the local player and forwards the bearing to {@code DamageIndicator}.
     * Not emitted for sourceless damage (fall, world hazards) — those carry no direction.
     */
    @RegisterSignal
    public final Signal2<CharacterInfo, Vector3> characterDamagedFrom =
            new Signal2<>(this, new StringName("character_damaged_from"));

}
