package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import com.openworld.ai.AIState;

/**
 * Sprints away from the last known threat position until the AI has covered
 * fleeDistance metres or a timeout expires, then returns to PatrolState.
 *
 * Entry points:
 *   PatrolState  — when isUnderAttack AND useFleeOnAttack AND no ammo
 *   SearchState  — when useFleeOnAttack AND no ammo
 *
 * The flee direction is the vector from the last known threat position to the
 * AI's position (directly away from the attacker). The navigation target is
 * set once on entry; NavAgent handles obstacle avoidance during the sprint.
 */
public class FleeState implements AIState {

    public static final FleeState INSTANCE = new FleeState();
    private FleeState() {}

    private static final double FLEE_TIMEOUT = 10.0;  // hard cap in case NavAgent can't reach goal

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetSearchTimer();
        ctrl.setFleeStartPosition(body.getGlobalPosition());
        body.forceSetStance(StanceName.UPRIGHT);

        // Navigate directly away from the last known threat.
        Vector3 myPos     = body.getGlobalPosition();
        Vector3 threatPos = ctrl.getLastKnownTargetPosition();
        Vector3 fleeDir;
        if (threatPos != null) {
            fleeDir = myPos.minus(threatPos).normalized();
            if (fleeDir.lengthSquared() < 0.001f) fleeDir = new Vector3(1f, 0f, 0f);
        } else {
            fleeDir = new Vector3(1f, 0f, 0f); // no known threat: flee along +X as fallback
        }
        float goalDist = body.getBehaviorConfig().fleeDistance;
        body.getNavAgent().setTargetPosition(myPos.plus(fleeDir.times(goalDist)));
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        ctrl.advanceSearchTimer(delta);
        if (ctrl.isSearchTimedOut(FLEE_TIMEOUT)) return PatrolState.INSTANCE;

        // Return to patrol once far enough from the start of the flee.
        Vector3 fleeStart = ctrl.getFleeStartPosition();
        if (fleeStart != null) {
            float distFled = (float) body.getGlobalPosition().distanceTo(fleeStart);
            if (distFled >= body.getBehaviorConfig().fleeDistance) return PatrolState.INSTANCE;
        }

        // Nav finished before hitting the distance target (ran into a dead end).
        if (body.getNavAgent().isNavigationFinished()) return PatrolState.INSTANCE;

        cmd.wantCombat   = false;
        cmd.movementType = MovementType.SPRINT;
        Vector3 dir = body.getNavAgent()
                .getNextPathPosition()
                .minus(body.getGlobalPosition())
                .normalized();
        cmd.movementDirection.setX(dir.getX());
        cmd.movementDirection.setZ(dir.getZ());

        return this;
    }
}
