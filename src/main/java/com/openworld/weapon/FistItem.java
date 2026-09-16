package com.openworld.weapon;

import godot.annotation.Script;
import com.openworld.character.CharacterVisuals;

/**
 * Permanent unarmed weapon occupying slot 0.
 * Placed in CharacterVisuals WeaponAttachment as a pre-discovered scene node — same
 * lifecycle as all other weapons. Never dropped, never picked up from the world.
 * Its punches are ordinary MeleeAttackSteps (Fist.tscn): a jab and a cross that alternate.
 */
@Script(className = "FistItem")
public class FistItem extends MeleeItem {

  public FistItem() {
    weaponId        = "fist";
    weaponName      = "Fist";
    slotType        = WeaponSlotType.FIST.ordinal();
    weaponArchetype = "fist";
    isDroppable    = false;
    isInfiniteAmmo = true;
    switchSpeed    = 1.5f;
    fireRate        = 2.0f;
    damage          = 10.0f;
    auto            = false;
  }

  // Everything else — the sweep, the chain, the animation — is MeleeItem's, driven by the
  // attackSteps authored in Fist.tscn (jab, cross).

  // Fist is never placed in the world as a pickup.
  @Override protected boolean shouldAutoPickup(godot.api.Node character) { return false; }
  @Override protected void    onCharacterEntered(godot.api.Node character) {}
}
