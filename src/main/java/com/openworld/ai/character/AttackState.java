package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.ai.AIState;
import com.openworld.character.Character;
import com.openworld.movement.character.MovementController;

public class AttackState implements AIState {

    public static final AttackState INSTANCE = new AttackState();
    private AttackState() {}

    /**
     * Melee range is only ~1-2 m, so the lateral strafe steps below would otherwise
     * carry the AI back out of range almost every frame (chase ↔ attack flicker, no
     * hits ever land). Breaking off to chase only once well outside the swing range
     * absorbs that jitter; closing back in (rather than strafing) keeps it inside.
     */
    private static final float MELEE_CHASE_HYSTERESIS = 1.5f;

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

        boolean isMelee = body.isMeleeEngagement();
        float attackRange = body.getEffectiveAttackRange();
        float chaseBreakRange = isMelee ? attackRange * MELEE_CHASE_HYSTERESIS : attackRange;
        if (dist > chaseBreakRange) return ChaseState.INSTANCE;

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
        boolean pitchOut = pitchDeg > body.getBehaviorConfig().aimPitchMax
                        || pitchDeg < body.getBehaviorConfig().aimPitchMin;

        // ── Combat stance (debounced — minimum 2 s per stance) ───────────────
        // Only evaluate when the hold timer has expired to prevent per-frame
        // oscillation when hasLoS or pitchOut flickers near the threshold.
        ctrl.tickStanceHoldTimer(delta);
        if (body.getBehaviorConfig().useCombatCrouch && ctrl.canChangeStance()) {
            boolean wantCrouch = hasLoS && !pitchOut && ctrl.isReactionReady()
                    && (!body.getBehaviorConfig().crouchOnSuppression || ctrl.isUnderAttack());
            StanceName target = wantCrouch ? StanceName.CROUCH : StanceName.UPRIGHT;
            if (target != ctrl.getIntendedAttackStance()) {
                ctrl.setIntendedAttackStance(target);
                ctrl.startStanceHoldTimer(2.0);
                body.forceSetStance(target);
            }
        }

        // ── Movement ──────────────────────────────────────────────────────────
        // Still phase: IDLE (speed = 0) so the AI fully stops; direction stays (0,0,0)
        // and the zero-direction emission in Character.applyInput clears MovementController.
        // Moving phase: WALK with a valid strafe/reposition/closing direction, or IDLE
        // to hold a melee swing position (lateral strafing has no place at arm's reach).
        boolean closeForMelee = isMelee && hDist > 0.01f && dist > attackRange * 0.85f;
        if (ctrl.isStillPhase()) {
            cmd.movementType = MovementType.IDLE;
        } else if (pitchOut && hDist > 0.01f) {
            cmd.movementType = MovementType.WALK;
            cmd.movementDirection.setX(-dx / hDist);
            cmd.movementDirection.setZ(-dz / hDist);
        } else if (closeForMelee) {
            // Walk straight at the target — at melee distances it's the lateral strafe
            // steps below that keep carrying the AI back out of its own swing range.
            cmd.movementType = MovementType.WALK;
            cmd.movementDirection.setX(dx / hDist);
            cmd.movementDirection.setZ(dz / hDist);
        } else if (isMelee) {
            // Close enough to swing — hold position and let the attacks land.
            cmd.movementType = MovementType.IDLE;
        } else {
            cmd.movementType = MovementType.WALK;
            if (ctrl.needsStrafeUpdate()) ctrl.refreshStrafe();
            ctrl.tickStrafeTimer(delta);
            cmd.movementDirection.setX(ctrl.getStrafeX());
            cmd.movementDirection.setZ(ctrl.getStrafeZ());
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
        // Timer only ticks outside the still phase so a sniper's stop-to-aim pause
        // (shootStillDuration > 0) cannot re-trigger a shot mid-pause.
        // Default shootStillDuration = 0 means the still phase is never entered:
        // the AI fires at full weapon rate while strafing (CS/GTA style).
        if (!ctrl.isStillPhase()) ctrl.advanceAttackTimer(-delta);
        if (ctrl.isAttackReady() && !ctrl.isStillPhase()) {
            double fireRate = (body.weaponController != null
                    && body.weaponController.getCurrentWeaponItem() != null)
                    ? body.weaponController.getCurrentWeaponItem().getFireRate() : 0.0;
            ctrl.resetAttackTimer(fireRate > 0.0 ? 1.0 / fireRate : 1.5);

            Vector3 newTarget = hasLoS
                    ? body.computeAimTarget(GD.randf() < body.computeEffectiveHitChance(), hDist)
                    : ctrl.computeSuppressTarget(hDist);
            if (newTarget == null) return SearchState.INSTANCE;

            ctrl.setCurrentAimTarget(newTarget);
            body.aimAtPosition(newTarget, delta);
            body.snapAimRay(newTarget);
            cmd.aimTargetPosition = newTarget;
            // Movement is fully controlled by the movement block above.
            // startStillPhase is a no-op when shootStillDuration == 0.
            ctrl.startStillPhase(body.getBehaviorConfig().shootStillDuration);
            cmd.fire = true;
        }

        return this;
    }
}
