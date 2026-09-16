package com.openworld.weapon;

import godot.api.Node;
import godot.global.GD;

/**
 * Where a carried weapon hangs — the hand socket, a free holster socket, or stowed hidden on the character
 * (PLAN.md 2.8 item 5: a plain-Java collaborator split out of {@link WeaponController}, the
 * {@code CharacterRagdoll} precedent). The controller owns the socket map and the stow node; this owns the
 * placement rules. Behaviour is unchanged from when these were private methods on the controller.
 */
final class WeaponSockets {

  private final WeaponController wc;

  WeaponSockets(WeaponController wc) { this.wc = wc; }

  void showWeapon(int slotIndex) {
    for (int i = 0; i < wc.weapons.length; i++) {
      if (wc.weapons[i] == null) continue;
      if (i == slotIndex) moveWeaponToHand(wc.weapons[i]);
      else moveWeaponToHolster(wc.weapons[i]);
    }
  }

  /** Returns the Marker3D registered under {@code socketName}, or null if not found. */
  Node resolveSocket(String socketName) {
    return (socketName == null || socketName.isEmpty()) ? null : wc.socketMap.get(socketName);
  }

  /** Reparents {@code item} to its holdSocket Marker3D and shows it. An item with no holdSocket
   *  (a throwable) is stowed on the character, hidden — see {@link #stowWeapon}. */
  void moveWeaponToHand(WeaponItem item) {
    Node target = resolveSocket(item.holdSocket);
    if (target != null) {
      reparentWeapon(item, target, false);
      item.show();
    } else {
      stowWeapon(item);
    }
  }

  /** Reparents {@code item} to the first free socket in its holsterSockets list and shows it.
   *  A socket is considered free when it has no children or already holds this weapon.
   *  An item with no free holster socket is stowed on the character, hidden. */
  void moveWeaponToHolster(WeaponItem item) {
    for (String socketName : item.holsterSockets) {
      Node target = resolveSocket(socketName);
      if (target == null) continue;
      if (target.getChildCount() > 0 && !target.getChild(0).equals(item)) continue;
      reparentWeapon(item, target, true);
      item.show();
      return;
    }
    stowWeapon(item);
  }

  /**
   * Park a carried weapon that has no socket to show it at: hidden, on the character's weapon
   * attachment. It must GO somewhere — leaving it in the world scene is what the old frozen-body
   * workaround did, and a throwable carried that way sat invisible at wherever it was collected,
   * with a stale transform that nothing dared read.
   */
  void stowWeapon(WeaponItem item) {
    item.hide();
    if (wc.stowNode != null && GD.isInstanceValid(wc.stowNode) && !wc.stowNode.equals(item.getParent())) {
      item.reparent(wc.stowNode, false);
      item.setTransform(new godot.core.Transform3D());
    }
  }

  /**
   * Reparents {@code item} to {@code target} and aligns it. Skips the reparent if {@code item} is
   * already a child of {@code target}, to avoid re-triggering {@code _ready}.
   *
   * <p>The alignment is the WEAPON's to state ({@code WeaponItem.alignmentFor}): a weapon that
   * declares a {@code GripPoint} puts THAT point on the socket, and one that declares none keeps
   * the historical zeroed transform, which puts its ORIGIN there. Zeroing unconditionally is what
   * forced a per-weapon marker onto the character rig for every weapon in the game — see
   * {@code WeaponItem.gripPoint} for why that is the wrong way round.
   */
  void reparentWeapon(WeaponItem item, Node target, boolean holstered) {
    Node current = item.getParent();
    if (current != null && current.equals(target)) return;
    item.reparent(target, false);
    item.setTransform(item.alignmentFor(holstered));
  }

}
