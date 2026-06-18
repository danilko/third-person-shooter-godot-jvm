package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.BaseMaterial3D;
import godot.api.BoxMesh;
import godot.api.CylinderMesh;
import godot.api.MeshInstance3D;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.core.Color;
import godot.core.Vector3;

/**
 * In-scene anchor for a {@link WorldZone} (PLAN.md Part E / E1).
 *
 * <p>{@link WorldZone} is pure data and an AutoLoad script can't take inspector-assigned zone
 * {@code .tres}, so designers drop a {@code WorldZoneMarker} into the level, assign a zone, and
 * position it — the marker's <b>global position is the zone center</b>. It registers itself with
 * {@link WorldZoneManager} in {@code _ready()} and deregisters in {@code _exitTree()} (the same
 * register-with-AutoLoad idiom {@code Character} uses with {@code SpatialEntityGrid}). AutoLoads are
 * ready before the main scene, so the manager exists when a marker's {@code _ready} runs.
 *
 * <p><b>Debug visualization:</b> when {@link #showDebugVolume} is on (default), the marker builds at
 * runtime a translucent box matching {@code zone.size} (the spawn volume) plus two flat rings at
 * {@code loadRadius}/{@code unloadRadius}, so you can <i>see</i> a zone and walk into it. The box
 * tints green while the zone is streamed in (driven by {@link #setLoadedVisual} from the manager) and
 * cyan while idle. These are pure debug meshes — delete-free in a shipping build by toggling the flag.
 */
@RegisterClass(className = "WorldZoneMarker")
public class WorldZoneMarker extends Node3D {

    /** The zone this marker anchors. */
    @Export @RegisterProperty public WorldZone zone;

    /** Draw the translucent spawn-volume box + load/unload rings at runtime (debug aid). */
    @Export @RegisterProperty public boolean showDebugVolume = true;

    private static final Color IDLE_COLOR   = new Color(0.0, 0.7, 1.0, 0.12);  // cyan  — unloaded
    private static final Color LOADED_COLOR = new Color(0.1, 1.0, 0.3, 0.20);  // green — streamed in
    private static final Color LOAD_RING    = new Color(1.0, 0.85, 0.0, 0.10); // yellow ring (load)
    private static final Color UNLOAD_RING  = new Color(1.0, 0.25, 0.2, 0.07); // red ring  (unload)

    private StandardMaterial3D volumeMat;  // box material, recoloured on load/unload

    @RegisterFunction
    @Override
    public void _ready() {
        WorldZoneManager mgr = WorldZoneManager.get();
        if (mgr != null) mgr.registerMarker(this);
        if (showDebugVolume && zone != null) buildDebugVisuals();
    }

    @RegisterFunction
    @Override
    public void _exitTree() {
        WorldZoneManager mgr = WorldZoneManager.get();
        if (mgr != null) mgr.unregisterMarker(this);
    }

    /** Recolour the spawn-volume box to reflect streamed-in (green) vs idle (cyan). */
    public void setLoadedVisual(boolean loaded) {
        if (volumeMat != null) volumeMat.setAlbedo(loaded ? LOADED_COLOR : IDLE_COLOR);
    }

    // ── Debug mesh construction ───────────────────────────────────────────────

    private void buildDebugVisuals() {
        volumeMat = makeMaterial(IDLE_COLOR);
        BoxMesh box = new BoxMesh();
        box.setSize(zone.size);
        MeshInstance3D boxInst = new MeshInstance3D();
        boxInst.setMesh(box);
        boxInst.setMaterialOverride(volumeMat);
        addChild(boxInst);

        addRing(zone.loadRadius, LOAD_RING);
        addRing(zone.unloadRadius, UNLOAD_RING);
    }

    private void addRing(float radius, Color color) {
        CylinderMesh disc = new CylinderMesh();
        disc.setTopRadius(radius);
        disc.setBottomRadius(radius);
        disc.setHeight(0.1f);
        disc.setRadialSegments(48);
        MeshInstance3D inst = new MeshInstance3D();
        inst.setMesh(disc);
        inst.setMaterialOverride(makeMaterial(color));
        addChild(inst);
    }

    private StandardMaterial3D makeMaterial(Color color) {
        StandardMaterial3D mat = new StandardMaterial3D();
        mat.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        mat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        mat.setCullMode(BaseMaterial3D.CullMode.DISABLED);
        mat.setAlbedo(color);
        return mat;
    }
}
