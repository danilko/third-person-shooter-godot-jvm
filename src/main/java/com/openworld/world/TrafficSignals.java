package com.openworld.world;

import com.openworld.util.MiniJson;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.BaseMaterial3D;
import godot.api.Camera3D;
import godot.api.FileAccess;
import godot.api.FontFile;
import godot.api.GeometryInstance3D;
import godot.api.Label3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.QuadMesh;
import godot.api.ImmediateMesh;
import godot.api.Mesh;
import godot.api.SphereMesh;
import godot.api.StandardMaterial3D;
import godot.api.Time;
import godot.core.Basis;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The island's traffic signals WORK (user, 2026-09-26: "enable both pedestrian + traffic light") -- registered as
 * the AutoLoad "TrafficSignals".
 *
 * <p><b>What it runs is the road build's plan, not a guess.</b> {@code roadkit_cli gltf} writes
 * {@code <network>.signals.json} beside the lanekits ({@code point_furniture.signal_plan}): every signalised junction
 * (the Japanese rule: a crossing of two narrow streets has none), its arms in phase groups, the lanes that obey each
 * arm and where their stop line is, and every lens of every vehicle and pedestrian signal and every name plate, in the
 * lanekit's frame. This node finds each road network the world streams (its ZoneMarkers, the way
 * {@link RoadMap} does), reads its plan once and places it with the network's own transform.
 *
 * <p><b>The clock</b> is {@link SignalTiming} over the SYSTEM clock: every peer computes the same phase with no
 * message, and the host's traffic and a client's lamps agree.
 *
 * <p><b>Three consumers:</b>
 * <ul>
 * <li>the traffic brain asks {@link #stopDistance} (VehicleAIController.signalSpeedLimit): a car on an arm's lane
 *     stops at the stop line on RED, and on YELLOW when it can still stop comfortably;</li>
 * <li>the LAMPS near the camera are lit ({@link #visualRadius}): the LENS MESH itself (TrafficLight_2_Japan.blend's lens
 *     objects, via each piece's lamps.json; a ball only for a plan with no mesh) -- green
 *     (Japan's 青), yellow or red on the vehicle heads, the red and green man on the pedestrian heads, the green man
 *     flashing for its last {@link SignalTiming#PED_FLASH} s. Far junctions cost nothing: their nodes are freed;</li>
 * <li>the NAME PLATES (the kit's "E 12 St" is gone from the .blend): a blue plate on each vehicle signal's arm with
 *     the name of the street being CROSSED, in kanji and romaji ({@link StreetNames}).</li>
 * <li>the EXPRESSWAY GUIDE SIGNS (PLAN.md item 1g): white text on the green panel of each baked sign piece, from
 *     {@code <network>.signs.json} ({@code point_furniture.expressway_sign_plan}) -- 出口 EXIT + the street an exit
 *     lands on, JCT + the expressway a junction ramp leads to, 入口 ENTRANCE + the route at an on-ramp. Names come
 *     from {@link StreetNames} (fictional on purpose).</li>
 * </ul>
 * Pedestrians do not cross streets yet (the crowd walks the footways and turns at their ends), so the pedestrian
 * lights are shown, not obeyed. {@link #enabled} off is the control: no lamps, and traffic ignores the lights.
 */
@Script(className = "TrafficSignals")
public class TrafficSignals extends Node3D {

    private static TrafficSignals instance;

    public static TrafficSignals get() { return instance; }

    /** Junctions within this of the camera have their lamps and plates built (m). */
    @Export public float visualRadius = 160.0f;
    /** Expressway guide signs within this of the camera have their text built (m): read from far off at speed. */
    @Export public float signRadius = 350.0f;
    /** Seconds between lamp updates. */
    @Export public float evalInterval = 0.1f;
    /** A car stops at the stop line on a yellow only when it can at this deceleration (m/s^2). */
    @Export public float yellowStopDecel = 3.0f;
    /** The control knob: off is the world before signals worked. */
    @Visible public boolean enabled = true;
    /** Run the phases on GAME time (physics frames) instead of the shared wall clock: for a headless probe at
     *  {@code --fixed-fps}, whose game time is not real time. Peers agree only on the wall clock, so play uses it. */
    @Visible public boolean gameClock = false;

    /** How far the car's nose is ahead of its body origin (m): it is the nose that stops at the line. */
    public static final double NOSE = 2.3;
    /** m past the stop line (nose) beyond which a car is committed and clears the junction whatever the light. */
    public static final double COMMITTED = 3.0;

    private static final class Arm { int index; int group; double stopBack; String road; }
    private static final class Lamp { boolean vehicle; int arm; int colour; Vector3 pos; double radius; Vector3 pole;
                                      double yaw; int head; String lamps; BreakableProps props; int poleIndex = -1; }
    private static final class Plate { int arm; String cross; Vector3 pos; Vector3 normal; double w, h; Vector3 pole; boolean built; }

    private static final class Sign { String kind, dest, route; Vector3 pos, normal; double w, h; Node3D view; }

    private static final class Junction {
        String id;
        Vector3 centre;
        Basis frame;
        int groups;
        double offset;
        final Map<Integer, Arm> arms = new HashMap<>();
        final List<Lamp> lamps = new ArrayList<>();
        final List<Plate> plates = new ArrayList<>();
        Node3D view;
        final List<MeshInstance3D> lampNodes = new ArrayList<>();
        boolean polesResolved;
        double resolveAge;
    }

    private final List<Junction> junctions = new ArrayList<>();
    private final List<Sign> signs = new ArrayList<>();
    private final Map<String, Object[]> laneArm = new HashMap<>();        // lane id -> {Junction, Arm}
    private double green = 22.0, yellow = 3.0, allRed = 2.0;
    private String signature = "";
    private long sceneId = -1;
    private double timer, loadTimer;
    private int litNow, litVehicleNow;
    private final StandardMaterial3D[] lit = new StandardMaterial3D[3];
    private StandardMaterial3D plateMat;

    @Register
    @Override
    public void _ready() {
        instance = this;
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        LENS_CACHE.clear();
        clear();
    }

    // ── the plan ──────────────────────────────────────────────────────────────

    /** Re-reads the plans when the scene or its set of road networks changed. Cheap otherwise. */
    private void refresh() {
        ZoneManager zm = ZoneManager.get();
        if (zm == null) return;
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        long sid = scene != null ? scene.getInstanceId() : 0;
        Map<String, Transform3D> nets = new HashMap<>();
        for (ZoneMarker m : zm.getMarkers()) {
            if (m == null || !GD.isInstanceValid(m) || m.zone == null) continue;
            String gp = m.zone.geometryPath;
            if (gp == null || gp.isEmpty()) continue;
            String file = gp.substring(gp.lastIndexOf('/') + 1);
            String stem = file.contains(".") ? file.substring(0, file.lastIndexOf('.')) : file;
            String suffix = "_" + m.zone.zoneId;
            if (!stem.startsWith("Roads_") || !stem.endsWith(suffix)) continue;
            String prefix = stem.substring(0, stem.length() - suffix.length());
            nets.putIfAbsent(prefix, m.zone.geometryFrame(m));
        }
        StringBuilder sig = new StringBuilder();
        nets.keySet().stream().sorted().forEach(k -> sig.append(k).append('|'));
        if (sid == sceneId && sig.toString().equals(signature)) return;
        sceneId = sid;
        signature = sig.toString();
        clear();
        for (Map.Entry<String, Transform3D> e : nets.entrySet()) {
            load(e.getKey(), e.getValue());
            loadSigns(e.getKey(), e.getValue());
        }
        if (!junctions.isEmpty())
            GD.print("TrafficSignals: " + junctions.size() + " signalised junction(s), " + laneArm.size()
                    + " signalled lane(s) from " + nets.size() + " network(s)");
    }

    @SuppressWarnings("unchecked")
    private void load(String prefix, Transform3D frame) {
        String path = "res://assets/world_source/pieces/" + prefix + ".signals.json";
        if (!FileAccess.fileExists(path)) return;
        Map<String, Object> doc;
        try {
            doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(path));
        } catch (IllegalArgumentException | ClassCastException e) {
            GD.printErr("TrafficSignals: " + path + ": " + e.getMessage());
            return;
        }
        green = num(doc.get("green"), green);
        yellow = num(doc.get("yellow"), yellow);
        allRed = num(doc.get("all_red"), allRed);
        Basis b = frame.getBasis();
        for (Object jo : (List<Object>) doc.get("junctions")) {
            Map<String, Object> jm = (Map<String, Object>) jo;
            Junction j = new Junction();
            j.id = prefix + ":" + jm.get("id");
            j.frame = b;
            j.centre = frame.times(vec(jm.get("centre")));
            j.groups = (int) num(jm.get("groups"), 1);
            j.offset = SignalTiming.offset(j.id, SignalTiming.cycle(j.groups, green, yellow, allRed));
            for (Object ao : (List<Object>) jm.get("arms")) {
                Map<String, Object> am = (Map<String, Object>) ao;
                Arm a = new Arm();
                a.index = (int) num(am.get("index"), 0);
                a.group = (int) num(am.get("group"), 0);
                a.stopBack = num(am.get("stop_back"), 7.45);
                a.road = String.valueOf(am.get("road"));
                j.arms.put(a.index, a);
                for (Object lo : (List<Object>) am.get("in_lanes")) laneArm.put(String.valueOf(lo), new Object[]{j, a});
            }
            for (Object lo : (List<Object>) jm.get("lamps")) {
                Map<String, Object> lm = (Map<String, Object>) lo;
                Lamp l = new Lamp();
                l.vehicle = "vehicle".equals(lm.get("kind"));
                l.arm = (int) num(lm.get("arm"), 0);
                String c = String.valueOf(lm.get("colour"));
                l.colour = "green".equals(c) ? 0 : "yellow".equals(c) ? 1 : 2;
                // just in front of the lens, so the glow is not inside the hood's own geometry
                Vector3 n = b.times(vec(lm.get("normal")));
                l.pos = frame.times(vec(lm.get("pos"))).plus(n.times(0.03));
                l.radius = num(lm.get("radius"), 0.12);
                l.pole = lm.containsKey("pole") ? frame.times(vec(lm.get("pole"))) : null;
                l.yaw = num(lm.get("yaw"), 0.0);
                l.head = (int) num(lm.get("head"), 0);
                l.lamps = lm.containsKey("lamps") ? String.valueOf(lm.get("lamps")) : null;
                j.lamps.add(l);
            }
            for (Object po : (List<Object>) jm.get("plates")) {
                Map<String, Object> pm = (Map<String, Object>) po;
                Plate p = new Plate();
                p.arm = (int) num(pm.get("arm"), 0);
                p.cross = String.valueOf(pm.get("cross"));
                p.pos = frame.times(vec(pm.get("pos")));
                p.normal = b.times(vec(pm.get("normal"))).normalized();
                p.pole = pm.containsKey("pole") ? frame.times(vec(pm.get("pole"))) : null;
                List<Object> sz = (List<Object>) pm.get("size");
                p.w = num(sz.get(0), 1.4);
                p.h = num(sz.get(1), 0.4);
                j.plates.add(p);
            }
            junctions.add(j);
        }
    }

    @SuppressWarnings("unchecked")
    private void loadSigns(String prefix, Transform3D frame) {
        String path = "res://assets/world_source/pieces/" + prefix + ".signs.json";
        if (!FileAccess.fileExists(path)) return;
        try {
            Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(path));
            for (Object so : (List<Object>) doc.get("signs")) {
                Map<String, Object> m = (Map<String, Object>) so;
                Sign g = new Sign();
                g.kind = String.valueOf(m.get("kind"));
                g.dest = String.valueOf(m.get("dest"));
                g.route = String.valueOf(m.get("route"));
                g.pos = frame.times(vec(m.get("pos")));
                g.normal = frame.getBasis().times(vec(m.get("normal"))).normalized();
                List<Object> sz = (List<Object>) m.get("size");
                g.w = num(sz.get(0), 5.0);
                g.h = num(sz.get(1), 2.5);
                signs.add(g);
            }
        } catch (IllegalArgumentException | ClassCastException e) {
            GD.printErr("TrafficSignals: " + path + ": " + e.getMessage());
        }
    }

    private static double num(Object o, double d) { return o instanceof Number n ? n.doubleValue() : d; }

    @SuppressWarnings("unchecked")
    private static Vector3 vec(Object o) {
        List<Object> l = (List<Object>) o;
        return new Vector3(num(l.get(0), 0), num(l.get(1), 0), num(l.get(2), 0));
    }

    private void clear() {
        for (Junction j : junctions) freeView(j);
        junctions.clear();
        for (Sign g : signs) freeSign(g);
        signs.clear();
        laneArm.clear();
        litNow = 0;
    }

    // ── the clock ─────────────────────────────────────────────────────────────

    private double now() {
        if (gameClock) {
            return godot.api.Engine.INSTANCE.getPhysicsFrames() / (double) Math.max(1,
                    godot.api.Engine.INSTANCE.getPhysicsTicksPerSecond());
        }
        return Time.INSTANCE.getUnixTimeFromSystem();
    }

    private int vehicleState(Junction j, Arm a, double t) {
        return SignalTiming.vehicle(j.groups, a.group, t + j.offset, green, yellow, allRed);
    }

    private int pedState(Junction j, Arm a, double t) {
        return SignalTiming.pedestrian(j.groups, a.group, t + j.offset, green, yellow, allRed);
    }

    /**
     * How far (m) a car on lane {@code laneId}, {@code progress} m along a lane {@code total} m long and going
     * {@code speed} m/s, must stop within -- its NOSE at the stop line -- or -1 when it may go: not a signalled lane,
     * green, past the line, or a yellow it cannot stop for.
     */
    public double stopDistance(String laneId, double progress, double total, double speed) {
        if (!enabled) return -1.0;
        Object[] e = laneArm.get(laneId);
        if (e == null) return -1.0;
        Junction j = (Junction) e[0];
        Arm a = (Arm) e[1];
        double d = total - a.stopBack - progress - NOSE;
        // COMMITTED only with the nose well into the junction: a car nudged a metre over the line by the one
        // stopping behind it (measured: an ambient car's bump sent the held car through the red) still holds
        if (d < -COMMITTED) return -1.0;
        int st = vehicleState(j, a, now());
        if (st == SignalTiming.GREEN) return -1.0;
        if (st == SignalTiming.YELLOW && speed * speed / (2.0 * yellowStopDecel) > d) return -1.0;
        return Math.max(0.0, d);
    }

    // ── the lamps and plates near the camera ──────────────────────────────────

    @Register
    @Override
    public void _process(double delta) {
        loadTimer -= delta;
        if (loadTimer <= 0.0) {
            loadTimer = 1.0;
            refresh();
        }
        timer -= delta;
        if (timer > 0.0) return;
        timer = Math.max(0.03f, evalInterval);
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (!enabled || cam == null || !GD.isInstanceValid(cam)) {
            for (Junction j : junctions) freeView(j);
            for (Sign g : signs) freeSign(g);
            litNow = 0;
            return;
        }
        Vector3 c = cam.getGlobalPosition();
        double sr2 = signRadius * (double) signRadius;
        for (Sign g : signs) {
            double dx = g.pos.getX() - c.getX(), dz = g.pos.getZ() - c.getZ();
            if (dx * dx + dz * dz > sr2) freeSign(g);
            else if (g.view == null) buildSign(g);
        }
        double t = now();
        boolean blink = (t * 2.0) % 1.0 < 0.5;
        int n = 0, nv = 0;
        for (Junction j : junctions) {
            double dx = j.centre.getX() - c.getX(), dz = j.centre.getZ() - c.getZ();
            if (dx * dx + dz * dz > visualRadius * (double) visualRadius) {
                freeView(j);
                continue;
            }
            if (j.view == null) buildView(j);
            if (!j.polesResolved && (j.resolveAge -= evalInterval) <= 0.0) resolvePoles(j);
            for (int i = 0; i < j.lamps.size(); i++) {
                Lamp l = j.lamps.get(i);
                Arm a = j.arms.get(l.arm);
                boolean on = false;
                // no pole streamed in, or knocked down: a lens hangs on nothing, so it stays dark
                boolean standing = l.pole == null || (l.props != null && GD.isInstanceValid(l.props)
                        && !l.props.poleBroken(l.poleIndex));
                if (a != null && standing) {
                    if (l.vehicle) {
                        on = vehicleState(j, a, t) == l.colour;
                    } else {
                        int p = pedState(j, a, t);
                        on = l.colour == 0 ? (p == SignalTiming.WALK || (p == SignalTiming.FLASH && blink))
                                           : p == SignalTiming.STOP;
                    }
                }
                j.lampNodes.get(i).setVisible(on);
                if (on) n++;
                if (on && l.vehicle) nv++;
            }
        }
        litNow = n;
        litVehicleNow = nv;
    }

    /** The baked pole (a BreakableProps instance) standing within 0.3 m of `base`, as {props, index}, or null. */
    private static Object[] findPole(Vector3 base) {
        for (BreakableProps bp : BreakableProps.live()) {
            if (!GD.isInstanceValid(bp) || !bp.nearBounds(base.getX(), base.getZ(), 1.0)) continue;
            for (int i = 0; i < bp.poles(); i++) {
                Vector3 q = bp.poleBase(i);
                double dx = q.getX() - base.getX(), dz = q.getZ() - base.getZ();
                if (dx * dx + dz * dz < 0.09) return new Object[]{bp, i};
            }
        }
        return null;
    }

    /** Binds every lamp to the baked pole it hangs on, and builds each name plate once ITS pole is streamed in:
     *  nothing is lit or hung on a pole whose piece has not streamed (or that a car has knocked down). */
    private void resolvePoles(Junction j) {
        boolean all = true;
        for (Lamp l : j.lamps) {
            if (l.pole == null || (l.props != null && GD.isInstanceValid(l.props))) continue;
            Object[] f = findPole(l.pole);
            l.props = f == null ? null : (BreakableProps) f[0];
            l.poleIndex = f == null ? -1 : (Integer) f[1];
            if (l.props == null) all = false;
        }
        if (j.view != null) {
            for (Plate p : j.plates) {
                if (p.built) continue;
                if (p.pole != null && findPole(p.pole) == null) {
                    all = false;
                    continue;
                }
                buildPlate(j.view, p);
                p.built = true;
            }
        }
        j.polesResolved = all;
        j.resolveAge = 1.0;
    }

    /** Lens meshes by lamps file + kind + colour, built once from the file's triangles (Godot piece frame). */
    private static final Map<String, Mesh> LENS_CACHE = new HashMap<>();
    /** How far the lit lens stands proud of the baked (dark) one, along each face's own normal (m). */
    private static final double LENS_PROUD = 0.004;

    @SuppressWarnings("unchecked")
    private static Mesh lensMesh(String file, boolean vehicle, int colour, int head) {
        String key = file + "|" + vehicle + "|" + colour + "|" + head;
        if (LENS_CACHE.containsKey(key)) return LENS_CACHE.get(key);
        Mesh out = null;
        try {
            if (FileAccess.fileExists(file)) {
                Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(FileAccess.getFileAsString(file));
                String want = colour == 0 ? "green" : colour == 1 ? "yellow" : "red";
                for (Object o : (List<Object>) doc.get(vehicle ? "vehicle" : "pedestrian")) {
                    Map<String, Object> d = (Map<String, Object>) o;
                    if (!want.equals(d.get("colour")) || !(d.get("tris") instanceof List)
                            || (int) num(d.get("head"), 0) != head) continue;
                    List<Object> t = (List<Object>) d.get("tris");
                    ImmediateMesh m = new ImmediateMesh();
                    m.surfaceBegin(Mesh.PrimitiveType.TRIANGLES, null);
                    for (int i = 0; i + 8 < t.size(); i += 9) {
                        Vector3 a = new Vector3(num(t.get(i), 0), num(t.get(i + 1), 0), num(t.get(i + 2), 0));
                        Vector3 b = new Vector3(num(t.get(i + 3), 0), num(t.get(i + 4), 0), num(t.get(i + 5), 0));
                        Vector3 c = new Vector3(num(t.get(i + 6), 0), num(t.get(i + 7), 0), num(t.get(i + 8), 0));
                        Vector3 n = b.minus(a).cross(c.minus(a));
                        if (n.length() < 1e-9) continue;
                        n = n.normalized();
                        Vector3 up = n.times(LENS_PROUD);
                        // glTF triangles are counter-clockwise; Godot's front face is clockwise
                        m.surfaceSetNormal(n);
                        m.surfaceAddVertex(a.plus(up));
                        m.surfaceAddVertex(c.plus(up));
                        m.surfaceAddVertex(b.plus(up));
                    }
                    m.surfaceEnd();
                    out = m;
                    break;
                }
            }
        } catch (IllegalArgumentException | ClassCastException e) {
            GD.printErr("TrafficSignals: " + file + ": " + e.getMessage());
        }
        LENS_CACHE.put(key, out);
        return out;
    }

    /** Lamps drawn as the lens MESH (not the fallback ball) among the built views -- a probe readout. */
    @Register public int lensLampsNow() {
        int n = 0;
        for (Junction j : junctions) for (MeshInstance3D mi : j.lampNodes)
            if (GD.isInstanceValid(mi) && mi.getMesh() instanceof ImmediateMesh) n++;
        return n;
    }

    private StandardMaterial3D litMat(int colour) {
        if (lit[colour] == null) {
            StandardMaterial3D m = new StandardMaterial3D();
            m.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
            // Japan's 青 is a blue-green; the yellow is amber
            Color col = colour == 0 ? new Color(0.1, 0.95, 0.75, 1) : colour == 1 ? new Color(1.0, 0.72, 0.08, 1)
                                                                    : new Color(1.0, 0.12, 0.08, 1);
            m.setAlbedo(col);
            lit[colour] = m;
        }
        return lit[colour];
    }

    private void buildView(Junction j) {
        j.view = new Node3D();
        j.view.setName(new StringName("Signals_" + junctions.indexOf(j)));
        j.view.setAsTopLevel(true);
        addChild(j.view);
        j.lampNodes.clear();
        Basis frame = j.frame;
        for (Lamp l : j.lamps) {
            MeshInstance3D mi = new MeshInstance3D();
            Mesh lens = l.lamps != null && l.pole != null ? lensMesh(l.lamps, l.vehicle, l.colour, l.head) : null;
            mi.setMaterialOverride(litMat(l.colour));
            mi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
            mi.setVisible(false);
            j.view.addChild(mi);
            if (lens != null) {
                // the LENS itself (TrafficLight_2_Japan.blend's lens mesh, pushed a few mm proud of the baked dark one),
                // placed as the pole's piece is: at its base, turned by its yaw, in the network's frame
                mi.setMesh(lens);
                mi.setGlobalTransform(new Transform3D(frame.times(new Basis(new Vector3(0, 1, 0), l.yaw)), l.pole));
            } else {
                SphereMesh sp = new SphereMesh();
                sp.setRadius((float) (l.radius * 0.85));
                sp.setHeight((float) (l.radius * 1.7));
                sp.setRadialSegments(10);
                sp.setRings(5);
                mi.setMesh(sp);
                mi.setGlobalPosition(l.pos);
            }
            j.lampNodes.add(mi);
        }
        for (Plate p : j.plates) p.built = false;
    }

    /** A Japanese street-name plate: white kanji over romaji on blue, facing the traffic under the signal. */
    private void buildPlate(Node3D parent, Plate p) {
        String ja = StreetNames.ja(p.cross);
        if (ja == null) return;
        String en = StreetNames.en(p.cross);
        FontFile font = StreetNames.font();
        double w = Math.max(p.w, ja.length() * 0.26 + 0.3);
        Vector3 z = p.normal;
        Vector3 x = new Vector3(0, 1, 0).cross(z).normalized();
        Vector3 y = z.cross(x);
        Transform3D base = new Transform3D(new Basis(x, y, z), p.pos);
        MeshInstance3D board = new MeshInstance3D();
        QuadMesh q = new QuadMesh();
        q.setSize(new Vector2(w, p.h));
        board.setMesh(q);
        if (plateMat == null) {
            plateMat = new StandardMaterial3D();
            plateMat.setAlbedo(new Color(0.08, 0.26, 0.66, 1));
        }
        board.setMaterialOverride(plateMat);
        board.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        parent.addChild(board);
        board.setGlobalTransform(base);
        parent.addChild(label(ja, font, 64, 0.2 / 64.0, base, 0.05));
        if (en != null) parent.addChild(label(en, font, 32, 0.075 / 32.0, base, -0.13));
    }

    /** A Japanese expressway guide sign's text on its baked green panel: a small tag top-left (出口 EXIT / JCT /
     *  入口 ENTRANCE), then the destination in kanji, large, and in romaji under it, each shrunk to fit the panel. */
    private void buildSign(Sign g) {
        String name = "entrance".equals(g.kind) ? g.route : g.dest;
        String ja = StreetNames.ja(name), en = StreetNames.en(name);
        if (ja == null) ja = name;
        FontFile font = StreetNames.font();
        Node3D v = new Node3D();
        addChild(v);
        g.view = v;
        Vector3 z = g.normal;
        Vector3 x = new Vector3(0, 1, 0).cross(z).normalized();
        Vector3 y = z.cross(x);
        Transform3D base = new Transform3D(new Basis(x, y, z), g.pos);
        if ("lanes".equals(g.kind)) {
            // A LANE-DESIGNATION sign (方面別車線案内, review P1-4): one column per lane, left to right, each its
            // destination and an arrow down onto that lane
            String[] dests = g.dest.split("\\|");
            double colW = g.w / dests.length;
            for (int i = 0; i < dests.length; i++) {
                String dja = StreetNames.ja(dests[i]), den = StreetNames.en(dests[i]);
                if (dja == null) dja = dests[i];
                Transform3D col = new Transform3D(base.getBasis(), base.getOrigin().plus(x.times(-0.5 * g.w + colW * (i + 0.5))));
                double bigC = Math.min(0.22 * g.h, 0.86 * colW / Math.max(1, dja.length()));
                v.addChild(label(dja, font, 64, bigC / 64.0, col, 0.2 * g.h));
                if (den != null) {
                    double smallC = Math.min(0.11 * g.h, 0.9 * colW / Math.max(1, 0.55 * den.length()));
                    v.addChild(label(den, font, 32, smallC / 32.0, col, -0.02 * g.h));
                }
                v.addChild(label("↓", font, 64, 0.26 * g.h / 64.0, col, -0.28 * g.h));
            }
            return;
        }
        String tag = "exit".equals(g.kind) ? "出口 EXIT" : "jct".equals(g.kind) ? "JCT" : "入口 ENTRANCE";
        double tagH = 0.16 * g.h;
        Label3D t = label(tag, font, 48, tagH / 48.0, base, 0.34 * g.h);
        t.setHorizontalAlignment(godot.core.HorizontalAlignment.LEFT);
        t.setTransform(t.getTransform().translated(x.times(-0.45 * g.w)));
        v.addChild(t);
        double bigH = Math.min(0.3 * g.h, 0.86 * g.w / Math.max(1, ja.length()));
        v.addChild(label(ja, font, 64, bigH / 64.0, base, 0.02 * g.h));
        if (en != null) {
            double smallH = Math.min(0.13 * g.h, 0.9 * g.w / Math.max(1, 0.55 * en.length()));
            v.addChild(label(en, font, 32, smallH / 32.0, base, -0.3 * g.h));
        }
    }

    private static void freeSign(Sign g) {
        if (g.view != null && GD.isInstanceValid(g.view)) g.view.queueFree();
        g.view = null;
    }

    private static Label3D label(String text, FontFile font, int size, double pixel, Transform3D base, double up) {
        Label3D l = new Label3D();
        l.setText(text);
        if (font != null) l.setFont(font);
        l.setFontSize(size);
        l.setPixelSize((float) pixel);
        l.setModulate(new Color(1, 1, 1, 1));
        l.setOutlineSize(0);
        l.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        Vector3 at = base.getOrigin().plus(base.getBasis().getColumn(1).times(up))
                .plus(base.getBasis().getColumn(2).times(0.01));
        l.setTransform(new Transform3D(base.getBasis(), at));
        return l;
    }

    private void freeView(Junction j) {
        if (j.view != null && GD.isInstanceValid(j.view)) j.view.queueFree();
        j.polesResolved = false;
        for (Lamp l : j.lamps) l.props = null;
        for (Plate p : j.plates) p.built = false;
        j.view = null;
        j.lampNodes.clear();
    }

    // ── probe readouts ────────────────────────────────────────────────────────

    /** Expressway guide signs loaded, and how many have their text built near the camera. */
    @Register public int expresswaySignsNow() { return signs.size(); }

    @Register public int builtSignsNow() {
        int n = 0;
        for (Sign g : signs) if (g.view != null) n++;
        return n;
    }

    /** The text of the built sign nearest `(x, z)`, "" when none: tag|kanji|romaji. */
    @Register public String signTextNear(double x, double z) {
        Sign best = null;
        double bd = 1e18;
        for (Sign g : signs) {
            if (g.view == null) continue;
            double d = Math.hypot(g.pos.getX() - x, g.pos.getZ() - z);
            if (d < bd) { bd = d; best = g; }
        }
        if (best == null) return "";
        StringBuilder sb = new StringBuilder();
        for (Node c : best.view.getChildren()) if (c instanceof Label3D l) sb.append(l.getText()).append('|');
        return sb.toString();
    }

    /** Signalised junctions loaded. */
    @Register public int junctionsNow() { return junctions.size(); }

    /** Lamps lit this tick (near the camera). */
    @Register public int litLampsNow() { return litNow; }

    /** Lit VEHICLE lenses (the heads over the carriageway) among them. */
    @Register public int litVehicleLampsNow() { return litVehicleNow; }

    /** Junctions whose lamps are built (near the camera). */
    @Register public int viewsNow() {
        int n = 0;
        for (Junction j : junctions) if (j.view != null) n++;
        return n;
    }

    /** Name plates built near the camera. */
    @Register public int platesNow() {
        int n = 0;
        for (Junction j : junctions) if (j.view != null) for (Node c : j.view.getChildren()) if (c instanceof Label3D) n++;
        return n;
    }

    /** The vehicle light of a lane now: "G", "Y", "R", or "" when it is not a signalled lane. */
    @Register public String laneStateNow(String laneId) {
        Object[] e = laneArm.get(laneId);
        if (e == null) return "";
        int s = vehicleState((Junction) e[0], (Arm) e[1], now());
        return s == SignalTiming.GREEN ? "G" : s == SignalTiming.YELLOW ? "Y" : "R";
    }

    /** Seconds until lane `laneId`'s light next turns `want` ("G" or "R"), scanning ahead; -1 when never. */
    @Register public double secondsUntilNow(String laneId, String want) {
        Object[] e = laneArm.get(laneId);
        if (e == null) return -1.0;
        double t0 = now();
        for (double dt = 0.0; dt < 400.0; dt += 0.1) {
            int s = vehicleState((Junction) e[0], (Arm) e[1], t0 + dt);
            if (("G".equals(want) && s == SignalTiming.GREEN) || ("R".equals(want) && s == SignalTiming.RED)) return dt;
        }
        return -1.0;
    }

    /** {@link #stopDistance} for a probe. */
    @Register public double stopDistanceNow(String laneId, double progress, double total, double speed) {
        return stopDistance(laneId, progress, total, speed);
    }

    /** Signalled lane ids (a probe picks one to drive). */
    @Register public String signalledLanesNow() {
        Set<String> s = new HashSet<>(laneArm.keySet());
        return String.join(",", s);
    }
}
