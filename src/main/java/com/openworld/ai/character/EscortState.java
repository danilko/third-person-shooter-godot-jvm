package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.character.Character;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import com.openworld.ai.AIState;

/**
 * Follows a designated escort target at a configurable distance.
 *
 * Transitions:
 *   → AttackState  when escort target takes damage AND a hostile is in attack range
 *   → ChaseState   when escort target takes damage AND a hostile is visible but far
 *   → PatrolState  when escort target dies or is cleared
 *
 * The escort target is set on AICharacter.escortTarget (populated from the
 * inspector NodePath or at runtime via AICharacter.setEscortTarget()).
 * AICharacter.onEscortTargetDamaged() sets the escortTargetUnderAttack flag in
 * AIController whenever the escorted character takes a hit.
 */
public class EscortState implements AIState {

    public static final EscortState INSTANCE = new EscortState();
    private EscortState() {}

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.clearNavTarget();
        ctrl.clearEscortTargetAttacked();
        ctrl.resetLostTargetTimer();
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {
        ctrl.clearEscortTargetAttacked();
        body.forceSetStance(StanceName.UPRIGHT);
    }

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        Character target = body.escortTarget;

        // Escort target gone or dead → return to patrol.
        if (target == null || !target.isAlive()) {
            body.escortTarget = null;
            return PatrolState.INSTANCE;
        }

        // Escort target was hit → scan for the attacker and engage.
        if (ctrl.isEscortTargetUnderAttack()) {
            body.refreshTarget(delta);
            Character hostile = body.getTarget();
            if (hostile != null && hostile.isAlive()) {
                float dist = (float) body.getGlobalPosition()
                        .distanceTo(hostile.getGlobalPosition());
                ctrl.clearEscortTargetAttacked();
                if (dist <= body.getEffectiveAttackRange() && body.hasAnyAmmo())
                    return AttackState.INSTANCE;
                return ChaseState.INSTANCE;
            }
            // No hostile found nearby — clear flag and resume escort.
            ctrl.clearEscortTargetAttacked();
        }

        // Follow the escort target.
        float myDist    = (float) body.getGlobalPosition().distanceTo(target.getGlobalPosition());
        float followDst = body.behaviorConfigOrDefaults().followDistance;
        cmd.wantCombat = false;

        if (myDist > followDst) {
            cmd.movementType = MovementType.WALK;
            Vector3 targetPos = target.getGlobalPosition();
            if (ctrl.shouldUpdateNav(targetPos)) {
                body.getNavAgent().setTargetPosition(targetPos);
                ctrl.recordNavTarget(targetPos);
            }
            if (!body.getNavAgent().isNavigationFinished()) {
                Vector3 dir = body.getNavAgent()
                        .getNextPathPosition()
                        .minus(body.getGlobalPosition())
                        .normalized();
                cmd.movementDirection.setX(dir.getX());
                cmd.movementDirection.setZ(dir.getZ());
            }
        }
        // Within followDistance → stand still (UserCommand default is IDLE / zero direction).

        return this;
    }
}
