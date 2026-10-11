package com.openworld.game.mission;

import com.openworld.game.activity.Activity;
import com.openworld.game.activity.ActivityInstance;
import com.openworld.game.activity.ActivityPlacement;
import com.openworld.game.activity.ActivityRuntime;
import com.openworld.game.campaign.content.KonbiniActivity;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node3D;
import godot.core.VariantArray;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * WHERE "the konbini job" is in the world, and its tuning (PLAN.md 2.1): the PLACEMENT of the activity
 * {@code m01_konbini}. The mission itself -- its stages, its fail rule, what each outcome changes -- is
 * {@link KonbiniActivity} and {@code Act1}'s row for it; the framework ({@code ActivityDirector}) owns who may start
 * it, the host check, the door unlocks and the cleanup this node used to hand-roll.
 *
 * <p><b>The frame (2026-10-11).</b> {@code island_buildings} puts this node on the shop's footprint CENTRE and turns
 * it to the shop's yaw, so the scene is authored in the BUILDING's frame: +Z is the shop front (a KonbiniS is
 * 12.7 x 18.2 m, its sliding door at local (3.64, 9.1)). The crew stands on the pavement at z 11-12; the start zone
 * is the whole shop plus that pavement, so the job is offered inside the store too. The shop is an ordinary OPEN
 * konbini (`_Shop`: clerk, counter, weapons) -- it was a locked mission building with the crew inside it.
 *
 * <p>The scene ({@code M01_Konbini.tscn}) carries what a level designer places: this node, the
 * {@code ZoneTrigger} whose beat id is the activity's start zone, and the {@code Zone} that streams the crew of named
 * story characters. The exports below are the run's tuning, handed to it in {@link #configure}.
 */
@Script(className = "KonbiniMission")
public class KonbiniMission extends Node3D implements ActivityPlacement {

    public static final String VARIANT_KILLED = "BOSS_KILLED";
    public static final String VARIANT_SPARED = "BOSS_SPARED";

    @Export public String missionId = "m01_konbini";
    @Export public String bossId = "m01_boss";
    @Export public VariantArray<String> crewIds = new VariantArray<>(String.class);
    @Export public String hostileFaction = com.openworld.character.Faction.GANG_A;
    @Export public float surrenderHealthFraction = 0.5f;
    @Export public float spareDistance = 45f;
    @Export public float spareSeconds = 15f;
    /**
     * While the job runs, every LOCKED {@code world.Door} within this of the node is unlocked, so the player may
     * open the shop (its building is placed as the `_Open` variant, whose doors ship locked -- every other building
     * in the city is shut for good). Re-locked when the job ends: a shop is open for the job, not for ever.
     */
    @Export public float doorUnlockRadius = 25f;

    /** IDLE, then the run's stage (FIGHT, SURRENDER), then DONE -- probe readout. */
    @Visible public String phase = "IDLE";
    /** The variant it completed with, or "FAILED: why" -- probe readout. */
    @Visible public String outcome = "";

    @Register
    @Override
    public void _ready() {
        ActivityRuntime rt = ActivityRuntime.get();
        if (rt == null) {
            GD.printErr("[KonbiniMission] no ActivityRuntime autoload -- the mission cannot run");
            return;
        }
        rt.place(this);
    }

    @Register
    @Override
    public void _exitTree() {
        ActivityRuntime rt = ActivityRuntime.get();
        if (rt != null) rt.unplace(this);
    }

    @Override public String placedActivityId() { return missionId; }

    @Override public void configure(Activity activity) {
        if (!(activity instanceof KonbiniActivity k)) return;
        k.boss = bossId;
        List<String> crew = new ArrayList<>();
        for (int i = 0; i < crewIds.size(); i++) crew.add(crewIds.get(i));
        k.crew = crew;
        k.hostileFaction = hostileFaction;
        k.surrenderHealthFraction = surrenderHealthFraction;
        k.spareDistance = spareDistance;
        k.spareSeconds = spareSeconds;
        k.doorUnlockRadius = doorUnlockRadius;
    }

    @Override public void stageEntered(String stageId) {
        phase = stageId;
        outcome = "";
    }

    @Override public void ended(ActivityInstance.Outcome how, String variant, String reason) {
        phase = "DONE";
        outcome = how == ActivityInstance.Outcome.COMPLETED ? variant : "FAILED: " + reason;
    }

    /** Console / probe entry: start the job for this machine's player as if they had walked in. */
    @Register
    public boolean startNow() {
        ActivityRuntime rt = ActivityRuntime.get();
        return rt != null && rt.startNow(missionId, "STORY").isEmpty();
    }

    /** How many doors the running job holds unlocked -- probe readout. */
    @Register
    public int unlockedDoorsNow() {
        ActivityRuntime rt = ActivityRuntime.get();
        return rt == null ? 0 : rt.doorsHeldNow(missionId);
    }
}
