package com.openworld.ai.light;

import com.openworld.util.MiniJson;
import godot.api.FileAccess;
import godot.api.GeometryInstance3D;
import godot.api.Image;
import godot.api.ImageTexture;
import godot.api.Mesh;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node3D;
import godot.api.ResourceLoader;
import godot.api.Shader;
import godot.api.ShaderMaterial;
import godot.api.Texture2D;
import godot.core.PackedByteArray;
import godot.core.PackedFloat32Array;
import godot.core.PackedVector3Array;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * What a light combatant LOOKS like (PLAN.md 2.3): the baked bodies ({@code <body>_vat.json}, the crowd's bake with
 * the combat clips, cloth parts and the right hand per frame) and the baked weapons ({@code light_weapons.json}),
 * and the draw layers -- one {@link MultiMesh} per (body, outfit) and one per (body, weapon). Loaded once; the layers
 * belong to the node that asks for them.
 */
final class LightLooks {

    static final String SHADER = "res://assets/characters/crowd/ped_vat.gdshader";
    static final String WEAPON_SHADER = "res://assets/characters/crowd/light_weapon.gdshader";
    static final String WEAPONS = "res://assets/characters/crowd/light_weapons.json";
    static final String GAITS = "res://src/main/resources/com/openworld/character/anim/character_gaits.json";
    /** The cloth parts in the bake's order (bake_ped_vat.gd PARTS); 0 = skin / hair. */
    static final String[] PARTS = { "", "Tops", "Bottoms", "Onepice", "Accessory", "Shoes", "cloth" };

    /** One clip on a body's texture: its first row, frame count, frames a second. */
    record Clip(int row, int frames, double fps) {
        double seconds() { return frames / Math.max(fps, 1e-3); }
    }

    static final class Body {
        String name;
        double height = 1.62;
        double weight = 1.0;
        Mesh mesh;
        Texture2D positions, atlas, hands;
        double scissor = 0.5;
        final Map<String, Clip> clips = new HashMap<>();
        final Map<String, Transform3D> sockets = new HashMap<>();
        Clip clip(String key, String fallback) {
            Clip c = clips.get(key);
            return c != null ? c : clips.get(fallback);
        }
    }

    record WeaponLook(String id, Mesh mesh, String socket, boolean ranged, String archetype) { }

    private static Map<String, Body> bodies;
    private static Map<String, WeaponLook> weapons;

    static synchronized Map<String, Body> bodies() {
        if (bodies != null) return bodies;
        bodies = new LinkedHashMap<>();
        Object gaits = MiniJson.parse(FileAccess.getFileAsString(GAITS));
        if (!(gaits instanceof Map<?, ?> g) || !(g.get("bodies") instanceof Map<?, ?> names)) return bodies;
        Map<?, ?> weights = g.get("crowd_weights") instanceof Map<?, ?> w ? w : Map.of();
        List<String> sorted = new ArrayList<>();
        for (Object k : names.keySet()) sorted.add(String.valueOf(k));
        java.util.Collections.sort(sorted);
        for (String name : sorted) {
            String meta = "res://assets/characters/" + name + "/" + name + "_vat.json";
            if (!FileAccess.fileExists(meta) || !(MiniJson.parse(FileAccess.getFileAsString(meta)) instanceof Map<?, ?> m)) continue;
            Body b = new Body();
            b.name = name;
            if (weights.get(name) instanceof Number n) b.weight = Math.max(0.0, n.doubleValue());
            String bodyJson = "res://assets/characters/" + name + "/" + name + ".body.json";
            if (FileAccess.fileExists(bodyJson) && MiniJson.parse(FileAccess.getFileAsString(bodyJson)) instanceof Map<?, ?> bj
                    && bj.get("crown_m") instanceof Number cm && cm.doubleValue() > 0.5) b.height = cm.doubleValue() + 0.04;
            b.mesh = load(m.get("mesh")) instanceof Mesh me ? me : null;
            b.positions = load(m.get("positions")) instanceof Texture2D t ? t : null;
            b.atlas = load(m.get("atlas")) instanceof Texture2D t ? t : null;
            if (m.get("alpha_scissor") instanceof Number a) b.scissor = a.doubleValue();
            int rows = m.get("rows") instanceof Number r ? r.intValue() : 0;
            float[] hand = new float[Math.max(1, rows) * 12];
            for (int i = 0; i < Math.max(1, rows); i++) { hand[i * 12] = 1; hand[i * 12 + 5] = 1; hand[i * 12 + 10] = 1; }
            if (m.get("clips") instanceof Map<?, ?> clips) {
                for (Map.Entry<?, ?> e : clips.entrySet()) {
                    if (!(e.getValue() instanceof Map<?, ?> c)) continue;
                    int row = ((Number) c.get("row")).intValue(), frames = ((Number) c.get("frames")).intValue();
                    b.clips.put(String.valueOf(e.getKey()), new Clip(row, frames, ((Number) c.get("fps")).doubleValue()));
                    if (c.get("hand") instanceof List<?> hs) {
                        for (int f = 0; f < hs.size() && row + f < rows; f++) {
                            if (!(hs.get(f) instanceof List<?> t) || t.size() < 12) continue;
                            // texel k of row: (basis column k, origin k)
                            for (int k = 0; k < 3; k++) {
                                for (int j = 0; j < 3; j++) hand[(row + f) * 12 + k * 4 + j] = ((Number) t.get(k * 3 + j)).floatValue();
                                hand[(row + f) * 12 + k * 4 + 3] = ((Number) t.get(9 + k)).floatValue();
                            }
                        }
                    }
                }
            }
            if (m.get("sockets") instanceof Map<?, ?> ss) {
                for (Map.Entry<?, ?> e : ss.entrySet()) if (e.getValue() instanceof List<?> t && t.size() >= 12) b.sockets.put(String.valueOf(e.getKey()), t12(t));
            }
            b.hands = handTexture(hand, Math.max(1, rows));
            if (b.mesh == null || b.positions == null || b.atlas == null || !b.clips.containsKey("walk")) {
                GD.pushError("LightLooks: " + name + "'s VAT bake is incomplete -- run tools/godot/bake_ped_vat.gd");
                continue;
            }
            bodies.put(name, b);
        }
        return bodies;
    }

