package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.MovementType;
import com.character.UserCommand;
import godot.core.Vector3;

public class RefillAmmoState implements AIState {

    public static final RefillAmmoState INSTANCE = new RefillAmmoState();
    private RefillAmmoState() {}

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        if (body.ammoRefill != null)
            body.getNavAgent().setTargetPosition(body.ammoRefill.getGlobalPosition());
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        if (body.ammoRefill == null || body.hasAnyAmmo()) return PatrolState.INSTANCE;

        if (body.isAtAmmoRefill()) {
            body.weaponController.fillWeaponAmmo();
            return PatrolState.INSTANCE;
        }

        cmd.wantCombat = false;
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
