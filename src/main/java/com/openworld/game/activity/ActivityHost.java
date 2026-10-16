package com.openworld.game.activity;

import com.openworld.game.campaign.CampaignWrite;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.event.Spot;
import com.openworld.game.profile.CareerState;

import java.util.List;

/**
 * Everything an {@link Activity} and the {@link ActivityDirector} ask of the WORLD (PLAN.md 2.1): the players, the
 * story characters, the place, how the player is told things, money. Two implementations: the engine's
 * ({@code ActivityRuntime}, over the live scene, the profiles and the ledger) and {@link FakeActivityHost} (a table
 * in memory with a clock a test advances). An activity that needs something new of the world adds it HERE, never by
 * reaching into the scene.
 *
 * <p>A PLAYER is named by their player id (the body's characterId, which is their PersistentPlayerId); a story
 * CHARACTER by its authored id.
 */
public interface ActivityHost {

    // ── players ──

    /** Is this player in the session with a body? */
    boolean playerPresent(String playerId);

    /** Dead or downed. */
    boolean playerDown(String playerId);

    Spot playerAt(String playerId);

    /** Does the WORLD belong to this player (the host, or the one player of a single-player game)? */
    boolean ownsWorld(String playerId);

    /** A guest asks to run a world-altering activity in this world: has the host said yes (once)? */
    boolean worldConsent(String activityId, String guestId);

    /** This player's story with the world they are in: what requirements are asked of and effects written to.
     *  Null when the player has no profile here. */
    CampaignWrite story(String playerId);

    /** Null when the player has none here. */
    CareerState career(String playerId);

    /** The player's story advanced: take their campaign checkpoint (what a game over rolls them back to, CR4). */
    void storyCheckpoint(String playerId);

    /** Keep (or, with null, forget) the run's checkpoint in its owner's profile (CR5). */
    void keepCheckpoint(String playerId, ActivityCheckpoint checkpoint);

    ActivityCheckpoint keptCheckpoint(String playerId);

    // ── story characters ──

    /** Is its body in the world now (its zone streamed in)? */
    boolean present(String characterId);

    boolean alive(String characterId);

    /** 0..1; 0 when it is not present. */
    double healthFraction(String characterId);

    Spot at(String characterId);

    /** "" when it is not present. */
    String faction(String characterId);

    void setFaction(String characterId, String faction);

    /** Put its AI in a scripted state ({@code ScriptCommand}'s names: "FLEE", "PATROL", ...). */
    void command(String characterId, String state);

    /** Give it back to its own AI. */
    void uncommand(String characterId);

    // ── the place ──

    /** Where the activity is placed in the world (its placement node); {@link Spot#NOWHERE} when it has none. */
    Spot anchor(String activityId);

    /** A placement may tune the run before its first stage (typed: it sets the activity's public fields). */
    void configure(String activityId, Activity activity);

    /** Unlock every LOCKED door within {@code radius} of {@code at} for this run; returns how many. */
    int unlockDoors(String instanceId, Spot at, double radius);

    /** The run's faction overlay (empty = none). */
    void relations(String instanceId, List<Plan.Relation> rows);

    /** The run's hold on the police and the gangs (Plan's noDispatch / wanted* / squad / reserve / incident, PLAN.md
     *  P1e step 5), for its participants until {@link #release}. */
    void enforcement(String instanceId, String activityId, Plan.Enforcement hooks);

    /** Can this world requirement, which does not hold, be staged as a temporary overlay for a REPLAY? */
    boolean canStage(Requirement need);

    void stage(String instanceId, List<Requirement> needs);

    /** Undo everything the run took of the world: its doors, its faction overlay, its enforcement hooks and
     *  reserved bodies, its marker, a staged replay world. Called once at its end, whatever the end. */
    void release(String instanceId);

    // ── telling the player ──

    /** This player stands where the activity starts and may start it: offer it (a prompt naming it; taking it is
     *  {@code ActivityDirector.accept}). Never started by merely walking in. */
    void offer(String activityId, String playerId);

    /** The run's participants are told what to do now: a speaker's line ("" = nobody speaks, it is the objective). */
    void say(String instanceId, String speaker, String line);

    /** Mark something in the world for the participants: a cast member or a marker id; "" clears it. */
    void mark(String instanceId, String what);

    // ── money ──

    /** The economy table's reward for completing it (0 = none). */
    long reward(String activityId);

    void pay(String playerId, long dollars);

    void log(String line);
}