    static synchronized Map<String, WeaponLook> weapons() {
        if (weapons != null) return weapons;
        weapons = new HashMap<>();
        if (!FileAccess.fileExists(WEAPONS) || !(MiniJson.parse(FileAccess.getFileAsString(WEAPONS)) instanceof Map<?, ?> m)
                || !(m.get("weapons") instanceof Map<?, ?> ws)) return weapons;
        for (Map.Entry<?, ?> e : ws.entrySet()) {
            if (!(e.getValue() instanceof Map<?, ?> w) || !(load(w.get("mesh")) instanceof Mesh mesh)) continue;
            String id = String.valueOf(e.getKey());
            weapons.put(id, new WeaponLook(id, mesh, String.valueOf(w.get("socket")), Boolean.TRUE.equals(w.get("ranged")),
                    String.valueOf(w.get("archetype"))));
        }
        return weapons;
    }

    /** A body by name, else the crowd-weighted roll {@code r} in [0, 1) over every baked body; null if none is baked. */
    static Body body(String name, double r) {
        Map<String, Body> bs = bodies();
        if (name != null && bs.containsKey(name)) return bs.get(name);
        double total = 0;
        for (Body b : bs.values()) total += b.weight;
        double t = r * total, acc = 0;
        Body last = null;
        for (Body b : bs.values()) {
            acc += b.weight;
            last = b;
            if (t < acc) return b;
        }
        return last;
    }

    private static Object load(Object path) {
        return path == null ? null : ResourceLoader.INSTANCE.load(String.valueOf(path), "", ResourceLoader.CacheMode.REUSE);
    }

    private static Transform3D t12(List<?> t) {
        double[] v = new double[12];
        for (int i = 0; i < 12; i++) v[i] = ((Number) t.get(i)).doubleValue();
        return new Transform3D(new Vector3(v[0], v[1], v[2]), new Vector3(v[3], v[4], v[5]), new Vector3(v[6], v[7], v[8]),
                new Vector3(v[9], v[10], v[11]));
    }

    private static Texture2D handTexture(float[] data, int rows) {
        ByteBuffer bb = ByteBuffer.allocate(data.length * 4).order(ByteOrder.LITTLE_ENDIAN);
        for (float f : data) bb.putFloat(f);
        Image img = Image.createFromData(3, rows, false, Image.Format.RGBAF, new PackedByteArray(bb.array()));
        return img == null ? null : ImageTexture.createFromImage(img);
    }

    /** sRGB 0..1 -> linear (the shader's palette is not hinted: an array uniform's hint is not applied to a packed value). */
    private static double linear(double c) { return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }

    // ── the draw layers ──────────────────────────────────────────────────────────────────────────

