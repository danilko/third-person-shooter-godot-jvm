package com.openworld.carrier.boat;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleConfig;
import com.openworld.world.WaterVolume;
import godot.annotation.RegisterClass;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Watercraft carrier stub (drivable prototype — placeholder hull, tuning later).
 *
 * Overrides {@link #applyLocomotion} entirely (no wheels): four corner buoyancy probes
 * spring the hull to the water line of the overlapping {@link WaterVolume} (found by a
 * throttled group scan — volumes are few), prop thrust along −Z and rudder yaw torque
 * apply only while afloat, and the shared stability assists (upright + angular damp;
 * set {@code downforceCoefficient = 0} in the boat's config preset) keep it level.
 * Seats, boost, authority, destruction, and replication all inherit from {@link Vehicle}.
 */
@RegisterClass(className = "Boat")
public class Boat extends Vehicle {

    private static final double WATER_SCAN_INTERVAL = 0.5;
    private double waterScanTimer = 0.0;
    /** Surface Y of the water volume under the hull; NaN when not over water. */
    private double cachedSurfaceY = Double.NaN;

    @Override
    protected boolean requiresWheels() { return false; }

    @Override
    protected boolean applyLocomotion(VehicleConfig cfg, double delta) {
        updateBoost(cfg, delta);
        refreshWaterSurface(delta);

        float speed = (float) getLinearVelocity().length();
        boolean afloat = false;

        if (!Double.isNaN(cachedSurfaceY)) {
            Vector3 up = Vector3.Companion.getUP();
            Vector3 origin = getGlobalPosition();
            Vector3 linVel = getLinearVelocity();
            Vector3 angVel = getAngularVelocity();
            float[][] corners = {
                    { cfg.hullHalfWidth, -cfg.hullHalfLength}, {-cfg.hullHalfWidth, -cfg.hullHalfLength},
                    { cfg.hullHalfWidth,  cfg.hullHalfLength}, {-cfg.hullHalfWidth,  cfg.hullHalfLength}};
            for (float[] corner : corners) {
                Vector3 probe = toGlobal(new Vector3(corner[0], 0f, corner[1]));
                double depth = cachedSurfaceY - probe.getY();
                if (depth <= 0) continue;
                afloat = true;
                Vector3 r = probe.minus(origin);
                double probeVy = linVel.plus(angVel.cross(r)).getY();
                double force = cfg.buoyancyStrength * Math.min(depth, 1.5)
                        - cfg.buoyancyDamping * probeVy;
                applyForce(up.times(force), r);
            }
        }

        if (afloat) {
            Vector3 forward = getGlobalBasis().getZ().times(-1);
            if (cmd.motor != 0) {
                applyCentralForce(forward.times(
                        cfg.acceleration * cmd.motor * getBoostAccelScale()));
            }
            // Rudder authority grows with way-on (a stationary boat barely turns).
            float rudder = (float) GD.clamp(cmd.steering, -1.0, 1.0);
            if (rudder != 0f) {
                float way = (float) GD.clamp(speed / Math.max(1e-3f, cfg.maxSpeed) + 0.15, 0.0, 1.0);
                applyTorque(Vector3.Companion.getUP().times(rudder * cfg.rudderTorque * way));
            }
        }
        setLinearDamp(afloat ? cfg.waterDrag : 0.05f);

        setCenterOfMassMode(CenterOfMassMode.CUSTOM);
        setCenterOfMass(new Vector3(0f, -0.5f, 0f));
        applyStabilityAssists(cfg, afloat, speed);
        return afloat;
    }

    /** Throttled lookup of the WaterVolume whose box contains the hull's XZ position. */
    private void refreshWaterSurface(double delta) {
        waterScanTimer -= delta;
        if (waterScanTimer > 0.0) return;
        waterScanTimer = WATER_SCAN_INTERVAL;
        cachedSurfaceY = Double.NaN;
        if (getTree() == null) return;
        Vector3 pos = getGlobalPosition();
        for (Node node : getTree().getNodesInGroup(WaterVolume.WATER_GROUP)) {
            if (!(node instanceof WaterVolume water)) continue;
            double surfaceY = water.getSurfaceY();
            // Coarse containment: within the volume's footprint radius and below-ish the surface.
            // Fine for the stub — proper per-shape XZ tests come with real water bodies.
            if (pos.getY() - 5.0 > surfaceY) continue;
            cachedSurfaceY = Double.isNaN(cachedSurfaceY) ? surfaceY : Math.max(cachedSurfaceY, surfaceY);
        }
    }
}
