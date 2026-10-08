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
 * down along it"): an Area3D in front of a climbable face. A character inside it climbs (movement.character
 * .MovementController's ladder branch, CS 1.6's rule): pushing INTO the ladder goes up while looking level or up and
 * down while looking down, pushing away does the opposite, sideways slides along it, jump lets go, and at the top a
 * push carries the body onto the ledge. No animation (the body keeps its stance clip). Its {@code -Z} points INTO the
 * face (the way a climber looks); {@link #top} is the ledge's height over the node's origin. Built by
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
        connect(new StringName("body_entered"), godot.core.MethodCallable.createUnsafe(this, "on_body_entered"));
        connect(new StringName("body_exited"), godot.core.MethodCallable.createUnsafe(this, "on_body_exited"));
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
