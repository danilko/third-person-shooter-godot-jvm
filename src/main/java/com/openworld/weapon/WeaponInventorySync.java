package com.openworld.weapon;

import godot.api.Node;
import godot.api.PackedScene;
import godot.core.StringName;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Inventory state reconciliation (Round 11 N2 — MSG_INVENTORY), split out of {@link WeaponController} as a
 * plain-Java collaborator (PLAN.md 2.8 item 5).
 *
 * <p>The event-replicated inventory (MSG_PICKUP_TAKEN / MSG_WEAPON_DROPPED) can diverge permanently from a
 * single missed/raced event, and some inventory was never event-replicated at all (AI rifles equipped at
 * runtime via requestEquip). The host periodically broadcasts each character's authoritative slot
 * manifest; this builds it (host side) and reconciles toward it (receiver side). Behaviour unchanged.
 */
final class WeaponInventorySync {

  private final WeaponController wc;

  WeaponInventorySync(WeaponController wc) { this.wc = wc; }

  //
  // The event-replicated inventory (MSG_PICKUP_TAKEN / MSG_WEAPON_DROPPED) can diverge
  // permanently from a single missed/raced event, and some inventory was never
  // event-replicated at all (AI rifles equipped at runtime via requestEquip). The host
  // periodically broadcasts each character's authoritative slot manifest; this pair
  // builds it (host side) and reconciles toward it (receiver side).

  /** Maximum pickupId length the wire accepts (NetworkManager.MAX_STRING_LENGTH) — oversized path-derived loadout ids are sent as "" (receiver keeps its local id). */
  static final int MAX_WIRE_ID_LENGTH = 64;

  /** Host side: snapshot of every occupied slot (slot 0/fist excluded — permanent scene furniture). */
  List<com.openworld.net.NetMessageCodec.InventorySlotEntry> buildInventoryEntries() {
    List<com.openworld.net.NetMessageCodec.InventorySlotEntry> entries = new ArrayList<>();
    for (int slot = 1; slot < wc.weapons.length; slot++) {
      WeaponItem w = wc.weapons[slot];
      if (w == null) continue;
      String scenePath = w.getSceneFilePath();
      String pickupId = (w.pickupId != null && !w.pickupId.isEmpty() && w.pickupId.length() <= MAX_WIRE_ID_LENGTH)
          ? w.pickupId : "";
      entries.add(new com.openworld.net.NetMessageCodec.InventorySlotEntry(slot,
          w.weaponId != null ? w.weaponId : "",
          scenePath != null ? scenePath : "",
          pickupId, w.getMagazine(), w.getReserve()));
    }
    return entries;
  }

  /**
   * Receiver side: reconcile this character's slots toward the host's manifest.
   *
   * <p>{@code addOnly} is true for the body this peer OWNS: its inventory is driven by its
   * own input plus the reliable event echoes, and overwriting it from a (lag-stale) manifest
   * would re-create the Round 10.2 echo feedback loop — so for owned bodies we only converge
   * pickupId on a matching slot, never remove items, touch ammo, or resurrect a slot the owner
   * emptied (the throwable-restock fix — see the loop body). Non-owned puppets reconcile fully:
   * match per slot by
   * weaponId, converge ammo + pickupId on match, equip from the manifest on mismatch
   * (preferring the matching local world pickup over instantiating a duplicate), and discard
   * local extras WITHOUT dropping them to the world (a reconcile drop would spawn orphan,
   * unsynced pickups).
   *
   * <p>Skipped entirely while local equips/drops are still queued — the manifest was built
   * before them and would fight their outcome; the next sweep (~300 ms) reconciles cleanly.
   */
  void applyReplicatedInventory(List<com.openworld.net.NetMessageCodec.InventorySlotEntry> entries, boolean addOnly) {
    if (!wc.pendingEquips.isEmpty() || !wc.pendingDrops.isEmpty()) {
      com.openworld.net.NetStats.increment("inventory_apply_deferred");
      return;
    }
    Map<Integer, com.openworld.net.NetMessageCodec.InventorySlotEntry> bySlot = new HashMap<>();
    for (com.openworld.net.NetMessageCodec.InventorySlotEntry e : entries) bySlot.put(e.slot(), e);

    for (int slot = 1; slot < wc.weapons.length; slot++) {
      com.openworld.net.NetMessageCodec.InventorySlotEntry entry = bySlot.get(slot);
      WeaponItem local = wc.weapons[slot];

      if (entry == null) {
        if (local != null && !addOnly) {
          com.openworld.net.NetStats.increment("inventory_reconciled_remove");
          discardSlotItem(slot);
        }
        continue;
      }

      if (local != null) {
        if (manifestMatches(local, entry)) {
          if (!addOnly) {
            local.setMagazine(entry.magazine());
            local.setReserve(entry.reserve());
            wc.notifyAmmoChange(local);
          }
          if (!entry.pickupId().isEmpty()) local.pickupId = entry.pickupId();
          continue;
        }
        if (addOnly) continue;   // owned body: never displace what the owner is holding
        com.openworld.net.NetStats.increment("inventory_reconciled_replace");
        discardSlotItem(slot);
      }

      // Reached only when the slot is locally empty but the manifest lists an item.
      // For an OWNED body, do NOT resurrect it: an owned body's slot presence is driven by
      // its own input and the RELIABLE, ordered grant/drop events — never by a lag-stale
      // manifest. This was the throwable-restock bug: a client throws its last grenade and
      // clears the slot, but the host's copy hasn't caught the throw (consumption rides no
      // reliable event, and the active-magazine snapshot can't carry the same-frame
      // slot-clear), so its manifest still lists the stack and the next sweep re-instantiated
      // it. The owner's inventory is restored on (re)join by baseline spawns + pickups, not by
      // this path; AI inventory is non-owned (full reconcile), so its runtime rifle still heals.
      if (addOnly) {
        com.openworld.net.NetStats.increment("inventory_owned_no_resurrect");
        continue;
      }
      equipReconciled(slot, entry);
    }
  }

