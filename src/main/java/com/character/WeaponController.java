package com.character;

import com.game.EventBus;
import godot.annotation.*;
import godot.api.*;
import godot.core.Callable;
import godot.core.NodePath;
import godot.core.Signal1;
import godot.core.Signal2;
import godot.core.StringName;
import godot.core.StringNames;
import godot.core.VariantArray;
import godot.core.Vector3;
import godot.global.GD;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RegisterClass(className = "WeaponController")
public class WeaponController extends Node {

  @RegisterProperty @Export public AnimationController animationController;

  @RegisterProperty @Export
  public NodePath aimRayPath = new NodePath("ActiveCamera/AimRay");

  @RegisterProperty @Export
  public NodePath weaponAttachmentPath = new NodePath("MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/WeaponAttachment");

  /**
   * All weapon socket Marker3D nodes for this character, listed as NodePaths from the
   * scene root. Each Marker3D node name becomes a key in the socket registry.
   *
   * WeaponItem.holdSocket / WeaponItem.holsterSockets reference these names.
   * Example: a rifle with holdSocket="MarkerRifle" attaches to the Marker3D named
   * "MarkerRifle" registered here. A shovel with holsterSockets=["MarkerBack"] parks at
   * the Marker3D named "MarkerBack". No code changes needed for new weapons or poses.
   */
  @RegisterProperty @Export
  public VariantArray<NodePath> socketPaths = new VariantArray<>(NodePath.class);

  @RegisterSignal
  public final Signal1<Float> weaponFired = new Signal1<>(this, new StringName("weapon_fired"));

  @RegisterSignal
  public final Signal2<Integer, Integer> ammoChanged = new Signal2<>(this, new StringName("ammo_changed"));

  @RegisterProperty @Export public AudioStreamPlayer3D weaponAudio;

  /**
   * Defines the type of each slot by index.
   * Slot 0 is always FIST — permanent, non-droppable, auto-populated in _ready().
   * Slots 1–6 are the standard weapon inventory.
   */
  protected WeaponSlotType[] slotTypes = {
      WeaponSlotType.FIST,        // slot 0 — permanent fist (key: key 0)
      WeaponSlotType.PRIMARY,     // slot 1 — first long weapon  (key 1)
      WeaponSlotType.PRIMARY,     // slot 2 — second long weapon (key 2)
      WeaponSlotType.SECONDARY,   // slot 3 — sidearm            (key 3)
      WeaponSlotType.MELEE,       // slot 4 — melee              (key 4)
      WeaponSlotType.THROWABLE,   // slot 5 — throwable          (key 5)
      WeaponSlotType.CONSUMABLE,  // slot 6 — consumable         (key 6)
  };

  private WeaponItem[] weapons;
  private int activeSlotIndex  = 0;
  private int pendingSlotIndex = 0;

  // Weapons queued for equip/drop; processed in _process (idle) to avoid
  // reparenting a RigidBody3D (CollisionObject) during a physics callback.
  private final List<WeaponItem> pendingEquips = new ArrayList<>();
  // Items already equipped during the current _process pass — see the race-guard
  // comment in equipWeapon(). Cleared at the start of each pass that has work to do.
  private final Set<WeaponItem> equippedThisPass = new HashSet<>();
  private final List<WeaponItem> pendingDrops  = new ArrayList<>();
  // True when pendingDrops was populated by dropAllWeapons() (death); false for a
  // manual single-weapon drop. Controls which physics parameters are used.
  private boolean isDeathDrop = false;

  // Populated in _ready() from socketPaths: node name → Marker3D node.
  private final Map<String, Node> socketMap = new HashMap<>();

  private RayCast3D aimRay;
  private RayCast3D originalAimRay;
  private EventBus eventBus;

  private Timer transitionTimer;
  private Timer fireTimer;
  private Timer reloadTimer;

  // ── Accessors ─────────────────────────────────────────────────────────────

  public int getWeapon() { return activeSlotIndex; }

  /** True when a real weapon (slot > 0) is active. False when fist is active. */
  public boolean isArmed() { return activeSlotIndex > 0; }

