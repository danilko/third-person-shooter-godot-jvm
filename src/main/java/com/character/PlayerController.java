package com.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Input;
import godot.api.Timer;
import godot.core.Vector3;

/**
 * Translates human keyboard/mouse input into a UserCommand each tick.
 *
 * Equivalent to Unreal's APlayerController / Source Engine's CBasePlayer command
 * generation. Lives as a child node of Player. Accesses the Player body via
 * getOwner() for aimRay, aimStayTimer, and combat state.
 *
 * Network (Phase 4): on the owning client this runs locally for prediction;
 * the resulting UserCommand is stamped with a monotone sequenceNumber and stored
 * in the predictionBuffer ring buffer. When the server sends back a corrected
 * state, reconcile(serverAck) discards acknowledged entries and the caller
 * replays unacknowledged commands against the snapped server state.
 *
 * Phase 4 TODO (actual transport):
 *   - After stamping sequenceNumber, serialize the UserCommand and send to server
 *     via rpc_id(1, "server_receive_cmd", ...) or a PackedByteArray RPC.
 *   - Wire reconcile() to a signal/RPC from the server indicating divergence.
 */
@RegisterClass(className = "PlayerController")
public class PlayerController extends Controller {

    private static final int BUFFER_SIZE = 64;

    private Player body;
    private Timer  aimStayTimer;

    // ── Client-side prediction state ──────────────────────────────────────────
    private int            localSequence   = 0;
    private final UserCommand[] predictionBuffer = new UserCommand[BUFFER_SIZE];

    @RegisterFunction
    @Override
    public void _ready() {
        body = (Player) getOwner();
        aimStayTimer = (Timer) body.getNode("AimStayTimer");
    }

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();
        Input inp = Input.INSTANCE;

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
        // Phase 4 TODO: rpc_id(1, "server_receive_cmd", serialize(cmd))

        return cmd;
    }

    /**
     * Discard prediction buffer entries confirmed by the server, then replay
     * any unacknowledged commands against the snapped server state.
     *
     * Called by the network layer when the server sends a state correction.
     * @param serverAck The last sequenceNumber the server confirmed processing.
     */
    public void reconcile(int serverAck) {
        // Discard entries the server has already processed
        for (int seq = serverAck; seq >= Math.max(0, serverAck - BUFFER_SIZE + 1); seq--) {
            predictionBuffer[seq % BUFFER_SIZE] = null;
        }
        // Phase 4 TODO:
        //   1. Snap body to server-authoritative state (MultiplayerSynchronizer
        //      already wrote global_position, velocity, etc. to the body).
        //   2. Replay unacknowledged commands (serverAck+1 … localSequence):
        //        for (int seq = serverAck + 1; seq <= localSequence; seq++) {
        //            UserCommand cmd = predictionBuffer[seq % BUFFER_SIZE];
        //            if (cmd != null) body.applyInput(cmd, fixedDelta);
        //        }
        //   applyInput() is deterministic so replaying produces the corrected
        //   predicted state without touching any authoritative server data.
    }
}
