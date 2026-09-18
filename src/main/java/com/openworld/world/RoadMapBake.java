package com.openworld.world;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * The baked road map's graph file (PLAN.md 4.7b): the whole network already in WORLD space, the
 * cell index over it, the map square, and the signature of the sources it was baked from. Engine-
 * free, so the round trip is unit-tested. The picture is a separate file (a compressed Godot Image
 * resource, written by {@link RoadMap#bake}).
 *
 * <p>Lanes carry their authored {@code next}/{@code inner}/{@code outer} ids, not resolved
 * successors: {@link RoadGraph#finish} resolves them on load by the one rule the live build uses,
 * so a bake cannot carry a different successor rule than the game.
 */
public final class RoadMapBake {

    static final int MAGIC = 0x524D4150;   // "RMAP"
    static final int VERSION = 1;

    /** What a bake holds besides the graph. */
    public static final class Meta {
        /** The sources it was baked from: one "sidecar|frame|md5" entry per sidecar, sorted. */
        public final String signature;
        /** The map square: north-west corner and edge (metres). */
        public final double minX, minZ, size;
        /** The picture's edge (px). */
        public final int imagePx;
        public Meta(String signature, double minX, double minZ, double size, int imagePx) {
            this.signature = signature; this.minX = minX; this.minZ = minZ; this.size = size;
            this.imagePx = imagePx;
        }
    }

    /** A bake read back: its meta and the graph, finished, with its index attached. */
    public static final class Loaded {
        public final Meta meta;
        public final RoadGraph graph;
        Loaded(Meta meta, RoadGraph graph) { this.meta = meta; this.graph = graph; }
    }

    private RoadMapBake() { }

    public static byte[] write(Meta meta, RoadGraph g) {
        RoadIndex idx = g.index();
        if (idx == null) throw new IllegalArgumentException("graph has no index");
        List<RoadGraph.Lane> lanes = idx.lanes();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(1 << 20);
        try (DataOutputStream o = new DataOutputStream(bytes)) {
            o.writeInt(MAGIC);
            o.writeInt(VERSION);
            o.writeUTF(meta.signature);
            o.writeDouble(meta.minX); o.writeDouble(meta.minZ); o.writeDouble(meta.size);
            o.writeInt(meta.imagePx);
            o.writeInt(lanes.size());
            for (RoadGraph.Lane l : lanes) {
                o.writeUTF(l.id);
                o.writeFloat(l.width);
                o.writeUTF(l.zoneId);
                o.writeUTF(l.roadName);
                o.writeInt(l.nextIds.size());
                for (String s : l.nextIds) o.writeUTF(s);
                o.writeUTF(l.innerId);
                o.writeUTF(l.outerId);
                o.writeInt(l.x.length);
                for (int i = 0; i < l.x.length; i++) {
                    o.writeDouble(l.x[i]); o.writeDouble(l.y[i]); o.writeDouble(l.z[i]);
                }
            }
            o.writeDouble(idx.minX); o.writeDouble(idx.minZ); o.writeDouble(idx.cell);
            o.writeInt(idx.nx); o.writeInt(idx.nz);
            for (float u : idx.upper) o.writeFloat(u);
            for (int[] c : idx.cells) {
                o.writeShort(c.length);
                for (int i : c) o.writeShort(i);
            }
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        return bytes.toByteArray();
    }

    /** Only the meta, for a freshness check that does not build the graph. Null if unreadable. */
    public static Meta readMeta(byte[] data) {
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(data))) {
            return meta(in);
        } catch (IOException | IllegalArgumentException e) {
            return null;
        }
    }

    public static Loaded read(byte[] data) {
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(data))) {
            Meta meta = meta(in);
            RoadGraph g = new RoadGraph();
            int n = in.readInt();
            for (int k = 0; k < n; k++) {
                String id = in.readUTF();
                float width = in.readFloat();
                String zone = in.readUTF(), road = in.readUTF();
                int nn = in.readInt();
                List<String> next = new ArrayList<>(nn);
                for (int i = 0; i < nn; i++) next.add(in.readUTF());
                String inner = in.readUTF(), outer = in.readUTF();
                int pts = in.readInt();
                double[] x = new double[pts], y = new double[pts], z = new double[pts];
                for (int i = 0; i < pts; i++) { x[i] = in.readDouble(); y[i] = in.readDouble(); z[i] = in.readDouble(); }
                g.addLane(id, x, y, z, width, zone, road, next, inner, outer);
            }
            g.finish();
            double ix = in.readDouble(), iz = in.readDouble(), cell = in.readDouble();
            int nx = in.readInt(), nz = in.readInt();
            float[] upper = new float[nx * nz];
            for (int i = 0; i < upper.length; i++) upper[i] = in.readFloat();
            int[][] cells = new int[nx * nz][];
            for (int c = 0; c < cells.length; c++) {
                int len = in.readShort() & 0xffff;
                int[] list = new int[len];
                for (int i = 0; i < len; i++) list[i] = in.readShort() & 0xffff;
                cells[c] = list;
            }
            g.setIndex(new RoadIndex(ix, iz, cell, nx, nz, upper, cells, new ArrayList<>(g.lanes())));
            return new Loaded(meta, g);
        } catch (IOException e) {
            throw new IllegalArgumentException("road map bake: " + e.getMessage(), e);
        }
    }

    private static Meta meta(DataInputStream in) throws IOException {
        if (in.readInt() != MAGIC) throw new IllegalArgumentException("not a road map bake");
        int v = in.readInt();
        if (v != VERSION) throw new IllegalArgumentException("road map bake version " + v + ", want " + VERSION);
        String sig = in.readUTF();
        double minX = in.readDouble(), minZ = in.readDouble(), size = in.readDouble();
        int px = in.readInt();
        return new Meta(sig, minX, minZ, size, px);
    }
}
