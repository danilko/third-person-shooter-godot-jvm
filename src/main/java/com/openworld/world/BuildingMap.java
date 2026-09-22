package com.openworld.world;

import godot.api.Image;
import godot.api.ImageTexture;
import godot.api.Texture2D;
import godot.core.PackedByteArray;

import java.util.List;

/**
 * The map's BUILDING layer (user, 2026-09-22: "place squares on the minimap and the big map so the user knows the
 * surroundings"): every building's footprint, painted once into ONE picture over the same map square as the road
 * picture ({@link RoadMap#mapSquare}), so the minimap and the full map draw the whole city as a single textured
 * polygon -- the road picture's rule, and for the same reason: 3 000 rectangles drawn one bridge call at a time
 * cost more than the rest of the map together.
 *
 * <p>Derived, never authored: the footprints are {@link Places#footprints} (a building's type AABB, placed, written by
 * {@code island_buildings.py write} beside the map's places), and the picture is rebuilt when that record or the
 * map square changes. Painted at load in the game (tens of milliseconds, once) rather than baked: the buildings are
 * re-derived far more often than the roads, and a separate bake would be one more thing to keep fresh.
 *
 * <p>Alpha is coverage (1 inside a footprint); the mips are AVERAGED ({@code Image.generate_mipmaps}), unlike the
 * roads' max-filtered ones, so a zoomed-out city reads as the density of its blocks rather than a solid slab.
 */
public final class BuildingMap {

    /** The picture's edge in pixels, at most. 4608 m over 2048 px = 2.25 m/px: a 5 m shop is two pixels across. */
    public static final int MAX_PX = 2048;

    private static Texture2D texture = null;
    private static Image image = null;
    private static int builtFor = -1;
    private static double[] builtSquare = null;

    private BuildingMap() {}

    /** The building picture over {@link RoadMap#mapSquare}, or null with no roads or no footprints. */
    public static Texture2D texture() {
        double[] sq = RoadMap.mapSquare();
        List<float[]> fps = Places.footprints();
        if (sq == null || fps.isEmpty()) return null;
        int v = Places.version();
        if (texture != null && v == builtFor && java.util.Arrays.equals(sq, builtSquare)) return texture;
        int px = Math.min(MAX_PX, Math.max(256, Integer.highestOneBit((int) Math.ceil(sq[2] / 2.0))));
        byte[] cov = paint(fps, sq[0], sq[1], sq[2], px);
        byte[] la8 = new byte[px * px * 2];
        for (int i = 0; i < px * px; i++) { la8[2 * i] = (byte) 255; la8[2 * i + 1] = cov[i]; }
        image = Image.createFromData(px, px, false, Image.Format.LA8, new PackedByteArray(la8));
        image.generateMipmaps(false);
        texture = ImageTexture.createFromImage(image);
        builtFor = v;
        builtSquare = sq;
        return texture;
    }

    /** Coverage 0..1 at a world point (probe readout; 0 off the picture). */
    public static double coverageAt(double x, double z) {
        double[] sq = RoadMap.mapSquare();
        if (texture() == null || image == null || sq == null) return 0;
        int px = image.getWidth();
        int c = (int) Math.floor((x - sq[0]) / sq[2] * px), r = (int) Math.floor((z - sq[1]) / sq[2] * px);
        if (c < 0 || r < 0 || c >= px || r >= px) return 0;
        return image.getPixel(c, r).getA();
    }

    /** Engine-free: each footprint (a convex quad) filled into a px x px coverage raster over the square. */
    public static byte[] paint(List<float[]> fps, double minX, double minZ, double size, int px) {
        byte[] out = new byte[px * px];
        double mpp = size / px;
        for (float[] q : fps) {
            double[] xs = {q[1], q[3], q[5], q[7]}, zs = {q[2], q[4], q[6], q[8]};
            double ax = Math.min(Math.min(xs[0], xs[1]), Math.min(xs[2], xs[3]));
            double bx = Math.max(Math.max(xs[0], xs[1]), Math.max(xs[2], xs[3]));
            double az = Math.min(Math.min(zs[0], zs[1]), Math.min(zs[2], zs[3]));
            double bz = Math.max(Math.max(zs[0], zs[1]), Math.max(zs[2], zs[3]));
            int c0 = Math.max(0, (int) Math.floor((ax - minX) / mpp)), c1 = Math.min(px - 1, (int) Math.floor((bx - minX) / mpp));
            int r0 = Math.max(0, (int) Math.floor((az - minZ) / mpp)), r1 = Math.min(px - 1, (int) Math.floor((bz - minZ) / mpp));
            // the quad's winding, so "inside" is the same sign for every edge whichever way it was written
            double area = 0;
            for (int k = 0; k < 4; k++) area += xs[k] * zs[(k + 1) % 4] - xs[(k + 1) % 4] * zs[k];
            double sgn = area >= 0 ? 1 : -1;
            for (int r = r0; r <= r1; r++) {
                double z = minZ + (r + 0.5) * mpp;
                for (int c = c0; c <= c1; c++) {
                    double x = minX + (c + 0.5) * mpp;
                    boolean in = true;
                    for (int k = 0; k < 4 && in; k++) {
                        double ex = xs[(k + 1) % 4] - xs[k], ez = zs[(k + 1) % 4] - zs[k];
                        if (sgn * (ex * (z - zs[k]) - ez * (x - xs[k])) < 0) in = false;
                    }
                    if (in) out[r * px + c] = (byte) 255;
                }
            }
        }
        return out;
    }
}
