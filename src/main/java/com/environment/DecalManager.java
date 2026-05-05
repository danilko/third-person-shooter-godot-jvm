package com.environment;

import com.util.ObjectPool;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Decal;
import godot.api.Node;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * World-level manager for bullet-hole decals.
 *
 * Scene setup (Godot editor) — one template node, pool auto-filled:
 *   Add exactly ONE Decal as a direct child. Configure its texture and size.
 *   _ready() duplicates it to poolSize and builds the pool automatically.
 *
 *   DecalManager
 *     Template (Decal)  ← set texture + size here; duplicated at runtime
 *
 * Pool strategy:
 *   Unlike ParticleManager (fire-and-forget), decals are HELD by the pool for
 *   decalLifetime seconds, then released. _process() ages each active decal and
 *   returns it to the pool when it expires. If the pool is exhausted the spawn
 *   is silently skipped — oldest holes will naturally recycle soon.
 *
 * Discovery: registers itself in group "decal_manager".
 */
@RegisterClass(className = "DecalManager")
public class DecalManager extends Node {

    /** Total number of pooled decal instances (template + duplicates). */
    @Export
    @RegisterProperty
    public int poolSize = 16;

    /** Seconds a bullet hole remains visible before being recycled. */
    @Export
    @RegisterProperty
    public float decalLifetime = 8.0f;

    // ── Internal per-decal state ──────────────────────────────────────────────

    private static class DecalEntry {
        final Decal decal;
        double age = 0.0;

        DecalEntry(Decal d) { this.decal = d; }
    }

    /** All entries (pooled + active) — iterated each frame in _process. */
    private final List<DecalEntry> allEntries = new ArrayList<>();
    private ObjectPool<DecalEntry> pool;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        addToGroup("decal_manager");

        // Find the first Decal child — it is the configured template
        Decal template = null;
        for (int i = 0; i < getChildCount(); i++) {
            if (getChild(i) instanceof Decal d) { template = d; break; }
        }
        if (template == null) return;   // no template configured — pool stays empty

        List<DecalEntry> entries = new ArrayList<>();

        template.setVisible(false);
        entries.add(new DecalEntry(template));

        // Duplicate the template to fill the pool
        for (int i = 1; i < poolSize; i++) {
            Decal copy = (Decal) template.duplicate(15);
            copy.setVisible(false);
            addChild(copy);
            entries.add(new DecalEntry(copy));
        }

        allEntries.addAll(entries);

        int[] idx = {0};
        pool = new ObjectPool<>(entries.size(),
                () -> entries.get(idx[0]++),
                e -> {
                    e.decal.setVisible(false);
                    e.age = 0.0;
                });
    }

    /** Age every active decal; release back to pool when lifetime expires. */
    @RegisterFunction
    @Override
    public void _process(double delta) {
        if (pool == null) return;
        for (DecalEntry entry : allEntries) {
            if (!entry.decal.isVisible()) continue;
            entry.age += delta;
            if (entry.age >= decalLifetime) {
                pool.release(entry);
            }
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Spawn a bullet-hole decal at the impact point, oriented to the surface.
     * No-op if the pool is exhausted.
     */
    public void spawn(Vector3 hitPoint, Vector3 hitNormal) {
        if (pool == null || pool.available() == 0) return;

        DecalEntry entry = pool.acquire();
        entry.age = 0.0;

        entry.decal.setGlobalPosition(hitPoint.plus(hitNormal.normalized().times(0.005f)));
        orientToSurface(entry.decal, hitNormal.normalized());
        entry.decal.setVisible(true);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Orient the decal so its local +Y axis aligns with the surface normal.
     * Godot's Decal projects along local -Y, so +Y = outward normal shoots the
     * projection into the surface correctly.
     */
    private void orientToSurface(Decal decal, Vector3 normal) {
        Vector3 ref   = (Math.abs(normal.getY()) < 0.9f)
                        ? Vector3.Companion.getUP()
                        : Vector3.Companion.getFORWARD();
        Vector3 right = ref.cross(normal).normalized();
        Vector3 fwd   = normal.cross(right);
        Basis b = new Basis(right, normal, fwd);
        decal.setGlobalTransform(new Transform3D(b, decal.getGlobalPosition()));
    }
}
