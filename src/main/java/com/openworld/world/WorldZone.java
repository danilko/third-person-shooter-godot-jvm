package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.PackedScene;
import godot.api.Resource;
import godot.core.Vector3;
import godot.core.VariantArray;

/**
 * Data for one streamed open-world zone (PLAN.md Part E / E1) — a placeholder AABB zone:
 * a bounding box plus the AI population to stream in around it. Authored as a {@code .tres}
 * and assigned to a {@link WorldZoneMarker} placed in the level; the marker's world position is
 * the zone <b>center</b>, so designers position a zone by dragging its marker.
 *
 * <p>Geometry is optional — placeholder zones leave {@link #geometry} null and only stream AI;
 * a real zone (once Blender content exists, per BLENDER_CONVENTIONS) sets a geometry scene that
 * is instanced locally on every peer when the zone loads.
 *
 * <p>Load/unload uses hysteresis ({@code unloadRadius} > {@code loadRadius}) so a player lingering
 * at the boundary does not flicker the zone in and out.
 */
@RegisterClass(className = "WorldZone")
public class WorldZone extends Resource {

    /** Stable id for logging / debugging. */
    @Export @RegisterProperty public String zoneId = "";

    /** Full extents (metres) of the spawn box, centered on the marker. AI spawn at random XZ
     *  points inside this box at the marker's Y. */
    @Export @RegisterProperty public Vector3 size = new Vector3(60.0f, 10.0f, 60.0f);

    /** Load when a player comes within this horizontal distance (m) of the marker. */
    @Export @RegisterProperty public float loadRadius = 200.0f;

    /** Unload when all players are beyond this horizontal distance (m). Must exceed loadRadius. */
    @Export @RegisterProperty public float unloadRadius = 350.0f;

    /** Optional zone geometry instanced on load (null for placeholder zones). */
    @Export @RegisterProperty public PackedScene geometry;

    /** Ambient AI spawn groups streamed in on load. */
    @Export @RegisterProperty
    public VariantArray<SpawnConfig> spawnConfigs = new VariantArray<>(SpawnConfig.class);

    /** Named story AI spawned (at stable ids) on load. */
    @Export @RegisterProperty
    public VariantArray<NamedCharacterConfig> namedCharacters =
            new VariantArray<>(NamedCharacterConfig.class);

    public WorldZone() { super(); }
}
