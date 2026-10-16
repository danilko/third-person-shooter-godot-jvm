package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.movement.character.MovementType;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import com.openworld.ai.AIState;

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

        // Squad-mate spotted a target this AI can't see yet (PLAN.md E3) — canSeeTarget's scan adopts
        // the shared target, so close in on it rather than keep patrolling.
        if (body.getTarget() != null) {
            cmd.wantCombat = true;
            ctrl.setLastKnownTargetPosition(body.getTarget().getGlobalPosition());
            return ChaseState.INSTANCE;
        }

        // Heard hostile gunfire / an explosion / a crash nearby (PLAN.md E2) → investigate the source.
        Vector3 alarm = body.hearAlarm();
        if (alarm != null) {
            ctrl.setLastKnownTargetPosition(alarm);
            return SearchState.INSTANCE;
        }

        if (ctrl.isUnderAttack() && ctrl.hasLastKnownPosition()) {
            // Flee instead of search when configured and out of ammo.
            if (body.behaviorConfigOrDefaults().useFleeOnAttack && !body.hasAnyAmmo()) return FleeState.INSTANCE;
            return SearchState.INSTANCE;
        }

        cmd.wantCombat   = false;
        cmd.movementType = MovementType.WALK;

        // a guard's post (PLAN.md 2.2): stand ON it, facing out. Never by the nav agent once there -- inside a building
        // with no navmesh the agent's target snaps to the nearest navmesh point OUTSIDE, and the guard walked off 15 m
        // (probe_site_guards); back to it straight when the way is clear
        if (body.standsAtPost && body.holdPoint != null) {
            Vector3 off = body.holdPoint.minus(body.getGlobalPosition());
            off.setY(0f);
            if (off.length() < 0.8) {
                cmd.movementType = MovementType.IDLE;
                if (body.postFacePoint != null) {
                    body.aimAtPosition(body.postFacePoint, delta);
                    cmd.aimTargetPosition = body.postFacePoint;
                }
                return this;
            }
            Vector3 dir = off.normalized();
            if (!ChaseState.walkableLine(body, body.holdPoint)) {
                body.getNavAgent().setTargetPosition(body.holdPoint);
                Vector3 nav = body.getNavAgent().getNextPathPosition().minus(body.getGlobalPosition());
                nav.setY(0f);
                if (nav.length() >= 0.5f) dir = nav.normalized();
            }
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
            return this;
        }

        if (!body.getNavAgent().isNavigationFinished()) {
            Vector3 dir = body.getNavAgent()
                              .getNextPathPosition()
                              .minus(body.getGlobalPosition())
                              .normalized();
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        } else {
            body.setNextPatrolTarget();
            // a post (a guard, an encounter member standing): look out the way its marker faces (PLAN.md 2.2)
            if (body.postFacePoint != null && (body.patrolRoute == null || body.patrolRoute.isEmpty())) {
                body.aimAtPosition(body.postFacePoint, delta);
                cmd.aimTargetPosition = body.postFacePoint;
            }
        }

        return this;
    }
}
