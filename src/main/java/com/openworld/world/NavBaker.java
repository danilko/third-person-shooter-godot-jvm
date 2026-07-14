package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.NavigationMesh;
import godot.api.NavigationMeshSourceGeometryData3D;
import godot.api.NavigationRegion3D;
import godot.api.NavigationServer3D;
import godot.api.Node;
import godot.api.PackedScene;
import godot.api.ResourceSaver;
import godot.core.Error;
import godot.core.StringName;
import godot.global.GD;

/**
 * Bakes a {@link NavigationRegion3D} into an already-baked district {@code .tscn} (PLAN.md I6
 * "stays Godot-side: pedestrian navmesh bake"), from that scene's own collision geometry
 * ({@code StaticBody3D}/{@code ConcavePolygonShape3D} — the coarse collision proxies
 * {@code WorldBaker}'s visual bulk rides alongside, per CLAUDE.md's Combat/Weapon System note that
 * a {@code MultiMesh} carries no collision of its own).
 *
 * <p>Uses the runtime (non-editor) navmesh-baking API — the same class of workaround
 * {@code WorldBaker} already established as the only option here (godot-kotlin-jvm 0.15.0-4.6
 * exposes no editor API — see CLAUDE.md Known Quirks). <b>Deliberately calls the two-step
 * {@link NavigationServer3D#parseSourceGeometryData}/{@link NavigationServer3D#bakeFromSourceGeometryData}
 * pair, not the single-call {@code NavigationMeshGenerator.bake()} convenience wrapper</b> — that
 * wrapper was verified (empirically, against a trivial hand-built ground plane) to silently return
 * zero polygons in this godot-kotlin-jvm binding, while the explicit two-step call it should be
 * equivalent to works correctly. {@code STATIC_COLLIDERS} parsing means this needs only
 * {@code PhysicsServer3D}-side shape data, not a live {@code RenderingServer} — unlike
 * {@code WorldBaker}'s MultiMesh step, this bake works fine under {@code --headless}.
 *
 * <p>Deliberately a separate class from {@code WorldBaker}: that one converts a glTF source into a
 * native scene; this one enriches an <b>already-native</b>, already-baked scene with a second
 * artifact (a nav region) built from ITS OWN geometry — a different operation with a different
 * input, run as its own pass after the glTF bake completes and is saved to disk.
 *
 * <p>Baked in the district's own local frame (each district's content sits at local origin per
 * {@code build_district.py}), so the region's baked polygons translate correctly for free when
 * {@code WorldZoneManager} streams the district in at its zone's world position — a
 * {@code NavigationRegion3D} is a normal descendant node and inherits its ancestors' transform like
 * any other. {@code useEdgeConnections} stays on (the default) so adjacent, edge-abutting
 * districts' regions merge into one traversable navmesh at their seam once both are streamed in —
 * per Godot's own edge-connection-margin merging, not anything district-specific here.
 */
@RegisterClass(className = "NavBaker")
public class NavBaker extends Node {

    @Export @RegisterProperty public String scenePath = "";
    @Export @RegisterProperty public boolean bakeOnReady = false;
    @Export @RegisterProperty public boolean quitWhenDone = false;

    /** Roughly a human character's capsule (CLAUDE.md's stance/movement scale) — not tuned per district. */
    private static final float AGENT_HEIGHT = 1.8f;
    private static final float AGENT_RADIUS = 0.4f;
    private static final float AGENT_MAX_CLIMB = 0.5f;
    private static final float AGENT_MAX_SLOPE_DEG = 46f;

    /**
     * Rasterization voxel size (engine default is 0.25/0.25). Coarsened for the DEM-terrain
     * districts: the real PLATEAU TIN is dense and irregular, and at the default resolution the
     * polygonizer emits a handful of duplicate free edges where TIN detail and building collision
     * proxies interleave — Godot then logs "Navigation region synchronization had N edge error(s)"
     * on every region sync at runtime. Halving the resolution re-polygonizes those spots away and
     * shrinks the mesh; centimetre-precision walkability is meaningless on 504 m district chunks.
     */
    private static final float CELL_SIZE = 0.5f;
    private static final float CELL_HEIGHT = 0.5f;

