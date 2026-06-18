package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node3D;

/**
 * In-scene anchor for a {@link WorldZone} (PLAN.md Part E / E1).
 *
 * <p>{@link WorldZone} is pure data and an AutoLoad script can't take inspector-assigned zone
 * {@code .tres}, so designers drop a {@code WorldZoneMarker} into the level, assign a zone, and
 * position it — the marker's <b>global position is the zone center</b>. It registers itself with
 * {@link WorldZoneManager} in {@code _ready()} and deregisters in {@code _exitTree()} (the same
 * register-with-AutoLoad idiom {@code Character} uses with {@code SpatialEntityGrid}). AutoLoads are
 * ready before the main scene, so the manager exists when a marker's {@code _ready} runs.
 */
@RegisterClass(className = "WorldZoneMarker")
public class WorldZoneMarker extends Node3D {

    /** The zone this marker anchors. */
    @Export @RegisterProperty public WorldZone zone;

    @RegisterFunction
    @Override
    public void _ready() {
        WorldZoneManager mgr = WorldZoneManager.get();
        if (mgr != null) mgr.registerMarker(this);
    }

    @RegisterFunction
    @Override
    public void _exitTree() {
        WorldZoneManager mgr = WorldZoneManager.get();
        if (mgr != null) mgr.unregisterMarker(this);
    }
}
