package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.movement.character.MovementType;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import com.openworld.ai.AIState;

public class SearchState implements AIState {

    public static final SearchState INSTANCE = new SearchState();
    private SearchState() {}

    private static final double SEARCH_TIMEOUT = 5.0;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetSearchTimer();
        if (ctrl.hasLastKnownPosition() && body.getNavAgent() != null)
            body.getNavAgent().setTargetPosition(body.leashed(ctrl.getLastKnownTargetPosition()));
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        if (body.canSeeTarget(delta)) {
            float dist = (float) body.getGlobalPosition()
                                     .distanceTo(body.getTarget().getGlobalPosition());
            if (dist <= body.getEffectiveAttackRange() && body.hasAnyAmmo()) return AttackState.INSTANCE;
            return ChaseState.INSTANCE;
        }

        ctrl.advanceSearchTimer(delta);
        if (ctrl.isSearchTimedOut(SEARCH_TIMEOUT)) return PatrolState.INSTANCE;

        // Out of ammo and still under attack → flee rather than continue searching.
        if (body.behaviorConfigOrDefaults().useFleeOnAttack && !body.hasAnyAmmo()
                && ctrl.isUnderAttack()) return FleeState.INSTANCE;

        cmd.wantCombat = true;

        // a body holding a point (cover, a guard's post, PLAN.md 2.2) looks no further than its leash: straight to the
        // leash's edge when the way is clear, then it stands watching (inside a building the nav agent's path leads
        // to the nearest navmesh point outside -- guards walked 15 m off their posts after a distant sound)
        if (body.holds() && ctrl.hasLastKnownPosition()) {
            Vector3 goal = body.leashed(ctrl.getLastKnownTargetPosition());
            Vector3 off = goal.minus(body.getGlobalPosition());
            off.setY(0f);
            Vector3 look = ctrl.getLastKnownTargetPosition().plus(new Vector3(0, AICharacter.TARGET_BODY_HEIGHT, 0));
            body.aimAtPosition(look, delta);
            cmd.aimTargetPosition = look;
            if (off.length() < 1.0) {
                cmd.movementType = MovementType.IDLE;
                return this;
            }
            Vector3 dir = off.normalized();
            if (!ChaseState.walkableLine(body, goal)) {
                Vector3 nav = body.getNavAgent().getNextPathPosition().minus(body.getGlobalPosition());
                nav.setY(0f);
                if (nav.length() >= 0.5f) dir = nav.normalized();
            }
            cmd.movementType = MovementType.WALK;
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
            return this;
        }

        boolean arrived = !ctrl.hasLastKnownPosition()
                || body.getNavAgent().isNavigationFinished();

        if (arrived) {
            if (body.holds()) {
                // a held point (cover, a post): it watches from there instead of peeking about (PLAN.md 2.2)
                cmd.movementType = MovementType.IDLE;
            } else {
                if (ctrl.needsStrafeUpdate()) ctrl.refreshStrafe();
                ctrl.tickStrafeTimer(delta);
                cmd.movementDirection.setX(ctrl.getStrafeX());
                cmd.movementDirection.setZ(ctrl.getStrafeZ());
                cmd.movementType = MovementType.WALK;
            }

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
