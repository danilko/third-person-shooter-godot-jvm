package com.character.ai;

import com.character.CharacterInput;
import com.character.Enemy;
import com.character.MovementType;
import godot.core.Vector3;

/**
 * Enemy sprints to the nearest ammo refill station.
 * Fills all weapons on arrival, then returns to {@link PatrolState}.
 * Aborts immediately if ammo becomes available (e.g., picked up mid-path).
 */
public class RefillAmmoState implements EnemyAIState {

    public static final RefillAmmoState INSTANCE = new RefillAmmoState();

    private RefillAmmoState() {}

    @Override
    public void enter(Enemy enemy) {
        if (enemy.ammoRefill != null) {
            enemy.getNavAgent().setTargetPosition(enemy.ammoRefill.getGlobalPosition());
        }
    }

    @Override
    public void exit(Enemy enemy) {}

    @Override
    public EnemyAIState update(Enemy enemy, CharacterInput input, double delta) {
        if (enemy.ammoRefill == null || enemy.hasAnyAmmo()) {
            return PatrolState.INSTANCE;
        }

        if (enemy.isAtAmmoRefill()) {
            enemy.weaponController.fillWeaponAmmo();
            return PatrolState.INSTANCE;
        }

        input.wantCombat = false;
        input.movementType = MovementType.SPRINT;

        Vector3 dir = enemy.getNavAgent()
                           .getNextPathPosition()
                           .minus(enemy.getGlobalPosition())
                           .normalized();
        input.movementDirection.setX(dir.getX());
        input.movementDirection.setZ(dir.getZ());

        return this;
    }
}
