package com.openworld.world;

import godot.api.Node;
import godot.api.Node3D;
import godot.api.SceneTree;
import godot.api.Time;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/**
 * Every level-design marker in the live world, by kind (PLAN.md 2.0). A building's {@code MARK_<kind>_<n>} Empties
 * (kits/interiors) are baked into its scene as nodes in the group {@link #GROUP} carrying their props as metadata
 * ({@code kind}, {@code team}, {@code weapon}, ...; -Z is the way a marker faces) -- "a weapon spot in an armoury, a
 * spawn point, a cover point". Nothing spawns from them by itself; whoever needs them used to walk a building's
 * children and read metadata by hand. This is the one reader: a mission, an encounter, the AI's cover search ask
 * {@link #near} / {@link #ofKind} / {@link #under} and get typed {@link Marker}s.
 *
 * <p>Buildings stream in and out, so the index is rebuilt from the group when the tree's node count has changed (or
 * after {@link #MAX_AGE_MSEC}); a marker whose node has been freed is never returned. Queries are for events (a
 * mission starting, a wave spawning), not for every frame of every AI.
 */
public final class MarkerRegistry {
    private MarkerRegistry() {}

    public static final String GROUP = "mission_marker";
    private static final StringName GROUP_NAME = new StringName(GROUP);
    private static final StringName KIND = new StringName("kind");
    /** A tree whose node count did not change is still re-read this often (a marker swapped for another). */
    public static final long MAX_AGE_MSEC = 1000;

    /** One marker: its node, its kind, where it is and which way it faces (world space, read when asked). */
    public static final class Marker {
        public final Node3D node;
        public final String kind;

        Marker(Node3D node, String kind) {
            this.node = node;
            this.kind = kind;
        }

        public boolean valid() { return GD.isInstanceValid(node) && node.isInsideTree(); }

        public Vector3 position() { return node.getGlobalPosition(); }

        /** The way it faces: its -Z, level. */
        public Vector3 facing() {
            Vector3 z = node.getGlobalBasis().getZ();
            Vector3 f = new Vector3(-z.getX(), 0, -z.getZ());
            return f.length() < 1e-6 ? new Vector3(0, 0, -1) : f.normalized();
        }

        /** A custom property of the marker ({@code team}, {@code weapon}, ...), {@code def} when it has none. */
        public String prop(String key, String def) {
            StringName k = new StringName(key);
            if (!node.hasMeta(k)) return def;
            Object v = node.getMeta(k);
            return v == null ? def : String.valueOf(v);
        }

        public double num(String key, double def) {
            StringName k = new StringName(key);
            return node.hasMeta(k) && node.getMeta(k) instanceof Number n ? n.doubleValue() : def;
        }

        public String team() { return prop("team", ""); }
    }

    private static final Map<String, List<Marker>> BY_KIND = new HashMap<>();
    private static int total;
    private static long builtForTree = -1;
    private static int builtAtCount = -1;
    private static long builtAtMsec;
    private static int rebuilds;

    private static void refresh(SceneTree tree) {
        long now = Time.getTicksMsec();
        int count = tree.getNodeCount();
        if (tree.getInstanceId() == builtForTree && count == builtAtCount && now - builtAtMsec < MAX_AGE_MSEC) return;
        builtForTree = tree.getInstanceId();
        builtAtCount = count;
        builtAtMsec = now;
        rebuilds++;
        BY_KIND.clear();
        total = 0;
        for (Node n : tree.getNodesInGroup(GROUP_NAME)) {
            if (!(n instanceof Node3D n3)) continue;
            Marker m = new Marker(n3, kindOf(n3));
            BY_KIND.computeIfAbsent(m.kind, k -> new ArrayList<>()).add(m);
            total++;
        }
    }

    /** A marker's kind: its {@code kind} property, else its name {@code MARK_<kind>_<n>}. */
    public static String kindOf(Node3D n) {
        if (n.hasMeta(KIND)) {
            String k = String.valueOf(n.getMeta(KIND));
            if (!k.isEmpty()) return k;
        }
        return kindFromName(n.getName().toString());
    }

    /** {@code MARK_cover_03} -> {@code cover}; a name that is not a marker's reads as "". */
    public static String kindFromName(String name) {
        if (name == null || !name.startsWith("MARK_")) return "";
        String k = name.substring("MARK_".length());
        int cut = k.lastIndexOf('_');
        if (cut > 0 && k.substring(cut + 1).chars().allMatch(java.lang.Character::isDigit)) k = k.substring(0, cut);
        return k;
    }

    private static SceneTree treeOf(Node ctx) { return ctx != null && ctx.isInsideTree() ? ctx.getTree() : null; }

    /** Every live marker of {@code kind} (null / "" = every kind). {@code ctx}: any node in the tree. */
    public static List<Marker> ofKind(Node ctx, String kind) {
        List<Marker> out = new ArrayList<>();
        SceneTree tree = treeOf(ctx);
        if (tree == null) return out;
        refresh(tree);
        if (kind == null || kind.isEmpty()) {
            for (List<Marker> l : BY_KIND.values()) for (Marker m : l) if (m.valid()) out.add(m);
        } else {
            for (Marker m : BY_KIND.getOrDefault(kind, List.of())) if (m.valid()) out.add(m);
        }
        return out;
    }

    /** The markers of {@code kind} within {@code radius} of {@code at}, nearest first. */
    public static List<Marker> near(Node ctx, String kind, Vector3 at, double radius) {
        List<Marker> out = new ArrayList<>();
        for (Marker m : ofKind(ctx, kind)) if (m.position().distanceTo(at) <= radius) out.add(m);
        out.sort(Comparator.comparingDouble(m -> m.position().distanceTo(at)));
        return out;
    }

    /** The nearest marker of {@code kind} within {@code radius}, or null. */
    public static Marker nearest(Node ctx, String kind, Vector3 at, double radius) {
        List<Marker> l = near(ctx, kind, at, radius);
        return l.isEmpty() ? null : l.get(0);
    }

    /**
     * The markers of ONE building: those under {@code root} (the building's scene root, or its {@code Markers} node),
     * in scene order. No tree-wide index is needed, so it also works on a scene that is not in the tree yet.
     */
    public static List<Marker> under(Node root, String kind) {
        List<Marker> out = new ArrayList<>();
        if (root == null || !GD.isInstanceValid(root)) return out;
        java.util.ArrayDeque<Node> stack = new java.util.ArrayDeque<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            Node n = stack.pop();
            List<Node> kids = new ArrayList<>(n.getChildren());
            for (int i = kids.size() - 1; i >= 0; i--) stack.push(kids.get(i));
            if (n == root || !(n instanceof Node3D n3) || !n.isInGroup(GROUP_NAME)) continue;
            String k = kindOf(n3);
            if (kind == null || kind.isEmpty() || kind.equals(k)) out.add(new Marker(n3, k));
        }
        return out;
    }

    /** The kinds present now, sorted (a probe's readout, a designer's console listing). */
    public static List<String> kinds(Node ctx) {
        SceneTree tree = treeOf(ctx);
        if (tree == null) return List.of();
        refresh(tree);
        return new ArrayList<>(new TreeSet<>(BY_KIND.keySet()));
    }

    public static int count(Node ctx, String kind) { return ofKind(ctx, kind).size(); }

    public static int rebuildCount() { return rebuilds; }

    /** Drop the index (engine teardown: it holds nodes). */
    public static void clear() {
        BY_KIND.clear();
        total = 0;
        builtForTree = -1;
        builtAtCount = -1;
    }
}
