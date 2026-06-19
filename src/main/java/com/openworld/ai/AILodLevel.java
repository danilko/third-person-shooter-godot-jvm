package com.openworld.ai;

/**
 * Distance-based AI level-of-detail tier (PLAN.md Part D / D2). An AICharacter's tier is set
 * from {@code nearestPlayerDist()} on the ~2 s LOD timer; each tier strips progressively more
 * per-frame work so hundreds of distant AIs cost a fraction of a nearby one — the Steam Deck
 * frame-budget win.
 *
 * <ul>
 *   <li>{@link #ACTIVE} (&lt; 80 m): full FSM, NavAgent pathfinding, and AnimationTree writes.</li>
 *   <li>{@link #PASSIVE} (80–200 m): simplified tick — no pathfinding, no FSM transitions, hold
 *       last heading, and skip AnimationTree parameter writes (hold last pose). The AnimationTree
 *       JVM-bridge writes are among the most expensive per-AI calls, so skipping them is what makes
 *       50+ mid-range AIs affordable.</li>
 *   <li>{@link #FROZEN} (&gt; 200 m): skip {@code _physicsProcess} entirely.</li>
 * </ul>
 *
 * Tiers are ordered ACTIVE &lt; PASSIVE &lt; FROZEN so callers can gate with {@code ordinal()}
 * comparisons (e.g. "skip animation when level is at least PASSIVE").
 */
public enum AILodLevel {
    ACTIVE,
    PASSIVE,
    FROZEN
}
