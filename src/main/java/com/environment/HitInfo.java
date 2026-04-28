package com.environment;

import godot.api.Node;
import godot.core.Vector3;

/**
 * Immutable snapshot of one raycast hit.
 *
 * Passed from WeaponController to ImpactManager so the processHit() signature
 * stays stable as new effects are added (decals, sounds, impulse, etc.).
 *
 * Network note: this is the struct that would be serialized and transmitted
 * for deterministic hit replay. All fields are value types or stable node refs.
 */
public class HitInfo {

    /** The colliding node returned by AimRay (may be null if ray hit nothing). */
    public final Node    hitNode;

    /** World-space point of impact. */
    public final Vector3 hitPoint;

    /**
     * Outward surface normal at the impact point, from AimRay.getCollisionNormal().
     * Used to orient decals and to compute physically-correct impulse directions.
     */
    public final Vector3 hitNormal;

    public HitInfo(Node hitNode, Vector3 hitPoint, Vector3 hitNormal) {
        this.hitNode   = hitNode;
        this.hitPoint  = hitPoint;
        this.hitNormal = hitNormal;
    }
}
