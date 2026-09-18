package com.openworld.game.mission;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;
import godot.core.VariantArray;
import com.openworld.character.Health;
import com.openworld.debug.DebugHarness;
import com.openworld.world.manager.ImpactManager;

/**
 * Designer-editable mission definition.
 *
 * Attach as a Resource (e.g. a .tres preset) or build in code for debug/test
 * purposes (see DebugHarness). Handed to MissionManager.startMission().
 *
 * objectiveType is a plain String — use MissionObjectiveType constants
 * (ELIMINATE_ALL / HOLD_POINT / ESCORT / DELIVER / RACE) or a custom value for future
 * objective kinds. ELIMINATE_ALL is tracked by MissionManager itself; RACE is handed to
 * RaceDirector (R2). The rest are schema only.
 *
 * Story-graph fields (possibleOutcomeVariants, opposingFactionJoinable) define the
 * outcome-variant schema MissionDirector (F1) will fold into the player's
 * accumulated variant-membership set — see the "Resolved" design note in PLAN.md.
 */
@Script(className = "MissionInfo")
public class MissionInfo extends Resource {

    /** Stable identifier — addressed by MissionManager, MissionDirector, and SaveSystem. */
    @Export public String missionId = "";

    /** Factions whose members count as "the player side" for win/loss evaluation. */
    @Export
    public VariantArray<String> playerFactions = new VariantArray<>(String.class);

    /** Use MissionObjectiveType constants or a custom objective string. */
    @Export public String objectiveType = MissionObjectiveType.ELIMINATE_ALL;

    /** Seconds before the mission auto-fails. 0 = no limit. On a RACE this is the time trial's clock. */
    @Export public float timeLimit = 0f;

    /**
     * RACE only (R2): which circuit of {@code RaceCheckpoint} gates this mission runs. Empty means
     * "the circuit named after this mission", which is the case that needs no second name; setting
     * it lets two missions (a sprint and a three-lap version) share one authored route.
     */
    @Export public String raceId = "";

    /** RACE only: how many times the route is completed. 1 = a point-to-point sprint or one lap. */
    @Export public int raceLaps = 1;

    /** When false, ImpactManager/Health should ignore damage between playerFactions members. */
    @Export public boolean allowFriendlyFire = false;

    /**
     * Declared set of outcome variants this mission can produce on completion
     * (e.g. "ELIMINATED", "ESCAPED", "BETRAYED"). MissionManager picks one when
     * the objective resolves; MissionDirector (F1) checks membership against this
     * set to drive the unlock graph.
     */
    @Export
    public VariantArray<String> possibleOutcomeVariants = new VariantArray<>(String.class);

    /**
     * Faction relationships while this mission runs (PLAN.md F2) — e.g. {@code GangA_vs_Police.tres}.
     * Null keeps whatever the region / defaults say. Applied by {@code MissionManager.startMission} as
     * {@code FactionManager}'s mission layer and removed when the mission completes or fails, so a
     * mission's table (and any betrayal flipped on top of it) never outlives the mission.
     */
    @Export public com.openworld.character.FactionTable factionTable = null;

    /** True when a co-player may join this mission on the opposing faction (PvP-as-variant). */
    @Export public boolean opposingFactionJoinable = false;
}
