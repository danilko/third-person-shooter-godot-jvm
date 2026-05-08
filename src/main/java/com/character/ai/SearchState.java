package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;
import com.character.MovementType;
import godot.core.Vector3;

/**
 * AI sprints to the target's last known position and searches the area.
 * Triggered when LoS is lost during combat or when the AI is hit while patrolling.
 * Re-engages immediately if the target is spotted; gives up after {@link #SEARCH_TIMEOUT}.
 */
public class SearchState implements AIState {

    public static final SearchState INSTANCE = new SearchState();

    private SearchState() {}

    private static final double SEARCH_TIMEOUT = 5.0;

    @Override
    public void enter(AICharacter c) {
        c.resetSearchTimer();
        if (c.hasLastKnownPosition() && c.getNavAgent() != null)
            c.getNavAgent().setTargetPosition(c.getLastKnownTargetPosition());
    }

    @Override
    public void exit(AICharacter c) {}

    @Override
    public AIState update(AICharacter c, CharacterInput input, double delta) {
        if (c.canSeeTarget()) {
            float dist = (float) c.getGlobalPosition()
                                   .distanceTo(c.getTarget().getGlobalPosition());
            if (dist <= c.attackRange && c.hasAnyAmmo()) return AttackState.INSTANCE;
            return ChaseState.INSTANCE;
        }

        c.advanceSearchTimer(delta);
        if (c.isSearchTimedOut(SEARCH_TIMEOUT)) return PatrolState.INSTANCE;

        input.wantCombat = true;

        boolean arrivedAtLastKnown = !c.hasLastKnownPosition()
                || c.getNavAgent().isNavigationFinished();

        if (arrivedAtLastKnown) {
            if (c.needsStrafeUpdate()) c.refreshStrafe();
            c.tickStrafeTimer(delta);
            input.movementDirection.setX(c.getStrafeX());
            input.movementDirection.setZ(c.getStrafeZ());
            input.movementType = MovementType.WALK;

            if (c.hasLastKnownPosition()) {
                Vector3 lookTarget = c.getLastKnownTargetPosition()
                        .plus(new Vector3(0, AICharacter.TARGET_BODY_HEIGHT, 0));
                c.aimAtPosition(lookTarget, delta);
                input.aimTargetPosition = lookTarget;
            }
        } else {
            input.movementType = MovementType.SPRINT;
            Vector3 dir = c.getNavAgent()
                           .getNextPathPosition()
                           .minus(c.getGlobalPosition())
                           .normalized();
            input.movementDirection.setX(dir.getX());
            input.movementDirection.setZ(dir.getZ());
        }

        return this;
    }
}
