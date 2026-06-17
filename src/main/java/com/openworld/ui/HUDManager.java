package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.movement.character.CombatState;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.weapon.WeaponController;
import com.openworld.character.CharacterInfo;
import com.openworld.game.EventBus;
import com.openworld.net.NetworkManager;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleWeaponMode;
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
import com.openworld.camera.PlayerCameraController;
import com.openworld.item.Pickup;

/**
 * World-level HUD manager. Lives as a CanvasLayer in World.tscn so all HUD
 * scenes render on top of the game world regardless of camera.
 *
 * Responsibilities:
 *  1. Relay active player's local signals (ammoChanged, Health.healthChanged) to
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
		  "res://src/main/resources/com/openworld/ui/DefeatedFeedEntry.tscn";

  /** Which set of HUD widgets is shown. One declarative transition per context. */
  private enum HudContext { ON_FOOT, IN_VEHICLE }

  private Control        activeHUD;
  private Node           player;
  private String         playerCharacterId = "";
  private Crosshair      crosshair;
  private Feed           feed;          // bottom-right kill feed
  private Feed           statusFeed;    // top-center transient toasts (pickups, mission events)
  private WeaponSlotsUI  weaponSlotsUI;

  private HudContext     currentContext  = HudContext.ON_FOOT;
  private Vehicle        currentVehicle;  // non-null only while IN_VEHICLE

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
	// Feeds are direct children of HUDManager so they stay visible across HUD
	// context switches (FootHUD ↔ VehicleHUD).
	Node feedNode = getNodeOrNull("Feed");
	if (feedNode instanceof Feed f) feed = f;
	Node statusFeedNode = getNodeOrNull("StatusFeed");
	if (statusFeedNode instanceof Feed sf) {
	  statusFeed = sf;
	  // StatusFeed instances the same Feed scene as the bottom-right kill feed, so move
	  // its row container to the top-center here (avoids a fragile per-instance .tscn
	  // override of an instanced sub-scene's child).
	  Node vbox = statusFeed.getNodeOrNull("VBoxContainer");
	  if (vbox instanceof Control vb) vb.setPosition(new Vector2(460f, 24f), false);
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

	  // Pickup toasts route through the same status feed as mission events
	  // (was previously a dead connection — nothing connected weaponPickedUp).
	  bus.weaponPickedUp.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onWeaponPickedUp")),
		  Object.ConnectFlags.DEFAULT);
	}

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
	// playerSpawned fires for *every* Player.tscn instance — including replicated
	// remote bodies (spawnPlayerBody on the server, spawnReplicatedCharacter on the
	// client both instantiate Player.tscn, and Player._ready emits unconditionally).
	// Without an ownership check, wirePlayer rewires health/ammo/weapon-slot listeners
	// to whichever body spawned most recently — "HUD never updates" once a remote
	// body shows up. Same isAuthorityFor ownership gate as PlayerCameraController:
	// pure ownerPeerId check, not controller.isAuthority() (a server-side
	// ServerProxyController body is "authoritative" but isn't the locally-viewed one).
	if (spawnedPlayer instanceof Character c && c.characterInfo != null) {
	  Node netNode = getNodeOrNull("/root/NetworkManager");
	  if (netNode instanceof NetworkManager net && net.isNetworked()
			  && !net.isAuthorityFor(c.characterInfo)) {
		return;
	  }
	}
	wirePlayer(spawnedPlayer);
  }

  @RegisterFunction
  public void onPlayerCombatStateChanged(CombatState state) {
	refreshCrosshair();
  }

  // ── HUD context machine ───────────────────────────────────────────────────

  /**
   * Single declarative transition between HUD contexts. Each context fully defines
   * which widgets are visible — replacing the old scattered per-widget show/hide deltas
   * that had to remember to undo each other. Add a context here, not another enter/exit
   * mutation pair.
   */
  private void applyContext(HudContext ctx) {
	currentContext = ctx;
	activateHUD(ctx == HudContext.IN_VEHICLE ? "VehicleHUD" : "FootHUD");
	if (weaponSlotsUI != null) {
	  if (ctx == HudContext.IN_VEHICLE) weaponSlotsUI.hide(); else weaponSlotsUI.show();
	}
	refreshCrosshair();
  }

  /**
   * The single place crosshair visibility is decided (was previously driven from three
   * separate sites). On foot it follows the player's combat state and the player's weapon
   * controller; in a vehicle it shows only for a VEHICLE_WEAPON vehicle, with no weapon
   * controller (fixed spread).
   */
  private void refreshCrosshair() {
	if (crosshair == null) return;
	if (currentContext == HudContext.IN_VEHICLE) {
	  boolean vehWeapon = currentVehicle != null
			  && currentVehicle.getWeaponMode() == VehicleWeaponMode.VEHICLE_WEAPON;
	  crosshair.weaponController = null;
	  crosshair.setShowCrosshair(vehWeapon);
	} else {
	  Node wcNode = player != null ? player.getNodeOrNull("WeaponController") : null;
	  crosshair.weaponController = wcNode instanceof WeaponController wc ? wc : null;
	  boolean inCombat = player instanceof Character c && c.combat;
	  crosshair.setShowCrosshair(inCombat);
	}
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
	  // healthChanged (not the discrete hit event) so the HUD bar tracks every health
	  // change — local damage/heal and replicated updates — uniformly.
	  h.healthChanged.connectUnsafe(
		  Callable.createUnsafe(this, StringNames.toGodotName("onPlayerHealthChanged")),
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
	  if (child instanceof CharacterHUD hud) {
		hud.setPlayerCharacterId(info.characterId);
		// C2 routing (onCharacterHealthChanged/onCharacterAmmoChanged) looks widgets
		// up in characterHUDs by characterId — registerCharacterHUD existed but was
		// never called from anywhere, so replicated health (applyReplicatedHealth
		// emits characterHealthChanged) never reached the HUD.
		registerCharacterHUD(info.characterId, hud);
	  }
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
	currentVehicle = vehicle instanceof Vehicle v ? v : null;
	applyContext(HudContext.IN_VEHICLE);
  }

  @RegisterFunction
  public void onVehicleExited(CharacterInfo occupantInfo) {
	if (occupantInfo == null || !playerCharacterId.equals(occupantInfo.characterId)) return;
	Node vhudNode = getNodeOrNull("VehicleHUD");
	if (vhudNode instanceof VehicleHUD hud) hud.setVehicle(null);
	currentVehicle = null;
	applyContext(HudContext.ON_FOOT);
  }

  // ── Signal relays — player → EventBus ─────────────────────────────────────

  @RegisterFunction
  public void onPlayerAmmoChanged(int magazine, int reserve) {
	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) bus.playerAmmoChanged.emit(magazine, reserve);
  }

  @RegisterFunction
  public void onPlayerHealthChanged(float currentHealth) {
	emitHealth(currentHealth);
  }

  // ── Status feed (mission + pickup toasts) ─────────────────────────────────

  /** Push a transient text (+ optional icon) row to the top-center status feed. */
  private void pushStatus(String text, Texture2D icon) {
	if (statusFeed == null) return;
	StatusFeedEntry entry = new StatusFeedEntry();
	entry.lifespan = statusFeed.entryLifespan;
	entry.setContent(text, icon);
	statusFeed.push(entry);
  }

  @RegisterFunction
  public void onWeaponPickedUp(String characterId, String weaponName, Texture2D weaponIcon) {
	if (!playerCharacterId.isEmpty() && !playerCharacterId.equals(characterId)) return;
	pushStatus("Picked up " + weaponName, weaponIcon);
  }

  @RegisterFunction
  public void onMissionStarted(String missionId, String objectiveType) {
	pushStatus("Mission started: " + missionId + " (" + objectiveType + ")", null);
  }

  @RegisterFunction
  public void onMissionCompletedHud(String missionId, String winningFaction, String outcomeVariant) {
	pushStatus("Mission complete — " + winningFaction + " wins (" + outcomeVariant + ")", null);
  }

  @RegisterFunction
  public void onMissionFailedHud(String missionId, String reason) {
	pushStatus("Mission failed — " + reason, null);
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
