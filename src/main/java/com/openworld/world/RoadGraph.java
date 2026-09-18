package com.openworld.world;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

/**
 * The whole road network as a routable graph (PLAN.md 4.7) — engine-free, so the GPS route is
 * unit-tested against the real {@code .lanekit.json} files.
 *
 * <p><b>Why it is not {@link LaneGraph}:</b> that graph is built from the {@link Lane} NODES in the
 * scene, and a streamed zone's lanes exist only while the zone is loaded, so a route to a waypoint
 * in an unloaded zone would have nothing to walk. This graph is built from the lanekit sidecars —
 * the same record the baker turned into those nodes — so it covers the whole world regardless of
 * streaming. The successor rule is the runtime's: a lane's authored {@code next} list if it has one,
 * else every lane starting within {@link LaneGraph#JUNCTION_RADIUS} of its end minus the direct
 * reverse ({@link LaneGraph#successorsOf}). A route therefore only ever makes a movement a car
 * could make.
 *
 * <p><b>The search.</b> Dijkstra over lanes, where {@code E[L]} is the cost (metres) to be at the
 * START of lane L. A lane change onto an {@code inner_lane}/{@code outer_lane} neighbour costs
 * {@link #LANE_CHANGE_COST}: a GPS line is about which ROAD to take, but a left turn is only
 * reachable from the lane that owns its connector, and without the lateral edge those routes would
 * not exist. The start and the goal are projections onto lanes; both take every lane within
 * {@link #CANDIDATE_SLACK} of the nearest one, so a player standing on a two-way street is not sent
 * to the end of the wrong carriageway to turn round. Walking to the road costs its distance.
 *
 * <p>Coordinates are plain {@code double}s (x, y, z in Godot's Y-up world frame) — no Godot types.
 */
public final class RoadGraph {

    /** A lane change between two parallel lanes, in metres of equivalent driving. */
    public static final double LANE_CHANGE_COST = 15.0;
    /** Lanes whose snap distance is within this of the nearest one are also start/goal candidates. */
    public static final double CANDIDATE_SLACK = 10.0;
    /** Drawing tolerance: the route's map polyline keeps a point only where it bends more than this. */
    public static final double DRAW_TOLERANCE = 0.5;

    /** One directional lane. Points are in WORLD space (the sidecar's frame already applied). */
    public static final class Lane {
        public final String id;
        public final double[] x, y, z;
        /** Cumulative arc length at each point (3D). */
        public final double[] cum;
        public final float width;
        public final String zoneId;
        public final String roadName;
        final List<String> nextIds;
        final String innerId, outerId;
        final List<Lane> succ = new ArrayList<>();
        final List<Lane> pred = new ArrayList<>();
        final List<Lane> side = new ArrayList<>();
        private double[] bounds;

        Lane(String id, double[] x, double[] y, double[] z, float width, String zoneId, String roadName,
             List<String> nextIds, String innerId, String outerId) {
            this.id = id; this.x = x; this.y = y; this.z = z; this.width = width;
            this.zoneId = zoneId; this.roadName = roadName;
            this.nextIds = nextIds; this.innerId = innerId; this.outerId = outerId;
            cum = new double[x.length];
            for (int i = 1; i < x.length; i++) {
                double dx = x[i] - x[i - 1], dy = y[i] - y[i - 1], dz = z[i] - z[i - 1];
                cum[i] = cum[i - 1] + Math.sqrt(dx * dx + dy * dy + dz * dz);
            }
        }

        public double length() { return cum[cum.length - 1]; }
        public int pointCount() { return x.length; }
        public List<Lane> successors() { return Collections.unmodifiableList(succ); }
        public List<Lane> neighbours() { return Collections.unmodifiableList(side); }

        /** {minX, minZ, maxX, maxZ} of the lane in plan. Cached. */
        public double[] boundsXZ() {
            if (bounds == null) {
                double[] b = {Double.MAX_VALUE, Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE};
                for (int i = 0; i < x.length; i++) {
                    b[0] = Math.min(b[0], x[i]); b[1] = Math.min(b[1], z[i]);
                    b[2] = Math.max(b[2], x[i]); b[3] = Math.max(b[3], z[i]);
                }
                bounds = b;
            }
            return bounds;
        }

