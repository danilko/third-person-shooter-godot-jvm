package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.StaticBody3D;
import com.openworld.world.manager.ImpactManager;

/**
 * Attach as the script on any StaticBody3D that needs non-default impact particles.
 * Objects without this script automatically receive DEFAULT particles.
 *
 * In the Godot editor, replace the node's script (or change its type) to HittableBody
 * and set surfaceType to one of: FLESH, METAL, STONE, WOOD, DEFAULT.
 *
 * Characters resolve to FLESH automatically in ImpactManager — no script needed on them.
 */
@Script(className = "HittableBody")
public class HittableBody extends StaticBody3D {

    @Export
    public String surfaceType = SurfaceType.DEFAULT.name();

    /**
     * The exported {@code surfaceType} name as its enum. Not {@code getSurfaceType} — that
     * shape would bind the String field to an enum-typed accessor property.
     */
    public SurfaceType resolveSurfaceType() {
        try {
            return SurfaceType.valueOf(surfaceType.toUpperCase());
        } catch (IllegalArgumentException e) {
            return SurfaceType.DEFAULT;
        }
    }
}
