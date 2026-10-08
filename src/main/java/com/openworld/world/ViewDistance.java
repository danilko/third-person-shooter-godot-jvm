package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Camera3D;
import godot.api.Environment;
import godot.api.GeometryInstance3D;
import godot.api.Node;
import godot.api.Viewport;
import godot.api.World3D;
import godot.api.WorldEnvironment;
import godot.core.AABB;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

/**
 * "How far can the player see" — the ONE owner (PLAN.md 2b), registered as the AutoLoad "ViewDistance".
 *
 * <p>The GTA SA trick: a light aerial haze for the look (Sky3D's screen fog, the user's option B), plus a NARROW
 * Godot depth-fog band that goes from clear to fully opaque over {@link #band} metres ending at the view distance
 * D, tinted to the sky behind it; nothing past D can then be seen, so every mesh is culled at D plus its own
 * radius (its nearest point is then in full fog). Measured on `shot_city.gd --fogs=...+cull:D`: culled and
 * not-culled pictures differ only on moving things.
 *
 * <p><b>D is not one number.</b> At street level it is {@link #streetDistance} (user pick, 2026-10-08: 500 m); it
 * grows with the camera's height above the ground ({@link #heightGain} per metre past {@link #heightFree}), because
 * a fixed D is a white wall from 120 m up; and it grows while a scope is raised (the camera FOV narrows), so a
 * sniper can see as far as he can aim. Collision, AI, traffic and the map are NOT affected: only drawing.
 *
 * <p><b>The cut moves in steps, the fog follows it smoothly.</b> Rewriting thousands of ranges costs a pass, so
 * the CULL distance is quantised to {@link #cullStep} and rewritten over several frames
 * ({@link #passBudget} meshes a frame); the FOG end is the eased D, never past the cut actually in force. Growing:
 * the cut grows first, then the fog. Shrinking: the fog comes in at once (extra meshes are drawn inside full fog
 * for a few frames, which costs nothing visible), then the cut follows.
 *
 * <p>A mesh's own shorter range (a building's height rule, a crowd's draw distance) always wins: the range applied
 * is {@code min(own, D + radius)}. A mesh whose radius is over {@link #maxRadius} (the far ocean, Sky3D's fog
 * quad) is left alone, as are Terrain3D and Sky3D. Meshes are found by {@code SceneTree.node_added} and measured
 * one frame later (a mesh is often given after {@code add_child}).
 *
 * <p>{@code OW_NO_VIEW_DISTANCE=1} (or {@link #enabled} off) is the control: every range and the fog put back.
 */
@Script(className = "ViewDistance")
public class ViewDistance extends Node {

    private static ViewDistance instance;

    /** The live owner, or null if the AutoLoad isn't present. */
    public static ViewDistance get() { return instance; }

    @Export public boolean enabled = System.getenv("OW_NO_VIEW_DISTANCE") == null;
    /** D at street level (m): the depth fog is opaque here and nothing past it is drawn. */
    @Export public double streetDistance = 500.0;
    /** Width of the depth-fog band before D (clear -> opaque). */
    @Export public double band = 150.0;
    /** Height above ground (m) that still counts as street level. */
    @Export public double heightFree = 15.0;
    /** Extra D per metre of height past {@link #heightFree}. */
    @Export public double heightGain = 4.0;
    /** D never grows past this. */
    @Export public double maxDistance = 3000.0;
    /** D while a scope is raised: at least this (and street D x the zoom, up to it). */
    @Export public double scopedDistance = 1000.0;
    /** Unzoomed vertical FOV (deg) the zoom is measured against, and the zoom that counts as a scope. */
    @Export public double referenceFov = 75.0;
    @Export public double scopeZoom = 1.8;
    /** The cut is rewritten in steps of this (m); hysteresis {@link #cullHysteresis} before it shrinks. */
    @Export public double cullStep = 250.0;
    @Export public double cullHysteresis = 100.0;
    /** How fast the fog end eases (1/s). */
    @Export public double ease = 2.0;
    /** Meshes rewritten per frame during a pass, and measured per frame from the add queue. */
    @Export public int passBudget = 1500;
    /** Meshes wider than this (radius, m) are never culled. */
    @Export public double maxRadius = 1200.0;
    /** Option B: Sky3D's screen haze. */
    @Export public double hazeDensity = 0.0007;
    @Export public double hazeEnd = 1000.0;

