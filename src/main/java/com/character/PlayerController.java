package com.character;

import com.vehicle.VehicleBody;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Input;
import godot.api.Timer;
import godot.core.Vector3;

/**
 * Translates human keyboard/mouse input into a UserCommand each tick.
 *
 * Equivalent to Unreal's APlayerController / Source Engine's CBasePlayer command
 * generation. Lives as a child node of a Controllable (Player or VehicleBody).
 * Detects the body type each tick via getControllable() and generates the
 * appropriate command fields:
 *   Player body     → movement, combat, weapon, jump, stance fields
 *   VehicleBody     → throttle, steering, handbrake fields
 *
 * Hot-swap (Phase 5): call setTarget(newBody) before reparenting so gatherInput()
 * immediately generates the correct command type for the incoming body.
 *
 * Network (Phase 4): on the owning client this runs locally for prediction;
 * the resulting UserCommand is stamped with a monotone sequenceNumber and stored
 * in the predictionBuffer ring buffer. When the server sends back a corrected
 * state, reconcile(serverAck) discards acknowledged entries and the caller
 * replays unacknowledged commands against the snapped server state.
 */
@RegisterClass(className = "PlayerController")
public class PlayerController extends Controller {

    private static final int BUFFER_SIZE = 64;

    // ── Client-side prediction state ──────────────────────────────────────────
    private int              localSequence    = 0;
    private final UserCommand[] predictionBuffer = new UserCommand[BUFFER_SIZE];

    // ── Cached body references (re-resolved when body type changes) ───────────
    private Player     cachedPlayer;
    private Timer      cachedAimStayTimer;
    private VehicleBody cachedVehicle;

    @RegisterFunction
    @Override
    public void _ready() {
        resolveBody();
    }

    private void resolveBody() {
        Controllable c = getControllable();
        if (c instanceof Player p) {
            cachedPlayer       = p;
            cachedAimStayTimer = (Timer) p.getNode("AimStayTimer");
            cachedVehicle      = null;
        } else if (c instanceof VehicleBody v) {
            cachedVehicle      = v;
            cachedPlayer       = null;
            cachedAimStayTimer = null;
        } else {
            cachedPlayer  = null;
            cachedVehicle = null;
        }
    }

    @Override
    public UserCommand gatherInput(double delta) {
        // Re-resolve if the body has changed (hot-swap or first tick after reparent).
        Controllable c = getControllable();
        if (c instanceof Player p && p != cachedPlayer) resolveBody();
        else if (c instanceof VehicleBody v && v != cachedVehicle) resolveBody();

        if (cachedVehicle != null) return gatherVehicleInput();
        if (cachedPlayer  != null) return gatherCharacterInput();
        return new UserCommand();
    }

    // ── Character (on-foot) input ─────────────────────────────────────────────

    private UserCommand gatherCharacterInput() {
        UserCommand cmd = new UserCommand();
        Input inp = Input.INSTANCE;
        Player body = cachedPlayer;

        // ── Movement ──────────────────────────────────────────────────────────
        float moveX = inp.getActionStrength("left")    - inp.getActionStrength("right");
        float moveZ = inp.getActionStrength("forward") - inp.getActionStrength("back");
        cmd.movementDirection.setX(moveX);
        cmd.movementDirection.setZ(moveZ);

        if (cmd.movementDirection.lengthSquared() > 0.001) {
            cmd.movementType = inp.isActionPressed("walk", false)
                    ? MovementType.WALK : MovementType.SPRINT;
        }

        // ── Combat / aim ──────────────────────────────────────────────────────
        boolean aimOrFire = inp.isActionPressed("aim", false)
                         || inp.isActionPressed("fire", false);

        Timer aimStayTimer = cachedAimStayTimer;
        if (aimOrFire) {
            aimStayTimer.stop();
        } else if (body.isCombat() && (inp.isActionJustReleased("aim", false)
                                    || inp.isActionJustReleased("fire", false))) {
            aimStayTimer.start();
        }

        cmd.wantCombat = aimOrFire || (body.isCombat() && !aimStayTimer.isStopped());

        // ── Aim target ────────────────────────────────────────────────────────
        if (cmd.wantCombat) {
            Vector3 rayDeg = body.aimRay.getRotationDegrees();
            body.aimRay.setRotationDegrees(new Vector3(rayDeg.getX(), 0.0f, 0.0f));

            if (body.aimRay.isColliding() &&
                    body.aimRay.getCollisionPoint()
                               .minus(body.aimRay.getGlobalTransform().getOrigin())
                               .length() > 0.1) {
                cmd.aimTargetPosition = body.aimRay.getCollisionPoint();
            } else {
                cmd.aimTargetPosition = body.aimRay.toGlobal(body.aimRay.getTargetPosition());
            }
        }

        // ── Weapon / body actions ─────────────────────────────────────────────
        cmd.fire    = inp.isActionPressed("fire", false);
        cmd.reload  = inp.isActionJustPressed("reload", false);
        cmd.drop    = inp.isActionJustPressed("drop", false);
        cmd.jump    = inp.isActionJustPressed("jump", false);
        cmd.roll    = inp.isActionJustPressed("roll", false);

        for (String stanceKey : body.stances.keys()) {
            if (inp.isActionJustPressed(stanceKey.toLowerCase(), false)) {
                cmd.desiredStance = StanceName.fromKey(stanceKey);
                break;
            }
        }

        // ── Sequence stamp + prediction buffer (Phase 4) ──────────────────────
        cmd.sequenceNumber = ++localSequence;
        predictionBuffer[cmd.sequenceNumber % BUFFER_SIZE] = cmd.copy();

        return cmd;
    }

    // ── Vehicle input ─────────────────────────────────────────────────────────

    /**
     * Maps keyboard to vehicle throttle/steering/handbrake using the same
     * directional action bindings as on-foot movement so no extra mappings
     * are needed in the input map.
     *
     *   forward / back  → throttle (+1 / -1)
     *   left / right    → steering (-1 / +1, negated to match Godot convention)
     *   jump            → handbrake
     *   use             → enter/exit vehicle (enterExit)
     */
    private UserCommand gatherVehicleInput() {
        UserCommand cmd = new UserCommand();
        Input inp = Input.INSTANCE;

        cmd.throttle  = inp.getActionStrength("forward") - inp.getActionStrength("back");
        cmd.steering  = -(inp.getActionStrength("right") - inp.getActionStrength("left"));
        cmd.handbrake = inp.isActionPressed("jump", false);
        cmd.enterExit = inp.isActionJustPressed("use", false);

        cmd.sequenceNumber = ++localSequence;
        predictionBuffer[cmd.sequenceNumber % BUFFER_SIZE] = cmd.copy();

        return cmd;
    }

    // ── Reconciliation (Phase 4) ──────────────────────────────────────────────

    /**
     * Discard prediction buffer entries confirmed by the server, then replay
     * any unacknowledged commands against the snapped server state.
     */
    public void reconcile(int serverAck) {
        for (int seq = serverAck; seq >= Math.max(0, serverAck - BUFFER_SIZE + 1); seq--) {
            predictionBuffer[seq % BUFFER_SIZE] = null;
        }
        // Phase 4 TODO: snap body to server state, then replay unacknowledged commands.
    }
}
