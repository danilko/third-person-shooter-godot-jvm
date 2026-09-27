package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.GeometryInstance3D;
import godot.api.Material;
import godot.api.MultiMesh;
import godot.api.MultiMeshInstance3D;
import godot.api.Node3D;
import godot.api.QuadMesh;
import godot.api.ResourceLoader;
import godot.core.PackedFloat32Array;
import godot.core.PackedStringArray;
import godot.core.StringName;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

/**
 * The crop on the island's paddy sections (user, 2026-09-25): rice or wheat, drawn from Binbun3D's Godot Grass
 * (CC0, `assets/vfx/grass/`) as billboard quads about a metre tall.
 *
 * <p>The FIELDS are derived by `tools/island_buildings.py` (a farm grid cell of dry land clear of roads, rail and
 * sites) and handed to this node by the streamed building cell it sits in, as 50 m CHUNKS: `chunks` holds
 * {@code x0, z0, y, kind} per chunk (Godot frame, `kind` 0 rice / 1 wheat) and `masks` a hex bitmask per chunk of
 * which 2 m cells are field ({@code CELLS x CELLS}, row-major along +z, bit 0 the most significant of the first
 * digit). The instances are GENERATED here, deterministically from the chunk's position, rather than stored:
 * written into the cell scenes they would be tens of megabytes of text.
 *
 * <p>One {@link MultiMeshInstance3D} per chunk, not per field, because a MultiMesh is ONE instance to the
 * renderer: its visibility range is whole-batch, and a batch bigger than the range culls every crop at any
 * distance (measured on the street trees, CLAUDE.md "Street trees"). Each chunk's buffer is set in ONE call.
 */
@Script
public class CropField extends Node3D {

    /** Chunk edge (m) and the field cell the mask is written in (m). */
    public static final float CHUNK = 50.0f;
    public static final int CELLS = 25;
    public static final float CELL = CHUNK / CELLS;
    /** Crop quads per field cell, on a GRID x GRID jittered lattice. A ripe field reads as a closed canopy with the
     *  soil barely showing (user, 2026-09-26): 4 x 4 per 2 m cell is 4 quads a square metre, each ~1.3 m wide, so
     *  every metre of soil sits under two or three overlapping plants. 2 x 2 left more soil than crop, 3 x 3 still showed ~40% from above. */
    public static final int GRID = 4;
    public static final int PER_CELL = GRID * GRID;

    @Export public PackedFloat32Array chunks = new PackedFloat32Array();
    @Export public PackedStringArray masks = new PackedStringArray();
    /** Where a chunk stops drawing (m from the camera), faded out over {@link #drawMargin}. */
    @Export public double drawDistance = 180.0;
    @Export public double drawMargin = 30.0;

    private static final String[] MATERIALS = {
        "res://assets/vfx/grass/crop_rice.tres", "res://assets/vfx/grass/crop_wheat.tres"};
    /** Quad size per kind (m): width x height. Rice at heading stands ~1.0-1.2 m, wheat ~1.1-1.3 m (user: "raise
     *  height"); the width is wider than a plant so neighbouring quads overlap into a canopy. */
    private static final float[][] SIZE = {{1.3f, 1.2f}, {1.3f, 1.3f}};

    /** A chunk is BUILT when the camera comes within {@link #drawDistance} + this, and FREED past + {@link #freeMargin}:
     *  a dense crop is ~10 000 quads a chunk, so only the fields round the camera exist at all. */
    @Export public double buildMargin = 40.0;
    @Export public double freeMargin = 100.0;

    private static final double CHECK_SECONDS = 0.5;

    private int built;
    private float[] data;
    private int count;
    private MultiMeshInstance3D[] live;
    private final QuadMesh[] meshes = new QuadMesh[SIZE.length];
    private double sinceCheck = CHECK_SECONDS;

    @Override
    public void _ready() {
        data = chunks.toFloatArray();
        count = Math.min(data.length / 4, masks.getSize());
        live = new MultiMeshInstance3D[count];
    }

