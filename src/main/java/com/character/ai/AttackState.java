package com.character.ai;

import com.character.AICharacter;
import com.character.AIController;
import com.character.MovementType;
import com.character.StanceName;
import com.character.UserCommand;
import godot.core.Vector3;
import godot.global.GD;

public class AttackState implements AIState {

    public static final AttackState INSTANCE = new AttackState();
    private AttackState() {}

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetAttackTimer();
        ctrl.resetReactionTimer();
        ctrl.resetLostTargetTimer();
        ctrl.setCurrentAimTarget(null);
        ctrl.setIntendedAttackStance(StanceName.UPRIGHT);
        ctrl.startStanceHoldTimer(0);  // clear any leftover hold from a previous engagement
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {
        body.clearCameraAimTarget();
        ctrl.setIntendedAttackStance(StanceName.UPRIGHT);
        body.forceSetStance(StanceName.UPRIGHT);
    }

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        // Re-evaluate nearest live hostile each frame so a closer threat that
        // appears mid-combat (e.g. a player walking in) is not ignored.
        body.refreshTarget(delta);
        if (body.getTarget() == null) {
            return PatrolState.INSTANCE;
        }

        Vector3 targetPos = body.getTarget().getGlobalPosition();
        Vector3 myPos     = body.getGlobalPosition();
        float dx    = (float) (targetPos.getX() - myPos.getX());
        float dz    = (float) (targetPos.getZ() - myPos.getZ());
        float hDist = (float) Math.sqrt(dx * dx + dz * dz);
        float dist  = (float) myPos.distanceTo(targetPos);

        if (dist > body.attackRange) return ChaseState.INSTANCE;

        cmd.wantCombat = true;
        ctrl.advanceReactionTimer(delta);

        boolean hasLoS = body.hasLineOfSight(delta);
        if (hasLoS) {
            ctrl.setLastKnownTargetPosition(new Vector3(targetPos));
            ctrl.resetLostTargetTimer();
        } else {
            ctrl.advanceLostTargetTimer(delta);
            if (!ctrl.hasLastKnownPosition() || ctrl.isSuppressExpired()) return SearchState.INSTANCE;
        }

        // ── Still-phase tick (stop-to-shoot) ─────────────────────────────────
        ctrl.tickStillTimer(delta);

        // ── Pitch to target (needed by both stance and movement decisions) ─────
        Vector3 eyePos = myPos.plus(new Vector3(0, AICharacter.EYE_HEIGHT, 0));
        float targetY  = (float) targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT;
        float dy       = targetY - (float) eyePos.getY();
        float pitchDeg = (hDist > 0.01f) ? (float) Math.toDegrees(Math.atan2(dy, hDist)) : 0f;
        boolean pitchOut = pitchDeg > body.aimPitchMax || pitchDeg < body.aimPitchMin;

        // ── Combat stance (debounced — minimum 2 s per stance) ───────────────
        // Only evaluate when the hold timer has expired to prevent per-frame
        // oscillation when hasLoS or pitchOut flickers near the threshold.
        ctrl.tickStanceHoldTimer(delta);
        if (body.useCombatCrouch && ctrl.canChangeStance()) {
            StanceName target = (hasLoS && !pitchOut && ctrl.isReactionReady())
                    ? StanceName.CROUCH
                    : StanceName.UPRIGHT;
            if (target != ctrl.getIntendedAttackStance()) {
                ctrl.setIntendedAttackStance(target);
                ctrl.startStanceHoldTimer(2.0);
                body.forceSetStance(target);
            }
        }

        // ── Movement ──────────────────────────────────────────────────────────
        // movementType is WALK in all branches; direction stays zero during still phase.
        cmd.movementType = MovementType.WALK;
        if (!ctrl.isStillPhase()) {
            if (pitchOut && hDist > 0.01f) {
                cmd.movementDirection.setX(-dx / hDist);
                cmd.movementDirection.setZ(-dz / hDist);
            } else {
                if (ctrl.needsStrafeUpdate()) ctrl.refreshStrafe();
                ctrl.tickStrafeTimer(delta);
                cmd.movementDirection.setX(ctrl.getStrafeX());
                cmd.movementDirection.setZ(ctrl.getStrafeZ());
            }
        }

        // ── Aim initialisation ────────────────────────────────────────────────
        if (ctrl.getCurrentAimTarget() == null) {
            Vector3 initial = hasLoS ? body.getAimBonePosition() : ctrl.getLastKnownTargetPosition();
            ctrl.setCurrentAimTarget(initial);
        }
        body.aimAtPosition(ctrl.getCurrentAimTarget(), delta);
        cmd.aimTargetPosition = ctrl.getCurrentAimTarget();

        // ── Weapon selection ──────────────────────────────────────────────────
        int bestWeapon = body.selectBestWeapon();
        if (bestWeapon < 0) return RefillAmmoState.INSTANCE;
        if (body.weaponController != null && bestWeapon != body.weaponController.getWeapon()) {
            if (!body.weaponController.isWeaponTransitioning()) cmd.desiredWeapon = bestWeapon;
            return this;
        }

        if (!ctrl.isReactionReady()) return this;

        // ── Fire on cooldown ──────────────────────────────────────────────────
        ctrl.advanceAttackTimer(-delta);
        if (ctrl.isAttackReady()) {
            double fireRate = (body.weaponController != null
                    && body.weaponController.getCurrentWeaponStats() != null)
                    ? body.weaponController.getCurrentWeaponStats().getFireRate() : 0.0;
            ctrl.resetAttackTimer(fireRate > 0.0 ? 1.0 / fireRate : 1.5);

            Vector3 newTarget = hasLoS
                    ? body.computeAimTarget(GD.randf() < body.computeEffectiveHitChance(), hDist)
                    : ctrl.computeSuppressTarget(hDist);
            if (newTarget == null) return SearchState.INSTANCE;

            ctrl.setCurrentAimTarget(newTarget);
            body.aimAtPosition(newTarget, delta);
            body.snapAimRay(newTarget);
            cmd.aimTargetPosition = newTarget;
            cmd.movementDirection.setX(0);
            cmd.movementDirection.setZ(0);
            ctrl.startStillPhase(body.shootStillDuration);
            cmd.fire = true;
        }

        return this;
    }
}