    /** One MultiMesh and its instance buffer (FLOATS a body: 3x4 transform [, colour], custom data). */
    static final class Layer {
        final MultiMeshInstance3D mmi;
        final int floats;
        float[] buf = new float[0];
        int count;
        Layer(MultiMeshInstance3D mmi, int floats) { this.mmi = mmi; this.floats = floats; }

        /** Room for one more instance; returns its offset in {@link #buf}. */
        int next() {
            if (buf.length < (count + 1) * floats) {
                int cap = Math.max(8, Integer.highestOneBit(Math.max(1, count)) << 1);
                float[] nb = new float[cap * floats];
                System.arraycopy(buf, 0, nb, 0, buf.length);
                buf = nb;
                mmi.getMultimesh().setInstanceCount(cap);
            }
            return floats * count++;
        }

        void upload() {
            MultiMesh mm = mmi.getMultimesh();
            if (buf.length > 0) mm.setBuffer(new PackedFloat32Array(buf));
            mm.setVisibleInstanceCount(count);
        }
    }

    private static Shader bodyShader, weaponShader;

    static Layer bodyLayer(Node3D parent, Body b, String outfit) {
        if (bodyShader == null) bodyShader = load(SHADER) instanceof Shader s ? s : null;
        ShaderMaterial mat = new ShaderMaterial();
        mat.setShader(bodyShader);
        mat.setShaderParameter("albedo_tex", b.atlas);
        mat.setShaderParameter("vat_pos", b.positions);
        mat.setShaderParameter("alpha_scissor", b.scissor);
        Map<String, Object> o = outfit == null || outfit.isEmpty() ? null : com.openworld.game.data.Tables.OUTFITS.get().get(outfit);
        if (o != null) {
            PackedVector3Array pal = new PackedVector3Array();
            for (String part : PARTS) {
                Object v = part.isEmpty() ? null : com.openworld.character.OutfitTable.valueFor(o, part);
                if (v instanceof List<?> rgb && rgb.size() >= 3) {
                    pal.append(new Vector3(linear(((Number) rgb.get(0)).doubleValue()), linear(((Number) rgb.get(1)).doubleValue()),
                            linear(((Number) rgb.get(2)).doubleValue())));
                } else {
                    pal.append(new Vector3(-1, -1, -1));   // the part keeps its own (an artist's material is not drawn here)
                }
            }
            mat.setShaderParameter("outfit", pal);
            mat.setShaderParameter("dressed", true);
        }
        return layer(parent, b.mesh, mat, true);
    }

    static Layer weaponLayer(Node3D parent, Body b, WeaponLook w) {
        if (weaponShader == null) weaponShader = load(WEAPON_SHADER) instanceof Shader s ? s : null;
        ShaderMaterial mat = new ShaderMaterial();
        mat.setShader(weaponShader);
        mat.setShaderParameter("hand_tex", b.hands);
        Transform3D socket = b.sockets.get(w.socket());
        mat.setShaderParameter("socket", socket != null ? socket : new Transform3D());
        return layer(parent, w.mesh(), mat, false);
    }

    private static Layer layer(Node3D parent, Mesh mesh, ShaderMaterial mat, boolean colors) {
        MultiMesh mm = new MultiMesh();
        mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);   // must precede instanceCount
        mm.setUseColors(colors);
        mm.setUseCustomData(true);
        mm.setMesh(mesh);
        MultiMeshInstance3D mmi = new MultiMeshInstance3D();
        mmi.setMultimesh(mm);
        mmi.setMaterialOverride(mat);
        mmi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        mmi.setAsTopLevel(true);
        parent.addChild(mmi);
        return new Layer(mmi, colors ? 20 : 16);
    }

    /** Write one instance: a yaw about +Y at (x, y, z), [white colour,] the clip as custom data. */
    static void write(Layer l, double x, double y, double z, double yaw, float row, float frames, float start, float fps) {
        int o = l.next();
        float[] b = l.buf;
        float c = (float) Math.cos(yaw), s = (float) Math.sin(yaw);
        b[o] = c;      b[o + 1] = 0f; b[o + 2] = s;   b[o + 3] = (float) x;
        b[o + 4] = 0f; b[o + 5] = 1f; b[o + 6] = 0f;  b[o + 7] = (float) y;
        b[o + 8] = -s; b[o + 9] = 0f; b[o + 10] = c;  b[o + 11] = (float) z;
        int k = o + 12;
        if (l.floats == 20) { b[k] = 1f; b[k + 1] = 1f; b[k + 2] = 1f; b[k + 3] = 0f; k += 4; }
        b[k] = row; b[k + 1] = frames; b[k + 2] = start; b[k + 3] = fps;
    }
}
