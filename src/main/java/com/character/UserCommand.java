package com.character;

import godot.core.Vector3;

/**
 * Per-tick command snapshot — the universal protocol between Controller and Character.
 *
 * Equivalent to Source Engine's CUserCmd. Produced by a Controller each physics
 * tick and consumed by Character.applyInput().
 *
 * All fields are primitives or copied value types: cheap to copy, diff, and
 * serialize over the network. Under ownership-based authority the command never
 * crosses the wire — only the owner's resulting state does (MSG_SNAPSHOT) — so
 * this stays a purely local intent struct; tick orders inputs for debugging/audit.
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
    public boolean    wantUnequip;

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
     * Totally orders inputs (also stamped on outgoing snapshots for audit).
     */
    public long tick;

    // ── Vehicle fields (Phase 5) — ignored by Character.applyInput ────────────
    public float motor;
    public float   steering;
    public boolean handbrake;
    public boolean brake;
    public boolean enterExit;
    public boolean resetVehicle;

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
        wantUnequip       = false;
        aimTargetPosition = null;
        tick              = 0;
        motor = 0f;
        steering          = 0f;
        handbrake         = false;
        brake             = false;
        enterExit         = false;
        resetVehicle      = false;
    }

    /** Shallow copy (defensive snapshot for buffering/debugging). */
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
        c.wantUnequip     = wantUnequip;
        c.aimTargetPosition = aimTargetPosition != null
                ? new Vector3(aimTargetPosition.getX(),
                              aimTargetPosition.getY(),
                              aimTargetPosition.getZ())
                : null;
        c.tick            = tick;
        c.motor = motor;
        c.steering        = steering;
        c.handbrake       = handbrake;
        c.brake           = brake;
        c.enterExit       = enterExit;
        c.resetVehicle    = resetVehicle;
        return c;
    }
}
