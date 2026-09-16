package com.openworld.util;

import godot.api.CollisionObject3D;
import godot.api.RayCast3D;
import godot.core.RID;
import godot.core.VariantArray;
import godot.global.GD;

import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * The ONE place an aim ray's self-exceptions are added and removed, so a stateless space query can apply
 * exactly the same exclusions (PLAN.md 2.8 item 6). {@code RayCast3D} offers {@code add_exception} but no
 * way to READ the set back, so every trace used to borrow the scene node itself — move it, force an update,
 * put it back — which leaves the ray (and the {@code AimTarget} hanging off it) displaced if anything in
 * between throws. Recording the RIDs here lets {@code WeaponItem.trace} run an {@code intersect_ray} with
 * the ray's mask and these RIDs and never touch the node.
 *
 * <p>JVM-static, keyed by the ray's instance id; entries of freed rays are pruned on every add, and
 * {@link #clear()} runs from {@code GameManager._exitTree} (the IconRegistry leak rule).
 */
public final class RayExclusions {

    private RayExclusions() {}

    private static final Map<Long, Set<RID>> BY_RAY = new HashMap<>();
    /** The ray object per id, only so freed rays can be pruned (GD has no instance-from-id here). */
    private static final Map<Long, RayCast3D> RAYS = new HashMap<>();

    public static void add(RayCast3D ray, CollisionObject3D co) {
        if (ray == null || co == null) return;
        ray.addException(co);
        pruneFreed();
        RAYS.put(ray.getInstanceId(), ray);
        BY_RAY.computeIfAbsent(ray.getInstanceId(), k -> new LinkedHashSet<>()).add(co.getRid());
    }

    public static void remove(RayCast3D ray, CollisionObject3D co) {
        if (ray == null || co == null) return;
        ray.removeException(co);
        Set<RID> set = BY_RAY.get(ray.getInstanceId());
        if (set != null) set.remove(co.getRid());
    }

    /** The RIDs excluded from {@code ray}, as an exclude array for a query (a fresh copy). */
    public static VariantArray<RID> of(RayCast3D ray) {
        VariantArray<RID> out = new VariantArray<>(RID.class);
        Set<RID> set = ray != null ? BY_RAY.get(ray.getInstanceId()) : null;
        if (set != null) for (RID r : set) out.add(r);
        return out;
    }

    /** How many RIDs are recorded for {@code ray} — probes read it. */
    public static int count(RayCast3D ray) {
        Set<RID> set = ray != null ? BY_RAY.get(ray.getInstanceId()) : null;
        return set != null ? set.size() : 0;
    }

    public static void clear() { BY_RAY.clear(); RAYS.clear(); }

    private static void pruneFreed() {
        if (BY_RAY.size() < 64) return;
        RAYS.entrySet().removeIf(e -> {
            boolean dead = !GD.isInstanceValid(e.getValue());
            if (dead) BY_RAY.remove(e.getKey());
            return dead;
        });
    }
}
