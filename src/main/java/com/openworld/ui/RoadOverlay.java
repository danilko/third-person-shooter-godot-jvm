package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Player;
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
import java.util.Map;

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
        return drawPicture(ci, RoadMap.mapTexture(), origin, center, scale, viewW, viewH, clipRadiusPx, color, rot);
    }

    /** The building layer ({@link com.openworld.world.BuildingMap}), over the same square as the roads and drawn
     *  UNDER them, with the same view mapping. False when there is none. */
    static boolean drawBuildings(CanvasItem ci, Vector3 origin, Vector2 center, float scale,
                                 float viewW, float viewH, float clipRadiusPx, Color color, float rot) {
        return drawPicture(ci, com.openworld.world.BuildingMap.texture(), origin, center, scale, viewW, viewH,
                clipRadiusPx, color, rot);
    }

    /** Any picture that covers {@link RoadMap#mapSquare} as one textured polygon (the roads, the buildings). */
    private static boolean drawPicture(CanvasItem ci, Texture2D tex, Vector3 origin, Vector2 center, float scale,
                                       float viewW, float viewH, float clipRadiusPx, Color color, float rot) {
        double[] b = RoadMap.mapSquare();
        if (tex == null || b == null || scale <= 0) return false;
        List<Vector2> pts = new ArrayList<>();
        if (clipRadiusPx > 0) {
            pts.addAll(clipPolygon(center.getX(), center.getY(), clipRadiusPx));
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

    static final Color RAIL = new Color(0.96f, 0.96f, 0.94f, 0.95f);
    static final Color RAIL_DASH = new Color(0.10f, 0.10f, 0.12f, 1f);
    static final Color TRAIN = new Color(0.98f, 0.98f, 0.98f, 1f);
    static final Color TRAIN_HEAD = new Color(1f, 0.80f, 0.15f, 1f);

    /**
     * The rail lines, drawn the way a Japanese map draws a JR line (a white band with black dashes in it, which reads
     * on a dark map as well as a light one), and every train in service on them as a white bar with a yellow head -- so a player can see where the line goes and
     * where the next train is. Read from {@link com.openworld.world.TrainSystem}: nothing to draw without trains.
     */
    static void drawRail(CanvasItem ci, Vector3 origin, Vector2 center, float scale, float clipRadiusPx,
                         float widthPx, boolean trains, float rot) {
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        for (double[] xz : com.openworld.world.TrainSystem.mapLines()) {
            List<Vector2> pts = new ArrayList<>(xz.length / 2);
            for (int i = 0; i < xz.length; i += 2) pts.add(project(xz[i], xz[i + 1], ox, oz, cx, cy, scale, rot));
            List<List<Vector2>> runs = clipRadiusPx > 0 ? clipRun(pts, cx, cy, clipRadiusPx) : List.of(pts);
            for (List<Vector2> run : runs) {
                if (run.size() < 2) continue;
                ci.drawPolyline(new PackedVector2Array(run), RAIL, widthPx, true);
                dashed(ci, run, RAIL_DASH, Math.max(1f, widthPx * 0.45f), widthPx * 2.2f);
            }
        }
        if (!trains) return;
        for (double[] tr : com.openworld.world.TrainSystem.mapTrains()) {
            Vector2 h = project(tr[0], tr[1], ox, oz, cx, cy, scale, rot);
            Vector2 t = project(tr[2], tr[3], ox, oz, cx, cy, scale, rot);
            if (clipRadiusPx > 0 && (!insideClip(h.getX(), h.getY(), cx, cy, clipRadiusPx)
                    || !insideClip(t.getX(), t.getY(), cx, cy, clipRadiusPx))) continue;
            // at least a few pixels long, so a whole-island view still shows the train
            Vector2 d = h.minus(t);
            float len = (float) Math.hypot(d.getX(), d.getY());
            float min = widthPx * 2.5f;
            if (len < min) {
                Vector2 dir = len > 1e-3 ? d.div(len) : new Vector2(1, 0);
                Vector2 mid = h.plus(t).times(0.5);
                h = mid.plus(dir.times(min / 2));
                t = mid.minus(dir.times(min / 2));
            }
            ci.drawLine(t, h, new Color(0f, 0f, 0f, 0.9f), widthPx * 2.4f, true);
            ci.drawLine(t, h, TRAIN, widthPx * 1.6f, true);
            ci.drawCircle(h, widthPx * 1.1f, TRAIN_HEAD, true, -1f, true);
        }
    }

    /** Dashes along a screen polyline (period 2 x dash), continuous across its vertices. */
    private static void dashed(CanvasItem ci, List<Vector2> run, Color col, float width, float dash) {
        double phase = 0;
        for (int i = 0; i + 1 < run.size(); i++) {
            Vector2 a = run.get(i), b = run.get(i + 1);
            double L = Math.hypot(b.getX() - a.getX(), b.getY() - a.getY());
            double u = 0;
            while (u < L) {
                double inPeriod = phase % (2 * dash);
                double left = (inPeriod < dash ? dash : 2 * dash) - inPeriod;
                double step = Math.min(left, L - u);
                if (inPeriod < dash && L > 1e-6) {
                    Vector2 p0 = a.lerp(b, (float) (u / L)), p1 = a.lerp(b, (float) ((u + step) / L));
                    ci.drawLine(p0, p1, col, width, true);
                }
                u += step;
                phase += step;
            }
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
        for (List<Vector2> run : clipRun(pts, cx, cy, r)) {
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
    /** The player as a heading TRIANGLE pointing along {@code dir} (screen space, unit), the minimap's own shape --
     *  one owner, so both maps draw the same player. */
    static void drawHeading(CanvasItem ci, Vector2 center, Vector2 dir, float size, Color col) {
        float dx = (float) dir.getX(), dy = (float) dir.getY();
        float cx = (float) center.getX(), cy = (float) center.getY();
        PackedVector2Array tri = new PackedVector2Array();
        tri.pushBack(new Vector2(cx + dx * size, cy + dy * size));
        tri.pushBack(new Vector2(cx - dx * size * 0.5f - dy * size * 0.55f, cy - dy * size * 0.5f + dx * size * 0.55f));
        tri.pushBack(new Vector2(cx - dx * size * 0.5f + dy * size * 0.55f, cy - dy * size * 0.5f - dx * size * 0.55f));
        ci.drawColoredPolygon(tri, col, new PackedVector2Array(), null);
    }

    /** The viewport camera's forward on the XZ plane as a north-up screen direction (x right, +z down). */
    static Vector2 cameraHeading(CanvasItem ci) {
        godot.api.Viewport vp = ci.getViewport();
        godot.api.Camera3D cam = vp != null ? vp.getCamera3d() : null;
        if (cam == null) return new Vector2(0f, -1f);
        Vector3 fwd = cam.getGlobalBasis().getZ().times(-1f);
        float x = (float) fwd.getX(), z = (float) fwd.getZ();
        float len = (float) Math.sqrt(x * x + z * z);
        return len < 1e-3f ? new Vector2(0f, -1f) : new Vector2(x / len, z / len);
    }

    /**
     * Whether a body earns a blip on either map (user, 2026-09-26: GTA shows no neutral pedestrians or ambient
     * traffic -- a map full of dots nobody can act on hides the ones that matter): another PLAYER, anyone HOSTILE
     * to the local player, and a vehicle driven by either. One rule for the minimap and the full map.
     */
    static boolean worthABlip(Character self, godot.api.Node n) {
        if (n == self) return false;
        Character c = n instanceof Vehicle v ? v.driverNow() : (n instanceof Character ch ? ch : null);
        if (c == null || !c.isAlive()) return false;
        if (c instanceof Player) return true;
        String mine = self != null && self.characterInfo != null ? self.characterInfo.faction : Faction.NEUTRAL;
        String theirs = c.characterInfo != null ? c.characterInfo.faction : Faction.NEUTRAL;
        return Faction.areHostile(mine, theirs);
    }

    static void drawPlaces(CanvasItem ci, List<Places.Place> places, Vector3 origin, Vector2 center,
                           float scale, float clipRadiusPx, float rot, float sizePx, int minTier, Font font,
                           int fontSize) {
        drawPlaces(ci, places, origin, center, scale, clipRadiusPx, rot, sizePx, minTier, font, fontSize, font, true);
    }

    /**
     * As above: {@code numberFont} prints each place's type number in its square (null = none), and
     * {@code showAllNames} false prints names only for landmark-tier places, so a zoomed-out map carries every
     * shop as a numbered square without a wall of text.
     */
    static void drawPlaces(CanvasItem ci, List<Places.Place> places, Vector3 origin, Vector2 center,
                           float scale, float clipRadiusPx, float rot, float sizePx, int minTier, Font font,
                           int fontSize, Font numberFont, boolean showAllNames) {
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        List<float[]> labels = new ArrayList<>();
        for (Places.Place p : places) {
            if (p.tier() < minTier) continue;
            Vector2 at = project(p.at().getX(), p.at().getZ(), ox, oz, cx, cy, scale, rot);
            if (clipRadiusPx > 0 && !insideClip(at.getX(), at.getY(), cx, cy, clipRadiusPx)) continue;
            PlaceKind k = PlaceKind.of(p);
            Color col = k.color;
            float h = sizePx * 0.5f;
            ci.drawRect(new Rect2(at.getX() - h, at.getY() - h, sizePx, sizePx), col, true, -1f, false);
            ci.drawRect(new Rect2(at.getX() - h, at.getY() - h, sizePx, sizePx),
                    new Color(0f, 0f, 0f, 0.7f), false, 1f, false);
            // the type's NUMBER inside the square (the legend on the full map says which is which): a stand-in for
            // a label that would crowd a zoomed-out map
            if (numberFont != null && sizePx >= 9f) {
                int fs = Math.max(7, (int) (sizePx * 0.8f));
                ci.drawString(numberFont, new Vector2(at.getX() - h, at.getY() + fs * 0.36f), k.code,
                        HorizontalAlignment.CENTER, sizePx, fs, new Color(0f, 0f, 0f, 0.9f));
            }
            if (font != null && (k.major || showAllNames)) {
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

    /**
     * What KIND of place a blip is -- one colour and one number per kind (user, 2026-09-22: "a number on the square /
     * a different colour for each type of location for now; later maybe a label"). The ONE table, read by the blips
     * and by the full map's legend, so the two cannot disagree. Keyed on the place's scene kind (a type from
     * {@code building_types.json}) and, for the roles the placement names, on the place's own name.
     */
    enum PlaceKind {
        // Redone 2026-10-11 (user): no "Weapon counter" (every konbini sells weapons; the stand-alone store is gone)
        // and no "Landmark" -- the map names what a player DOES something at: where they live, a mission, the police,
        // a gang's ground, where they are patched up, and every building they can walk into.
        SAFEHOUSE("H", "Safe house", new Color(1.00f, 1.00f, 1.00f, 1f), true),
        MISSION("M", "Mission", new Color(1.00f, 0.90f, 0.25f, 1f), true),
        POLICE("P", "Police (station, koban)", new Color(0.35f, 0.60f, 1.00f, 1f), true),
        GANG("G", "Gang ground", new Color(0.95f, 0.30f, 0.75f, 1f), true),
        MEDICAL("+", "Hospital, clinic, fire", new Color(1.00f, 0.45f, 0.40f, 1f), true),
        STATION("T", "Station", new Color(0.45f, 0.85f, 1.00f, 1f), true),
        KONBINI_L("K", "Konbini, large (weapons)", new Color(0.25f, 0.80f, 0.40f, 1f), false),
        KONBINI_S("k", "Konbini, small (weapons)", new Color(0.60f, 0.92f, 0.62f, 1f), false),
        GARAGE("2", "Gas, repair, car dealer", new Color(1.00f, 0.62f, 0.20f, 1f), false),
        BANK("3", "Bank", new Color(0.80f, 0.72f, 0.30f, 1f), false),
        FOOD("4", "Food and nightlife", new Color(1.00f, 0.75f, 0.55f, 1f), false),
        SHOP("5", "Shops and services", new Color(0.75f, 0.62f, 1.00f, 1f), false),
        OTHER("6", "Other enterable / site", new Color(0.82f, 0.82f, 0.82f, 1f), false);

        final String code;
        final String label;
        final Color color;
        /** Named at every zoom (the rest only once zoomed in), and the ones a zoomed-out player navigates by. */
        final boolean major;

        PlaceKind(String code, String label, Color color, boolean major) {
            this.code = code;
            this.label = label;
            this.color = color;
            this.major = major;
        }

        private static boolean any(String k, String... starts) {
            for (String s : starts) if (k.startsWith(s)) return true;
            return false;
        }

        static PlaceKind of(Places.Place p) {
            String k = p.kind() == null ? "" : p.kind();
            if (k.equals(MISSION_KIND)) return MISSION;
            if (k.startsWith("SafeHouse")) return SAFEHOUSE;
            // a gang's ground first: an abducted player is held there, whatever the building is
            if (p.gang() != null && !p.gang().isEmpty()) return GANG;
            if (k.startsWith("Gang")) return GANG;
            if (any(k, "Koban", "PoliceStation", "ImpoundLot")) return POLICE;
            if (any(k, "Hospital", "Clinic", "FireStation", "FireBranch")) return MEDICAL;
            if (k.startsWith("Station_")) return STATION;
            if (k.startsWith("KonbiniL")) return KONBINI_L;
            if (k.startsWith("Konbini")) return KONBINI_S;
            if (any(k, "GasStation", "RepairShop", "CarDealer")) return GARAGE;
            if (k.startsWith("Bank")) return BANK;
            if (any(k, "FamilyRestaurant", "Izakaya", "Karaoke", "MaidCafe", "Pachinko", "GameCentre", "HotelLove",
                    "AdultServices", "PublicMarket", "Shotengai")) return FOOD;
            if (any(k, "Supermarket", "DepartmentStore", "ClothingStore", "FashionBuilding", "HomeCentre", "SuburbanMall",
                    "PostOffice", "WardOffice", "CivicCenter", "PublicLibrary", "SuperSento", "OnsenRyokan", "HotelBusiness",
                    "ShootingRange", "ShopHouse", "AirportTerminal", "StationMall")) return SHOP;
            return OTHER;
        }
    }

    /** The kind of a place that is a MISSION's start (game.activity.ActivityRuntime's placements), added to the
     *  places a map draws by {@link #withMissions}: it is not a building, so it is not in the places record. */
    static final String MISSION_KIND = "Mission";

    /** {@code places} plus one MISSION place per mission that stands in this world and can be started (or is
     *  running) now -- where its placement node is. */
    static List<Places.Place> withMissions(List<Places.Place> places) {
        com.openworld.game.activity.ActivityRuntime rt = com.openworld.game.activity.ActivityRuntime.get();
        if (rt == null) return places;
        Map<String, Vector3> spots = rt.missionSpots();
        if (spots.isEmpty()) return places;
        List<Places.Place> out = new ArrayList<>(places);
        for (Map.Entry<String, Vector3> e : spots.entrySet())
            out.add(new Places.Place(e.getKey(), MISSION_KIND, Places.LANDMARK_TIER, e.getValue(), e.getValue(), "",
                    List.of(), null, null));
        return out;
    }

    /** The full map's key to {@link PlaceKind}: one square and one line per kind, bottom-left of the view. */
    static void drawPlaceLegend(CanvasItem ci, Font font, int fontSize, float x, float bottom, float sizePx) {
        if (font == null) return;
        PlaceKind[] all = PlaceKind.values();
        // two more rows when there are trains: the rail line and a train on it
        boolean rail = !com.openworld.world.TrainSystem.mapLines().isEmpty();
        int rows = all.length + (rail ? 2 : 0);
        float line = Math.max(sizePx, fontSize) + 4f;
        float w = 0f;
        for (PlaceKind k : all) {
            w = Math.max(w, (float) font.getStringSize(k.label, HorizontalAlignment.LEFT, -1f, fontSize).getX());
        }
        float top = bottom - line * rows - 8f;
        ci.drawRect(new Rect2(x - 6f, top, w + sizePx + 22f, line * rows + 8f), new Color(0f, 0f, 0f, 0.55f),
                true, -1f, false);
        float y = top + 4f;
        for (PlaceKind k : all) {
            ci.drawRect(new Rect2(x, y + (line - sizePx) * 0.5f, sizePx, sizePx), k.color, true, -1f, false);
            int fs = Math.max(7, (int) (sizePx * 0.8f));
            ci.drawString(font, new Vector2(x, y + (line - sizePx) * 0.5f + sizePx * 0.5f + fs * 0.36f), k.code,
                    HorizontalAlignment.CENTER, sizePx, fs, new Color(0f, 0f, 0f, 0.9f));
            ci.drawString(font, new Vector2(x + sizePx + 6f, y + line * 0.5f + fontSize * 0.36f), k.label,
                    HorizontalAlignment.LEFT, -1f, fontSize, new Color(1f, 1f, 1f, 0.9f));
            y += line;
        }
        if (!rail) return;
        float my = y + line * 0.5f;
        List<Vector2> seg = List.of(new Vector2(x - 2f, my), new Vector2(x + sizePx + 2f, my));
        ci.drawPolyline(new PackedVector2Array(seg), RAIL, 3f, true);
        dashed(ci, seg, RAIL_DASH, 1.4f, 3f);
        ci.drawString(font, new Vector2(x + sizePx + 6f, my + fontSize * 0.36f), "Rail line",
                HorizontalAlignment.LEFT, -1f, fontSize, new Color(1f, 1f, 1f, 0.9f));
        y += line;
        my = y + line * 0.5f;
        ci.drawLine(new Vector2(x - 2f, my), new Vector2(x + sizePx + 2f, my), new Color(0f, 0f, 0f, 0.9f), 6f, true);
        ci.drawLine(new Vector2(x - 2f, my), new Vector2(x + sizePx + 2f, my), TRAIN, 4f, true);
        ci.drawCircle(new Vector2(x + sizePx - 1f, my), 3f, TRAIN_HEAD, true, -1f, true);
        ci.drawString(font, new Vector2(x + sizePx + 6f, my + fontSize * 0.36f), "Train",
                HorizontalAlignment.LEFT, -1f, fontSize, new Color(1f, 1f, 1f, 0.9f));
    }

    /**
     * A north marker: an "N" in a dark disc, {@code radius} px, at {@code at}. The minimap puts it ON ITS RIM in
     * north's on-screen direction (so on a heading-up radar it travels round the rim as you turn); the full map, which
     * is north-up, puts it in a corner.
     */
    static void drawNorth(CanvasItem ci, Font font, Vector2 at, float radius) {
        ci.drawCircle(at, radius, new Color(0f, 0f, 0f, 0.7f), true, -1f, false);
        ci.drawArc(at, radius, 0f, (float) (2 * Math.PI), 24, new Color(1f, 1f, 1f, 0.8f), 1.5f, false);
        if (font == null) return;
        int fs = Math.max(8, (int) (radius * 1.3f));
        ci.drawString(font, new Vector2(at.getX() - radius, at.getY() + fs * 0.36f), "N",
                HorizontalAlignment.CENTER, radius * 2f, fs, new Color(1f, 0.35f, 0.3f, 1f));
    }

    // ── the postal grid as the map's background (PLAN.md 3.26, user 2026-09-22) ──────────────────────

    /** Alternating cell fills: a faint checkerboard, so crossing into the next cell is visible at a glance. */
    static final Color GRID_A = new Color(1f, 1f, 1f, 0.04f);
    static final Color GRID_B = new Color(1f, 1f, 1f, 0.11f);
    static final Color GRID_LINE = new Color(1f, 1f, 1f, 0.22f);
    static final Color GRID_LABEL = new Color(1f, 1f, 1f, 0.85f);
    static final Color GRID_LABEL_OUTLINE = new Color(0f, 0f, 0f, 0.8f);

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
    /** One postal cell (1-based column i, row j) projected to the screen and clipped to what is drawn. */
    private static List<Vector2> postalCellPoly(int i, int j, double ox, double oz, double cx, double cy, float scale,
                                                float rot, List<Vector2> disc, float viewW, float viewH) {
        double half = com.openworld.world.PostalGrid.HALF, cell = com.openworld.world.PostalGrid.CELL;
        double x0 = -half + (i - 1) * cell, z0 = -half + (j - 1) * cell;
        List<Vector2> quad = new ArrayList<>(4);
        quad.add(project(x0, z0, ox, oz, cx, cy, scale, rot));
        quad.add(project(x0 + cell, z0, ox, oz, cx, cy, scale, rot));
        quad.add(project(x0 + cell, z0 + cell, ox, oz, cx, cy, scale, rot));
        quad.add(project(x0, z0 + cell, ox, oz, cx, cy, scale, rot));
        return disc != null ? clipConvex(quad, disc) : clipConvex(quad, rectPolygon(viewW, viewH));
    }

    /** A cell label's font size: the map's own size when the cell is big, down to 7 px on a small one. */
    private static int labelFontSize(List<Vector2> poly, int fontSize) {
        double minX = Double.MAX_VALUE, maxX = -Double.MAX_VALUE;
        for (Vector2 v : poly) { minX = Math.min(minX, v.getX()); maxX = Math.max(maxX, v.getX()); }
        return Math.max(7, Math.min(fontSize, (int) ((maxX - minX) * 0.26)));
    }

    /** Where a cell's "x-y" is drawn -- the centroid of its visible part -- or null when that part is too small to
     *  carry a label. The ONE owner, so a click on a label and the label itself cannot disagree. */
    private static Vector2 postalLabelPoint(List<Vector2> poly, float minLabelPx) {
        if (poly.size() < 3) return null;
        double minX = Double.MAX_VALUE, maxX = -Double.MAX_VALUE, minY = Double.MAX_VALUE, maxY = -Double.MAX_VALUE;
        double sx = 0, sy = 0;
        for (Vector2 v : poly) {
            minX = Math.min(minX, v.getX()); maxX = Math.max(maxX, v.getX());
            minY = Math.min(minY, v.getY()); maxY = Math.max(maxY, v.getY());
            sx += v.getX(); sy += v.getY();
        }
        if (Math.min(maxX - minX, maxY - minY) < minLabelPx) return null;
        return new Vector2((float) (sx / poly.size()), (float) (sy / poly.size()));
    }

    /**
     * The postal cell whose drawn "x-y" label is under {@code click} (within {@code halfW} x {@code halfH} px of it),
     * as {i, j}, or null -- for a full (unclipped, north-up) map view. Same arguments as {@link #drawPostalGrid}.
     */
    static int[] pickPostalLabel(Vector3 origin, Vector2 center, float scale, float viewW, float viewH,
                                 float minLabelPx, Vector2 click, float halfW, float halfH) {
        double half = com.openworld.world.PostalGrid.HALF, cell = com.openworld.world.PostalGrid.CELL;
        int n = com.openworld.world.PostalGrid.CELLS;
        double ox = origin.getX(), oz = origin.getZ(), cx = center.getX(), cy = center.getY();
        // the label sits inside its cell's visible part, so only the cell under the click and its neighbours can own it
        double wx = ox + (click.getX() - cx) / scale, wz = oz + (click.getY() - cy) / scale;
        int ci = (int) Math.floor((wx + half) / cell) + 1, cj = (int) Math.floor((wz + half) / cell) + 1;
        for (int i = Math.max(1, ci - 1); i <= Math.min(n, ci + 1); i++) {
            for (int j = Math.max(1, cj - 1); j <= Math.min(n, cj + 1); j++) {
                Vector2 at = postalLabelPoint(postalCellPoly(i, j, ox, oz, cx, cy, scale, 0f, null, viewW, viewH),
                        minLabelPx);
                if (at != null && Math.abs(click.getX() - at.getX()) <= halfW
                        && Math.abs(click.getY() - at.getY()) <= halfH) {
                    return new int[] {i, j};
                }
            }
        }
        return null;
    }

    static void drawPostalGrid(CanvasItem ci, Vector3 origin, Vector2 center, float scale, float clipRadiusPx,
                               float viewW, float viewH, float rot, Font font, int fontSize, float minLabelPx) {
        double half = com.openworld.world.PostalGrid.HALF, cell = com.openworld.world.PostalGrid.CELL;
        int n = com.openworld.world.PostalGrid.CELLS;
        double ox = origin.getX(), oz = origin.getZ();
        double cx = center.getX(), cy = center.getY();
        // how far from the view centre anything on screen can be, in world metres
        double reach = clipRadiusPx > 0 ? clipRadiusPx * Math.sqrt(2.0) / scale
                : Math.hypot(Math.max(cx, viewW - cx), Math.max(cy, viewH - cy)) / scale;
        int i0 = Math.max(1, (int) Math.floor((ox - reach + half) / cell) + 1);
        int i1 = Math.min(n, (int) Math.floor((ox + reach + half) / cell) + 1);
        int j0 = Math.max(1, (int) Math.floor((oz - reach + half) / cell) + 1);
        int j1 = Math.min(n, (int) Math.floor((oz + reach + half) / cell) + 1);
        if (i0 > i1 || j0 > j1) return;
        List<Vector2> disc = clipRadiusPx > 0 ? clipPolygon(cx, cy, clipRadiusPx) : null;
        for (int i = i0; i <= i1; i++) {
            for (int j = j0; j <= j1; j++) {
                double x0 = -half + (i - 1) * cell, z0 = -half + (j - 1) * cell;
                List<Vector2> poly = postalCellPoly(i, j, ox, oz, cx, cy, scale, rot, disc, viewW, viewH);
                if (poly.size() < 3) continue;
                ci.drawColoredPolygon(new PackedVector2Array(poly), ((i + j) & 1) == 0 ? GRID_A : GRID_B,
                        new PackedVector2Array(), null);
                if (font == null) continue;
                Vector2 at = postalLabelPoint(poly, minLabelPx);
                if (at == null) continue;
                // the number fits its cell: a zoomed-out map prints every cell's code small instead of none
                int fs = labelFontSize(poly, fontSize);
                Vector2 pos = new Vector2(at.getX() - 40f, at.getY() + fs * 0.35f);
                ci.drawStringOutline(font, pos, i + "-" + j, HorizontalAlignment.CENTER, 80f, fs, 3, GRID_LABEL_OUTLINE);
                ci.drawString(font, pos, i + "-" + j, HorizontalAlignment.CENTER, 80f, fs, GRID_LABEL);
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

    /**
     * The minimap's shape (PLAN.md NEXT item 10): a ROUNDED SQUARE of half size {@code r} when true -- it shows more in
     * its corners at the same size -- or the old disc of radius {@code r}. Every clip on the minimap asks this one
     * shape (the pictures, the postal grid, the lines, the blips), so nothing can be drawn outside the frame.
     */
    static boolean squareClip = true;
    /** The square's corner radius, as a share of its half size: 0, a SQUARE (user 2026-10-05: a flat, square HUD). */
    static final double CORNER = 0.0;

    /** The clip shape as a convex polygon, wound like {@link #discPolygon} (angle increasing). */
    static List<Vector2> clipPolygon(double cx, double cy, double r) {
        if (!squareClip) return discPolygon(cx, cy, r);
        double rc = r * CORNER, k = r - rc;
        double[][] corners = {{k, k}, {-k, k}, {-k, -k}, {k, -k}};
        if (rc < 1e-6) {
            List<Vector2> sq = new ArrayList<>(4);
            for (double[] c : corners) sq.add(new Vector2((float) (cx + c[0]), (float) (cy + c[1])));
            return sq;
        }
        List<Vector2> pts = new ArrayList<>(28);
        for (int q = 0; q < 4; q++) {
            for (int i = 0; i <= 6; i++) {
                double a = Math.PI / 2 * (q + i / 6.0);
                pts.add(new Vector2((float) (cx + corners[q][0] + Math.cos(a) * rc),
                        (float) (cy + corners[q][1] + Math.sin(a) * rc)));
            }
        }
        return pts;
    }

    /** Is the screen point inside the clip shape? */
    static boolean insideClip(double x, double y, double cx, double cy, double r) {
        double dx = x - cx, dy = y - cy;
        if (!squareClip) return dx * dx + dy * dy <= r * r;
        return Math.abs(dx) <= r && Math.abs(dy) <= r;
    }

    /** The point pulled onto the clip shape's edge, `inset` px inside it, along the ray from the centre (a point
     *  already inside stays where it is). */
    static Vector2 clampToClip(Vector2 p, double cx, double cy, double r, double inset) {
        double dx = p.getX() - cx, dy = p.getY() - cy;
        double h = r - inset;
        double m = squareClip ? Math.max(Math.abs(dx), Math.abs(dy)) : Math.hypot(dx, dy);
        if (m <= h || m < 1e-6) return p;
        return new Vector2((float) (cx + dx * h / m), (float) (cy + dy * h / m));
    }

    /** The parts of a polyline inside the clip shape. */
    static List<List<Vector2>> clipRun(List<Vector2> pts, double cx, double cy, double r) {
        return squareClip ? clipToSquare(pts, cx, cy, r) : clipToCircle(pts, cx, cy, r);
    }

    /** The parts of a polyline inside the axis-aligned square of half size {@code r} (Liang-Barsky per segment). */
    static List<List<Vector2>> clipToSquare(List<Vector2> pts, double cx, double cy, double r) {
        List<List<Vector2>> runs = new ArrayList<>();
        List<Vector2> cur = null;
        for (int i = 0; i + 1 < pts.size(); i++) {
            double ax = pts.get(i).getX() - cx, ay = pts.get(i).getY() - cy;
            double dx = pts.get(i + 1).getX() - cx - ax, dy = pts.get(i + 1).getY() - cy - ay;
            double t0 = 0, t1 = 1;
            double[] p = {-dx, dx, -dy, dy}, q = {ax + r, r - ax, ay + r, r - ay};
            boolean out = false;
            for (int k = 0; k < 4 && !out; k++) {
                if (Math.abs(p[k]) < 1e-12) {
                    if (q[k] < 0) out = true;
                } else {
                    double t = q[k] / p[k];
                    if (p[k] < 0) t0 = Math.max(t0, t); else t1 = Math.min(t1, t);
                    if (t0 > t1) out = true;
                }
            }
            if (out) { cur = null; continue; }
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