    /** Readouts: the eased D, the cut in force and the cut being written. */
    @Visible public double distance = 500.0;
    @Visible public double cullApplied = 0.0;
    @Visible public double cullTarget = 0.0;
    @Visible public int tracked = 0;

    /** One tracked mesh: own range (0 = none), radius, last range we wrote. */
    private static final class Rec {
        final GeometryInstance3D g;
        double own, r, last;
        Rec(GeometryInstance3D g, double own, double r) { this.g = g; this.own = own; this.r = r; this.last = own; }
    }

    /** instance id -> record. */
    private final Map<Long, Rec> meshes = new HashMap<>();
    private final ArrayDeque<GeometryInstance3D> pending = new ArrayDeque<>();
    /** The pass walks a SNAPSHOT: meshes streamed in during it go straight into the map at the cut in force. */
    private ArrayList<Map.Entry<Long, Rec>> pass;
    private int passAt;
    private double passCut;

    private Environment env;
    private Node sky;
    private long envScene = -1;
    private boolean fogOwned;
    private boolean wasEnabled;
    private double skyRetry;
    private double pruneTimer = 10.0;

    @Register
    @Override
    public void _ready() {
        instance = this;
        getTree().connect(new StringName("node_added"), MethodCallable.createUnsafe(this, "on_node_added"));
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        meshes.clear();
        pending.clear();
        pass = null;
    }

    @Register
    public void onNodeAdded(Node n) {
        if (n instanceof GeometryInstance3D g) pending.add(g);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (!enabled) {
            if (wasEnabled) restoreAll();
            wasEnabled = false;
            return;
        }
        wasEnabled = true;
        measurePending();
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam == null) return;
        double want = wantedDistance(cam);
        double k = 1.0 - Math.exp(-ease * delta);
        distance += (want - distance) * k;
        if (Math.abs(want - distance) < 0.5) distance = want;

