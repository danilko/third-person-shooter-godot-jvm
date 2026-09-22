package com.openworld.weapon;

/**
 * The grip archetypes, by NAME (PLAN.md 2.8 item 8). A weapon scene stores {@code weapon_archetype = "rifle"};
 * the blend index the AnimationTree needs ({@code weaponPoseIndex}) is derived here, so a scene never holds a
 * bare number whose meaning depends on its position in a list. The ORDER is still append-only — the index IS
 * the blend-point position in {@code WeaponAim}/{@code WeaponHold}/{@code WeaponChangeAnimation} — and it is held
 * to {@code blender/tools/weapon_archetypes.json} by {@code WeaponCatalogTest}.
 */
public enum GripArchetype {
    PISTOL("pistol"),
    RIFLE("rifle"),
    LAUNCHER("launcher"),
    DUAL_PISTOL("dual_pistol"),
    MELEE("melee"),
    FIST("fist"),
    SHIELD("shield"),
    SHIELD_MELEE("shield_melee"),
    THROWABLE("throwable"),
    SNIPER("sniper"),
    /** A pump shotgun: its support hand is on the pump, far forward of a rifle's, so it has its own AIM
     *  pose ({@code upright_aim_shotgun}); every other family plays the rifle's (PLAN.md 6.17). */
    SHOTGUN("shotgun");

    public final String key;

    GripArchetype(String key) { this.key = key; }

    /** The AnimationTree blend position. */
    public int index() { return ordinal(); }

    /** The archetype named {@code key}, or null when no archetype has that name. */
    public static GripArchetype fromKey(String key) {
        if (key == null) return null;
        for (GripArchetype a : values()) if (a.key.equals(key)) return a;
        return null;
    }
}
