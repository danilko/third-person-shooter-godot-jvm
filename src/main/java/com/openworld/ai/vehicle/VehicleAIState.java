package com.openworld.ai.vehicle;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.control.UserCommand;

/**
 * One state in a {@link VehicleAIController}'s finite state machine (PLAN.md I3).
 *
 * Mirrors the on-foot {@link com.openworld.ai.AIState} pattern: states are
 * stateless singletons; all mutable data (route, route index, timers) lives on
 * the {@link VehicleAIController}. Returning a different VehicleAIState from
 * {@link #update} triggers a transition.
 *
 * The explicit (body, ctrl) split keeps each state's data sources unambiguous:
 *   body — hardware / sensing  (NavigationAgent3D, the forward ObstacleRay, transform)
 *   ctrl — memory / state      (route, current waypoint index, throttle)
 */
public interface VehicleAIState {

    /** Called once on entry. */
    void enter(Vehicle body, VehicleAIController ctrl);

    /** Called once on exit. */
    void exit(Vehicle body, VehicleAIController ctrl);

    /**
     * Produce a vehicle UserCommand (motor/steering/brake) for this tick.
     * Return {@code this} to stay, or another instance to transition.
     */
    VehicleAIState update(Vehicle body, VehicleAIController ctrl, UserCommand cmd, double delta);
}
