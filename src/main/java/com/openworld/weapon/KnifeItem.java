package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;

/**
 * CS:GO-style knife: tap fire = quick stab, hold fire = heavy slash on release.
 *
 * Light attack (tap, < chargeThreshold):
 *   Fast stab — narrow cone, short range, base damage.
 *
 * Heavy attack (hold ≥ chargeThreshold, release):
 *   Slow slash — wide cone, longer reach, ~2.5× damage.
 *
 * Both attacks use the raycast-cone hit detection from MeleeItem. No Area3D hitbox
 * is needed — the charge time is accumulated in _physicsProcess, and the attack
 * executes in stopUseWeapon on button-release.
 *
 * Scene setup: same as MeleeItem — HitTimer (one_shot=true) required.
 */
@RegisterClass(className = "KnifeItem")
public class KnifeItem extends MeleeItem {

    /** Seconds of hold needed to trigger a heavy slash instead of a quick stab. */
    @Export @RegisterProperty public float chargeThreshold   = 0.5f;

    /** Damage for the heavy slash. */
    @Export @RegisterProperty public float heavyDamage       = 100f;

    /** Reach for the heavy slash (metres from torso). */
    @Export @RegisterProperty public float heavyMeleeRange   = 2.0f;

    /** Cone half-angle for the heavy slash — wider arc than the quick stab. */
    @Export @RegisterProperty public float heavyConeAngleDeg = 35f;

    private float[][] heavyOffsets;

    private double  chargeTime        = 0.0;
    private boolean isCharging        = false;
    private boolean heavyAttackActive = false;

    @RegisterFunction
    @Override
    public void _ready() {
        super._ready();  // builds swingOffsets from coneAngleDeg
        heavyOffsets = buildOffsets(heavyConeAngleDeg);
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (isCharging) chargeTime += delta;
        super._physicsProcess(delta);  // runs the swing-window hit detection
    }

    // ── WeaponAction ──────────────────────────────────────────────────────────

    /** Press: start charging. Audio and swing execute on release (stopUseWeapon). */
    @Override
    public void useWeapon() {
        isCharging = true;
        chargeTime = 0.0;
    }

    /**
     * Release: execute the attack. Short hold → quick stab; long hold → heavy slash.
     * Audio plays here (not on press) so the slash sound aligns with the swing.
     */
    @Override
    public void stopUseWeapon() {
        if (!isCharging) return;
        isCharging        = false;
        heavyAttackActive = chargeTime >= chargeThreshold;
        if (weaponAudio != null && fireAudio != null) {
            weaponAudio.stop();
            weaponAudio.setStream(fireAudio);
            weaponAudio.play();
        }
        startSwing();
    }

    /** Block new charge while already charging or during the swing cooldown. */
    @Override
    public boolean canUse() {
        return !isCharging && super.canUse();
    }

    /** Selects light or heavy attack parameters based on current charge state. */
    @Override
    protected boolean performMeleeHit() {
        float     dmg = heavyAttackActive ? heavyDamage     : damage;
        float     rng = heavyAttackActive ? heavyMeleeRange  : meleeRange;
        float[][] off = heavyAttackActive ? heavyOffsets     : swingOffsets;
        return performMeleeHitWith(dmg, rng, off);
    }
}
