package com.character;

import com.game.EventBus;
import godot.annotation.*;
import godot.api.*;
import godot.core.NodePath;
import godot.core.Signal1;
import godot.core.Signal2;
import godot.core.StringName;
import godot.core.VariantArray;
import godot.core.Vector3;
import godot.global.GD;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

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
  @RegisterProperty @Export public BoneAttachment3D neckBoneAttachement;

  /**
   * Defines the type of each slot by index.
   * Layout: two PRIMARY, one SECONDARY, one MELEE, one THROWABLE, one CONSUMABLE, one OFFHAND.
   * Override in a subclass or replace in _ready() before calling super to customise.
   */
  protected WeaponSlotType[] slotTypes = {
      WeaponSlotType.PRIMARY,     // slot 0 — first long weapon   (key 1)
      WeaponSlotType.PRIMARY,     // slot 1 — second long weapon  (key 2)
      WeaponSlotType.SECONDARY,   // slot 2 — sidearm             (key 3)
      WeaponSlotType.MELEE,       // slot 3 — melee               (key 4)
      WeaponSlotType.THROWABLE,   // slot 4 — throwable           (key 5)
      WeaponSlotType.CONSUMABLE,  // slot 5 — health / consumable (key 6)
      WeaponSlotType.OFFHAND,     // slot 6 — shield / torch      (key 0)
  };

  private WeaponItem[] weapons;
  private int     activeSlotIndex  = 0;
  private int     pendingSlotIndex = 0;
  private boolean isUnarmed        = false;

  // Weapons queued for equip/drop; processed in _process (idle) to avoid
  // reparenting a RigidBody3D (CollisionObject) during a physics callback.
  private final List<WeaponItem> pendingEquips = new ArrayList<>();
  private final List<WeaponItem> pendingDrops  = new ArrayList<>();
  // True when pendingDrops was populated by dropAllWeapons() (death); false for a
  // manual single-weapon drop. Controls which physics parameters are used.
  private boolean isDeathDrop = false;

  // Populated in _ready() from socketPaths: node name → Marker3D node.
  private final Map<String, Node> socketMap = new HashMap<>();

  private RayCast3D aimRay;
  private RayCast3D originalAimRay;

  private Timer transitionTimer;
  private Timer fireTimer;
  private Timer reloadTimer;

  // ── Accessors ─────────────────────────────────────────────────────────────

  public int getWeapon() { return isUnarmed ? -1 : activeSlotIndex; }

  public boolean isUnarmed() { return isUnarmed; }

  public WeaponItem getCurrentWeaponStats() { return getCurrentWeaponItem(); }

  public WeaponItem getCurrentWeaponItem() {
    return isUnarmed ? null : weapons[activeSlotIndex];
  }

  public int getWeaponCount() {
    int n = 0;
    for (WeaponItem w : weapons) if (w != null) n++;
    return n;
  }

  public WeaponItem getWeaponStats(int slotIndex) { return getWeaponItem(slotIndex); }

  public WeaponItem getWeaponItem(int slotIndex) {
    if (slotIndex < 0 || slotIndex >= weapons.length) return null;
    return weapons[slotIndex];
  }

  public float getCurrentSpreadDeg() {
    WeaponItem w = getCurrentWeaponItem();
    return w != null ? w.getCurrentSpreadDeg() : 0f;
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @RegisterFunction
  @Override
  public void _process(double delta) {
    // Process equips first (deferred from Area3D body_entered signals)
    if (!pendingEquips.isEmpty()) {
      for (WeaponItem item : new ArrayList<>(pendingEquips)) equipWeapon(item);
      pendingEquips.clear();
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

    // Build socket registry from legacy owner-relative paths (no CharacterVisuals).
    // When using CharacterVisuals, Character._ready() calls postInitFromVisuals() instead.
    if (!socketPaths.isEmpty()) {
      for (java.lang.Object obj : socketPaths) {
        NodePath p = (NodePath) obj;
        if (p == null || p.toString().isEmpty()) continue;
        Node socket = getOwner().getNodeOrNull(p);
        if (socket != null) socketMap.put(socket.getName().toString(), socket);
      }

      // Discover weapons pre-placed inside attachment markers in the scene.
      discoverPrePlacedWeapons(getOwner(), weaponAttachmentPath);
      showWeapon(activeSlotIndex);
    }

    if (neckBoneAttachement != null) {
      ((AnimationPlayer) neckBoneAttachement.getNode("AnimationPlayer")).play("MuzzleFlash");
    }

    emitInitialAmmoState();
  }

  /**
   * Wires all mesh-dependent references from a newly instantiated CharacterVisuals scene.
   * Called by Character._ready() after addChild(visualsInstance) and after setting
   * neckBoneAttachement.  Safe to call with a null config (no-op).
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

    // Start muzzle-flash loop now that neckBoneAttachement is resolved.
    if (neckBoneAttachement != null) {
      Node apNode = neckBoneAttachement.getNodeOrNull("AnimationPlayer");
      if (apNode instanceof AnimationPlayer ap) ap.play("MuzzleFlash");
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
   */
  public void equipWeapon(WeaponItem item) {
    WeaponSlotType type = item.getSlotType();
    int targetSlot = findFreeSlot(type);
    if (targetSlot < 0) targetSlot = findFirstSlot(type);
    if (targetSlot < 0) return;

    WeaponItem displaced = weapons[targetSlot];
    boolean willBeActive = isUnarmed || targetSlot == activeSlotIndex || weapons[activeSlotIndex] == null;

    item.onPickedUp();
    injectCharacterRefs(item);
    weapons[targetSlot] = item;

    if (willBeActive) {
      isUnarmed = false;
      activeSlotIndex = targetSlot;
      moveWeaponToHand(item);
      if (item.getReloadAudio() != null) {
        weaponAudio.setStream(item.getReloadAudio());
        weaponAudio.play();
      }
      animationController.onWeaponEquip(item.weaponPoseIndex);
      ammoChanged.emit(item.getMagazine(), item.getReserve());
    } else {
      // Weapon goes into an inactive slot — mount at its holster socket.
      moveWeaponToHolster(item);
      WeaponItem active = getCurrentWeaponItem();
      ammoChanged.emit(active != null ? active.getMagazine() : 0,
                       active != null ? active.getReserve()  : 0);
    }

    Node busNode = getNodeOrNull("/root/EventBus");
    if (busNode instanceof EventBus bus) {
      String characterId = (getOwner() instanceof Character c && c.characterInfo != null)
          ? c.characterInfo.characterId : "";
      bus.weaponPickedUp.emit(characterId, item.getDisplayName(), item.weaponIcon);
    }

    if (displaced != null) returnWeaponToWorld(displaced);
  }

  /**
   * Removes the currently active weapon from the inventory and returns it to the
   * world at the character's feet with a throw impulse.
   */
  @RegisterFunction
  public void dropCurrentWeapon() {
    WeaponItem current = weapons[activeSlotIndex];
    if (current == null) return;
    weapons[activeSlotIndex] = null;
    current.hide();       // hide immediately — reparent is deferred to _process
    pendingDrops.add(current);
    activateFirstAvailableSlot();
  }

  /**
   * Releases every carried weapon back into the world. Called on character death.
   * Safe to invoke from a physics callback — actual reparenting is deferred to _process().
   * Each weapon spawns at hip height + 0.5 m extra and is thrown in a random radial
   * direction so weapons fan out rather than pile on one spot.
   */
  public void dropAllWeapons() {
    for (int i = 0; i < weapons.length; i++) {
      WeaponItem item = weapons[i];
      if (item == null) continue;
      weapons[i] = null;
      item.hide();
      pendingDrops.add(item);
    }
    isDeathDrop = true;
  }

  // ── Signal handlers ───────────────────────────────────────────────────────

  @RegisterFunction
  public void onWeaponFire() {
    if (fireTimer.getTimeLeft() > 0 || reloadTimer.getTimeLeft() > 0) return;
    WeaponItem w = getCurrentWeaponItem();
    if (w == null) return;
    if (w.getMagazine() == 0) { onWeaponReload(); return; }
    if (!w.canUse()) return;

    fireTimer.setWaitTime(1.0 / w.getFireRate());
    fireTimer.start();

    w.useWeapon();
    weaponFired.emit(w.getFireRate() * 0.2f);
    ammoChanged.emit(w.getMagazine(), w.getReserve());
  }

  @RegisterFunction
  public void onWeaponNotFire() {
    WeaponItem w = getCurrentWeaponItem();
    if (w != null) w.stopUseWeapon();
  }

  @RegisterFunction
  public void onWeaponReload() {
    WeaponItem w = getCurrentWeaponItem();
    if (w == null || w.getReserve() == 0 || isWeaponReloading()) return;
    reloadTimer.setWaitTime(1.0 / w.getReloadSpeed());
    if (w.getReloadAudio() != null) {
      weaponAudio.setStream(w.getReloadAudio());
      weaponAudio.play();
    }
    reloadTimer.start();
    animationController.onWeaponReload();
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
    if (slotIndex == -1) { unequipCurrent(); return; }
    if (slotIndex < 0 || slotIndex >= weapons.length) return;
    if (weapons[slotIndex] == null) return;

    if (isUnarmed) {
      // Re-equip from empty hands — skip put-down animation, just draw the new weapon.
      isUnarmed = false;
      pendingSlotIndex = slotIndex;
      transitionTimer.setWaitTime(1.0 / weapons[pendingSlotIndex].getSwitchSpeed());
      transitionTimer.start();
      return;
    }

    if (slotIndex == activeSlotIndex) { showWeapon(activeSlotIndex); return; }

    pendingSlotIndex = slotIndex;
    showWeapon(activeSlotIndex);
    transitionTimer.setWaitTime(1.0 / weapons[pendingSlotIndex].getSwitchSpeed());
    transitionTimer.start();
  }

  private void unequipCurrent() {
    if (isUnarmed) return;
    isUnarmed = true;
    showWeapon(-1);
    ammoChanged.emit(0, 0);
  }

  @RegisterFunction
  public void onWeaponTransitionComplete() {
    activeSlotIndex = pendingSlotIndex;
    showWeapon(activeSlotIndex);
    WeaponItem next = weapons[activeSlotIndex];
    if (next != null) animationController.onWeaponEquip(next.weaponPoseIndex);
    if (next != null) ammoChanged.emit(next.getMagazine(), next.getReserve());
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

  public int  getSlotCount()             { return slotTypes.length; }
  public boolean isSlotFreeFor(WeaponSlotType type) { return findFreeSlot(type) >= 0; }
  public boolean isWeaponReloading()     { return reloadTimer.getTimeLeft() > 0; }
  public boolean isWeaponTransitioning() { return transitionTimer.getTimeLeft() > 0; }

  public boolean hasAmmoForWeapon(int slotIndex) {
    WeaponItem w = getWeaponItem(slotIndex);
    return w != null && (w.getMagazine() > 0 || w.getReserve() > 0);
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

  /**
   * Replaces the AimRay used by the currently equipped weapon with {@code vehicleRay}.
   * Saves the original ray so {@link #restoreAimRay()} can undo the swap.
   * Called by Vehicle when PASSENGER_WEAPON occupant enters so the weapon fires along
   * the vehicle camera's forward direction rather than the character's camera ray.
   */
  public void overrideAimRay(RayCast3D vehicleRay) {
    originalAimRay = aimRay;
    aimRay = vehicleRay;
    injectCharacterRefs(getCurrentWeaponItem());
  }

  /** Restores the character's original AimRay after exiting PASSENGER_WEAPON mode. */
  public void restoreAimRay() {
    if (originalAimRay == null) return;
    aimRay = originalAimRay;
    originalAimRay = null;
    injectCharacterRefs(getCurrentWeaponItem());
  }

  private void injectCharacterRefs(WeaponItem item) {
    if (item instanceof FirearmItem fi) {
      fi.setup((CharacterBody3D) getOwner(), aimRay, neckBoneAttachement, weaponAudio);
    }
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
   *  If holdSocket is empty or not registered, shows the weapon at its current position. */
  private void moveWeaponToHand(WeaponItem item) {
    Node target = resolveSocket(item.holdSocket);
    if (target != null) reparentWeapon(item, target);
    item.show();
  }

  /** Reparents {@code item} to the first free socket in its holsterSockets list and shows it.
   *  A socket is considered free when it has no children or already holds this weapon.
   *  Hides the weapon if the list is empty, none of the names are registered, or all
   *  registered sockets are occupied by other weapons. */
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
   * keepGlobalTransform=true so the weapon stays at its hand position in world space
   * after reparent. Jolt Physics does not reliably propagate setGlobalPosition on a
   * frozen body, so onReturnedToWorld() unfreezes before we set position.
   */
  private void returnWeaponToWorld(WeaponItem item, Vector3 spawnPos, Vector3 impulse) {
    if (item instanceof FirearmItem fi) fi.setup(null, null, null, null);
    item.show();
    item.reparent(getTree().getCurrentScene(), true);
    item.onReturnedToWorld();
    item.setGlobalPosition(spawnPos);
    // Reset any residual velocity from the frozen/equipped state before applying
    // the intended throw impulse, otherwise the weapon can tunnel through thin floors.
    item.setLinearVelocity(Vector3.Companion.getZERO());
    item.setAngularVelocity(Vector3.Companion.getZERO());
    item.applyCentralImpulse(impulse);
  }

  private void activateFirstAvailableSlot() {
    for (int i = 0; i < weapons.length; i++) {
      if (weapons[i] != null) {
        onSetWeapon(i);
        return;
      }
    }
    // No weapons remain — clear HUD ammo display
    ammoChanged.emit(0, 0);
  }

  private void emitInitialAmmoState() {
    WeaponItem w = getCurrentWeaponItem();
    if (w != null) ammoChanged.emit(w.getMagazine(), w.getReserve());
    else ammoChanged.emit(0, 0);
  }
}