  /** Same item identity? weaponId is the designed key; scenePath is the fallback for items with no id set. */
  boolean manifestMatches(WeaponItem local, com.openworld.net.NetMessageCodec.InventorySlotEntry entry) {
    String localId = local.weaponId != null ? local.weaponId : "";
    if (!localId.isEmpty() || !entry.weaponId().isEmpty()) return localId.equals(entry.weaponId());
    String localScene = local.getSceneFilePath();
    return localScene != null && localScene.equals(entry.scenePath());
  }

  /**
   * Removes a slot's item during reconciliation — clears refs and frees it, never returns
   * it to the world (the manifest says the authority doesn't have it; a world drop here
   * would create an orphan pickup no other peer knows about).
   */
  void discardSlotItem(int slot) {
    WeaponItem item = wc.weapons[slot];
    if (item == null) return;
    boolean wasActive = slot == wc.activeSlotIndex;
    wc.weapons[slot] = null;
    item.setup(null, null, null);
    item.hide();
    item.queueFree();
    if (wasActive) wc.activateFirstAvailableSlot();
  }

  /**
   * Materialises a manifest entry into {@code slot}: prefer adopting the matching local
   * world pickup by the manifest's pickupId (kills the ghost-pickup case when healing a
   * lost grant echo), else instantiate the validated weapon scene — the same
   * add-to-tree-then-equip shape DebugHarness.equipDebugRifle uses. Runs at idle time
   * (NetworkManager._process), where the item's world body can be taken away and rebuilt.
   */
  void equipReconciled(int slot, com.openworld.net.NetMessageCodec.InventorySlotEntry entry) {
    WeaponItem item = findWorldPickupById(entry.pickupId());
    if (item == null) item = instantiateWeaponScene(entry.scenePath());
    if (item == null) {
      com.openworld.net.NetStats.increment("inventory_equip_failed");
      GD.print("WeaponController: inventory reconcile could not materialise '" + entry.weaponId()
          + "' (scene '" + entry.scenePath() + "') for slot " + slot + " on '" + wc.getOwner().getName() + "'");
      return;
    }
    if (!entry.pickupId().isEmpty()) item.pickupId = entry.pickupId();
    item.setMagazine(entry.magazine());
    item.setReserve(entry.reserve());
    item.onPickedUp();
    wc.injectCharacterRefs(item);
    wc.weapons[slot] = item;
    if (slot == wc.activeSlotIndex) {
      wc.sockets.moveWeaponToHand(item);
      if (wc.animationController != null) wc.animationController.onWeaponEquip(item.weaponPoseIndex());
      wc.ammoChanged.emit(item.getMagazine(), item.getReserve());
    } else {
      wc.sockets.moveWeaponToHolster(item);
    }
    com.openworld.net.NetStats.increment("inventory_reconciled_equip");
  }

  /** Resolves a manifest pickupId to an un-taken WeaponItem in the world "pickups" group, or null. */
  WeaponItem findWorldPickupById(String pickupId) {
    if (pickupId == null || pickupId.isEmpty() || wc.getTree() == null) return null;
    for (Node node : wc.getTree().getNodesInGroup(new StringName(com.openworld.item.Pickup.PICKUPS_GROUP))) {
      if (node instanceof WeaponItem w && pickupId.equals(w.pickupId) && !w.isTaken()) return w;
    }
    return null;
  }

  /** Loads + instantiates a manifest weapon scene into the current scene tree (must be in-tree before socket reparenting). Path already validated by NetworkManager.isValidInventory. */
  WeaponItem instantiateWeaponScene(String scenePath) {
    if (scenePath == null || scenePath.isEmpty()) return null;
    java.lang.Object loaded = GD.load(scenePath);
    if (!(loaded instanceof PackedScene scene)) return null;
    Node instance = scene.instantiate();
    if (!(instance instanceof WeaponItem item)) {
      instance.queueFree();
      return null;
    }
    wc.getTree().getCurrentScene().addChild(item);
    return item;
  }

}
