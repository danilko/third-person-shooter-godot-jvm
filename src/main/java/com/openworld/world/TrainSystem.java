package com.openworld.world;

import com.openworld.util.CollisionLayers;
import com.openworld.util.MiniJson;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.AnimatableBody3D;
import godot.api.BaseMaterial3D;
import godot.api.BoxShape3D;
import godot.api.Camera3D;
import godot.api.CollisionShape3D;
import godot.api.FileAccess;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.ResourceLoader;
import godot.api.SphereMesh;
import godot.api.StandardMaterial3D;
import godot.api.Time;
import godot.core.Basis;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.CRC32;

/**
 * RUNNING TRAINS (PLAN.md "NEXT" piece 5, user 2026-09-29: "one or two sets per line") -- registered as the AutoLoad
 * "TrainSystem".
 *
 * <p><b>The track is the rail build's, read from its sidecars.</b> Every ZoneMarker streaming a rail piece
 * ({@code Roads_*Rail_<zone>}) names its lanekit (the {@link RoadMap} convention); its {@code road_class "rail"} lanes
 * are joined along their {@code next} edges into TRACKS, each a chain from one buffer stop to the other (a line's two
 * tracks are two chains). The geometry is read once, so a train exists whether or not its pieces are streamed.
 *
 * <p><b>The stops are the stations'.</b> The island's come from the rail reserve ({@code IslandRailReserve.json}),
 * DebugWorld's from its layout ({@code debug_world_layout.json}): a track that passes through a station's box (within
 * {@link #STOP_REACH} of its centre) stops there, with the train's centre at the platform's centre.
 *
 * <p><b>The timetable is a clock, not physics</b> ({@link TrainTimetable}): each set shuttles on ONE track, dwelling at
 * every platform with its doors open, reversing at the ends; its position is a function of the system clock (plus a
 * per-set phase from its track's id), so every peer runs the same trains with no message. The Main line carries a
 * set on each track, the other lines one; a freight siding none.
 *
 * <p><b>Cars exist only near the camera</b> ({@link #spawnDistance}): a 4-car EMU1 set (Tc + M + M + Tc turned), each
 * car an {@link AnimatableBody3D} placed every physics frame from its two bogie points on the track, so a character
 * standing on it rides it. Far away a train is only its clock position.
 *
 * <p><b>Level crossings</b> (踏切): the rail build writes {@code <network>.crossings.json} (each crossing and its signal
 * units). A crossing is CLOSED while a set is on it, running toward it within {@link #WARN_M}, or about to leave a
 * platform toward it; the traffic brain stops at it ({@link #stopDistance}, VehicleAIController.signalSpeedLimit), and
 * the units near the camera FLASH (alternating red lamps). Crossings with no plan file are found from the road lanes
 * that cross a track at its own height, with no lamps. {@link #enabled} off is the control: no trains, no closures.
 */
@Script(className = "TrainSystem")
public class TrainSystem extends Node3D {

    private static TrainSystem instance;

    public static TrainSystem get() { return instance; }

    /** The control knob: off is the world before trains ran. */
    @Visible public boolean enabled = true;
    /** Run the timetable on GAME time (physics frames) instead of the shared wall clock, for a headless probe. */
    @Visible public boolean gameClock = false;
    /** A set's cars are instanced within this of the camera (m), and freed past it + 150. */
    @Export public float spawnDistance = 650.0f;
    /** Crossing units within this of the camera flash (m). */
    @Export public float lampRadius = 220.0f;

