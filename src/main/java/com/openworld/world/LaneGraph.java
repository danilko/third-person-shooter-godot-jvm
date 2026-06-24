package com.openworld.world;

import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The connected traffic lane-graph (PLAN.md I3b) — <b>nodes = junctions, edges = lanes</b>.
 *
 * <p>Derived from geometry, not hand-authored: every {@link VehicleRoute} in the active scene is a
 * directional lane; lanes whose endpoints fall within {@link #JUNCTION_RADIUS} of each other share a
 * junction. {@link #successorsOf} then returns the lanes a car may continue onto at the end of a lane
 * (every outgoing lane at its end-junction, excluding the direct reverse), so a car picks a random turn
 * at each junction with no per-route wiring. This scales to any road network (e.g. I6 Blender-authored
 * lanes) where the lightweight {@code VehicleRoute.nextRoutes} strings would not.
 *
 * <p>Plain Java helper (like {@code SpawnPool}), not a {@code @RegisterClass} / AutoLoad. Cached per
 * scene via the scene-instance id (mirrors {@code WorldZoneManager.detectSceneReload}); routes are
 * static scene content, so the graph is built once per scene and reused.
 */
public final class LaneGraph {

    /** Endpoints within this distance (m, XZ) are treated as the same junction. Must comfortably exceed
     *  a road's lane spacing (opposing lanes ±1.75 m = 3.5 m apart) so paired lanes share a junction,
     *  while staying well under the gap between distinct junctions. */
    public static final double JUNCTION_RADIUS = 4.5;

    /** Set true to log the derived junction/lane counts once per scene build. */
    public static boolean debug = false;

    private static LaneGraph instance;

    private long sceneId = 0;
    private final Map<VehicleRoute, Integer> startJunction = new HashMap<>();
    private final Map<VehicleRoute, Integer> endJunction   = new HashMap<>();
    private final Map<Integer, List<VehicleRoute>> outgoing = new HashMap<>();

    private LaneGraph() {}

    /** Lanes a car may continue onto at the end of {@code lane} — outgoing lanes at its end-junction,
     *  minus the direct reverse. Empty when the lane dead-ends (no connected lane). */
    public static List<VehicleRoute> successorsOf(VehicleRoute lane) {
        LaneGraph g = forScene(lane);
        if (g == null) return new ArrayList<>();
        Integer ej = g.endJunction.get(lane);
        if (ej == null) return new ArrayList<>();
        VehicleRoute rev = g.reverseInternal(lane);
        List<VehicleRoute> result = new ArrayList<>();
        for (VehicleRoute o : g.outgoing.getOrDefault(ej, new ArrayList<>()))
            if (o != lane && o != rev) result.add(o);
        return result;
    }

    /** The lane running back the way {@code lane} came (starts at its end-junction, ends at its
     *  start-junction) — the U-turn target. Null when none is authored. */
    public static VehicleRoute reverseOf(VehicleRoute lane) {
        LaneGraph g = forScene(lane);
        return g == null ? null : g.reverseInternal(lane);
    }

    private VehicleRoute reverseInternal(VehicleRoute lane) {
        Integer sj = startJunction.get(lane), ej = endJunction.get(lane);
        if (sj == null || ej == null) return null;
        for (VehicleRoute o : outgoing.getOrDefault(ej, new ArrayList<>())) {
            if (o == lane) continue;
            Integer oej = endJunction.get(o);
            if (oej != null && oej.equals(sj)) return o;
        }
        return null;
    }

    private static LaneGraph forScene(Node anyNode) {
        if (anyNode == null || anyNode.getTree() == null) return null;
        Node scene = anyNode.getTree().getCurrentScene();
        if (scene == null) return null;
        long id = scene.getInstanceId();
        if (instance == null || instance.sceneId != id) {
            instance = new LaneGraph();
            instance.sceneId = id;
            instance.build(scene);
        }
        return instance;
    }

    private void build(Node scene) {
        startJunction.clear(); endJunction.clear(); outgoing.clear();
        List<VehicleRoute> lanes = new ArrayList<>();
        collect(scene, lanes);
        List<Vector3> junctions = new ArrayList<>();   // representative position per junction id
        for (VehicleRoute lane : lanes) {
            Vector3 sp = lane.startPoint(), ep = lane.endPoint();
            if (sp == null || ep == null) continue;
            int sj = junctionFor(sp, junctions);
            int ej = junctionFor(ep, junctions);
            startJunction.put(lane, sj);
            endJunction.put(lane, ej);
            outgoing.computeIfAbsent(sj, k -> new ArrayList<>()).add(lane);
        }
        if (debug) GD.print("LaneGraph: built " + lanes.size() + " lanes / " + junctions.size()
                + " junctions for scene " + scene.getName());
    }

    private static int junctionFor(Vector3 p, List<Vector3> junctions) {
        for (int i = 0; i < junctions.size(); i++) {
            double dx = junctions.get(i).getX() - p.getX(), dz = junctions.get(i).getZ() - p.getZ();
            if (Math.sqrt(dx * dx + dz * dz) <= JUNCTION_RADIUS) return i;
        }
        junctions.add(p);
        return junctions.size() - 1;
    }

    private static void collect(Node node, List<VehicleRoute> out) {
        if (node instanceof VehicleRoute r) out.add(r);
        for (Node c : node.getChildren()) collect(c, out);
    }
}
