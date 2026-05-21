package com.vehicle;

import com.character.Controller;
import com.character.UserCommand;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.NavigationAgent3D;
import godot.api.Node;
import godot.core.Vector3;

/**
 * AI controller for VehicleBody — navigates toward waypoints set at runtime.
 *
 * Design: stateless waypoint follower using NavigationAgent3D.
 * External systems (spawner, game objective) set the navigation target via
 * setNavigationTarget(Vector3) and the controller steers toward it.
 *
 * Steering: proportional — project the vector-to-next-point onto the vehicle's
 * right axis. Positive dot → target is to the right → steer right (positive).
 *
 * Future: replace with a multi-state FSM (patrol, chase, retreat) analogous
 * to the on-foot CharacterController / AIController hierarchy.
 */
@RegisterClass(className = "VehicleAIController")
public class VehicleAIController extends Controller {

    /** Throttle fraction applied when driving toward the target (0–1). */
    @RegisterProperty @Export public float cruiseThrottle = 0.6f;

    /** Distance from waypoint considered "arrived" — NavigationAgent3D stops. */
    @RegisterProperty @Export public float arrivalThreshold = 3.0f;

    private Vehicle        vehicleBody;
    private NavigationAgent3D navAgent;

    @RegisterFunction
    @Override
    public void _ready() {
        Node owner = getOwner();
        if (owner instanceof Vehicle v) {
            vehicleBody = v;
        }
        if (vehicleBody != null) {
            Node nav = vehicleBody.getNodeOrNull("NavigationAgent3D");
            if (nav instanceof NavigationAgent3D n) navAgent = n;
        }
    }

    /** Point the vehicle toward this world-space position. */
    public void setNavigationTarget(Vector3 target) {
        if (navAgent != null) navAgent.setTargetPosition(target);
    }

    @Override
    public UserCommand gatherInput(double delta) {
        UserCommand cmd = new UserCommand();

        if (vehicleBody == null || navAgent == null) return cmd;
        if (navAgent.isNavigationFinished()) return cmd;

        Vector3 nextPos = navAgent.getNextPathPosition();
        Vector3 toNext  = nextPos.minus(vehicleBody.getGlobalPosition());

        // Steering: dot of toNext direction against vehicle right axis.
        // Right axis = column 0 of the basis (local +X in Godot's convention).
        Vector3 right   = vehicleBody.getGlobalTransform().getBasis().getColumn(0);
        float steerDot  = (float) toNext.normalized().dot(right);

        cmd.motor = cruiseThrottle;
        cmd.steering = Math.max(-1f, Math.min(1f, steerDot));

        return cmd;
    }
}
