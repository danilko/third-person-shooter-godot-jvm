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
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        // Re-evaluate nearest live hostile each frame so a closer threat is not ignored.
        body.refreshTarget(delta);
        if (body.getTarget() == null) {
            return PatrolState.INSTANCE;
        }

        float dist = (float) body.getGlobalPosition()
                                 .distanceTo(body.getTarget().getGlobalPosition());
        cmd.wantCombat = true;

        // Evaluate LoS once and reuse — avoids two forced raycasts per frame.
        boolean hasLoS = body.hasLineOfSight(delta);

        if (dist <= body.attackRange && hasLoS) {
            if (!body.hasAnyAmmo()) return RefillAmmoState.INSTANCE;
            return AttackState.INSTANCE;
        }

        cmd.movementType = MovementType.SPRINT;

        if (hasLoS) {
            ctrl.resetLostTargetTimer();
            Vector3 targetPos = body.getTarget().getGlobalPosition();
            ctrl.setLastKnownTargetPosition(new Vector3(targetPos));
            body.getNavAgent().setTargetPosition(targetPos);

            Vector3 aimTarget = new Vector3(targetPos.getX(),
                    targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT,
                    targetPos.getZ());
            body.aimAtPosition(aimTarget, delta);
            cmd.aimTargetPosition = aimTarget;
        } else {
            ctrl.advanceLostTargetTimer(delta);
            if (ctrl.isTargetLost()) return PatrolState.INSTANCE;
            if (ctrl.hasLastKnownPosition())
                body.getNavAgent().setTargetPosition(ctrl.getLastKnownTargetPosition());
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
