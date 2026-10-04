package com.openworld.ai;

import com.openworld.control.Controller;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import godot.annotation.Script;
import godot.core.Vector3;

/**
 * A shop clerk at the register (PLAN.md W3): stands still facing the counter, hands empty. When threatened and
 * the clerk gives up ({@link #surrender}) it crouches behind the counter and stays there. A clerk that fights back
 * is handed the ordinary AI brain instead (world.ShopClerkSpot does that), so this controller has no combat.
 */
@Script(className = "ClerkController")
public class ClerkController extends Controller {

    /** The world point the clerk faces (over the counter). */
    public Vector3 facePoint;
    public boolean surrendered;

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();
        cmd.movementDirection = Vector3.Companion.getZERO();
        cmd.movementType = MovementType.IDLE;
        cmd.wantCombat = false;
        cmd.desiredStance = surrendered ? StanceName.CROUCH : StanceName.UPRIGHT;
        cmd.aimTargetPosition = facePoint;
        return cmd;
    }
}
