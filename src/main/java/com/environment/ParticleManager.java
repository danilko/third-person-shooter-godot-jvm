package com.environment;

import com.util.ObjectPool;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.GPUParticles3D;
import godot.api.Node;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * World-level manager that holds one particle pool per surface type.
 *
 * Scene setup (Godot editor) — one template node per type, pool auto-filled:
 *   Add one child Node per surface type named after the SurfaceType constant.
 *   Inside each container put exactly ONE GPUParticles3D, fully configured.
 *   _ready() duplicates it to poolSizePerType and builds the pool automatically.
 *
 *   ParticleManager
 *     FLESH/
 *       Template (GPUParticles3D)  ← configure here; duplicated at runtime
 *     METAL/
 *       Template (GPUParticles3D)  ← configure here; duplicated at runtime
 *
 * Discovery: registers itself in group "particle_manager".
 * Fallback chain: requested type → DEFAULT → FLESH → silent no-op.
 */
@RegisterClass(className = "ParticleManager")
public class ParticleManager extends Node {

    /** Number of pooled instances created per surface type from the template. */
    @Export
    @RegisterProperty
    public int poolSizePerType = 16;

    private final Map<SurfaceType, ObjectPool<GPUParticles3D>> pools =
            new EnumMap<>(SurfaceType.class);

    @RegisterFunction
    @Override
    public void _ready() {
        addToGroup("particle_manager");

        for (SurfaceType type : SurfaceType.values()) {
            Node container = getNodeOrNull(type.name());
            if (container == null || container.getChildCount() == 0) continue;

            // First child is the configured template
            Node first = container.getChild(0);
            if (!(first instanceof GPUParticles3D template)) continue;

            List<GPUParticles3D> particles = new ArrayList<>();
            particles.add(template);

            // Duplicate the template to fill the pool; add duplicates to the container
            for (int i = 1; i < poolSizePerType; i++) {
                GPUParticles3D copy = (GPUParticles3D) template.duplicate(15);
                container.addChild(copy);
                particles.add(copy);
            }

            int[] idx = {0};
            pools.put(type, new ObjectPool<>(particles.size(),
                    () -> particles.get(idx[0]++),
                    p -> {}));  // fire-and-forget — no reset needed
        }
    }

    /**
     * Position and emit one burst at worldPosition for the given surface type.
     * Falls back to DEFAULT, then FLESH if no pool exists for the requested type.
     */
    public void spawn(SurfaceType type, Vector3 worldPosition) {
        ObjectPool<GPUParticles3D> pool = resolve(type);
        if (pool == null) return;
        GPUParticles3D p = pool.acquire();
        p.setGlobalPosition(worldPosition);
        p.setEmitting(true);
        pool.release(p);
    }

    private ObjectPool<GPUParticles3D> resolve(SurfaceType type) {
        ObjectPool<GPUParticles3D> pool = pools.get(type);
        if (pool != null) return pool;
        pool = pools.get(SurfaceType.DEFAULT);
        if (pool != null) return pool;
        return pools.get(SurfaceType.FLESH);
    }
}
