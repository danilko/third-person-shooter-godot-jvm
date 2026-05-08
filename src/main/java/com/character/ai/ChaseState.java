package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;
import com.character.MovementType;
import godot.core.Vector3;

/**
 * AI character sprints toward the target and enters attack range.
 * Navigates toward last known target position when LoS is broken.
 * Falls back to {@link PatrolState} after losing the target for too long.
 */
public class ChaseState implements AIState {

    public static final ChaseState INSTANCE = new ChaseState();

    private ChaseState() {}

    @Override
    public void enter(AICharacter c) {
        c.resetLostTargetTimer();
    }

    @Override
    public void exit(AICharacter c) {}

    @Override
    public AIState update(AICharacter c, CharacterInput input, double delta) {
        if (c.getTarget() == null) return PatrolState.INSTANCE;

        float dist = (float) c.getGlobalPosition()
                               .distanceTo(c.getTarget().getGlobalPosition());

        input.wantCombat = true;

        if (dist <= c.attackRange && c.hasLineOfSight()) {
            if (!c.hasAnyAmmo()) return RefillAmmoState.INSTANCE;
            return AttackState.INSTANCE;
        }

        input.movementType = MovementType.SPRINT;

        if (c.hasLineOfSight()) {
            c.resetLostTargetTimer();
            Vector3 targetPos = c.getTarget().getGlobalPosition();
            c.setLastKnownTargetPosition(new Vector3(targetPos));
            c.getNavAgent().setTargetPosition(targetPos);

            Vector3 aimTarget = new Vector3(targetPos.getX(),
                    targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT,
                    targetPos.getZ());
            c.aimAtPosition(aimTarget, delta);
            input.aimTargetPosition = aimTarget;
        } else {
            c.advanceLostTargetTimer(delta);
            if (c.isTargetLost()) return PatrolState.INSTANCE;
            if (c.hasLastKnownPosition())
                c.getNavAgent().setTargetPosition(c.getLastKnownTargetPosition());
        }

        Vector3 dir = c.getNavAgent()
                       .getNextPathPosition()
                       .minus(c.getGlobalPosition())
                       .normalized();
        input.movementDirection.setX(dir.getX());
        input.movementDirection.setZ(dir.getZ());

        return this;
    }
}
