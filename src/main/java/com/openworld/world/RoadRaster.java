package com.openworld.world;

/**
 * Paints the road network into one north-up image of the whole map square (PLAN.md 4.7b) — the
 * picture half of the baked road map, what the minimap and the full map draw instead of redrawing
 * every lane every frame (GTA's pre-rendered radar). Engine-free.
 *
 * <p>It paints ROADS, not lanes: every lane is swept at its own width (a carriageway's lanes sit one
 * lane-width apart, so their union is the carriageway), and then the picture is CLOSED by
 * {@link #GAP_FILL} — grown by it and shrunk back — so the median between a divided road's two
 * carriageways (3 m on the island's arterials) and the slivers at a junction fill in, while every
 * outer edge stays where it was. A divided road reads as one road, the way a GTA map draws it.
 * Pixel (0,0) is the north-west corner {@code (minX, minZ)}; +column is +X, +row is +Z, so the image
 * reads the same way as the map (north up).
 *
 * <p>Mip levels are the MAXIMUM of each 2x2 block, not the average: a 20 m road on the whole-island
 * view is a fifth of a pixel, and an averaged mip chain fades it to nothing, where a max chain keeps
 * every road at least one pixel wide at every zoom.
 */
public final class RoadRaster {

    /** The largest image edge (px). 4096 covers the island's 4.3 km at ~1.05 m/px. */
    public static final int MAX_PX = 4096;
    /** The finest pixel (m) — a small world is not painted finer than this. */
    public static final double MIN_METRES_PER_PX = 0.5;
    /** Closing radius (m): gaps narrower than twice this between painted lanes are filled. */
    public static final double GAP_FILL = 2.5;

    private RoadRaster() { }

    /** The image edge for a map square of {@code size} metres: a power of two, so every mip level
     *  halves exactly. */
    public static int edgeFor(double size) {
        int want = (int) Math.ceil(size / MIN_METRES_PER_PX);
        int px = 1;
        while (px < want && px < MAX_PX) px <<= 1;
        return px;
    }

    /** Level-0 coverage, one byte per pixel (0 = off the road, 255 = on it), anti-aliased over a
     *  pixel, gaps under {@code 2·GAP_FILL} closed. The outermost ring of pixels is left empty, so a
     *  texture clamped at its edge draws nothing past the map. */
    public static byte[] coverage(RoadGraph g, double minX, double minZ, double size, int px) {
        double mpp = size / px;
        // D = metres from each pixel centre to the nearest lane's EDGE (negative inside a lane).
        float[] d = new float[px * px];
        java.util.Arrays.fill(d, Float.POSITIVE_INFINITY);
        for (RoadGraph.Lane l : g.lanes()) {
            double half = l.width * 0.5;
            for (int i = 0; i + 1 < l.x.length; i++)
                capsule(d, px, minX, minZ, mpp, l.x[i], l.z[i], l.x[i + 1], l.z[i + 1], half, GAP_FILL + 2 * mpp);
        }
        // Closing: grow by GAP_FILL (the set D <= GAP_FILL), then shrink back by the distance from
        // each grown pixel to the nearest pixel outside it (an 8-neighbour chamfer transform).
        float[] e = new float[px * px];
        for (int k = 0; k < e.length; k++) e[k] = d[k] <= GAP_FILL ? Float.POSITIVE_INFINITY : 0f;
        chamfer(e, px);
        byte[] a = new byte[px * px];
        for (int k = 0; k < a.length; k++) {
            double painted = -d[k] / mpp + 0.5;                          // the lanes themselves, anti-aliased
            double closed = (e[k] * mpp - 0.5 * mpp - GAP_FILL) / mpp + 0.5;   // the closed set
            double cov = Math.max(painted, closed);
            if (cov <= 0) continue;
            a[k] = (byte) (cov >= 1 ? 255 : (int) Math.round(cov * 255));
        }
        for (int i = 0; i < px; i++) {
            a[i] = 0; a[(px - 1) * px + i] = 0; a[i * px] = 0; a[i * px + px - 1] = 0;
        }
        return a;
    }

