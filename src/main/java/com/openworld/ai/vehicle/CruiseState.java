package com.openworld.ai.vehicle;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.control.UserCommand;
import godot.core.Vector3;

/**
 * Default ambient-traffic state (PLAN.md I3 / I3b): follow the assigned lane by <b>pure pursuit</b> over
 * its smoothed, lane-offset path.
 *
 * <p>Steering is emitted as a <b>target wheel angle</b> ({@code cmd.steerToTarget}) proportional to the
 * heading error toward the look-ahead point, so the wheel converges and holds it (no rate winding =
 * no lane-to-lane wobble). Throttle eases off by whichever is greater — current steer or the upcoming
 * lane bend — so the car slows <i>before</i> a corner.
 *
 * → {@link BrakeState} when blocked ahead / yielding at a junction. At a one-way lane's end the car
 * continues via the lane-graph or applies the lane's {@code endBehavior}.
 */
public class CruiseState implements VehicleAIState {

    public static final CruiseState INSTANCE = new CruiseState();
    private CruiseState() {}

    @Override
    public void enter(Vehicle body, VehicleAIController ctrl) {}

    @Override
    public void exit(Vehicle body, VehicleAIController ctrl) {}

    @Override
    public VehicleAIState update(Vehicle body, VehicleAIController ctrl, UserCommand cmd, double delta) {
        // Yield to whatever is directly ahead, or to a junction another vehicle is crossing (I3b).
        if (ctrl.isPathBlocked() || ctrl.shouldYield()) return BrakeState.INSTANCE;

        Vector3 pos = body.getGlobalPosition();

        // Already at a dead-end (no continuation) — hold stopped; WorldZoneManager despawns us.
        if (ctrl.isFinished()) { cmd.motor = 0f; cmd.steering = 0f; return this; }

        ctrl.updateProgress(pos);

        // Reached the end of a one-way lane: continue onto a connected lane (lane-graph / endBehavior);
        // if there is none this lane is a dead-end → stop (the zone then reclaims the car).
        if (ctrl.atRouteEnd() && !ctrl.advanceToNextRoute()) {
            cmd.motor = 0f; cmd.steering = 0f; return this;
        }

        Vector3 target = ctrl.lookaheadPoint();
        if (target == null) return this;
        Vector3 toTarget = target.minus(pos);
        if (toTarget.length() < 1e-3) return this;

        // Right axis = column 0 of the basis (local +X). steerDot = +sin(angle) when the target is to
        // our right. UserCommand.steering (player convention) is POSITIVE = turn LEFT, so negate. With
        // steerToTarget the value is the desired NORMALIZED wheel angle (not a rate), scaled by steerGain
        // and saturated — the wheel converges to it and holds.
        Vector3 right   = body.getGlobalTransform().getBasis().getColumn(0);
        Vector3 nearDir = toTarget.normalized();
        float   steerDot = (float) nearDir.dot(right);
        float   steer    = Math.max(-1f, Math.min(1f, -steerDot * ctrl.steerGain));

        // Anticipate the corner: probe the lane farther along; if it bends away from the heading to the
        // steer target, slow before reaching it. Lane-relative (independent of car facing / basis sign).
        float bend = 0f;
        Vector3 probe = ctrl.curvaturePoint();
        if (probe != null) {
            Vector3 farSeg = probe.minus(target);
            if (farSeg.length() > 1e-2)
                bend = Math.max(0f, Math.min(1f, 1f - (float) nearDir.dot(farSeg.normalized())));
        }

        float turnFactor = Math.max(Math.abs(steer), bend);
        cmd.steerToTarget = true;
        cmd.steering = steer;
        cmd.motor    = ctrl.cruiseThrottle * (1f - ctrl.turnSlowdown * turnFactor);
        return this;
    }
}
