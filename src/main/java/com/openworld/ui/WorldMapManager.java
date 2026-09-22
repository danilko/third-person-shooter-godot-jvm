package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.character.NameplateTarget;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.WaypointStore;
import com.openworld.world.Places;
import com.openworld.world.SpatialEntityGrid;
import com.openworld.world.ZoneManager;
import com.openworld.world.ZoneMarker;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.InputEventMouseButton;
import godot.api.InputEventMouseMotion;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Vector2;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Full-screen toggled map (PLAN.md I5, 4.7b), opened with the {@code map} action (M). It is the GTA
 * pause map: it opens FITTED to the whole world (the road map's square, i.e. to the
 * {@link com.openworld.world.WorldBounds} wall), so every road and how they connect is on screen at
 * once; the wheel zooms about the cursor, a left drag pans, a left CLICK (press and release without
 * a drag) drops a GPS waypoint ({@link Player#setWaypoint}, which records + replicates it) and a
 * right click clears it. Roads are the baked road picture ({@link RoadOverlay#drawMap}); over them
 * the local player's route, the players near the view, every player's waypoint and the player.
 *
 * <p>Overlay discipline mirrors {@code WeaponRadialMenu}: while open it sets the local
 * {@code Character.inputBlocked = true} and mouse mode {@code VISIBLE} (so a click can't fire the gun —
 * {@code Character._physicsProcess} feeds an empty command while blocked) and moves itself to the front
 * to capture clicks. <b>Does not pause the simulation</b> (host-authoritative co-op keeps running).
 */
@Script(className = "WorldMapManager")
public class WorldMapManager extends Control {

    /** World metres from the view centre to the nearer screen edge. Set to fit the world on open. */
    @Export public float rangeMeters = 250f;
    @Export public Color backgroundColor = new Color(0.02f, 0.03f, 0.05f, 0.85f);
    @Export public Color regionColor = new Color(0.4f, 0.8f, 1f, 0.6f);
    @Export public Color selfColor = new Color(1f, 1f, 1f, 1f);
    @Export public float blipRadius = 4f;

    /** Road colour (the baked road picture is tinted with it). */
    @Export public Color roadColor = RoadOverlay.ROAD;
    /** GPS route line width (px). */
    @Export public float routeWidthPx = 4f;
    /** Mouse-wheel zoom limits (metres centre-to-edge) and step. The fitted view may exceed max. */
    @Export public float minRangeMeters = 60f;
    @Export public float maxRangeMeters = 6000f;
    @Export public float zoomStep = 1.25f;
    /** A press that moves further than this (px) before release is a pan, not a click. */
    @Export public float dragThresholdPx = 6f;
    /** Characters/vehicles are drawn only within this many metres of the player. */
    @Export public float blipRangeMeters = 400f;
    /** Draw each zone's load ring (a streaming debug aid). */
    @Export public boolean showZoneRings = false;
    /** PLAN.md 3.18n: place blips, and how near a click has to land to take a blip. */
    @Export public boolean showPlaces = true;
    @Export public float placeSizePx = 9f;
    @Export public float placePickPx = 14f;
    /** Ordinary shops appear only once the view is tighter than this (m centre-to-edge); landmarks always. */
    @Export public float placeDetailRange = 900f;
    @Export public int placeFontSize = 12;
    /** The debug underlay: each streaming zone's id over its marker (PLAN.md 3.18n, "which zone is this bug in"). */
    @Export public boolean showZoneIds = false;
    /** PLAN.md 3.26: the postal grid -- 24 x 24 cells of 192 m, x across the top and y down the side, and each
     *  cell's "x-y" when zoomed in far enough to read it. Every cell, sea included. */
    @Export public boolean showPostalGrid = true;
    @Export public Color postalLabelColor = new Color(1f, 1f, 1f, 0.55f);
    /** A cell's own "x-y" is drawn only once it is this many pixels across. */
    @Export public float postalCellLabelPx = 70f;

    /** The place a click last took, or "" (probe readout). */
    private String pickedPlace = "";

    private Player player;
    private boolean open = false;
    private boolean mapDrawn = false;
    /** The world point at the centre of the view (XZ; Y unused). */
    private double viewX, viewZ;
    private boolean pressing = false, dragging = false;
    private Vector2 pressAt = new Vector2(0f, 0f), lastMouse = new Vector2(0f, 0f);

    /** Whether the road picture was drawn on the last frame the map was open (probe readout). */
    @Register
    public boolean roadMapDrawnNow() { return mapDrawn; }

    /** The map's own world→screen mapping (probe readout). */
    @Register
    public Vector2 worldToScreenNow(Vector3 world) { return worldToScreen(world); }

    /** The place a click last snapped its waypoint to, or "" (probe readout). */
    @Register
    public String pickedPlaceNow() { return pickedPlace; }

    /** How many places the map would draw at the current view (probe readout). */
    @Register
    public int placesDrawnNow() { return showPlaces ? visiblePlaces().size() : 0; }

    /** The region under a world point, as the map reads it (probe readout). */
    @Register
    public String regionAtNow(Vector3 world) { return Places.regionAt(world.getX(), world.getZ()); }

    /** The map's own screen→world mapping (probe readout); Y is the player's height. */
    @Register
    public Vector3 screenToWorldNow(Vector2 px) { Vector3 w = screenToWorld(px); return w != null ? w : Vector3.Companion.getZERO(); }

    public void wirePlayer(Player p) { player = p; }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.STOP);   // capture clicks while open
        setTextureFilter(godot.api.CanvasItem.TextureFilter.LINEAR_WITH_MIPMAPS);   // the road picture's max mips
        setVisible(false);
    }

    @Register
    @Override
    public void _input(InputEvent event) {
        if (event.isActionPressed("map", false, false)) toggle();
        else if (open && event.isActionPressed("ui_cancel", false, false)) close();
    }

    /** Clicks land here (local coords) only while the STOP control is visible/front-most. */
    @Register
    @Override
    public void _guiInput(InputEvent event) {
        if (!open || player == null) return;
        if (event instanceof InputEventMouseButton mb) {
            godot.core.MouseButton b = mb.getButtonIndex();
            if (b == godot.core.MouseButton.LEFT) {
                if (mb.isPressed()) {
                    pressing = true;
                    dragging = false;
                    pressAt = mb.getPosition();
                    lastMouse = pressAt;
                } else if (pressing) {
                    pressing = false;
                    if (!dragging) {
                        Vector3 world = screenToWorld(mb.getPosition());
                        if (world != null) {
                            // A click within `placePickPx` of a blip is a click on that PLACE, and its waypoint
                            // goes to the front of the building rather than to the bare pixel: picking a shop off
                            // the map is the whole point of drawing it. The pick radius is in PIXELS, so it does
                            // not change with zoom.
                            Places.Place hit = pickPlace(mb.getPosition());
                            pickedPlace = hit == null ? "" : hit.name();
                            player.setWaypoint(hit == null ? world : hit.go());
                        }
                    }
                    dragging = false;
                }
            } else if (mb.isPressed() && b == godot.core.MouseButton.RIGHT) {
                player.clearWaypoint();   // right-click clears the destination
            } else if (mb.isPressed() && (b == godot.core.MouseButton.WHEEL_UP || b == godot.core.MouseButton.WHEEL_DOWN)) {
                zoomAbout(mb.getPosition(), b == godot.core.MouseButton.WHEEL_UP ? 1f / zoomStep : zoomStep);
            }
        } else if (event instanceof InputEventMouseMotion mm && pressing) {
            Vector2 p = mm.getPosition();
            if (!dragging && distance(p, pressAt) > dragThresholdPx) dragging = true;
            if (dragging) {
                float scale = scale();
                viewX -= (p.getX() - lastMouse.getX()) / scale;
                viewZ -= (p.getY() - lastMouse.getY()) / scale;
                clampView();
            }
            lastMouse = p;
        }
    }

    /** Zoom by {@code factor} keeping the world point under {@code px} where it is. */
    private void zoomAbout(Vector2 px, float factor) {
        Vector3 before = screenToWorld(px);
        float max = Math.max(maxRangeMeters, fitRange());
        rangeMeters = Math.max(minRangeMeters, Math.min(max, rangeMeters * factor));
        Vector3 after = screenToWorld(px);
        if (before != null && after != null) {
            viewX += before.getX() - after.getX();
            viewZ += before.getZ() - after.getZ();
        }
        clampView();
    }

    /** The range that fits the whole map square on screen, or the current range with no map. */
    private float fitRange() {
        double[] sq = com.openworld.world.RoadMap.mapSquare();
        return sq == null ? rangeMeters : (float) (sq[2] * 0.5);
    }

    /** Keep the view centre on the map square (with no map, anywhere). */
    private void clampView() {
        double[] sq = com.openworld.world.RoadMap.mapSquare();
        if (sq == null) return;
        viewX = Math.max(sq[0], Math.min(sq[0] + sq[2], viewX));
        viewZ = Math.max(sq[1], Math.min(sq[1] + sq[2], viewZ));
    }

    /** Open fitted to the whole world; with no road map, centred on the player as before. */
    private void fitWorld() {
        double[] sq = com.openworld.world.RoadMap.mapSquare();
        if (sq != null) {
            viewX = sq[0] + sq[2] * 0.5;
            viewZ = sq[1] + sq[2] * 0.5;
            rangeMeters = (float) (sq[2] * 0.5);
        } else if (player != null) {
            Vector3 o = player.getGlobalPosition();
            viewX = o.getX();
            viewZ = o.getZ();
        }
    }

    private void toggle() { if (open) close(); else open(); }

    private void open() {
        if (player == null) return;
        open = true;
        pressing = dragging = false;
        fitWorld();
        Node parent = getParent();
        if (parent != null) parent.moveChild(this, parent.getChildCount() - 1);
        Input.setMouseMode(Input.MouseMode.VISIBLE);
        player.inputBlocked = true;
        setVisible(true);
        queueRedraw();
    }

    private void close() {
        open = false;
        if (player != null) player.inputBlocked = false;
        Input.setMouseMode(Input.MouseMode.CAPTURED);
        setVisible(false);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (open) queueRedraw();
    }

    @Register
    @Override
    public void _draw() {
        if (!open) return;
        Places.bind(this);   // the places are per scene
        Vector2 size = getSize();
        drawRect(new godot.core.Rect2(0.0, 0.0, size.getX(), size.getY()), backgroundColor, true, -1f, false);
        if (player == null || !godot.global.GD.isInstanceValid(player)) return;

        Vector2 center = size.times(0.5f);
        float scale = scale();
        Vector3 view = new Vector3(viewX, 0.0, viewZ);
        Vector3 origin = player.getGlobalPosition();

        // The postal grid goes UNDER the roads: a light checkerboard of the 192 m cells with each cell's number,
        // so the next boundary is readable at a glance without hiding what you navigate by.
        if (showPostalGrid) {
            RoadOverlay.drawPostalGrid(this, view, center, scale, 0f, (float) size.getX(), (float) size.getY(),
                    0f, RoadOverlay.mapFont(), placeFontSize, postalCellLabelPx);
        }
        // Roads (4.7b): the baked picture under the whole control, one textured quad.
        mapDrawn = RoadOverlay.drawMap(this, view, center, scale, (float) size.getX(), (float) size.getY(),
                0f, roadColor);
        if (showPlaces) {
            RoadOverlay.drawPlaces(this, visiblePlaces(), view, center, scale, 0f, 0f, placeSizePx,
                    minPlaceTier(), RoadOverlay.mapFont(), placeFontSize);
        }

        ZoneManager wzm = (showZoneRings || showZoneIds) ? ZoneManager.get() : null;
        if (wzm != null) {
            for (ZoneMarker m : wzm.getMarkers()) {
                if (m == null || !godot.global.GD.isInstanceValid(m) || m.zone == null) continue;
                Vector2 at = worldToScreen(m.getGlobalPosition());
                if (showZoneRings) drawCircle(at, m.zone.loadRadius * scale, regionColor, false, 1f, true);
                // "which zone is this bug in" is answered by reading coordinates today; this is the debug half
                // of the underlay and is off by default, because a populated world has ~200 markers.
                if (showZoneIds && RoadOverlay.mapFont() != null && m.zone.zoneId != null) {
                    drawString(RoadOverlay.mapFont(), at, m.zone.zoneId,
                            godot.core.HorizontalAlignment.LEFT, -1f, placeFontSize, regionColor);
                }
            }
        }

        if (showPostalGrid) drawPostalEdgeNumbers(size);

        Vector3 wp = player.getWaypoint();
        if (wp != null && player.characterInfo != null) {
            RoadOverlay.drawRoute(this, com.openworld.world.RoadMap.routeFor(
                    player.characterInfo.characterId, origin, wp), wp, view, center, scale, 0f,
                    routeWidthPx, player.getNameplateColor());
        }

        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid != null) {
            List<Node> near = new ArrayList<>();
            grid.queryRadius(origin, blipRangeMeters, near);
            for (Node n : near) {
                if (n == player || !(n instanceof Node3D n3) || !(n instanceof NameplateTarget nt)) continue;
                drawCircle(worldToScreen(n3.getGlobalPosition()), blipRadius, nt.getNameplateColor(), true, -1f, true);
            }
        }

        for (Map.Entry<String, Vector3> e : WaypointStore.entries().entrySet()) {
            drawWaypoint(worldToScreen(e.getValue()), waypointColor(e.getKey()));
        }

        // The player, wherever they are on the map.
        drawCircle(worldToScreen(origin), 5f, selfColor, true, -1f, true);
    }

    // ── helpers ────────────────────────────────────────────────────────────────

    /** Pixels per metre: {@link #rangeMeters} from the centre to the nearer edge (less a margin). */
    private float scale() {
        Vector2 size = getSize();
        float radiusPx = Math.min((float) size.getX(), (float) size.getY()) * 0.5f - 10f;
        return Math.max(1e-5f, radiusPx / rangeMeters);
    }

    /** The column numbers along the top edge and the row numbers down the left edge, kept on screen. */
    private void drawPostalEdgeNumbers(Vector2 size) {
        var font = RoadOverlay.mapFont();
        if (font == null) return;
        double half = com.openworld.world.PostalGrid.HALF, cell = com.openworld.world.PostalGrid.CELL;
        int n = com.openworld.world.PostalGrid.CELLS;
        float w = (float) size.getX(), h = (float) size.getY();
        int fs = placeFontSize;
        for (int k = 1; k <= n; k++) {
            double mid = -half + (k - 0.5) * cell;
            float sx = (float) worldToScreen(new Vector3(mid, 0.0, 0.0)).getX();
            float sy = (float) worldToScreen(new Vector3(0.0, 0.0, mid)).getY();
            if (sx > 0 && sx < w)
                drawString(font, new Vector2(sx - 12f, fs + 4f), Integer.toString(k),
                        godot.core.HorizontalAlignment.CENTER, 24f, fs, postalLabelColor);
            if (sy > 0 && sy < h)
                drawString(font, new Vector2(4f, sy + fs * 0.4f), Integer.toString(k),
                        godot.core.HorizontalAlignment.LEFT, -1f, fs, postalLabelColor);
        }
    }

    private Vector2 worldToScreen(Vector3 world) {
        Vector2 center = getSize().times(0.5f);
        float scale = scale();
        return new Vector2((float) (center.getX() + (world.getX() - viewX) * scale),
                           (float) (center.getY() + (world.getZ() - viewZ) * scale));
    }

    /** Invert the north-up map transform: a clicked pixel → world XZ at the player's height. */
    private Vector3 screenToWorld(Vector2 px) {
        if (player == null) return null;
        Vector2 center = getSize().times(0.5f);
        float scale = scale();
        double wx = viewX + (px.getX() - center.getX()) / scale;
        double wz = viewZ + (px.getY() - center.getY()) / scale;
        return new Vector3(wx, player.getGlobalPosition().getY(), wz);
    }

    /** Ordinary shops only once the view is tight enough that they are not a wall of blips. */
    private int minPlaceTier() { return rangeMeters > placeDetailRange ? Places.LANDMARK_TIER : 0; }

    /** The places that can fall inside the view, at the current tier. */
    private List<Places.Place> visiblePlaces() {
        Vector2 size = getSize();
        double radius = 0.5 * Math.hypot(size.getX(), size.getY()) / Math.max(1e-5f, scale());
        List<Places.Place> out = new ArrayList<>();
        int tier = minPlaceTier();
        for (Places.Place p : Places.near(new Vector3(viewX, 0.0, viewZ), radius)) {
            if (p.tier() >= tier) out.add(p);
        }
        return out;
    }

    /** The place whose blip is within {@link #placePickPx} of a screen point, or null. */
    private Places.Place pickPlace(Vector2 px) {
        if (!showPlaces) return null;
        Places.Place best = null;
        float bd = placePickPx;
        for (Places.Place p : visiblePlaces()) {
            float d = distance(px, worldToScreen(p.at()));
            if (d <= bd) { bd = d; best = p; }
        }
        return best;
    }

    private static float distance(Vector2 a, Vector2 b) {
        float dx = (float) (a.getX() - b.getX()), dy = (float) (a.getY() - b.getY());
        return (float) Math.sqrt(dx * dx + dy * dy);
    }

    private void drawWaypoint(Vector2 c, Color col) {
        float s = 7f;
        PackedVector2Array diamond = new PackedVector2Array();
        diamond.pushBack(new Vector2((float) c.getX(), (float) c.getY() - s));
        diamond.pushBack(new Vector2((float) c.getX() + s, (float) c.getY()));
        diamond.pushBack(new Vector2((float) c.getX(), (float) c.getY() + s));
        diamond.pushBack(new Vector2((float) c.getX() - s, (float) c.getY()));
        drawColoredPolygon(diamond, col, new PackedVector2Array(), null);
    }

    private Color waypointColor(String characterId) {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p != null && godot.global.GD.isInstanceValid(p) && p.characterInfo != null
                    && characterId.equals(p.characterInfo.characterId)) {
                return p.getNameplateColor();
            }
        }
        return new Color(1f, 1f, 1f, 1f);
    }
}
