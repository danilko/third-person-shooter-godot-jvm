package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.MovementType;
import com.character.UserCommand;
import godot.core.Vector3;

public class SearchState implements AIState {

    public static final SearchState INSTANCE = new SearchState();
    private SearchState() {}

    private static final double SEARCH_TIMEOUT = 5.0;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetSearchTimer();
        if (ctrl.hasLastKnownPosition() && body.getNavAgent() != null)
            body.getNavAgent().setTargetPosition(ctrl.getLastKnownTargetPosition());
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        if (body.canSeeTarget(delta)) {
            float dist = (float) body.getGlobalPosition()
                                     .distanceTo(body.getTarget().getGlobalPosition());
            if (dist <= body.attackRange && body.hasAnyAmmo()) return AttackState.INSTANCE;
            return ChaseState.INSTANCE;
        }

        ctrl.advanceSearchTimer(delta);
        if (ctrl.isSearchTimedOut(SEARCH_TIMEOUT)) return PatrolState.INSTANCE;

        cmd.wantCombat = true;

        boolean arrived = !ctrl.hasLastKnownPosition()
                || body.getNavAgent().isNavigationFinished();

        if (arrived) {
            if (ctrl.needsStrafeUpdate()) ctrl.refreshStrafe();
            ctrl.tickStrafeTimer(delta);
            cmd.movementDirection.setX(ctrl.getStrafeX());
            cmd.movementDirection.setZ(ctrl.getStrafeZ());
            cmd.movementType = MovementType.WALK;

            if (ctrl.hasLastKnownPosition()) {
                Vector3 look = ctrl.getLastKnownTargetPosition()
                        .plus(new Vector3(0, AICharacter.TARGET_BODY_HEIGHT, 0));
                body.aimAtPosition(look, delta);
                cmd.aimTargetPosition = look;
            }
        } else {
            cmd.movementType = MovementType.SPRINT;
            Vector3 dir = body.getNavAgent()
                              .getNextPathPosition()
                              .minus(body.getGlobalPosition())
                              .normalized();
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        }

        return this;
    }
}
