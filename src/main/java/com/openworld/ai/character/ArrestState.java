package com.openworld.ai.character;

import com.openworld.ai.AIController;
import com.openworld.ai.AIState;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.MovementType;
import godot.core.Vector3;

/**
 * A police officer running a wanted player down to ARREST them (game.EnforcementDispatch; PLAN.md W5). The low-star
 * half of the GTA rule: below the dispatch's {@code shoot_at} stars, and while the player is not lethal-wanted, police
 * close in with a weapon drawn and aimed, and do not fire. The dispatcher decides the arrest itself (an officer within
 * reach of the player for long enough) and moves the officer to the shooting FSM when the stars climb.
 *
 * <p>The target lives on the {@link AIController} ({@link AIController#getPursuit()}), the stateless-singleton rule.
 * No pursuit, or a dead one -> back to Patrol. Steering is {@link ScriptedMoveState}'s (the NavAgent only while it
 * genuinely leads somewhere).
 */
public class ArrestState implements AIState {

    public static final ArrestState INSTANCE = new ArrestState();
    private ArrestState() {}

    /** Sprint until this close, then walk the last metres (the arrest reach is the dispatcher's, ~2 m). */
    private static final float WALK_INSIDE = 6.0f;
    /** Stop pushing inside this: standing on the player's feet makes nobody arrested faster. */
    private static final float HOLD_INSIDE = 1.4f;
    /** Draw and aim inside this. */
    private static final float AIM_INSIDE = 25.0f;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        body.clearTarget();
        ctrl.clearNavTarget();
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        Character p = ctrl.getPursuit();
        if (p == null || !p.isAlive()) return PatrolState.INSTANCE;
        Vector3 at = p.getGlobalPosition();
        if (body.getNavAgent() != null && ctrl.shouldUpdateNav(at)) {
            body.getNavAgent().setTargetPosition(at);
            ctrl.recordNavTarget(new Vector3(at));
        }
        Vector3 d = at.minus(body.getGlobalPosition());
        d.setY(0f);
        float dist = (float) d.length();
        if (ctrl.pursuitAway) {          // stood down: walk away from the player, straight
            cmd.movementType = MovementType.WALK;
            if (dist > 0.001f) {
                cmd.movementDirection.setX(-d.getX() / dist);
                cmd.movementDirection.setZ(-d.getZ() / dist);
            }
            return this;
        }
        if (dist <= AIM_INSIDE) {
            cmd.wantCombat = true;
            Vector3 chest = at.plus(new Vector3(0, 1.2, 0));
            cmd.aimTargetPosition = chest;
            body.aimAtPosition(chest, delta);
        }
        if (dist <= HOLD_INSIDE || ctrl.pursuitStand) {
            cmd.movementType = MovementType.IDLE;
            return this;
        }
        cmd.movementType = dist > WALK_INSIDE ? MovementType.SPRINT : MovementType.WALK;
        Vector3 dir = ctrl.pursuitDirect ? (d.length() > 0.001 ? d.normalized() : null)
                : ScriptedMoveState.steerDirection(body, at);
        if (dir != null) {
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        }
        return this;
    }
}
