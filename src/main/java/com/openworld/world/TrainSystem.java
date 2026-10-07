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
 * per-set phase from its track's id), so every peer runs the same trains with no message. A double-track line is a
 * CIRCUIT (out on one track, back on the other, the change made mid-stop at the terminus) with 2 x {@link #setsPerWay}
 * sets; a lone track a SHUTTLE with one. (Before 2026-10-02: one set per track, shuttling both ways.) The Main line carries a
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
    /** The control knob for the doors: off, no door ever opens (the boarding probe's control). */
    @Visible public boolean doorsEnabled = true;
    /** Seconds added to the clock (a probe jumps the timetable to the moment it wants). */
    @Visible public double clockOffset = 0.0;
    /** Hold riders at their place in the new car for {@link #PIN_TICKS} physics steps after a terminus turn (the new
     *  cars' collision is in place only after the next physics sync). Off is the control. */
    @Visible public boolean pinRiders = true;
    static final int PIN_TICKS = 8;
    /** Print every hit (probe). */
    @Visible public boolean debugHits = false;
    /** Run the timetable on GAME time (physics frames) instead of the shared wall clock, for a headless probe. */
    @Visible public boolean gameClock = false;
    /** Probe-only: every level crossing reads OPEN (the 一時停止 rule is then measured on its own). */
    @Visible public boolean crossingsForcedOpen = false;
    /** A set's cars are instanced within this of the camera (m), and freed past it + 150. */
    @Export public float spawnDistance = 650.0f;
    /** Crossing units within this of the camera flash (m). */
    @Export public float lampRadius = 220.0f;
    /**
     * Sets per DIRECTION on a double-track line (user, 2026-10-02: "one train each way per line for now; more later as
     * part of the performance tuning"). A line's circuit carries twice this many, evenly spaced in time. A set costs
     * nothing far away (a clock position) and ~0.1 ms a physics step with its cars near the camera.
     */
    @Export public int setsPerWay = 1;

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
    static final String FACTS = "res://assets/vehicles/trains/EMU1.train.json";
    /** A set's health; bullets hit it at {@link #HIT_MULT}, blasts at {@link #BLAST_MULT}: a rocket or two per car. */
    public static final float SET_HP = 3000f, HIT_MULT = 0.15f, BLAST_MULT = 2.0f;
    /** A destroyed set comes back at the first platform it would reach this long after (s), and its wreck stays that
     *  long or until then. */
    public static final double RESPAWN_GAP = 45.0;
    /** s the doors take to open or shut; they shut this long before the train leaves. */
    public static final double DOOR_TIME = 1.4, DOOR_CLOSE_BEFORE = 3.5;
    /** Below this speed (m/s) a train pushes what it meets aside; above it, it hits. */
    public static final double HIT_SPEED = 2.0;
    /** Interior lights are lit within this of the camera (m). */
    public static final double LIGHT_RADIUS = 140.0;

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
        /** The set's id: its first track's id and its place among the sets sharing that circuit ("<track>#<k>"). */
        String id;
        /** The tracks it runs: one (a shuttle) or a line's two (a circuit: out on one, back on the other). */
        Track[] tracks;
        /** tracks[0], kept for the shuttle-era call sites (crossing plans, ids). */
        Track track;
        TrainTimetable tt;
        double phase;
        final List<Car> cars = new ArrayList<>();
        TrainTimetable.State state;
        /** The set's health, shared by its four cars (they are freed and rebuilt with the camera; this is not). */
        float hp = SET_HP;
        boolean invulnerable;
        /** Out of service between these two times (shared clock): destroyed, and not yet back at a platform. */
        double downAt = -1, backAt = -1;
        /** The dwell the doors are serving (its stop, -1 while running) -- a new dwell re-asks where the platform is. */
        int doorStop = -1;
        boolean doorDir;
        /** Per track, each stop's station (index into stationIds, -1 none). */
        int[][] stopStation = new int[0][];
        /** The track the cars were last placed on (a change is the terminus swap). */
        int lastTrack = -1;
        Track trackNow() { return tracks[state != null ? state.track() : 0]; }
        int trackIndex(Track t) {
            for (int i = 0; i < tracks.length; i++) if (tracks[i] == t) return i;
            return -1;
        }
        final Map<Long, Double> hitAt = new HashMap<>();
        boolean outOfService(double t) { return backAt > 0 && t < backAt; }
    }

    /** One car's door (both leaves) on a spawned car. */
    static final class Door {
        CollisionShape3D shape;
        final List<Node3D> leaves = new ArrayList<>();
        final List<Vector3> closed = new ArrayList<>();
        final List<Vector3> slide = new ArrayList<>();
        Vector3 centre;          // the doorway's centre, car frame
        Vector3 size;
        int side;                // +1 / -1 across the car, car frame
        boolean platform;        // a platform stands at this door (asked at each dwell)
        double open;             // 0 shut .. 1 open
    }

    /** One spawned car. */
    static final class Car {
        AnimatableBody3D body;
        boolean flipped;
        final List<Door> doors = new ArrayList<>();
        final List<godot.api.OmniLight3D> lights = new ArrayList<>();
        List<godot.api.Label3D> screens = new ArrayList<>();
        String screenText = "";
        com.openworld.character.Health health;
    }

    /** A destroyed set's cars, left standing burnt where they died until the set comes back. */
    static final class Wreck { final List<AnimatableBody3D> bodies = new ArrayList<>(); double until; }

    /** A car's layout, from EMU1.train.json (make_train.py writes it off the .blend). */
    static final class CarProto {
        final List<double[]> cols = new ArrayList<>();
        final List<String[]> doorNodes = new ArrayList<>();
        final List<double[][]> doorSlides = new ArrayList<>();
        final List<double[]> doorBoxes = new ArrayList<>();
        final List<Integer> doorSides = new ArrayList<>();
        final List<double[]> lights = new ArrayList<>();
    }

    /** One crossing of a road lane over a track. */
    static final class Crossing { Track track; double s; String lane; double laneS; Vector3 pos; }

    /** A 踏切 signal unit's two lamps. */
    static final class Unit { Vector3 pos, fwd; List<Crossing> crossings = new ArrayList<>(); MeshInstance3D[] lamp;
        BreakableProps props; int poleIndex = -1; }

    private final List<Track> tracks = new ArrayList<>();
    /** The stations' ids (the rail reserve's / DebugWorld's), the names StationNames.json displays. */
    private final List<String> stationIds = new ArrayList<>();
    private final List<double[]> stationPos = new ArrayList<>();
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
        stationPos.clear();
        stationPos.addAll(stations);
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

    /** Every station's platform centre (Godot x, z) and its index in {@link #stationIds}. */
    @SuppressWarnings("unchecked")
    private List<double[]> loadStations(Set<String> prefixes) {
        List<double[]> out = new ArrayList<>();
        stationIds.clear();
        String reserve = "res://assets/world_source/buildings/IslandRailReserve.json";
        String debug = "res://assets/world_source/debug_world_layout.json";
        boolean island = prefixes.stream().anyMatch(p -> p.contains("IslandRail"));
        try {
            if (island && FileAccess.fileExists(reserve)) {
                Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(reserve));
                for (Object o : (List<Object>) d.get("boxes")) {
                    Map<String, Object> b = (Map<String, Object>) o;
                    String id = String.valueOf(b.get("id"));
                    if (!id.startsWith("station:")) continue;
                    stationIds.add(id.substring("station:".length()));
                    out.add(new double[]{num(b.get("x"), 0), -num(b.get("y"), 0), stationIds.size() - 1});
                    // record (x, y) -> Godot
                }
            } else if (FileAccess.fileExists(debug)) {
                Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(debug));
                if (d.get("stations") instanceof List<?> st) {
                    for (Object o : st) {
                        Map<String, Object> so = (Map<String, Object>) o;
                        List<Object> p = (List<Object>) so.get("pos");
                        stationIds.add(String.valueOf(so.get("name")));
                        out.add(new double[]{num(p.get(0), 0), num(p.get(2), 0), stationIds.size() - 1});
                    }
                }
            }
        } catch (RuntimeException e) {
            GD.printErr("TrainSystem: stations: " + e.getMessage());
        }
        return out;
    }

    private static boolean runsTrains(Track t) {
        String ln = t.line.toLowerCase();
        return !(ln.contains("freight") || ln.contains("siding") || ln.contains("depot"));
    }

    /** A track's stops: {s, station index} ascending, its buffer stops when it passes fewer than two stations. */
    private List<double[]> stopsOf(Track t, List<double[]> stations) {
        double half = SET_L / 2.0;
        List<double[]> stops = new ArrayList<>();
        for (double[] st : stations) {
            double[] pr = t.project(st[0], st[1]);
            if (pr[1] > STOP_REACH) continue;
            double s = Math.max(half + 2.0, Math.min(t.length() - half - 2.0, pr[0]));
            if (stops.stream().noneMatch(v -> Math.abs(v[0] - s) < 40.0)) stops.add(new double[]{s, st[2]});
        }
        stops.sort((x, y) -> Double.compare(x[0], y[0]));
        if (stops.size() < 2) {
            stops.clear();
            stops.add(new double[]{half + 2.0, -1});
            stops.add(new double[]{t.length() - half - 2.0, -1});
        }
        return stops;
    }

    private double[] capsOf(Track t, double[] sa) {
        double half = SET_L / 2.0;
        double[] caps = new double[sa.length - 1];
        for (int i = 0; i < caps.length; i++) {
            double c = TOP_SPEED;
            for (int k = 0; k < t.cum.length; k++) {
                if (t.cum[k] >= sa[i] - half && t.cum[k] <= sa[i + 1] + half) c = Math.min(c, t.cap[k]);
            }
            caps[i] = Math.max(4.0, c);
        }
        return caps;
    }

    /** The track that runs back along {@code a}: its start near a's end and its end near a's start. */
    private Track partnerOf(Track a, Set<Track> used) {
        Track best = null;
        double bd = 60.0;
        for (Track b : tracks) {
            if (b == a || used.contains(b) || !runsTrains(b) || b.length() < SET_L + 20.0) continue;
            int na = a.x.length - 1, nb = b.x.length - 1;
            double d1 = Math.hypot(b.x[0] - a.x[na], b.z[0] - a.z[na]);
            double d2 = Math.hypot(b.x[nb] - a.x[0], b.z[nb] - a.z[0]);
            double d = Math.max(d1, d2);
            if (d < bd) { bd = d; best = b; }
        }
        return best;
    }

    /**
     * The sets. A double-track line (a track and the one running back along it, ends within 60 m) is a CIRCUIT: out
     * on one track, back on the other, the change made in the middle of the terminus stop. It carries
     * 2 x {@link #setsPerWay} sets evenly spaced in time (they never meet). A lone track is a SHUTTLE with one set.
     */
    private void buildSets(List<double[]> stations) {
        Set<Track> used = new HashSet<>();
        List<Track> order = new ArrayList<>(tracks);
        order.sort((x, y) -> x.id.compareTo(y.id));
        for (Track a : order) {
            if (used.contains(a) || !runsTrains(a) || a.length() < SET_L + 20.0) continue;
            used.add(a);
            Track b = partnerOf(a, used);
            Track[] ts;
            TrainTimetable tt;
            int[][] stopStation;
            if (b != null) {
                used.add(b);
                ts = new Track[]{a, b};
                List<double[]> sa = stopsOf(a, stations), sb = stopsOf(b, stations);
                double[][] st = {sa.stream().mapToDouble(v -> v[0]).toArray(), sb.stream().mapToDouble(v -> v[0]).toArray()};
                tt = TrainTimetable.circuit(st, new double[][]{capsOf(a, st[0]), capsOf(b, st[1])});
                stopStation = new int[][]{sa.stream().mapToInt(v -> (int) v[1]).toArray(),
                        sb.stream().mapToInt(v -> (int) v[1]).toArray()};
            } else {
                ts = new Track[]{a};
                List<double[]> sa = stopsOf(a, stations);
                double[] st = sa.stream().mapToDouble(v -> v[0]).toArray();
                tt = new TrainTimetable(st, capsOf(a, st));
                stopStation = new int[][]{sa.stream().mapToInt(v -> (int) v[1]).toArray()};
            }
            int n = b != null ? 2 * Math.max(1, setsPerWay) : 1;
            CRC32 crc = new CRC32();
            crc.update(a.id.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            double base = (crc.getValue() % 100000L) / 100000.0 * tt.period();
            for (int k = 0; k < n; k++) {
                TrainSet set = new TrainSet();
                set.id = a.id + "#" + k;
                set.tracks = ts;
                set.track = a;
                set.tt = tt;
                set.stopStation = stopStation;
                set.phase = base + k * tt.period() / n;
                sets.add(set);
            }
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

    /**
     * The timetable's clock. It must advance by exactly one physics step per step: on the raw wall clock, two steps
     * run in one render frame (a busy scene) read nearly the same time, so the train moved 0 and then double -- a rider
     * felt every frame as a jolt (user, 2026-10-02; tools/godot/probe_train_smooth.gd measured 299 of 300 steps off
     * with 25 ms frames). So the clock is a STEP clock ANCHORED to the shared wall clock: it starts on the wall
     * clock, adds each physics delta, is eased toward the wall clock by {@link #CLOCK_EASE} of the difference per
     * second (peers still agree, to well under a second), and snaps to it past {@link #CLOCK_SNAP} (a pause, a clock
     * change, a debugger stop).
     */
    private double now() {
        if (gameClock) {
            return clockOffset + godot.api.Engine.INSTANCE.getPhysicsFrames() / (double) Math.max(1,
                    godot.api.Engine.INSTANCE.getPhysicsTicksPerSecond());
        }
        if (Double.isNaN(stepClock)) stepClock = wall();
        return clockOffset + stepClock;
    }

    private double wall() { return Time.INSTANCE.getUnixTimeFromSystem(); }

    /** Advance the step clock by one physics step (from _physicsProcess, before anything reads it). */
    private void tickClock(double delta) {
        double w = wall();
        if (Double.isNaN(stepClock)) { stepClock = w; return; }
        stepClock += delta;
        double err = w - stepClock;
        if (Math.abs(err) > CLOCK_SNAP) stepClock = w;
        else stepClock += err * Math.min(1.0, CLOCK_EASE * delta);
    }

    private double stepClock = Double.NaN;
    /** s of disagreement with the wall clock past which the step clock snaps to it. */
    static final double CLOCK_SNAP = 20.0;
    /** Share of the disagreement taken out per second (0.2: a 0.1 s error is gone in ~10 s, at 2% of a step). */
    static final double CLOCK_EASE = 0.2;

    /** One hold line per 踏切, and a car past it held while it can still stop short of the train (off: a line per
     *  track and "3 m past the line is committed", the control for PLAN.md 0.16). */
    @Visible public boolean groupHold = true;
    private final java.util.Set<Crossing> forcedClosed = new java.util.HashSet<>();

    /** Probe: hold the crossing of road lane {@code lane} nearest lane position {@code laneS} closed (or release it). */
    @Register
    public boolean forceCrossingClosedNow(String lane, double laneS, boolean on) {
        Crossing best = null;
        for (Crossing c : byLane.getOrDefault(lane, List.of()))
            if (best == null || Math.abs(c.laneS - laneS) < Math.abs(best.laneS - laneS)) best = c;
        if (best == null) return false;
        if (on) forcedClosed.add(best); else forcedClosed.remove(best);
        return true;
    }

    private boolean closed(Crossing c, double t) {
        if (enabled && forcedClosed.contains(c)) return true;
        if (!enabled || crossingsForcedOpen) return false;
        for (TrainSet set : sets) {
            int ti = set.trackIndex(c.track);
            if (ti < 0 || set.outOfService(t)) continue;
            if (set.tt.crossingClosed(ti, c.s, t + set.phase, SET_L, WARN_M, OCCUPY_MARGIN, PREWARN_S)) return true;
        }
        return false;
    }

    /**
     * How far (m) a car on road lane {@code laneId}, {@code progress} m along it, must stop within (its NOSE at the
     * crossing's hold line), or -1 when it may go: no crossing ahead on this lane, or the crossing is open.
     */
    public double stopDistance(String laneId, double progress) { return stopDistance(laneId, progress, 0.0); }

    /**
     * As above for a car moving at {@code speed} m/s. A car past the hold line still stops (distance 0) while it can stop
     * before the train's envelope, {@link #LX_DANGER} from the 踏切's first track at {@link #LX_BRAKE}: only a car that
     * can no longer is let through. "3 m past the line" was the old test, and a car that crept 3 m on a closed crossing
     * was released 6 m short of the rails into the next train (PLAN.md 0.16).
     */
    public double stopDistance(String laneId, double progress, double speed) {
        if (!enabled) return -1.0;
        List<Crossing> cs = byLane.get(laneId);
        if (cs == null) return -1.0;
        double t = now(), best = -1.0, nose = progress + NOSE;
        for (Crossing c : cs) {
            // ONE hold line per 踏切: a closed track holds the car before the FIRST track of its group. A line per
            // track let a car creep up to the far track's line, 4 m past the real one (PLAN.md 0.16).
            double first = groupHold ? groupStart(cs, c.laneS) : c.laneS;
            if (first + CROSSING_GROUP < nose || !closed(c, t)) continue;   // well past it: not this car's business
            double room = first - LX_DANGER - nose;
            boolean committed = groupHold ? speed * speed / (2.0 * LX_BRAKE) > room
                    : first - HOLD_BACK - nose < -COMMITTED;
            if (committed) continue;
            double d = Math.max(0.0, first - HOLD_BACK - nose);
            if (best < 0 || d < best) best = d;
        }
        return best;
    }

    /** m from a 踏切's first track inside which a car is in the train's way (the EMU1's 1.49 m half width and 1 m),
     *  and the m/s^2 a car can stop at, which together decide whether a car past the hold line can still stop. */
    public static final double LX_DANGER = 2.5, LX_BRAKE = 6.0;

    /** The lane position of the first crossing of the 踏切 {@code laneS} belongs to (crossings chained within
     *  {@link #CROSSING_GROUP} of each other are one). */
    private static double groupStart(List<Crossing> cs, double laneS) {
        double first = laneS;
        for (boolean moved = true; moved; ) {
            moved = false;
            for (Crossing o : cs) {
                if (o.laneS < first && o.laneS >= first - CROSSING_GROUP) { first = o.laneS; moved = true; }
            }
        }
        return first;
    }

    /** Diagnostics (PLAN.md 0.16): the train clock and each crossing of {@code laneId} as "laneS:closed". */
    public String crossingStateFor(String laneId) {
        StringBuilder b = new StringBuilder(String.format("clock %.2f", now()));
        double t = now();
        for (Crossing c : byLane.getOrDefault(laneId, List.of()))
            b.append(String.format(" %.1f:%s", c.laneS, closed(c, t) ? "closed" : "open"));
        return b.toString();
    }

    /**
     * True when a car whose centre is {@code s} m along road lane {@code laneId} would stand on a 踏切 or between its
     * hold line and its far side, open or closed: a spawn slot there puts a car where a train can hit it before its
     * brain has run once (seen in the perf run: lane cho_0_R0, progress 0.0, state "?").
     */
    public boolean onCrossing(String laneId, double s) {
        if (!enabled) return false;
        List<Crossing> cs = byLane.get(laneId);
        if (cs == null) return false;
        for (Crossing c : cs) {
            double first = groupStart(cs, c.laneS), last = first;
            for (Crossing o : cs) if (o.laneS >= first && o.laneS <= first + CROSSING_GROUP) last = Math.max(last, o.laneS);
            if (s + NOSE > first - HOLD_BACK && s - NOSE < last + HOLD_BACK) return true;
        }
        return false;
    }

    /** Crossings of one lane closer than this along it are ONE 踏切 (a double track is two `Crossing`s 4 m apart). */
    public static final double CROSSING_GROUP = 25.0;

    /**
     * The next LEVEL CROSSING on road lane {@code laneId} ahead of {@code progress}, open or closed, ignoring any whose
     * lane position is at or before {@code skipThroughS}: {@code {nose distance to its hold line, the lane position its
     * far side ends at (its last track + HOLD_BACK)}}, or null. What the traffic brain's 一時停止 asks
     * (Road Traffic Act art. 33: stop before every 踏切, enter only with room past it).
     */
    public double[] nextCrossing(String laneId, double progress, double skipThroughS) {
        if (!enabled) return null;
        List<Crossing> cs = byLane.get(laneId);
        if (cs == null) return null;
        double first = Double.MAX_VALUE;
        for (Crossing c : cs) {
            if (c.laneS <= skipThroughS) continue;
            if (c.laneS - HOLD_BACK - progress - NOSE < -COMMITTED) continue;
            first = Math.min(first, c.laneS);
        }
        if (first == Double.MAX_VALUE) return null;
        double last = first;
        for (Crossing c : cs) {
            if (c.laneS >= first && c.laneS <= first + CROSSING_GROUP) last = Math.max(last, c.laneS);
        }
        return new double[]{Math.max(0.0, first - HOLD_BACK - progress - NOSE), last + HOLD_BACK};
    }

    // ── the cars and the lamps ───────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        long t0us = Time.INSTANCE.getTicksUsec();
        try {
            step(delta);
        } finally {
            lastStepUs = Time.INSTANCE.getTicksUsec() - t0us;
        }
    }

    private long lastStepUs;

    /** Microseconds the last physics step of the train system took (probe readout). */
    @Register public long lastStepUsNow() { return lastStepUs; }

    private void step(double delta) {
        tickClock(delta);
        loadTimer -= delta;
        if (loadTimer <= 0.0) {
            loadTimer = 2.0;
            refresh();
        }
        double t = now();
        updateWrecks(t);
        if (sets.isEmpty()) return;
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        Vector3 eye = cam != null && cam.isInsideTree() ? cam.getGlobalPosition() : null;
        for (TrainSet set : sets) {
            set.state = set.tt.at(t + set.phase);
            if (set.outOfService(t)) {
                if (!set.cars.isEmpty()) freeCars(set);
                continue;
            }
            if (set.backAt > 0) {          // back in service at its platform
                set.backAt = set.downAt = -1;
                set.hp = SET_HP;
            }
            double[] c = set.trackNow().at(set.state.s());
            double d = eye == null ? 1e9 : Math.hypot(c[0] - eye.getX(), c[2] - eye.getZ());
            boolean want = enabled && d < spawnDistance;
            if (want && set.cars.isEmpty()) spawnCars(set);
            else if (!enabled || (!set.cars.isEmpty() && d > spawnDistance + 150.0)) freeCars(set);
            if (set.cars.isEmpty()) {
                set.lastTrack = set.state.track();
                continue;
            }
            if (set.lastTrack >= 0 && set.lastTrack != set.state.track()) swapTrack(set);
            set.lastTrack = set.state.track();
            placeCars(set);
            updateDoors(set, delta);
            updateLights(set, eye);
            readHealth(set, t);
            if (!set.cars.isEmpty()) hitAhead(set, delta, t);
        }
        if (!pins.isEmpty()) holdPins();
        displayTimer -= delta;
        if (displayTimer <= 0.0 && enabled) {
            displayTimer = 0.5;
            displays().updateBoards(eye, t);
            for (TrainSet set : sets) {
                if (set.cars.isEmpty()) continue;
                String text = displays().screenText(set, t);
                for (Car c : set.cars) {
                    boolean on = eye != null && GD.isInstanceValid(c.body)
                            && c.body.getGlobalPosition().distanceTo(eye) < TrainDisplays.SCREEN_RADIUS;
                    for (godot.api.Label3D l : c.screens) {
                        if (l.isVisible() != on) l.setVisible(on);
                        if (on && !text.equals(c.screenText)) l.setText(text);
                    }
                    if (on) c.screenText = text;
                }
            }
        }
    }

    // ── the cars: a shell you can walk into, doors, lights, health ────────────

    private CarProto tcProto, mProto;

    @SuppressWarnings("unchecked")
    private void loadProtos() {
        if (tcProto != null) return;
        tcProto = new CarProto();
        mProto = new CarProto();
        if (!FileAccess.fileExists(FACTS)) return;
        try {
            Map<String, Object> d = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(FACTS));
            Map<String, Object> cars = (Map<String, Object>) d.get("cars");
            for (String k : new String[]{"EMU1_Tc", "EMU1_M"}) {
                if (!(cars.get(k) instanceof Map<?, ?> cm)) continue;
                CarProto p = k.endsWith("Tc") ? tcProto : mProto;
                if (cm.get("colliders") instanceof List<?> cl) for (Object o : cl) p.cols.add(nums(o));
                if (cm.get("lights") instanceof List<?> ll) for (Object o : ll) p.lights.add(nums(o));
                if (cm.get("doors") instanceof List<?> dl) {
                    for (Object o : dl) {
                        Map<String, Object> dm = (Map<String, Object>) o;
                        p.doorBoxes.add(nums(dm.get("box")));
                        p.doorSides.add((int) num(dm.get("side"), 1));
                        List<Object> lv = (List<Object>) dm.get("leaves");
                        String[] names = new String[lv.size()];
                        double[][] sl = new double[lv.size()][];
                        for (int i = 0; i < lv.size(); i++) {
                            Map<String, Object> l = (Map<String, Object>) lv.get(i);
                            names[i] = String.valueOf(l.get("node"));
                            sl[i] = nums(l.get("slide"));
                        }
                        p.doorNodes.add(names);
                        p.doorSlides.add(sl);
                    }
                }
            }
        } catch (RuntimeException e) {
            GD.printErr("TrainSystem: " + FACTS + ": " + e.getMessage());
        }
    }

    private static double[] nums(Object o) {
        List<?> l = (List<?>) o;
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) out[i] = num(l.get(i), 0);
        return out;
    }

    private static CollisionShape3D boxShape(double[] b, boolean flip) {
        CollisionShape3D cs = new CollisionShape3D();
        BoxShape3D bs = new BoxShape3D();
        bs.setSize(new Vector3(b[3], b[4], b[5]));
        cs.setShape(bs);
        cs.setPosition(new Vector3(flip ? -b[0] : b[0], b[1], flip ? -b[2] : b[2]));
        return cs;
    }

    private void spawnCars(TrainSet set) {
        if (tcScene == null) {
            if (ResourceLoader.load(TC) instanceof PackedScene p) tcScene = p;
            if (ResourceLoader.load(M) instanceof PackedScene p) mScene = p;
        }
        loadProtos();
        int si = sets.indexOf(set);
        for (int i = 0; i < CARS; i++) {
            boolean tc = i == 0 || i == CARS - 1;
            boolean flip = i == CARS - 1;                    // the rear cab faces back
            CarProto proto = tc ? tcProto : mProto;
            Car car = new Car();
            car.flipped = flip;
            AnimatableBody3D body = new AnimatableBody3D();
            body.setName(new StringName("Train_" + si + "_" + i));
            body.setSyncToPhysics(true);
            body.setCollisionLayer(CollisionLayers.WORLD);
            body.setCollisionMask(0);
            body.addToGroup(new StringName("train_car"));
            car.body = body;
            if (proto.cols.isEmpty()) {
                // no facts file: the old solid box
                body.addChild(boxShape(new double[]{0, 0.3 + 3.35 / 2.0, 0, 2.9, 3.35, CAR_L - 0.6}, false));
            }
            for (double[] b : proto.cols) body.addChild(boxShape(b, flip));
            Node3D mesh = null;
            PackedScene ps = tc ? tcScene : mScene;
            if (ps != null && ps.instantiate() instanceof Node3D m) {
                mesh = m;
                mesh.setName(new StringName("Model"));
                if (flip) mesh.setRotation(new Vector3(0, Math.PI, 0));
                body.addChild(mesh);
            }
            for (int k = 0; k < proto.doorBoxes.size(); k++) {
                Door dr = new Door();
                double[] b = proto.doorBoxes.get(k);
                dr.shape = boxShape(b, flip);
                body.addChild(dr.shape);
                dr.centre = dr.shape.getPosition();
                dr.size = new Vector3(b[3], b[4], b[5]);
                dr.side = (flip ? -1 : 1) * proto.doorSides.get(k);
                String[] names = proto.doorNodes.get(k);
                for (int n = 0; n < names.length; n++) {
                    if (mesh == null || !(mesh.findChild(names[n], true, false) instanceof Node3D leaf)) continue;
                    dr.leaves.add(leaf);
                    dr.closed.add(leaf.getPosition());
                    double[] sl = proto.doorSlides.get(k)[n];
                    dr.slide.add(new Vector3(sl[0], sl[1], sl[2]));
                }
                car.doors.add(dr);
            }
            List<double[]> centres = new ArrayList<>();
            for (Door dr : car.doors) centres.add(new double[]{dr.side, dr.centre.getZ()});
            car.screens = TrainDisplays.buildScreens(body, centres);
            for (double[] lp : proto.lights) {
                godot.api.OmniLight3D l = new godot.api.OmniLight3D();
                l.setPosition(new Vector3(flip ? -lp[0] : lp[0], lp[1], flip ? -lp[2] : lp[2]));
                l.setParam(godot.api.Light3D.Param.RANGE, 9.0f);
                l.setParam(godot.api.Light3D.Param.ENERGY, 0.9f);
                l.setColor(new Color(1.0, 0.97, 0.90, 1.0));
                l.setShadow(false);
                l.setVisible(false);
                body.addChild(l);
                car.lights.add(l);
            }
            com.openworld.character.Health h = new com.openworld.character.Health();
            h.setName(new StringName("Health"));
            h.maxHealth = SET_HP;
            h.hitDamageMultiplier = HIT_MULT;
            h.explosionDamageMultiplier = BLAST_MULT;
            h.bladeDamageMultiplier = 0.1f;      // San Andreas style (user 2026-10-07): melee hurts a vehicle, slowly
            h.bluntDamageMultiplier = 0.1f;
            h.displayName = "Train";
            h.invulnerable = set.invulnerable;
            body.addChild(h);
            car.health = h;
            addChild(body);
            h.applyReplicatedHealth(set.hp);
            set.cars.add(car);
        }
        set.doorStop = -1;
    }

    private void freeCars(TrainSet set) {
        for (Car c : set.cars) if (GD.isInstanceValid(c.body)) c.body.queueFree();
        set.cars.clear();
    }

    /**
     * The cheap turn at a circuit's terminus (user decision, 2026-10-02): halfway through the stop the set leaves the
     * track it arrived on and stands on the one it leaves on. Its cars are rebuilt there, and anyone aboard moves WITH
     * their car: car i becomes car 3 - i, which stands at the same end of the platform and faces the same way, so a
     * rider moves only the few metres across to the other track.
     */
    private void swapTrack(TrainSet set) {
        List<Transform3D> before = new ArrayList<>();
        for (Car c : set.cars) before.add(visualFrame(c));
        List<Object[]> riders = new ArrayList<>();          // {character, car index, local position}
        for (Node n : getTree().getNodesInGroup(new StringName("characters"))) {
            if (!(n instanceof com.openworld.character.Character ch) || ch.currentVehicleNode != null) continue;
            for (int i = 0; i < before.size(); i++) {
                Vector3 l = before.get(i).affineInverse().times(ch.getGlobalPosition());
                // aboard: inside the walls, in a doorway (to the door's outer face) or on the gangway to the next car
                if (Math.abs(l.getX()) < 1.6 && l.getY() > 0.6 && l.getY() < 3.6 && Math.abs(l.getZ()) < CAR_L / 2 + 0.3) {
                    riders.add(new Object[]{ch, i, l});
                    break;
                }
            }
        }
        freeCars(set);
        spawnCars(set);
        placeCars(set);
        // the platform-side doors of the new cars stand OPEN at once: rebuilt shut, a rider in a doorway overlapped
        // the shut door's collider and was pushed out of the train
        set.doorStop = set.state.stop();
        for (int i = 0; i < set.cars.size(); i++) {
            Car c = set.cars.get(i);
            Transform3D pose = carPose(set, i);
            for (Door d : c.doors) {
                d.platform = platformBeside(pose, d);
                if (d.platform && doorsEnabled && set.state.untilDepart() > DOOR_CLOSE_BEFORE) {
                    d.open = 1.0;
                    d.shape.setDisabled(true);
                    for (int k = 0; k < d.leaves.size(); k++) {
                        Node3D leaf = d.leaves.get(k);
                        if (GD.isInstanceValid(leaf)) leaf.setPosition(d.closed.get(k).plus(d.slide.get(k)));
                    }
                }
            }
        }
        for (Object[] r : riders) {
            int j = set.cars.size() - 1 - (int) r[1];
            if (j < 0 || j >= set.cars.size()) continue;
            com.openworld.character.Character ch = (com.openworld.character.Character) r[0];
            // the new car's pose from the track: a body just built and moved reports its new transform only after the
            // next physics sync (sync_to_physics)
            Transform3D nf = visualFrame(carPose(set, j), set.cars.get(j).flipped);
            Vector3 lp = (Vector3) r[2];
            // the set runs the other way now: a car whose frame turned (a middle car) mirrors the rider's place in it,
            // so they stay where they stood, only moved across to the other track
            Vector3 oldFwd = before.get((int) r[1]).getBasis().getZ(), newFwd = nf.getBasis().getZ();
            if (oldFwd.dot(newFwd) < 0) lp = new Vector3(-lp.getX(), lp.getY(), -lp.getZ());
            Vector3 to = nf.times(lp);
            if (debugHits) GD.print("TrainSystem: swap carries " + ch.getName() + " from car " + r[1] + " " + ch.getGlobalPosition()
                    + " to car " + j + " " + to + " (car at " + set.cars.get(j).body.getGlobalPosition() + ")");
            ch.setGlobalPosition(to);
            ch.setVelocity(new Vector3(0, 0, 0));
            if (pinRiders) pins.add(new Pin(ch, set, j, nf.affineInverse().times(to), PIN_TICKS));
        }
        swaps++;
    }

    private int swaps;

    /** A rider held at a place in a car for a few physics steps after the turn. */
    record Pin(com.openworld.character.Character ch, TrainSet set, int car, Vector3 local, int ticks) { }

    private final List<Pin> pins = new ArrayList<>();

    /** Hold each pinned rider at its place in its car (the car's pose from the track) with no velocity. */
    private void holdPins() {
        for (int i = pins.size() - 1; i >= 0; i--) {
            Pin p = pins.get(i);
            if (!GD.isInstanceValid(p.ch()) || p.ticks() <= 0 || p.car() >= p.set().cars.size()) {
                pins.remove(i);
                continue;
            }
            Car c = p.set().cars.get(p.car());
            p.ch().setGlobalPosition(visualFrame(carPose(p.set(), p.car()), c.flipped).times(p.local()));
            p.ch().setVelocity(new Vector3(0, 0, 0));
            pins.set(i, new Pin(p.ch(), p.set(), p.car(), p.local(), p.ticks() - 1));
        }
    }

    /** A car's frame as its MODEL faces (the rear cab car's model is turned 180 deg in its body). */
    private static Transform3D visualFrame(Car c) { return visualFrame(c.body.getGlobalTransform(), c.flipped); }

    private static Transform3D visualFrame(Transform3D xf, boolean flipped) {
        if (!flipped) return xf;
        // times() MUTATES its receiver (godot-jvm): xf is always a fresh value here
        return xf.times(new Transform3D(new Basis(new Vector3(0, 1, 0), Math.PI), new Vector3(0, 0, 0)));
    }

    /** Where car {@code i} of the set stands now: its body's transform, from its two bogie points on the track. */
    private static Transform3D carPose(TrainSet set, int i) {
        Track t = set.trackNow();
        // car 0 at the +s end: its cab faces +s; the set keeps its orientation when it runs back
        double sc = set.state.s() + (1.5 - i) * CAR_L;
        double[] a = t.at(sc - BOGIE_HALF), b = t.at(sc + BOGIE_HALF);
        double fx = b[0] - a[0], fz = b[2] - a[2];
        Vector3 pos = new Vector3((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0 + RAIL_H, (a[2] + b[2]) / 2.0);
        return new Transform3D(new Basis(new Vector3(0, 1, 0), Math.atan2(-fx, -fz)), pos);
    }

    private void placeCars(TrainSet set) {
        for (int i = 0; i < set.cars.size(); i++) set.cars.get(i).body.setGlobalTransform(carPose(set, i));
    }

    /**
     * Doors: at a dwell, every door with a PLATFORM beside it opens (asked once per dwell with a ray down beside it, so
     * an island platform opens one side and a side platform the other, and a short platform only the doors it
     * reaches); they shut {@link #DOOR_CLOSE_BEFORE} s before the train leaves, held while someone stands in the
     * doorway until the last half second (the train keeps its timetable). An open door's collider is off.
     */
    private void updateDoors(TrainSet set, double delta) {
        TrainTimetable.State st = set.state;
        boolean dwell = st.dwell();
        if (dwell && set.doorStop != st.stop()) {
            set.doorStop = st.stop();
            // the pose from the track, not the body: a car just rebuilt (a terminus swap) reports its new transform only
            // after the next physics sync, and a ray from the old one found no platform for the whole stop
            for (int i = 0; i < set.cars.size(); i++) {
                Car c = set.cars.get(i);
                Transform3D pose = carPose(set, i);
                for (Door d : c.doors) d.platform = platformBeside(pose, d);
            }
        } else if (!dwell) {
            set.doorStop = -1;
        }
        double step = delta / DOOR_TIME;
        for (Car c : set.cars) {
            for (Door d : c.doors) {
                boolean want = doorsEnabled && dwell && d.platform && st.untilDepart() > DOOR_CLOSE_BEFORE;
                if (!want && d.open > 0.0 && dwell && st.untilDepart() > 0.5 && doorwayOccupied(c, d)) want = true;
                double target = want ? 1.0 : 0.0;
                if (d.open == target) continue;
                d.open = target > d.open ? Math.min(1.0, d.open + step) : Math.max(0.0, d.open - step);
                for (int k = 0; k < d.leaves.size(); k++) {
                    Node3D leaf = d.leaves.get(k);
                    if (GD.isInstanceValid(leaf)) leaf.setPosition(d.closed.get(k).plus(d.slide.get(k).times(d.open)));
                }
                d.shape.setDisabled(d.open > 0.5);
            }
        }
    }

    private godot.api.PhysicsDirectSpaceState3D space() {
        return getWorld3d() != null ? getWorld3d().getDirectSpaceState() : null;
    }

    private godot.core.VariantArray<godot.core.RID> trainRids() {
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        for (TrainSet s : sets) for (Car c : s.cars) if (GD.isInstanceValid(c.body)) ex.append(c.body.getRid());
        for (Wreck w : wrecks) for (AnimatableBody3D b : w.bodies) if (GD.isInstanceValid(b)) ex.append(b.getRid());
        return ex;
    }

    /** Is there a platform beside this door: a surface, not the train's, within 0.35 m under its floor? */
    private boolean platformBeside(Transform3D xf, Door d) {
        godot.api.PhysicsDirectSpaceState3D sp = space();
        if (sp == null) return false;
        double floor = 1.13;
        Vector3 from = xf.times(new Vector3(d.side * 1.85, floor + 0.5, d.centre.getZ()));
        Vector3 to = xf.times(new Vector3(d.side * 1.85, floor - 0.6, d.centre.getZ()));
        godot.api.PhysicsRayQueryParameters3D q = godot.api.PhysicsRayQueryParameters3D.create(from, to,
                CollisionLayers.WORLD, trainRids());
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("position") instanceof Vector3 p)) return false;
        Vector3 local = xf.affineInverse().times(p);
        return local.getY() > floor - 0.35;
    }

    private boolean doorwayOccupied(Car c, Door d) {
        godot.api.PhysicsDirectSpaceState3D sp = space();
        if (sp == null) return false;
        godot.api.PhysicsShapeQueryParameters3D q = new godot.api.PhysicsShapeQueryParameters3D();
        BoxShape3D b = new BoxShape3D();
        b.setSize(new Vector3(0.9, d.size.getY(), d.size.getZ()));
        q.setShape(b);
        q.setTransform(c.body.getGlobalTransform().times(new Transform3D(new Basis(), d.centre)));
        q.setCollisionMask(CollisionLayers.CHARACTER);
        q.setExclude(trainRids());
        return !sp.intersectShape(q, 1).isEmpty();
    }

    private void updateLights(TrainSet set, Vector3 eye) {
        for (Car c : set.cars) {
            boolean on = eye != null && c.body.getGlobalPosition().distanceTo(eye) < LIGHT_RADIUS;
            for (godot.api.OmniLight3D l : c.lights) if (l.isVisible() != on) l.setVisible(on);
        }
    }

    // ── health, destruction, the wreck and the respawn ──────────────────────

    private final List<Wreck> wrecks = new ArrayList<>();
    private StandardMaterial3D burntMat;

    private com.openworld.net.NetworkManager net() {
        return getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n ? n : null;
    }

    private boolean authority() {
        com.openworld.net.NetworkManager n = net();
        return n == null || !n.isNetworked() || n.isServer();
    }

    /** The set's health is its four cars' (each car's Health takes the hits); the lowest wins and is shared. */
    private void readHealth(TrainSet set, double t) {
        float low = set.hp;
        for (Car c : set.cars) if (GD.isInstanceValid(c.health)) low = Math.min(low, c.health.healthNow());
        if (low >= set.hp) return;
        set.hp = low;
        for (Car c : set.cars) {
            if (GD.isInstanceValid(c.health) && c.health.healthNow() > low) c.health.applyReplicatedHealth(low);
        }
        if (set.hp <= 0f && authority()) destroySet(set, t, true);
    }

    /**
     * Destroy a set at time {@code t}: its cars become a burnt wreck where they stand (blasts at each car), and the set
     * is out of service until the first platform dwell {@link #RESPAWN_GAP} s later ({@link TrainTimetable
     * #nextDwellStart}) -- every peer derives that from {@code t}, so the event carries only the time.
     */
    private void destroySet(TrainSet set, double t, boolean broadcast) {
        if (set.outOfService(t) || set.downAt > 0) return;
        set.downAt = t;
        set.backAt = set.tt.nextDwellStart(t + set.phase, RESPAWN_GAP) - set.phase;
        set.hp = 0f;
        Wreck w = new Wreck();
        w.until = set.backAt;
        Node em = getTree() != null ? getTree().getFirstNodeInGroup("explosion_manager") : null;
        for (Car c : set.cars) {
            if (!GD.isInstanceValid(c.body)) continue;
            for (Door d : c.doors) d.shape.setDisabled(false);
            for (godot.api.OmniLight3D l : c.lights) l.setVisible(false);
            burn(c.body);
            w.bodies.add(c.body);
            Vector3 at = c.body.getGlobalTransform().times(new Vector3(0, 2.0, 0));
            if (em instanceof com.openworld.world.manager.ExplosionManager ex) {
                if (authority()) ex.triggerExplosion(at, 7.0f, 140f, 6f, "Train", "", "Train", null, c.body);
                else ex.spawnExplosion(at);
            }
        }
        set.cars.clear();
        if (!w.bodies.isEmpty()) wrecks.add(w);
        String id = set.id;
        if (broadcast) {
            com.openworld.net.NetworkManager net = net();
            if (net != null && net.isNetworked() && net.isServer()) {
                net.broadcastWorldEvent(com.openworld.game.GameManager.WORLD_EVENT_TRAIN_DESTROYED, id, 0f,
                        List.of(String.valueOf(t)));
            }
        }
        if (getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus) bus.trainDestroyed.emit(id);
        GD.print("TrainSystem: set on " + id + " destroyed, back at its platform in "
                + Math.round(set.backAt - t) + " s");
    }

    /** A client: the host destroyed the set on track {@code trackId} at {@code when} (shared clock). */
    public void applyRemoteDestroyed(String trackId, String when) {
        double t;
        try {
            t = Double.parseDouble(when);
        } catch (NumberFormatException e) {
            t = now();
        }
        for (TrainSet set : sets) if (set.id.equals(trackId)) destroySet(set, t, false);
    }

    private void burn(AnimatableBody3D body) {
        if (burntMat == null) {
            burntMat = new StandardMaterial3D();
            burntMat.setAlbedo(new Color(0.07, 0.065, 0.06, 1.0));
            burntMat.setRoughness(0.95f);
        }
        List<Node> stack = new ArrayList<>(List.of(body));
        while (!stack.isEmpty()) {
            Node n = stack.remove(stack.size() - 1);
            if (n instanceof MeshInstance3D mi) mi.setMaterialOverride(burntMat);
            for (Node ch : n.getChildren()) stack.add(ch);
        }
    }

    private void updateWrecks(double t) {
        for (int i = wrecks.size() - 1; i >= 0; i--) {
            Wreck w = wrecks.get(i);
            if (t < w.until && enabled) continue;
            for (AnimatableBody3D b : w.bodies) if (GD.isInstanceValid(b)) b.queueFree();
            wrecks.remove(i);
        }
    }

    /**
     * What a blast does to the trains (ExplosionManager.triggerExplosion, the authority path): every car within the
     * radius of its box takes the falloff damage times its blast multiplier, through its own Health.
     */
    public void blast(Vector3 center, float radius, float maxDamage, String weapon, String attacker, String faction) {
        if (!enabled) return;
        for (TrainSet set : sets) {
            for (Car c : set.cars) {
                if (!GD.isInstanceValid(c.body) || !GD.isInstanceValid(c.health)) continue;
                Vector3 l = c.body.getGlobalTransform().affineInverse().times(center);
                double dx = Math.max(0, Math.abs(l.getX()) - 1.5), dz = Math.max(0, Math.abs(l.getZ()) - CAR_L / 2);
                double dy = Math.max(0, Math.max(0.3 - l.getY(), l.getY() - 4.0));
                double dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
                float dmg = BlastFalloff.damage(maxDamage, radius, dist) * c.health.explosionDamageMultiplier;
                if (dmg > 0f) c.health.takeDamage(c.body, dmg, weapon, null, attacker, faction, center);
            }
        }
    }

    // ── what a moving train does to what is on the track ─────────────────────

    /**
     * Anything in front of a moving set's leading car is HIT: a character takes damage by speed (a walking-pace nudge
     * at {@link #HIT_SPEED}, a kill past ~10 m/s) and is thrown clear of the track; a car is shoved along and damaged.
     * Damage is applied only where damage is (the host / single player); every peer throws what it simulates.
     */
    private void hitAhead(TrainSet set, double delta, double t) {
        double v = set.state.v();
        double speed = Math.abs(v);
        if (speed < 0.5) return;
        godot.api.PhysicsDirectSpaceState3D sp = space();
        if (sp == null) return;
        godot.core.VariantArray<godot.core.RID> ex = trainRids();
        // every car's own volume (the nose's grown by this step's travel): what overlaps it and is not RIDING it
        Set<Long> done = new HashSet<>();
        for (int ci = 0; ci < set.cars.size(); ci++) {
            Car car = set.cars.get(ci);
            if (!GD.isInstanceValid(car.body)) continue;
            Transform3D xf = car.body.getGlobalTransform();
            boolean lead = (v > 0 && ci == 0) || (v < 0 && ci == set.cars.size() - 1);
            // the set runs toward +s and car 0's -Z faces +s (placeCars), so "ahead" is -Z when v > 0
            double dir = v > 0 ? -1.0 : 1.0;
            double grow = lead ? speed * delta + 1.0 : 0.0;
            Vector3 c = new Vector3(0, 1.9, dir * grow / 2.0);
            godot.api.PhysicsShapeQueryParameters3D q = new godot.api.PhysicsShapeQueryParameters3D();
            BoxShape3D b = new BoxShape3D();
            b.setSize(new Vector3(2.9, 3.3, CAR_L + grow));
            q.setShape(b);
            q.setTransform(car.body.getGlobalTransform().times(new Transform3D(new Basis(), c)));   // times() mutates: a fresh one
            q.setCollisionMask(CollisionLayers.CHARACTER | CollisionLayers.VEHICLE);
            q.setExclude(ex);
            godot.core.VariantArray<godot.core.Dictionary<Object, Object>> hits = sp.intersectShape(q, 16);
            if (hits.isEmpty()) continue;
            Transform3D inv = xf.affineInverse();
            Vector3 fwd = xf.getBasis().getZ().times(dir).normalized();
            Vector3 right = xf.getBasis().getX().normalized();
            for (int i = 0; i < hits.size(); i++) {
                Object col = hits.get(i).get("collider");
                if (!(col instanceof Node n)) continue;
                Node target = n;
                while (target != null && !(target instanceof com.openworld.character.Character)
                        && !(target instanceof godot.api.RigidBody3D)) target = target.getParent();
                if (target == null || !done.add(target.getInstanceId())) continue;
                if (target instanceof com.openworld.character.Character ch) {
                    Vector3 l = inv.times(ch.getGlobalPosition());
                    // a passenger: standing on this car's floor, inside its walls (or on the gangway)
                    if (Math.abs(l.getX()) < 1.45 && l.getY() > 0.8 && l.getY() < 3.4) continue;
                    if (ch.currentVehicleNode != null) continue;
                }
                Double last = set.hitAt.get(target.getInstanceId());
                if (last != null && t - last < 1.0) continue;
                set.hitAt.put(target.getInstanceId(), t);
                if (debugHits) {
                    Vector3 l = inv.times(((Node3D) target).getGlobalPosition());
                    GD.print("TrainSystem: hit " + target.getName() + " by set " + sets.indexOf(set) + " car " + ci
                            + " at local " + l + " speed " + speed);
                }
                if (target instanceof com.openworld.character.Character ch) hitCharacter(ch, xf, fwd, right, speed);
                else if (target instanceof godot.api.RigidBody3D rb) hitBody(rb, fwd, speed);
                hitCount++;
            }
        }
    }

    private int hitCount;

    private void hitCharacter(com.openworld.character.Character ch, Transform3D xf, Vector3 fwd, Vector3 right,
                              double speed) {
        if (speed >= HIT_SPEED && authority() && ch.getNodeOrNull("Health") instanceof com.openworld.character.Health h
                && !h.isDead()) {
            float dmg = (float) Math.min(1500.0, 1.2 * speed * speed + 10.0);
            h.takeDamage(ch, dmg, "Train", null, "Train", "", xf.getOrigin());
        }
        // thrown clear: out to the side the body is already on, past the car's flank
        Vector3 p = ch.getGlobalPosition();
        double lat = p.minus(xf.getOrigin()).dot(right);
        double sgn = lat >= 0 ? 1.0 : -1.0;
        if (ch.isAlive()) {
            ch.setGlobalPosition(p.plus(right.times(sgn * Math.max(0.0, 2.2 - Math.abs(lat)))).plus(fwd.times(0.5)));
        } else {
            ch.applyHitImpulse(ch, fwd.plus(right.times(sgn * 0.6)).plus(new Vector3(0, 0.5, 0)).normalized(),
                    (float) (speed * 25.0));
        }
    }

    private void hitBody(godot.api.RigidBody3D rb, Vector3 fwd, double speed) {
        if (!rb.isFreezeEnabled()) {
            double m = rb.getMass();
            rb.applyCentralImpulse(fwd.times(m * speed * 1.3).plus(new Vector3(0, m * Math.min(4.0, speed * 0.3), 0)));
        }
        if (speed >= HIT_SPEED && authority() && rb.getNodeOrNull("Health") instanceof com.openworld.character.Health h
                && !h.isDead()) {
            h.takeDamage(rb, (float) (speed * 30.0), "Train", null, "Train", "", rb.getGlobalPosition());
            // A train hitting a car is never meant to happen to traffic (the cars hold at a closed crossing), so when it
            // does, say what the car was doing (PLAN.md 0.13: one ambient car in five runs was destroyed on a 踏切).
            String why = rb instanceof com.openworld.carrier.vehicle.Vehicle v
                    && v.getController() instanceof com.openworld.ai.vehicle.VehicleAIController ai ? ai.describeBlock() : "";
            GD.print(String.format("TrainSystem: train at %.1f m/s hit %s at %s v=%.1f m/s %s", speed, rb.getName(),
                    rb.getGlobalPosition(), rb.getLinearVelocity().length(), why));
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
            // a unit a car has knocked down (it is a breakable pole, BreakableProps) flashes nothing: the cars stop
            // from the timetable, never from the unit, so a crossing with its units down still closes for a train
            if (on && unitDown(u)) on = false;
            if (!near || !on) {
                if (u.lamp != null) for (MeshInstance3D m : u.lamp) m.setVisible(false);
                continue;
            }
            if (u.lamp == null) u.lamp = buildLamps(u);
            u.lamp[0].setVisible(phaseA);
            u.lamp[1].setVisible(!phaseA);
        }
    }

    /** Is this unit's baked pole knocked down (or not streamed in)? */
    private static boolean unitDown(Unit u) {
        if (u.props == null || !GD.isInstanceValid(u.props)) {
            Object[] f = TrafficSignals.findPole(u.pos);
            if (f == null) return false;          // an unbreakable or unbaked unit: nothing to knock down
            u.props = (BreakableProps) f[0];
            u.poleIndex = (Integer) f[1];
        }
        return u.props.poleBroken(u.poleIndex);
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
        for (Wreck w : wrecks) for (AnimatableBody3D b : w.bodies) if (GD.isInstanceValid(b)) b.queueFree();
        wrecks.clear();
        for (Unit u : units) if (u.lamp != null) for (MeshInstance3D m : u.lamp) if (GD.isInstanceValid(m)) m.queueFree();
        sets.clear();
        tracks.clear();
        mapLineCache = null;
        if (displays != null) displays.clear();
        crossings.clear();
        byLane.clear();
        units.clear();
    }

    // ── probe readouts ───────────────────────────────────────────────────────

    @Register public int setCountNow() { return sets.size(); }
    @Register public int trackCountNow() { return tracks.size(); }
    @Register public int crossingCountNow() { return crossings.size(); }
    /** Probe readout: every level crossing as "lane|lane position". */
    @Register public String crossingLanesNow() {
        StringBuilder b = new StringBuilder();
        for (Crossing c : crossings) b.append(c.lane).append('|').append(c.laneS).append(';');
        return b.toString();
    }
    @Register public int unitCountNow() { return units.size(); }
    @Register public int carsNow() { int n = 0; for (TrainSet s : sets) n += s.cars.size(); return n; }
    @Register public int hitsNow() { return hitCount; }

    // ── what passengers read (TrainDisplays) ─────────────────────────────────

    private TrainDisplays displays;
    private double displayTimer;

    TrainDisplays displays() {
        if (displays == null) displays = new TrainDisplays(this);
        return displays;
    }

    String stationId(int i) { return i >= 0 && i < stationIds.size() ? stationIds.get(i) : ""; }
    List<double[]> stationPositions() { return stationPos; }
    List<TrainSet> setsNow() { return sets; }
    godot.core.VariantArray<godot.core.RID> trainRidsNow() { return trainRids(); }

    /** The map's panel for the station nearest a world point (within {@code reach} m): name, then each way's next
     *  two departures in game time. Empty when there is none. */
    public static List<String> stationPanel(double x, double z, double reach) {
        TrainSystem ts = instance;
        if (ts == null || !ts.enabled) return List.of();
        return ts.displays().stationPanel(x, z, reach, ts.now());
    }

    @Register public int boardCountNow() { return displays().boardCount(); }
    @Register public String boardTextNow() { return displays().anyBoardText(); }
    @Register
    public String stationPanelNow(Vector3 p) { return String.join("\n", stationPanel(p.getX(), p.getZ(), 120.0)); }
    /** Set i, car c: the first door-top screen's text (probe). */
    @Register
    public String screenTextNow(int i, int c) {
        if (i < 0 || i >= sets.size() || c < 0 || c >= sets.get(i).cars.size()) return "";
        List<godot.api.Label3D> l = sets.get(i).cars.get(c).screens;
        return l.isEmpty() ? "" : l.get(0).getText();
    }

    /** A blast at {@code c} as the explosion system deals it (probe). */
    @Register public void blastNow(Vector3 c, float radius, float maxDamage) { blast(c, radius, maxDamage, "Probe", "Probe", ""); }

    // ── the map (user, 2026-10-02: "combine the train line to the map to help the player coordinate") ─────

    /** One polyline per LINE (x0, z0, x1, z1, ...; ~8 m apart): a track that runs within {@link #MAP_SAME} m of one
     *  already drawn (the other track of the line, 4 m away) is not drawn again -- one line on a map. */
    public static List<double[]> mapLines() {
        TrainSystem ts = instance;
        if (ts == null) return List.of();
        if (ts.mapLineCache == null) {
            List<double[]> out = new ArrayList<>();
            for (Track t : ts.tracks) {
                int n = Math.max(2, (int) Math.ceil(t.length() / 8.0) + 1);
                double[] xz = new double[2 * n];
                for (int i = 0; i < n; i++) {
                    double[] p = t.at(t.length() * i / (n - 1));
                    xz[2 * i] = p[0];
                    xz[2 * i + 1] = p[2];
                }
                // drawn already if most of it lies along a drawn line
                int near = 0;
                for (int i = 0; i < n; i++) {
                    boolean hit = false;
                    for (double[] o : out) {
                        for (int k = 0; k < o.length && !hit; k += 2) {
                            hit = Math.hypot(o[k] - xz[2 * i], o[k + 1] - xz[2 * i + 1]) < MAP_SAME;
                        }
                        if (hit) break;
                    }
                    if (hit) near++;
                }
                if (near > n * 0.8) continue;
                out.add(xz);
            }
            ts.mapLineCache = out;
        }
        return ts.mapLineCache;
    }

    private List<double[]> mapLineCache;
    static final double MAP_SAME = 12.0;

    @Register public int mapLineCountNow() { return mapLines().size(); }
    @Register public int mapTrainCountNow() { return mapTrains().size(); }

    /** Every set in service right now as {head x, head z, tail x, tail z} (from the clock, spawned or not). */
    public static List<double[]> mapTrains() {
        TrainSystem ts = instance;
        if (ts == null || !ts.enabled) return List.of();
        double t = ts.now();
        List<double[]> out = new ArrayList<>();
        for (TrainSet s : ts.sets) {
            if (s.outOfService(t)) continue;
            TrainTimetable.State st = s.tt.at(t + s.phase);
            int dir = st.dwell() ? 1 : st.dir();
            Track tr = s.tracks[st.track()];
            double[] h = tr.at(st.s() + dir * SET_L / 2), tl = tr.at(st.s() - dir * SET_L / 2);
            out.add(new double[]{h[0], h[2], tl[0], tl[2]});
        }
        return out;
    }
    @Register public int wrecksNow() { return wrecks.size(); }

    // ── missions: a set can be made invulnerable (an escort), destroyed outright (a heist), asked about ─────

    /** The set nearest a world point (plan), or -1. */
    @Register
    public int nearestSetNow(Vector3 p) {
        double t = now(), best = Double.MAX_VALUE;
        int bi = -1;
        for (int i = 0; i < sets.size(); i++) {
            TrainSet s = sets.get(i);
            if (s.outOfService(t)) continue;
            TrainTimetable.State st = s.tt.at(t + s.phase);
            double[] c = s.tracks[st.track()].at(st.s());
            double d = Math.hypot(c[0] - p.getX(), c[2] - p.getZ());
            if (d < best) { best = d; bi = i; }
        }
        return bi;
    }

    /** Destroy set {@code i} now (the host / single player; a client's call does nothing). */
    @Register
    public boolean destroySetNow(int i) {
        if (i < 0 || i >= sets.size() || !authority()) return false;
        TrainSet s = sets.get(i);
        if (s.outOfService(now())) return false;
        destroySet(s, now(), true);
        return true;
    }

    @Register
    public void setInvulnerableNow(int i, boolean on) {
        if (i < 0 || i >= sets.size()) return;
        TrainSet s = sets.get(i);
        s.invulnerable = on;
        for (Car c : s.cars) if (GD.isInstanceValid(c.health)) c.health.invulnerable = on;
    }

    @Register public float setHealthNow(int i) { return i >= 0 && i < sets.size() ? sets.get(i).hp : 0f; }

    @Register public boolean setOutOfServiceNow(int i) { return i >= 0 && i < sets.size() && sets.get(i).outOfService(now()); }

    /** When set {@code i} comes back (shared clock), or -1 while in service. */
    @Register public double setBackAtNow(int i) { return i >= 0 && i < sets.size() ? sets.get(i).backAt : -1; }

    /** Set {@code i}'s doors: [open fraction, platform 0/1] per door of car {@code car}, flattened. */
    @Register
    public godot.core.PackedFloat64Array carDoorsNow(int i, int car) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= sets.size() || car < 0 || car >= sets.get(i).cars.size()) return out;
        for (Door d : sets.get(i).cars.get(car).doors) { out.append(d.open); out.append(d.platform ? 1.0 : 0.0); }
        return out;
    }

    /** Set {@code i}'s car body (probe). */
    @Register
    public Node3D carBodyNow(int i, int car) {
        if (i < 0 || i >= sets.size() || car < 0 || car >= sets.get(i).cars.size()) return null;
        return sets.get(i).cars.get(car).body;
    }

    /** The clock the timetable runs on (probe). */
    @Register public double clockNow() { return now(); }

    /** Set {@code i} at game/system time {@code t}: [s, v, dwell 0/1, stop, x, y, z, track length, period, track,
     *  seconds until it moves]. */
    @Register
    public godot.core.PackedFloat64Array setStateAt(int i, double t) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= sets.size()) return out;
        TrainSet s = sets.get(i);
        TrainTimetable.State st = s.tt.at(t + s.phase);
        Track tr = s.tracks[st.track()];
        double[] p = tr.at(st.s());
        for (double v : new double[]{st.s(), st.v(), st.dwell() ? 1 : 0, st.stop(), p[0], p[1], p[2],
                tr.length(), s.tt.period(), st.track(), st.untilDepart()}) out.append(v);
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
        int ti = -1;
        for (int k = 0; k < sets.size() && si < 0; k++) {
            int idx = sets.get(k).trackIndex(c.track);
            if (idx >= 0) { si = k; ti = idx; }
        }
        for (double v : new double[]{si, c.s, c.pos.getX(), c.pos.getY(), c.pos.getZ(), ti}) out.append(v);
        return out;
    }

    /**
     * Probe (PLAN.md 0.16): over {@code [t0, t1)} in steps of {@code dt}, the SHORTEST time crossing {@code i} had been
     * closed when a train's front reached the road ({@code [lead s, at time t]}; lead 0 = arrived at an open crossing,
     * NaN = no train reached it in the window). A 踏切 must warn long before a car can no longer clear it.
     */
    @Register
    public godot.core.PackedFloat64Array crossingLeadNow(int i, double t0, double t1, double dt) {
        godot.core.PackedFloat64Array out = new godot.core.PackedFloat64Array();
        if (i < 0 || i >= crossings.size() || dt <= 0) return out;
        Crossing c = crossings.get(i);
        double closedSince = Double.NaN, best = Double.NaN, bestAt = Double.NaN;
        boolean wasIn = false;
        for (double t = t0; t < t1; t += dt) {
            boolean cl = closed(c, t);
            if (!cl) closedSince = Double.NaN;
            else if (Double.isNaN(closedSince)) closedSince = t;
            boolean in = false;
            for (TrainSet set : sets) {
                int ti = set.trackIndex(c.track);
                if (ti < 0 || set.outOfService(t)) continue;
                TrainTimetable.State st = set.tt.at(t + set.phase);
                if (st.track() == ti && Math.abs(c.s - st.s()) <= SET_L / 2.0) in = true;
            }
            if (in && !wasIn) {
                double lead = cl ? t - closedSince : 0.0;
                if (Double.isNaN(best) || lead < best) { best = lead; bestAt = t; }
            }
            wasIn = in;
        }
        out.append(best);
        out.append(bestAt);
        return out;
    }

    /** Is crossing {@code i} closed at time {@code t}? */
    @Register public boolean crossingClosedAt(int i, double t) {
        return i >= 0 && i < crossings.size() && closed(crossings.get(i), t);
    }

    /** The set's track id (probe). */
    @Register public int swapsNow() { return swaps; }

    /** Set {@code i}'s circuit described (probe): each track's id, length, ends and its stops with their stations. */
    @Register
    public String setDebugNow(int i) {
        if (i < 0 || i >= sets.size()) return "";
        TrainSet set = sets.get(i);
        StringBuilder sb = new StringBuilder(set.id + (set.tt.isCircuit() ? " circuit" : " shuttle"));
        List<TrainTimetable.Leg> legs = List.of(set.tt.legs());
        for (int ti = 0; ti < set.tracks.length; ti++) {
            Track t = set.tracks[ti];
            int n = t.x.length - 1;
            sb.append(String.format("%n  track %d %s line %s len %.0f: start (%.0f, %.1f, %.0f) end (%.0f, %.1f, %.0f)", ti,
                    t.id, t.line, t.length(), t.x[0], t.y[0], t.z[0], t.x[n], t.y[n], t.z[n]));
            for (TrainTimetable.Leg l : legs) {
                if (!l.dwell() || l.track() != ti) continue;
                double[] p = t.at(l.s0());
                sb.append(String.format("%n    stop %d s %.0f at (%.0f, %.1f, %.0f) station %s", l.stop(), l.s0(), p[0], p[1], p[2],
                        stationId(set.stopStation[ti][l.stop()])));
            }
        }
        return sb.toString();
    }
    @Register public String setIdNow(int i) { return i >= 0 && i < sets.size() ? sets.get(i).id : ""; }
    @Register public String setTrackNow(int i) { return i >= 0 && i < sets.size() ? sets.get(i).track.id : ""; }
}
