package com.game;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterSignal;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.Signal0;
import godot.core.Signal1;
import godot.core.Signal2;
import godot.core.Signal3;
import godot.core.Signal4;
import godot.core.Signal5;
import godot.core.Signal7;
import godot.core.StringName;

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

    /** Emitted by Player.onDied(). Payload: none — the player is a singleton. */
    @RegisterSignal
    public final Signal0 playerDied = new Signal0(this, new StringName("player_died"));

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
}
