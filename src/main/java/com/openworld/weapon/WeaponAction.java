package com.openworld.weapon;

import com.openworld.movement.character.Stance;

/**
 * Contract for all equippable items. Each concrete type (FirearmItem, GrenadeItem, MeleeItem)
 * implements the parts that are meaningful for it and inherits no-op defaults from WeaponItem.
 */
public interface WeaponAction {
    /** Primary action: fire, throw, swing. */
    void useWeapon();

    /** Released or interrupted: clear semi-auto lock, cancel wind-up. */
    void stopUseWeapon();

    /** Called by WeaponController after its reload timer expires. */
    void onReloadComplete();

    /** Weapon-internal readiness check (semi-auto lock, wind-up state, etc.). */
    boolean canUse();

    /** Slot type — determines which inventory slot this item occupies. */
    WeaponType getWeaponType();

    /** Current total spread in degrees; 0 for non-ranged weapons. */
    float getCurrentSpreadDeg();

    /** Notifies the weapon of a stance change for spread/animation purposes. */
    void onSetStance(Stance stance);
}
