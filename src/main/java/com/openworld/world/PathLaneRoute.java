package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Curve3D;
import godot.api.Node3D;
import godot.api.Path3D;
import godot.core.PackedVector3Array;
import godot.core.Vector3;

/**
 * A directional lane backed by a native {@link Path3D}/{@link Curve3D} instead of the
 * {@link VehicleRoute} Marker3D-list + hand-rolled Catmull-Rom smoothing — built at bake time by
 * {@link WorldBaker} from a Blender-exported {@code .lanekit.json} sidecar (see
 * {@code assets/world_source/lib/intersection_kit.py}). Implements {@link Lane}, so it plugs into
 * the existing {@link LaneGraph} (endpoint-proximity junction derivation) and
 * {@link com.openworld.ai.vehicle.VehicleAIController} (arc-length lane following) unchanged —
 * a car already goes straight or turns depending on which successor lane it lands on at a
 * junction, via the same mechanism that already drives a {@link VehicleRoute} network; no new AI
 * decision-making.
 *
 * <p><b>Static/baked only.</b> Unlike {@code VehicleRoute} (whose marker children an editor user
 * might still be reshaping), a {@code PathLaneRoute}'s curve is fixed the moment it's built — its
 * arc-length cache is computed once in {@link #_ready()}, not rebuilt on demand.
 *
 * <p><b>Connectivity for this route type is entirely geometry-derived</b> ({@link LaneGraph}) —
 * {@link #pickNextRoute()}/{@link #resolveRoute(String)} always return null; there is no
 * explicit-successor string list to parse (unlike {@code VehicleRoute.nextRoutes}). It also does
 * <b>not</b> register with {@link WorldZoneManager}'s route registry — that registry backs
 * ambient-traffic zone spawn configs, an intentionally separate future step for this route type.
 */
@RegisterClass(className = "PathLaneRoute")
public class PathLaneRoute extends Node3D implements Lane {

    /** True = a closed ring. False = a one-way lane ending in {@link #endBehavior}. */
    @Export @RegisterProperty public boolean loop = false;

    /** Turn movement this lane makes through a junction — "L"/"S"/"R", "" on a plain lane. */
    @Export @RegisterProperty public String turn = "";

    /** Compass/arm label a car on this connector arrives from — "" on a plain lane. */
    @Export @RegisterProperty public String approach = "";

    /** Right-side lane offset (m) — reserved, mirrors {@code VehicleRoute.laneOffset}; a
     *  {@code PathLaneRoute}'s curve is already the exact per-lane centerline (baked in Blender),
     *  so this is 0 unless a future consumer wants an additional runtime offset. */
    @Export @RegisterProperty public float laneOffset = 0f;

    /** Lane width (m) — informational, from the exported sidecar's {@code lane_width}. */
    @Export @RegisterProperty public float laneWidth = 3.5f;

    /** End-of-lane behaviour: {@link VehicleRoute#END_CHAIN} / {@link VehicleRoute#END_UTURN} /
     *  {@link VehicleRoute#END_DESPAWN}. */
    @Export @RegisterProperty public String endBehavior = VehicleRoute.END_CHAIN;

    /** Optional explicit return lane name for {@link VehicleRoute#END_UTURN} (else derived from
     *  {@link LaneGraph}) — not populated by the current sidecar export; reserved. */
    @Export @RegisterProperty public String returnRoute = "";

    private static final String PATH_CHILD_NAME = "Path3D";

    private Curve3D curve;
    private Vector3[] bakedGlobal;   // baked points pre-converted to world space (identity-transform fast path still correct)
    private double[]  cum;
    private double     totalLen;

    public PathLaneRoute() { super(); }

    @RegisterFunction
    @Override
    public void _ready() {
        var pathNode = getNodeOrNull(PATH_CHILD_NAME);
        if (pathNode instanceof Path3D p3d) curve = p3d.getCurve();
        ensureBaked();
    }

    /** The backing {@link Curve3D}, or null if the expected "Path3D" child is missing/unset. */
    public Curve3D getCurveResource() { return curve; }

    private Path3D pathChild() {
        var n = getNodeOrNull(PATH_CHILD_NAME);
        return n instanceof Path3D p3d ? p3d : null;
    }

    // ── Baked arc-length cache (built once — this route is static content) ──────────────────

    private void ensureBaked() {
        if (bakedGlobal != null) return;
        Path3D p3d = pathChild();
        if (curve == null || p3d == null) { bakedGlobal = new Vector3[0]; cum = new double[0]; totalLen = 0; return; }
        PackedVector3Array pts = curve.getBakedPoints();
        int n = pts.getSize();
        bakedGlobal = new Vector3[Math.max(n, 1)];
        if (n == 0) { bakedGlobal[0] = p3d.toGlobal(new Vector3(0, 0, 0)); cum = new double[]{0}; totalLen = 0; return; }
        for (int i = 0; i < n; i++) bakedGlobal[i] = p3d.toGlobal(pts.get(i));
        cum = new double[n];
        totalLen = 0;
        for (int i = 1; i < n; i++) { totalLen += horiz(bakedGlobal[i - 1], bakedGlobal[i]); cum[i] = totalLen; }
        if (loop) totalLen += horiz(bakedGlobal[n - 1], bakedGlobal[0]);
    }

