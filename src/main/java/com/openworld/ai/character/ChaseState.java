package com.openworld.ai.character;

import com.openworld.character.AICharacter;
import com.openworld.ai.AIController;
import com.openworld.movement.character.MovementType;
import com.openworld.control.UserCommand;
import godot.core.Vector3;
import com.openworld.ai.AIState;

public class ChaseState implements AIState {

    public static final ChaseState INSTANCE = new ChaseState();
    private ChaseState() {}

    /** Inside this distance (m), with the target in sight, the chase walks straight at it instead of the nav path. */
    static final float CLOSE_DIRECT = 8.0f;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        ctrl.resetLostTargetTimer();
        ctrl.clearNavTarget();  // force a fresh nav update on the first chase frame
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        body.refreshTarget(delta);
        if (body.getTarget() == null) {
            return PatrolState.INSTANCE;
        }

        float dist = (float) body.getGlobalPosition()
                                 .distanceTo(body.getTarget().getGlobalPosition());
        cmd.wantCombat = true;

        boolean hasLoS = body.hasLineOfSight(delta);

        if (dist <= body.getEffectiveAttackRange() && hasLoS) {
            if (!body.hasAnyAmmo()) return RefillAmmoState.INSTANCE;
            return AttackState.INSTANCE;
        }

        cmd.movementType = MovementType.SPRINT;

        if (hasLoS) {
            ctrl.resetLostTargetTimer();
            Vector3 targetPos = body.getTarget().getGlobalPosition();
            ctrl.setLastKnownTargetPosition(new Vector3(targetPos));
            // Only request a path recompute when the target has moved > 1.5 m — prevents
            // 60 navAgent path-recomputes/sec while chasing a moving player.
            if (ctrl.shouldUpdateNav(targetPos)) {
                // a body holding a point (cover, a post) goes back to it while it can see the target
                body.getNavAgent().setTargetPosition(body.holds() ? body.blackboard.holdPoint : targetPos);
                ctrl.recordNavTarget(targetPos);
            }
            Vector3 aimTarget = new Vector3(targetPos.getX(),
                    targetPos.getY() + AICharacter.TARGET_BODY_HEIGHT,
                    targetPos.getZ());
            body.aimAtPosition(aimTarget, delta);
            cmd.aimTargetPosition = aimTarget;
        } else {
            ctrl.advanceLostTargetTimer(delta);
            if (ctrl.isTargetLost()) return PatrolState.INSTANCE;
            if (ctrl.hasLastKnownPosition()) {
                Vector3 lastKnown = ctrl.getLastKnownTargetPosition();
                if (ctrl.shouldUpdateNav(lastKnown)) {
                    body.getNavAgent().setTargetPosition(body.leashed(lastKnown));
                    ctrl.recordNavTarget(lastKnown);
                }
            }
        }

        // Off a navmesh the agent hands back the body's own position (ScriptedMoveState.steerDirection's trap): two
        // baton officers 3.9 m from a still player stood there for 90 s. The agent is believed only while its next
        // point is a real step ahead; otherwise steer at the target (in sight) or its last known place.
        Vector3 goal = hasLoS ? body.getTarget().getGlobalPosition()
                : ctrl.hasLastKnownPosition() ? ctrl.getLastKnownTargetPosition() : body.getGlobalPosition();
        // a body holding a point (cover, a post, PLAN.md 2.2): with the target in sight it fights from the point
        // (back to it, then it waits there for the target to come into range); out of sight it hunts no further than
        // its leash, then stands at the edge watching
        if (body.holds()) {
            Vector3 to = hasLoS ? body.blackboard.holdPoint : body.leashed(goal);
            Vector3 off = to.minus(body.getGlobalPosition());
            off.setY(0f);
            if (off.length() < 1.0) {
                cmd.movementType = MovementType.IDLE;
                cmd.movementDirection.setX(0);
                cmd.movementDirection.setZ(0);
                return this;
            }
            goal = to;
        }
        Vector3 dir;
        if (body.holds() && walkableLine(body, goal)) {
            // back to its point (or the leash's edge) in the open: straight there
            dir = goal.minus(body.getGlobalPosition());
            dir.setY(0f);
            dir = dir.length() > 0.001f ? dir.normalized() : null;
        } else if (hasLoS && dist < CLOSE_DIRECT && !body.holds() && walkableLine(body, goal)) {
            // In sight and close: straight at it. The agent leads to the nearest NAVMESH point, which for a target
            // on a slab or a kerb island is metres off it -- baton officers circled 3.5 m from a still player while
            // their reach is 1.9 m (probe_enforcement, 2026-10-07).
            dir = goal.minus(body.getGlobalPosition());
            dir.setY(0f);
            dir = dir.length() > 0.001f ? dir.normalized() : null;
        } else {
            // the agent's next point, unless it is not a real step ahead (off a navmesh it hands back the body's own
            // position); a FINISHED agent still leads (HEAD's rule -- treating it as no guidance walked breaching
            // officers into a konbini wall right after they switched onto its interior navmesh)
            Vector3 step = body.getNavAgent().getNextPathPosition().minus(body.getGlobalPosition());
            step.setY(0f);
            if (step.length() >= 0.5f) dir = step.normalized();
            else {
                dir = goal.minus(body.getGlobalPosition());
                dir.setY(0f);
                dir = dir.length() > 0.001f ? dir.normalized() : null;
            }
        }
        if (dir == null) dir = Vector3.Companion.getZERO();
        cmd.movementDirection.setX(dir.getX());
        cmd.movementDirection.setZ(dir.getZ());
        return this;
    }

    /** A clear WORLD line at knee and chest height from the body to {@code goal}: sight alone is not a way (the
     *  officer saw the player through a konbini's glazing and walked into the wall; probe_breach, 2026-10-07). */
    static boolean walkableLine(AICharacter body, Vector3 goal) {
        if (body.getViewport() == null || body.getViewport().getWorld3d() == null) return true;
        var sp = body.getViewport().getWorld3d().getDirectSpaceState();
        Vector3 from = body.getGlobalPosition();
        for (double h : new double[] {0.5, 1.3}) {
            var q = godot.api.PhysicsRayQueryParameters3D.create(from.plus(new Vector3(0, h, 0)),
                    goal.plus(new Vector3(0, h, 0)), com.openworld.util.CollisionLayers.WORLD,
                    new godot.core.VariantArray<>(godot.core.RID.class));
            var hit = sp.intersectRay(q);
            if (hit != null && !hit.isEmpty()) return false;
        }
        return true;
    }
}
