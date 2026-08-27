package com.openworld.ai;

import godot.annotation.Export;
import godot.annotation.Script;
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
@Script(className = "AIBehaviorConfig")
public class AIBehaviorConfig extends Resource {

    // ── Detection ─────────────────────────────────────────────────────────────

    /** Distance (m) at which this AI can detect a hostile target. */
    @Export public float detectionRange = 120.0f;

    /** Distance (m) at which this AI perceives world stimuli (gunshots, explosions — PLAN.md E2).
     *  Capped against each stimulus's own audible radius, so a quiet event is heard only up close. */
    @Export public float hearingRadius = 150.0f;

    /** Distance (m) at which this AI transitions from Chase to Attack. */
    @Export public float attackRange = 150.0f;

    /** Patrol wander radius around the spawn point (m). */
    @Export public float patrolRadius = 80.0f;

    // ── Aim limits ────────────────────────────────────────────────────────────

    /** Minimum pitch angle (deg, negative = below horizon) the AI can aim. */
    @Export public float aimPitchMin = -55.0f;

    /** Maximum pitch angle (deg) the AI can aim upward. */
    @Export public float aimPitchMax = 75.0f;

    // ── Accuracy ──────────────────────────────────────────────────────────────

    /**
     * Which body part the AI aims at on a successful accuracy roll.
     * Valid values: "HEAD", "CHEST", "BODY", "LEGS".
     * Maps to damage multipliers in Health.getDamageMultiplier().
     */
    @Export public String aimBodyPart = "CHEST";

    /** Probability [0–1] of the shot hitting the intended body part. */
    @Export public float hitChance = 0.5f;

    /**
     * Per-AI aim scatter multiplier.  Miss shots scatter by:
     *   aimScatterRadius × (hDist/10) + weaponSpreadM
     * Tune up for weaker AIs, down for elite.
     */
    @Export public float aimScatterRadius = 2.5f;

    /**
     * Fraction of hitChance lost when moving at full walk speed.
     * 0 = no penalty; 1 = zero accuracy at full speed.
     * The AI's stop-to-shoot pause naturally recovers full hitChance.
     */
    @Export public float moveAccuracyPenalty = 0.75f;

    // ── Timing ────────────────────────────────────────────────────────────────

    /** Seconds from first LoS before the AI fires its first shot (reaction delay). */
    @Export public float reactionTime = 0.6f;

    /** Seconds after losing LoS that the AI keeps firing at last known position. */
    @Export public float suppressionDuration = 1.5f;

    /**
     * Seconds the AI stops moving after each shot (sniper/precision archetype only).
     * Default 0 = fire while strafing (CS/GTA style — accuracy is handled by
     * moveAccuracyPenalty instead). Set > 0 for archetypes that need a stop-to-aim
     * pause, e.g. a sniper with shootStillDuration = 1.0.
     */
    @Export public float shootStillDuration = 0.0f;

    /** Seconds the AI holds a strafe direction before reversing. */
    @Export public float strafeChangeDuration = 1.0f;

    // ── Stance ────────────────────────────────────────────────────────────────

    /**
     * When true, the AI may crouch during combat. Exact trigger depends on
     * crouchOnSuppression: if true, only crouches while under attack (reactive
     * cover); if false, crouches proactively once LoS + reaction are complete.
     */
    @Export public boolean useCombatCrouch = false;

    /**
     * When true (requires useCombatCrouch), the AI only crouches while actively
     * under attack (took damage within the last 2.5 s). Matches CS/Battlefield
     * reactive-cover behaviour. When false, crouches as soon as LoS + reaction
     * are ready (proactive — the old behaviour).
     */
    @Export public boolean crouchOnSuppression = true;

    /**
     * Total patrol FOV cone in degrees. 360 disables the check (omnidirectional).
     * Default 200° = ±100° from the movement-forward vector, blocking detection
     * of enemies directly behind. Only applied in canSeeTarget() (patrol/search).
     * Has no effect in AttackState where the AI is already locked on.
     */
    @Export public float detectionFovDeg = 200.0f;

    // ── Escort ────────────────────────────────────────────────────────────────

    /**
     * Desired follow distance (m) from the escort target in EscortState.
     * AI moves toward the target when beyond this range, idles when within.
     */
    @Export public float followDistance = 3.0f;

    // ── Flee ──────────────────────────────────────────────────────────────────

    /** Distance (m) to run before returning to Patrol in FleeState. */
    @Export public float fleeDistance = 20.0f;

    /**
     * When true, the AI transitions to FleeState instead of SearchState when hit
     * and out of ammo. Use for civilians, wounded soldiers, or cowardly archetypes.
     */
    @Export public boolean useFleeOnAttack = false;

    // ── Breaching ───────────────────────────────────────────────────────────────

    /**
     * When the AI has a target in weapon range but its line of sight is blocked by geometry (a wall,
     * a building) for {@code suppressionDuration}, <b>true</b> = pursue/approach to regain a clean shot
     * (paths around cover or through a doorway into a building, re-engaging once it sees the target
     * again) — an aggressive breacher that clears rooms; <b>false</b> = hold-and-shoot (sweep the last
     * known spot via SearchState then return to post) — snipers, static guards, defenders that engage
     * only from where they stand. This is the lever between "AI follows you into the building" and
     * "AI camps outside and fires through the window".
     */
    @Export public boolean breachWhenBlocked = true;

    // ── Carjack reaction (PLAN.md I3c) ───────────────────────────────────────────

    /**
     * How an ambient-traffic driver reacts when the player carjacks its vehicle (PLAN.md I3c).
     * String (not an enum — the godot-kotlin-jvm registration scanner chokes on raw enum exports):
     * <ul>
     *   <li>{@code "FLEE"} (default) — a civilian panics and runs from the carjacker (FleeState).
     *   <li>{@code "FIGHT"} — a gang/hostile driver turns aggressive (host-authoritative faction flip,
     *       replicated) and attacks the carjacker (AttackState).
     * </ul>
     */
    @Export public String reactToCarjack = "FLEE";

    public AIBehaviorConfig() { super(); }
}
