package com.environment;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.StaticBody3D;

/**
 * Attach as the script on any StaticBody3D that needs non-default impact particles.
 * Objects without this script automatically receive DEFAULT particles.
 *
 * In the Godot editor, replace the node's script (or change its type) to HittableBody
 * and set surfaceType to one of: FLESH, METAL, STONE, WOOD, DEFAULT.
 *
 * Characters resolve to FLESH automatically in ImpactManager — no script needed on them.
 */
@RegisterClass(className = "HittableBody")
public class HittableBody extends StaticBody3D {

    @Export
    @RegisterProperty
    public String surfaceType = SurfaceType.DEFAULT.name();

    public SurfaceType getSurfaceType() {
        try {
            return SurfaceType.valueOf(surfaceType.toUpperCase());
        } catch (IllegalArgumentException e) {
            return SurfaceType.DEFAULT;
        }
    }
}
