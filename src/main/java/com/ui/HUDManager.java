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
import godot.api.Label;
import godot.api.Node;
import godot.api.Object;
import godot.api.PackedScene;
import godot.api.Texture2D;
import godot.api.Timer;
import godot.core.Callable;
import godot.core.HorizontalAlignment;
import godot.core.NodePath;
import godot.core.StringNames;
import godot.core.Vector2;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;

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

  private Control        activeHUD;
  private Node           player;
  private String         playerCharacterId = "";
  private Crosshair      crosshair;
  private Feed           feed;
  private WeaponSlotsUI  weaponSlotsUI;

  /** Top-of-screen mission status banner — built at runtime, hidden until a mission event fires. */
  private Label          missionBanner;
  private Timer          missionBannerTimer;
  private static final double MISSION_BANNER_DURATION = 4.0;

  /**
   * characterId → HUD widget registry (C2: multi-character HUD wiring).
   * Lets any character — not just the local player — have a dedicated HUD widget
   * (e.g. squad/escort overlays, future co-op split screens) that automatically
   * receives that character's health/ammo/death events. Purely additive: the
   * single-player FootHUD/playerCharacterId flow below is untouched.
   */
  private final Map<String, Node> characterHUDs = new HashMap<>();

  /** Register a HUD widget to receive health/ammo/death events for the given character. */
  public void registerCharacterHUD(String characterId, Node hudWidget) {
	if (characterId == null || characterId.isEmpty() || hudWidget == null) return;
	characterHUDs.put(characterId, hudWidget);
  }

  /** Stop routing events for the given character to its registered HUD widget. */
  public void unregisterCharacterHUD(String characterId) {
	if (characterId == null) return;
	characterHUDs.remove(characterId);
  }

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

	  // C2 — multi-character HUD wiring: route per-character events to whichever
	  // widget (if any) is registered for that characterId via registerCharacterHUD().
	  bus.characterHealthChanged.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onCharacterHealthChanged")),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterAmmoChanged.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onCharacterAmmoChanged")),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterDied.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onCharacterDiedHud")),
		  Object.ConnectFlags.DEFAULT);

	  // C1 — mission status banner: surfaces start/complete/fail events that were
	  // previously only visible via GD.print in the console.
	  bus.missionStarted.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onMissionStarted")),
		  Object.ConnectFlags.DEFAULT);
	  bus.missionCompleted.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onMissionCompletedHud")),
		  Object.ConnectFlags.DEFAULT);
	  bus.missionFailed.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onMissionFailedHud")),
		  Object.ConnectFlags.DEFAULT);
	}

	buildMissionBanner();

	// Cache the crosshair and weapon slot bar — siblings of FootHUD/VehicleHUD,
	// persists across HUD context switches.
	Node ch = getNodeOrNull("Crosshair");
	if (ch instanceof Crosshair c) crosshair = c;

	for (Node child : getChildren()) {
	  if (child instanceof WeaponSlotsUI ui) { weaponSlotsUI = ui; break; }
	}

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

	if (weaponSlotsUI != null && newPlayer instanceof Character c) {
	  weaponSlotsUI.wireCharacter(c);
	}
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
	if (weaponSlotsUI != null) weaponSlotsUI.hide();
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
	if (weaponSlotsUI != null) weaponSlotsUI.show();
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

  // ── Mission status banner ─────────────────────────────────────────────────

  /** Builds a centred top-of-screen Label + auto-hide Timer; no .tscn changes needed. */
  private void buildMissionBanner() {
	missionBanner = new Label();
	missionBanner.setHorizontalAlignment(HorizontalAlignment.CENTER);
	missionBanner.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER_TOP, false);
	missionBanner.setPosition(new Vector2(-260f, 24f), false);
	missionBanner.setSize(new Vector2(520f, 40f), false);
	missionBanner.hide();
	addChild(missionBanner);

	missionBannerTimer = new Timer();
	missionBannerTimer.setOneShot(true);
	missionBannerTimer.setWaitTime(MISSION_BANNER_DURATION);
	addChild(missionBannerTimer);
	missionBannerTimer.getTimeout().connectUnsafe(
		Callable.createUnsafe(this, StringNames.toGodotName("onMissionBannerTimeout")),
		Object.ConnectFlags.DEFAULT);
  }

  private void showMissionBanner(String text) {
	if (missionBanner == null) return;
	missionBanner.setText(text);
	missionBanner.show();
	if (missionBannerTimer != null) missionBannerTimer.start();
  }

  @RegisterFunction
  public void onMissionStarted(String missionId, String objectiveType) {
	showMissionBanner("Mission started: " + missionId + " (" + objectiveType + ")");
  }

  @RegisterFunction
  public void onMissionCompletedHud(String missionId, String winningFaction, String outcomeVariant) {
	showMissionBanner("Mission complete — " + winningFaction + " wins (" + outcomeVariant + ")");
  }

  @RegisterFunction
  public void onMissionFailedHud(String missionId, String reason) {
	showMissionBanner("Mission failed — " + reason);
  }

  @RegisterFunction
  public void onMissionBannerTimeout() {
	if (missionBanner != null) missionBanner.hide();
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

  // ── C2: per-character HUD routing ─────────────────────────────────────────

  @RegisterFunction
  public void onCharacterHealthChanged(CharacterInfo info, float currentHealth) {
	if (info == null) return;
	Node hud = characterHUDs.get(info.characterId);
	if (hud instanceof CharacterHUD ch) ch.onHealthChanged(currentHealth);
  }

  @RegisterFunction
  public void onCharacterAmmoChanged(CharacterInfo info, int magazine, int reserve) {
	if (info == null) return;
	Node hud = characterHUDs.get(info.characterId);
	if (hud instanceof CharacterHUD ch) ch.onAmmoChanged(magazine, reserve);
  }

  @RegisterFunction
  public void onCharacterDiedHud(CharacterInfo info) {
	if (info == null) return;
	unregisterCharacterHUD(info.characterId);
  }

  private PackedScene resolveDefeatedEntryScene() {
	if (defeatedEntryScene != null) return defeatedEntryScene;
	godot.api.Object loaded = GD.load(DEFEATED_ENTRY_SCENE_PATH);
	return (loaded instanceof PackedScene ps) ? ps : null;
  }
}
