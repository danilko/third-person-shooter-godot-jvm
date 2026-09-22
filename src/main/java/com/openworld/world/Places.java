package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.api.FileAccess;
import godot.api.Node;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * What the map can NAME: the island's enterable buildings, its landmarks, and the region boxes
 * (`world/IslandPlaces.json`, derived by {@code tools/island_buildings.py} from the same placement that writes
 * the buildings themselves — PLAN.md 3.18n, user: "the map should say WHERE you are").
 *
 * <p><b>Nothing here is authored.</b> A building is a place because the placement made it enterable (its scene
 * is a {@code _Shop} or {@code _Open} variant), and a region is a box the placement already uses to decide what
 * stands there. So a new shop or a moved region reaches the map by re-running {@code derive}, and the map can
 * never name a building that is not there — which is the failure a hand-kept list of map markers has.
 *
 * <p>Two positions per place and they mean different things: {@link Place#at} is where the blip sits (the
 * footprint centre, so a big site's blip is on the site) and {@link Place#go} is the front face, which is where
 * the door is — a waypoint dropped on a blip should send you to the front of the shop. {@code RoadMap} then
 * snaps the goal to the nearest lane, so {@code go} decides which side of the block you are routed to.
 *
 * <p>Plain static data, like {@link Sidewalks} and {@code RoadMap}: read once, lazily, and nothing here holds a
 * Godot object.
 */
public final class Places {

    /**
     * PER SCENE, like {@code RoadMap}'s bake: the places are a fact about ONE world, and a single fixed path
     * drew the island's shops on DebugWorld's map at island coordinates — a blip naming a building 2 km away
     * that is not there. The current scene's stem names the file; a world with no file has no places.
     */
    public static final String DIR = "res://src/main/resources/com/openworld/world/places/";
    /** Places of this tier or better are drawn at any map scale; the rest only when zoomed in. */
    public static final int LANDMARK_TIER = 2;

    /** One place: what to call it, where its blip sits, and where a waypoint on it should send you. */
    public record Place(String name, String kind, int tier, Vector3 at, Vector3 go) {}

    /** A named region of the island, as an XZ box in the Godot world frame. */
    public record Region(String name, double x0, double z0, double x1, double z1) {
        public boolean holds(double x, double z) { return x >= x0 && x <= x1 && z >= z0 && z <= z1; }
    }

    private static List<Place> places = null;
    /** Every building's footprint quad, {kind, x0, z0, x1, z1, x2, z2, x3, z3} (kind 1 = a place). */
    private static List<float[]> footprints = new ArrayList<>();
    /** Bumped on every (re)load, so a picture built from the footprints knows it is stale. */
    private static int version = 0;
    private static List<Region> regions = null;
    private static String loadedFor = "\u0000";
    private static String wanted = "";
    private static final Map<Long, List<Integer>> buckets = new HashMap<>();
    private static final double BUCKET = 200.0;

    private Places() {}

    private static long key(double x, double z) {
        long i = (long) Math.floor(x / BUCKET), j = (long) Math.floor(z / BUCKET);
        return (i << 32) ^ (j & 0xffffffffL);
    }

    private static Vector3 vec(Object o) {
        @SuppressWarnings("unchecked") List<Object> a = (List<Object>) o;
        return new Vector3((Double) a.get(0), (Double) a.get(1), (Double) a.get(2));
    }

    /** {@code <DIR><scene stem>.places.json} for the scene that is up, or "" with no scene. */
    public static String pathFor(String scenePath) {
        if (scenePath == null || scenePath.isEmpty()) return "";
        String stem = scenePath.substring(scenePath.lastIndexOf('/') + 1);
        int dot = stem.lastIndexOf('.');
        if (dot > 0) stem = stem.substring(0, dot);
        return DIR + stem + ".places.json";
    }

    /**
     * Say which world is up. Every caller is a node, so the scene comes from the tree rather than from an
     * engine singleton, and re-binding to the same scene costs one string compare. Unbound = no places.
     */
    public static void bind(Node any) {
        if (any == null) return;
        // The world is found by walking the OWNER chain to its outermost root, which is {@code RoadMap}'s own
        // rule for the same question. `getCurrentScene()` alone is null for a world that was `add_child`ed
        // rather than `change_scene_to_file`d -- which is how every probe builds one, so keying on it would
        // make the gates measure a different code path from the game.
        Node n = any;
        while (n.getOwner() != null) n = n.getOwner();
        String path = n.getSceneFilePath();
        if (path.isEmpty() && any.getTree() != null) {
            Node scene = any.getTree().getCurrentScene();
            if (scene != null) path = scene.getSceneFilePath();
        }
        wanted = pathFor(path);
    }

    @SuppressWarnings("unchecked")
    private static synchronized void load() {
        if (places != null && loadedFor.equals(wanted)) return;
        String path = wanted;
        loadedFor = path;
        places = new ArrayList<>();
        regions = new ArrayList<>();
        footprints = new ArrayList<>();
        version++;
        buckets.clear();
        if (path.isEmpty() || !FileAccess.fileExists(path)) return;
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(path));
        for (Object o : (List<Object>) doc.get("places")) {
            Map<String, Object> m = (Map<String, Object>) o;
            places.add(new Place(String.valueOf(m.get("name")), String.valueOf(m.get("kind")),
                    (int) (double) (Double) m.get("tier"), vec(m.get("at")), vec(m.get("go"))));
        }
        for (Object o : (List<Object>) doc.get("regions")) {
            Map<String, Object> m = (Map<String, Object>) o;
            List<Object> b = (List<Object>) m.get("box");
            regions.add(new Region(String.valueOf(m.get("name")), (Double) b.get(0), (Double) b.get(1),
                    (Double) b.get(2), (Double) b.get(3)));
        }
        Object fps = doc.get("footprints");
        if (fps instanceof List<?> rows) {
            for (Object o : rows) {
                List<Object> r = (List<Object>) o;
                float[] q = new float[r.size()];
                for (int k = 0; k < q.length; k++) q[k] = (float) (double) (Double) r.get(k);
                if (q.length == 9) footprints.add(q);
            }
        }
        for (int i = 0; i < places.size(); i++) {
            Vector3 p = places.get(i).at();
            buckets.computeIfAbsent(key(p.getX(), p.getZ()), k -> new ArrayList<>()).add(i);
        }
    }

    public static List<Place> all() { load(); return places; }

    /** The building footprints of this world (see {@code island_buildings.write_places}); empty with none. */
    public static List<float[]> footprints() { load(); return footprints; }

    /** Changes whenever the record is (re)loaded -- for a picture that caches what it drew from it. */
    public static int version() { load(); return version; }

    public static List<Region> regions() { load(); return regions; }

    /**
     * The region holding this point, or {@code ""} outside every one. FIRST match wins, which is the placement's
     * own rule ({@code island_buildings.region_of}) — the boxes overlap, and one owner of "which region is this"
     * is what lets the HUD and the placement agree.
     */
    public static String regionAt(double x, double z) {
        for (Region r : regions()) if (r.holds(x, z)) return r.name();
        return "";
    }

    /** Places within {@code radius} of a point (XZ). */
    public static List<Place> near(Vector3 centre, double radius) {
        load();
        List<Place> out = new ArrayList<>();
        int r = (int) Math.ceil(radius / BUCKET);
        long ci = (long) Math.floor(centre.getX() / BUCKET), cj = (long) Math.floor(centre.getZ() / BUCKET);
        double rr = radius * radius;
        for (long i = ci - r; i <= ci + r; i++) {
            for (long j = cj - r; j <= cj + r; j++) {
                List<Integer> b = buckets.get((i << 32) ^ (j & 0xffffffffL));
                if (b == null) continue;
                for (int k : b) {
                    Place p = places.get(k);
                    double dx = p.at().getX() - centre.getX(), dz = p.at().getZ() - centre.getZ();
                    if (dx * dx + dz * dz <= rr) out.add(p);
                }
            }
        }
        return out;
    }

    /** The place whose blip is within {@code radius} of a point, nearest first, or null. */
    public static Place nearest(Vector3 point, double radius) {
        Place best = null;
        double bd = radius * radius;
        for (Place p : near(point, radius)) {
            double dx = p.at().getX() - point.getX(), dz = p.at().getZ() - point.getZ();
            if (dx * dx + dz * dz <= bd) {
                bd = dx * dx + dz * dz;
                best = p;
            }
        }
        return best;
    }

    /** Drop the cache (a scene swap, or a probe that rewrote the record). */
    public static synchronized void reset() {
        places = null;
        loadedFor = "\u0000";
        regions = null;
        buckets.clear();
    }
}
