package com.ui;

import com.character.Character;
import com.character.Health;
import com.character.Player;
import com.character.WeaponController;
import com.game.EventBus;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.CanvasLayer;
import godot.api.Control;
import godot.api.Node;
import godot.api.Object;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringNames;

/**
 * World-level HUD manager. Lives as a CanvasLayer in World.tscn so all HUD
 * scenes render on top of the game world regardless of camera.
 *
 * Responsibilities:
 *  1. Relay active player's local signals (ammoChanged, Health.damaged) to
 *     EventBus so HUDs remain completely decoupled from the player node.
 *  2. Switch between HUD contexts (foot, vehicle, ...) by showing/hiding
 *     named child Control nodes.
 *
 * Scene setup:
 *   HUDManager (CanvasLayer, script = HUDManager.gdj)
 *     FootHUD  (CharacterHUD scene)
 *     VehicleHUD (future)
 *
 * To switch HUD context at runtime call activateHUD("VehicleHUD").
 */
@RegisterClass(className = "HUDManager")
public class HUDManager extends CanvasLayer {

  /** Path to the player node whose signals this manager relays. */
  @RegisterProperty @Export
  public NodePath playerPath = new NodePath("../Player");

  /** Name of the HUD child to show on startup. */
  @RegisterProperty @Export
  public String initialHUD = "FootHUD";

  /** Path to the WeaponRadialMenu child (relative to this node). Set empty to skip wiring. */
  @RegisterProperty @Export
  public NodePath radialMenuPath = new NodePath("WeaponRadialMenu");

  private Control activeHUD;
  private Node player;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _ready() {
    Node found = getNodeOrNull(playerPath);
    if (found != null) wirePlayer(found);

    if (!initialHUD.isEmpty()) activateHUD(initialHUD);
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Switch to the named HUD child (e.g. "FootHUD", "VehicleHUD").
   * Hides the current HUD and shows the new one.
   */
  public void activateHUD(String name) {
    Node child = getNodeOrNull(new NodePath(name));
    if (child instanceof Control c) setActiveHUD(c);
  }

  /**
   * Wire a new player node's signals to the EventBus relay and configure all
   * HUD children that need player references (WeaponRadialMenu etc.).
   * Call this when the player respawns or a different character takes control.
   */
  public void wirePlayer(Node newPlayer) {
    player = newPlayer;

    Node wcNode = player.getNodeOrNull("WeaponController");
    if (wcNode instanceof WeaponController wc) {
      wc.ammoChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPlayerAmmoChanged")),
          Object.ConnectFlags.DEFAULT);
    }

    Node healthNode = player.getNodeOrNull("Health");
    if (healthNode instanceof Health h) {
      h.damaged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPlayerHealthDamaged")),
          Object.ConnectFlags.DEFAULT);
      emitHealth(h.getCurrentHealth());
    }

    wireWeaponRadialMenu(newPlayer, wcNode);
  }

  private void wireWeaponRadialMenu(Node newPlayer, Node wcNode) {
    if (radialMenuPath == null || radialMenuPath.isEmpty()) return;
    Node rmNode = getNodeOrNull(radialMenuPath);
    if (!(rmNode instanceof WeaponRadialMenu rm)) return;
    if (newPlayer instanceof Character c) rm.wireCharacter(c);
  }

  public Control getActiveHUD() { return activeHUD; }

  // ── Signal relays — player → EventBus ─────────────────────────────────────

  @RegisterFunction
  public void onPlayerAmmoChanged(int magazine, int reserve) {
    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) bus.playerAmmoChanged.emit(magazine, reserve);
  }

  @RegisterFunction
  public void onPlayerHealthDamaged(float damage) {
    if (player == null) return;
    Node healthNode = player.getNodeOrNull("Health");
    if (healthNode instanceof Health h) emitHealth(h.getCurrentHealth());
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private void setActiveHUD(Control hud) {
    if (activeHUD != null) activeHUD.hide();
    activeHUD = hud;
    if (activeHUD != null) activeHUD.show();
  }

  private void emitHealth(float currentHealth) {
    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) bus.playerHealthChanged.emit(currentHealth);
  }
}
