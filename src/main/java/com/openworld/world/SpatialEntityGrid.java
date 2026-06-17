package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.core.StringName;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Uniform spatial hash over the XZ plane — registered as an AutoLoad singleton named
 * "SpatialEntityGrid" (PLAN.md Part D / D1).
 *
 * <p>Replaces the O(characterCount) {@code getTree().getNodesInGroup("characters")} scan that
 * {@code AICharacter.discoverTarget()} ran every {@code TARGET_SCAN_INTERVAL}: the world is diced
 * into {@code cellSize × cellSize} buckets and a target search only visits the handful of cells
 * overlapping the AI's detection circle — O(k) in the local neighbourhood, not O(n) over the whole
 * scene. With hundreds of AIs spread across an open world this is the difference between every AI
 * touching every other AI each scan and each AI touching only its neighbours.
 *
 * <p>Both on-foot {@code Character} and {@code Vehicle} bodies register here (they share the
 * "characters" group), so the vehicle-occupant branch of {@code discoverTarget()} benefits too.
 *
 * <p><b>Lifecycle:</b> bodies {@link #register} in {@code _ready()}, {@link #move} on a throttled
 * cadence from {@code _physicsProcess}, and {@link #unregister} in {@code _exitTree()}. The grid is
 * reached through the JVM-static {@link #get()} (set in {@code _ready()}); that static is cleared in
 * {@link #_exitTree()} along with the bucket maps so no Godot {@code Node} leaks past engine exit
 * (same discipline as {@code IconRegistry.clear()} — see CLAUDE.md "Known Quirks"). When the grid is
 * absent (test scenes without the AutoLoad) callers fall back to the group scan, so it is a pure
 * drop-in accelerator.
 */
@RegisterClass(className = "SpatialEntityGrid")
public class SpatialEntityGrid extends Node {

    private static SpatialEntityGrid instance;

    /** The live grid, or null if the AutoLoad isn't present (callers must fall back). */
    public static SpatialEntityGrid get() { return instance; }

    /** Cell edge length in metres. Exported so it can be tuned per scene without code changes. */
    @Export @RegisterProperty public float cellSize = 50.0f;

    /** cell key → the nodes currently bucketed in that cell. */
    private final Map<Long, List<Node>> cells = new HashMap<>();
    /** node → its current cell key, so {@link #move} only re-buckets on an actual cell change. */
    private final Map<Node, Long> nodeCell = new HashMap<>();

    @RegisterFunction
    @Override
    public void _ready() {
        instance = this;
        addToGroup(new StringName("spatial_grid"), false);
    }

    @RegisterFunction
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        cells.clear();
        nodeCell.clear();
    }

    /** Packs the (floored) cell coordinates of a world position into a single long key. */
    private long keyFor(double x, double z) {
        long cx = (long) Math.floor(x / cellSize);
        long cz = (long) Math.floor(z / cellSize);
        return (cx << 32) | (cz & 0xFFFFFFFFL);
    }

    /** Add a node to (or, if already present, re-bucket it into) the cell containing {@code pos}. */
    public void register(Node node, Vector3 pos) {
        if (node == null) return;
        long key = keyFor(pos.getX(), pos.getZ());
        Long prev = nodeCell.get(node);
        if (prev != null) {
            if (prev == key) return;            // unchanged cell — nothing to do
            removeFromCell(prev, node);
        }
        cells.computeIfAbsent(key, k -> new ArrayList<>()).add(node);
        nodeCell.put(node, key);
    }

    /** Update a node's cell after it moves. No-op (a map lookup) while it stays in the same cell. */
    public void move(Node node, Vector3 pos) {
        register(node, pos);
    }

    /** Remove a node entirely (death / despawn / leaving the tree). */
    public void unregister(Node node) {
        if (node == null) return;
        Long prev = nodeCell.remove(node);
        if (prev != null) removeFromCell(prev, node);
    }

    private void removeFromCell(long key, Node node) {
        List<Node> bucket = cells.get(key);
        if (bucket == null) return;
        bucket.remove(node);
        if (bucket.isEmpty()) cells.remove(key);
    }

    /**
     * Collect every registered node whose cell overlaps the {@code radius} circle around
     * {@code center} into {@code out} (cleared first). This is a cell-level (not exact-distance)
     * filter — callers still distance-test individual results — so it returns a small superset of
     * the true neighbours. Iterates {@code (2·radius/cellSize + 1)²} cells, independent of the
     * total entity count.
     */
    public void queryRadius(Vector3 center, float radius, List<Node> out) {
        out.clear();
        long minCx = (long) Math.floor((center.getX() - radius) / cellSize);
        long maxCx = (long) Math.floor((center.getX() + radius) / cellSize);
        long minCz = (long) Math.floor((center.getZ() - radius) / cellSize);
        long maxCz = (long) Math.floor((center.getZ() + radius) / cellSize);
        for (long cx = minCx; cx <= maxCx; cx++) {
            for (long cz = minCz; cz <= maxCz; cz++) {
                List<Node> bucket = cells.get((cx << 32) | (cz & 0xFFFFFFFFL));
                if (bucket != null) out.addAll(bucket);
            }
        }
    }
}
