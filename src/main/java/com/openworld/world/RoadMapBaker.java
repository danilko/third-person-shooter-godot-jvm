package com.openworld.world;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;

/**
 * The GDScript handle on {@link RoadMap#bake} (PLAN.md 4.7b), which is static and so unreachable
 * from a tool script. {@code tools/godot/bake_road_map.gd} instances the scene, adds one of these,
 * and calls {@code bake_now} / {@code bake_status_now}.
 */
@Script(className = "RoadMapBaker")
public class RoadMapBaker extends Node {

    /** Bake the current scene's road map; the report starts "OK" or "FAIL". */
    @Register
    public String bakeNow() { return RoadMap.bake(); }

    /** "fresh", or why the committed bake does not match the scene. */
    @Register
    public String bakeStatusNow() { return RoadMap.bakeStatus(); }

    /** "bake" or "live": what the running game would draw from. */
    @Register
    public String sourceNow() { return RoadMap.source(); }
}
