package com.openworld.debug;

import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.CharacterInfo;
import com.openworld.world.LaneGraph;
import com.openworld.world.PathLaneRoute;
import com.openworld.world.WorldBaker;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.*;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.List;
import java.util.UUID;

/**
 * Headless regression smoke test for {@code PathLaneRoute}/{@code Lane}/{@code LaneGraph} (the
 * "intersection lane-graph -> native Path3D" work, road_blender_godot.md item 6 -- same idiom as
 * {@link DriveTestHost}). Bakes the `intersection_prototype.4way.lanekit.json` sidecar via
 * {@link WorldBaker}, loads the result, and drives one vehicle on a turn movement + one on a
 * through movement: confirms the arc-length sampling round-trips exactly, that {@link LaneGraph}
 * connects a coincident-start partner {@code PathLaneRoute} (proximity-derived, same as it would
 * across a hand-authored {@code VehicleRoute} network), and that the turn vehicle's heading
 * actually changes while the through vehicle's stays flat -- i.e. a car ends up going straight or
 * turning purely because of which {@code Lane} it's on, via the existing, unmodified
 * {@code VehicleAIController}/{@code LaneGraph} machinery. Run with:
 *
 *   godot --headless res://src/main/resources/com/openworld/debug/PathLaneRouteTest.tscn
 *
 * Grep for "PLRTEST SUMMARY" / "PLRTEST verdict" (PASS iff turn heading change > 20 deg and
 * straight < 10 deg, measured only while each controller is still actively driving -- see
 * SETTLE_SECONDS/isFinished() below for why).
 */
@RegisterClass(className = "PathLaneRouteTestHost")
public class PathLaneRouteTestHost extends Node3D {

    private static final String SRC = "res://src/main/resources/com/openworld/debug/EmptyBakeSource.tscn";
    private static final String OUT = "res://src/main/resources/com/openworld/debug/PathLaneRouteBaked.tscn";
    private static final String LANEKIT =
            "/data/danilko/git/third-person-shooter/assets/world_source/kit/intersection_prototype.4way.lanekit.json";
    // Both lanes are ~24m; at the default cruiseSpeed (~11 m/s) that's traversed in ~2.5s. Both
    // lanes are genuine dead ends in this isolated fixture (their exit ports aren't wired to
    // anything yet -- see road_blender_godot.md item 6), so heading change is measured only
    // WHILE the controller is still actively driving its assigned lane (!isFinished()) and past
    // the initial SETTLE_SECONDS spawn-alignment transient -- once a car finishes a dead-end lane
    // it just coasts under residual momentum with no steering input, which accumulates unrelated
    // heading drift that would otherwise swamp the signal this test actually cares about.
    private static final double RUN_SECONDS = 6.0;
    private static final double SETTLE_SECONDS = 1.0;

    private Vehicle turnVehicle, straightVehicle;
    private VehicleAIController turnCtrl, straightCtrl;
    private double lastYawTurn = Double.NaN, lastYawStraight = Double.NaN;
    private double accumTurn = 0, accumStraight = 0;
    private double timer = RUN_SECONDS;
    private boolean done = false;