    private static void capsule(float[] d, int px, double minX, double minZ, double mpp,
                                double ax, double az, double bx, double bz, double half, double beyond) {
        double reach = half + beyond;
        int c0 = Math.max(0, (int) Math.floor((Math.min(ax, bx) - reach - minX) / mpp));
        int c1 = Math.min(px - 1, (int) Math.floor((Math.max(ax, bx) + reach - minX) / mpp));
        int r0 = Math.max(0, (int) Math.floor((Math.min(az, bz) - reach - minZ) / mpp));
        int r1 = Math.min(px - 1, (int) Math.floor((Math.max(az, bz) + reach - minZ) / mpp));
        double dx = bx - ax, dz = bz - az, l2 = dx * dx + dz * dz;
        for (int r = r0; r <= r1; r++) {
            double pz = minZ + (r + 0.5) * mpp;
            for (int c = c0; c <= c1; c++) {
                double pxw = minX + (c + 0.5) * mpp;
                double t = l2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((pxw - ax) * dx + (pz - az) * dz) / l2));
                double qx = ax + dx * t - pxw, qz = az + dz * t - pz;
                float v = (float) (Math.sqrt(qx * qx + qz * qz) - half);
                int k = r * px + c;
                if (v < d[k]) d[k] = v;
            }
        }
    }

    /** In place: each non-zero pixel becomes its distance (px) to the nearest zero pixel. */
    private static void chamfer(float[] e, int px) {
        final float D1 = 1f, D2 = (float) Math.sqrt(2);
        for (int r = 0; r < px; r++)
            for (int c = 0; c < px; c++) {
                int k = r * px + c;
                float v = e[k];
                if (v == 0f) continue;
                if (c > 0) v = Math.min(v, e[k - 1] + D1);
                if (r > 0) {
                    v = Math.min(v, e[k - px] + D1);
                    if (c > 0) v = Math.min(v, e[k - px - 1] + D2);
                    if (c + 1 < px) v = Math.min(v, e[k - px + 1] + D2);
                }
                e[k] = v;
            }
        for (int r = px - 1; r >= 0; r--)
            for (int c = px - 1; c >= 0; c--) {
                int k = r * px + c;
                float v = e[k];
                if (v == 0f) continue;
                if (c + 1 < px) v = Math.min(v, e[k + 1] + D1);
                if (r + 1 < px) {
                    v = Math.min(v, e[k + px] + D1);
                    if (c + 1 < px) v = Math.min(v, e[k + px + 1] + D2);
                    if (c > 0) v = Math.min(v, e[k + px - 1] + D2);
                }
                e[k] = v;
            }
    }

    /** Number of levels (level 0 included) of a {@code px}-square power-of-two image. */
    public static int levels(int px) {
        int n = 1;
        while (px > 1) { px >>= 1; n++; }
        return n;
    }

    /** Level 0 and every max-filtered mip level, concatenated as Godot's {@code FORMAT_LA8} data
     *  (luminance 255, alpha = coverage), largest first. */
    public static byte[] la8WithMaxMips(byte[] level0, int px) {
        int total = 0;
        for (int s = px; ; s >>= 1) { total += s * s * 2; if (s == 1) break; }
        byte[] out = new byte[total];
        byte[] cur = level0;
        int s = px, off = 0;
        while (true) {
            for (int i = 0; i < s * s; i++) { out[off + 2 * i] = (byte) 255; out[off + 2 * i + 1] = cur[i]; }
            off += s * s * 2;
            if (s == 1) break;
            int h = s >> 1;
            byte[] next = new byte[h * h];
            for (int r = 0; r < h; r++)
                for (int c = 0; c < h; c++) {
                    int k = 2 * r * s + 2 * c;
                    int m = Math.max(Math.max(cur[k] & 0xff, cur[k + 1] & 0xff),
                            Math.max(cur[k + s] & 0xff, cur[k + s + 1] & 0xff));
                    next[r * h + c] = (byte) m;
                }
            cur = next;
            s = h;
        }
        return out;
    }
}
