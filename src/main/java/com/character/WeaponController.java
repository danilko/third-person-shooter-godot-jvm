package com.character;

import com.game.EventBus;
import godot.annotation.*;
import godot.api.*;
import godot.core.NodePath;
import godot.core.Signal1;
import godot.core.Signal2;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;
import java.util.ArrayList;
import java.util.List;

@RegisterClass(className = "WeaponController")
public class WeaponController extends Node {

  @RegisterProperty @Export public AnimationController animationController;

  @RegisterProperty @Export
  public NodePath aimRayPath = new NodePath("CameraRoot/Yaw/Pitch/Pivot/SpringArm/Camera/AimRay");

  @RegisterProperty @Export
  public NodePath cameraControllerPath = new NodePath("CameraRoot");

  @RegisterProperty @Export
  public NodePath weaponAttachmentPath = new NodePath("MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/WeaponAttachment");

  @RegisterSignal
  public final Signal1<Float> weaponFired = new Signal1<>(this, new StringName("weapon_fired"));

  @RegisterSignal
  public final Signal2<Integer, Integer> ammoChanged = new Signal2<>(this, new StringName("ammo_changed"));

  @RegisterProperty @Export public AudioStreamPlayer3D weaponAudio;
  @RegisterProperty @Export public BoneAttachment3D neckBoneAttachement;

  /**
   * Defines the type of each slot by index.
   * Override in a subclass or replace in _ready() before calling super to customise
   * the layout — e.g. add a second PRIMARY slot by inserting WeaponSlotType.PRIMARY
   * at position 1 and shifting the rest.
   */
  protected WeaponSlotType[] slotTypes = {
      WeaponSlotType.PRIMARY,
      WeaponSlotType.SECONDARY,
      WeaponSlotType.MELEE,
      WeaponSlotType.THROWABLE,
      WeaponSlotType.OFFHAND
  };

  private WeaponItem[] weapons;
  private int activeSlotIndex  = 0;
  private int pendingSlotIndex = 0;

  // Weapons queued for equip/drop; processed in _process (idle) to avoid
  // reparenting a RigidBody3D (CollisionObject) during a physics callback.
  private final List<WeaponItem> pendingEquips = new ArrayList<>();
  private final List<WeaponItem> pendingDrops  = new ArrayList<>();
  // True when pendingDrops was populated by dropAllWeapons() (death); false for a
  // manual single-weapon drop. Controls which physics parameters are used.
  private boolean isDeathDrop = false;

  private RayCast3D aimRay;
  private CameraController cam;

  private Timer transitionTimer;
  private Timer fireTimer;
  private Timer reloadTimer;

  // ── Accessors ─────────────────────────────────────────────────────────────

  public int getWeapon() { return activeSlotIndex; }

  public WeaponItem getCurrentWeaponStats() { return getCurrentWeaponItem(); }

  public WeaponItem getCurrentWeaponItem() {
    return weapons[activeSlotIndex];
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
    Node camNode = getOwner().getNode(cameraControllerPath);
    if (camNode instanceof CameraController c) cam = c;

    // Discover weapons pre-placed inside attachment markers in the scene
    Node attachment = getOwner().getNodeOrNull(weaponAttachmentPath);
    if (attachment != null) for (Node child : attachment.getChildren()) {
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

    if (weapons[activeSlotIndex] != null) weapons[activeSlotIndex].show();

    if (neckBoneAttachement != null) {
      ((AnimationPlayer) neckBoneAttachement.getNode("AnimationPlayer")).play("MuzzleFlash");
    }

    emitInitialAmmoState();
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

    Node attachment = getOwner().getNodeOrNull(weaponAttachmentPath);
    if (attachment == null) return;

    String markerKey = item.weaponId.isEmpty() ? item.weaponName : item.weaponId;
    Node marker = markerKey.isEmpty() ? null : attachment.getNodeOrNull(new NodePath("Marker" + markerKey));
    Node target = (marker != null) ? marker : attachment;

    item.onPickedUp();
    item.reparent(target, false);
    item.setPosition(Vector3.Companion.getZERO());
    item.setRotation(Vector3.Companion.getZERO());
    injectCharacterRefs(item);

    weapons[targetSlot] = item;

    if (targetSlot == activeSlotIndex || weapons[activeSlotIndex] == null) {
      activeSlotIndex = targetSlot;
      showWeapon(activeSlotIndex);
      animationController.onWeaponTransition(item.weaponPoseIndex, true);
      ammoChanged.emit(item.getMagazine(), item.getReserve());
    } else {
      item.hide();
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
    if (slotIndex < 0 || slotIndex >= weapons.length) return;
    if (weapons[slotIndex] == null) return;
    if (slotIndex == activeSlotIndex) { showWeapon(activeSlotIndex); return; }

    pendingSlotIndex = slotIndex;
    showWeapon(activeSlotIndex);
    WeaponItem current = weapons[activeSlotIndex];
    if (current != null) animationController.onWeaponTransition(current.weaponPoseIndex, false);
    transitionTimer.setWaitTime(1.0 / weapons[pendingSlotIndex].getSwitchSpeed());
    transitionTimer.start();
  }

  @RegisterFunction
  public void onWeaponTransitionComplete() {
    activeSlotIndex = pendingSlotIndex;
    showWeapon(activeSlotIndex);
    WeaponItem next = weapons[activeSlotIndex];
    if (next != null) animationController.onWeaponTransition(next.weaponPoseIndex, true);
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

  private void injectCharacterRefs(WeaponItem item) {
    if (item instanceof FirearmItem fi) {
      fi.setup((CharacterBody3D) getOwner(), aimRay, cam, neckBoneAttachement, weaponAudio);
    }
  }

  private void showWeapon(int slotIndex) {
    for (int i = 0; i < weapons.length; i++) {
      if (weapons[i] != null) {
        if (i == slotIndex) weapons[i].show();
        else weapons[i].hide();
      }
    }
  }

  // Manual drop: throw forward at chest height (1.0 m).
  private void returnWeaponToWorld(WeaponItem item) {
    CharacterBody3D character = (CharacterBody3D) getOwner();
    Vector3 spawnPos = character.getGlobalPosition().plus(new Vector3(0, 1.0f, 0));
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
    if (item instanceof FirearmItem fi) fi.setup(null, null, null, null, null);
    item.show();
    item.reparent(getTree().getCurrentScene(), true);
    item.onReturnedToWorld();
    item.setGlobalPosition(spawnPos);
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