    @RegisterFunction
    @Override
    public void _ready() {
        StaticBody3D ground = new StaticBody3D();
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D box = new BoxShape3D();
        box.setSize(new Vector3(2000f, 1f, 2000f));
        cs.setShape(box);
        ground.addChild(cs);
        ground.setPosition(new Vector3(0f, -0.5f, 0f));
        addChild(ground);

        WorldBaker.bake(this, SRC, OUT, "res://src/main/resources/com/openworld/world/kit/", LANEKIT);

        java.lang.Object loaded = GD.load(OUT);
        if (!(loaded instanceof PackedScene packed)) { GD.printErr("PLRTEST: bake output missing"); finishNow(); return; }
        Node baked = packed.instantiate();
        if (baked == null) { GD.printErr("PLRTEST: instantiate failed"); finishNow(); return; }
        addChild(baked);

        PathLaneRoute turnLane = findLane(baked, "Intersection_4WAY_001_N_E_L0");
        PathLaneRoute straightLane = findLane(baked, "Intersection_4WAY_001_N_S_L0");
        if (turnLane == null || straightLane == null) {
            GD.printErr("PLRTEST: expected PathLaneRoute nodes not found (turn=" + turnLane + " straight=" + straightLane + ")");
            finishNow(); return;
        }

        GD.print(String.format("PLRTEST turnLane total=%.2f turn=%s start=%s end=%s",
                turnLane.total(), turnLane.getTurn(), turnLane.startPoint(), turnLane.endPoint()));
        GD.print(String.format("PLRTEST straightLane total=%.2f turn=%s start=%s end=%s",
                straightLane.total(), straightLane.getTurn(), straightLane.startPoint(), straightLane.endPoint()));

        Vector3 p0 = turnLane.pointAtLength(0);
        Vector3 p1 = turnLane.pointAtLength(turnLane.total());
        boolean okStart = p0.minus(turnLane.startPoint()).length() < 0.05;
        boolean okEnd = p1.minus(turnLane.endPoint()).length() < 0.05;
        GD.print("PLRTEST arc-length endpoints match start/end: " + (okStart && okEnd));

        // Synthetic partner PathLaneRoute starting exactly at turnLane's end point -- proves
        // cross-instance PathLaneRoute-to-PathLaneRoute connectivity via LaneGraph's proximity
        // clustering (same mechanism that would connect this junction to a hand-authored
        // VehicleRoute network or another PathLaneRoute junction once ports are actually linked).
        // Added BEFORE the first LaneGraph query -- LaneGraph caches its graph once per scene
        // (routes are static content), so a topology change after the first successorsOf() call
        // would go unnoticed by design; this is not something a real, static-content bake ever
        // needs to react to.
        PathLaneRoute partner = buildSyntheticPartner("SyntheticPartner", turnLane.endPoint());
        addChild(partner);
        List<com.openworld.world.Lane> succWithPartner = LaneGraph.successorsOf(turnLane);
        StringBuilder names = new StringBuilder();
        for (com.openworld.world.Lane l : succWithPartner) names.append(((Node) l).getName()).append(", ");
        GD.print("PLRTEST successors with a coincident-start partner present (expect 1, the partner): "
                + succWithPartner.size() + " [" + names + "]");

        turnVehicle = spawnVehicle("TurnVehicle", turnLane.startPoint(), turnLane, true);
        straightVehicle = spawnVehicle("StraightVehicle", straightLane.startPoint(), straightLane, false);

        GD.print("PLRTEST vehicles spawned, running physics for " + RUN_SECONDS + "s...");
    }

    private PathLaneRoute findLane(Node n, String name) {
        if (n instanceof PathLaneRoute p && n.getName().toString().equals(name)) return p;
        for (Node c : n.getChildren()) {
            PathLaneRoute found = findLane(c, name);
            if (found != null) return found;
        }
        return null;
    }

    private PathLaneRoute buildSyntheticPartner(String name, Vector3 start) {
        PathLaneRoute lane = new PathLaneRoute();
        lane.setName(new StringName(name));
        Curve3D curve = new Curve3D();
        curve.addPoint(start);
        curve.addPoint(start.plus(new Vector3(0, 0, 10)));
        Path3D path3d = new Path3D();
        path3d.setName(new StringName("Path3D"));
        path3d.setCurve(curve);
        lane.addChild(path3d);
        return lane;
    }

