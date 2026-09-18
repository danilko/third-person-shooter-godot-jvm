package com.openworld.ui;

import com.openworld.world.RoadGraph;
import godot.api.CanvasItem;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Vector2;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * Draws the road network and a GPS route onto a north-up map (PLAN.md 4.7) — shared by
 * {@link MinimapController} and {@link WorldMapManager} so the two cannot draw different roads.
 * The mapping is theirs: {@code screen = centre + (world.xz − origin.xz) · scale}. Each lane is one
 * polyline as wide as the lane (never thinner than {@code minWidthPx}), so a two-lane carriageway
 * reads as one road. A lane whose bounds are outside the view is skipped; with a
 * {@code clipRadiusPx} (the round minimap) every polyline is also clipped to that circle.
 * Each polyline is handed over in ONE bridge call (the {@code Collection} constructor).
 */
final class RoadOverlay {

    static final Color ROAD = new Color(0.62f, 0.64f, 0.68f, 0.85f);

    private RoadOverlay() { }

    /** Draw every lane in view; returns how many lanes were drawn. */
    static int drawRoads(CanvasItem ci, RoadGraph g, Vector3 origin, Vector2 center, float scale,
                         double viewHalfX, double viewHalfZ, float clipRadiusPx, float minWidthPx, Color color) {
        if (g == null) return 0;
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        int drawn = 0;
        for (RoadGraph.Lane l : g.lanes()) {
            double[] b = l.boundsXZ();
            if (b[2] < ox - viewHalfX || b[0] > ox + viewHalfX || b[3] < oz - viewHalfZ || b[1] > oz + viewHalfZ)
                continue;
            double[] xz = l.drawXZ();
            List<Vector2> pts = new ArrayList<>(xz.length / 2);
            for (int i = 0; i < xz.length; i += 2)
                pts.add(new Vector2((float) (cx + (xz[i] - ox) * scale), (float) (cy + (xz[i + 1] - oz) * scale)));
            float w = Math.max(minWidthPx, l.width * scale);
            if (polyline(ci, pts, cx, cy, clipRadiusPx, color, w)) drawn++;
        }
        return drawn;
    }

    /** Draw a route, then a thin straight line from where it leaves the road to the waypoint. */
    static void drawRoute(CanvasItem ci, RoadGraph.Route r, Vector3 waypoint, Vector3 origin, Vector2 center,
                          float scale, float clipRadiusPx, float widthPx, Color color) {
        if (r == null) return;
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        List<Vector2> pts = new ArrayList<>(r.pointCount());
        double[] p = r.points;
        for (int i = 0; i < p.length; i += 3)
            pts.add(new Vector2((float) (cx + (p[i] - ox) * scale), (float) (cy + (p[i + 2] - oz) * scale)));
        polyline(ci, pts, cx, cy, clipRadiusPx, color, widthPx);
        if (waypoint != null && r.goalPoint != null) {
            List<Vector2> tail = new ArrayList<>(2);
            tail.add(new Vector2((float) (cx + (r.goalPoint[0] - ox) * scale), (float) (cy + (r.goalPoint[2] - oz) * scale)));
            tail.add(new Vector2((float) (cx + (waypoint.getX() - ox) * scale), (float) (cy + (waypoint.getZ() - oz) * scale)));
            polyline(ci, tail, cx, cy, clipRadiusPx, color, Math.max(1f, widthPx * 0.4f));
        }
    }

    /** Draw {@code pts}, clipped to the circle when {@code r > 0}. True when anything was drawn. */
    private static boolean polyline(CanvasItem ci, List<Vector2> pts, double cx, double cy, float r,
                                    Color color, float width) {
        if (pts.size() < 2) return false;
        if (r <= 0) {
            ci.drawPolyline(new PackedVector2Array(pts), color, width, true);
            return true;
        }
        boolean any = false;
        for (List<Vector2> run : clipToCircle(pts, cx, cy, r)) {
            if (run.size() < 2) continue;
            ci.drawPolyline(new PackedVector2Array(run), color, width, true);
            any = true;
        }
        return any;
    }

    /** The parts of a polyline inside a circle, as separate runs. */
    static List<List<Vector2>> clipToCircle(List<Vector2> pts, double cx, double cy, double r) {
        List<List<Vector2>> runs = new ArrayList<>();
        List<Vector2> cur = null;
        double r2 = r * r;
        for (int i = 0; i + 1 < pts.size(); i++) {
            double ax = pts.get(i).getX() - cx, ay = pts.get(i).getY() - cy;
            double bx = pts.get(i + 1).getX() - cx, by = pts.get(i + 1).getY() - cy;
            double dx = bx - ax, dy = by - ay;
            double A = dx * dx + dy * dy, B = 2 * (ax * dx + ay * dy), C = ax * ax + ay * ay - r2;
            double t0 = 0, t1 = 1;
            if (A < 1e-12) {
                if (C > 0) { cur = null; continue; }
            } else {
                double disc = B * B - 4 * A * C;
                if (disc <= 0) { cur = null; continue; }
                double sq = Math.sqrt(disc);
                t0 = Math.max(0, (-B - sq) / (2 * A));
                t1 = Math.min(1, (-B + sq) / (2 * A));
                if (t0 >= t1) { cur = null; continue; }
            }
            Vector2 p0 = new Vector2((float) (cx + ax + dx * t0), (float) (cy + ay + dy * t0));
            Vector2 p1 = new Vector2((float) (cx + ax + dx * t1), (float) (cy + ay + dy * t1));
            if (cur == null || t0 > 0) {
                cur = new ArrayList<>();
                runs.add(cur);
                cur.add(p0);
            }
            cur.add(p1);
            if (t1 < 1) cur = null;
        }
        return runs;
    }
}
