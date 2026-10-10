package com.openworld.game.activity;

/**
 * What ONE participant got out of a run (PLAN.md 2.1, the co-op model's rule 4) -- it replaces the global
 * "missionCompleted": {@code storyCredit} says whether the variant, its flags and its ending went into THIS player's
 * story (only a participant who was themselves eligible; others are paid and nothing else), {@code worldApplied}
 * whether the variant's world effects were written through them (the owner, once), {@code pay} what they were paid.
 */
public record ActivityResult(String instanceId, String activityId, String playerId, Activity.Role role, Activity.Mode mode,
                             ActivityInstance.Outcome outcome, String variant, String reason, boolean storyCredit,
                             boolean worldApplied, long pay) {
}
