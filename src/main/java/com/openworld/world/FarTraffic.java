package com.openworld.world;

import com.openworld.carrier.vehicle.VehicleModels;
import com.openworld.util.WeightedPick;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.ArrayMesh;
import godot.api.Camera3D;
import godot.api.GeometryInstance3D;
import godot.api.Mesh;
import godot.api.MeshInstance3D;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.ResourceLoader;
import godot.api.SurfaceTool;
import godot.core.PackedFloat32Array;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * THE FAR TRAFFIC TIER (PLAN.md R-10, decision 4: "a far kinematic, script-free car tier like the ped VAT tier, not a
 * bigger budget"). The simulated traffic is a ring (`ZoneManager.trafficSimRadius`, 300 m) and a budget (20 cars), so
 * a street seen from further out read empty. Beyond that ring, out to {@link #farRadius}, this node keeps
 * {@link #budget} cars that are only DATA -- a lane, a position along it, a speed and a model -- moved along the lanes
 * the ZoneManager has registered (the same `pickNextRoute` / `LaneGraph.successorsOf` successors the AI follows),
 * holding at a red light (`TrafficSignals.stopDistance`) and behind the car ahead on their lane, and drawn as ONE
 * MultiMesh per model (each model's parts merged into one mesh at first use): no body, no collision, no script per
 * car, one buffer upload per model per frame.
 *
 * <p>Like the crowd's far tier it is LOCAL to each peer and never replicated (cosmetic state, PLAN.md 3.11b). A far car
 * that drives into the simulation ring is dropped (the ring has its own cars); one is never born inside the camera's
 * view nearer than {@link #hiddenSpawnDistance}. Cars are centred on THIS peer's camera.
 */
@Script
public class FarTraffic extends Node {

    /** Cars kept in the ring. 0 = off. */
    @Export public int budget = 60;
    /** Outer radius (m) from the camera; the inner radius is the simulation ring + {@link #ringGap}. */
    @Export public float farRadius = 700f;
    @Export public float ringGap = 20f;
    /** A car is born in view only further than this (m); nearer it is born out of view. */
    @Export public float hiddenSpawnDistance = 450f;
    /** Probe / control knob. */
    @Visible public boolean enabled = true;

    static final double ACCEL = 2.5, DECEL = 4.0, GAP = 8.0, DEFAULT_SPEED = 11.0, SPEED_SHARE = 0.85;

    private static final class Car {
        Lane lane;
        double s, v, target;
        int model;
    }

    private final List<Car> cars = new ArrayList<>();
    private final List<String> modelIds = new ArrayList<>();
    private final List<MultiMeshInstance3D> draws = new ArrayList<>();
    private final Map<String, Integer> modelIndex = new HashMap<>();
    private final Random rng = new Random(0x5eed);
    private double maintainTimer;
    private Camera3D lastCam;

    private double travelled;
    private String diag = "";

    /** Probe readout: why the tier is (not) filling. */
    @Register public String diagNow() { return diag; }

    /** Probe readout: metres driven by every far car since the start. */
    @Register public double travelledNow() { return travelled; }

    /** Probe readout: the nearest and furthest far car from the current camera (plan m), "min|max", or "". */
    @Register public String rangeNow() {
        if (lastCam == null || !GD.isInstanceValid(lastCam) || cars.isEmpty()) return "";
        Vector3 eye = lastCam.getGlobalPosition();
        double lo = Double.MAX_VALUE, hi = 0.0;
        for (Car c : cars) {
            Vector3 p = c.lane.pointAtLength(c.s);
            double d = Math.hypot(p.getX() - eye.getX(), p.getZ() - eye.getZ());
            lo = Math.min(lo, d);
            hi = Math.max(hi, d);
        }
        return lo + "|" + hi;
    }

    /** Probe readout: cars alive in the far tier. */
    @Register public int carsNow() { return cars.size(); }

    /** Probe readout: the far car nearest (x, z), as "lane|s|speed", or "". */
    @Register public String nearestNow(float x, float z) {
        Car best = null;
        double bd = Double.MAX_VALUE;
        for (Car c : cars) {
            Vector3 p = c.lane.pointAtLength(c.s);
            double d = Math.hypot(p.getX() - x, p.getZ() - z);
            if (d < bd) { bd = d; best = c; }
        }
        return best == null ? "" : ((Node) best.lane).getName() + "|" + best.s + "|" + best.v;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (!enabled || budget <= 0) {
            if (!cars.isEmpty()) { cars.clear(); draw(); }
            return;
        }
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam == null || !cam.isInsideTree()) { diag = "no camera"; return; }
        lastCam = cam;
        Vector3 eye = cam.getGlobalPosition();
        ZoneManager zm = ZoneManager.get();
        double inner = (zm != null && zm.trafficSimRadius > 0f ? zm.trafficSimRadius : 300.0) + ringGap;
        double dt = Math.min(delta, 0.1);
        move(dt);
        // drop: a freed lane, past the ring, or into the simulation ring
        cars.removeIf(c -> {
            if (!(c.lane instanceof Node n) || !GD.isInstanceValid(n)) return true;
            Vector3 p = c.lane.pointAtLength(c.s);
            double d = Math.hypot(p.getX() - eye.getX(), p.getZ() - eye.getZ());
            return d > farRadius + 30.0 || d < inner - 10.0;
        });
        maintainTimer -= delta;
        if (maintainTimer <= 0.0) {
            maintainTimer = 0.5;
            spawn(eye, inner, cam);
        }
        draw();
    }

    private void move(double dt) {
        // car-following per lane: each car's leader is the nearest ahead on its lane
        Map<Lane, List<Car>> byLane = new HashMap<>();
        for (Car c : cars) byLane.computeIfAbsent(c.lane, k -> new ArrayList<>()).add(c);
        TrafficSignals ts = TrafficSignals.get();
        List<Car> drop = new ArrayList<>();
        for (Car c : cars) {
            double want = c.target;
            for (Car o : byLane.get(c.lane)) {
                if (o == c || o.s <= c.s) continue;
                double gap = o.s - c.s - GAP;
                want = Math.min(want, Math.sqrt(2.0 * DECEL * Math.max(0.0, gap)));
            }
            if (ts != null && c.lane instanceof Node n) {
                double d = ts.stopDistance(n.getName().toString(), c.s, c.lane.total(), c.v);
                if (d >= 0.0) want = Math.min(want, Math.sqrt(2.0 * DECEL * Math.max(0.0, d - 0.3)));
            }
            c.v = want > c.v ? Math.min(want, c.v + ACCEL * dt) : Math.max(want, c.v - DECEL * 1.5 * dt);
            c.s += c.v * dt;
            travelled += c.v * dt;
            if (c.s >= c.lane.total()) {
                Lane next = nextOf(c.lane);
                if (next == null) { drop.add(c); continue; }
                c.s -= c.lane.total();
                c.lane = next;
                c.target = targetSpeed(next);
            }
        }
        cars.removeAll(drop);
    }

    private static Lane nextOf(Lane lane) {
        if (lane.isLoop()) return lane;
        Lane next = lane.pickNextRoute();
        if (next != null) return next;
        List<Lane> succ = LaneGraph.successorsOf(lane);
        if (succ.isEmpty()) return null;
        double[] out = lane.endTangentXZ();
        float[] w = new float[succ.size()];
        for (int i = 0; i < succ.size(); i++) {
            double[] in = succ.get(i).startTangentXZ();
            double dot = (out != null && in != null) ? out[0] * in[0] + out[1] * in[1] : 1.0;
            double half = (dot + 1.0) / 2.0;
            w[i] = (float) (half * half + 0.05);
        }
        return succ.get(WeightedPick.pick(succ.size(), w, GD.randf()));
    }

    private double targetSpeed(Lane lane) {
        double lim = lane instanceof PathLaneRoute p && p.speedLimit > 0f ? p.speedLimit / 3.6 : DEFAULT_SPEED;
        return lim * SPEED_SHARE * (0.9 + 0.2 * rng.nextDouble());
    }

    private void spawn(Vector3 eye, double inner, Camera3D cam) {
        ZoneManager zm = ZoneManager.get();
        if (zm == null || cars.size() >= budget) return;
        List<Lane> pool = new ArrayList<>();
        for (Lane l : zm.registeredLanes()) {
            if (l instanceof PathLaneRoute p && (p.isRail() || !GD.isInstanceValid(p))) continue;
            Vector3 e = l.entryPoint();
            if (e == null) continue;
            double d = Math.hypot(e.getX() - eye.getX(), e.getZ() - eye.getZ());
            if (d < farRadius + l.total() && d + l.total() > inner) pool.add(l);
        }
        diag = "lanes " + zm.registeredLanes().size() + ", in ring " + pool.size() + ", models " + modelIndex;
        if (pool.isEmpty()) return;
        for (int tries = 0; tries < 24 && cars.size() < budget; tries++) {
            Lane l = pool.get(rng.nextInt(pool.size()));
            double s = rng.nextDouble() * l.total();
            Vector3 p = l.pointAtLength(s);
            double d = Math.hypot(p.getX() - eye.getX(), p.getZ() - eye.getZ());
            if (d < inner + 30.0 || d > farRadius - 30.0) continue;
            if (d < hiddenSpawnDistance && cam.isPositionInFrustum(p)) continue;
            boolean crowded = false;
            for (Car o : cars) if (o.lane == l && Math.abs(o.s - s) < 2.0 * GAP) { crowded = true; break; }
            if (crowded) continue;
            Car c = new Car();
            c.lane = l;
            c.s = s;
            c.target = targetSpeed(l);
            c.v = c.target;
            c.model = model(VehicleModels.trafficScene("civilian", rng.nextDouble()));
            if (c.model >= 0) cars.add(c);
        }
    }

    /** The draw slot of a model scene path (its `assets/vehicles/<ID>.glb` merged into one mesh), or -1. */
    private int model(String scenePath) {
        String file = scenePath.substring(scenePath.lastIndexOf('/') + 1);
        String id = file.endsWith(".tscn") ? file.substring(0, file.length() - 5) : file;
        Integer k = modelIndex.get(id);
        if (k != null) return k;
        int idx = -1;
        Mesh mesh = mergedMesh("res://assets/vehicles/" + id + ".glb");
        if (mesh != null) {
            MultiMesh mm = new MultiMesh();
            mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);
            mm.setMesh(mesh);
            mm.setInstanceCount(budget);
            mm.setVisibleInstanceCount(0);
            MultiMeshInstance3D mi = new MultiMeshInstance3D();
            mi.setName("Far_" + id);
            mi.setMultimesh(mm);
            mi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
            mi.setExtraCullMargin(16384f);      // the instances span the ring; the default AABB is the origin's
            addChild(mi);
            idx = draws.size();
            draws.add(mi);
            modelIds.add(id);
        }
        modelIndex.put(id, idx);
        return idx;
    }

    /** Every mesh of a model scene, transformed into its root's frame and merged per material: one draw per model. */
    private static Mesh mergedMesh(String path) {
        if (!ResourceLoader.INSTANCE.exists(path, "")) return null;
        var res = GD.load(path);
        if (!(res instanceof PackedScene ps)) return null;
        Node root = ps.instantiate();
        if (!(root instanceof Node3D r3)) { if (root != null) root.free(); return null; }
        Map<Object, SurfaceTool> byMat = new java.util.LinkedHashMap<>();
        List<MeshInstance3D> meshes = new ArrayList<>();
        collect(root, meshes);
        Transform3D rootInv = r3.getTransform().affineInverse();
        for (MeshInstance3D mi : meshes) {
            Mesh m = mi.getMesh();
            if (m == null) continue;
            Transform3D xf = rootInv.times(relative(mi, r3));
            for (int i = 0; i < m.getSurfaceCount(); i++) {
                var mat = mi.getSurfaceOverrideMaterial(i) != null ? mi.getSurfaceOverrideMaterial(i) : m.surfaceGetMaterial(i);
                Object key = mat == null ? "none" : mat;
                SurfaceTool st = byMat.computeIfAbsent(key, kk -> { SurfaceTool t = new SurfaceTool(); return t; });
                st.appendFrom(m, i, xf);
            }
        }
        ArrayMesh out = new ArrayMesh();
        for (Map.Entry<Object, SurfaceTool> e : byMat.entrySet()) {
            SurfaceTool st = e.getValue();
            if (e.getKey() instanceof godot.api.Material mt) st.setMaterial(mt);
            st.commit(out);
        }
        root.free();
        return out.getSurfaceCount() > 0 ? out : null;
    }

    private static void collect(Node n, List<MeshInstance3D> out) {
        if (n instanceof MeshInstance3D mi && mi.isVisible()) out.add(mi);
        for (int i = 0; i < n.getChildCount(); i++) collect(n.getChild(i), out);
    }

    /** `n`'s transform in `root`'s frame (the node is not in the tree: the parent chain, composed). */
    private static Transform3D relative(Node3D n, Node3D root) {
        Transform3D t = n.getTransform();
        Node p = n.getParent();
        while (p != null && p != root) {
            if (p instanceof Node3D p3) t = p3.getTransform().times(t);
            p = p.getParent();
        }
        return t;
    }

    private void draw() {
        int m = draws.size();
        if (m == 0) return;
        int[] count = new int[m];
        float[][] buf = new float[m][];
        for (int i = 0; i < m; i++) buf[i] = new float[12 * Math.max(1, budget)];
        for (Car c : cars) {
            int k = c.model;
            if (k < 0 || k >= m || count[k] >= budget) continue;
            Vector3 p = c.lane.pointAtLength(c.s);
            Vector3 q = c.lane.pointAtLength(Math.min(c.lane.total(), c.s + 2.0));
            double dx = q.getX() - p.getX(), dz = q.getZ() - p.getZ();
            double L = Math.hypot(dx, dz);
            if (L < 1e-6) { Vector3 b = c.lane.pointAtLength(Math.max(0.0, c.s - 2.0)); dx = p.getX() - b.getX(); dz = p.getZ() - b.getZ(); L = Math.hypot(dx, dz); }
            if (L < 1e-6) { dx = 0; dz = -1; L = 1; }
            // forward is -Z: basis columns x = right, z = back
            double fx = dx / L, fz = dz / L;
            double bx = -fx, bz = -fz;          // z axis (back)
            double rx = bz, rz = -bx;           // x axis = up x z: right of travel
            float[] b = buf[k];
            int o = 12 * count[k]++;
            // MultiMesh 3D transform buffer: row-major 3x4 (basis rows, then origin in the 4th column)
            b[o] = (float) rx;  b[o + 1] = 0f; b[o + 2] = (float) bx;  b[o + 3] = (float) p.getX();
            b[o + 4] = 0f;      b[o + 5] = 1f; b[o + 6] = 0f;          b[o + 7] = (float) p.getY();
            b[o + 8] = (float) rz; b[o + 9] = 0f; b[o + 10] = (float) bz; b[o + 11] = (float) p.getZ();
        }
        for (int i = 0; i < m; i++) {
            MultiMesh mm = draws.get(i).getMultimesh();
            mm.setBuffer(new PackedFloat32Array(buf[i]));
            mm.setVisibleInstanceCount(count[i]);
        }
    }
}
