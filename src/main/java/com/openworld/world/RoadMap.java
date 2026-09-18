package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.api.DirAccess;
import godot.api.FileAccess;
import godot.api.Image;
import godot.api.ImageTexture;
import godot.api.Node;
import godot.api.ResourceLoader;
import godot.api.ResourceSaver;
import godot.api.Texture2D;
import godot.api.Time;
import godot.core.Basis;
import godot.core.PackedByteArray;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
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
 *
 * <p><b>The baked road map (4.7b).</b> Nothing about the roads is derived per frame. A scene's roads
 * are baked once by {@code tools/godot/bake_road_map.gd} into {@link #BAKE_DIR}{@code <Scene>
 * .roadmap.bin} (the graph in world space plus the {@link RoadIndex} cell grid over the whole map
 * square, so a position finds its candidate lanes with one array read) and {@code <Scene>
 * .roadmap.res} (the road picture of the whole world to the {@link WorldBounds} wall, with
 * max-filtered mips — {@link RoadRaster}). The minimap and the map draw that picture as one
 * textured polygon. A bake is used only while its signature (every sidecar's path, placement and
 * md5, and the map square) matches the scene; otherwise the same code builds it live at load, says
 * so once, and {@link #source} reads {@code "live"} — a stale bake is never drawn.
 */
public final class RoadMap {

    /** The directory the build writes lanekit sidecars to. */
    public static final String LANEKIT_DIR = "res://assets/world_source/pieces/";
    /** Where a scene's baked road map lives: {@code <SceneName>.roadmap.bin} / {@code .res}. */
    public static final String BAKE_DIR = "res://src/main/resources/com/openworld/world/roadmap/";
    /** Margin (m) round the roads when the scene has no {@link WorldBounds} to set the square. */
    public static final double AUTO_MARGIN = 100.0;
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
    private static RoadMapBake.Meta square;
    private static String bakeBase;
    private static String source = "";
    private static String staleReason = "";
    private static Texture2D texture;
    private static Image image;

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
        load(zm.getMarkers());
        graphVersion++;
        ROUTES.clear();
        return graph;
    }

    /** Bumped on every rebuild, so a cache of drawn roads knows to refresh. */
    public static int version() { return graphVersion; }

    /** The sidecar paths the current network was read from. */
    public static Set<String> sources() { return new HashSet<>(sources); }

    /** One road sidecar of the scene and where its piece is placed. */
    private record Source(String path, double[] frame) { }

    private static List<Source> sourcesOf(List<ZoneMarker> markers) {
        List<Source> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (ZoneMarker m : markers) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null) continue;
            String path = lanekitPathFor(m.zone.geometryPath);
            if (path == null || !seen.add(path) || !FileAccess.fileExists(path)) continue;
            out.add(new Source(path, frame(m.zone.geometryFrame(m))));
        }
        out.sort((a, b) -> a.path.compareTo(b.path));
        return out;
    }

    /** The scene the markers were authored in: the bake is per scene. */
    private static String scenePathOf(List<ZoneMarker> markers) {
        for (ZoneMarker m : markers) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null || lanekitPathFor(m.zone.geometryPath) == null)
                continue;
            Node owner = m.getOwner();
            if (owner != null && !owner.getSceneFilePath().isEmpty()) return owner.getSceneFilePath();
        }
        return null;
    }

    /** The map square from the world's wall, or null (then it is fitted to the roads). */
    private static double[] boundsSquare() {
        WorldBounds wb = WorldBounds.get();
        if (wb == null || !GD.isInstanceValid(wb) || !wb.isInsideTree()) return null;
        Vector3 c = wb.getGlobalPosition();
        double h = wb.halfExtent;
        return new double[]{c.getX() - h, c.getZ() - h, 2 * h};
    }

    private static String signatureOf(List<Source> srcs, double[] sq) {
        List<String> parts = new ArrayList<>();
        for (Source s : srcs) {
            StringBuilder f = new StringBuilder();
            for (double v : s.frame) f.append(String.format(Locale.ROOT, "%.4f,", v));
            parts.add(s.path + "|" + f + "|" + FileAccess.getMd5(s.path));
        }
        Collections.sort(parts);
        String sqs = sq == null ? "auto"
                : String.format(Locale.ROOT, "%.3f,%.3f,%.3f", sq[0], sq[1], sq[2]);
        return "square=" + sqs + "\n" + String.join("\n", parts);
    }

    private static void load(List<ZoneMarker> markers) {
        sources.clear();
        graph = null;
        square = null;
        texture = null;
        image = null;
        source = "";
        staleReason = "";
        List<Source> srcs = sourcesOf(markers);
        if (srcs.isEmpty()) return;
        for (Source s : srcs) sources.add(s.path);
        String scene = scenePathOf(markers);
        bakeBase = scene == null ? null : BAKE_DIR + baseName(scene);
        double[] sq = boundsSquare();
        String sig = signatureOf(srcs, sq);
        long t0 = Time.INSTANCE.getTicksMsec();
        String bin = bakeBase == null ? null : bakeBase + ".roadmap.bin";
        if (bin == null) {
            staleReason = "the markers belong to no saved scene";
        } else if (!FileAccess.fileExists(bin)) {
            staleReason = "no bake at " + bin;
        } else {
            byte[] data = FileAccess.getFileAsBytes(bin).toByteArray();
            RoadMapBake.Meta meta = RoadMapBake.readMeta(data);
            if (meta == null) staleReason = bin + " is unreadable or an old version";
            else if (!meta.signature.equals(sig)) staleReason = "the roads changed since " + bin + " was baked";
            else {
                RoadMapBake.Loaded l = RoadMapBake.read(data);
                graph = l.graph;
                square = l.meta;
                source = "bake";
                GD.print("RoadMap: " + graph.laneCount() + " lanes from the bake " + bin + " in "
                        + (Time.INSTANCE.getTicksMsec() - t0) + " ms");
                return;
            }
        }
        buildLive(srcs, sq, sig);
        if (graph != null) {
            source = "live";
            GD.print("RoadMap: " + graph.laneCount() + " lanes built LIVE from " + srcs.size()
                    + " sidecar(s) in " + (Time.INSTANCE.getTicksMsec() - t0) + " ms, because " + staleReason
                    + " -- run tools/godot/bake_road_map.gd");
        }
    }

    private static void buildLive(List<Source> srcs, double[] sq, String sig) {
        RoadGraph g = new RoadGraph();
        for (Source s : srcs) {
            Object doc;
            try {
                doc = MiniJson.parse(FileAccess.getFileAsString(s.path));
            } catch (IllegalArgumentException e) {
                GD.printErr("RoadMap: " + s.path + ": " + e.getMessage());
                continue;
            }
            g.addLanekit(doc, s.frame);
        }
        if (g.laneCount() == 0) return;
        g.finish();
        if (sq == null) sq = fitSquare(g);
        g.setIndex(RoadIndex.build(g, sq[0], sq[1], sq[2], RoadIndex.DEFAULT_CELL));
        graph = g;
        square = new RoadMapBake.Meta(sig, sq[0], sq[1], sq[2], RoadRaster.edgeFor(sq[2]));
    }

    private static double[] fitSquare(RoadGraph g) {
        double x0 = Double.MAX_VALUE, z0 = Double.MAX_VALUE, x1 = -Double.MAX_VALUE, z1 = -Double.MAX_VALUE;
        for (RoadGraph.Lane l : g.lanes()) {
            double[] b = l.boundsXZ();
            x0 = Math.min(x0, b[0]); z0 = Math.min(z0, b[1]); x1 = Math.max(x1, b[2]); z1 = Math.max(z1, b[3]);
        }
        double size = Math.max(x1 - x0, z1 - z0) + 2 * AUTO_MARGIN;
        return new double[]{(x0 + x1) * 0.5 - size * 0.5, (z0 + z1) * 0.5 - size * 0.5, size};
    }

    private static String baseName(String scenePath) {
        int slash = scenePath.lastIndexOf('/');
        int dot = scenePath.lastIndexOf('.');
        return scenePath.substring(slash + 1, dot > slash ? dot : scenePath.length());
    }

    /** "bake" (the committed bake matched), "live" (built at load, see {@link #staleReason}), or "". */
    public static String source() { graph(); return source; }

    /** Why the bake was not used ("" when it was). */
    public static String staleReason() { graph(); return staleReason; }

    /** The map square the picture and the index cover: {minX, minZ, size}; null with no roads. */
    public static double[] mapSquare() {
        graph();
        return square == null ? null : new double[]{square.minX, square.minZ, square.size};
    }

    /** The road picture of the whole map square (alpha = road). Null with no roads. */
    public static Texture2D mapTexture() {
        graph();
        if (texture != null || square == null) return texture;
        long t0 = Time.INSTANCE.getTicksMsec();
        String res = bakeBase == null ? null : bakeBase + ".roadmap.res";
        if ("bake".equals(source) && res != null && FileAccess.fileExists(res)
                && ResourceLoader.load(res, "", ResourceLoader.CacheMode.IGNORE) instanceof Image img
                && img.getWidth() == square.imagePx) {
            image = img;
        } else {
            image = paint(graph, square);
            if ("bake".equals(source)) GD.printErr("RoadMap: " + res + " is missing or the wrong size; painted live");
        }
        texture = ImageTexture.createFromImage(image);
        GD.print("RoadMap: road picture " + square.imagePx + " px (" + String.format(Locale.ROOT, "%.2f",
                square.size / square.imagePx) + " m/px) ready in " + (Time.INSTANCE.getTicksMsec() - t0) + " ms");
        return texture;
    }

    /** Road coverage 0..1 of the picture at a world point (probe readout; 0 off the map). */
    public static double coverageAt(double x, double z) {
        if (mapTexture() == null || image == null) return 0;
        int px = square.imagePx;
        int c = (int) Math.floor((x - square.minX) / square.size * px);
        int r = (int) Math.floor((z - square.minZ) / square.size * px);
        if (c < 0 || r < 0 || c >= px || r >= px) return 0;
        return image.getPixel(c, r).getA();
    }

    private static Image paint(RoadGraph g, RoadMapBake.Meta sq) {
        byte[] cov = RoadRaster.coverage(g, sq.minX, sq.minZ, sq.size, sq.imagePx);
        byte[] la8 = RoadRaster.la8WithMaxMips(cov, sq.imagePx);
        return Image.createFromData(sq.imagePx, sq.imagePx, true, Image.Format.LA8, new PackedByteArray(la8));
    }

    /**
     * Bake the current scene's road map: always built from the sidecars (never from an old bake),
     * then written as {@code .roadmap.bin} + {@code .roadmap.res}. Returns a one-line report, starting
     * {@code "OK"} or {@code "FAIL"}.
     */
    public static String bake() {
        ZoneManager zm = ZoneManager.get();
        if (zm == null) return "FAIL no ZoneManager";
        List<ZoneMarker> markers = zm.getMarkers();
        List<Source> srcs = sourcesOf(markers);
        String scene = scenePathOf(markers);
        if (srcs.isEmpty() || scene == null) return "FAIL no road sidecars in a saved scene";
        clear();
        double[] sq = boundsSquare();
        String sig = signatureOf(srcs, sq);
        long t0 = Time.INSTANCE.getTicksMsec();
        buildLive(srcs, sq, sig);
        if (graph == null) return "FAIL no lanes in " + srcs;
        long tIndex = Time.INSTANCE.getTicksMsec() - t0;
        byte[] data = RoadMapBake.write(square, graph);
        bakeBase = BAKE_DIR + baseName(scene);
        DirAccess.makeDirRecursiveAbsolute(BAKE_DIR);
        FileAccess f = FileAccess.open(bakeBase + ".roadmap.bin", FileAccess.ModeFlags.WRITE);
        if (f == null) return "FAIL cannot write " + bakeBase + ".roadmap.bin";
        f.storeBuffer(new PackedByteArray(data));
        f.close();
        long t1 = Time.INSTANCE.getTicksMsec();
        image = paint(graph, square);
        godot.core.Error err = ResourceSaver.save(image, bakeBase + ".roadmap.res",
                ResourceSaver.SaverFlags.FLAG_COMPRESS);
        if (err != godot.core.Error.OK) return "FAIL saving " + bakeBase + ".roadmap.res: " + err;
        long tPaint = Time.INSTANCE.getTicksMsec() - t1;
        // What was just written is what the next load reads.
        built = false;
        String report = String.format(Locale.ROOT,
                "OK %s: %d lanes from %d sidecar(s), square %.0f m at %d px (%.2f m/px), index %dx%d cells; "
                        + "graph+index %d ms, picture %d ms; %s.roadmap.bin %d bytes",
                baseName(scene), graph.laneCount(), srcs.size(), square.size, square.imagePx,
                square.size / square.imagePx, graph.index().nx, graph.index().nz, tIndex, tPaint, bakeBase,
                data.length);
        GD.print("RoadMap bake: " + report);
        return report;
    }

    /** Is the scene's bake current? {@code "fresh"}, or why not. Builds nothing. */
    public static String bakeStatus() {
        ZoneManager zm = ZoneManager.get();
        if (zm == null) return "no ZoneManager";
        List<ZoneMarker> markers = zm.getMarkers();
        List<Source> srcs = sourcesOf(markers);
        String scene = scenePathOf(markers);
        if (srcs.isEmpty() || scene == null) return "no road sidecars in a saved scene";
        String bin = BAKE_DIR + baseName(scene) + ".roadmap.bin";
        if (!FileAccess.fileExists(bin)) return "no bake at " + bin;
        RoadMapBake.Meta meta = RoadMapBake.readMeta(FileAccess.getFileAsBytes(bin).toByteArray());
        if (meta == null) return bin + " is unreadable or an old version";
        if (!meta.signature.equals(signatureOf(srcs, boundsSquare()))) return "the roads changed since " + bin + " was baked";
        if (!FileAccess.fileExists(BAKE_DIR + baseName(scene) + ".roadmap.res")) return "no picture beside " + bin;
        return "fresh";
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
        square = null;
        texture = null;
        image = null;
        source = "";
        staleReason = "";
        graphSignature = "";
        graphSceneId = 0;
        sources.clear();
        ROUTES.clear();
    }
}
