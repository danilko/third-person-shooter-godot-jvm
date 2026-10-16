package com.openworld.ai;

import godot.core.Vector3;

import java.util.List;

/**
 * The ORDERS an outside system gives an AI (PLAN.md P1c / 2.3): what an encounter, a building's guard post, an
 * activity or the dispatch writes, and what the FSM states read. One per {@code AICharacter} and one per light
 * combatant ({@code ai.light.LightCombatants}) -- the SAME object is handed across when a light combatant is promoted
 * to a full body and back when it is demoted, so an order survives the tier change. Plain Java: never replicated
 * (the host decides; clients see the bodies), never a Godot Resource (a .tscn-embedded one would be shared).
 *
 * <p>Not a behaviour tree: the states stay the FSM's, this only says where and at whom.
 */
public final class AIBlackboard {

    // ── where it fights (PLAN.md 2.2: moved from AICharacter) ──
    /** Hostile to every PLAYER whatever the faction table says (an engaged encounter: a gang crew that has turned on
     *  the players without the whole gang turning). Other AI are judged by the table as usual. */
    public boolean huntsPlayers;
    /** A point it fights FROM (a cover marker, a guard's post): it goes there and holds it instead of strafing, and
     *  will not chase further than {@link #holdLeash} from it. Null = fights anywhere (the default). */
    public Vector3 holdPoint;
    /** How far from {@link #holdPoint} it may chase a target (m); 0 = it never leaves the point. */
    public double holdLeash;
    /** Crouch at the hold point between shots (a low cover: a car, a crate, a wall's end). */
    public boolean holdCrouch;
    /** A patrol ROUTE walked in order and round again, instead of the random walk round the spawn point. */
    public List<Vector3> patrolRoute;
    /** Calm, it stands ON {@link #holdPoint} instead of strolling round its spawn point (a guard's post). */
    public boolean standsAtPost;
    /** Where a calm body stands facing when its walk is done (a guard's post looks out of its marker's -Z). */
    public Vector3 postFacePoint;

    // ── who placed it and at whom (PLAN.md 2.3) ──
    /** What placed it ("encounter:<id>", "horde", a station id, an activity id); "" = ambient. Read by whoever
     *  counts its own members, so a light one and its full body are the same member. */
    public String owner = "";
    /** A character id an activity says to go for, ahead of whatever is nearer; "" = the nearest hostile. */
    public String pinnedTarget = "";

    // ── the LOOK it was given, so the other tier can wear it (PLAN.md 2.3) ──
    /** The body ("shino", "fumiriya", ...): the light tier draws its VAT bake, a full body wears its visuals. */
    public String body = "";
    /** The outfit (character/outfits.json) both tiers dress it in; "" = the body as authored. */
    public String outfit = "";
    /** The loadout key it was armed from (character/loadouts.json), "" = none. */
    public String loadout = "";
    /** The weapon it carries in its hands (its loadout's roll), "" = fists. */
    public String weapon = "";
    /** The side it was spawned as (the dispatch's side: police / gang id / ...), for UnitSpawner. */
    public String side = "";
    /** Its faction (may differ from the side whose clothes it wears). */
    public String faction = "";

    /** Does it fight from a point? (Whether it may right now is the body's question: it needs a loaded gun.) */
    public boolean hasHoldPoint() { return holdPoint != null; }

    /** {@code goal} kept within {@link #holdLeash} of {@link #holdPoint}; the same object when there is no hold point
     *  or it is inside the leash. Pure: the light tier and the full body use the same rule. */
    public Vector3 leashed(Vector3 goal) {
        if (holdPoint == null || goal == null) return goal;
        double dx = goal.getX() - holdPoint.getX(), dz = goal.getZ() - holdPoint.getZ();
        double len = Math.sqrt(dx * dx + dz * dz);
        if (len <= holdLeash) return goal;
        if (holdLeash <= 0.01 || len < 1e-3) return new Vector3(holdPoint);
        double k = holdLeash / len;
        return new Vector3(holdPoint.getX() + dx * k, holdPoint.getY(), holdPoint.getZ() + dz * k);
    }
}
