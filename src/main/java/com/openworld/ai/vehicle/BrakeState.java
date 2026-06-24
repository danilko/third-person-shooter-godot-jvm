package com.openworld.ai.vehicle;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.control.UserCommand;

/**
 * Yield state (PLAN.md I3/I3b): cut throttle and brake while the path ahead is blocked (forward
 * obstacle ray tripped) OR while another vehicle is crossing a junction we're waiting to enter.
 * Keeps a stopped vehicle from creeping into the one in front of it / into cross traffic.
 *
 * → {@link CruiseState} once both the obstacle ray and the junction read clear again.
 */
public class BrakeState implements VehicleAIState {

    public static final BrakeState INSTANCE = new BrakeState();
    private BrakeState() {}

    @Override
    public void enter(Vehicle body, VehicleAIController ctrl) {}

    @Override
    public void exit(Vehicle body, VehicleAIController ctrl) {}

    @Override
    public VehicleAIState update(Vehicle body, VehicleAIController ctrl, UserCommand cmd, double delta) {
        if (!ctrl.isPathBlocked() && !ctrl.shouldYield()) return CruiseState.INSTANCE;

        cmd.motor    = 0f;
        cmd.brake    = true;
        cmd.steering = 0f;
        return this;
    }
}