        /** Point at arc length {@code s} (clamped). */
        public double[] at(double s) {
            if (s <= 0) return new double[]{x[0], y[0], z[0]};
            int n = x.length;
            if (s >= cum[n - 1]) return new double[]{x[n - 1], y[n - 1], z[n - 1]};
            int i = segmentAt(s);
            double seg = cum[i + 1] - cum[i];
            double t = seg < 1e-9 ? 0 : (s - cum[i]) / seg;
            return new double[]{x[i] + (x[i + 1] - x[i]) * t, y[i] + (y[i + 1] - y[i]) * t,
                    z[i] + (z[i + 1] - z[i]) * t};
        }

        private int segmentAt(double s) {
            int lo = 0, hi = cum.length - 2;
            while (lo < hi) {
                int mid = (lo + hi + 1) >>> 1;
                if (cum[mid] <= s) lo = mid; else hi = mid - 1;
            }
            return lo;
        }
    }

    /** Where a position lands on a lane. */
    public static final class Snap {
        public final Lane lane;
        public final double offset;
        public final double distance;
        public final double[] point;
        Snap(Lane lane, double offset, double distance, double[] point) {
            this.lane = lane; this.offset = offset; this.distance = distance; this.point = point;
        }
    }

    /** One stretch of a route: {@code lane} from {@code from} to {@code to} metres along it. */
    public static final class Leg {
        public final Lane lane;
        public final double from, to;
        Leg(Lane lane, double from, double to) { this.lane = lane; this.from = from; this.to = to; }
    }

    /** A route: the legs in driving order, and the polyline through them. */
    public static final class Route {
        public final List<Leg> legs;
        /** {x0, y0, z0, x1, ...} along the legs. */
        public final double[] points;
        /** Metres along the lanes (lane changes add no length). */
        public final double length;
        /** The search cost (length + lane-change and walk-to-road terms). */
        public final double cost;
        /** Where the route leaves the road for the destination. */
        public final double[] goalPoint;

        Route(List<Leg> legs, double[] points, double length, double cost, double[] goalPoint) {
            this.legs = legs; this.points = points; this.length = length; this.cost = cost;
            this.goalPoint = goalPoint;
        }

        private double[] drawXZ;

        public int pointCount() { return points.length / 3; }

        /** {x0, z0, x1, z1, ...} simplified for the map (Douglas-Peucker in XZ). Cached, so a map
         *  redrawn every frame hands over the same few points instead of every lane sample. */
        public double[] drawXZ() {
            if (drawXZ == null) {
                int n = pointCount();
                double[] xs = new double[n], zs = new double[n];
                for (int i = 0; i < n; i++) { xs[i] = points[3 * i]; zs[i] = points[3 * i + 2]; }
                drawXZ = n < 2 ? new double[]{xs.length > 0 ? xs[0] : 0, zs.length > 0 ? zs[0] : 0}
                        : simplifyXZ(xs, zs, DRAW_TOLERANCE);
            }
            return drawXZ;
        }

        public List<String> laneIds() {
            List<String> out = new ArrayList<>();
            for (Leg l : legs) out.add(l.lane.id);
            return out;
        }

        /** Arc length along the route of the point nearest {@code p} in XZ, searching every segment. */
        public double progressOf(double px, double pz) {
            return nearest(px, pz)[0];
        }

        /** XZ distance from {@code p} to the route. */
        public double distanceXZ(double px, double pz) {
            return nearest(px, pz)[1];
        }

        /** The point {@code lookahead} metres along the route past the point nearest {@code p}. */
        public double[] steerPoint(double px, double pz, double lookahead) {
            return pointAt(progressOf(px, pz) + lookahead);
        }

        /** Point at arc length {@code s} along the polyline (XZ+Y), clamped to the ends. */
        public double[] pointAt(double s) {
            int n = pointCount();
            if (n == 0) return goalPoint;
            double acc = 0;
            for (int i = 0; i + 1 < n; i++) {
                double seg = dist3(i, i + 1);
                if (acc + seg >= s) {
                    double t = seg < 1e-9 ? 0 : (s - acc) / seg;
                    return new double[]{lerp(i, i + 1, 0, t), lerp(i, i + 1, 1, t), lerp(i, i + 1, 2, t)};
                }
                acc += seg;
            }
            return new double[]{points[3 * (n - 1)], points[3 * (n - 1) + 1], points[3 * (n - 1) + 2]};
        }

