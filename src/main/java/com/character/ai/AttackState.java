package com.character.ai;

import com.character.AICharacter;
import com.character.CharacterInput;
import com.character.MovementType;
import godot.api.Node3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * CS 1.6-style attack: AI strafes laterally, waits for a reaction delay,
 * then fires with per-shot accuracy controlled by {@link AICharacter#hitChance}.
 *
 * When LoS is lost the AI fires suppression shots at the last known target
 * position for up to {@link AICharacter#suppressionDuration} seconds before
 * transitioning to SearchState.
 */
public class AttackState implements AIState {

    public static final AttackState INSTANCE = new AttackState();

    private AttackState() {}

    @Override
    public void enter(AICharacter c) {
        c.resetAttackTimer();
        c.resetReactionTimer();
        c.resetLostTargetTimer();
        c.setCurrentAimTarget(null);
    }

    @Override
    public void exit(AICharacter c) {
        c.clearCameraAimTarget();
    }

    @Override
    public AIState update(AICharacter c, CharacterInput input, double delta) {
        if (c.getTarget() == null) return PatrolState.INSTANCE;

        Vector3 targetPos = c.getTarget().getGlobalPosition();
        Vector3 myPos     = c.getGlobalPosition();
        float dx    = (float) (targetPos.getX() - myPos.getX());
        float dz    = (float) (targetPos.getZ() - myPos.getZ());
        float hDist = (float) Math.sqrt(dx * dx + dz * dz);
        float dist  = (float) myPos.distanceTo(targetPos);

        if (dist > c.attackRange) return ChaseState.INSTANCE;

        input.wantCombat = true;
        c.advanceReactionTimer(delta);

        boolean hasLoS = c.hasLineOfSight();
        if (hasLoS) {
            c.setLastKnownTargetPosition(new Vector3(targetPos));
            c.resetLostTargetTimer();
        } else {
            c.advanceLostTargetTimer(delta);
            if (!c.hasLastKnownPosition() || c.isSuppressExpired()) return SearchState.INSTANCE;
        }

        // ── Movement: retreat on extreme pitch, strafe otherwise ────────────────
        Vector3 eyePos = myPos.plus(new Vector3(0, AICharacter.EYE_HEIGHT, 0));
        float targetY  = (float) targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT;
        float dy       = targetY - (float) eyePos.getY();
        float pitchDeg = (hDist > 0.01f) ? (float) Math.toDegrees(Math.atan2(dy, hDist)) : 0f;
        boolean pitchOutOfRange = pitchDeg > c.aimPitchMax || pitchDeg < c.aimPitchMin;

        if (pitchOutOfRange && hDist > 0.01f) {
            input.movementDirection.setX(-dx / hDist);
            input.movementDirection.setZ(-dz / hDist);
            input.movementType = MovementType.WALK;
        } else {
            if (c.needsStrafeUpdate()) c.refreshStrafe();
            c.tickStrafeTimer(delta);
            input.movementDirection.setX(c.getStrafeX());
            input.movementDirection.setZ(c.getStrafeZ());
            input.movementType = MovementType.WALK;
        }

        // ── Initialise aim target ────────────────────────────────────────────────
        if (c.getCurrentAimTarget() == null) {
            Vector3 initialTarget = hasLoS
                    ? ((Node3D) c.getTarget().getNode(
                            "MeshRoot/Model/Godot_Chan_Stealth/Skeleton3D/PhysicalBoneSimulator3D/Physical Bone neck_01"))
                            .getGlobalPosition()
                    : c.getLastKnownTargetPosition();
            c.setCurrentAimTarget(initialTarget);
        }
        c.aimAtPosition(c.getCurrentAimTarget(), delta);
        input.aimTargetPosition = c.getCurrentAimTarget();

        // ── Weapon selection ─────────────────────────────────────────────────────
        int bestWeapon = c.selectBestWeapon();
        if (bestWeapon < 0) return RefillAmmoState.INSTANCE;
        if (c.weaponController != null && bestWeapon != c.weaponController.getWeapon()) {
            if (!c.weaponController.isWeaponTransitioning()) input.desiredWeapon = bestWeapon;
            return this;
        }

        if (!c.isReactionReady()) return this;

        // ── Fire on cooldown ─────────────────────────────────────────────────────
        c.advanceAttackTimer(-delta);
        if (c.isAttackReady()) {
            double fireRate = (c.weaponController != null
                    && c.weaponController.getCurrentWeaponStats() != null)
                    ? c.weaponController.getCurrentWeaponStats().getFireRate()
                    : 0.0;
            c.resetAttackTimer(fireRate > 0.0 ? 1.0 / fireRate : 1.5);

            Vector3 newTarget;
            if (hasLoS) {
                newTarget = c.computeAimTarget(GD.randf() < c.hitChance, hDist);
            } else {
                newTarget = c.computeSuppressTarget(hDist);
                if (newTarget == null) return SearchState.INSTANCE;
            }

            c.setCurrentAimTarget(newTarget);
            c.aimAtPosition(newTarget, delta);
            c.snapAimRay(newTarget);
            input.aimTargetPosition = newTarget;
            input.fire = true;
        }

        return this;
    }
}
