package com.openworld.control;

import godot.core.Vector3;
import com.openworld.ai.AIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.net.NetworkController;

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

    /**
     * Raw "looking down the sights" intent for this tick — the aim button HELD, nothing else.
     *
     * <p>Deliberately NOT {@link #wantCombat}, which is a wider thing: it is also set by firing, by
     * the aim-stay timer, and unconditionally in first person. The scope is the one consumer that
     * needs the button itself, because a scoped rifle carried in FPS must not be permanently scoped.
     * What it is allowed to mean is decided downstream — {@code WeaponController.isScoped()} asks the
     * held weapon whether it has a scope at all, and {@code Character.isScoped()} refuses while dead
     * or riding — so this stays a plain intent and every way out of the scope is a derivation rather
     * than a call site somebody has to remember (PLAN.md 2.7 piece 1).
     */
    public boolean wantScope;

    /**
     * Hold-breath input, raw — the key held. Only means anything while scoped, and whether a hold is
     * running is {@code camera.ScopeSway}'s to decide (it needs a fresh press and breath to spend).
     */
    public boolean holdBreath;

    /** No scope zoom request this tick. */
    public static final int SCOPE_ZOOM_NONE = 0;
    /** Wheel up: off -> first level -> closer level (stops there), latched with no button held. */
    public static final int SCOPE_ZOOM_IN = 1;
    /** Wheel down: closer level -> first level -> off. */
    public static final int SCOPE_ZOOM_OUT = -1;
    /** Toggle: off -> first level -> closer level -> off, latched with no button held (middle mouse — CS's AWP right click). */
    public static final int SCOPE_ZOOM_CYCLE = 2;

    /**
     * A one-tick EDGE: which way to change the scope's zoom level ({@code SCOPE_ZOOM_*}). Meaningless
     * unless a scope is raised; {@code WeaponController.applyScopeZoom} decides.
     */
    public int scopeZoom;

    // ── Weapon actions ────────────────────────────────────────────────────────
    public boolean fire;
    public boolean reload;
    /** One-tick edge: the remote-charge detonator (REC1), set off whatever is held (GTA's sticky bomb). */
    public boolean detonate;
    public boolean drop;

    // ── Body actions ──────────────────────────────────────────────────────────
    public boolean jump;

    /** Vertical swim intent while in the SWIM stance: +1 surface/ascend, -1 dive, 0 hold. */
    public double swimVertical;

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
    /** False (player): {@code steering} is a turn <b>rate</b> the wheel integrates (hold-to-turn).
     *  True (AI): {@code steering} is the desired <b>normalized wheel angle</b> [-1,1] the wheel
     *  converges to — see VehicleWheel.applyWheelSteering. Lets AI hold a stable steer angle instead
     *  of winding the rate integrator (the cornering-wobble fix, I3b). */
    public boolean steerToTarget;
    public boolean handbrake;
    public boolean brake;
    public boolean enterExit;
    public boolean resetVehicle;
    /** NOS/booster held (vehicle only) — sprint action while driving. */
    public boolean boost;

    // ── Construction ──────────────────────────────────────────────────────────
    public UserCommand() {
        movementDirection = new Vector3();
        movementType      = MovementType.IDLE;
        wantCombat        = false;
        wantScope         = false;
        holdBreath        = false;
        scopeZoom         = SCOPE_ZOOM_NONE;
        fire              = false;
        reload            = false;
        drop              = false;
        jump              = false;
        swimVertical      = 0.0;
        desiredStance     = null;
        desiredWeapon     = -1;
        wantUnequip       = false;
        aimTargetPosition = null;
        tick              = 0;
        motor = 0f;
        steering          = 0f;
        steerToTarget     = false;
        handbrake         = false;
        brake             = false;
        enterExit         = false;
        resetVehicle      = false;
        boost             = false;
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
        c.wantScope       = wantScope;
        c.holdBreath      = holdBreath;
        c.scopeZoom       = scopeZoom;
        c.fire            = fire;
        c.reload          = reload;
        c.drop            = drop;
        c.jump            = jump;
        c.swimVertical    = swimVertical;
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
        c.steerToTarget   = steerToTarget;
        c.handbrake       = handbrake;
        c.brake           = brake;
        c.enterExit       = enterExit;
        c.resetVehicle    = resetVehicle;
        c.boost           = boost;
        return c;
    }
}
