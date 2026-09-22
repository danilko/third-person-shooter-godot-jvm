package com.openworld.ui;

import com.openworld.world.Places;
import com.openworld.world.RoadGraph;
import com.openworld.world.RoadMap;
import godot.api.CanvasItem;
import godot.api.Font;
import godot.api.ThemeDB;
import godot.core.HorizontalAlignment;
import godot.core.Rect2;
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

    // ── places and regions (PLAN.md 3.18n) ─────────────────────────────────────────────────────────

    /** A place's blip is a SQUARE, so it never reads as a character or a vehicle (both are discs). */
    static final Color PLACE = new Color(1f, 0.86f, 0.45f, 0.95f);
    static final Color LANDMARK = new Color(1f, 0.72f, 0.3f, 1f);

    /**
     * Draw a square blip for each place, and its name when {@code font} is given. {@code minTier} hides the
     * ordinary shops when the view is zoomed out, so a whole-island map shows landmarks and not 130 konbini.
     * Nothing is latched: what is drawn is derived from the view every frame.
     */
    static void drawPlaces(CanvasItem ci, List<Places.Place> places, Vector3 origin, Vector2 center,
                           float scale, float clipRadiusPx, float rot, float sizePx, int minTier, Font font,
                           int fontSize) {
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        List<float[]> labels = new ArrayList<>();
        for (Places.Place p : places) {
            if (p.tier() < minTier) continue;
            Vector2 at = project(p.at().getX(), p.at().getZ(), ox, oz, cx, cy, scale, rot);
            if (clipRadiusPx > 0) {
                double dx = at.getX() - cx, dy = at.getY() - cy;
                if (dx * dx + dy * dy > clipRadiusPx * clipRadiusPx) continue;
            }
            Color col = p.tier() >= Places.LANDMARK_TIER ? LANDMARK : PLACE;
            float h = sizePx * 0.5f;
            ci.drawRect(new Rect2(at.getX() - h, at.getY() - h, sizePx, sizePx), col, true, -1f, false);
            ci.drawRect(new Rect2(at.getX() - h, at.getY() - h, sizePx, sizePx),
                    new Color(0f, 0f, 0f, 0.55f), false, 1f, false);
            if (font != null) {
                // two places side by side (the safe house and the weapon counter are 21 m apart) must not print
                // their names on top of each other: a label that would overlap one already drawn steps down a line
                float lx = (float) (at.getX() + h + 3f), ly = (float) (at.getY() + fontSize * 0.35f);
                float lw = (float) font.getStringSize(p.name(), HorizontalAlignment.LEFT, -1f, fontSize).getX();
                for (int step = 0; step < 4 && overlaps(labels, lx, ly, lw, fontSize); step++) ly += fontSize + 2f;
                labels.add(new float[] {lx, ly - fontSize, lw, fontSize + 2f});
                ci.drawString(font, new Vector2(lx, ly), p.name(), HorizontalAlignment.LEFT, -1f, fontSize, col);
            }
        }
    }

    private static boolean overlaps(List<float[]> rs, float x, float baseline, float w, float h) {
        float y = baseline - h;
        for (float[] r : rs) {
            if (x < r[0] + r[2] && x + w > r[0] && y < r[1] + r[3] && y + h > r[1]) return true;
        }
        return false;
    }

    // ── the postal grid as the map's background (PLAN.md 3.26, user 2026-09-22) ──────────────────────

    /** Alternating cell fills: a faint checkerboard, so crossing into the next cell is visible at a glance. */
    static final Color GRID_A = new Color(1f, 1f, 1f, 0.04f);
    static final Color GRID_B = new Color(1f, 1f, 1f, 0.11f);
    static final Color GRID_LINE = new Color(1f, 1f, 1f, 0.22f);
    static final Color GRID_LABEL = new Color(1f, 1f, 1f, 0.42f);

    /**
     * The postal grid ({@link com.openworld.world.PostalGrid}, the ONE owner of the cells) as a light
     * checkerboard with its cell lines and each cell's "x-y" in the middle — drawn UNDER the roads, so it
     * tells you where the next cell boundary is without hiding what you navigate by. It replaced the region
     * underlay, whose overlapping boxes were hard to read (user, 2026-09-22).
     *
     * <p>{@code clipRadiusPx > 0} clips to the minimap's disc (the cells are turned by {@code rot} with the
     * rest of a heading-up map); otherwise the rectangle {@code (0,0)-(viewW,viewH)}. A cell's number is
     * drawn upright at the middle of its VISIBLE part, and only where that part is at least
     * {@code minLabelPx} across, so a zoomed-out map is not a wall of numbers.
     */
    static void drawPostalGrid(CanvasItem ci, Vector3 origin, Vector2 center, float scale, float clipRadiusPx,
                               float viewW, float viewH, float rot, Font font, int fontSize, float minLabelPx) {
        double half = com.openworld.world.PostalGrid.HALF, cell = com.openworld.world.PostalGrid.CELL;
        int n = com.openworld.world.PostalGrid.CELLS;
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        // how far from the view centre anything on screen can be, in world metres
        double reach = clipRadiusPx > 0 ? clipRadiusPx / scale
                : Math.hypot(Math.max(cx, viewW - cx), Math.max(cy, viewH - cy)) / scale;
        int i0 = Math.max(1, (int) Math.floor((ox - reach + half) / cell) + 1);
        int i1 = Math.min(n, (int) Math.floor((ox + reach + half) / cell) + 1);
        int j0 = Math.max(1, (int) Math.floor((oz - reach + half) / cell) + 1);
        int j1 = Math.min(n, (int) Math.floor((oz + reach + half) / cell) + 1);
        if (i0 > i1 || j0 > j1) return;
        List<Vector2> disc = clipRadiusPx > 0 ? discPolygon(cx, cy, clipRadiusPx) : null;
        for (int i = i0; i <= i1; i++) {
            for (int j = j0; j <= j1; j++) {
                double x0 = -half + (i - 1) * cell, z0 = -half + (j - 1) * cell;
                List<Vector2> quad = new ArrayList<>(4);
                quad.add(project(x0, z0, ox, oz, cx, cy, scale, rot));
                quad.add(project(x0 + cell, z0, ox, oz, cx, cy, scale, rot));
                quad.add(project(x0 + cell, z0 + cell, ox, oz, cx, cy, scale, rot));
                quad.add(project(x0, z0 + cell, ox, oz, cx, cy, scale, rot));
                List<Vector2> poly = disc != null ? clipConvex(quad, disc)
                        : clipConvex(quad, rectPolygon(viewW, viewH));
                if (poly.size() < 3) continue;
                ci.drawColoredPolygon(new PackedVector2Array(poly), ((i + j) & 1) == 0 ? GRID_A : GRID_B,
                        new PackedVector2Array(), null);
                if (font == null) continue;
                double minX = Double.MAX_VALUE, maxX = -Double.MAX_VALUE, minY = Double.MAX_VALUE, maxY = -Double.MAX_VALUE;
                double sx = 0, sy = 0;
                for (Vector2 v : poly) {
                    minX = Math.min(minX, v.getX()); maxX = Math.max(maxX, v.getX());
                    minY = Math.min(minY, v.getY()); maxY = Math.max(maxY, v.getY());
                    sx += v.getX(); sy += v.getY();
                }
                if (Math.min(maxX - minX, maxY - minY) < minLabelPx) continue;
                float lx = (float) (sx / poly.size()), ly = (float) (sy / poly.size());
                ci.drawString(font, new Vector2(lx - 40f, ly + fontSize * 0.35f), i + "-" + j,
                        HorizontalAlignment.CENTER, 80f, fontSize, GRID_LABEL);
            }
        }
        // the cell lines, clipped like everything else on the map
        for (int k = i0 - 1; k <= i1; k++) {
            double v = -half + k * cell;
            double za = Math.max(-half, oz - reach), zb = Math.min(half, oz + reach);
            List<Vector2> line = List.of(project(v, za, ox, oz, cx, cy, scale, rot), project(v, zb, ox, oz, cx, cy, scale, rot));
            polyline(ci, new ArrayList<>(line), cx, cy, clipRadiusPx, GRID_LINE, 1f);
        }
        for (int k = j0 - 1; k <= j1; k++) {
            double v = -half + k * cell;
            double xa = Math.max(-half, ox - reach), xb = Math.min(half, ox + reach);
            List<Vector2> line = List.of(project(xa, v, ox, oz, cx, cy, scale, rot), project(xb, v, ox, oz, cx, cy, scale, rot));
            polyline(ci, new ArrayList<>(line), cx, cy, clipRadiusPx, GRID_LINE, 1f);
        }
    }

    private static List<Vector2> discPolygon(double cx, double cy, double r) {
        List<Vector2> pts = new ArrayList<>(DISC_SEGMENTS);
        for (int i = 0; i < DISC_SEGMENTS; i++) {
            double a = 2 * Math.PI * i / DISC_SEGMENTS;
            pts.add(new Vector2((float) (cx + Math.cos(a) * r), (float) (cy + Math.sin(a) * r)));
        }
        return pts;
    }

    private static List<Vector2> rectPolygon(double w, double h) {
        return List.of(new Vector2(0f, 0f), new Vector2((float) w, 0f), new Vector2((float) w, (float) h),
                new Vector2(0f, (float) h));
    }

    /**
     * Sutherland-Hodgman: {@code subject} clipped to the convex {@code clip}. Both wound the same way
     * (the screen-space projections here are all clockwise on a y-down screen, and a rotation keeps that).
     */
    static List<Vector2> clipConvex(List<Vector2> subject, List<Vector2> clip) {
        List<Vector2> out = new ArrayList<>(subject);
        double area = 0;
        for (int i = 0; i < clip.size(); i++) {
            Vector2 a = clip.get(i), b = clip.get((i + 1) % clip.size());
            area += a.getX() * b.getY() - b.getX() * a.getY();
        }
        double sign = Math.signum(area);
        for (int e = 0; e < clip.size() && !out.isEmpty(); e++) {
            Vector2 a = clip.get(e), b = clip.get((e + 1) % clip.size());
            List<Vector2> in = out;
            out = new ArrayList<>(in.size() + 2);
            for (int i = 0; i < in.size(); i++) {
                Vector2 p = in.get(i), q = in.get((i + 1) % in.size());
                double dp = sign * side(a, b, p), dq = sign * side(a, b, q);
                if (dp >= 0) out.add(p);
                if ((dp >= 0) != (dq >= 0)) {
                    double t = dp / (dp - dq);
                    out.add(new Vector2((float) (p.getX() + (q.getX() - p.getX()) * t),
                            (float) (p.getY() + (q.getY() - p.getY()) * t)));
                }
            }
        }
        return out;
    }

    private static double side(Vector2 a, Vector2 b, Vector2 p) {
        return (b.getX() - a.getX()) * (p.getY() - a.getY()) - (b.getY() - a.getY()) * (p.getX() - a.getX());
    }

    /** The shared fallback font, or null. */
    static Font mapFont() { return ThemeDB.getFallbackFont(); }
}
