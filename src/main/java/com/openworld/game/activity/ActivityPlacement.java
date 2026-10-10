package com.openworld.game.activity;

/**
 * What a scene node gives an activity (PLAN.md 2.1 / CR6: "scene nodes only provide placement for an activity id"):
 * WHERE it is -- the node is a Node3D, its position is the activity's anchor -- and its tuning. The node declares
 * nothing about the campaign and decides nothing; it registers with {@code ActivityRuntime.place} in {@code _ready}.
 */
public interface ActivityPlacement {

    String placedActivityId();

    /** Set the run's tuning (its public fields) before its first stage. */
    default void configure(Activity activity) {}

    /** The run entered a stage (a readout for probes and the editor). */
    default void stageEntered(String stageId) {}

    default void ended(ActivityInstance.Outcome outcome, String variant, String reason) {}
}
