package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;

/**
 * Per-AI tuning resource.  Set this on each AICharacter inspector to give the
 * character a behaviour profile.  Ship .tres presets per archetype and swap them
 * without touching code.
 *
 * Example presets: EnemySoldierBehavior.tres, GuardBehavior.tres, CivilianBehavior.tres
 *
 * All fields default to the values previously hard-coded on AICharacter so existing
 * scenes without a config assigned fall back to identical behaviour.
 */
@RegisterClass(className = "AIBehaviorConfig")
public class AIBehaviorConfig extends Resource {

    // ── Detection ─────────────────────────────────────────────────────────────

    /** Distance (m) at which this AI can detect a hostile target. */
    @Export @RegisterProperty public float detectionRange = 120.0f;

    /** Distance (m) at which this AI transitions from Chase to Attack. */
    @Export @RegisterProperty public float attackRange = 150.0f;

    /** Patrol wander radius around the spawn point (m). */
    @Export @RegisterProperty public float patrolRadius = 80.0f;

    // ── Aim limits ────────────────────────────────────────────────────────────

    /** Minimum pitch angle (deg, negative = below horizon) the AI can aim. */
    @Export @RegisterProperty public float aimPitchMin = -55.0f;

    /** Maximum pitch angle (deg) the AI can aim upward. */
    @Export @RegisterProperty public float aimPitchMax = 75.0f;

    // ── Accuracy ──────────────────────────────────────────────────────────────

    /**
     * Which body part the AI aims at on a successful accuracy roll.
     * Valid values: "HEAD", "CHEST", "BODY", "LEGS".
     * Maps to damage multipliers in Health.getDamageMultiplier().
     */
    @Export @RegisterProperty public String aimBodyPart = "CHEST";

    /** Probability [0–1] of the shot hitting the intended body part. */
    @Export @RegisterProperty public float hitChance = 0.5f;

    /**
     * Per-AI aim scatter multiplier.  Miss shots scatter by:
     *   aimScatterRadius × (hDist/10) + weaponSpreadM
     * Tune up for weaker AIs, down for elite.
     */
    @Export @RegisterProperty public float aimScatterRadius = 2.5f;

    /**
     * Fraction of hitChance lost when moving at full walk speed.
     * 0 = no penalty; 1 = zero accuracy at full speed.
     * The AI's stop-to-shoot pause naturally recovers full hitChance.
     */
    @Export @RegisterProperty public float moveAccuracyPenalty = 0.75f;

    // ── Timing ────────────────────────────────────────────────────────────────

    /** Seconds from first LoS before the AI fires its first shot (reaction delay). */
    @Export @RegisterProperty public float reactionTime = 0.6f;

    /** Seconds after losing LoS that the AI keeps firing at last known position. */
    @Export @RegisterProperty public float suppressionDuration = 1.5f;

    /** Seconds the AI stops moving after each shot (stop-to-shoot pause). */
    @Export @RegisterProperty public float shootStillDuration = 0.25f;

    /** Seconds the AI holds a strafe direction before reversing. */
    @Export @RegisterProperty public float strafeChangeDuration = 1.0f;

    // ── Stance ────────────────────────────────────────────────────────────────

    /**
     * When true, the AI crouches once it has LoS and has completed its reaction
     * delay.  Returns upright when repositioning or losing sight.
     */
    @Export @RegisterProperty public boolean useCombatCrouch = true;

    public AIBehaviorConfig() { super(); }
}
