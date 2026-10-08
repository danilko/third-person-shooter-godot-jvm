package com.openworld.world.manager;

import com.openworld.util.ObjectPool;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Decal;
import godot.api.Node;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;
import com.openworld.world.SurfaceType;

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
@Script(className = "DecalManager")
public class DecalManager extends Node {

    /** Total number of pooled decal instances (template + duplicates). */
    @Export
    public int poolSize = 16;

    /** Seconds a bullet hole remains visible before being recycled. */
    @Export
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
    private int activeCount = 0;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Register
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
        baseSize = template.getSize();
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
    @Register
    @Override
    public void _process(double delta) {
        if (pool == null || activeCount == 0) return;
        for (DecalEntry entry : allEntries) {
            if (!entry.decal.isVisible()) continue;
            entry.age += delta;
            if (entry.age >= decalLifetime) {
                activeCount--;
                pool.release(entry);
            }
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Spawn a bullet-hole decal at the impact point, oriented to the surface.
     * No-op if the pool is exhausted.
     */
    public void spawn(Vector3 hitPoint, Vector3 hitNormal) { spawn(hitPoint, hitNormal, SurfaceType.STONE); }

    /**
     * A bullet hole for {@code surface}: its own texture ({@code assets/vfx/decals/bullet_hole_<surface>.png}, made by
     * {@code tools/vfx/make_bullet_holes.py}; DEFAULT = stone), turned at random about the normal and sized +-15 %.
     * FLESH makes none (a hole on a moving body would float). With every decal in use the OLDEST is moved here (CS: a
     * fresh hole always shows).
     */
    public void spawn(Vector3 hitPoint, Vector3 hitNormal, SurfaceType surface) {
        if (pool == null || hitPoint == null || hitNormal == null || surface == SurfaceType.FLESH) return;
        DecalEntry entry;
        if (pool.available() > 0) {
            entry = pool.acquire();
            activeCount++;
        } else {
            entry = null;
            for (DecalEntry e : allEntries) if (e.decal.isVisible() && (entry == null || e.age > entry.age)) entry = e;
            if (entry == null) return;
        }
        entry.age = 0.0;
        godot.api.Texture2D tex = textureFor(surface);
        if (tex != null) entry.decal.setTexture(Decal.DecalTexture.TEXTURE_ALBEDO, tex);
        Vector3 n = hitNormal.normalized();
        entry.decal.setGlobalPosition(hitPoint.plus(n.times(0.005f)));
        orientToSurface(entry.decal, n);
        entry.decal.rotateObjectLocal(Vector3.Companion.getUP(), (float) (Math.random() * Math.PI * 2));
        double k = 0.85 + 0.3 * Math.random();
        entry.decal.setSize(baseSize.times(new Vector3(k, 1.0, k)));
        entry.decal.setVisible(true);
        spawned++;
    }

    /** Holes made so far (probe readout). */
    private int spawned;
    @Register public int decalsSpawnedNow() { return spawned; }

    private Vector3 baseSize = new Vector3(0.1, 0.1, 0.1);
    private final java.util.Map<SurfaceType, godot.api.Texture2D> textures = new java.util.EnumMap<>(SurfaceType.class);

    private godot.api.Texture2D textureFor(SurfaceType surface) {
        SurfaceType key = switch (surface) {
            case METAL, WOOD, GLASS -> surface;
            default -> SurfaceType.STONE;
        };
        return textures.computeIfAbsent(key, k -> {
            String path = "res://assets/vfx/decals/bullet_hole_" + k.name().toLowerCase() + ".png";
            return godot.api.ResourceLoader.INSTANCE.exists(path, "")
                    && godot.global.GD.load(path) instanceof godot.api.Texture2D t ? t : null;
        });
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
