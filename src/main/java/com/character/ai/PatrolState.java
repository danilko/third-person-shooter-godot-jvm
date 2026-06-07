package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.MovementType;
import com.character.UserCommand;
import godot.core.Vector3;

public class PatrolState implements AIState {

    public static final PatrolState INSTANCE = new PatrolState();
    private PatrolState() {}

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        body.clearTarget();
        ctrl.clearLastKnownPosition();
        body.setNextPatrolTarget();
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        // Escort target assigned → bodyguard mode takes priority over patrol.
        if (body.escortTarget != null && body.escortTarget.isAlive()) return EscortState.INSTANCE;

        int bestWeapon = body.selectBestWeapon();
        if (bestWeapon >= 0 && body.weaponController != null
                && bestWeapon != body.weaponController.getWeapon()
                && !body.weaponController.isWeaponTransitioning()) {
            cmd.desiredWeapon = bestWeapon;
        }

        if (body.canSeeTarget(delta)) {
            cmd.wantCombat = true;
            float dist = (float) body.getGlobalPosition()
                                     .distanceTo(body.getTarget().getGlobalPosition());
            if (dist <= body.getEffectiveAttackRange() && body.hasAnyAmmo()) return AttackState.INSTANCE;
            return ChaseState.INSTANCE;
        }

        if (ctrl.isUnderAttack() && ctrl.hasLastKnownPosition()) {
            // Flee instead of search when configured and out of ammo.
            if (body.getBehaviorConfig().useFleeOnAttack && !body.hasAnyAmmo()) return FleeState.INSTANCE;
            return SearchState.INSTANCE;
        }

        cmd.wantCombat   = false;
        cmd.movementType = MovementType.WALK;

        if (!body.getNavAgent().isNavigationFinished()) {
            Vector3 dir = body.getNavAgent()
                              .getNextPathPosition()
                              .minus(body.getGlobalPosition())
                              .normalized();
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        } else {
            body.setNextPatrolTarget();
        }

        return this;
    }
}
