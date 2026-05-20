package com.ui;

import com.character.Character;
import com.character.CombatState;
import com.character.Health;
import com.character.Player;
import com.character.WeaponController;
import com.character.CharacterInfo;
import com.game.EventBus;
import com.vehicle.Vehicle;
import com.vehicle.VehicleWeaponMode;
import godot.api.Node3D;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.CanvasLayer;
import godot.api.Control;
import godot.api.Node;
import godot.api.Object;
import godot.api.PackedScene;
import godot.api.Texture2D;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.StringNames;
import godot.global.GD;

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

  /** Name of the HUD child to show on startup. */
  @RegisterProperty @Export
  public String initialHUD = "FootHUD";

  /** Path to the WeaponRadialMenu child (relative to this node). Set empty to skip wiring. */
  @RegisterProperty @Export
  public NodePath radialMenuPath = new NodePath("WeaponRadialMenu");

  /** Scene for {@link DefeatedFeedEntry} rows. Falls back to hard-coded path if null. */
  @RegisterProperty @Export
  public PackedScene defeatedEntryScene;

  private static final String DEFEATED_ENTRY_SCENE_PATH =
          "res://src/main/resources/com/ui/DefeatedFeedEntry.tscn";

  private Control   activeHUD;
  private Node      player;
  private String    playerCharacterId = "";
  private Crosshair crosshair;
  private Feed      feed;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _ready() {
    // Scan children for the Feed — must be a direct child of HUDManager so it
    // stays visible across HUD context switches (FootHUD ↔ VehicleHUD).
    for (Node child : getChildren()) {
      if (child instanceof Feed f) { feed = f; break; }
    }

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      // playerSpawned fires deferred from Player._ready() so this connection
      // is always in place before the signal arrives, regardless of tree order.
      bus.playerSpawned.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPlayerSpawned")),
          Object.ConnectFlags.DEFAULT);
      bus.vehicleEntered.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onVehicleEntered")),
          Object.ConnectFlags.DEFAULT);
      bus.vehicleExited.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onVehicleExited")),
          Object.ConnectFlags.DEFAULT);
      bus.characterEliminated.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onCharacterEliminated")),
          Object.ConnectFlags.DEFAULT);
    }

    // Cache the crosshair — it lives as a sibling of FootHUD/VehicleHUD so it
    // persists across HUD context switches.
    Node ch = getNodeOrNull("Crosshair");
    if (ch instanceof Crosshair c) crosshair = c;

    if (!initialHUD.isEmpty()) activateHUD(initialHUD);
  }

  @RegisterFunction
  public void onPlayerSpawned(Node spawnedPlayer) {
    wirePlayer(spawnedPlayer);
  }

  @RegisterFunction
  public void onPlayerCombatStateChanged(CombatState state) {
    if (crosshair != null) crosshair.setShowCrosshair(state.isCombat());
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
    playerCharacterId = (newPlayer instanceof Character c && c.characterInfo != null)
            ? c.characterInfo.characterId : "";

    Node wcNode = player.getNodeOrNull("WeaponController");
    if (wcNode instanceof WeaponController wc) {
      wc.ammoChanged.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPlayerAmmoChanged")),
          Object.ConnectFlags.DEFAULT);
      // Wire crosshair spread source once — self-managed from here on.
      if (crosshair != null) crosshair.weaponController = wc;
    }

    // Drive crosshair visibility from the player's combat-state changes.
    if (newPlayer instanceof Character c) {
      c.changedCombatState.connectUnsafe(
          Callable.createUnsafe(this, StringNames.toGodotName("onPlayerCombatStateChanged")),
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
    wireCharacterHUD(newPlayer);
  }

  private void wireCharacterHUD(Node newPlayer) {
    if (!(newPlayer instanceof Character c)) return;
    CharacterInfo info = c.characterInfo;
    if (info == null) return;
    for (Node child : getChildren()) {
      if (child instanceof CharacterHUD hud) hud.setPlayerCharacterId(info.characterId);
    }
  }

  private void wireWeaponRadialMenu(Node newPlayer, Node wcNode) {
    if (radialMenuPath == null || radialMenuPath.isEmpty()) return;
    Node rmNode = getNodeOrNull(radialMenuPath);
    if (!(rmNode instanceof WeaponRadialMenu rm)) return;
    if (newPlayer instanceof Character c) rm.wireCharacter(c);
  }

  public Control getActiveHUD() { return activeHUD; }

  // ── Vehicle HUD switching ─────────────────────────────────────────────────

  @RegisterFunction
  public void onVehicleEntered(Node vehicle, CharacterInfo occupantInfo) {
    if (occupantInfo == null || !playerCharacterId.equals(occupantInfo.characterId)) return;
    Node vhudNode = getNodeOrNull("VehicleHUD");
    if (vhudNode instanceof VehicleHUD hud && vehicle instanceof Node3D v) {
      hud.setVehicle(v);
    }
    activateHUD("VehicleHUD");
    // VEHICLE_WEAPON: combat state is not forced on (no character weapon), but the
    // vehicle fires its own gun — show crosshair with fixed spread (null weapon controller).
    if (crosshair != null && vehicle instanceof Vehicle v
            && v.getWeaponMode() == VehicleWeaponMode.VEHICLE_WEAPON) {
      crosshair.weaponController = null;
      crosshair.setShowCrosshair(true);
    }
  }

  @RegisterFunction
  public void onVehicleExited(CharacterInfo occupantInfo) {
    if (occupantInfo == null || !playerCharacterId.equals(occupantInfo.characterId)) return;
    Node vhudNode = getNodeOrNull("VehicleHUD");
    if (vhudNode instanceof VehicleHUD hud) hud.setVehicle(null);
    activateHUD("FootHUD");
    // Restore crosshair weapon controller and visibility from the player's state.
    if (crosshair != null) {
      Node wcNode = player != null ? player.getNodeOrNull("WeaponController") : null;
      crosshair.weaponController = wcNode instanceof WeaponController wc ? wc : null;
      boolean inCombat = player instanceof Character c && c.combat;
      crosshair.setShowCrosshair(inCombat);
    }
  }

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

  /** Push a {@link DefeatedFeedEntry} row to the kill feed for any character elimination. */
  @RegisterFunction
  public void onCharacterEliminated(String attackerName, String attackerFaction,
                                    String victimName,   String victimFaction,
                                    String weaponName,   Texture2D weaponIcon,
                                    boolean headshot) {
    if (feed == null) return;
    PackedScene scene = resolveDefeatedEntryScene();
    if (scene == null) return;
    DefeatedFeedEntry entry = (DefeatedFeedEntry) scene.instantiate();
    entry.lifespan = feed.entryLifespan;
    feed.push(entry);
    entry.populate(attackerName, attackerFaction, victimName, victimFaction, weaponIcon, headshot);
  }

  private PackedScene resolveDefeatedEntryScene() {
    if (defeatedEntryScene != null) return defeatedEntryScene;
    godot.api.Object loaded = GD.load(DEFEATED_ENTRY_SCENE_PATH);
    return (loaded instanceof PackedScene ps) ? ps : null;
  }
}
