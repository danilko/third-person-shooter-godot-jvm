package com.openworld.ai;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;
import com.openworld.ai.character.AttackState;
import com.openworld.ai.character.EscortState;
import com.openworld.ai.character.FleeState;
import com.openworld.ai.character.SearchState;
import com.openworld.character.AICharacter;
import com.openworld.character.Health;
import com.openworld.movement.character.Stance;

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

    /** Distance (m) at which this AI perceives world stimuli (gunshots, explosions — PLAN.md E2).
     *  Capped against each stimulus's own audible radius, so a quiet event is heard only up close. */
    @Export @RegisterProperty public float hearingRadius = 150.0f;

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

    /**
     * Seconds the AI stops moving after each shot (sniper/precision archetype only).
     * Default 0 = fire while strafing (CS/GTA style — accuracy is handled by
     * moveAccuracyPenalty instead). Set > 0 for archetypes that need a stop-to-aim
     * pause, e.g. a sniper with shootStillDuration = 1.0.
     */
    @Export @RegisterProperty public float shootStillDuration = 0.0f;

    /** Seconds the AI holds a strafe direction before reversing. */
    @Export @RegisterProperty public float strafeChangeDuration = 1.0f;

    // ── Stance ────────────────────────────────────────────────────────────────

    /**
     * When true, the AI may crouch during combat. Exact trigger depends on
     * crouchOnSuppression: if true, only crouches while under attack (reactive
     * cover); if false, crouches proactively once LoS + reaction are complete.
     */
    @Export @RegisterProperty public boolean useCombatCrouch = false;

    /**
     * When true (requires useCombatCrouch), the AI only crouches while actively
     * under attack (took damage within the last 2.5 s). Matches CS/Battlefield
     * reactive-cover behaviour. When false, crouches as soon as LoS + reaction
     * are ready (proactive — the old behaviour).
     */
    @Export @RegisterProperty public boolean crouchOnSuppression = true;

    /**
     * Total patrol FOV cone in degrees. 360 disables the check (omnidirectional).
     * Default 200° = ±100° from the movement-forward vector, blocking detection
     * of enemies directly behind. Only applied in canSeeTarget() (patrol/search).
     * Has no effect in AttackState where the AI is already locked on.
     */
    @Export @RegisterProperty public float detectionFovDeg = 200.0f;

    // ── Escort ────────────────────────────────────────────────────────────────

    /**
     * Desired follow distance (m) from the escort target in EscortState.
     * AI moves toward the target when beyond this range, idles when within.
     */
    @Export @RegisterProperty public float followDistance = 3.0f;

    // ── Flee ──────────────────────────────────────────────────────────────────

    /** Distance (m) to run before returning to Patrol in FleeState. */
    @Export @RegisterProperty public float fleeDistance = 20.0f;

    /**
     * When true, the AI transitions to FleeState instead of SearchState when hit
     * and out of ammo. Use for civilians, wounded soldiers, or cowardly archetypes.
     */
    @Export @RegisterProperty public boolean useFleeOnAttack = false;

    public AIBehaviorConfig() { super(); }
}
