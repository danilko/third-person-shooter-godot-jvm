package com.openworld.world;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Area3D;
import godot.api.Node3D;
import godot.core.StringName;
import godot.core.Vector3;

/**
 * A vertical ladder (user 2026-10-07: "a vertical stair at the platform, like early CS 1.6, the character flows up and
 * down along it"): an Area3D in front of a climbable face. Being inside it grabs nothing: a character GRABS it by
 * walking into the face (within MovementController.LADDER_GRAB_DEG, from below the ledge) or with the interact key
 * (from the ledge too); on it, forward climbs up and over the top, back climbs down and steps off at the foot, jump or
 * interact lets go (movement.character.MovementController's ladder branch). No animation. Its {@code -Z} points INTO
 * the face (the way a climber looks); {@link #top} is the ledge's height over the node's origin. Built by
 * build_building_scenes.gd from a layout's {@code ladders} (station platforms: tools/station_layout.py).
 */
@Script(className = "Ladder")
public class Ladder extends Area3D {

    /** The ledge the ladder leads up to, metres above this node's origin. */
    @Export public float top = 1.26f;

    @Register
    @Override
    public void _ready() {
        setCollisionLayer(0);
        setCollisionMask(com.openworld.util.CollisionLayers.CHARACTER);
        setMonitoring(true);
        connect("body_entered", godot.core.MethodCallable.createUnsafe(this, "on_body_entered"));
        connect("body_exited", godot.core.MethodCallable.createUnsafe(this, "on_body_exited"));
    }

    /** The ladder's outward horizontal normal (away from the face, toward the climber's back), world. */
    public Vector3 outward() {
        Vector3 z = getGlobalTransform().getBasis().getColumn(2);
        z.setY(0);
        return z.length() > 1e-4 ? z.normalized() : new Vector3(0, 0, 1);
    }

    /** The world height of the ledge. */
    public double topY() { return getGlobalPosition().getY() + top; }

    @Register
    public void onBodyEntered(Node3D body) {
        if (body instanceof Character c && c.movementControllerNow() != null) c.movementControllerNow().setLadder(this);
    }

    @Register
    public void onBodyExited(Node3D body) {
        if (body instanceof Character c && c.movementControllerNow() != null) c.movementControllerNow().clearLadder(this);
    }
}
