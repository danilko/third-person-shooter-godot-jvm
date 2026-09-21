package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.api.FileAccess;
import godot.core.PackedVector3Array;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * The island's footways as walkable polylines (`world/IslandSidewalks.json`, derived by `tools/island_buildings.py` from
 * the same road solve that places the buildings: the centre of each road-run side's footway, Godot world frame, at
 * footway height). Read once, lazily, and bucketed on a {@link #BUCKET} grid so "a sidewalk near here" is a few array
 * reads. What reads it: ZoneManager's {@code SpawnConfig.behavior = "sidewalk"} spawn (PLAN.md 3.6 pedestrians).
 *
 * <p>Plain static data, like {@code RoadMap}: nothing here holds a Godot object but the one path array a walker is
 * handed, which is a value type.
 */
public final class Sidewalks {

    public static final String PATH = "res://src/main/resources/com/openworld/world/IslandSidewalks.json";
    private static final double BUCKET = 50.0;

    /** One footway: its points and cumulative arc length. */
    public static final class Walk {
        public final Vector3[] pts;
        public final double[] cum;
        Walk(Vector3[] pts) {
            this.pts = pts;
            cum = new double[pts.length];
            for (int i = 1; i < pts.length; i++) cum[i] = cum[i - 1] + pts[i].distanceTo(pts[i - 1]);
        }
        public double length() { return cum[cum.length - 1]; }
        public PackedVector3Array packed() {
            PackedVector3Array a = new PackedVector3Array();
            for (Vector3 p : pts) a.append(p);
            return a;
        }
    }

    /** A place on a footway: which walk and how far along it. */
    public record Spot(Walk walk, double along, Vector3 point) {}

    private static List<Walk> walks = null;
    private static final Map<Long, List<int[]>> buckets = new HashMap<>();   // bucket -> [walk, point index]

    private Sidewalks() {}

    private static long key(double x, double z) {
        long i = (long) Math.floor(x / BUCKET), j = (long) Math.floor(z / BUCKET);
        return (i << 32) ^ (j & 0xffffffffL);
    }

    @SuppressWarnings("unchecked")
    public static synchronized List<Walk> all() {
        if (walks != null) return walks;
        walks = new ArrayList<>();
        buckets.clear();
        if (!FileAccess.fileExists(PATH)) {
            GD.printErr("Sidewalks: no " + PATH + " (run tools/island_buildings.py derive)");
            return walks;
        }
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(PATH));
        for (Object o : (List<Object>) doc.get("sidewalks")) {
            List<Object> raw = (List<Object>) ((Map<String, Object>) o).get("points");
            Vector3[] pts = new Vector3[raw.size()];
            for (int i = 0; i < pts.length; i++) {
                List<Object> p = (List<Object>) raw.get(i);
                pts[i] = new Vector3((Double) p.get(0), (Double) p.get(1), (Double) p.get(2));
            }
            if (pts.length < 2) continue;
            int w = walks.size();
            walks.add(new Walk(pts));
            for (int i = 0; i < pts.length; i++) {
                buckets.computeIfAbsent(key(pts[i].getX(), pts[i].getZ()), k -> new ArrayList<>()).add(new int[]{w, i});
            }
        }
        return walks;
    }

    /** Every footway point within {@code radius} of {@code centre} (XZ), as spots. */
    public static List<Spot> near(Vector3 centre, double radius) {
        List<Walk> ws = all();
        List<Spot> out = new ArrayList<>();
        int r = (int) Math.ceil(radius / BUCKET);
        long ci = (long) Math.floor(centre.getX() / BUCKET), cj = (long) Math.floor(centre.getZ() / BUCKET);
        for (long i = ci - r; i <= ci + r; i++) {
            for (long j = cj - r; j <= cj + r; j++) {
                List<int[]> b = buckets.get((i << 32) ^ (j & 0xffffffffL));
                if (b == null) continue;
                for (int[] e : b) {
                    Walk w = ws.get(e[0]);
                    Vector3 p = w.pts[e[1]];
                    double dx = p.getX() - centre.getX(), dz = p.getZ() - centre.getZ();
                    if (dx * dx + dz * dz <= radius * radius) out.add(new Spot(w, w.cum[e[1]], p));
                }
            }
        }
        return out;
    }

    /** A random footway spot within {@code radius} of {@code centre}, or null when there is none. */
    public static Spot randomNear(Vector3 centre, double radius, Random rng) {
        List<Spot> s = near(centre, radius);
        return s.isEmpty() ? null : s.get(rng.nextInt(s.size()));
    }
}
