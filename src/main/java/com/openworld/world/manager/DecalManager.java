package com.openworld.world.manager;

import com.openworld.util.ObjectPool;
import com.openworld.world.SurfaceType;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Decal;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Texture2D;
import godot.core.Basis;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Transform3D;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * World-level manager for impact MARKS: the decal a hit leaves.
 *
 * <p><b>One mark per KIND of hit, never per surface</b> ({@link Mark}): a bullet leaves a hole, a blade or an axe a
 * slash, an explosion on the ground a scorch; a blunt blow leaves none (a car still dents: VehicleDamageModel). The
 * surface only TINTS the mark ({@link #tintFor}), the shape most games share across materials. Textures are
 * {@code assets/vfx/decals/impact_<mark>.png}, made once by {@code tools/vfx/make_impact_marks.py}.
 *
 * <p>Static geometry takes a POOLED decal in world space ({@link #poolSize}, each kept {@link #decalLifetime}, a
 * scorch {@link #scorchLifetime}; with every one in use the oldest moves to the new hit). Something that MOVES (a car)
 * takes its own decal parented to it, so the mark rides with it, at most {@link #MARKS_PER_BODY} per body (the oldest
 * goes), freed with the body. A character takes no mark (blood particles only).
 *
 * <p>Scene setup: exactly ONE Decal child, the template (its size is the bullet hole's), duplicated to the pool size.
 * Discovery: group "decal_manager".
 */
@Script(className = "DecalManager")
public class DecalManager extends Node {

    /** What made the mark; decides its texture and size. */
    public enum Mark { HOLE, SLASH, SCORCH }

    /** Total number of pooled decal instances (template + duplicates). */
    @Export
    public int poolSize = 64;

    /** Seconds a hole or slash stays before it is recycled. */
    @Export
    public float decalLifetime = 20.0f;

    /** Seconds a blast's scorch stays (CS 1.6 kept them for the round). */
    @Export
    public float scorchLifetime = 90.0f;

    /** Marks a moving body (a car) keeps; past it the oldest goes. */
    public static final int MARKS_PER_BODY = 14;

    private static class DecalEntry {
        final Decal decal;
        double age = 0.0;
        double life = 0.0;
        DecalEntry(Decal d) { this.decal = d; }
    }

    private final List<DecalEntry> allEntries = new ArrayList<>();
    private ObjectPool<DecalEntry> pool;
    private int activeCount = 0;
    private Vector3 baseSize = new Vector3(0.1, 0.1, 0.1);
    private final Map<Mark, Texture2D> textures = new EnumMap<>(Mark.class);
    private final Map<Mark, Integer> spawned = new EnumMap<>(Mark.class);
    private int attached;

    @Register
    @Override
    public void _ready() {
        addToGroup("decal_manager");
        Decal template = null;
        for (int i = 0; i < getChildCount(); i++) {
            if (getChild(i) instanceof Decal d) { template = d; break; }
        }
        if (template == null) return;
        baseSize = template.getSize();
        List<DecalEntry> entries = new ArrayList<>();
        template.setVisible(false);
        entries.add(new DecalEntry(template));
        for (int i = 1; i < poolSize; i++) {
            Decal copy = (Decal) template.duplicate(15);
            copy.setVisible(false);
            addChild(copy);
            entries.add(new DecalEntry(copy));
        }
        allEntries.addAll(entries);
        int[] idx = {0};
        pool = new ObjectPool<>(entries.size(), () -> entries.get(idx[0]++), e -> {
            e.decal.setVisible(false);
            e.age = 0.0;
        });
    }

    @Register
    @Override
    public void _process(double delta) {
        if (pool == null || activeCount == 0) return;
        for (DecalEntry entry : allEntries) {
            if (!entry.decal.isVisible()) continue;
            entry.age += delta;
            if (entry.age >= entry.life) {
                activeCount--;
                pool.release(entry);
            }
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /** A bullet hole on static geometry (the old entry point). */
    public void spawn(Vector3 hitPoint, Vector3 hitNormal) { spawn(hitPoint, hitNormal, Mark.HOLE, SurfaceType.STONE, null, 0f); }

    /**
     * A mark at {@code hitPoint}, facing out along {@code hitNormal}. {@code attachTo} non-null = a body that moves:
     * the mark is its own decal parented to it. {@code size} 0 = the mark's default (a hole the template's size,
     * a slash 0.6 m); a scorch passes its own diameter. Turned at random about the normal, sized +-15 %.
     */
    public void spawn(Vector3 hitPoint, Vector3 hitNormal, Mark mark, SurfaceType surface, Node3D attachTo, float size) {
        if (hitPoint == null || hitNormal == null || mark == null || surface == SurfaceType.FLESH) return;
        if (hitNormal.lengthSquared() < 1e-6) return;
        Decal d;
        if (attachTo != null) {
            if (!attachTo.isInsideTree()) return;
            d = new Decal();
            d.setName(new StringName("ImpactMark"));
            d.addToGroup(new StringName("impact_mark"));
            trimMarks(attachTo);
            attachTo.addChild(d);
            attached++;
        } else {
            if (pool == null) return;
            DecalEntry entry;
            if (pool.available() > 0) {
                entry = pool.acquire();
                activeCount++;
            } else {
                entry = null;   // all in use: the oldest (by share of its own lifetime) moves here
                for (DecalEntry e : allEntries)
                    if (e.decal.isVisible() && (entry == null || e.age / e.life > entry.age / entry.life)) entry = e;
                if (entry == null) return;
            }
            entry.age = 0.0;
            entry.life = mark == Mark.SCORCH ? scorchLifetime : decalLifetime;
            d = entry.decal;
        }
        Texture2D tex = textureFor(mark);
        if (tex != null) d.setTexture(Decal.DecalTexture.TEXTURE_ALBEDO, tex);
        d.setModulate(tintFor(surface));
        d.setAlbedoMix(1.0f);
        Vector3 n = hitNormal.normalized();
        double k = 0.85 + 0.3 * Math.random();
        double w = switch (mark) {
            case HOLE -> baseSize.getX();
            case SLASH -> 0.6;
            case SCORCH -> size > 0f ? size : 3.0;
        } * (mark == Mark.SCORCH ? 1.0 : k);
        if (mark != Mark.SCORCH && size > 0f) w = size * k;
        // a scorch projects through a deep box so it lands on uneven ground; a hole or slash only a few cm deep
        double depth = mark == Mark.SCORCH ? Math.max(1.0, w * 0.4) : 0.1;
        d.setSize(new Vector3(w, depth, w));
        Vector3 at = hitPoint.plus(n.times(mark == Mark.SCORCH ? 0.1 : 0.005));
        orient(d, n, at);
        d.rotateObjectLocal(Vector3.Companion.getUP(), (float) (Math.random() * Math.PI * 2));
        d.setVisible(true);
        spawned.merge(mark, 1, Integer::sum);
    }

    /** Marks of {@code mark} made so far (probe readout, by name: "HOLE", "SLASH", "SCORCH"). */
    @Register public int marksSpawnedNow(String mark) {
        try { return spawned.getOrDefault(Mark.valueOf(mark), 0); } catch (IllegalArgumentException e) { return -1; }
    }

    /** A mark by name on static geometry (probe / picture hook: shot_impacts.gd). */
    @Register public void markNow(Vector3 at, Vector3 normal, String mark, String surface, float size) {
        spawn(at, normal, Mark.valueOf(mark), SurfaceType.valueOf(surface), null, size);
    }

    /** Holes made so far (kept for older probes). */
    @Register public int decalsSpawnedNow() { return spawned.getOrDefault(Mark.HOLE, 0); }

    /** Marks parented to moving bodies so far (probe readout). */
    @Register public int marksAttachedNow() { return attached; }

    /** The surface's tint over the shared mark: stone/concrete neutral, metal a cool grey, wood a warm brown. */
    public static Color tintFor(SurfaceType surface) {
        return switch (surface == null ? SurfaceType.DEFAULT : surface) {
            case METAL -> new Color(0.75, 0.78, 0.85, 0.9);
            case WOOD -> new Color(0.95, 0.75, 0.55, 1.0);
            case GLASS -> new Color(0.9, 0.95, 1.0, 0.7);
            default -> new Color(1, 1, 1, 1);
        };
    }

    private Texture2D textureFor(Mark mark) {
        return textures.computeIfAbsent(mark, m -> {
            String path = "res://assets/vfx/decals/impact_" + m.name().toLowerCase() + ".png";
            return godot.api.ResourceLoader.INSTANCE.exists(path, "")
                    && godot.global.GD.load(path) instanceof Texture2D t ? t : null;
        });
    }

    /** Keep a body's own marks under MARKS_PER_BODY: free the oldest (children are in the order they were added). */
    private static void trimMarks(Node3D body) {
        List<Node> marks = new ArrayList<>();
        for (int i = 0; i < body.getChildCount(); i++) {
            Node c = body.getChild(i);
            if (c instanceof Decal && c.isInGroup(new StringName("impact_mark")) && !c.isQueuedForDeletion()) marks.add(c);
        }
        for (int i = 0; i <= marks.size() - MARKS_PER_BODY; i++) marks.get(i).queueFree();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /** Local +Y along the surface normal (a Decal projects along its -Y), placed at {@code at} in world space. */
    private static void orient(Decal decal, Vector3 normal, Vector3 at) {
        Vector3 ref = (Math.abs(normal.getY()) < 0.9f) ? Vector3.Companion.getUP() : Vector3.Companion.getFORWARD();
        Vector3 right = ref.cross(normal).normalized();
        Vector3 fwd = right.cross(normal);   // right-handed: a mirrored basis is culled by some renderers
        decal.setGlobalTransform(new Transform3D(new Basis(right, normal, fwd), at));
    }
}
