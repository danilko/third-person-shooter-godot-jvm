package com.openworld.weapon;

/**
 * What a weapon is busy with (PLAN.md 2.8 item 2). {@code WeaponController.fireTimer} used to mean four
 * things — the fire interval (a bolt cycle), the draw settle, the pickup-equip block and the merge-pickup
 * block — and the scope keyed off it, so a draw settle unscoped exactly like a bolt cycle. The timer still
 * does the timing; this names WHY it is running, and every reader asks the name.
 */
public enum WeaponState {
    /** Ready to fire. */
    IDLE,
    /** Between shots: the fire interval (a bolt action IS its fire rate). */
    CYCLING,
    /** A reload is running. */
    RELOADING,
    /** A holster -> draw transition is running. */
    SWITCHING,
    /** A short lockout after a draw or a pickup so a held trigger cannot fire mid-raise. */
    SETTLING;

    /** Precedence: switching > reloading > the fire lock's reason > idle. Engine-free, unit-tested. */
    public static WeaponState resolve(boolean switching, boolean reloading, boolean fireLocked, WeaponState lockReason) {
        if (switching) return SWITCHING;
        if (reloading) return RELOADING;
        if (fireLocked) return lockReason == null ? CYCLING : lockReason;
        return IDLE;
    }
}