    // ── Lane implementation ──────────────────────────────────────────────────────────────────

    @Override
    public Vector3 startPoint() {
        Path3D p3d = pathChild();
        if (curve == null || p3d == null || curve.getPointCount() == 0) return null;
        return p3d.toGlobal(curve.getPointPosition(0));
    }

    @Override
    public Vector3 endPoint() {
        Path3D p3d = pathChild();
        if (curve == null || p3d == null || curve.getPointCount() == 0) return null;
        return p3d.toGlobal(curve.getPointPosition(curve.getPointCount() - 1));
    }

    @Override
    public double[] startTangentXZ() { return tangentXZ(true); }

    @Override
    public double[] endTangentXZ() { return tangentXZ(false); }

    private double[] tangentXZ(boolean atStart) {
        Path3D p3d = pathChild();
        if (curve == null || p3d == null) return null;
        int n = curve.getPointCount();
        if (n < 2) return null;
        Vector3 a = p3d.toGlobal(curve.getPointPosition(atStart ? 0 : n - 2));
        Vector3 b = p3d.toGlobal(curve.getPointPosition(atStart ? 1 : n - 1));
        double dx = b.getX() - a.getX(), dz = b.getZ() - a.getZ();
        double len = Math.sqrt(dx * dx + dz * dz);
        return len < 1e-9 ? null : new double[]{dx / len, dz / len};
    }

    @Override
    public boolean isLoop() { return loop; }

    @Override
    public double total() { ensureBaked(); return totalLen; }

    @Override
    public Vector3 pointAtLength(double s) {
        ensureBaked();
        int m = bakedGlobal.length;
        if (m <= 1 || totalLen <= 1e-6) return m == 0 ? new Vector3() : bakedGlobal[0];
        if (loop) { s %= totalLen; if (s < 0) s += totalLen; }
        else s = Math.max(0, Math.min(totalLen, s));
        for (int i = 1; i < m; i++) {
            if (s <= cum[i]) {
                double segLen = cum[i] - cum[i - 1];
                return lerp(bakedGlobal[i - 1], bakedGlobal[i], segLen <= 1e-9 ? 0 : (s - cum[i - 1]) / segLen);
            }
        }
        if (loop) {
            double segLen = totalLen - cum[m - 1];
            return lerp(bakedGlobal[m - 1], bakedGlobal[0], segLen <= 1e-9 ? 0 : (s - cum[m - 1]) / segLen);
        }
        return bakedGlobal[m - 1];
    }

    @Override
    public double lengthAtNearest(Vector3 pos, double aroundS, double window) {
        ensureBaked();
        int m = bakedGlobal.length;
        if (m <= 1) return 0;
        double best = aroundS < 0 ? 0 : aroundS, bestD = Double.MAX_VALUE;
        for (int i = 0; i < m; i++) {
            if (aroundS >= 0) {
                double d = Math.abs(cum[i] - aroundS);
                if (loop) d = Math.min(d, totalLen - d);
                if (d > window) continue;
            }
            double dsq = horizSq(pos, bakedGlobal[i]);
            if (dsq < bestD) { bestD = dsq; best = cum[i]; }
        }
        return best;
    }

    @Override
    public Lane pickNextRoute() { return null; }   // geometry-derived connectivity only (LaneGraph)

    @Override
    public Lane resolveRoute(String name) { return null; }

    @Override public String getTurn() { return turn; }
    @Override public String getApproach() { return approach; }
    @Override public String getEndBehavior() { return endBehavior; }
    @Override public String getReturnRoute() { return returnRoute; }

    // ── Geometry helpers (deliberately duplicated from VehicleRoute's identical windowed-search
    //    loop rather than extracted into a shared helper — small, self-contained, and this is the
    //    only other call site) ────────────────────────────────────────────────────────────────

    private static Vector3 lerp(Vector3 a, Vector3 b, double t) {
        return new Vector3(a.getX() + (b.getX() - a.getX()) * t,
                           a.getY() + (b.getY() - a.getY()) * t,
                           a.getZ() + (b.getZ() - a.getZ()) * t);
    }

    private static double horiz(Vector3 a, Vector3 b) { return Math.sqrt(horizSq(a, b)); }

    private static double horizSq(Vector3 a, Vector3 b) {
        double dx = a.getX() - b.getX(), dz = a.getZ() - b.getZ();
        return dx * dx + dz * dz;
    }
}
