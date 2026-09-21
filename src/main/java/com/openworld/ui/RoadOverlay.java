package com.openworld.ui;

import com.openworld.world.RoadGraph;
import com.openworld.world.RoadMap;
import godot.api.CanvasItem;
import godot.api.Texture2D;
import godot.core.Color;
import godot.core.PackedColorArray;
import godot.core.PackedVector2Array;
import godot.core.Vector2;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * Draws the baked road picture and a GPS route onto a north-up map (PLAN.md 4.7, 4.7b) — shared by
 * {@link MinimapController} and {@link WorldMapManager} so the two cannot draw different roads.
 * The mapping is theirs: {@code screen = centre + (world.xz − origin.xz) · scale}.
 *
 * <p>The roads are ONE textured polygon per frame: {@link RoadMap#mapTexture} is the whole map
 * square painted once (baked, or painted at load when the bake is stale), and the polygon's UVs say
 * which part of it is under the view — a disc for the minimap, the control's rectangle for the map.
 * The route, which changes, is still drawn as a line (its simplified polyline, one bridge call).
 */
final class RoadOverlay {

    static final Color ROAD = new Color(0.62f, 0.64f, 0.68f, 0.85f);
    /** Vertices of the minimap's textured disc. */
    private static final int DISC_SEGMENTS = 48;

    private RoadOverlay() { }

    /**
     * Draw the road picture under the view. {@code clipRadiusPx > 0} draws a disc of that radius
     * about {@code center}; otherwise the rectangle {@code (0,0)-(viewW,viewH)}. False when there is
     * no picture.
     */
    static boolean drawMap(CanvasItem ci, Vector3 origin, Vector2 center, float scale,
                           float viewW, float viewH, float clipRadiusPx, Color color) {
        return drawMap(ci, origin, center, scale, viewW, viewH, clipRadiusPx, color, 0f);
    }

    /**
     * As above, with the picture turned by {@code rot} radians about {@code center} — a heading-up minimap.
     * The polygon's own vertices do not move; its UVs do, because a UV is the INVERSE of the world→screen
     * mapping and must carry the same rotation backwards, or the picture and the blips drawn over it are of
     * two different worlds.
     */
    static boolean drawMap(CanvasItem ci, Vector3 origin, Vector2 center, float scale,
                           float viewW, float viewH, float clipRadiusPx, Color color, float rot) {
        Texture2D tex = RoadMap.mapTexture();
        double[] b = RoadMap.mapSquare();
        if (tex == null || b == null || scale <= 0) return false;
        List<Vector2> pts = new ArrayList<>();
        if (clipRadiusPx > 0) {
            for (int i = 0; i < DISC_SEGMENTS; i++) {
                double a = 2 * Math.PI * i / DISC_SEGMENTS;
                pts.add(new Vector2((float) (center.getX() + Math.cos(a) * clipRadiusPx),
                        (float) (center.getY() + Math.sin(a) * clipRadiusPx)));
            }
        } else {
            pts.add(new Vector2(0f, 0f));
            pts.add(new Vector2(viewW, 0f));
            pts.add(new Vector2(viewW, viewH));
            pts.add(new Vector2(0f, viewH));
        }
        List<Vector2> uvs = new ArrayList<>(pts.size());
        double ox = origin.getX(), oz = origin.getZ();
        double cs = Math.cos(rot), sn = Math.sin(rot);
        for (Vector2 p : pts) {
            double sx = (p.getX() - center.getX()) / scale, sy = (p.getY() - center.getY()) / scale;
            double wx = ox + (sx * cs + sy * sn);            // the inverse rotation
            double wz = oz + (-sx * sn + sy * cs);
            uvs.add(new Vector2((float) ((wx - b[0]) / b[2]), (float) ((wz - b[1]) / b[2])));
        }
        PackedColorArray colors = new PackedColorArray();
        colors.pushBack(color);
        ci.drawPolygon(new PackedVector2Array(pts), colors, new PackedVector2Array(uvs), tex);
        return true;
    }

    /** Draw a route, then a thin straight line from where it leaves the road to the waypoint. */
    static void drawRoute(CanvasItem ci, RoadGraph.Route r, Vector3 waypoint, Vector3 origin, Vector2 center,
                          float scale, float clipRadiusPx, float widthPx, Color color) {
        drawRoute(ci, r, waypoint, origin, center, scale, clipRadiusPx, widthPx, color, 0f);
    }

    static void drawRoute(CanvasItem ci, RoadGraph.Route r, Vector3 waypoint, Vector3 origin, Vector2 center,
                          float scale, float clipRadiusPx, float widthPx, Color color, float rot) {
        if (r == null) return;
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        double[] xz = r.drawXZ();
        List<Vector2> pts = new ArrayList<>(xz.length / 2);
        for (int i = 0; i < xz.length; i += 2) pts.add(project(xz[i], xz[i + 1], ox, oz, cx, cy, scale, rot));
        polyline(ci, pts, cx, cy, clipRadiusPx, color, widthPx);
        if (waypoint != null && r.goalPoint != null) {
            List<Vector2> tail = new ArrayList<>(2);
            tail.add(project(r.goalPoint[0], r.goalPoint[2], ox, oz, cx, cy, scale, rot));
            tail.add(project(waypoint.getX(), waypoint.getZ(), ox, oz, cx, cy, scale, rot));
            polyline(ci, tail, cx, cy, clipRadiusPx, color, Math.max(1f, widthPx * 0.4f));
        }
    }

    /** The ONE world→screen mapping of this overlay: a world XZ delta, scaled, turned by {@code rot}. */
    static Vector2 project(double wx, double wz, double ox, double oz, double cx, double cy,
                           double scale, double rot) {
        double dx = (wx - ox) * scale, dz = (wz - oz) * scale;
        double cs = Math.cos(rot), sn = Math.sin(rot);
        return new Vector2((float) (cx + dx * cs - dz * sn), (float) (cy + dx * sn + dz * cs));
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
