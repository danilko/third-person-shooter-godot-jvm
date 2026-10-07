package com.openworld.world;

/**
 * What kind of hit a weapon deals, so the TARGET can decide how much it hurts (Source's damage types, Unreal's
 * DamageType; user 2026-10-07: "a knife may do barely anything to a vehicle"). The weapon declares its kind
 * ({@code WeaponItem.damageKind()}), each body's {@code Health} declares a multiplier per kind
 * ({@code Health.multiplierFor}): N weapons + M targets numbers instead of N x M.
 *
 * <ul>
 *   <li>{@link #BULLET} -- every gun, bullet or pellet. Scaled by {@code hitDamageMultiplier}.</li>
 *   <li>{@link #HEAVY} -- a heavy tool that can break things (the axe). Also {@code hitDamageMultiplier}: an axe
 *       dents a car like gunfire does.</li>
 *   <li>{@link #BLADE} -- a knife: deadly to a person, nothing to sheet metal ({@code bladeDamageMultiplier}).</li>
 *   <li>{@link #BLUNT} -- fists and light blunt melee ({@code bluntDamageMultiplier}).</li>
 * </ul>
 * Explosions keep their own path ({@code ExplosionManager}, {@code explosionDamageMultiplier}). Not on the wire:
 * damage is resolved where it is applied.
 */
public enum DamageKind { BULLET, HEAVY, BLADE, BLUNT }
