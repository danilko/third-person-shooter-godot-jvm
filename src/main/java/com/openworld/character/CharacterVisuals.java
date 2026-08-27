package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Node3D;

/**
 * Root node of a character visual scene (e.g. CharacterVisuals_GodotChan.tscn).
 * Character instantiates this from its characterVisuals PackedScene export,
 * attaches it to VisualsMount, and reads meshConfig to wire all mesh-dependent
 * references on its sibling components.
 */
@Script(className = "CharacterVisuals")
public class CharacterVisuals extends Node3D {

    /** Describes the node layout inside this visual scene. */
    @Export
    public MeshConfig meshConfig;
}
