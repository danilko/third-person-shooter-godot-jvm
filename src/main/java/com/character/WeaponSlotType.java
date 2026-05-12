package com.character;

/**
 * Category of a weapon slot. Decoupled from slot index so a controller can
 * define any number of slots of the same type (e.g. two PRIMARY slots).
 *
 * Ordinal order is preserved so scene-file int values stay stable:
 *   0 = PRIMARY  1 = SECONDARY  2 = MELEE  3 = THROWABLE  4 = OFFHAND
 */
public enum WeaponSlotType {
    PRIMARY,    // main ranged weapon (rifle, magic staff)
    SECONDARY,  // sidearm (pistol, wand)
    MELEE,      // close-range (knife, sword)
    THROWABLE,  // thrown items (grenade, magic orb)
    OFFHAND     // held off-hand (shield, torch) — never displaces a weapon slot
}
