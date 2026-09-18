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
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import godot.api.Object;
import godot.api.PackedScene;
import godot.api.Texture2D;
import godot.api.Timer;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.HorizontalAlignment;
import godot.core.NodePath;
import godot.core.StringNames;
import godot.core.Vector2;
import godot.core.Vector3;
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
 *  2. Show/hide HUD widgets per {@link Situation} via a declarative table ({@link #BASE_LAYOUT})
 *     plus a runtime override layer ({@link #setWidgetEnabled}). The situation is on-foot, or — while
 *     in a carrier — derived from the carrier's weapon mode, so the right weapon UI shows and player
 *     health stays visible while riding.
 *  3. Drive the damage-direction indicator for the local player (EventBus.characterDamagedFrom).
 *
 * Scene setup (HUDManager.tscn, a CanvasLayer): table-managed widget children are discovered by node
 * name (FootHUD, VehicleHUD, WeaponSlotsUI, DamageIndicator, future Minimap); Feed/StatusFeed/Crosshair
 * and the WeaponRadialMenu are not table-managed. Add a widget = drop the node + list its name in
 * BASE_LAYOUT.
 */
@Script(className = "HUDManager")
public class HUDManager extends CanvasLayer {

  /** Path to the WeaponRadialMenu child (relative to this node). Set empty to skip wiring. */
  @Export
  public NodePath radialMenuPath = new NodePath("WeaponRadialMenu");

  /** Scene for {@link DefeatedFeedEntry} rows. Falls back to hard-coded path if null. */
  @Export
  public PackedScene defeatedEntryScene;

  private static final String DEFEATED_ENTRY_SCENE_PATH =
		  "res://src/main/resources/com/openworld/ui/DefeatedFeedEntry.tscn";

  /**
   * HUD situations — richer than on-foot/in-vehicle: the in-vehicle case splits by the carrier's
   * weapon mode so the right weapon UI shows. Derived in {@link #situationForVehicle}. Each maps to a
   * declarative set of visible widgets in {@link #BASE_LAYOUT}.
   */
  private enum Situation { ON_FOOT, VEHICLE_DRIVE, VEHICLE_PASSENGER_WEAPON, VEHICLE_MOUNTED_WEAPON }

  // Widget node-name ids — must match the child node names in HUDManager.tscn.
  private static final String W_FOOT_HUD     = "FootHUD";       // player health + interact prompt
  private static final String W_VEHICLE_HUD  = "VehicleHUD";    // speedometer (bottom-right; no vehicle health)
  private static final String W_WEAPON_HUD   = "WeaponHUD";     // held weapon + ammo (bottom-right)
  private static final String W_WEAPON_SLOTS = "WeaponSlotsUI"; // inventory column, pops up on a switch
  private static final String W_DAMAGE_IND   = "DamageIndicator";

  /**
   * Declarative source of truth: which registry widgets are visible per situation. Edit this table to
   * change the HUD layout; adding a widget = drop its node in HUDManager.tscn + list its name here.
   * Kept as a code table (not an exported nested Dictionary, which crashes the godot-jvm
   * registration scanner — see CLAUDE.md). Player health ({@code FootHUD}) is listed in every vehicle
   * situation so it stays visible while riding (the occupant's body is exposed). The Crosshair and the
   * WeaponRadialMenu are intentionally NOT table-managed: the crosshair has finer combat/weapon-mode
   * gating in {@link #refreshCrosshair}, and the radial menu is a self-managed input overlay.
   */
  private static final java.util.EnumMap<Situation, java.util.Set<String>> BASE_LAYOUT =
      new java.util.EnumMap<>(Situation.class);
  static {
    // The bottom-right corner holds ONE panel at a time — the weapon on foot and for an armed passenger,
    // the speedometer for a driver — so the two never overlap.
    BASE_LAYOUT.put(Situation.ON_FOOT,
        java.util.Set.of(W_FOOT_HUD, W_WEAPON_HUD, W_WEAPON_SLOTS, W_DAMAGE_IND));
    BASE_LAYOUT.put(Situation.VEHICLE_DRIVE,
        java.util.Set.of(W_FOOT_HUD, W_VEHICLE_HUD, W_DAMAGE_IND));
    BASE_LAYOUT.put(Situation.VEHICLE_PASSENGER_WEAPON,
        java.util.Set.of(W_FOOT_HUD, W_WEAPON_HUD, W_WEAPON_SLOTS, W_DAMAGE_IND));
    BASE_LAYOUT.put(Situation.VEHICLE_MOUNTED_WEAPON,
        java.util.Set.of(W_FOOT_HUD, W_VEHICLE_HUD, W_DAMAGE_IND));
  }

  /** Table-managed widget nodes by name, discovered from children in _ready. */
  private final Map<String, Control> widgets = new HashMap<>();
  /** Runtime per-widget visibility overrides (id → forced visible/hidden) — wins over BASE_LAYOUT. */
  private final Map<String, Boolean> widgetOverrides = new HashMap<>();

  private Node            player;
  private String          playerCharacterId = "";
  private Crosshair       crosshair;
  private Feed            feed;          // bottom-right kill feed
  private Feed            statusFeed;    // top-center transient toasts (pickups, mission events)
  private WeaponSlotsUI   weaponSlotsUI;
  private WeaponHUD       weaponHud;
  private DamageIndicator damageIndicator;
  private WeaponProgress  weaponProgress;
  private ScopeOverlay    scopeOverlay;  // 2.7 — self-gated sniper optic
  private AreaWarning     areaWarning;   // P0 0.6 — self-gated world-edge warning
  private HitMarker       hitMarker;     // 2.8 item 9 — confirmed-hit marker
  private RaceHUD         raceHud;       // R2 — self-gated race clock / placing / boost
  private MinimapController minimap;     // I5 — always-on radar
  private WorldMapManager   worldMap;    // I5 — toggled full map
  private GpsArrow          gpsArrow;    // I5 — world-space waypoint arrow

  private Situation      currentSituation = Situation.ON_FOOT;
  private Vehicle        currentVehicle;  // non-null only while in a vehicle situation

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

  @Register
  @Override
  public void _ready() {
	// Feeds are direct children of HUDManager so they stay visible across HUD
	// context switches (FootHUD ↔ VehicleHUD).
	Node feedNode = getNodeOrNull("Feed");
	if (feedNode instanceof Feed f) feed = f;
	Node statusFeedNode = getNodeOrNull("StatusFeed");
	if (statusFeedNode instanceof Feed sf) {
	  statusFeed = sf;
	  // StatusFeed instances the same Feed scene as the top-right kill feed, so move its row
	  // container to the top-LEFT here (avoids a fragile per-instance .tscn override of an
	  // instanced sub-scene's child): pickups and mission toasts there, kills on the right,
	  // the minimap and health bottom-left, the weapon or speedometer bottom-right.
	  Node vbox = statusFeed.getNodeOrNull("VBoxContainer");
	  if (vbox instanceof Control vb) {
		vb.setAnchorsPreset(Control.LayoutPreset.PRESET_TOP_LEFT, false);
		vb.setPosition(new Vector2(20f, 20f), false);
	  }
	}

	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) {
	  // playerSpawned fires deferred from Player._ready() so this connection
	  // is always in place before the signal arrives, regardless of tree order.
	  bus.playerSpawned.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerSpawned"),
		  Object.ConnectFlags.DEFAULT);
	  bus.vehicleEntered.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onVehicleEntered"),
		  Object.ConnectFlags.DEFAULT);
	  bus.vehicleExited.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onVehicleExited"),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterEliminated.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterEliminated"),
		  Object.ConnectFlags.DEFAULT);

	  // C2 — multi-character HUD wiring: route per-character events to whichever
	  // widget (if any) is registered for that characterId via registerCharacterHUD().
	  bus.characterHealthChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterHealthChanged"),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterAmmoChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterAmmoChanged"),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterOxygenChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterOxygenChanged"),
		  Object.ConnectFlags.DEFAULT);
	  bus.characterDied.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterDiedHud"),
		  Object.ConnectFlags.DEFAULT);

	  // C1 — mission status banner: surfaces start/complete/fail events that were
	  // previously only visible via GD.print in the console.
	  bus.missionStarted.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionStarted"),
		  Object.ConnectFlags.DEFAULT);
	  bus.missionCompleted.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionCompletedHud"),
		  Object.ConnectFlags.DEFAULT);
	  bus.missionFailed.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionFailedHud"),
		  Object.ConnectFlags.DEFAULT);

	  // Pickup toasts route through the same status feed as mission events
	  // (was previously a dead connection — nothing connected weaponPickedUp).
	  bus.weaponPickedUp.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onWeaponPickedUp"),
		  Object.ConnectFlags.DEFAULT);

	  // Damage-direction indicator: routed per-character, filtered to the local player below.
	  bus.characterDamagedFrom.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterDamagedFrom"),
		  Object.ConnectFlags.DEFAULT);
	}

	// Cache the crosshair and weapon slot bar — siblings of FootHUD/VehicleHUD,
	// persists across HUD context switches.
	Node ch = getNodeOrNull("Crosshair");
	if (ch instanceof Crosshair c) crosshair = c;

	// Build the situational widget registry: every direct Control child EXCEPT the always-on feeds,
	// the self-gated crosshair, and the input-overlay radial menu. Adding a widget = drop its node +
	// list its name in BASE_LAYOUT — no new show/hide code here.
	for (Node child : getChildren()) {
	  if (!(child instanceof Control c)) continue;
	  String name = child.getName().toString();
	  if (name.equals("Feed") || name.equals("StatusFeed") || name.equals("Crosshair")
		  || name.equals("WeaponRadialMenu") || name.equals("WeaponProgress")
		  || name.equals("ScopeOverlay") || name.equals("AreaWarning") || name.equals("HitMarker")
		  || name.equals("Minimap") || name.equals("WorldMap") || name.equals("GpsArrow")
		  || name.equals("RaceHUD")) continue;
	  widgets.put(name, c);
	  if (c instanceof WeaponSlotsUI ws) weaponSlotsUI = ws;
	  if (c instanceof WeaponHUD wh) weaponHud = wh;
	  if (c instanceof DamageIndicator di) damageIndicator = di;
	}
	// WeaponProgress self-hides when idle (polls the controller each frame), so it is not
	// table-managed — cache it directly to wire its controller.
	Node wp = getNodeOrNull("WeaponProgress");
	if (wp instanceof WeaponProgress w) weaponProgress = w;
	// ScopeOverlay is self-gated too, and deliberately so: the scope is not a SITUATION (it comes
	// and goes on the aim button and on every interruption that ends it), so the table could only
	// hold a stale answer. It polls WeaponController.isScoped() like WeaponProgress polls the
	// reload timer.
	Node so = getNodeOrNull("ScopeOverlay");
	if (so instanceof ScopeOverlay s2) scopeOverlay = s2;
	// AreaWarning: the world edge's warning band (WorldBounds), event-driven and self-gated.
	if (getNodeOrNull("AreaWarning") instanceof AreaWarning aw) areaWarning = aw;
	if (getNodeOrNull("HitMarker") instanceof HitMarker hm) hitMarker = hm;
	// RaceHUD: a race is orthogonal to the ON_FOOT/VEHICLE situations (you can finish one on foot),
	// so it polls RaceDirector rather than being table-managed — the WeaponProgress idiom.
	if (getNodeOrNull("RaceHUD") instanceof RaceHUD rh) raceHud = rh;
	// I5 navigation widgets — always-on / self-toggled, not table-managed (like WeaponProgress).
	Node mm = getNodeOrNull("Minimap");
	if (mm instanceof MinimapController m) minimap = m;
	Node wmap = getNodeOrNull("WorldMap");
	if (wmap instanceof WorldMapManager w) worldMap = w;
	Node ga = getNodeOrNull("GpsArrow");
	if (ga instanceof GpsArrow a) gpsArrow = a;

	applyContext(Situation.ON_FOOT);
  }

  @Register
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

  @Register
  public void onPlayerCombatStateChanged(CombatState state) {
	refreshCrosshair();
  }

  // ── HUD context machine ───────────────────────────────────────────────────

  /**
   * Apply a situation: set every table-managed widget's visibility from BASE_LAYOUT (with any runtime
   * override applied), then refresh the crosshair. The single declarative transition — no scattered
   * per-widget show/hide deltas.
   */
  private void applyContext(Situation situation) {
	currentSituation = situation;
	for (Map.Entry<String, Control> e : widgets.entrySet()) {
	  e.getValue().setVisible(resolveWidgetVisible(e.getKey(), situation));
	}
	applyDriverCorner(situation);
	refreshCrosshair();
  }

  /**
   * A car that allows drive-bys is PASSENGER_WEAPON for everyone in it, driver included. A PASSENGER gets the weapon
   * panel and the inventory column. The DRIVER gets the vehicle cluster (speed + damage diagram) in the corner and,
   * stacked above it, the compact weapon panel — always, rather than swapping on aim, so neither flickers; the
   * inventory column stays hidden (switch with the weapon wheel). A runtime override still wins.
   */
  private static final float DRIVER_WEAPON_RAISE = 58f;   // the vehicle cluster's height + a gap
  private float weaponHudTop = Float.NaN, weaponHudBottom;

  private boolean isLocalDriver() {
	if (currentSituation != Situation.VEHICLE_PASSENGER_WEAPON || currentVehicle == null
		|| !GD.isInstanceValid(currentVehicle) || player == null) return false;
	// compared by engine instance id: two Java wrappers of one node are not == (CLAUDE.md, stale wrappers)
	Character driver = currentVehicle.getOccupant();
	return driver != null && driver.getInstanceId() == player.getInstanceId();
  }

  private boolean raceActive = false;

  /** Re-apply the layout when a race starts or ends (RaceDirector has no signal of its own; the HUD polls). */
  @Register
  @Override
  public void _process(double delta) {
	var rd = com.openworld.game.mission.RaceDirector.get();
	boolean active = rd != null && GD.isInstanceValid(rd) && rd.raceActiveNow();
	if (active != raceActive) {
	  raceActive = active;
	  applyContext(currentSituation);
	}
  }

  private void applyDriverCorner(Situation situation) {
	Control wh = widgets.get(W_WEAPON_HUD);
	if (wh != null && Float.isNaN(weaponHudTop)) {
	  weaponHudTop = (float) wh.getOffset(godot.core.Side.TOP);
	  weaponHudBottom = (float) wh.getOffset(godot.core.Side.BOTTOM);
	}
	boolean driver = isLocalDriver();
	if (wh != null) {
	  float raise = driver ? DRIVER_WEAPON_RAISE : 0f;
	  wh.setOffset(godot.core.Side.TOP, weaponHudTop - raise);
	  wh.setOffset(godot.core.Side.BOTTOM, weaponHudBottom - raise);
	}
	if (!driver) return;
	setUnlessOverridden(W_VEHICLE_HUD, true);
	setUnlessOverridden(W_WEAPON_HUD, !raceActive);
	setUnlessOverridden(W_WEAPON_SLOTS, false);
  }

  private void setUnlessOverridden(String id, boolean visible) {
	Control w = widgets.get(id);
	if (w != null && !widgetOverrides.containsKey(id)) w.setVisible(visible);
  }

  /** A widget is visible if a runtime override forces it; otherwise per the situation's BASE_LAYOUT set. */
  private boolean resolveWidgetVisible(String id, Situation situation) {
	Boolean override = widgetOverrides.get(id);
	if (override != null) return override;
	// A race is a context, not a situation (you can finish one on foot): while one runs, the combat HUD steps
	// aside for RaceHUD, as in GTA's races. Missions hide anything else through setWidgetEnabled.
	if (raceActive && (id.equals(W_WEAPON_HUD) || id.equals(W_WEAPON_SLOTS))) return false;
	java.util.Set<String> set = BASE_LAYOUT.get(situation);
	return set != null && set.contains(id);
  }

  /** Maps a vehicle's weapon mode to the HUD situation (null vehicle ⇒ plain drive). */
  private Situation situationForVehicle(Vehicle v) {
	if (v == null) return Situation.VEHICLE_DRIVE;
	return switch (v.getWeaponMode()) {
	  case PASSENGER_WEAPON -> Situation.VEHICLE_PASSENGER_WEAPON;
	  case VEHICLE_WEAPON   -> Situation.VEHICLE_MOUNTED_WEAPON;
	  default               -> Situation.VEHICLE_DRIVE;
	};
  }

  /**
   * Runtime override: force a HUD widget visible/hidden regardless of the current situation's table
   * entry — for per-carrier or gameplay tweaks (e.g. a turret carrier hiding the minimap). The id is
   * the widget's node name (e.g. {@code "WeaponSlotsUI"}, {@code "DamageIndicator"}).
   */
  @Register
  public void setWidgetEnabled(String id, boolean enabled) {
	widgetOverrides.put(id, enabled);
	applyContext(currentSituation);
  }

  /** Drop a runtime override so the widget follows the situation table again. */
  @Register
  public void clearWidgetOverride(String id) {
	widgetOverrides.remove(id);
	applyContext(currentSituation);
  }

  /**
   * The single place crosshair visibility is decided. On foot it follows the player's combat state and
   * weapon controller; for a mounted vehicle weapon it shows with fixed spread (no weapon controller);
   * for a passenger weapon it shows with the player's own weapon spread; while plain driving it hides.
   */
  private void refreshCrosshair() {
	if (crosshair == null) return;
	switch (currentSituation) {
	  case VEHICLE_MOUNTED_WEAPON -> {
		crosshair.weaponController = null;
		crosshair.setShowCrosshair(true);
	  }
	  case VEHICLE_PASSENGER_WEAPON -> {
		Node wcNode = player != null ? player.getNodeOrNull("WeaponController") : null;
		crosshair.weaponController = wcNode instanceof WeaponController wc ? wc : null;
		crosshair.setShowCrosshair(true);
	  }
	  case VEHICLE_DRIVE -> {
		crosshair.weaponController = null;
		crosshair.setShowCrosshair(false);
	  }
	  default -> {
		Node wcNode = player != null ? player.getNodeOrNull("WeaponController") : null;
		crosshair.weaponController = wcNode instanceof WeaponController wc ? wc : null;
		boolean inCombat = player instanceof Character c && c.combat;
		crosshair.setShowCrosshair(inCombat);
	  }
	}
  }

  // ── Public API ────────────────────────────────────────────────────────────

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
		  MethodCallable.createUnsafe(this, "onPlayerAmmoChanged"),
		  Object.ConnectFlags.DEFAULT);
	  // Wire crosshair spread source once — self-managed from here on.
	  if (crosshair != null) crosshair.weaponController = wc;
	}

	// Drive crosshair visibility from the player's combat-state changes.
	if (newPlayer instanceof Character c) {
	  c.changedCombatState.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerCombatStateChanged"),
		  Object.ConnectFlags.DEFAULT);
	}

	Node healthNode = player.getNodeOrNull("Health");
	if (healthNode instanceof Health h) {
	  // healthChanged (not the discrete hit event) so the HUD bar tracks every health
	  // change — local damage/heal and replicated updates — uniformly.
	  h.healthChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerHealthChanged"),
		  Object.ConnectFlags.DEFAULT);
	  emitHealth(h.getCurrentHealth());
	}

	wireWeaponRadialMenu(newPlayer, wcNode);
	wireCharacterHUD(newPlayer);

	if (weaponSlotsUI != null && newPlayer instanceof Character c) {
	  weaponSlotsUI.wireCharacter(c);
	}
	if (weaponHud != null && newPlayer instanceof Character c) {
	  weaponHud.wireCharacter(c);
	}
	if (damageIndicator != null && newPlayer instanceof Character c) {
	  damageIndicator.setPlayer(c);
	}
	if (weaponProgress != null && newPlayer instanceof Character c) {
	  weaponProgress.wireCharacter(c);
	}
	if (scopeOverlay != null && newPlayer instanceof Character c) {
	  scopeOverlay.wireCharacter(c);
	}
	if (areaWarning != null && newPlayer instanceof Character c) {
	  areaWarning.wireCharacter(c);
	}
	if (hitMarker != null && newPlayer instanceof Character c) {
	  hitMarker.wireCharacter(c);
	}
	// The reticle follows this character's SEATED aim point. It self-gates on
	// Character.isSeatedAimAnchored(), so on foot this reference changes nothing.
	if (crosshair != null && newPlayer instanceof Character c) {
	  crosshair.aimCharacter = c;
	}
	// I5 navigation widgets follow the local player.
	if (newPlayer instanceof Player p) {
	  if (minimap != null)  minimap.wirePlayer(p);
	  if (worldMap != null) worldMap.wirePlayer(p);
	  if (gpsArrow != null) gpsArrow.wirePlayer(p);
	  if (raceHud != null)  raceHud.wireCharacter(p);
	}
  }

  /**
   * EventBus.characterDamagedFrom → drive the damage-direction indicator for the LOCAL player only
   * (filtered by characterId, same as the other per-character HUD routing). The attacker world
   * position came from the authority (single-player/host) or the replicated damage broadcast.
   */
  @Register
  public void onCharacterDamagedFrom(CharacterInfo info, Vector3 source) {
	if (info == null || damageIndicator == null) return;
	if (!playerCharacterId.isEmpty() && !playerCharacterId.equals(info.characterId)) return;
	damageIndicator.onDamagedFrom(source);
  }

  private void wireCharacterHUD(Node newPlayer) {
	if (!(newPlayer instanceof Character c)) return;
	CharacterInfo info = c.characterInfo;
	if (info == null) return;
	for (Node child : getChildren()) {
	  if (child instanceof CharacterHUD hud) {
		hud.setPlayerCharacterId(info.characterId);
		if (c.getNodeOrNull("Health") instanceof Health h) {
		  hud.setMaxHealth(h.maxHealth);
		  hud.onHealthChanged(h.getCurrentHealth());
		}
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

  // ── Vehicle HUD switching ─────────────────────────────────────────────────

  @Register
  public void onVehicleEntered(Node vehicle, CharacterInfo occupantInfo) {
	if (occupantInfo == null || !playerCharacterId.equals(occupantInfo.characterId)) return;
	currentVehicle = vehicle instanceof Vehicle v ? v : null;
	setVehicleNameplateVisible(currentVehicle, false);   // your own car carries no floating label
	Node vhudNode = getNodeOrNull("VehicleHUD");
	if (vhudNode instanceof VehicleHUD hud && vehicle instanceof Node3D v) {
	  hud.setVehicle(v);
	}
	applyContext(situationForVehicle(currentVehicle));
  }

  @Register
  public void onVehicleExited(CharacterInfo occupantInfo) {
	if (occupantInfo == null || !playerCharacterId.equals(occupantInfo.characterId)) return;
	Node vhudNode = getNodeOrNull("VehicleHUD");
	if (vhudNode instanceof VehicleHUD hud) hud.setVehicle(null);
	setVehicleNameplateVisible(currentVehicle, true);
	currentVehicle = null;
	applyContext(Situation.ON_FOOT);
  }

  /**
   * Hide the nameplate of the vehicle the local player is in, and give it back on the way out — the same rule
   * {@code Character.applyNameplateVisibility} applies to the local player's own body. Local view only.
   */
  private static void setVehicleNameplateVisible(Vehicle v, boolean visible) {
	if (v != null && GD.isInstanceValid(v) && v.getNodeOrNull("Nameplate") instanceof Node3D np) np.setVisible(visible);
  }

  // ── Signal relays — player → EventBus ─────────────────────────────────────

  @Register
  public void onPlayerAmmoChanged(int magazine, int reserve) {
	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) bus.playerAmmoChanged.emit(magazine, reserve);
  }

  @Register
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

  @Register
  public void onWeaponPickedUp(String characterId, String weaponName, Texture2D weaponIcon) {
	if (!playerCharacterId.isEmpty() && !playerCharacterId.equals(characterId)) return;
	pushStatus("Picked up " + weaponName, weaponIcon);
  }

  @Register
  public void onMissionStarted(String missionId, String objectiveType) {
	pushStatus("Mission started: " + missionId + " (" + objectiveType + ")", null);
  }

  @Register
  public void onMissionCompletedHud(String missionId, String winningFaction, String outcomeVariant) {
	pushStatus("Mission complete — " + winningFaction + " wins (" + outcomeVariant + ")", null);
  }

  @Register
  public void onMissionFailedHud(String missionId, String reason) {
	pushStatus("Mission failed — " + reason, null);
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private void emitHealth(float currentHealth) {
	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) bus.playerHealthChanged.emit(currentHealth);
  }

  /** Push a {@link DefeatedFeedEntry} row to the kill feed for any character elimination. */
  @Register
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

  @Register
  public void onCharacterHealthChanged(CharacterInfo info, float currentHealth) {
	if (info == null) return;
	Node hud = characterHUDs.get(info.characterId);
	if (hud instanceof CharacterHUD ch) ch.onHealthChanged(currentHealth);
  }

  @Register
  public void onCharacterAmmoChanged(CharacterInfo info, int magazine, int reserve) {
	if (info == null) return;
	Node hud = characterHUDs.get(info.characterId);
	if (hud instanceof CharacterHUD ch) ch.onAmmoChanged(magazine, reserve);
  }

  /** Relay the active player's swim oxygen to the FootHUD breath meter (filtered like pickups). */
  @Register
  public void onCharacterOxygenChanged(CharacterInfo info, float current, float max) {
	if (info == null) return;
	if (!playerCharacterId.isEmpty() && !playerCharacterId.equals(info.characterId)) return;
	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) bus.playerOxygenChanged.emit(current, max);
  }

  @Register
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
