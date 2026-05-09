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
 * the resulting UserCommand is also sent to the server. isAuthority() returns
 * true only on the owning client via the parent Controller implementation.
 */
@RegisterClass(className = "PlayerController")
public class PlayerController extends Controller {

    private Player body;
    private Timer  aimStayTimer;

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

        return cmd;
    }
}
