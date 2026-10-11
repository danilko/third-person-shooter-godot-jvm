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
  private Feed            feed;          // the one feed, top-right under the clock and stars: kills + notices
  private Feed            statusFeed;    // = feed (status lines go in the same column)
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

  /** Where the cash row sits: under the clock and both star rows (WantedStars' second row is the gang's). */
  public static float cashTop() {
	return GameClock.MARGIN + (GameClock.H - WantedStars.STAR) * 0.5f + 2f * WantedStars.STAR + 6f + 6f;
  }

  /** Where the one feed starts: under the cash row. */
  public static float feedTop() {
	return cashTop() + CashReadout.H + 6f;
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @Register
  @Override
  public void _ready() {
	// Feeds are direct children of HUDManager so they stay visible across HUD
	// context switches (FootHUD ↔ VehicleHUD).
	Node feedNode = getNodeOrNull("Feed");
	if (feedNode instanceof Feed f) feed = f;
	// the game clock in the top-right corner (user, 2026-10-02), and the kill feed moved down under it
	if (getNodeOrNull("RearViewMirror") == null) {
	  RearViewMirror mirror = new RearViewMirror();
	  mirror.setName(new godot.core.StringName("RearViewMirror"));
	  addChild(mirror);
	}
	if (getNodeOrNull("GameClock") == null) {
	  GameClock clock = new GameClock();
	  clock.setName(new godot.core.StringName("GameClock"));
	  addChild(clock);
	}
	// the wanted level, left of the clock (PLAN.md W5)
	if (getNodeOrNull("WantedStars") == null) {
	  WantedStars ws = new WantedStars();
	  ws.setName(new godot.core.StringName("WantedStars"));
	  addChild(ws);
	}
	// the money, one row under them (user, 2026-10-10)
	if (getNodeOrNull("CashReadout") == null) {
	  CashReadout cash = new CashReadout();
	  cash.setName(new godot.core.StringName("CashReadout"));
	  addChild(cash);
	}
	// ONE feed (user, 2026-10-08): kill lines and status lines (pickups, missions, radio) share the top-right column,
	// BELOW the clock and both star rows (police, then the worst gang), so nothing there overlaps
	if (feed != null && feed.getNodeOrNull("VBoxContainer") instanceof Control kv) {
	  float top = feedTop();
	  kv.setOffset(godot.core.Side.TOP, top);
	  kv.setOffset(godot.core.Side.BOTTOM, top + 22f);
	  feed.maxEntries = Math.max(feed.maxEntries, 6);
	}
	statusFeed = feed;

	Node busNode = getNodeOrNull("/root/EventBus");
	if (busNode instanceof EventBus bus) {
	  // playerSpawned fires deferred from Player._ready() so this connection
	  // is always in place before the signal arrives, regardless of tree order.
	  bus.playerSpawned.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerSpawned"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.vehicleEntered.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onVehicleEntered"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.vehicleExited.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onVehicleExited"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.characterEliminated.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterEliminated"),
		  godot.core.ConnectFlags.DEFAULT);
	  // mission stingers (every peer: a client's mission events are mirrored by GameManager)
	  bus.missionStarted.connectUnsafe(MethodCallable.createUnsafe(this, "onMissionStartedSting"), godot.core.ConnectFlags.DEFAULT);
	  bus.missionCompleted.connectUnsafe(MethodCallable.createUnsafe(this, "onMissionCompletedSting"), godot.core.ConnectFlags.DEFAULT);
	  bus.missionFailed.connectUnsafe(MethodCallable.createUnsafe(this, "onMissionFailedSting"), godot.core.ConnectFlags.DEFAULT);

	  // C2 — multi-character HUD wiring: route per-character events to whichever
	  // widget (if any) is registered for that characterId via registerCharacterHUD().
	  bus.characterHealthChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterHealthChanged"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.characterAmmoChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterAmmoChanged"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.characterOxygenChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterOxygenChanged"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.characterDied.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterDiedHud"),
		  godot.core.ConnectFlags.DEFAULT);

	  // C1 — mission status banner: surfaces start/complete/fail events that were
	  // previously only visible via GD.print in the console.
	  bus.radioChatter.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onRadioChatter"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.missionStarted.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionStarted"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.missionCompleted.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionCompletedHud"),
		  godot.core.ConnectFlags.DEFAULT);
	  bus.missionFailed.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onMissionFailedHud"),
		  godot.core.ConnectFlags.DEFAULT);

	  // Pickup toasts route through the same status feed as mission events
	  // (was previously a dead connection — nothing connected weaponPickedUp).
	  bus.weaponPickedUp.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onWeaponPickedUp"),
		  godot.core.ConnectFlags.DEFAULT);

	  // Damage-direction indicator: routed per-character, filtered to the local player below.
	  bus.characterDamagedFrom.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onCharacterDamagedFrom"),
		  godot.core.ConnectFlags.DEFAULT);
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
		  || name.equals("RaceHUD") || name.equals("GameClock")
		  || name.equals("WantedStars") || name.equals("RearViewMirror") || name.equals("CashReadout")) continue;
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
	tickRegion(delta);
	tickMinimal(delta);
  }

  // ── F13: the minimal HUD (show on change, then fade) ─────────────────────

  /**
   * PLAN.md F13 (user, 2026-10-09: "the game tells the player through behaviour and the world first"). With
   * QualitySettings' HUD mode "minimal", four always-on widgets fade out and come back only when their state CHANGES or
   * must be seen: health (a hit, or below {@link #LOW_HEALTH}), the weapon panel (a switch / shot / reload, or while
   * aiming), the minimap (in a vehicle, with a waypoint set, or wanted), the clock (never in minimal -- the light tells
   * the time; the map shows it). Everything else is already event-driven or self-gated (stars hidden at zero and
   * flashing on change, the slots column on a switch, the feed, the hit marker, prompts). "full" = every alpha 1, the
   * HUD exactly as before. A fade is a MODULATE, under the situation table's visibility, so the two never fight.
   */
  public static final double LOW_HEALTH = 0.35;
  public static final double HOLD_SECONDS = 4.0;
  public static final double FADE_PER_SECOND = 2.5;

  private final java.util.Map<String, Double> revealLeft = new java.util.HashMap<>();
  private final java.util.Map<String, String> revealSig = new java.util.HashMap<>();
  private final java.util.Map<String, Double> revealAlpha = new java.util.HashMap<>();

  private void tickMinimal(double delta) {
	var q = com.openworld.game.QualitySettings.get();
	boolean minimal = q != null && q.hudMinimal;
	Player me = localPlayer != null && GD.isInstanceValid(localPlayer) ? localPlayer : null;
	var hp = me != null && me.getNodeOrNull("Health") instanceof com.openworld.character.Health h ? h : null;
	var wc = me != null ? me.weaponController : null;
	Control health = getNodeOrNull("FootHUD/Health") instanceof Control c ? c : null;
	reveal("health", health, minimal, delta,
		hp == null ? "" : String.valueOf(Math.round(hp.getCurrentHealth())),
		hp != null && hp.getCurrentHealth() < hp.maxHealth * LOW_HEALTH);
	reveal("weapon", widgets.get(W_WEAPON_HUD), minimal, delta,
		wc == null ? "" : wc.getCurrentWeaponIdNow() + (wc.isWeaponReloading() ? " R" : "") + (wc.isHolstered() ? " H" : ""),
		me != null && me.isCombat());
	boolean wanted = false;
	var ws = com.openworld.game.WantedSystem.get();
	if (ws != null && me != null && me.getCharacterInfo() != null)
	  wanted = ws.hudOf(me.getCharacterInfo().characterId).stars() > 0;
	reveal("minimap", minimap, minimal, delta, "",
		currentVehicle != null || (me != null && me.hasWaypointNow()) || wanted);
	reveal("clock", getNodeOrNull("GameClock") instanceof Control gc ? gc : null, minimal, delta, "", false);
	CashReadout cash = getNodeOrNull("CashReadout") instanceof CashReadout cr ? cr : null;
	reveal("cash", cash, minimal, delta, cash == null ? "" : String.valueOf(cash.balanceShown()), cash != null && cash.inDebt());
  }

  /** One widget's fade: back to full on a new signature or while {@code hold}, else down after HOLD_SECONDS. */
  private void reveal(String id, Control w, boolean minimal, double delta, String sig, boolean hold) {
	if (w == null || !GD.isInstanceValid(w)) return;
	String was = revealSig.put(id, sig);
	double left = revealLeft.getOrDefault(id, 0.0) - delta;
	if (!sig.isEmpty() && !sig.equals(was) && was != null) left = HOLD_SECONDS;
	if (hold) left = Math.max(left, 0.5);
	revealLeft.put(id, left);
	double target = !minimal || left > 0 ? 1.0 : 0.0;
	double a = revealAlpha.getOrDefault(id, 1.0);
	a = target > a ? target : Math.max(target, a - FADE_PER_SECOND * delta);   // in at once, out over 0.4 s
	revealAlpha.put(id, a);
	godot.core.Color m = w.getModulate();
	w.setModulate(new godot.core.Color(m.getR(), m.getG(), m.getB(), a));
  }

  /** A widget's minimal-HUD alpha ("health", "weapon", "minimap", "clock", "cash"; probe readout). */
  @Register
  public double revealAlphaNow(String id) { return revealAlpha.getOrDefault(id, 1.0); }

  // ── which part of the island you are in (PLAN.md 3.18n) ───────────────────

  /** Announce a region when the local player enters it, GTA's district toast: what makes "I'm in the
   *  harbour" sayable. DERIVED from the player's position every frame against the same region boxes the
   *  placement uses ({@link com.openworld.world.Places#regionAt}), never latched on a trigger volume, so it
   *  is right after a teleport, a respawn or a scene load with no event to miss. */
  private Player localPlayer;
  private String currentRegion = "";
  private String pendingRegion = "";
  private double pendingFor = 0.0;
  /** A new region must hold this long before it is announced. The boxes touch, so a body standing on an
   *  edge would otherwise toast on every frame's worth of jitter. */
  private static final double REGION_SETTLE = 1.0;

  private void tickRegion(double delta) {
	if (localPlayer == null || !GD.isInstanceValid(localPlayer)) return;
	com.openworld.world.Places.bind(this);   // the places are per scene
	var at = localPlayer.getGlobalPosition();
	String region = com.openworld.world.Places.regionAt(at.getX(), at.getZ());
	if (region.equals(currentRegion)) {
	  pendingRegion = "";
	  return;
	}
	if (!region.equals(pendingRegion)) {
	  pendingRegion = region;
	  pendingFor = 0.0;
	  return;
	}
	pendingFor += delta;
	if (pendingFor < REGION_SETTLE) return;
	currentRegion = region;
	pendingRegion = "";
	if (!region.isEmpty()) pushStatus(regionLabel(region), null);
  }

  /** The region the local player is in, or "" (probe readout). */
  @Register
  public String regionNow() { return currentRegion; }

  /** The HUD's situation (probe readout: ON_FOOT, VEHICLE_DRIVE, ...). */
  @Register
  public String situationNow() { return currentSituation == null ? "" : currentSituation.name(); }

  private static String regionLabel(String id) {
	return id.isEmpty() ? "" : java.lang.Character.toUpperCase(id.charAt(0)) + id.substring(1).replace('_', ' ');
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
		  godot.core.ConnectFlags.DEFAULT);
	  // Wire crosshair spread source once — self-managed from here on.
	  if (crosshair != null) crosshair.weaponController = wc;
	}

	// Drive crosshair visibility from the player's combat-state changes.
	if (newPlayer instanceof Character c) {
	  c.changedCombatState.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerCombatStateChanged"),
		  godot.core.ConnectFlags.DEFAULT);
	}

	Node healthNode = player.getNodeOrNull("Health");
	if (healthNode instanceof Health h) {
	  // healthChanged (not the discrete hit event) so the HUD bar tracks every health
	  // change — local damage/heal and replicated updates — uniformly.
	  h.healthChanged.connectUnsafe(
		  MethodCallable.createUnsafe(this, "onPlayerHealthChanged"),
		  godot.core.ConnectFlags.DEFAULT);
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
	  localPlayer = p;
	  currentRegion = "";                  // re-announce after a respawn or a body swap
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
		hud.setPlayer(c);
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
	currentVehicle = null;
	applyContext(Situation.ON_FOOT);
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
  public void onRadioChatter(String text) {
	pushStatus(text, null);
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

	// ── Mission stingers (audio.Sound MISSION_*) ────────────────────────────────

	@Register public void onMissionStartedSting(String id, String name) { sting(com.openworld.audio.Sound.MISSION_START); }
	@Register public void onMissionCompletedSting(String id, String name, String variant) { sting(com.openworld.audio.Sound.MISSION_COMPLETE); }
	@Register public void onMissionFailedSting(String id, String reason) { sting(com.openworld.audio.Sound.MISSION_FAIL); }

	/** Stingers played so far (probe readout). */
	private int stings;
	@Register public int stingsNow() { return stings; }

	private void sting(com.openworld.audio.Sound s) {
		stings++;
		com.openworld.audio.Sounds.ui(this, s);
	}
}