        /** {progress, distanceXZ} of the nearest point. */
        private double[] nearest(double px, double pz) {
            int n = pointCount();
            double best = Double.MAX_VALUE, bestS = 0, acc = 0;
            for (int i = 0; i + 1 < n; i++) {
                double ax = points[3 * i], az = points[3 * i + 2];
                double bx = points[3 * i + 3], bz = points[3 * i + 5];
                double dx = bx - ax, dz = bz - az;
                double l2 = dx * dx + dz * dz;
                double t = l2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / l2));
                double qx = ax + dx * t - px, qz = az + dz * t - pz;
                double d = qx * qx + qz * qz;
                double seg = dist3(i, i + 1);
                if (d < best) { best = d; bestS = acc + seg * t; }
                acc += seg;
            }
            if (n == 1) {
                double dx = points[0] - px, dz = points[2] - pz;
                best = dx * dx + dz * dz;
            }
            return new double[]{bestS, Math.sqrt(best)};
        }

        private double dist3(int a, int b) {
            double dx = points[3 * b] - points[3 * a], dy = points[3 * b + 1] - points[3 * a + 1],
                    dz = points[3 * b + 2] - points[3 * a + 2];
            return Math.sqrt(dx * dx + dy * dy + dz * dz);
        }

        private double lerp(int a, int b, int c, double t) {
            return points[3 * a + c] + (points[3 * b + c] - points[3 * a + c]) * t;
        }
    }

    private final Map<String, Lane> lanes = new LinkedHashMap<>();
    private boolean finished = false;
    private RoadIndex index;

    /** Attach a cell index (built for THIS graph) so {@link #snaps} looks up its candidate lanes in
     *  constant time instead of measuring every lane. Null detaches it. */
    public void setIndex(RoadIndex idx) { index = idx; }
    public RoadIndex index() { return index; }

    /** Add one lane as-is (the bake reader). Its successors are resolved by {@link #finish}, by the
     *  same rule as a lane read from a sidecar. */
    void addLane(String id, double[] x, double[] y, double[] z, float width, String zoneId, String roadName,
                 List<String> nextIds, String innerId, String outerId) {
        if (lanes.containsKey(id) || x.length < 2) return;
        lanes.put(id, new Lane(id, x, y, z, width, zoneId, roadName, nextIds, innerId, outerId));
        finished = false;
        index = null;
    }

    public Collection<Lane> lanes() { return Collections.unmodifiableCollection(lanes.values()); }
    public Lane lane(String id) { return lanes.get(id); }
    public int laneCount() { return lanes.size(); }

    /**
     * Add every lane of a parsed {@code .lanekit.json} document. {@code xf} is the frame the piece is
     * placed in, as {@code {m00, m01, m02, m10, m11, m12, m20, m21, m22, ox, oy, oz}} with
     * {@code world = M·p + o} (null = identity). Returns the number of lanes added; a lane id already
     * present is skipped (the first sidecar to name it wins).
     */
    @SuppressWarnings("unchecked")
    public int addLanekit(Object doc, double[] xf) {
        if (!(doc instanceof Map<?, ?> m) || !(m.get("lanes") instanceof List<?> arr)) return 0;
        int added = 0;
        for (Object o : arr) {
            if (!(o instanceof Map<?, ?> d)) continue;
            Object idObj = d.get("id");
            if (!(idObj instanceof String id) || lanes.containsKey(id)) continue;
            if (!(d.get("points") instanceof List<?> pts) || pts.size() < 2) continue;
            int n = pts.size();
            double[] x = new double[n], y = new double[n], z = new double[n];
            int k = 0;
            for (Object p : pts) {
                if (!(p instanceof List<?> v) || v.size() < 3) continue;
                double px = num(v.get(0)), py = num(v.get(1)), pz = num(v.get(2));
                if (xf != null) {
                    double wx = xf[0] * px + xf[1] * py + xf[2] * pz + xf[9];
                    double wy = xf[3] * px + xf[4] * py + xf[5] * pz + xf[10];
                    double wz = xf[6] * px + xf[7] * py + xf[8] * pz + xf[11];
                    px = wx; py = wy; pz = wz;
                }
                x[k] = px; y[k] = py; z[k] = pz; k++;
            }
            if (k < 2) continue;
            if (k < n) {
                x = java.util.Arrays.copyOf(x, k); y = java.util.Arrays.copyOf(y, k); z = java.util.Arrays.copyOf(z, k);
            }
            List<String> next = new ArrayList<>();
            if (d.get("next") instanceof List<?> nl) for (Object s : nl) if (s instanceof String str) next.add(str);
            double w = d.get("lane_width") instanceof Double dw ? dw : 3.5;
            lanes.put(id, new Lane(id, x, y, z, (float) w, str(d.get("zone_id")), str(d.get("road_name")),
                    next, str(d.get("inner_lane")), str(d.get("outer_lane"))));
            added++;
        }
        finished = false;
        index = null;
        return added;
    }

    /** Resolve successors, predecessors and lane-change neighbours. Called lazily by {@link #route}. */
    public void finish() {
        if (finished) return;
        finished = true;
        for (Lane l : lanes.values()) { l.succ.clear(); l.pred.clear(); l.side.clear(); }
        // Proximity index over lane STARTS, for lanes that carry no authored successors.
        Map<Long, List<Lane>> starts = new HashMap<>();
        double cell = LaneGraph.JUNCTION_RADIUS;
        for (Lane l : lanes.values()) starts.computeIfAbsent(key(l.x[0], l.z[0], cell), k -> new ArrayList<>()).add(l);
        for (Lane l : lanes.values()) {
            if (!l.nextIds.isEmpty()) {
                for (String nid : l.nextIds) {
                    Lane s = lanes.get(nid);
                    if (s != null && s != l && !l.succ.contains(s)) l.succ.add(s);
                }
            } else {
                int e = l.x.length - 1;
                for (Lane s : near(starts, l.x[e], l.z[e], cell)) {
                    if (s == l || dXZ(s.x[0], s.z[0], l.x[e], l.z[e]) > LaneGraph.JUNCTION_RADIUS) continue;
                    int se = s.x.length - 1;
                    boolean reverse = dXZ(s.x[se], s.z[se], l.x[0], l.z[0]) <= LaneGraph.JUNCTION_RADIUS;
                    if (!reverse) l.succ.add(s);
                }
            }
            for (String sid : new String[]{l.innerId, l.outerId}) {
                Lane s = sid.isEmpty() ? null : lanes.get(sid);
                if (s != null && s != l && !l.side.contains(s)) l.side.add(s);
            }
        }
        for (Lane l : lanes.values()) {
            for (Lane s : l.succ) s.pred.add(l);
            for (Lane s : l.side) if (!s.side.contains(l)) s.side.add(l);   // make lane changes symmetric
        }
    }

    /** Every lane a position snaps to within {@link #CANDIDATE_SLACK} of the nearest, nearest first.
     *  {@code yWeight} 0 = plan distance only (a map click); 1 = full 3D (a body on a bridge). */
    public List<Snap> snaps(double px, double py, double pz, double yWeight) {
        if (index != null) {
            List<Lane> cand = index.candidates(px, pz);
            if (cand != null && !cand.isEmpty()) {
                List<Snap> out = collect(cand, px, py, pz, yWeight);
                // Exact whenever the nearest found is within the cell's plan bound; a body far above
                // the road (3D snap) can exceed it, and then only a full scan is exact.
                if (yWeight == 0 || out.get(0).distance <= index.upperBound(px, pz)) return out;
            }
        }
        return collect(lanes.values(), px, py, pz, yWeight);
    }

    /** {@link #snaps} measuring every lane — what the index must agree with. */
    List<Snap> snapsBrute(double px, double py, double pz, double yWeight) {
        return collect(lanes.values(), px, py, pz, yWeight);
    }

    private static List<Snap> collect(Collection<Lane> from, double px, double py, double pz, double yWeight) {
        List<Snap> all = new ArrayList<>();
        double bestD = Double.MAX_VALUE;
        for (Lane l : from) {
            Snap s = snap(l, px, py, pz, yWeight);
            all.add(s);
            bestD = Math.min(bestD, s.distance);
        }
        List<Snap> out = new ArrayList<>();
        for (Snap s : all) if (s.distance <= bestD + CANDIDATE_SLACK) out.add(s);
        out.sort((a, b) -> Double.compare(a.distance, b.distance));
        return out;
    }

    /** Nearest point of one lane to {@code p}. */
    public static Snap snap(Lane l, double px, double py, double pz, double yWeight) {
        double best = Double.MAX_VALUE, bestS = 0;
        double[] bestP = null;
        for (int i = 0; i + 1 < l.x.length; i++) {
            double ax = l.x[i], ay = l.y[i], az = l.z[i];
            double dx = l.x[i + 1] - ax, dy = l.y[i + 1] - ay, dz = l.z[i + 1] - az;
            double l2 = dx * dx + dz * dz;
            double t = l2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / l2));
            double qx = ax + dx * t, qy = ay + dy * t, qz = az + dz * t;
            double ex = qx - px, ey = (qy - py) * yWeight, ez = qz - pz;
            double d = ex * ex + ey * ey + ez * ez;
            if (d < best) {
                best = d;
                bestS = l.cum[i] + (l.cum[i + 1] - l.cum[i]) * t;
                bestP = new double[]{qx, qy, qz};
            }
        }
        return new Snap(l, bestS, Math.sqrt(best), bestP);
    }

    /**
     * The cheapest legal route from {@code from} (a body — snapped in 3D) to {@code to} (a map
     * click — snapped in plan). Null when the network is empty or no candidate goal lane is
     * reachable from any candidate start lane.
     */
    public Route route(double fx, double fy, double fz, double tx, double ty, double tz) {
        finish();
        if (lanes.isEmpty()) return null;
        List<Snap> starts = snaps(fx, fy, fz, 1.0);
        List<Snap> goals = snaps(tx, ty, tz, 0.0);

        // E[L] = cost to be at the START of L; prev = how we got there.
        Map<Lane, Double> E = new HashMap<>();
        Map<Lane, Object> prev = new HashMap<>();   // Lane (a successor or lane-change edge) or Snap (a seed)
        Map<Lane, Boolean> viaSide = new HashMap<>();
        PriorityQueue<Object[]> pq = new PriorityQueue<>((a, b) -> Double.compare((Double) a[0], (Double) b[0]));
        for (Snap s : starts) {
            double rest = s.lane.length() - s.offset;
            for (Lane n : s.lane.succ) relax(E, prev, viaSide, pq, n, s.distance + rest, s, false);
            // Lane change off the seed lane, then on to the neighbour's successors.
            for (Lane side : s.lane.side)
                for (Lane n : side.succ)
                    relax(E, prev, viaSide, pq, n, s.distance + LANE_CHANGE_COST + (side.length() - s.offset),
                            new Snap(side, s.offset, s.distance, s.point), true);
        }
        while (!pq.isEmpty()) {
            Object[] top = pq.poll();
            Lane l = (Lane) top[1];
            double c = (Double) top[0];
            if (c > E.getOrDefault(l, Double.MAX_VALUE)) continue;
            for (Lane n : l.succ) relax(E, prev, viaSide, pq, n, c + l.length(), l, false);
            for (Lane n : l.side) relax(E, prev, viaSide, pq, n, c + LANE_CHANGE_COST, l, true);
        }

        // Pick the goal: reached from a lane start (E), or on a seed lane ahead of the start.
        double bestCost = Double.MAX_VALUE;
        Snap bestGoal = null, bestSeed = null;
        boolean bestSeedSide = false;
        for (Snap g : goals) {
            double e = E.getOrDefault(g.lane, Double.MAX_VALUE);
            if (e < Double.MAX_VALUE && e + g.offset + g.distance < bestCost) {
                bestCost = e + g.offset + g.distance; bestGoal = g; bestSeed = null;
            }
            for (Snap s : starts) {
                boolean same = s.lane == g.lane, side = s.lane.side.contains(g.lane);
                if (!same && !side) continue;
                if (g.offset < s.offset) continue;
                double c = s.distance + (side ? LANE_CHANGE_COST : 0) + g.offset - s.offset + g.distance;
                if (c < bestCost) { bestCost = c; bestGoal = g; bestSeed = s; bestSeedSide = side; }
            }
        }
        if (bestGoal == null) return null;

        // Rebuild the legs back to front.
        List<Leg> legs = new ArrayList<>();
        if (bestSeed != null) {
            if (bestSeedSide) legs.add(new Leg(bestSeed.lane, bestSeed.offset, bestSeed.offset));
            legs.add(new Leg(bestGoal.lane, bestSeed.offset, bestGoal.offset));
            Collections.reverse(legs);
        } else {
            legs.add(new Leg(bestGoal.lane, 0, bestGoal.offset));
            Lane cur = bestGoal.lane;
            int guard = lanes.size() * 2 + 4;
            while (guard-- > 0) {
                Object p = prev.get(cur);
                boolean side = viaSide.getOrDefault(cur, false);
                if (p instanceof Snap s) {
                    legs.add(new Leg(s.lane, s.offset, s.lane.length()));
                    break;
                }
                Lane pl = (Lane) p;
                if (side) {
                    // A lane change is a jump, not a stretch of road: record a zero-length leg so
                    // the lane list still says which lane the change was made from.
                    legs.add(new Leg(pl, 0, 0));
                } else {
                    legs.add(new Leg(pl, 0, pl.length()));
                }
                cur = pl;
            }
            // A seed that changed lanes: the Snap carries the NEIGHBOUR, so the seed lane itself is
            // lost; that is harmless (a jump of one lane width at the very start).
        }
        Collections.reverse(legs);
        // Zero-length legs (a lane change) stay in the list, so it still names every lane the route
        // uses in a legal order; they add nothing to the polyline.
        List<Leg> drivable = new ArrayList<>();
        for (Leg l : legs) if (l.to > l.from + 1e-9) drivable.add(l);
        if (drivable.isEmpty()) drivable.add(legs.get(legs.size() - 1));

        List<double[]> pts = new ArrayList<>();
        double length = 0;
        for (Leg leg : drivable) {
            length += leg.to - leg.from;
            pts.add(leg.lane.at(leg.from));
            for (int i = 0; i < leg.lane.x.length; i++) {
                double s = leg.lane.cum[i];
                if (s > leg.from && s < leg.to) pts.add(new double[]{leg.lane.x[i], leg.lane.y[i], leg.lane.z[i]});
            }
            pts.add(leg.lane.at(leg.to));
        }
        double[] flat = new double[pts.size() * 3];
        for (int i = 0; i < pts.size(); i++) System.arraycopy(pts.get(i), 0, flat, 3 * i, 3);
        return new Route(legs, flat, length, bestCost, bestGoal.point);
    }

    private static void relax(Map<Lane, Double> E, Map<Lane, Object> prev, Map<Lane, Boolean> viaSide,
                              PriorityQueue<Object[]> pq, Lane n, double c, Object from, boolean side) {
        if (c < E.getOrDefault(n, Double.MAX_VALUE)) {
            E.put(n, c);
            prev.put(n, from);
            viaSide.put(n, side);
            pq.add(new Object[]{c, n});
        }
    }

    // ── helpers ────────────────────────────────────────────────────────────────

    private static String str(Object o) { return o instanceof String s ? s : ""; }

    private static double num(Object o) { return o instanceof Number n ? n.doubleValue() : 0.0; }

    private static double dXZ(double ax, double az, double bx, double bz) {
        double dx = ax - bx, dz = az - bz;
        return Math.sqrt(dx * dx + dz * dz);
    }

    private static long key(double x, double z, double cell) {
        long ix = (long) Math.floor(x / cell), iz = (long) Math.floor(z / cell);
        return (ix << 32) ^ (iz & 0xffffffffL);
    }

    private static List<Lane> near(Map<Long, List<Lane>> grid, double x, double z, double cell) {
        List<Lane> out = new ArrayList<>();
        long ix = (long) Math.floor(x / cell), iz = (long) Math.floor(z / cell);
        for (long a = ix - 1; a <= ix + 1; a++)
            for (long b = iz - 1; b <= iz + 1; b++) {
                List<Lane> c = grid.get((a << 32) ^ (b & 0xffffffffL));
                if (c != null) out.addAll(c);
            }
        return out;
    }

    /** Douglas-Peucker over XZ, returning {x0, z0, x1, z1, ...}. */
    static double[] simplifyXZ(double[] x, double[] z, double tol) {
        int n = x.length;
        boolean[] keep = new boolean[n];
        keep[0] = keep[n - 1] = true;
        java.util.ArrayDeque<int[]> stack = new java.util.ArrayDeque<>();
        stack.push(new int[]{0, n - 1});
        while (!stack.isEmpty()) {
            int[] r = stack.pop();
            int a = r[0], b = r[1];
            double dx = x[b] - x[a], dz = z[b] - z[a];
            double l = Math.sqrt(dx * dx + dz * dz);
            double worst = -1; int wi = -1;
            for (int i = a + 1; i < b; i++) {
                double d = l < 1e-9 ? dXZ(x[i], z[i], x[a], z[a])
                        : Math.abs((x[i] - x[a]) * dz - (z[i] - z[a]) * dx) / l;
                if (d > worst) { worst = d; wi = i; }
            }
            if (wi >= 0 && worst > tol) {
                keep[wi] = true;
                stack.push(new int[]{a, wi});
                stack.push(new int[]{wi, b});
            }
        }
        int k = 0;
        for (boolean b : keep) if (b) k++;
        double[] out = new double[2 * k];
        int j = 0;
        for (int i = 0; i < n; i++) if (keep[i]) { out[j++] = x[i]; out[j++] = z[i]; }
        return out;
    }
}
