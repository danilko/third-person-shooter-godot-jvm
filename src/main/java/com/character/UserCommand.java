package com.character;

import godot.core.Vector3;

/**
 * Per-tick command snapshot — the universal protocol between Controller and Character.
 *
 * Equivalent to Source Engine's CUserCmd. Produced by a Controller each physics
 * tick and consumed by Character.applyInput().
 *
 * All fields are primitives or copied value types: cheap to copy, diff, and
 * serialize over the network. The tick counter and sequence fields support
 * client-side prediction and server reconciliation (Phase 4).
 */
public class UserCommand {

    // ── Movement ──────────────────────────────────────────────────────────────
    public Vector3       movementDirection;
    public MovementType  movementType;

    // ── Combat ────────────────────────────────────────────────────────────────
    public boolean wantCombat;

    // ── Weapon actions ────────────────────────────────────────────────────────
    public boolean fire;
    public boolean reload;
    public boolean drop;

    // ── Body actions ──────────────────────────────────────────────────────────
    public boolean jump;
    public boolean roll;

    // ── State requests ────────────────────────────────────────────────────────
    public StanceName desiredStance;
    public int        desiredWeapon;

    // ── Aim ───────────────────────────────────────────────────────────────────
    /**
     * World-space position the character is aiming at this tick.
     * null = do not update AimTarget node.
     * PlayerController: from camera raycast. AIController: tracked target position.
     * NetworkController: received from server authoritative aim state.
     */
    public Vector3 aimTargetPosition;

    // ── Network sequencing ────────────────────────────────────────────────────
    /**
     * Monotonically increasing tick number stamped by Character._physicsProcess.
     * Totally orders inputs for replay during server reconciliation.
     */
    public long tick;

    /**
     * Client-side send sequence, incremented each time the owning client sends
     * this command to the server. Used by the server to detect gaps.
     */
    public int sequenceNumber;

    /**
     * Last command sequence the server confirmed processing.
     * Client discards prediction buffer entries at or below this value.
     */
    public int lastServerAck;

    // ── Vehicle fields (Phase 5) — ignored by Character.applyInput ────────────
    public float   throttle;
    public float   steering;
    public boolean handbrake;
    public boolean drift;
    public boolean enterExit;

    // ── Construction ──────────────────────────────────────────────────────────
    public UserCommand() {
        movementDirection = new Vector3();
        movementType      = MovementType.IDLE;
        wantCombat        = false;
        fire              = false;
        reload            = false;
        drop              = false;
        jump              = false;
        roll              = false;
        desiredStance     = null;
        desiredWeapon     = -1;
        aimTargetPosition = null;
        tick              = 0;
        sequenceNumber    = 0;
        lastServerAck     = 0;
        throttle          = 0f;
        steering          = 0f;
        handbrake         = false;
        drift             = false;
        enterExit         = false;
    }

    /** Shallow copy for prediction rollback buffer. */
    public UserCommand copy() {
        UserCommand c     = new UserCommand();
        c.movementDirection = new Vector3(
                movementDirection.getX(),
                movementDirection.getY(),
                movementDirection.getZ());
        c.movementType    = movementType;
        c.wantCombat      = wantCombat;
        c.fire            = fire;
        c.reload          = reload;
        c.drop            = drop;
        c.jump            = jump;
        c.roll            = roll;
        c.desiredStance   = desiredStance;
        c.desiredWeapon   = desiredWeapon;
        c.aimTargetPosition = aimTargetPosition != null
                ? new Vector3(aimTargetPosition.getX(),
                              aimTargetPosition.getY(),
                              aimTargetPosition.getZ())
                : null;
        c.tick            = tick;
        c.sequenceNumber  = sequenceNumber;
        c.lastServerAck   = lastServerAck;
        c.throttle        = throttle;
        c.steering        = steering;
        c.handbrake       = handbrake;
        c.drift           = drift;
        c.enterExit       = enterExit;
        return c;
    }
}