        double step = Math.max(10.0, cullStep);
        double up = Math.ceil(want / step) * step;
        if (cullTarget <= 0.0 || up > cullTarget || want < cullTarget - step - cullHysteresis) cullTarget = up;
        pruneTimer -= delta;
        if (pass == null && cullTarget != cullApplied) startPass(cullTarget);
        else if (pass == null && pruneTimer <= 0.0 && cullApplied > 0.0) startPass(cullApplied);   // drop freed meshes
        if (pruneTimer <= 0.0) pruneTimer = 10.0;
        runPass();
        applyFog(cullApplied > 0.0 ? Math.min(distance, cullApplied) : distance);
    }

    private double wantedDistance(Camera3D cam) {
        Vector3 p = cam.getGlobalPosition();
        WorldBounds wb = WorldBounds.get();
        double ground = wb != null ? wb.terrainHeight(p.getX(), p.getZ()) : Double.NaN;
        if (Double.isNaN(ground)) ground = 0.0;
        double h = p.getY() - Math.max(0.0, ground);
        double d = streetDistance + heightGain * Math.max(0.0, h - heightFree);
        double fov = cam.getFov();
        if (fov > 1.0) {
            double zoom = Math.tan(Math.toRadians(referenceFov) / 2.0) / Math.tan(Math.toRadians(fov) / 2.0);
            if (zoom >= scopeZoom) d = Math.max(d, Math.min(scopedDistance, streetDistance * zoom));
        }
        return Math.min(maxDistance, d);
    }

    private void measurePending() {
        int n = 0;
        while (!pending.isEmpty() && n < passBudget) {
            GeometryInstance3D g = pending.poll();
            n++;
            if (!GD.isInstanceValid(g) || !g.isInsideTree()) continue;
            long id = g.getInstanceId();
            if (meshes.containsKey(id) || skipped(g)) continue;
            AABB box = g.getAabb();
            Vector3 s = g.getGlobalTransform().getBasis().getScale();
            double sc = Math.max(Math.abs(s.getX()), Math.max(Math.abs(s.getY()), Math.abs(s.getZ())));
            double r = box.getSize().length() * 0.5 * sc;
            if (!(r <= maxRadius)) continue;          // also NaN
            double own = g.getVisibilityRangeEnd();
            Rec rec = new Rec(g, own, r);
            meshes.put(id, rec);
            // during a pass the LARGER of the two cuts: never cut a new mesh short of where the fog may be
            double cut = pass != null ? Math.max(cullApplied, passCut) : cullApplied;
            if (cut > 0.0) write(rec, cut);
        }
        tracked = meshes.size();
    }

    private boolean skipped(GeometryInstance3D g) {
        if (g.isInGroup(new StringName("view_distance_ignore"))) return true;
        for (Node a = g.getParent(); a != null; a = a.getParent()) {
            String name = a.getName().toString();
            if ("Sky3D".equals(name) || "Terrain3D".equals(name)) return true;
            if (a == getTree().getRoot()) break;
        }
        return false;
    }

    private void startPass(double cut) {
        passCut = cut;
        pass = new ArrayList<>(meshes.entrySet());
        passAt = 0;
    }

    private void runPass() {
        if (pass == null) return;
        int n = 0;
        while (passAt < pass.size() && n < passBudget) {
            Map.Entry<Long, Rec> e = pass.get(passAt++);
            n++;
            if (!GD.isInstanceValid(e.getValue().g)) {
                meshes.remove(e.getKey());
                continue;
            }
            write(e.getValue(), passCut);
        }
        if (passAt >= pass.size()) {
            pass = null;
            cullApplied = passCut;
            tracked = meshes.size();
        }
    }

    /** min(own, cut + radius); a range somebody else changed since we wrote is their new own range. */
    private void write(Rec rec, double cut) {
        double cur = rec.g.getVisibilityRangeEnd();
        if (Math.abs(cur - rec.last) > 1e-3) rec.own = cur;
        double own = rec.own;
        double e = cut <= 0.0 ? own : (own > 0.0 ? Math.min(own, cut + rec.r) : cut + rec.r);
        if (Math.abs(e - cur) > 1e-3) rec.g.setVisibilityRangeEnd((float) e);
        rec.last = e;
    }

    private void restoreAll() {
        pass = null;
        for (Rec rec : meshes.values()) {
            if (GD.isInstanceValid(rec.g)) write(rec, 0.0);
        }
        cullApplied = 0.0;
        cullTarget = 0.0;
        if (env != null && GD.isInstanceValid(env) && fogOwned) env.setFogEnabled(false);
        if (sky != null && GD.isInstanceValid(sky)) sky.set(new StringName("fog_enabled"), false);
        fogOwned = false;
    }

    private void applyFog(double d) {
        Viewport vp = getViewport();
        World3D w = vp != null ? vp.getWorld3d() : null;
        Environment e = w != null ? w.getEnvironment() : null;
        if (e == null) {
            WorldEnvironment we = findSky();
            e = we != null ? we.getEnvironment() : null;
        }
        if (e == null) return;
        long sid = e.getInstanceId();
        if (sid != envScene || !fogOwned) {
            envScene = sid;
            env = e;
            e.setFogEnabled(true);
            e.setFogMode(Environment.FogMode.DEPTH);
            e.setFogDensity(1.0f);
            e.setFogHeightDensity(0.0f);
            e.setFogAerialPerspective(1.0f);
            e.setFogSkyAffect(0.0f);
            e.setFogDepthCurve(1.0f);
            fogOwned = true;
            sky = null;
        }
        e.setFogDepthBegin((float) Math.max(0.0, d - band));
        e.setFogDepthEnd((float) d);
        hazeOn();
    }

    /** Option B's Sky3D screen haze, set once per scene. */
    private void hazeOn() {
        if (sky != null && GD.isInstanceValid(sky)) return;
        WorldEnvironment we = findSky();
        if (we == null) return;
        sky = we;
        Node dome = we.getNodeOrNull("SkyDome");
        we.set(new StringName("fog_enabled"), true);
        if (dome != null) {
            dome.set(new StringName("fog_visible"), true);
            dome.set(new StringName("fog_start"), 0.0);
            dome.set(new StringName("fog_end"), hazeEnd);
            dome.set(new StringName("fog_density"), hazeDensity);
        }
    }

    private WorldEnvironment findSky() {
        skyRetry -= 1.0;
        if (skyRetry > 0.0) return null;
        skyRetry = 60.0;
        Node root = getTree() != null ? getTree().getRoot() : null;
        Node n = root != null ? root.findChild("Sky3D", true, false) : null;
        return n instanceof WorldEnvironment we ? we : null;
    }

    /** The view distance in force (m), for other systems' own ranges. */
    public static double current() {
        ViewDistance v = get();
        return v == null || !v.enabled ? Double.POSITIVE_INFINITY : v.distance;
    }

    @Register public double distanceNow() { return distance; }
    @Register public double cullNow() { return cullApplied; }
    @Register public int trackedNow() { return meshes.size(); }
    @Register public void setEnabledNow(boolean on) { enabled = on; }
}