  public WeaponItem getCurrentWeaponItem() {
    return weapons[activeSlotIndex];
  }

  public int getWeaponCount() {
    int n = 0;
    for (WeaponItem w : weapons) if (w != null) n++;
    return n;
  }

  public WeaponItem getWeaponItem(int slotIndex) {
    if (slotIndex < 0 || slotIndex >= weapons.length) return null;
    return weapons[slotIndex];
  }

  public float getCurrentSpreadDeg() {
    WeaponItem w = getCurrentWeaponItem();
    return w != null ? w.getCurrentSpreadDeg() : 0f;
  }

  /** The active AimRay for all character-owned weapons. May be the vehicle ray when overridden. */
  public RayCast3D getAimRay() { return aimRay; }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _process(double delta) {
    // Process equips first (deferred from Area3D body_entered signals)
    if (!pendingEquips.isEmpty()) {
      equippedThisPass.clear();
      for (WeaponItem item : new ArrayList<>(pendingEquips)) equipWeapon(item);
      pendingEquips.clear();
      equippedThisPass.clear();
    }
    // Then process any pending drops (single manual drop or full death-drop batch)
    if (!pendingDrops.isEmpty()) {
      List<WeaponItem> batch = new ArrayList<>(pendingDrops);
      boolean death = isDeathDrop;
      pendingDrops.clear();
      isDeathDrop = false;
      for (WeaponItem item : batch) {
        if (death) returnWeaponToWorldOnDeath(item);
        else       returnWeaponToWorld(item);
      }
    }
  }

  @RegisterFunction
  @Override
  public void _ready() {
    weapons = new WeaponItem[slotTypes.length];

    transitionTimer = (Timer) getNode("TransitionTimer");
    fireTimer       = (Timer) getNode("FireTimer");
    reloadTimer     = (Timer) getNode("ReloadTimer");

    if (getOwner().hasNode(aimRayPath)) {
      aimRay = (RayCast3D) getOwner().getNode(aimRayPath);
    }

    // Build socket registry from owner-relative socket paths (no CharacterVisuals).
    // Characters using CharacterVisuals skip this — postInitFromVisuals() rebuilds from visuals root.
    for (java.lang.Object obj : socketPaths) {
      NodePath p = (NodePath) obj;
      if (p == null || p.toString().isEmpty()) continue;
      Node socket = getOwner().getNodeOrNull(p);
      if (socket != null) socketMap.put(socket.getName().toString(), socket);
    }

    // Discover weapons pre-placed in the weapon attachment (e.g. vehicle weapon mounts).
    // For CharacterVisuals characters the attachment lives inside the visuals sub-scene, so
    // getNodeOrNull returns null here — postInitFromVisuals() re-discovers correctly later.
    discoverPrePlacedWeapons(getOwner(), weaponAttachmentPath);
    showWeapon(activeSlotIndex);

    emitInitialAmmoState();

    // Self-relay: re-broadcast every ammoChanged emission to EventBus.characterAmmoChanged
    // so multi-character HUD/game-state code (C2) can track any character's ammo, not
    // just the local player's. Avoids touching every existing ammoChanged.emit() call site.
    ammoChanged.connectUnsafe(
        Callable.createUnsafe(this, StringNames.toGodotName("relayAmmoToEventBus")),
        godot.api.Object.ConnectFlags.DEFAULT);
  }

