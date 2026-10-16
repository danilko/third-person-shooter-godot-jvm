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
    /** Within this plan distance a reloading unit strikes instead (PLAN.md 1g b). */
    private static final float MELEE_FALLBACK_REACH = 1.8f;
    /** A shot held because a body it may not shoot is in the line is tried again this soon (s), from a new strafe. */
    private static final double HOLD_FIRE_RETRY = 0.25;
    private static final double MELEE_FALLBACK_SECONDS = 2.0;
    /** Within this of its hold point a body is AT it; beyond {@link #HOLD_SPRINT} it runs there (PLAN.md 2.2). */
    private static final double HOLD_ARRIVED = 1.0, HOLD_SPRINT = 6.0;

    private static double flat(Vector3 a, Vector3 b) {
        double x = a.getX() - b.getX(), z = a.getZ() - b.getZ();
        return Math.sqrt(x * x + z * z);
    }

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
            // Confirmed sighting → rally squad-mates onto this target so they engage without waiting
            // for their own scan (PLAN.md E3). No-op for a solo AI.
            body.broadcastToSquad(body.getTarget(), targetPos);
        } else {
            ctrl.advanceLostTargetTimer(delta);
            if (!ctrl.hasLastKnownPosition() || ctrl.isSuppressExpired()) {
                // Lost the shot for good (no last-known, or suppression window elapsed). A breacher
                // pursues toward the target — ChaseState paths around the wall / through the doorway
                // (using the doorway NavigationLink) and re-enters AttackState once it regains a line,
                // so it follows you inside instead of camping. A hold-and-shoot AI sweeps the last spot.
                return (body.behaviorConfigOrDefaults().breachWhenBlocked && ctrl.hasLastKnownPosition())
                        ? ChaseState.INSTANCE
                        : SearchState.INSTANCE;
            }
        }

        // ── Still-phase tick (stop-to-shoot) ─────────────────────────────────
        ctrl.tickStillTimer(delta);

        // ── Pitch to target (needed by both stance and movement decisions) ─────
        Vector3 eyePos = myPos.plus(new Vector3(0, AICharacter.EYE_HEIGHT, 0));
        float targetY  = (float) targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT;
        float dy       = targetY - (float) eyePos.getY();
        float pitchDeg = (hDist > 0.01f) ? (float) Math.toDegrees(Math.atan2(dy, hDist)) : 0f;
        boolean pitchOut = pitchDeg > body.behaviorConfigOrDefaults().aimPitchMax
                        || pitchDeg < body.behaviorConfigOrDefaults().aimPitchMin;

        // ── Combat stance (debounced — minimum 2 s per stance) ───────────────
        // Only evaluate when the hold timer has expired to prevent per-frame
        // oscillation when hasLoS or pitchOut flickers near the threshold.
        ctrl.tickStanceHoldTimer(delta);
        boolean holding = body.holdPoint != null && !isMelee;
        if (holding && body.holdCrouch) {
            // at a low cover: down while it reloads or has no line, up to shoot (PLAN.md 2.2)
            boolean atCover = flat(myPos, body.holdPoint) <= HOLD_ARRIVED;
            boolean reloading = body.weaponController != null && body.weaponController.isWeaponReloading();
            StanceName target = atCover && (reloading || !hasLoS) ? StanceName.CROUCH : StanceName.UPRIGHT;
            if (target != ctrl.getIntendedAttackStance() && ctrl.canChangeStance()) {
                ctrl.setIntendedAttackStance(target);
                ctrl.startStanceHoldTimer(0.8);
                body.forceSetStance(target);
            }
        } else if (body.behaviorConfigOrDefaults().useCombatCrouch && ctrl.canChangeStance()) {
            boolean wantCrouch = hasLoS && !pitchOut && ctrl.isReactionReady()
                    && (!body.behaviorConfigOrDefaults().crouchOnSuppression || ctrl.isUnderAttack());
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
        if (holding) {
            // it fights FROM its point (a cover marker, a guard's post): there first, then it stands and shoots
            double off = flat(myPos, body.holdPoint);
            if (off <= HOLD_ARRIVED) {
                cmd.movementType = MovementType.IDLE;
            } else {
                // straight there when the way is clear (a cover point is a few metres off, in the open); the agent
                // only round a wall -- on a coarse navmesh its next point flips behind the body (probe_encounter)
                Vector3 step = body.holdPoint.minus(myPos);
                step.setY(0f);
                if (!ChaseState.walkableLine(body, body.holdPoint)) {
                    if (body.getNavAgent().getTargetPosition().distanceTo(body.holdPoint) > 0.5)
                        body.getNavAgent().setTargetPosition(body.holdPoint);
                    Vector3 nav = body.getNavAgent().getNextPathPosition().minus(myPos);
                    nav.setY(0f);
                    if (nav.length() >= 0.5f) step = nav;
                }
                Vector3 dir = step.length() > 0.001f ? step.normalized() : Vector3.Companion.getZERO();
                cmd.movementType = off > HOLD_SPRINT ? MovementType.SPRINT : MovementType.WALK;
                cmd.movementDirection.setX(dir.getX());
                cmd.movementDirection.setZ(dir.getZ());
            }
        } else if (ctrl.isStillPhase()) {
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
        // An AI does not stand reloading with the target in arm's reach: it strikes with its melee weapon or fists
        // instead (PLAN.md 1g b), then goes back to the gun and reloads. Out of ammo altogether it already fights with
        // the fists (selectBestWeapon falls back to slot 0).
        if (body.weaponController != null
                && body.weaponController.isWeaponReloading() && hDist < MELEE_FALLBACK_REACH
                && !isMelee) {
            body.startMeleeFallback(MELEE_FALLBACK_SECONDS);
        }
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
        if (ctrl.isAttackReady() && !ctrl.isStillPhase() && !body.attackHeld) {
            double fireRate = (body.weaponController != null
                    && body.weaponController.getCurrentWeaponItem() != null)
                    ? body.weaponController.getCurrentWeaponItem().getFireRate() : 0.0;
            ctrl.resetAttackTimer(fireRate > 0.0 ? 1.0 / fireRate : 1.5);

            Vector3 newTarget = hasLoS
                    ? body.computeAimTarget(GD.randf() < body.computeEffectiveHitChance(), hDist)
                    : ctrl.computeSuppressTarget(hDist);
            if (newTarget == null) return SearchState.INSTANCE;
            // somebody it may not shoot stands in the line: hold this shot, try again shortly from a new spot
            if (body.bystanderInLine(newTarget)) {
                if (AICharacter.holdFireOnBystanders) {
                    body.shotsHeld++;
                    ctrl.resetAttackTimer(HOLD_FIRE_RETRY);
                    ctrl.refreshStrafe();
                    return this;
                }
                body.shotsThrough++;
            }

            ctrl.setCurrentAimTarget(newTarget);
            body.aimAtPosition(newTarget, delta);
            body.snapAimRay(newTarget);
            cmd.aimTargetPosition = newTarget;
            // Movement is fully controlled by the movement block above.
            // startStillPhase is a no-op when shootStillDuration == 0.
            ctrl.startStillPhase(body.behaviorConfigOrDefaults().shootStillDuration);
            cmd.fire = true;
            body.shotsFired++;
        }

        return this;
    }
}
