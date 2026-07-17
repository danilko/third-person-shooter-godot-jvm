package com.openworld.game.mission;

import com.openworld.character.Faction;

/**
 * Mission objective type identifier constants.
 *
 * Stored as a plain String on MissionInfo (mirrors Faction.java) so designers can
 * author new objective types without touching this file. Only ELIMINATE_ALL has
 * real MissionManager logic today — the others are declared now so MissionInfo's
 * schema is stable for content authored ahead of their implementation.
 */
public final class MissionObjectiveType {

    public static final String ELIMINATE_ALL = "ELIMINATE_ALL";
    public static final String HOLD_POINT    = "HOLD_POINT";
    public static final String ESCORT        = "ESCORT";
    public static final String DELIVER       = "DELIVER";
    /** Checkpoint race (GTA SA/VC-style street race) — schema only; see PLAN.md "Race missions (groundwork)". */
    public static final String RACE          = "RACE";

    private MissionObjectiveType() {}
}