    public static final double CAR_L = 20.0, BOGIE_HALF = 6.9, RAIL_H = 0.16;
    public static final int CARS = 4;
    public static final double SET_L = CARS * CAR_L;
    /** A station's centre within this of a track (plan) makes it one of the track's stops (a hub's lines share it). */
    public static final double STOP_REACH = 30.0;
    public static final double WARN_M = 150.0, OCCUPY_MARGIN = 10.0, PREWARN_S = 8.0;
    /** m of a crossing road's lane from the crossing to where a car holds (the rail band and the 4.5 m to its signal). */
    public static final double HOLD_BACK = 9.0;
    public static final double NOSE = 2.3, COMMITTED = 3.0;
    /** m/s^2 of sideways acceleration a train takes a curve at, and its top speed (m/s). */
    public static final double CURVE_ACCEL = 0.8, TOP_SPEED = 25.0;
    static final String TC = "res://assets/vehicles/trains/EMU1_Tc.glb", M = "res://assets/vehicles/trains/EMU1_M.glb";

    /** One track: a chain of rail lanes, world space. */
    static final class Track {
        String id, line;
        double[] x, y, z, cum, cap;                 // cap: the speed cap (m/s) at each point
        double[] at(double s) {
            int n = x.length;
            if (s <= 0) return new double[]{x[0], y[0], z[0]};
            if (s >= cum[n - 1]) return new double[]{x[n - 1], y[n - 1], z[n - 1]};
            int lo = 0, hi = n - 1;
            while (hi - lo > 1) { int m = (lo + hi) >>> 1; if (cum[m] <= s) lo = m; else hi = m; }
            double seg = cum[hi] - cum[lo], t = seg < 1e-9 ? 0 : (s - cum[lo]) / seg;
            return new double[]{x[lo] + (x[hi] - x[lo]) * t, y[lo] + (y[hi] - y[lo]) * t, z[lo] + (z[hi] - z[lo]) * t};
        }
        double length() { return cum[cum.length - 1]; }
        /** {arclength, plan distance} of the point of the track nearest (px, pz). */
        double[] project(double px, double pz) {
            double best = Double.MAX_VALUE, bs = 0;
            for (int i = 0; i + 1 < x.length; i++) {
                double dx = x[i + 1] - x[i], dz = z[i + 1] - z[i], L2 = dx * dx + dz * dz;
                double t = L2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((px - x[i]) * dx + (pz - z[i]) * dz) / L2));
                double qx = x[i] + dx * t - px, qz = z[i] + dz * t - pz, d = qx * qx + qz * qz;
                if (d < best) { best = d; bs = cum[i] + (cum[i + 1] - cum[i]) * t; }
            }
            return new double[]{bs, Math.sqrt(best)};
        }
    }

    /** One train set on one track. */
    static final class TrainSet {
        Track track;
        TrainTimetable tt;
        double phase;
        final List<AnimatableBody3D> cars = new ArrayList<>();
        TrainTimetable.State state;
    }

    /** One crossing of a road lane over a track. */
    static final class Crossing { Track track; double s; String lane; double laneS; Vector3 pos; }

    /** A 踏切 signal unit's two lamps. */
    static final class Unit { Vector3 pos, fwd; List<Crossing> crossings = new ArrayList<>(); MeshInstance3D[] lamp; }

    private final List<Track> tracks = new ArrayList<>();
    private final List<TrainSet> sets = new ArrayList<>();
    private final List<Crossing> crossings = new ArrayList<>();
    private final Map<String, List<Crossing>> byLane = new HashMap<>();
    private final List<Unit> units = new ArrayList<>();
    private String signature = "";
    private long sceneId = -1;
    private double loadTimer, lampTimer;
    private PackedScene tcScene, mScene;
    private StandardMaterial3D lampMat;

    @Register
    @Override
    public void _ready() {
        instance = this;
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        clear();
    }

    // ── the track, the stops, the sets ────────────────────────────────────────

    private void refresh() {
        ZoneManager zm = ZoneManager.get();
        if (zm == null) return;
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        long sid = scene != null ? scene.getInstanceId() : 0;
        Map<String, double[]> kits = new HashMap<>();          // lanekit path -> frame
        Set<String> prefixes = new HashSet<>();
        for (ZoneMarker m : zm.getMarkers()) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null) continue;
            String gp = m.zone.geometryPath;
            if (gp == null || !gp.contains("Rail_")) continue;
            String path = RoadMap.lanekitPathFor(gp);
            if (path == null || !FileAccess.fileExists(path)) continue;
            kits.putIfAbsent(path, frame(m.zone.geometryFrame(m)));
            String file = gp.substring(gp.lastIndexOf('/') + 1);
            String stem = file.contains(".") ? file.substring(0, file.lastIndexOf('.')) : file;
            String suffix = "_" + m.zone.zoneId;
            if (stem.endsWith(suffix)) prefixes.add(stem.substring(0, stem.length() - suffix.length()));
        }
        StringBuilder sig = new StringBuilder();
        kits.keySet().stream().sorted().forEach(k -> sig.append(k).append('|'));
        if (sid == sceneId && sig.toString().equals(signature)) return;
        sceneId = sid;
        signature = sig.toString();
        clear();
        if (kits.isEmpty()) return;
        loadTracks(kits);
        List<double[]> stations = loadStations(prefixes);
        buildSets(stations);
        findCrossings(prefixes, kits);
        GD.print("TrainSystem: " + tracks.size() + " track(s), " + sets.size() + " set(s), " + crossings.size()
                + " crossing lane(s), " + units.size() + " signal unit(s)");
    }

    private static double[] frame(Transform3D t) {
        Basis b = t.getBasis();
        Vector3 bx = b.getX(), by = b.getY(), bz = b.getZ(), o = t.getOrigin();
        return new double[]{bx.getX(), by.getX(), bz.getX(), bx.getY(), by.getY(), bz.getY(),
                            bx.getZ(), by.getZ(), bz.getZ(), o.getX(), o.getY(), o.getZ()};
    }

    private static double[] xf(double[] f, double px, double py, double pz) {
        return new double[]{f[0] * px + f[1] * py + f[2] * pz + f[9], f[3] * px + f[4] * py + f[5] * pz + f[10],
                            f[6] * px + f[7] * py + f[8] * pz + f[11]};
    }

    private static double num(Object o, double d) { return o instanceof Number n ? n.doubleValue() : d; }

    private static final class RailLane { String id, road; double[][] pts; double speed; List<String> next = new ArrayList<>(); }

    @SuppressWarnings("unchecked")
    private void loadTracks(Map<String, double[]> kits) {
        Map<String, RailLane> lanes = new HashMap<>();
        for (Map.Entry<String, double[]> e : kits.entrySet()) {
            Object doc;
            try {
                doc = MiniJson.parse(FileAccess.getFileAsString(e.getKey()));
            } catch (IllegalArgumentException ex) {
                GD.printErr("TrainSystem: " + e.getKey() + ": " + ex.getMessage());
                continue;
            }
            if (!(doc instanceof Map<?, ?> m) || !(m.get("lanes") instanceof List<?> arr)) continue;
            for (Object o : arr) {
                if (!(o instanceof Map<?, ?> d) || !"rail".equals(String.valueOf(d.get("road_class")))) continue;
                if (!(d.get("points") instanceof List<?> pts) || pts.size() < 2) continue;
                RailLane l = new RailLane();
                l.id = String.valueOf(d.get("id"));
                l.road = String.valueOf(d.get("road_name"));
                l.speed = num(d.get("speed_limit"), 80.0) / 3.6;
                l.pts = new double[pts.size()][];
                int k = 0;
                for (Object p : pts) {
                    List<Object> v = (List<Object>) p;
                    l.pts[k++] = xf(e.getValue(), num(v.get(0), 0), num(v.get(1), 0), num(v.get(2), 0));
                }
                if (d.get("next") instanceof List<?> nl) for (Object s : nl) l.next.add(String.valueOf(s));
                lanes.put(l.id, l);
            }
        }
        Set<String> hasPred = new HashSet<>();
        for (RailLane l : lanes.values()) for (String n : l.next) if (lanes.containsKey(n)) hasPred.add(n);
        List<String> heads = new ArrayList<>();
        for (String id : lanes.keySet()) if (!hasPred.contains(id)) heads.add(id);
        heads.sort(String::compareTo);
        Set<String> used = new HashSet<>();
        for (String h : heads) {
            List<double[]> pts = new ArrayList<>();
            List<Double> caps = new ArrayList<>();
            String cur = h;
            String road = lanes.get(h).road;
            while (cur != null && lanes.containsKey(cur) && used.add(cur)) {
                RailLane l = lanes.get(cur);
                for (double[] p : l.pts) {
                    if (!pts.isEmpty()) {
                        double[] q = pts.get(pts.size() - 1);
                        if (Math.abs(q[0] - p[0]) + Math.abs(q[2] - p[2]) < 0.5) continue;
                    }
                    pts.add(p);
                    caps.add(l.speed);
                }
                cur = l.next.isEmpty() ? null : l.next.get(0);
            }
            if (pts.size() < 2) continue;
            Track t = new Track();
            t.id = h;
            t.line = road.split("__")[0];
            int n = pts.size();
            t.x = new double[n]; t.y = new double[n]; t.z = new double[n]; t.cum = new double[n]; t.cap = new double[n];
            for (int i = 0; i < n; i++) {
                t.x[i] = pts.get(i)[0]; t.y[i] = pts.get(i)[1]; t.z[i] = pts.get(i)[2]; t.cap[i] = caps.get(i);
                if (i > 0) {
                    double dx = t.x[i] - t.x[i - 1], dy = t.y[i] - t.y[i - 1], dz = t.z[i] - t.z[i - 1];
                    t.cum[i] = t.cum[i - 1] + Math.sqrt(dx * dx + dy * dy + dz * dz);
                }
            }
            // a curve's comfort cap: sqrt(a R), R the circumradius over points ~20 m either side
            for (int i = 0; i < n; i++) {
                double s = t.cum[i];
                double[] a = t.at(s - 20.0), b = t.at(s + 20.0), c = {t.x[i], t.y[i], t.z[i]};
                double r = circumradius(a, c, b);
                t.cap[i] = Math.min(Math.min(t.cap[i], TOP_SPEED), Math.sqrt(CURVE_ACCEL * r));
            }
            tracks.add(t);
        }
    }

    private static double circumradius(double[] a, double[] b, double[] c) {
        double ab = Math.hypot(b[0] - a[0], b[2] - a[2]), bc = Math.hypot(c[0] - b[0], c[2] - b[2]);
        double ca = Math.hypot(a[0] - c[0], a[2] - c[2]);
        double cross = Math.abs((b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]));
        if (cross < 1e-6) return 1e9;
        return ab * bc * ca / (2.0 * cross);
    }

    /** Every station's platform centre (Godot x, z). */
    @SuppressWarnings("unchecked")
    private List<double[]> loadStations(Set<String> prefixes) {
        List<double[]> out = new ArrayList<>();
        String reserve = "res://assets/world_source/buildings/IslandRailReserve.json";
        String debug = "res://assets/world_source/debug_world_layout.json";
        boolean island = prefixes.stream().anyMatch(p -> p.contains("IslandRail"));
        try {
            if (island && FileAccess.fileExists(reserve)) {
                Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(reserve));
                for (Object o : (List<Object>) d.get("boxes")) {
                    Map<String, Object> b = (Map<String, Object>) o;
                    if (!String.valueOf(b.get("id")).startsWith("station:")) continue;
                    out.add(new double[]{num(b.get("x"), 0), -num(b.get("y"), 0)});      // record (x, y) -> Godot
                }
            } else if (FileAccess.fileExists(debug)) {
                Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(debug));
                if (d.get("stations") instanceof List<?> st) {
                    for (Object o : st) {
                        List<Object> p = (List<Object>) ((Map<String, Object>) o).get("pos");
                        out.add(new double[]{num(p.get(0), 0), num(p.get(2), 0)});
                    }
                }
            }
        } catch (RuntimeException e) {
            GD.printErr("TrainSystem: stations: " + e.getMessage());
        }
        return out;
    }

    private static boolean carriesSet(Track t, List<Track> all) {
        String ln = t.line.toLowerCase();
        if (ln.contains("freight") || ln.contains("siding") || ln.contains("depot")) return false;
        if (ln.contains("main")) return true;                  // the Main line: a set on each track
        // the other lines: one set, on the track whose id sorts first
        return all.stream().filter(o -> o.line.equals(t.line)).map(o -> o.id).sorted().findFirst()
                .map(id -> id.equals(t.id)).orElse(false);
    }

    private void buildSets(List<double[]> stations) {
        double half = SET_L / 2.0;
        for (Track t : tracks) {
            if (!carriesSet(t, tracks) || t.length() < SET_L + 20.0) continue;
            List<Double> stops = new ArrayList<>();
            for (double[] st : stations) {
                double[] pr = t.project(st[0], st[1]);
                if (pr[1] > STOP_REACH) continue;
                double s = Math.max(half + 2.0, Math.min(t.length() - half - 2.0, pr[0]));
                if (stops.stream().noneMatch(v -> Math.abs(v - s) < 40.0)) stops.add(s);
            }
            stops.sort(Double::compareTo);
            if (stops.size() < 2) {
                // a track with fewer than two platforms still runs: end to end, its buffer stops the terminals
                stops.clear();
                stops.add(half + 2.0);
                stops.add(t.length() - half - 2.0);
            }
            double[] sa = stops.stream().mapToDouble(Double::doubleValue).toArray();
            double[] caps = new double[sa.length - 1];
            for (int i = 0; i < caps.length; i++) {
                double c = TOP_SPEED;
                for (int k = 0; k < t.cum.length; k++) {
                    if (t.cum[k] >= sa[i] - half && t.cum[k] <= sa[i + 1] + half) c = Math.min(c, t.cap[k]);
                }
                caps[i] = Math.max(4.0, c);
            }
            TrainSet set = new TrainSet();
            set.track = t;
            set.tt = new TrainTimetable(sa, caps);
            CRC32 crc = new CRC32();
            crc.update(t.id.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            set.phase = (crc.getValue() % 100000L) / 100000.0 * set.tt.period();
            sets.add(set);
        }
    }

    // ── level crossings ──────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private void findCrossings(Set<String> prefixes, Map<String, double[]> kits) {
        // the build's plan, where there is one: crossings and their signal units
        double[] frameOf = kits.values().iterator().next();
        for (String p : prefixes) {
            String path = "res://assets/world_source/pieces/" + p + ".crossings.json";
            if (!FileAccess.fileExists(path)) continue;
            try {
                Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(path));
                for (Object po : ((Map<String, Object>) d.get("pieces")).values()) {
                    for (Object uo : (List<Object>) ((Map<String, Object>) po).get("units")) {
                        Map<String, Object> u = (Map<String, Object>) uo;
                        List<Object> pp = (List<Object>) u.get("pos"), ff = (List<Object>) u.get("fwd");
                        double[] w = xf(frameOf, num(pp.get(0), 0), num(pp.get(1), 0), num(pp.get(2), 0));
                        Unit un = new Unit();
                        un.pos = new Vector3(w[0], w[1], w[2]);
                        un.fwd = new Vector3(num(ff.get(0), 0), 0, num(ff.get(2), 0)).normalized();
                        units.add(un);
                    }
                }
            } catch (RuntimeException e) {
                GD.printErr("TrainSystem: " + path + ": " + e.getMessage());
            }
        }
        // the road lanes crossing a track at its own height: where cars hold
        RoadGraph g = RoadMap.graph();
        if (g == null) return;
        for (Track t : tracks) {
            for (RoadGraph.Lane l : g.lanes()) {
                double[] b = l.boundsXZ();
                for (int i = 0; i + 1 < t.x.length; i++) {
                    double ax = t.x[i], az = t.z[i], bx = t.x[i + 1], bz = t.z[i + 1];
                    if (Math.max(ax, bx) < b[0] || Math.min(ax, bx) > b[2] || Math.max(az, bz) < b[1]
                            || Math.min(az, bz) > b[3]) continue;
                    for (int k = 0; k + 1 < l.x.length; k++) {
                        double[] hit = segHit(ax, az, bx, bz, l.x[k], l.z[k], l.x[k + 1], l.z[k + 1]);
                        if (hit == null) continue;
                        double ty = t.y[i] + (t.y[i + 1] - t.y[i]) * hit[0];
                        double ly = l.y[k] + (l.y[k + 1] - l.y[k]) * hit[1];
                        if (Math.abs(ty - ly) > 1.5) continue;
                        Crossing c = new Crossing();
                        c.track = t;
                        c.s = t.cum[i] + (t.cum[i + 1] - t.cum[i]) * hit[0];
                        c.lane = l.id;
                        c.laneS = l.cum[k] + (l.cum[k + 1] - l.cum[k]) * hit[1];
                        c.pos = new Vector3(ax + (bx - ax) * hit[0], ty, az + (bz - az) * hit[0]);
                        crossings.add(c);
                        byLane.computeIfAbsent(c.lane, x -> new ArrayList<>()).add(c);
                    }
                }
            }
        }
        for (Unit u : units) {
            for (Crossing c : crossings) if (c.pos.distanceTo(u.pos) < 30.0) u.crossings.add(c);
        }
    }

    /** Parameters {t, u} where segment a-b meets segment c-d (plan), or null. */
    private static double[] segHit(double ax, double az, double bx, double bz, double cx, double cz, double dx, double dz) {
        double rx = bx - ax, rz = bz - az, sx = dx - cx, sz = dz - cz;
        double den = rx * sz - rz * sx;
        if (Math.abs(den) < 1e-9) return null;
        double t = ((cx - ax) * sz - (cz - az) * sx) / den;
        double u = ((cx - ax) * rz - (cz - az) * rx) / den;
        if (t < 0 || t > 1 || u < 0 || u > 1) return null;
        return new double[]{t, u};
    }

    private double now() {
        if (gameClock) {
            return godot.api.Engine.INSTANCE.getPhysicsFrames() / (double) Math.max(1,
                    godot.api.Engine.INSTANCE.getPhysicsTicksPerSecond());
        }
        return Time.INSTANCE.getUnixTimeFromSystem();
    }

    private boolean closed(Crossing c, double t) {
        if (!enabled) return false;
        for (TrainSet set : sets) {
            if (set.track != c.track) continue;
            if (set.tt.crossingClosed(c.s, t + set.phase, SET_L, WARN_M, OCCUPY_MARGIN, PREWARN_S)) return true;
        }
        return false;
    }

    /**
     * How far (m) a car on road lane {@code laneId}, {@code progress} m along it, must stop within (its NOSE at the
     * crossing's hold line), or -1 when it may go: no crossing ahead on this lane, or the crossing is open.
     */
    public double stopDistance(String laneId, double progress) {
        if (!enabled) return -1.0;
        List<Crossing> cs = byLane.get(laneId);
        if (cs == null) return -1.0;
        double t = now(), best = -1.0;
        for (Crossing c : cs) {
            double d = c.laneS - HOLD_BACK - progress - NOSE;
            if (d < -COMMITTED || !closed(c, t)) continue;
            if (best < 0 || d < best) best = Math.max(0.0, d);
        }
        return best;
    }

    // ── the cars and the lamps ───────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        loadTimer -= delta;
        if (loadTimer <= 0.0) {
            loadTimer = 2.0;
            refresh();
        }
        if (sets.isEmpty()) return;
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        Vector3 eye = cam != null && cam.isInsideTree() ? cam.getGlobalPosition() : null;
        double t = now();
        for (TrainSet set : sets) {
            set.state = set.tt.at(t + set.phase);
            double[] c = set.track.at(set.state.s());
            double d = eye == null ? 1e9 : Math.hypot(c[0] - eye.getX(), c[2] - eye.getZ());
            boolean want = enabled && d < spawnDistance;
            if (want && set.cars.isEmpty()) spawnCars(set);
            else if (!enabled || (!set.cars.isEmpty() && d > spawnDistance + 150.0)) freeCars(set);
            if (!set.cars.isEmpty()) placeCars(set);
        }
    }

    private void spawnCars(TrainSet set) {
        if (tcScene == null) {
            if (ResourceLoader.load(TC) instanceof PackedScene p) tcScene = p;
            if (ResourceLoader.load(M) instanceof PackedScene p) mScene = p;
        }
        for (int i = 0; i < CARS; i++) {
            AnimatableBody3D car = new AnimatableBody3D();
            car.setName(new StringName("Train_" + sets.indexOf(set) + "_" + i));
            car.setSyncToPhysics(true);
            car.setCollisionLayer(CollisionLayers.WORLD);
            car.setCollisionMask(0);
            CollisionShape3D cs = new CollisionShape3D();
            BoxShape3D b = new BoxShape3D();
            b.setSize(new Vector3(2.9, 3.35, CAR_L - 0.6));
            cs.setShape(b);
            cs.setPosition(new Vector3(0, 0.3 + 3.35 / 2.0, 0));
            car.addChild(cs);
            PackedScene ps = (i == 0 || i == CARS - 1) ? tcScene : mScene;
            if (ps != null && ps.instantiate() instanceof Node3D mesh) {
                if (i == CARS - 1) mesh.setRotation(new Vector3(0, Math.PI, 0));    // the rear cab faces back
                car.addChild(mesh);
            }
            addChild(car);
            set.cars.add(car);
        }
    }

    private void freeCars(TrainSet set) {
        for (AnimatableBody3D c : set.cars) if (GD.isInstanceValid(c)) c.queueFree();
        set.cars.clear();
    }

    private void placeCars(TrainSet set) {
        Track t = set.track;
        for (int i = 0; i < set.cars.size(); i++) {
            // car 0 at the OUT end (+s): its cab faces +s; the set keeps its orientation when it runs back
            double sc = set.state.s() + (1.5 - i) * CAR_L;
            double[] a = t.at(sc - BOGIE_HALF), b = t.at(sc + BOGIE_HALF);
            double fx = b[0] - a[0], fz = b[2] - a[2];
            Vector3 pos = new Vector3((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0 + RAIL_H, (a[2] + b[2]) / 2.0);
            Basis basis = new Basis(new Vector3(0, 1, 0), Math.atan2(-fx, -fz));
            set.cars.get(i).setGlobalTransform(new Transform3D(basis, pos));
        }
    }

    @Register
    @Override
    public void _process(double delta) {
        lampTimer -= delta;
        if (lampTimer > 0.0 || units.isEmpty()) return;
        lampTimer = 0.1;
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam == null || !cam.isInsideTree()) return;
        Vector3 eye = cam.getGlobalPosition();
        double t = now();
        boolean phaseA = ((long) Math.floor(t / 0.6)) % 2 == 0;       // ~50 flashes a minute each, alternating
        for (Unit u : units) {
            boolean near = enabled && u.pos.distanceTo(eye) < lampRadius;
            boolean on = false;
            if (near) for (Crossing c : u.crossings) if (closed(c, t)) { on = true; break; }
            if (!near || !on) {
                if (u.lamp != null) for (MeshInstance3D m : u.lamp) m.setVisible(false);
                continue;
            }
            if (u.lamp == null) u.lamp = buildLamps(u);
            u.lamp[0].setVisible(phaseA);
            u.lamp[1].setVisible(!phaseA);
        }
    }

    private MeshInstance3D[] buildLamps(Unit u) {
        if (lampMat == null) {
            lampMat = new StandardMaterial3D();
            lampMat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
            lampMat.setAlbedo(new Color(1.0, 0.12, 0.08, 1.0));
        }
        // the unit's piece -Z is along `fwd`; its two lamps (library_procedural.crossing_signal) stand at x -/+0.36,
        // 2.6 m up, 0.13 m in front of its +Z face -- facing the traffic
        Basis bs = new Basis(new Vector3(0, 1, 0), Math.atan2(-u.fwd.getX(), -u.fwd.getZ()));
        MeshInstance3D[] out = new MeshInstance3D[2];
        for (int k = 0; k < 2; k++) {
            MeshInstance3D m = new MeshInstance3D();
            SphereMesh sm = new SphereMesh();
            sm.setRadius(0.11f);
            sm.setHeight(0.22f);
            m.setMesh(sm);
            m.setMaterialOverride(lampMat);
            m.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
            addChild(m);
            m.setGlobalPosition(u.pos.plus(bs.times(new Vector3(k == 0 ? -0.36 : 0.36, 2.6, 0.15))));
            out[k] = m;
        }
        return out;
    }

    private void clear() {
        for (TrainSet s : sets) freeCars(s);
        for (Unit u : units) if (u.lamp != null) for (MeshInstance3D m : u.lamp) if (GD.isInstanceValid(m)) m.queueFree();
        sets.clear();
        tracks.clear();
        crossings.clear();
        byLane.clear();
        units.clear();
    }

    // ── probe readouts ───────────────────────────────────────────────────────

    @Register public int setCountNow() { return sets.size(); }
    @Register public int trackCountNow() { return tracks.size(); }
    @Register public int crossingCountNow() { return crossings.size(); }
    @Register public int unitCountNow() { return units.size(); }
    @Register public int carsNow() { int n = 0; for (TrainSet s : sets) n += s.cars.size(); return n; }

    /** Set {@code i} at game/system time {@code t}: [s, v, dwell 0/1, stop, x, y, z, track length, period]. */
    @Register
    public godot.core.PackedFloat64Array setStateAt(int i, double t) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= sets.size()) return out;
        TrainSet s = sets.get(i);
        TrainTimetable.State st = s.tt.at(t + s.phase);
        double[] p = s.track.at(st.s());
        for (double v : new double[]{st.s(), st.v(), st.dwell() ? 1 : 0, st.stop(), p[0], p[1], p[2],
                s.track.length(), s.tt.period()}) out.append(v);
        return out;
    }

    /** Set {@code i}'s stops (arclengths along its track). */
    @Register
    public godot.core.PackedFloat64Array setStopsNow(int i) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= sets.size()) return out;
        for (TrainTimetable.Leg l : sets.get(i).tt.legs()) if (l.dwell() && !containsVal(out, l.s0())) out.append(l.s0());
        return out;
    }

    private static boolean containsVal(godot.core.PackedFloat64Array a, double v) {
        for (int k = 0; k < a.getSize(); k++) if (Math.abs(a.get(k) - v) < 1e-6) return true;
        return false;
    }

    /** Crossing {@code i}: [track index of its set-carrying track or -1, s, x, y, z]. */
    @Register
    public godot.core.PackedFloat64Array crossingNow(int i) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= crossings.size()) return out;
        Crossing c = crossings.get(i);
        int si = -1;
        for (int k = 0; k < sets.size(); k++) if (sets.get(k).track == c.track) si = k;
        for (double v : new double[]{si, c.s, c.pos.getX(), c.pos.getY(), c.pos.getZ()}) out.append(v);
        return out;
    }

    /** Is crossing {@code i} closed at time {@code t}? */
    @Register public boolean crossingClosedAt(int i, double t) {
        return i >= 0 && i < crossings.size() && closed(crossings.get(i), t);
    }

    /** The set's track id (probe). */
    @Register public String setTrackNow(int i) { return i >= 0 && i < sets.size() ? sets.get(i).track.id : ""; }
}
