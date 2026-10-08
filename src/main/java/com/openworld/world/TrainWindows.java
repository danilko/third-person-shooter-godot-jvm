package com.openworld.world;

import godot.api.ArrayMesh;
import godot.api.Material;
import godot.api.Mesh;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.AABB;
import godot.core.PackedInt32Array;
import godot.core.PackedVector2Array;
import godot.core.PackedVector3Array;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.VariantArray;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * A train car's windows, one piece each (PLAN.md 1g g, user 2026-10-07: "trains too ... each glass a separate piece"):
 * the car Body's {@code M_Train_glass} surface is split ONCE per car model into its connected islands (one per window,
 * welded by position), the surface is hidden, and every island is drawn by its own {@code Win<n>} MeshInstance3D
 * under the car's model, so one window can go. The car keeps its single box collider: a shot that hit the car asks
 * {@link #windowAt} whether it struck a window (the car's own glass rule then applies, in WeaponItem.throughGlass).
 * Cosmetic state, local per peer (feedback "cosmetic state needs no sync"): every peer breaks a window from its own
 * trace of the shot; the damage beyond it is the host's.
 */
public final class TrainWindows {

    public static final String GLASS = "M_Train_glass";

    /** One window of a car model: its mesh and bounds in the MODEL's frame. */
    record Win(ArrayMesh mesh, AABB box) {}

    private static final Map<String, List<Win>> MODELS = new HashMap<>();
    private static final Map<String, Material> MATS = new HashMap<>();

    private TrainWindows() {}

    /** Split {@code model}'s glass into windows (cached per {@code key}), hide the surface, and add the window nodes.
     *  Returns the window nodes, index = window. */
    public static List<MeshInstance3D> attach(Node3D model, String key) {
        List<MeshInstance3D> out = new ArrayList<>();
        MeshInstance3D body = null;
        int surf = -1;
        for (Node n : model.findChildren("*_Body", "MeshInstance3D", true, false)) {
            if (n instanceof MeshInstance3D mi && mi.getMesh() != null) {
                for (int s = 0; s < mi.getMesh().getSurfaceCount(); s++) {
                    Material m = mi.getMesh().surfaceGetMaterial(s);
                    if (m != null && GLASS.equals(m.getName())) { body = mi; surf = s; }
                }
            }
        }
        if (body == null) return out;
        List<Win> wins = MODELS.get(key);
        if (wins == null) {
            wins = islands(body, surf, model);
            MODELS.put(key, wins);
            MATS.put(key, body.getMesh().surfaceGetMaterial(surf));
        }
        body.setSurfaceOverrideMaterial(surf, com.openworld.carrier.vehicle.Glass.hidden());
        int i = 0;
        for (Win w : wins) {
            MeshInstance3D mi = new MeshInstance3D();
            mi.setName(new StringName("Win" + i++));
            mi.setMesh(w.mesh());
            mi.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
            model.addChild(mi);
            out.add(mi);
        }
        return out;
    }

    /** The window of {@code model} (its key) at world {@code point}, within {@code reach} m of its glass; -1 = none. */
    public static int windowAt(Node3D model, String key, Vector3 point, double reach) {
        List<Win> wins = MODELS.get(key);
        if (wins == null || model == null || !GD.isInstanceValid(model)) return -1;
        Vector3 local = model.getGlobalTransform().affineInverse().times(point);
        int best = -1;
        double bd = Double.MAX_VALUE;
        for (int i = 0; i < wins.size(); i++) {
            AABB b = wins.get(i).box();
            double d = distance(b, local);
            if (d <= reach && d < bd) { bd = d; best = i; }
        }
        return best;
    }

    private static double distance(AABB b, Vector3 p) {
        Vector3 lo = b.getPosition(), hi = b.getEnd();
        double dx = Math.max(0, Math.max(lo.getX() - p.getX(), p.getX() - hi.getX()));
        double dy = Math.max(0, Math.max(lo.getY() - p.getY(), p.getY() - hi.getY()));
        double dz = Math.max(0, Math.max(lo.getZ() - p.getZ(), p.getZ() - hi.getZ()));
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    @SuppressWarnings("unchecked")
    private static List<Win> islands(MeshInstance3D body, int surf, Node3D model) {
        List<Win> out = new ArrayList<>();
        VariantArray<Object> arr = body.getMesh().surfaceGetArrays(surf);
        PackedVector3Array v = (PackedVector3Array) arr.get((int) Mesh.ArrayType.VERTEX.getValue());
        Object nObj = arr.get((int) Mesh.ArrayType.NORMAL.getValue());
        Object uObj = arr.get((int) Mesh.ArrayType.TEX_UV.getValue());
        Object iObj = arr.get((int) Mesh.ArrayType.INDEX.getValue());
        Vector3[] vv = v.toVector3Array();
        Vector3[] nrm = nObj instanceof PackedVector3Array p ? p.toVector3Array() : null;
        Vector2[] uv = uObj instanceof PackedVector2Array p ? p.toVector2Array() : null;
        int vc = vv.length;
        int[] tris;
        int[] ia0 = iObj instanceof PackedInt32Array ia ? ia.toIntArray() : null;
        if (ia0 != null && ia0.length > 0) {
            tris = ia0;
        } else {
            tris = new int[vc];
            for (int k = 0; k < vc; k++) tris[k] = k;
        }
        // the body's frame relative to the model (the glb's node transforms; the model may not be in the tree yet)
        Transform3D xf = body.getTransform();
        for (Node n = body.getParent(); n != null && n != model; n = n.getParent())
            if (n instanceof Node3D n3) xf = n3.getTransform().times(xf);   // a fresh copy each call: times() mutates it
        Vector3[] w = new Vector3[vc];
        for (int k = 0; k < vc; k++) w[k] = xf.times(vv[k]);
        int[] par = new int[vc];
        Map<Long, Integer> weld = new HashMap<>();
        for (int k = 0; k < vc; k++) {
            long key = (Math.round(w[k].getX() * 1000) & 0x1FFFFF) << 42 | (Math.round(w[k].getY() * 1000) & 0x1FFFFF) << 21
                    | (Math.round(w[k].getZ() * 1000) & 0x1FFFFF);
            Integer f = weld.putIfAbsent(key, k);
            par[k] = f == null ? k : f;
        }
        for (int t = 0; t + 2 < tris.length; t += 3) {
            int a = find(par, tris[t]);
            for (int c = 1; c < 3; c++) {
                int b = find(par, tris[t + c]);
                if (a != b) par[b] = a;
            }
        }
        Map<Integer, List<Integer>> groups = new HashMap<>();
        for (int t = 0; t + 2 < tris.length; t += 3) groups.computeIfAbsent(find(par, tris[t]), x -> new ArrayList<>()).add(t);
        Material mat = body.getMesh().surfaceGetMaterial(surf);
        for (List<Integer> g : groups.values()) {
            PackedVector3Array pv = new PackedVector3Array(), pn = new PackedVector3Array();
            PackedVector2Array pu = new PackedVector2Array();
            Vector3 lo = null, hi = null;
            for (int t : g) {
                for (int c = 0; c < 3; c++) {
                    int k = tris[t + c];
                    Vector3 p = w[k];
                    pv.append(p);
                    pn.append(nrm != null ? xf.getBasis().times(nrm[k]).normalized() : new Vector3(0, 1, 0));
                    pu.append(uv != null ? uv[k] : new Vector2(0, 0));
                    lo = lo == null ? p : new Vector3(Math.min(lo.getX(), p.getX()), Math.min(lo.getY(), p.getY()), Math.min(lo.getZ(), p.getZ()));
                    hi = hi == null ? p : new Vector3(Math.max(hi.getX(), p.getX()), Math.max(hi.getY(), p.getY()), Math.max(hi.getZ(), p.getZ()));
                }
            }
            VariantArray<Object> a2 = new VariantArray<>(Object.class);
            a2.resize((int) Mesh.ArrayType.MAX.getValue());
            a2.set((int) Mesh.ArrayType.VERTEX.getValue(), pv);
            a2.set((int) Mesh.ArrayType.NORMAL.getValue(), pn);
            a2.set((int) Mesh.ArrayType.TEX_UV.getValue(), pu);
            ArrayMesh m = new ArrayMesh();
            m.addSurfaceFromArrays(Mesh.PrimitiveType.TRIANGLES, a2);
            m.surfaceSetMaterial(0, mat);
            out.add(new Win(m, new AABB(lo, hi.minus(lo))));
        }
        return out;
    }

    private static int find(int[] par, int x) {
        while (par[x] != x) { par[x] = par[par[x]]; x = par[x]; }
        return x;
    }

    /** Static state holds Godot resources: cleared at shutdown (GameManager._exitTree). */
    public static void clear() { MODELS.clear(); MATS.clear(); }
}