    /**
     * Clip the bake to the district's own 504 m grid cell ({@code world_grid.DISTRICT}, content
     * centered at local origin). The PLATEAU TIN + border-building colliders spill 10–25 m past the
     * cell edge, so an unclipped bake overlaps its neighbours' — and two loaded neighbours then
     * rasterize the same map cells at the seam, which is Godot's "More than 2 edges tried to occupy
     * the same map rasterization space" edge error.
     *
     * <p>{@code NAV_CLIP_INSET}: the clip is pulled a further 0.5 m INSIDE the cell on every side.
     * Regions that abut <i>exactly</i> still share border rasterization cells, and wherever a third
     * edge lands in one of those cells (notably 4-district corners) the same ">2 edges" warning
     * fires. The inset leaves a deliberate 1 m gap between neighbouring navmeshes so they never
     * share a cell; the map's edge-connection pass (see {@code navigation/3d/
     * default_edge_connection_margin = 1.5} in project.godot, raised from the 0.25 default to
     * bridge this gap) still connects the two free edges, so cross-district pathing is unaffected.
     */
    private static final float DISTRICT_HALF_EXTENT = 252f;
    private static final float NAV_CLIP_INSET = 0.5f;
    private static final float CLIP_Y_MIN = -100f;
    private static final float CLIP_Y_MAX = 1000f;

    @RegisterFunction
    @Override
    public void _ready() {
        if (bakeOnReady) bake();
    }

    public void bake() {
        bake(this, scenePath);
        if (quitWhenDone && getTree() != null) getTree().quit();
    }

    /**
     * Loads {@code scenePath} (an already-baked native district scene), adds a
     * {@code NavigationRegion3D} baked from its own static-collider geometry, and re-saves over
     * the same path. {@code host} must be in the tree (mirrors {@code WorldBaker.bake}'s contract).
     */
    public static void bake(Node host, String scenePath) {
        Object loaded = GD.load(scenePath);
        if (!(loaded instanceof PackedScene src)) {
            GD.printErr("NavBaker: could not load source scene '" + scenePath + "'");
            return;
        }
        Node root = src.instantiate();
        if (root == null) { GD.printErr("NavBaker: source instantiate failed"); return; }
        host.addChild(root);

        // Idempotence: drop any BakedNav a previous run left behind BEFORE parsing source geometry —
        // re-baking must replace the region, not stack a second identical navmesh on top of it
        // (overlapping duplicates are exactly what trips the runtime "edge error(s)" warning).
        Node stale = root.getNodeOrNull(new godot.core.NodePath("BakedNav"));
        if (stale != null) { root.removeChild(stale); stale.queueFree(); }

        NavigationMesh navMesh = new NavigationMesh();
        navMesh.setParsedGeometryType(NavigationMesh.ParsedGeometryType.STATIC_COLLIDERS);
        navMesh.setAgentHeight(AGENT_HEIGHT);
        navMesh.setAgentRadius(AGENT_RADIUS);
        navMesh.setAgentMaxClimb(AGENT_MAX_CLIMB);
        navMesh.setAgentMaxSlope(AGENT_MAX_SLOPE_DEG);
        navMesh.setCellSize(CELL_SIZE);
        navMesh.setCellHeight(CELL_HEIGHT);
        float clipHalf = DISTRICT_HALF_EXTENT - NAV_CLIP_INSET;
        navMesh.setFilterBakingAabb(new godot.core.AABB(
                new godot.core.Vector3(-clipHalf, CLIP_Y_MIN, -clipHalf),
                new godot.core.Vector3(2 * clipHalf, CLIP_Y_MAX - CLIP_Y_MIN, 2 * clipHalf)));

        // Two explicit steps (see class doc for why, not NavigationMeshGenerator.bake()): scan
        // root's whole subtree for STATIC_COLLIDERS geometry, then bake polygons from it.
        NavigationMeshSourceGeometryData3D srcData = new NavigationMeshSourceGeometryData3D();
        NavigationServer3D.INSTANCE.parseSourceGeometryData(navMesh, srcData, root);
        NavigationServer3D.INSTANCE.bakeFromSourceGeometryData(navMesh, srcData);
        int vertexCount = navMesh.getVertices().getSize();

        NavigationRegion3D navRegion = new NavigationRegion3D();
        navRegion.setName(new StringName("BakedNav"));
        navRegion.setUseEdgeConnections(true);
        root.addChild(navRegion);
        navRegion.setOwner(root);
        navRegion.setNavigationMesh(navMesh);

        PackedScene packed = new PackedScene();
        Error err = packed.pack(root);
        if (err == Error.OK) {
            Error save = ResourceSaver.save(packed, scenePath, ResourceSaver.SaverFlags.FLAG_NONE);
            GD.print("NavBaker: baked nav for '" + scenePath + "' (" + (save == Error.OK ? "saved" : "save FAILED " + save)
                    + ") — vertices=" + vertexCount);
        } else {
            GD.printErr("NavBaker: pack() failed: " + err);
        }
        host.removeChild(root);
        root.queueFree();
    }
}
