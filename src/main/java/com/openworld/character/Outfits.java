package com.openworld.character;

import godot.api.BaseMaterial3D;
import godot.api.FileAccess;
import godot.api.Material;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.ResourceLoader;
import godot.core.Color;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Uniforms (PLAN.md 1g c): {@code character/outfits.json} names, per outfit, what replaces each CLOTH surface of a
 * body -- a flat placeholder colour or an artist's material. The forces that wear them are data
 * ({@code crimes.json dispatch.bodies}, {@code gangs.json gangs.<id>.bodies}). Every VRoid body names its cloth
 * materials {@code <...>_<Part>_<nn>_CLOTH}, so the part is read off the material's name and nothing is authored per
 * body. One material per (source material, outfit), cached, so a squad of twelve shares a handful.
 */
public final class Outfits {

    public static final String TABLE = "res://src/main/resources/com/openworld/character/outfits.json";

    private static final Map<String, Material> CACHE = new HashMap<>();

    private Outfits() {}

    private static Map<String, Map<String, Object>> table() {
        return com.openworld.game.data.Tables.OUTFITS.get();
    }

    public static boolean has(String outfit) { return outfit != null && table().containsKey(outfit); }

    /**
     * Dress every cloth surface under {@code root} (a character's visuals) in {@code outfit}. Returns how many surfaces
     * changed (0 for an unknown outfit or a body with no cloth).
     */
    public static int apply(Node root, String outfit) {
        if (root == null || outfit == null || outfit.isEmpty()) return 0;
        Map<String, Object> o = table().get(outfit);
        if (o == null) return 0;
        int changed = 0;
        ArrayDeque<Node> stack = new ArrayDeque<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            Node n = stack.pop();
            for (Node c : n.getChildren()) stack.push(c);
            if (!(n instanceof MeshInstance3D mi) || mi.getMesh() == null) continue;
            for (int i = 0; i < mi.getMesh().getSurfaceCount(); i++) {
                Material src = mi.getMesh().surfaceGetMaterial(i);
                if (src == null) continue;
                String part = OutfitTable.partOf(src.getName());
                Material m = dressed(src, outfit, OutfitTable.valueFor(o, part));
                if (m != null) { mi.setSurfaceOverrideMaterial(i, m); changed++; }
            }
        }
        return changed;
    }

    private static Material dressed(Material src, String outfit, Object v) {
        if (v == null) return null;
        String key = src.getInstanceId() + "|" + outfit + "|" + v;
        Material hit = CACHE.get(key);
        if (hit != null) return hit;
        Material m = null;
        if (v instanceof String path) {
            if (ResourceLoader.INSTANCE.exists(path, "") && ResourceLoader.load(path) instanceof Material mat) m = mat;
        } else if (v instanceof List<?> rgb && rgb.size() >= 3 && src instanceof BaseMaterial3D b) {
            BaseMaterial3D copy = (BaseMaterial3D) b.duplicate();
            copy.setTexture(BaseMaterial3D.TextureParam.ALBEDO, null);
            copy.setAlbedo(new Color(f(rgb.get(0)), f(rgb.get(1)), f(rgb.get(2)), 1.0));
            copy.setName(src.getName() + "_" + outfit);
            m = copy;
        }
        if (m != null) CACHE.put(key, m);
        return m;
    }

    private static double f(Object o) { return o instanceof Number n ? n.doubleValue() : 0.5; }

    /** Static state holds Godot resources: cleared at shutdown (GameManager._exitTree, the IconRegistry rule). */
    public static void clear() { CACHE.clear(); }
}