  /** Receives our own ammoChanged signal and re-broadcasts it on EventBus, keyed by owner CharacterInfo. */
  @RegisterFunction
  public void relayAmmoToEventBus(int magazine, int reserve) {
    if (!(getOwner() instanceof Character c) || c.characterInfo == null) return;
    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) bus.characterAmmoChanged.emit(c.characterInfo, magazine, reserve);
  }

  /**
   * Wires all mesh-dependent references from a newly instantiated CharacterVisuals scene.
   * Called by Character._ready() after addChild(visualsInstance) and after setting
   * Safe to call with a null config (no-op).
   */
  public void postInitFromVisuals(Node visualsRoot, MeshConfig config) {
    if (visualsRoot == null || config == null) return;

    // Rebuild socket map from visuals-relative paths in meshConfig.
    socketMap.clear();
    for (java.lang.Object obj : config.socketPaths) {
      NodePath p = (NodePath) obj;
      if (p == null || p.toString().isEmpty()) continue;
      Node socket = visualsRoot.getNodeOrNull(p);
      if (socket != null) socketMap.put(socket.getName().toString(), socket);
    }

    // Discover weapons pre-placed in the weapon attachment node.
    discoverPrePlacedWeapons(visualsRoot, config.weaponAttachmentPath);
    showWeapon(activeSlotIndex);

    // Sync animation tree to the initial weapon pose (no transition fires on first discovery).
    WeaponItem initial = weapons[activeSlotIndex];
    if (initial != null && animationController != null) {
      animationController.onWeaponEquip(initial.weaponPoseIndex);
    }

    emitInitialAmmoState();
  }

  private void discoverPrePlacedWeapons(Node root, NodePath attachPath) {
    if (attachPath == null || attachPath.isEmpty()) return;
    Node attachment = root.getNodeOrNull(attachPath);
    if (attachment == null) return;
    for (Node child : attachment.getChildren()) {
      if (child.getChildCount() > 0 && child.getChild(0) instanceof WeaponItem w) {
        int slot = findFreeSlot(w.getSlotType());
        if (slot < 0) slot = findFirstSlot(w.getSlotType());
        if (slot < 0) continue;
        weapons[slot] = w;
        w.onPickedUp();
        injectCharacterRefs(w);
        w.hide();
      }
    }
  }

  // ── Runtime equip / drop ─────────────────────────────────────────────────

  /**
   * Queues {@code item} to be equipped in the next idle frame (_process).
   * Called from WeaponItem.onCharacterEntered which runs inside an Area3D
   * body_entered signal (physics context) where reparent() is forbidden.
   */
  public void requestEquip(WeaponItem item) {
    if (!pendingEquips.contains(item)) pendingEquips.add(item);
  }

  /**
   * Equips {@code item} into the first free slot whose type matches the weapon's
   * {@link WeaponItem#getSlotType()}. Falls back to the first slot of that type
   * (displacing the current occupant) if no free slot exists.
   * FIST slot (0) is structurally protected — no other weapon type maps to it.
   */
  public void equipWeapon(WeaponItem item) {
    WeaponSlotType type = item.getSlotType();
    int targetSlot = findFreeSlot(type);
    if (targetSlot < 0) targetSlot = findFirstSlot(type);
    if (targetSlot < 0) return;

    WeaponItem displaced = weapons[targetSlot];

    // Two nearby pickups of the same slot type can both pass shouldAutoPickup() in the
    // same physics frame — the matching slot still reads as "free" to both because the
    // actual equip is deferred to _process. Without this guard the second one would
    // immediately displace-and-throw the first back into the world the instant it lands
    // (e.g. "two throwables close together — one gets picked up and flung away again").
    // Hand it back to the world instead: same outcome as walking up to a full slot
    // (interact-prompt / re-trigger once settled), just consistent and non-jarring.
    if (displaced != null && equippedThisPass.contains(displaced)) {
      item.onReturnedToWorld();
      return;
    }

    boolean willBeActive = targetSlot == activeSlotIndex || weapons[activeSlotIndex] == null;

    item.onPickedUp();
    injectCharacterRefs(item);
    weapons[targetSlot] = item;
    equippedThisPass.add(item);

    // Items that opt into autoEquipOnPickup (e.g. throwables) jump straight to the
    // active slot when the character is unarmed (fist active), so they're immediately
    // usable without a manual slot switch. Generalizes the old throwable-only special
    // case so any weapon archetype can opt in via the exported flag — see
    // WeaponItem.autoEquipOnPickup.
    if (!willBeActive && item.autoEquipOnPickup && activeSlotIndex == 0) {
      willBeActive = true;
      activeSlotIndex = targetSlot;
    }

    if (willBeActive) {
      boolean wasArmed = isArmed();
      activeSlotIndex = targetSlot;
      moveWeaponToHand(item);
      // Block accidental fire on pickup: the fire button may already be held from the
      // previous weapon. Use the switch-speed delay (same as a manual slot switch) so the
      // player must release and re-press fire before the newly equipped weapon can fire.
      if (fireTimer.getTimeLeft() <= 0) {
        fireTimer.setWaitTime(1.0 / item.getSwitchSpeed());
        fireTimer.start();
      }
      if (item.getReloadAudio() != null) {
        weaponAudio.setStream(item.getReloadAudio());
        weaponAudio.play();
      }
      if (animationController != null) animationController.onWeaponEquip(item.weaponPoseIndex);
      ammoChanged.emit(item.getMagazine(), item.getReserve());
      if (wasArmed != isArmed()) emitArmedStateChanged(isArmed());
    } else {
      // Weapon goes into an inactive slot — mount at its holster socket.
      moveWeaponToHolster(item);
      WeaponItem active = getCurrentWeaponItem();
      ammoChanged.emit(active != null ? active.getMagazine() : 0,
                       active != null ? active.getReserve()  : 0);
    }

    EventBus bus = getEventBus();
    if (bus != null) {
      String characterId = (getOwner() instanceof Character c && c.characterInfo != null)
          ? c.characterInfo.characterId : "";
      bus.weaponPickedUp.emit(characterId, item.getDisplayName(), item.weaponIcon);
    }

    if (displaced != null && displaced.shouldDropToWorld()) returnWeaponToWorld(displaced);
    else if (displaced != null) displaced.setup(null, null, null);
  }

  /**
   * Removes the currently active weapon from the inventory and returns it to the
   * world at the character's feet with a throw impulse.
   * No-op if the active weapon is not droppable (e.g. fist at slot 0).
   */
  @RegisterFunction
  public void dropCurrentWeapon() {
    WeaponItem current = weapons[activeSlotIndex];
    if (current == null || !current.isDroppable) return;
    weapons[activeSlotIndex] = null;
    current.hide();
    // ThrowableItem with 0 carry count: clear refs but don't spawn a world pickup.
    if (current.shouldDropToWorld()) {
      pendingDrops.add(current);
    } else {
      current.setup(null, null, null);
    }
    activateFirstAvailableSlot();
  }

  /**
   * Releases every droppable weapon back into the world. Called on character death.
   * Safe to invoke from a physics callback — actual reparenting is deferred to _process().
   * Each weapon spawns at hip height + 0.5 m extra and is thrown in a random radial
   * direction so weapons fan out rather than pile on one spot.
   * Non-droppable weapons (fist) are skipped.
   */
  public void dropAllWeapons() {
    for (int i = 0; i < weapons.length; i++) {
      WeaponItem item = weapons[i];
      if (item == null || !item.isDroppable) continue;
      weapons[i] = null;
      item.hide();
      pendingDrops.add(item);
    }
    isDeathDrop = true;
  }

  // ── Signal handlers ───────────────────────────────────────────────────────

  @RegisterFunction
  public void onWeaponFire() {
    if (fireTimer.getTimeLeft() > 0 || reloadTimer.getTimeLeft() > 0 || isWeaponTransitioning()) return;
    WeaponItem w = getCurrentWeaponItem();
    if (w == null) return;
    if (!w.isInfiniteAmmo && w.getMagazine() == 0) { onWeaponReload(); return; }
    if (!w.canUse()) return;

    fireTimer.setWaitTime(1.0 / w.getFireRate());
    fireTimer.start();

    w.useWeapon();
    weaponFired.emit(w.getFireRate() * 0.2f);
    ammoChanged.emit(w.getMagazine(), w.getReserve());
    // After the last throw, let the weapon clear its own slot (ThrowableItem auto-empties)
    if (!w.isInfiniteAmmo && w.getMagazine() == 0) w.onMagazineEmpty();
  }

  @RegisterFunction
  public void onWeaponNotFire() {
    WeaponItem w = getCurrentWeaponItem();
    if (w != null) w.stopUseWeapon();
  }

  @RegisterFunction
  public void onWeaponReload() {
    WeaponItem w = getCurrentWeaponItem();
    if (w == null || w.isInfiniteAmmo || w.getReserve() == 0 || isWeaponReloading()) return;
    reloadTimer.setWaitTime(1.0 / w.getReloadSpeed());
    if (w.getReloadAudio() != null) {
      weaponAudio.setStream(w.getReloadAudio());
      weaponAudio.play();
    }
    reloadTimer.start();
    if (animationController != null) animationController.onWeaponReload();
  }

  @RegisterFunction
  public void onWeaponReloadComplete() {
    WeaponItem w = getCurrentWeaponItem();
    if (w == null) return;
    w.onReloadComplete();
    ammoChanged.emit(w.getMagazine(), w.getReserve());
  }

  @RegisterFunction
  public void onSetWeapon(int slotIndex) {
    if (isWeaponTransitioning()) return;
    if (slotIndex < 0 || slotIndex >= weapons.length) return;
    if (weapons[slotIndex] == null) return;
    if (slotIndex == activeSlotIndex) { showWeapon(activeSlotIndex); return; }

    pendingSlotIndex = slotIndex;
    showWeapon(activeSlotIndex);
    transitionTimer.setWaitTime(1.0 / weapons[pendingSlotIndex].getSwitchSpeed());
    transitionTimer.start();
  }

  @RegisterFunction
  public void onWeaponTransitionComplete() {
    boolean wasArmed = isArmed();
    activeSlotIndex = pendingSlotIndex;
    showWeapon(activeSlotIndex);
    WeaponItem next = weapons[activeSlotIndex];
    if (next != null) {
      animationController.onWeaponEquip(next.weaponPoseIndex);
      ammoChanged.emit(next.getMagazine(), next.getReserve());
    }
    if (wasArmed != isArmed()) emitArmedStateChanged(isArmed());
  }

  @RegisterFunction
  public void onSetStance(Stance stance) {
    for (WeaponItem w : weapons) if (w != null) w.onSetStance(stance);
  }

  // ── Ammo refill ───────────────────────────────────────────────────────────

  public void fillWeaponAmmo() {
    for (WeaponItem w : weapons) if (w != null) w.fillAmmo();
    WeaponItem w = getCurrentWeaponItem();
    if (w != null) ammoChanged.emit(w.getMagazine(), w.getReserve());
  }

  // ── State queries ─────────────────────────────────────────────────────────

  public int     getSlotCount()             { return slotTypes.length; }
  public boolean isSlotFreeFor(WeaponSlotType type) { return findFreeSlot(type) >= 0; }

  /**
   * Returns the first weapon in the given slot type whose weaponId matches.
   * Used by ThrowableItem to find an existing stack for carry-count merging.
   */
  public WeaponItem findWeaponByIdAndType(String weaponId, WeaponSlotType type) {
    for (int i = 0; i < slotTypes.length; i++) {
      if (slotTypes[i] == type && weapons[i] != null
          && weapons[i].weaponId.equals(weaponId)) return weapons[i];
    }
    return null;
  }

  /**
   * Emits ammoChanged for the given weapon if it is currently the active weapon.
   * Called by ThrowableItem after a carry-count merge so the HUD updates immediately.
   */
  public void notifyAmmoChange(WeaponItem forItem) {
    if (forItem != null && forItem == getCurrentWeaponItem()) {
      ammoChanged.emit(forItem.getMagazine(), forItem.getReserve());
    }
  }

  /**
   * Starts the fire timer using the given item's switch speed if it isn't already running.
   * Called by ThrowableItem after a merge pickup so rapid sequential pickups can't chain
   * into an accidental throw when the player holds the fire button.
   */
  public void resetFireTimerForEquip(WeaponItem item) {
    if (fireTimer.getTimeLeft() <= 0) {
      fireTimer.setWaitTime(1.0 / item.getSwitchSpeed());
      fireTimer.start();
    }
  }

  /**
   * Removes the active weapon from its slot without creating a world pickup, clears its
   * character refs, and switches to the next available weapon.
   * Called by ThrowableItem.onMagazineEmpty() after the last grenade is thrown so
   * the THROWABLE slot becomes free for any other throwable type.
   * The active slot is guaranteed to hold the item being emptied — no search needed.
   */
  public void clearActiveSlot() {
    WeaponItem item = weapons[activeSlotIndex];
    if (item == null) return;
    weapons[activeSlotIndex] = null;
    item.setup(null, null, null);
    item.hide();
    item.queueFree();
    activateFirstAvailableSlot();
  }
  public boolean isWeaponReloading()        { return reloadTimer.getTimeLeft() > 0; }
  public boolean isWeaponTransitioning()    { return transitionTimer.getTimeLeft() > 0; }

  public boolean hasAmmoForWeapon(int slotIndex) {
    WeaponItem w = getWeaponItem(slotIndex);
    if (w == null) return false;
    if (w.isInfiniteAmmo) return true;
    return w.getMagazine() > 0 || w.getReserve() > 0;
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  /** First slot index with the given type that has no weapon. -1 if none. */
  private int findFreeSlot(WeaponSlotType type) {
    for (int i = 0; i < slotTypes.length; i++) {
      if (slotTypes[i] == type && weapons[i] == null) return i;
    }
    return -1;
  }

  /** First slot index with the given type, occupied or not. -1 if none configured. */
  private int findFirstSlot(WeaponSlotType type) {
    for (int i = 0; i < slotTypes.length; i++) {
      if (slotTypes[i] == type) return i;
    }
    return -1;
  }

  private EventBus getEventBus() {
    if (eventBus == null) {
      Node n = getNodeOrNull("/root/EventBus");
      if (n instanceof EventBus eb) eventBus = eb;
    }
    return eventBus;
  }

  private void emitArmedStateChanged(boolean armed) {
    EventBus bus = getEventBus();
    if (bus != null) bus.armedStateChanged.emit(getOwner(), armed);
  }

  /**
   * Replaces the AimRay used by the currently equipped weapon with {@code vehicleRay}.
   * Saves the original ray so {@link #restoreAimRay()} can undo the swap.
   * Called by Vehicle when PASSENGER_WEAPON occupant enters so the weapon fires along
   * the vehicle camera's forward direction rather than the character's camera ray.
   */
  public void overrideAimRay(RayCast3D vehicleRay) {
    originalAimRay = aimRay;
    aimRay = vehicleRay;
  }

  /** Restores the character's original AimRay after exiting PASSENGER_WEAPON mode. */
  public void restoreAimRay() {
    if (originalAimRay == null) return;
    aimRay = originalAimRay;
    originalAimRay = null;
  }

  private void injectCharacterRefs(WeaponItem item) {
    CharacterBody3D character = getOwner() instanceof CharacterBody3D c ? c : null;
    item.setup(this, character, weaponAudio);
  }

  private void showWeapon(int slotIndex) {
    for (int i = 0; i < weapons.length; i++) {
      if (weapons[i] == null) continue;
      if (i == slotIndex) moveWeaponToHand(weapons[i]);
      else moveWeaponToHolster(weapons[i]);
    }
  }

  /** Returns the Marker3D registered under {@code socketName}, or null if not found. */
  private Node resolveSocket(String socketName) {
    return (socketName == null || socketName.isEmpty()) ? null : socketMap.get(socketName);
  }

  /** Reparents {@code item} to its holdSocket Marker3D and shows it.
   *  Items with no holdSocket (e.g. throwables) stay in the world scene where Jolt already
   *  registered their physics body; onPickedUp() already hid them, so just keep hidden. */
  private void moveWeaponToHand(WeaponItem item) {
    Node target = resolveSocket(item.holdSocket);
    if (target != null) {
      reparentWeapon(item, target);
      item.show();
    } else {
      item.hide();
    }
  }

  /** Reparents {@code item} to the first free socket in its holsterSockets list and shows it.
   *  A socket is considered free when it has no children or already holds this weapon.
   *  Items with no holster sockets stay in the world scene (hidden); do NOT reparent them
   *  to the owner — moving a frozen RigidBody3D confuses Jolt's body position and causes
   *  the item to clip through the ground when it is returned to the world later. */
  private void moveWeaponToHolster(WeaponItem item) {
    for (String socketName : item.holsterSockets) {
      Node target = resolveSocket(socketName);
      if (target == null) continue;
      if (target.getChildCount() > 0 && !target.getChild(0).equals(item)) continue;
      reparentWeapon(item, target);
      item.show();
      return;
    }
    item.hide();
  }

  /** Reparents {@code item} to {@code target}, zeroing local transform. Skips reparent
   *  if {@code item} is already a child of {@code target} to avoid re-triggering _ready. */
  private void reparentWeapon(WeaponItem item, Node target) {
    Node current = item.getParent();
    if (current != null && current.equals(target)) return;
    item.reparent(target, false);
    item.setPosition(Vector3.Companion.getZERO());
    item.setRotation(Vector3.Companion.getZERO());
  }

  // Manual drop: throw forward at chest height (1.3 m gives clearance when crouching/crawling).
  private void returnWeaponToWorld(WeaponItem item) {
    CharacterBody3D character = (CharacterBody3D) getOwner();
    Vector3 spawnPos = character.getGlobalPosition().plus(new Vector3(0, 1.3f, 0));
    Vector3 forward  = character.getGlobalTransform().getBasis().getZ().times(-1f);
    Vector3 impulse  = forward.times(3.0f)
        .plus(new Vector3(0, 4.0f, 0))
        .plus(character.getVelocity().times(0.3f));
    returnWeaponToWorld(item, spawnPos, impulse);
  }

  // Death drop: spawn higher (1.5 m) and scatter each weapon in a random direction
  // so multiple weapons fan out instead of piling on the same spot.
  private void returnWeaponToWorldOnDeath(WeaponItem item) {
    CharacterBody3D character = (CharacterBody3D) getOwner();
    Vector3 spawnPos = character.getGlobalPosition().plus(new Vector3(0, 1.5f, 0));
    float   angle    = GD.randf() * (float) (Math.PI * 2.0);
    Vector3 scatter  = new Vector3((float) Math.cos(angle), 0f, (float) Math.sin(angle)).times(2.5f);
    Vector3 impulse  = scatter
        .plus(new Vector3(0, (float) GD.randfRange(3.0f, 6.0f), 0))
        .plus(character.getVelocity().times(0.4f));
    returnWeaponToWorld(item, spawnPos, impulse);
  }

  /**
   * Shared mechanics for both drop variants: clears character refs, re-enables physics,
   * places the weapon at spawnPos, and applies impulse.
   *
   * Throwables (and any weapon without a socket) stay in the world scene while equipped
   * (frozen, hidden), so reparent is a no-op for them — skipping it avoids the
   * same-parent reparent edge-case. Socket-based weapons live under a Marker3D and need
   * to be moved back.
   * Jolt Physics does not reliably propagate setGlobalPosition on a frozen body, so
   * onReturnedToWorld() unfreezes before we set position.
   */
  private void returnWeaponToWorld(WeaponItem item, Vector3 spawnPos, Vector3 impulse) {
    item.setup(null, null, null);
    item.show();
    Node currentScene = getTree().getCurrentScene();
    if (!currentScene.equals(item.getParent())) {
      item.reparent(currentScene, true);
    }
    item.onReturnedToWorld();
    item.setGlobalPosition(spawnPos);
    // Reset any residual velocity from the frozen/equipped state before applying
    // the intended throw impulse, otherwise the weapon can tunnel through thin floors.
    item.setLinearVelocity(Vector3.Companion.getZERO());
    item.setAngularVelocity(Vector3.Companion.getZERO());
    item.applyCentralImpulse(impulse);
  }

  // After a drop, fall back to fist (slot 0) which is always available.
  private void activateFirstAvailableSlot() {
    for (int i = 0; i < weapons.length; i++) {
      if (weapons[i] != null) { onSetWeapon(i); return; }
    }
    ammoChanged.emit(0, 0);
  }

  private void emitInitialAmmoState() {
    WeaponItem w = getCurrentWeaponItem();
    if (w != null) ammoChanged.emit(w.getMagazine(), w.getReserve());
    else ammoChanged.emit(0, 0);
  }
}
