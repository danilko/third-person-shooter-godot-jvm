package com.openworld.weapon;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.Script;

/**
 * A scoped precision rifle. A {@link FirearmItem} whose accuracy depends on being AIMED, and the
 * home for the scope/zoom ability when it lands.
 *
 * <p><b>Why a class and not a new {@link WeaponType} value.</b> {@code WeaponType} is a coarse
 * behaviour category — RANGED / THROWN / MELEE — and the code tests it with
 * {@code == WeaponType.MELEE} / {@code == RANGED} in the AI and in {@code Character}'s combat entry.
 * A fourth value would make every one of those tests silently miss a sniper rifle. A sniper IS
 * ranged; what differs is its behaviour, and behaviour belongs in a subclass. This is the same split
 * the weapon set already makes ({@code ProjectileItem}, {@code ThrowableItem}, {@code MeleeItem},
 * {@code KnifeItem}, {@code AxeItem} are all classes, not enum values).
 *
 * <p><b>What it owns today: the hipfire penalty.</b> The CS:GO AWP rule — a scoped rifle is pinpoint
 * through the scope and near-useless from the hip — which is what makes a one-shot weapon fair. It
 * multiplies the cone by {@link #hipfireSpreadMultiplier} while the holder is not in combat (not
 * aiming). Only {@code getCurrentSpreadDeg} widens: {@code minimumSpreadDeg} is the FLOOR the host
 * validates a client's reported cone against (PLAN.md N1), and a floor that grew with the hipfire
 * multiplier would refuse an honest scoped shot from a client whose aim state the host has not seen
 * yet. Widening is always safe there; narrowing never is.
 *
 * <p><b>Still to build — the sniper mechanic proper:</b> the scope itself (an ADS field of view plus
 * either an overlay or a render-to-texture scope), hold-breath sway, and the bolt-cycle view punch.
 * Those need camera and HUD work, so they are deliberately not stubbed here: this codebase's rule is
 * that a field nothing reads is a field that will be wrong when something finally reads it. The
 * weapon's own aim POSE is separate and already exists — {@code weaponPoseIndex} 9, the {@code
 * sniper} grip archetype in {@code blender/tools/weapon_archetypes.json}.
 */
@Script(className = "SniperItem")
public class SniperItem extends FirearmItem {

  /**
   * How much wider the cone is when the holder is NOT aiming. 1.0 disables the rule; the shipped 8.0
   * turns SR3's 0.005° scoped cone into 0.04° from the hip, before movement and bloom — still a
   * rifle, not a shotgun, because this weapon's base spread is tiny to begin with.
   */
  @Export public float hipfireSpreadMultiplier = 8.0f;

  /** Setter half of the exported property (godot-jvm merges field + accessors into ONE property, so
   *  a getter without a setter would register READ_ONLY and never receive the scene's value). */
  public void setHipfireSpreadMultiplier(float v) { hipfireSpreadMultiplier = v; }

  public float getHipfireSpreadMultiplier() { return hipfireSpreadMultiplier; }

  @Override
  public float getCurrentSpreadDeg() {
    float base = super.getCurrentSpreadDeg();
    return aimed() ? base : base * hipfireSpreadMultiplier;
  }

  /**
   * Whether the holder is actually looking down the sights. {@code Character.combat} is the same flag
   * the aim modifiers, the crosshair and the stance system read, so "aimed" means one thing
   * everywhere. A weapon held by something that is not a {@code Character} (a test stand, a mounted
   * gun) counts as aimed: the penalty is a player-facing trade, not a way to weaken an AI silently.
   */
  private boolean aimed() {
    return !(owningCharacter instanceof Character c) || c.isCombat();
  }
}
