package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

/**
 * One swing of a melee weapon's attack chain — the whole of what makes a jab different from a
 * haymaker, as DATA rather than as a subclass.
 *
 * <p>A melee weapon declares an ordered list of these ({@code MeleeItem.attackSteps}). The default
 * chain walks it in order while the swings keep coming inside {@code MeleeItem.comboResetSeconds}
 * and starts over after a pause — so an axe authored as {@code [light, heavy]} is the Left 4 Dead
 * shape the design asked for, a fist authored as {@code [light, light_b]} alternates jab and cross,
 * and a weapon with one step simply repeats it. A subclass may pick steps some other way (the
 * knife's tap/hold, {@code KnifeItem}); the step itself does not know how it was chosen.
 *
 * <p><b>The code owns the timing; the clip is time-warped to fit it.</b> {@link #windup},
 * {@link #active} and {@link #recovery} are the swing, and {@code AnimationController.playMeleeAttack}
 * scales {@link #animation} so its whole length spans them. That is the Left 4 Dead split — the
 * animation is decorative, the hit is decided by a trace at a fixed moment — and it is what lets
 * feel be tuned here without re-authoring anything, and a placeholder clip of the wrong length play
 * correctly. When a real swing clip lands, set these to the clip's own contact frames and the scale
 * comes out at 1.
 *
 * <p>Read-only shared config: embedding one in a weapon {@code .tscn} is fine (every instance of
 * that weapon shares it and nothing mutates it — the {@code VehicleConfig} rule in CLAUDE.md).
 */
@Script(className = "MeleeAttackStep")
public class MeleeAttackStep extends Resource {

  /**
   * The AnimationTree clip this swing plays — an input name on the {@code AttackClip} transition
   * in {@code CharacterVisuals_GodotChan.tscn}, and an action in {@code merged_animation.blend}.
   * Named {@code attack_<step>_<weapon>} (e.g. {@code attack_heavy_mw2}). Two weapons may point at
   * the same clip; a missing name plays nothing and {@code probe_melee.gd} fails on it, because an
   * unknown transition input is otherwise silent.
   */
  @Export public String animation = "";

  /** Damage dealt to each target this swing connects with (bone multipliers still apply). */
  @Export public float damage = 25.0f;

  /** Reach in metres, measured from the attacker's CHEST along the swing direction. */
  @Export public float range = 1.6f;

  /**
   * Radius of the swept capsule. Generous on purpose — nobody ships a blade-accurate hitbox. The
   * forgiveness lives here and in the capsule's length, never in guessing a target for the player
   * (target snapping is what makes GTA's melee pick someone you did not mean).
   */
  @Export public float radius = 0.35f;

  /** Seconds from the press to the first frame that can connect. Low is what reads as "snappy". */
  @Export public float windup = 0.12f;

  /** Seconds the contact window stays open. A few frames, not the whole swing: a long window lets a
   *  target walk into a swing that has visibly finished, which reads as unearned. */
  @Export public float active = 0.06f;

  /** Seconds after the window closes before another swing may start. */
  @Export public float recovery = 0.30f;

  /** Seconds the swing FREEZES on contact (hitstop) — the single biggest lever on hit feel. */
  @Export public float hitstop = 0.06f;

  /** Degrees of upward camera kick on contact. Only a camera that is on screen notices. */
  @Export public float cameraKick = 1.5f;

  public MeleeAttackStep() { super(); }

  /** Windup + active + recovery: how long this swing occupies the weapon, and what its clip spans. */
  public float totalDuration() {
    return Math.max(0.01f, windup + active + recovery);
  }
}
