package com.openworld.ai.character;

import com.openworld.ai.AIController;
import com.openworld.ai.AIState;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.MovementType;
import godot.core.Vector3;

/**
 * The APPROACH a dispatched unit runs toward a player (game.EnforcementDispatch; PLAN.md W5/W6): sprint in, weapon
 * drawn and aimed inside 25 m, straight when the dispatcher says the line is clear, through a building's door first
 * when the player is indoors ({@link AIController#pursuitVia}). The dispatcher hands a hostile unit to the combat FSM
 * once it is close. Its other uses: walking away when stood down ({@code pursuitAway}) and an abduction's guards
 * standing over a captive ({@code pursuitStand}). It was named for the walk-up arrest, which is gone (user
 * 2026-10-07: police hunt the player down; a wanted player who goes down is arrested by RecoveryRules).
 *
 * <p>The target lives on the {@link AIController} ({@link AIController#getPursuit()}), the stateless-singleton rule.
 * No pursuit, or a dead one -> back to Patrol. Steering is {@link ScriptedMoveState}'s (the NavAgent only while it
 * genuinely leads somewhere).
 */
public class ArrestState implements AIState {

    /** Within this of its approach slot a body closes on the pursuit itself. */
    static final double SLOT_REACHED = 1.5;

    public static final ArrestState INSTANCE = new ArrestState();
    private ArrestState() {}

    /** Sprint until this close, then walk the last metres (the arrest reach is the dispatcher's, ~2 m). */
    private static final float WALK_INSIDE = 6.0f;
    /** Stop pushing inside this: standing on the player's feet makes nobody arrested faster. */
    private static final float HOLD_INSIDE = 1.4f;
    /** Draw and aim inside this. */
    private static final float AIM_INSIDE = 25.0f;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        body.clearTarget();
        ctrl.clearNavTarget();
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        Character p = ctrl.getPursuit();
        if (p == null || !p.isAlive()) return PatrolState.INSTANCE;
        if (ctrl.pursuitSearch && ctrl.pursuitPoint != null && !ctrl.pursuitAway) {
            // SEARCHING: the pursuit is lost. To this body's own search point and no further -- a FIXED goal, so the
            // navigation path is asked for once a point, not re-planned at a moving player every tick
            Vector3 sg = ctrl.pursuitPoint;
            if (body.getNavAgent() != null && ctrl.shouldUpdateNav(sg)) {
                body.getNavAgent().setTargetPosition(sg);
                ctrl.recordNavTarget(new Vector3(sg));
            }
            Vector3 ds = sg.minus(body.getGlobalPosition());
            ds.setY(0f);
            if (ds.length() <= SLOT_REACHED) { cmd.movementType = MovementType.IDLE; return this; }
            cmd.movementType = ds.length() > WALK_INSIDE ? MovementType.SPRINT : MovementType.WALK;
            Vector3 sdir = ctrl.pursuitDirect ? ds.normalized() : ScriptedMoveState.steerDirection(body, sg);
            if (sdir != null) {
                cmd.movementDirection.setX(sdir.getX());
                cmd.movementDirection.setZ(sdir.getZ());
            }
            return this;
        }
        Vector3 at = p.getGlobalPosition();
        // this body's own approach slot round the pursuit (the dispatcher's), until it is there
        Vector3 goal = at;
        Vector3 off = ctrl.pursuitOffset;
        if (off != null && off.lengthSquared() > 0.01 && ctrl.pursuitVia.isEmpty() && !ctrl.pursuitAway) {
            Vector3 g = at.plus(off);
            Vector3 dg = g.minus(body.getGlobalPosition());
            dg.setY(0f);
            if (dg.length() > SLOT_REACHED) goal = g;
        }
        if (body.getNavAgent() != null && ctrl.shouldUpdateNav(goal)) {
            body.getNavAgent().setTargetPosition(goal);
            ctrl.recordNavTarget(new Vector3(goal));
        }
        Vector3 d = at.minus(body.getGlobalPosition());
        d.setY(0f);
        float dist = (float) d.length();
        if (ctrl.pursuitAway) {          // stood down: walk away from the player, straight
            cmd.movementType = MovementType.WALK;
            if (dist > 0.001f) {
                cmd.movementDirection.setX(-d.getX() / dist);
                cmd.movementDirection.setZ(-d.getZ() / dist);
            }
            return this;
        }
        if (dist <= AIM_INSIDE) {
            cmd.wantCombat = true;
            Vector3 chest = at.plus(new Vector3(0, 1.2, 0));
            cmd.aimTargetPosition = chest;
            body.aimAtPosition(chest, delta);
        }
        if (dist <= HOLD_INSIDE || ctrl.pursuitStand) {
            cmd.movementType = MovementType.IDLE;
            return this;
        }
        // BREACH (PLAN.md W6): through a building's door first -- straight to each waypoint, popped within a metre
        while (!ctrl.pursuitVia.isEmpty()) {
            Vector3 w = ctrl.pursuitVia.get(0);
            Vector3 dw = w.minus(body.getGlobalPosition());
            dw.setY(0f);
            if (dw.length() < 1.0) { ctrl.pursuitVia.remove(0); continue; }
            cmd.movementType = MovementType.SPRINT;
            Vector3 n = dw.normalized();
            cmd.movementDirection.setX(n.getX());
            cmd.movementDirection.setZ(n.getZ());
            return this;
        }
        cmd.movementType = dist > WALK_INSIDE ? MovementType.SPRINT : MovementType.WALK;
        Vector3 dg = goal.minus(body.getGlobalPosition());
        dg.setY(0f);
        Vector3 dir = ctrl.pursuitDirect ? (dg.length() > 0.001 ? dg.normalized() : null)
                : ScriptedMoveState.steerDirection(body, goal);
        if (dir != null) {
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        }
        return this;
    }
}
