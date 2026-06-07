package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.MovementType;
import com.character.UserCommand;
import godot.core.Vector3;

public class ChaseState implements AIState {

    public static final ChaseState INSTANCE = new ChaseState();
    private ChaseState() {}

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetLostTargetTimer();
        ctrl.clearNavTarget();  // force a fresh nav update on the first chase frame
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        body.refreshTarget(delta);
        if (body.getTarget() == null) {
            return PatrolState.INSTANCE;
        }

        float dist = (float) body.getGlobalPosition()
                                 .distanceTo(body.getTarget().getGlobalPosition());
        cmd.wantCombat = true;

        boolean hasLoS = body.hasLineOfSight(delta);

        if (dist <= body.getEffectiveAttackRange() && hasLoS) {
            if (!body.hasAnyAmmo()) return RefillAmmoState.INSTANCE;
            return AttackState.INSTANCE;
        }

        cmd.movementType = MovementType.SPRINT;

        if (hasLoS) {
            ctrl.resetLostTargetTimer();
            Vector3 targetPos = body.getTarget().getGlobalPosition();
            ctrl.setLastKnownTargetPosition(new Vector3(targetPos));
            // Only request a path recompute when the target has moved > 1.5 m — prevents
            // 60 navAgent path-recomputes/sec while chasing a moving player.
            if (ctrl.shouldUpdateNav(targetPos)) {
                body.getNavAgent().setTargetPosition(targetPos);
                ctrl.recordNavTarget(targetPos);
            }
            Vector3 aimTarget = new Vector3(targetPos.getX(),
                    targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT,
                    targetPos.getZ());
            body.aimAtPosition(aimTarget, delta);
            cmd.aimTargetPosition = aimTarget;
        } else {
            ctrl.advanceLostTargetTimer(delta);
            if (ctrl.isTargetLost()) return PatrolState.INSTANCE;
            if (ctrl.hasLastKnownPosition()) {
                Vector3 lastKnown = ctrl.getLastKnownTargetPosition();
                if (ctrl.shouldUpdateNav(lastKnown)) {
                    body.getNavAgent().setTargetPosition(lastKnown);
                    ctrl.recordNavTarget(lastKnown);
                }
            }
        }

        Vector3 dir = body.getNavAgent()
                          .getNextPathPosition()
                          .minus(body.getGlobalPosition())
                          .normalized();
        cmd.movementDirection.setX(dir.getX());
        cmd.movementDirection.setZ(dir.getZ());
        return this;
    }
}
