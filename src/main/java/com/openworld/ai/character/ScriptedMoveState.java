package com.openworld.ai.character;

import com.openworld.ai.AIController;
import com.openworld.ai.AIState;
import com.openworld.character.AICharacter;
import com.openworld.control.UserCommand;
import com.openworld.movement.character.MovementType;
import godot.core.Vector3;

/**
 * "Go there and stand there" — the state a scripted order puts a named AI into
 * (PLAN.md Part F / F1, {@code MissionDirector.commandCharacter}).
 *
 * <p><b>An order is not a mood: nothing in the world cancels it.</b> Sight of an enemy, being shot,
 * hearing gunfire — none of them transition out, because the only caller is the director and the
 * director is the thing that knows when the beat is over ({@code MissionDirector.releaseCharacter},
 * or any other {@link com.openworld.game.mission.ScriptCommand} sent after it). The autonomous states
 * are the opposite by design: they react. Mixing the two would mean a cutscene walk that a passing
 * civilian could derail, and a mission that silently plays differently every run.
 *
 * <p>The destination lives on the {@link AIController} (states are stateless singletons — the
 * codebase rule), so re-entering the state with a new destination is one write and no allocation.
 */
public class ScriptedMoveState implements AIState {

    public static final ScriptedMoveState INSTANCE = new ScriptedMoveState();
    private ScriptedMoveState() {}

    /** Horizontal distance from the destination that counts as arrived. */
    private static final float ARRIVE_DIST = 1.5f;

    /** Shortest next-path step that counts as the NavAgent actually leading somewhere. */
    private static final float NAV_MIN_STEP = 0.5f;

    @Override
    public void enter(AICharacter body, AIController ctrl) {
        body.clearTarget();
        Vector3 dest = ctrl.getScriptedDestination();
        if (dest != null && body.getNavAgent() != null) body.getNavAgent().setTargetPosition(dest);
    }

    @Override
    public void exit(AICharacter body, AIController ctrl) {}

    @Override
    public AIState update(AICharacter body, AIController ctrl, UserCommand cmd, double delta) {
        Vector3 dest = ctrl.getScriptedDestination();
        // The order was cleared out from under us (director released the character) → back to normal life.
        if (dest == null) return PatrolState.INSTANCE;

        cmd.wantCombat   = false;
        cmd.movementType = MovementType.WALK;

        if (hasArrived(body, dest)) {
            ctrl.setScriptedArrived(true);
            return this;                       // stand at the spot until released
        }

        Vector3 dir = steerDirection(body, dest);
        if (dir != null) {
            cmd.movementDirection.setX(dir.getX());
            cmd.movementDirection.setZ(dir.getZ());
        }
        return this;
    }

    /**
     * Where to walk this frame: the NavAgent's next path point when it is genuinely giving one, the
     * destination itself otherwise. Null when there is nowhere to go.
     *
     * <p><b>A NavAgent OFF the navmesh is not silent — it lies.</b> With no navigation map under the
     * body it reports {@code isNavigationFinished() == false} forever and hands back the body's own
     * position (measured: the previous frame's, one tick stale). Trusting that produces a direction
     * pointing exactly BACKWARD along the body's own travel, which feeds itself: the AI accelerated to
     * full speed AWAY from its destination and kept going (measured on the bare probe stand — 20 m from
     * the origin to 110 m in 30 s). So the agent is believed only while its next point is a real step
     * ahead; a step shorter than {@link #NAV_MIN_STEP} means it has nothing to say and the destination
     * answers instead. Both worlds have navmeshes, so this is the off-navmesh case — a rooftop, a deck,
     * a mission beat authored anywhere the bake did not reach — and it is exactly where a scripted
     * order must not turn into a runaway.
     */
    private static Vector3 steerDirection(AICharacter body, Vector3 dest) {
        Vector3 pos = body.getGlobalPosition();
        Vector3 dir = null;
        if (body.getNavAgent() != null && !body.getNavAgent().isNavigationFinished()) {
            Vector3 step = body.getNavAgent().getNextPathPosition().minus(pos);
            step.setY(0f);
            if (step.length() >= NAV_MIN_STEP) dir = step;
        }
        if (dir == null) {
            dir = dest.minus(pos);
            dir.setY(0f);
        }
        return dir.length() > 0.001f ? dir.normalized() : null;
    }

    /**
     * Arrival is asked of the DESTINATION, not only of the NavAgent: an unreachable or off-navmesh
     * target leaves {@code isNavigationFinished()} true from the first frame, which would read as
     * "arrived" while the body is still metres away — and an arrival that is a lie is worse than a
     * walk that takes a moment, because the beat after it fires in the wrong place. A body with no
     * NavAgent at all still walks: the steering above falls back to the destination itself.
     */
    private static boolean hasArrived(AICharacter body, Vector3 dest) {
        Vector3 d = dest.minus(body.getGlobalPosition());
        d.setY(0f);
        return d.length() <= ARRIVE_DIST;
    }
}
