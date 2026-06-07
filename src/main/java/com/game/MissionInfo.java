package com.game;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;
import godot.core.VariantArray;

/**
 * Designer-editable mission definition.
 *
 * Attach as a Resource (e.g. a .tres preset) or build in code for debug/test
 * purposes (see DebugHarness). Handed to MissionManager.startMission().
 *
 * objectiveType is a plain String — use MissionObjectiveType constants
 * (ELIMINATE_ALL / HOLD_POINT / ESCORT / DELIVER) or a custom value for future
 * objective kinds. Only ELIMINATE_ALL has MissionManager logic today.
 *
 * Story-graph fields (possibleOutcomeVariants, opposingFactionJoinable) define the
 * outcome-variant schema MissionDirector (F1) will fold into the player's
 * accumulated variant-membership set — see the "Resolved" design note in PLAN.md.
 */
@RegisterClass(className = "MissionInfo")
public class MissionInfo extends Resource {

    /** Stable identifier — addressed by MissionManager, MissionDirector, and SaveSystem. */
    @RegisterProperty @Export public String missionId = "";

    /** Factions whose members count as "the player side" for win/loss evaluation. */
    @RegisterProperty @Export
    public VariantArray<String> playerFactions = new VariantArray<>(String.class);

    /** Use MissionObjectiveType constants or a custom objective string. */
    @RegisterProperty @Export public String objectiveType = MissionObjectiveType.ELIMINATE_ALL;

    /** Seconds before the mission auto-fails. 0 = no limit. */
    @RegisterProperty @Export public float timeLimit = 0f;

    /** When false, ImpactManager/Health should ignore damage between playerFactions members. */
    @RegisterProperty @Export public boolean allowFriendlyFire = false;

    /**
     * Declared set of outcome variants this mission can produce on completion
     * (e.g. "ELIMINATED", "ESCAPED", "BETRAYED"). MissionManager picks one when
     * the objective resolves; MissionDirector (F1) checks membership against this
     * set to drive the unlock graph.
     */
    @RegisterProperty @Export
    public VariantArray<String> possibleOutcomeVariants = new VariantArray<>(String.class);

    /** True when a co-player may join this mission on the opposing faction (PvP-as-variant). */
    @RegisterProperty @Export public boolean opposingFactionJoinable = false;
}
