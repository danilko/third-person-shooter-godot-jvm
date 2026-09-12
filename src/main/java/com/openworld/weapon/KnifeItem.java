package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;

/**
 * CS:GO-style knife: tap fire = quick stab, hold fire = heavy slash on release.
 *
 * <p>The knife differs from every other melee weapon in ONE thing — how a swing is CHOSEN — so that
 * is all it overrides. The swings themselves are ordinary {@link MeleeAttackStep}s in
 * {@code attackSteps} (step 0 the stab, {@link #heavyStepIndex} the slash), and they run through
 * MeleeItem's sweep, hitstop and animation exactly like an axe's chain does. Before, the knife kept
 * its own heavy damage/range/cone fields and its own cone table, i.e. a second copy of what a swing
 * is.
 *
 * <p>The press starts charging and the RELEASE swings, so the swing's timing starts at release.
 * Buffering is off: this weapon's input IS the hold, and a buffered press would start a charge the
 * player never held.
 */
@Script(className = "KnifeItem")
public class KnifeItem extends MeleeItem {

  /** Seconds of hold needed to trigger the heavy slash instead of the quick stab. */
  @Export public float chargeThreshold = 0.5f;

  /** Which of {@code attackSteps} the heavy slash is. The tap always plays step 0. */
  @Export public int heavyStepIndex = 1;

  private double  chargeTime = 0.0;
  private boolean isCharging = false;

  @Register
  @Override
  public void _physicsProcess(double delta) {
    if (isCharging) chargeTime += delta;
    super._physicsProcess(delta);
  }

  /** Press: start charging. The swing (and its sound) happens on release. */
  @Override
  public void useWeapon() {
    isCharging = true;
    chargeTime = 0.0;
  }

  /** Release: a short hold stabs, a long one slashes. */
  @Override
  public void stopUseWeapon() {
    if (!isCharging) return;
    isCharging = false;
    playSwingAudio();
    beginSwing(chargeTime >= chargeThreshold ? heavyStepIndex : 0, false);
  }

  /** No new charge while one is held or a swing is still running. */
  @Override
  public boolean canUse() { return !isCharging && super.canUse(); }

  @Override public double fireBufferSeconds() { return 0.0; }
}
