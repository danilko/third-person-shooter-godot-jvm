package com.openworld.debug;

import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.world.Lane;
import com.openworld.world.ZoneManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.core.Vector3;

/**
 * A traffic brain a headless probe can aim: the ordinary {@link VehicleAIController} (same pure
 * pursuit, same lane chaining at junctions) put on a lane BY NAME from GDScript, blind to other cars,
 * and able to ride a fixed distance to one side of the lane — which is how a probe drives beside a
 * kerb or a barrier on purpose. Used by {@code tools/godot/probe_road_launch.gd} (PLAN.md 0.1).
 *
 * <p>Set {@code cruise_speed}/{@code cruise_throttle}/{@code junction_throttle_scale} on it like any
 * traffic controller; a lane's own {@code speed_limit} still wins, so a probe that wants to drive faster
 * than the road clears {@link #ignoreSpeedLimit}.
 */
@Script(className = "LaneDriveProbeController")
public class LaneDriveProbeController extends VehicleAIController {

    /** Metres to the RIGHT of the lane centre the car aims for (negative = left). */
    @Export public float lateralOffset = 0f;

    /** Drive at {@code cruiseSpeed} whatever the lane's own speed limit says. */
    @Export public boolean ignoreSpeedLimit = true;

    /** Put the car on the lane named {@code name}; false when no such lane is registered (not streamed). */
    @Register
    public boolean driveLane(String name) {
        ZoneManager zm = ZoneManager.get();
        Lane lane = zm != null ? zm.routeByName(name) : null;
        if (lane == null) return false;
        setRoute(lane);
        return true;
    }

    /** Name of the lane the car is on now, or "" (it changes at every junction). */
    @Register
    public String currentLaneName() {
        return getRoute() instanceof godot.api.Node n ? n.getName().toString() : "";
    }

    @Override
    public boolean isPathBlocked() { return false; }

    @Override
    public boolean shouldYield() { return false; }

    @Override
    public float effectiveCruiseSpeed() {
        return ignoreSpeedLimit ? cruiseSpeed : super.effectiveCruiseSpeed();
    }

    @Override
    public Vector3 lookaheadPoint() {
        Vector3 p = super.lookaheadPoint();
        if (p == null || lateralOffset == 0f) return p;
        Vector3 q = curvaturePoint();
        if (q == null) return p;
        Vector3 dir = new Vector3(q.getX() - p.getX(), 0.0, q.getZ() - p.getZ());
        if (dir.length() < 1e-3) return p;
        dir = dir.normalized();
        // Right of a heading (dx, dz) on the XZ plane, with +Y up, is (-dz, dx).
        Vector3 right = new Vector3(-dir.getZ(), 0.0, dir.getX());
        return p.plus(right.times(lateralOffset));
    }
}
