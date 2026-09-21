package com.openworld.world;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.BaseMaterial3D;
import godot.api.GeometryInstance3D;
import godot.api.ImmediateMesh;
import godot.api.Mesh;
import godot.api.MeshInstance3D;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * The GPS route drawn ON THE ROAD — registered as the AutoLoad "RouteRibbon" (user, 2026-09-19).
 *
 * <p>A line on the radar tells you the shape of the turn; a line on the tarmac tells you WHICH LANE, and you
 * read it without looking away from the road. GTA IV/V draw one (San Andreas only drew it on the radar), and
 * here it costs almost nothing, because the hard part already exists: {@link RoadMap#routeFor} returns the
 * route as lane samples in 3D and re-routes at most once a second (a new waypoint, a rebuilt network, or the
 * body more than {@code OFF_ROUTE_METERS} from the route). So this is one {@link ImmediateMesh} rebuilt only
 * when the route or the player's progress along it has actually moved — one draw call of a few hundred
 * triangles, not a per-frame search.
 *
 * <p><b>It takes the lane's own Y</b> ({@code Route.points} is {x, y, z} triples), so it rides a bridge deck
 * and a tunnel floor correctly with no raycast. A ray down from above would have found whatever deck is
 * overhead instead, which on this island is a real case — the expressway crosses its own ramps.
 *
 * <p><b>It is DERIVED, never latched</b> (W29's rule, and `RoadMap.gpsTarget`'s): it shows what the routing
 * already says, and it disappears with the waypoint. Nothing here is saved or networked — a teammate's
 * waypoint is drawn on the MAP but each peer routes for itself.
 */
@Script(className = "RouteRibbon")
public class RouteRibbon extends Node3D {

    private static RouteRibbon instance;

    public static RouteRibbon get() { return instance; }

    /** Width of the band on the road (m). A lane is 4.5 m, so this sits inside it. */
    @Export public float widthMeters = 2.4f;
    /** How far above the lane it floats (m) — enough to clear the road's own crossfall and paint. */
    @Export public float lift = 0.12f;
    /** How much of the route ahead is drawn (m). Beyond a few hundred metres it is the map's job. */
    @Export public float lengthAhead = 250.0f;
    /** ...and how much behind, so the band does not vanish from under the car at a junction. */
    @Export public float lengthBehind = 15.0f;
    /** Seconds between rebuild checks. */
    @Export public float evalInterval = 0.2f;
    /** Alpha at the near end; it fades out along the drawn length so the far end does not read as a wall. */
    @Export public float alpha = 0.55f;
    /** The control knob: off is the map-only route this replaced. */
    @Visible public boolean enabled = true;

    private MeshInstance3D node;
    private ImmediateMesh mesh;
    private double timer;
    private Object lastRoute;
    private double lastProgress = -1e9;
    private int segments;

    @Register
    @Override
    public void _ready() { instance = this; }

    @Register
    @Override
    public void _exitTree() { if (instance == this) instance = null; }

    @Register
    @Override
    public void _process(double delta) {
        timer -= delta;
        if (timer > 0.0) return;
        timer = Math.max(0.05f, evalInterval);
        Player p = localPlayer();
        if (!enabled || p == null || p.getWaypoint() == null || p.characterInfo == null) {
            hideBand();
            return;
        }
        Vector3 origin = p.getGlobalPosition();
        RoadGraph.Route r = RoadMap.routeFor(p.characterInfo.characterId, origin, p.getWaypoint());
        if (r == null || r.pointCount() < 2) {
            hideBand();
            return;
        }
        double progress = r.progressOf(origin.getX(), origin.getZ());
        // rebuild only when it would look different: a new route, or 5 m of travel along this one
        if (r == lastRoute && Math.abs(progress - lastProgress) < 5.0 && node != null && node.isVisible()) return;
        lastRoute = r;
        lastProgress = progress;
        build(r, progress, p.getNameplateColor());
    }

    private void build(RoadGraph.Route r, double progress, Color color) {
        ensureNode();
        double[] pts = r.points;
        int n = r.pointCount();
        mesh.clearSurfaces();
        mesh.surfaceBegin(Mesh.PrimitiveType.TRIANGLE_STRIP, null);
        double from = progress - lengthBehind, to = progress + lengthAhead;
        double s = 0.0;
        int drawn = 0;
        Vector3 prev = null;
        for (int i = 0; i < n; i++) {
            Vector3 here = new Vector3(pts[3 * i], pts[3 * i + 1] + lift, pts[3 * i + 2]);
            if (prev != null) s += Math.hypot(here.getX() - prev.getX(), here.getZ() - prev.getZ());
            prev = here;
            if (s < from || s > to) continue;
            Vector3 next = new Vector3(pts[3 * Math.min(i + 1, n - 1)], 0.0, pts[3 * Math.min(i + 1, n - 1) + 2]);
            Vector3 back = new Vector3(pts[3 * Math.max(i - 1, 0)], 0.0, pts[3 * Math.max(i - 1, 0) + 2]);
            Vector3 along = next.minus(back);
            if (along.lengthSquared() < 1e-9) continue;
            // the band lies FLAT on the road, so its width runs across the lane, not toward the camera
            Vector3 side = new Vector3(-along.getZ(), 0.0, along.getX()).normalized().times(widthMeters * 0.5);
            double fade = 1.0 - Math.max(0.0, (s - progress) / Math.max(1.0, lengthAhead));
            mesh.surfaceSetColor(new Color(color.getR(), color.getG(), color.getB(), alpha * fade));
            mesh.surfaceAddVertex(here.plus(side));
            mesh.surfaceAddVertex(here.minus(side));
            drawn++;
        }
        mesh.surfaceEnd();
        segments = Math.max(0, drawn - 1);
        node.setVisible(drawn >= 2);
    }

    private void hideBand() {
        segments = 0;
        lastRoute = null;
        if (node != null && GD.isInstanceValid(node)) node.setVisible(false);
    }

    private Player localPlayer() {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p != null && GD.isInstanceValid(p) && p.isLocallyOwnedPlayer()) return p;
        }
        return null;
    }

    private void ensureNode() {
        if (node != null && GD.isInstanceValid(node)) return;
        mesh = new ImmediateMesh();
        node = new MeshInstance3D();
        node.setName(new StringName("RouteBand"));
        node.setMesh(mesh);
        node.setAsTopLevel(true);
        node.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        StandardMaterial3D m = new StandardMaterial3D();
        m.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        m.setFlag(BaseMaterial3D.Flags.ALBEDO_FROM_VERTEX_COLOR, true);
        m.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        m.setCullMode(BaseMaterial3D.CullMode.DISABLED);
        // NOT depth-test-disabled, unlike the grenade arc: a route band that draws through buildings and cars
        // reads as a bug. The `lift` is what keeps it off the tarmac instead.
        node.setMaterialOverride(m);
        addChild(node);
        node.setGlobalTransform(new Transform3D());
    }

    // ── Probe readouts ────────────────────────────────────────────────────────

    /** Quads in the band right now (0 = not drawn). */
    @Register public int bandSegmentsNow() { return node != null && node.isVisible() ? segments : 0; }

    /** Is the band on screen at all? */
    @Register public boolean bandShownNow() { return node != null && GD.isInstanceValid(node) && node.isVisible(); }
}
