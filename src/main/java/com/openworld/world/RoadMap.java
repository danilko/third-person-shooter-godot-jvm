package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.api.FileAccess;
import godot.api.Node;
import godot.api.Time;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The one place the map, the minimap and the GPS arrow get the road network and the route from
 * (PLAN.md 4.7). Plain static like {@code WaypointStore} — not a node.
 *
 * <p><b>Where the roads come from.</b> Every {@link ZoneMarker} whose zone streams a road piece
 * ({@code .../pieces/<stem>.tscn}) names, by the build's own convention, the piece's lanekit
 * sidecar {@code res://assets/world_source/pieces/<stem>.lanekit.json} ({@code build_piece.sh}
 * resolves it the same way). The sidecar is read directly rather than the {@link Lane} nodes the
 * zone instances, because those exist only while the zone is streamed in, and a route to a
 * waypoint in an unloaded zone would otherwise have nothing to walk. Each sidecar is placed with the
 * zone's own geometry frame ({@link Zone#geometryFrame}), so the lanes land exactly where the piece
 * puts them. There is no second road record.
 *
 * <p><b>The route</b> is per character, recomputed when the waypoint changes, when the network is
 * rebuilt, or when the body has left it by more than {@link #OFF_ROUTE_METERS} (throttled to
 * {@link #REROUTE_SECONDS}) — GTA's "recalculating" rule, never a per-frame search.
 */
public final class RoadMap {

    /** The directory the build writes lanekit sidecars to. */
    public static final String LANEKIT_DIR = "res://assets/world_source/pieces/";
    /** Leave the route by this much (XZ metres) and it is recomputed. */
    public static final double OFF_ROUTE_METERS = 25.0;
    /** At most one re-route per this many seconds per character. */
    public static final double REROUTE_SECONDS = 1.0;
    /** How far along the route the GPS arrow points. */
    public static final double LOOKAHEAD_METERS = 30.0;
    /** Within this plan distance of the waypoint the arrow points straight at it. */
    public static final double DIRECT_METERS = 40.0;

    private static RoadGraph graph;
    private static boolean built = false;
    private static long graphSceneId;
    private static String graphSignature = "";
    private static int graphVersion = 0;
    private static final Set<String> sources = new HashSet<>();

    private static final class Cached {
        Vector3 waypoint;
        RoadGraph.Route route;
        int version;
        double computedAt;
    }
    private static final Map<String, Cached> ROUTES = new HashMap<>();

    private RoadMap() { }

    /** The network for the current scene, built on first use and rebuilt when the zone set changes.
     *  Null when no road piece in the scene has a sidecar. */
    public static RoadGraph graph() {
        ZoneManager zm = ZoneManager.get();
        if (zm == null || zm.getTree() == null) return graph;
        Node scene = zm.getTree().getCurrentScene();
        long sceneId = scene != null ? scene.getInstanceId() : 0;
        StringBuilder sig = new StringBuilder();
        for (ZoneMarker m : zm.getMarkers()) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null) continue;
            String path = lanekitPathFor(m.zone.geometryPath);
            if (path != null) sig.append(path).append('|');
        }
        String s = sig.toString();
        if (built && sceneId == graphSceneId && s.equals(graphSignature)) return graph;
        built = true;
        graphSceneId = sceneId;
        graphSignature = s;
        graph = build(zm.getMarkers());
        graphVersion++;
        ROUTES.clear();
        return graph;
    }

    /** Bumped on every rebuild, so a cache of drawn roads knows to refresh. */
    public static int version() { return graphVersion; }

    /** The sidecar paths the current network was read from. */
    public static Set<String> sources() { return new HashSet<>(sources); }

    private static RoadGraph build(List<ZoneMarker> markers) {
        sources.clear();
        RoadGraph g = new RoadGraph();
        long t0 = Time.INSTANCE.getTicksMsec();
        for (ZoneMarker m : markers) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null) continue;
            String path = lanekitPathFor(m.zone.geometryPath);
            if (path == null || sources.contains(path) || !FileAccess.fileExists(path)) continue;
            Object doc;
            try {
                doc = MiniJson.parse(FileAccess.getFileAsString(path));
            } catch (IllegalArgumentException e) {
                GD.printErr("RoadMap: " + path + ": " + e.getMessage());
                continue;
            }
            g.addLanekit(doc, frame(m.zone.geometryFrame(m)));
            sources.add(path);
        }
        if (g.laneCount() == 0) return null;
        g.finish();
        GD.print("RoadMap: " + g.laneCount() + " lanes from " + sources.size() + " sidecar(s) in "
                + (Time.INSTANCE.getTicksMsec() - t0) + " ms");
        return g;
    }

    /** {@code .../pieces/<stem>.tscn} (or {@code .scn}) → the sidecar path; null for anything else. */
    public static String lanekitPathFor(String geometryPath) {
        if (geometryPath == null || geometryPath.isEmpty()) return null;
        int slash = geometryPath.lastIndexOf('/');
        int dot = geometryPath.lastIndexOf('.');
        if (dot <= slash) return null;
        return LANEKIT_DIR + geometryPath.substring(slash + 1, dot) + ".lanekit.json";
    }

    private static double[] frame(Transform3D t) {
        Basis b = t.getBasis();
        Vector3 bx = b.getX(), by = b.getY(), bz = b.getZ(), o = t.getOrigin();
        return new double[]{bx.getX(), by.getX(), bz.getX(),
                            bx.getY(), by.getY(), bz.getY(),
                            bx.getZ(), by.getZ(), bz.getZ(),
                            o.getX(), o.getY(), o.getZ()};
    }

    /** The route from {@code from} to {@code waypoint} for {@code characterId}, cached as described
     *  above. Null with no network, no waypoint or no legal route. */
    public static RoadGraph.Route routeFor(String characterId, Vector3 from, Vector3 waypoint) {
        RoadGraph g = graph();
        if (g == null || waypoint == null || from == null || characterId == null) return null;
        Cached c = ROUTES.computeIfAbsent(characterId, k -> new Cached());
        double now = Time.INSTANCE.getTicksMsec() / 1000.0;
        boolean stale = c.version != graphVersion || c.waypoint == null || !c.waypoint.equals(waypoint);
        if (!stale && c.route != null && now - c.computedAt >= REROUTE_SECONDS
                && c.route.distanceXZ(from.getX(), from.getZ()) > OFF_ROUTE_METERS) stale = true;
        if (!stale && c.route == null && now - c.computedAt >= REROUTE_SECONDS) stale = true;
        if (stale) {
            c.route = g.route(from.getX(), from.getY(), from.getZ(),
                    waypoint.getX(), waypoint.getY(), waypoint.getZ());
            c.waypoint = waypoint;
            c.version = graphVersion;
            c.computedAt = now;
        }
        return c.route;
    }

    /** The route last computed for {@code characterId}, without searching. */
    public static RoadGraph.Route cachedRoute(String characterId) {
        Cached c = characterId != null ? ROUTES.get(characterId) : null;
        return c != null ? c.route : null;
    }

    /**
     * Where a GPS arrow for a body at {@code from} should point: along the route, {@link
     * #LOOKAHEAD_METERS} past the body's place on it — which leads a body off the road onto it
     * first — and straight at the waypoint once within {@link #DIRECT_METERS} of it, past the
     * route's end, or when there is no route at all.
     */
    public static Vector3 gpsTarget(String characterId, Vector3 from, Vector3 waypoint) {
        if (waypoint == null || from == null) return waypoint;
        double dx = waypoint.getX() - from.getX(), dz = waypoint.getZ() - from.getZ();
        if (Math.sqrt(dx * dx + dz * dz) < DIRECT_METERS) return waypoint;
        RoadGraph.Route r = routeFor(characterId, from, waypoint);
        if (r == null || r.pointCount() < 2) return waypoint;
        double s = r.progressOf(from.getX(), from.getZ());
        if (s + LOOKAHEAD_METERS >= r.length) return waypoint;
        double[] p = r.pointAt(s + LOOKAHEAD_METERS);
        return new Vector3(p[0], p[1], p[2]);
    }

    /** Drop the cached network and every route (scene restart / shutdown hygiene). */
    public static void clear() {
        graph = null;
        built = false;
        graphSignature = "";
        graphSceneId = 0;
        sources.clear();
        ROUTES.clear();
    }
}
