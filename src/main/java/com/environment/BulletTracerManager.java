package com.environment;

import godot.annotation.*;
import godot.api.*;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * World-level pool of thin MeshInstance3D quads that snap from muzzle to hit point
 * each shot and fade after tracerLifetime seconds.
 *
 * Scene setup: add one MeshInstance3D child as the template (BoxMesh size 0.01 × 0.01 × 1,
 * unshaded warm-yellow material). _ready() duplicates it to poolSize instances.
 * Add this node to the "bullet_tracer_manager" group via _ready() (done in code).
 */
@RegisterClass(className = "BulletTracerManager")
public class BulletTracerManager extends Node3D {

    @Export
    @RegisterProperty
    public float tracerLifetime = 0.06f;

    @Export
    @RegisterProperty
    public int poolSize = 16;

    private final List<MeshInstance3D> pool = new ArrayList<>();
    private final List<Float> ages = new ArrayList<>();

    @RegisterFunction
    @Override
    public void _ready() {
        addToGroup("bullet_tracer_manager");

        if (getChildCount() == 0) return;
        Node first = getChild(0);
        if (!(first instanceof MeshInstance3D template)) return;
        template.setVisible(false);

        for (int i = 0; i < poolSize; i++) {
            MeshInstance3D inst = (MeshInstance3D) template.duplicate();
            addChild(inst);
            pool.add(inst);
            ages.add(tracerLifetime); // starts expired = available
        }
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
        for (int i = 0; i < ages.size(); i++) {
            float age = ages.get(i);
            if (age >= tracerLifetime) continue;
            age += (float) delta;
            ages.set(i, age);
            if (age >= tracerLifetime) pool.get(i).setVisible(false);
        }
    }

    public void spawnTracer(Vector3 from, Vector3 to) {
        float length = (float) to.minus(from).length();
        if (length < 0.05f) return;

        MeshInstance3D tracer = acquire();
        if (tracer == null) return;

        // Place centre at midpoint, orient -Z toward hit point, scale Z to full length.
        Vector3 mid = from.plus(to.minus(from).times(0.5f));
        tracer.setGlobalPosition(mid);

        // Avoid degenerate cross-product when shot is nearly vertical.
        Vector3 up = Math.abs(to.minus(from).normalized().getY()) < 0.99f
                ? new Vector3(0, 1, 0)
                : new Vector3(1, 0, 0);
        tracer.lookAt(to, up);
        tracer.setScale(new Vector3(1, 1, length));
        tracer.setVisible(true);
    }

    private MeshInstance3D acquire() {
        for (int i = 0; i < pool.size(); i++) {
            if (ages.get(i) >= tracerLifetime) {
                ages.set(i, 0f);
                return pool.get(i);
            }
        }
        return null; // pool exhausted — skip this tracer
    }
}