    /** Mirrors {@link DriveTestHost}'s spawn order exactly: attach the {@code Controller} child
     *  BEFORE {@code addChild(v)} puts the vehicle in the tree, since {@code Vehicle._ready()}
     *  scans its children for a {@code Controller} at that moment -- attaching it after would be
     *  invisible to that scan and the vehicle would never receive input (silently sits under
     *  gravity only, which is exactly the bug this ordering fixes). */
    private Vehicle spawnVehicle(String name, Vector3 pos, PathLaneRoute lane, boolean isTurn) {
        java.lang.Object res = ResourceLoader.INSTANCE.load(
                "res://src/main/resources/com/openworld/vehicle/Vehicle.tscn", "",
                ResourceLoader.CacheMode.REUSE);
        if (!(res instanceof PackedScene packed) || !(packed.instantiate() instanceof Vehicle v)) {
            GD.printErr("PLRTEST: cannot load Vehicle.tscn");
            return null;
        }
        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = name;
        v.characterInfo = info;
        v.setName(new StringName(name));

        VehicleAIController ctrl = new VehicleAIController();
        v.addChild(ctrl);        // BEFORE addChild(v) -- see javadoc above
        ctrl.setRoute(lane);
        if (isTurn) turnCtrl = ctrl; else straightCtrl = ctrl;

        addChild(v);
        v.setGlobalPosition(pos.plus(new Vector3(0, 0.5, 0)));
        // Align spawn heading to the lane's own start tangent -- otherwise the AI's proportional
        // (no-derivative-damping) steering has to correct a large initial heading error, and that
        // correction transient (a real, physically-plausible oscillation, not a Lane/PathLaneRoute
        // bug) would dominate any heading-change measurement far longer than expected.
        double[] t = lane.startTangentXZ();
        if (t != null) v.setGlobalRotation(new Vector3(0, Math.atan2(-t[0], -t[1]), 0));
        return v;
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (done) return;
        // Skip the first SETTLE_SECONDS: both cars spawn at whatever orientation Vehicle.tscn
        // defaults to, not aligned with their lane's tangent, so there's an initial "turn to face
        // the lane" transient common to BOTH cars regardless of lane shape -- measuring from t=0
        // would swamp the actual lane-curvature signal with that shared confound.
        boolean settled = (RUN_SECONDS - timer) >= SETTLE_SECONDS;
        if (turnVehicle != null) {
            double yaw = turnVehicle.getGlobalRotation().getY();
            if (settled && !turnCtrl.isFinished() && !Double.isNaN(lastYawTurn))
                accumTurn += Math.abs(angDiff(yaw, lastYawTurn));
            lastYawTurn = yaw;
        }
        if (straightVehicle != null) {
            double yaw = straightVehicle.getGlobalRotation().getY();
            if (settled && !straightCtrl.isFinished() && !Double.isNaN(lastYawStraight))
                accumStraight += Math.abs(angDiff(yaw, lastYawStraight));
            lastYawStraight = yaw;
        }
        timer -= delta;
        if (((int) (timer * 10)) % 10 == 0 && turnVehicle != null) {
            GD.print(String.format("PLRTEST TICK t=%.1f turnFinished=%s straightFinished=%s turnPos=%s straightPos=%s",
                    RUN_SECONDS - timer, turnCtrl.isFinished(), straightCtrl.isFinished(),
                    turnVehicle.getGlobalPosition(), straightVehicle.getGlobalPosition()));
        }
        if (timer <= 0.0) finishNow();
    }

    private static double angDiff(double a, double b) {
        return Math.atan2(Math.sin(a - b), Math.cos(a - b));
    }

    private void finishNow() {
        if (done) return;
        done = true;
        double tDeg = Math.toDegrees(accumTurn), sDeg = Math.toDegrees(accumStraight);
        GD.print(String.format("PLRTEST SUMMARY turnHeadingChangeDeg=%.1f straightHeadingChangeDeg=%.1f", tDeg, sDeg));
        GD.print("PLRTEST verdict=" + ((tDeg > 20.0 && sDeg < 10.0) ? "PASS" : "CHECK"));
        if (getTree() != null) getTree().quit();
    }
}