    @Override
    public void _process(double delta) {
        sinceCheck += delta;
        if (sinceCheck < CHECK_SECONDS || count == 0) return;
        sinceCheck = 0.0;
        Camera3D cam = getViewport() == null ? null : getViewport().getCamera3d();
        if (cam == null) return;
        Vector3 at = cam.getGlobalPosition();
        double near = drawDistance + buildMargin, far = drawDistance + freeMargin;
        for (int i = 0; i < count; i++) {
            double cx = data[i * 4] + CHUNK / 2.0, cz = data[i * 4 + 1] + CHUNK / 2.0;
            double d = Math.hypot(at.getX() - cx, at.getZ() - cz) - CHUNK * 0.7071;
            if (live[i] == null && d < near) build(i);
            else if (live[i] != null && d > far) {
                built -= (int) live[i].getMultimesh().getInstanceCount();
                live[i].queueFree();
                live[i] = null;
            }
        }
    }

    private void build(int i) {
        int kind = Math.max(0, Math.min(SIZE.length - 1, (int) data[i * 4 + 3]));
        if (meshes[kind] == null) meshes[kind] = mesh(kind);
        if (meshes[kind] == null) return;
        float[] buf = instances(data[i * 4], data[i * 4 + 1], data[i * 4 + 2], masks.get(i));
        if (buf.length == 0) return;
        MultiMesh mm = new MultiMesh();
        mm.setTransformFormat(MultiMesh.TransformFormat.TRANSFORM_3D);   // must precede instanceCount
        mm.setMesh(meshes[kind]);
        mm.setInstanceCount(buf.length / 12);
        mm.setBuffer(new PackedFloat32Array(buf));
        MultiMeshInstance3D mmi = new MultiMeshInstance3D();
        mmi.setName(new StringName("Crop" + i));
        mmi.setMultimesh(mm);
        mmi.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
        mmi.setVisibilityRangeEnd((float) drawDistance);
        mmi.setVisibilityRangeEndMargin((float) drawMargin);
        mmi.setVisibilityRangeFadeMode(GeometryInstance3D.VisibilityRangeFadeMode.SELF);
        addChild(mmi);
        live[i] = mmi;
        built += buf.length / 12;
    }

    private QuadMesh mesh(int kind) {
        Material mat = (Material) ResourceLoader.load(MATERIALS[kind]);
        if (mat == null) {
            GD.printErr("CropField: no material at " + MATERIALS[kind]);
            return null;
        }
        QuadMesh q = new QuadMesh();
        q.setSize(new Vector2(SIZE[kind][0], SIZE[kind][1]));
        q.setCenterOffset(new Vector3(0.0, SIZE[kind][1] / 2.0, 0.0));
        q.setMaterial(mat);
        return q;
    }

    /** The chunk's instance buffer (12 floats per instance: a 3x4 transform, identity basis -- the shader faces it). */
    static float[] instances(float x0, float z0, float y, String mask) {
        int count = 0;
        for (int k = 0; k < CELLS * CELLS; k++) if (bit(mask, k)) count++;
        float[] out = new float[count * PER_CELL * 12];
        int o = 0;
        for (int k = 0; k < CELLS * CELLS; k++) {
            if (!bit(mask, k)) continue;
            int row = k / CELLS, col = k % CELLS;
            for (int j = 0; j < PER_CELL; j++) {
                long h = hash(Math.round(x0) * 73856093L ^ Math.round(z0) * 19349663L ^ k * 83492791L ^ j * 2654435761L);
                float jx = ((h & 0xFFFF) / 65535.0f + (j % GRID)) / GRID;
                float jz = (((h >>> 16) & 0xFFFF) / 65535.0f + (j / GRID)) / GRID;
                out[o] = 1.0f;       out[o + 1] = 0.0f;  out[o + 2] = 0.0f;  out[o + 3] = x0 + (col + jx) * CELL;
                out[o + 4] = 0.0f;   out[o + 5] = 1.0f;  out[o + 6] = 0.0f;  out[o + 7] = y;
                out[o + 8] = 0.0f;   out[o + 9] = 0.0f;  out[o + 10] = 1.0f; out[o + 11] = z0 + (row + jz) * CELL;
                o += 12;
            }
        }
        return out;
    }

    static boolean bit(String hex, int k) {
        int d = k >> 2;
        if (d >= hex.length()) return false;
        int v = Character.digit(hex.charAt(d), 16);
        return v >= 0 && ((v >> (3 - (k & 3))) & 1) != 0;
    }

    private static long hash(long x) {
        x ^= x >>> 33; x *= 0xff51afd7ed558ccdL; x ^= x >>> 33; x *= 0xc4ceb9fe1a85ec53L; x ^= x >>> 33;
        return x;
    }

    /** Probe readout: how many crop quads this node has built now (only the chunks near the camera exist). */
    @Register
    public int cropsBuiltNow() { return built; }
}
