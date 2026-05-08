package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;
import com.character.MovementType;
import godot.core.Vector3;

/**
 * AI character wanders within its patrol radius.
 * Transitions to {@link ChaseState} or {@link AttackState} when a hostile target is spotted.
 * Transitions to {@link SearchState} immediately when hit (even without visual contact).
 */
public class PatrolState implements AIState {

    public static final PatrolState INSTANCE = new PatrolState();

    private PatrolState() {}

    @Override
    public void enter(AICharacter c) {
        c.clearTarget();
        c.setNextPatrolTarget();
    }

    @Override
    public void exit(AICharacter c) {}

    @Override
    public AIState update(AICharacter c, CharacterInput input, double delta) {
        int bestWeapon = c.selectBestWeapon();
        if (bestWeapon >= 0 && c.weaponController != null
                && bestWeapon != c.weaponController.getWeapon()
                && !c.weaponController.isWeaponTransitioning()) {
            input.desiredWeapon = bestWeapon;
        }

        if (c.canSeeTarget()) {
            input.wantCombat = true;
            float dist = (float) c.getGlobalPosition()
                                   .distanceTo(c.getTarget().getGlobalPosition());
            if (dist <= c.attackRange && c.hasAnyAmmo()) return AttackState.INSTANCE;
            return ChaseState.INSTANCE;
        }

        if (c.isUnderAttack() && c.hasLastKnownPosition()) return SearchState.INSTANCE;

        input.wantCombat   = false;
        input.movementType = MovementType.WALK;

        if (!c.getNavAgent().isNavigationFinished()) {
            Vector3 dir = c.getNavAgent()
                           .getNextPathPosition()
                           .minus(c.getGlobalPosition())
                           .normalized();
            input.movementDirection.setX(dir.getX());
            input.movementDirection.setZ(dir.getZ());
        } else {
            c.setNextPatrolTarget();
        }

        return this;
    }
}
