package com.openworld.weapon;

/**
 * What a thrown projectile does when it goes off. One {@link GrenadeProjectile} class flies every throwable;
 * its scene names the effect ({@code effect = "flash"}), so a new throwable is a scene, not a class.
 *
 * <ul>
 *   <li>{@link #FRAG} - a blast: damage and push (FRG1, and the pipe bomb PIB1);</li>
 *   <li>{@link #FLASH} - blinds whoever can see it (FLA1): no damage;</li>
 *   <li>{@link #SMOKE} - a cloud that blocks sight for a while (SMO1): no damage;</li>
 *   <li>{@link #REMOTE} - a charge that sticks where it lands and waits for its thrower's detonator (REC1), then
 *       blasts like a frag.</li>
 * </ul>
 * The ordinal rides MSG_DETONATION, so the list is APPEND-ONLY.
 */
public enum GrenadeEffect {
    FRAG, FLASH, SMOKE, REMOTE;

    public static GrenadeEffect parse(String s) {
        if (s == null) return FRAG;
        switch (s.trim().toLowerCase()) {
            case "flash": return FLASH;
            case "smoke": return SMOKE;
            case "remote": return REMOTE;
            default: return FRAG;
        }
    }

    public static GrenadeEffect fromOrdinal(int i) {
        GrenadeEffect[] v = values();
        return i >= 0 && i < v.length ? v[i] : FRAG;
    }

    /** Does this effect deal blast damage when it goes off? */
    public boolean blasts() { return this == FRAG || this == REMOTE; }
}
