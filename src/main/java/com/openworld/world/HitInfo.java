package com.openworld.world;

import godot.api.Node;
import godot.core.Vector3;
import com.openworld.weapon.WeaponController;
import com.openworld.world.manager.ImpactManager;

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

    /**
     * The weapon's per-round damage that sizes the mark (a bullet hole by calibre), or 0 = size it from the damage
     * dealt. A firearm states it on every path -- its own hit, a client's prediction, a peer's replay of a host-resolved
     * shot -- so the hole is the same size on every peer whatever the dealt damage was (a window took some, a headshot).
     */
    public final float calibre;

    public HitInfo(Node hitNode, Vector3 hitPoint, Vector3 hitNormal) { this(hitNode, hitPoint, hitNormal, 0f); }

    public HitInfo(Node hitNode, Vector3 hitPoint, Vector3 hitNormal, float calibre) {
        this.hitNode   = hitNode;
        this.hitPoint  = hitPoint;
        this.hitNormal = hitNormal;
        this.calibre   = calibre;
    }
}
