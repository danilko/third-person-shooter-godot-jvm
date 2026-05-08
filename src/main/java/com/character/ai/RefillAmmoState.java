package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;
import com.character.MovementType;
import godot.core.Vector3;

/**
 * AI sprints to the nearest ammo refill station.
 * Fills all weapons on arrival, then returns to {@link PatrolState}.
 * Aborts immediately if ammo becomes available (e.g., picked up mid-path).
 */
public class RefillAmmoState implements AIState {

    public static final RefillAmmoState INSTANCE = new RefillAmmoState();

    private RefillAmmoState() {}

    @Override
    public void enter(AICharacter c) {
        if (c.ammoRefill != null)
            c.getNavAgent().setTargetPosition(c.ammoRefill.getGlobalPosition());
    }

    @Override
    public void exit(AICharacter c) {}

    @Override
    public AIState update(AICharacter c, CharacterInput input, double delta) {
        if (c.ammoRefill == null || c.hasAnyAmmo()) return PatrolState.INSTANCE;

        if (c.isAtAmmoRefill()) {
            c.weaponController.fillWeaponAmmo();
            return PatrolState.INSTANCE;
        }

        input.wantCombat = false;
        input.movementType = MovementType.SPRINT;

        Vector3 dir = c.getNavAgent()
                       .getNextPathPosition()
                       .minus(c.getGlobalPosition())
                       .normalized();
        input.movementDirection.setX(dir.getX());
        input.movementDirection.setZ(dir.getZ());

        return this;
    }
}
