package com.environment;

/**
 * Categorises a collider's surface so ImpactManager can select the right
 * particle pool from ParticleManager.
 *
 * Characters resolve to FLESH automatically — no tagging needed.
 * For any other hittable object that needs non-default particles, attach
 * a HittableBody script and set its surfaceType field.
 *
 * To add a new type: add a constant here, create a matching child container
 * in the ParticleManager scene node (named after the constant, e.g. "METAL"),
 * and populate it with GPUParticles3D nodes in the Godot editor.
 */
public enum SurfaceType {
    FLESH,    // characters — resolved automatically by ImpactManager
    METAL,    // machinery, vehicles, metal walls
    STONE,    // concrete, brick, rock
    WOOD,     // wooden surfaces, crates
    DEFAULT   // fallback for anything without a HittableBody script
}
