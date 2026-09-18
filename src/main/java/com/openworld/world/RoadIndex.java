package com.openworld.world;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * A uniform cell grid over the whole map square that answers "which lanes can a point here snap
 * to" in constant time (PLAN.md 4.7b) — the lookup half of the baked road map. Engine-free.
 *
 * <p>Every cell covers the map to the world boundary, sea included, so a map click 600 m offshore
 * still finds its road with one array read. For each cell, with centre {@code c} and half-diagonal
 * {@code h}: {@code U = min over lanes of d(c, lane) + h} bounds the nearest lane's plan distance
 * from ANY point in the cell, and the cell lists every lane with {@code d(c, lane) <= U + h +
 * CANDIDATE_SLACK}. A lane left out is further than {@code U + CANDIDATE_SLACK} from every point in
 * the cell, so {@link RoadGraph#snaps} over the list is exactly {@code snaps} over the whole graph
 * for a plan snap, and for a 3D snap whenever the nearest found is within {@code U} (the graph
 * checks, and falls back to a full scan otherwise — a body high above every road).
 */
public final class RoadIndex {

    /** Cell edge (m). 32 m keeps a junction cell to a few dozen lanes and the island to 18k cells. */
    public static final double DEFAULT_CELL = 32.0;

    public final double minX, minZ, cell;
    public final int nx, nz;
    final float[] upper;
    final int[][] cells;
    private final List<RoadGraph.Lane> lanes;
    private final List<List<RoadGraph.Lane>> resolved;

    RoadIndex(double minX, double minZ, double cell, int nx, int nz, float[] upper, int[][] cells,
              List<RoadGraph.Lane> lanes) {
        this.minX = minX; this.minZ = minZ; this.cell = cell; this.nx = nx; this.nz = nz;
        this.upper = upper; this.cells = cells; this.lanes = lanes;
        resolved = new ArrayList<>(cells.length);
        for (int[] c : cells) {
            List<RoadGraph.Lane> r = new ArrayList<>(c.length);
            for (int i : c) r.add(lanes.get(i));
            resolved.add(Collections.unmodifiableList(r));
        }
    }

    /** Build over the square {@code [minX, minX+size] x [minZ, minZ+size]}. */
    public static RoadIndex build(RoadGraph g, double minX, double minZ, double size, double cell) {
        List<RoadGraph.Lane> lanes = new ArrayList<>(g.lanes());
        int n = Math.max(1, (int) Math.ceil(size / cell));
        double h = cell * Math.sqrt(0.5);
        double[][] bb = new double[lanes.size()][];
        for (int i = 0; i < lanes.size(); i++) bb[i] = lanes.get(i).boundsXZ();
        float[] upper = new float[n * n];
        int[][] cells = new int[n * n][];
        double[] boxD = new double[lanes.size()];
        Integer[] order = new Integer[lanes.size()];
        double[] exact = new double[lanes.size() * 2];
        for (int iz = 0; iz < n; iz++) {
            for (int ix = 0; ix < n; ix++) {
                double cx = minX + (ix + 0.5) * cell, cz = minZ + (iz + 0.5) * cell;
                for (int i = 0; i < lanes.size(); i++) {
                    order[i] = i;
                    double dx = Math.max(0, Math.max(bb[i][0] - cx, cx - bb[i][2]));
                    double dz = Math.max(0, Math.max(bb[i][1] - cz, cz - bb[i][3]));
                    boxD[i] = Math.sqrt(dx * dx + dz * dz);
                }
                Arrays.sort(order, (a, b) -> Double.compare(boxD[a], boxD[b]));
                double best = Double.MAX_VALUE;
                int measured = 0;
                for (Integer i : order) {
                    if (boxD[i] > best + 2 * h + RoadGraph.CANDIDATE_SLACK) break;
                    exact[measured++] = i;
                    double d = planDistance(lanes.get(i), cx, cz);
                    exact[measured++] = d;
                    best = Math.min(best, d);
                }
                double keep = best + 2 * h + RoadGraph.CANDIDATE_SLACK;
                int[] list = new int[measured / 2];
                int k = 0;
                for (int m = 0; m < measured; m += 2) if (exact[m + 1] <= keep) list[k++] = (int) exact[m];
                int[] trimmed = Arrays.copyOf(list, k);
                Arrays.sort(trimmed);
                cells[iz * n + ix] = trimmed;
                upper[iz * n + ix] = (float) (best + h);
            }
        }
        return new RoadIndex(minX, minZ, cell, n, n, upper, cells, lanes);
    }

    private int cellOf(double x, double z) {
        int ix = (int) Math.floor((x - minX) / cell), iz = (int) Math.floor((z - minZ) / cell);
        if (ix < 0 || iz < 0 || ix >= nx || iz >= nz) return -1;
        return iz * nx + ix;
    }

    /** The candidate lanes for a point, or null outside the grid (the caller then scans). */
    public List<RoadGraph.Lane> candidates(double x, double z) {
        int c = cellOf(x, z);
        return c < 0 ? null : resolved.get(c);
    }

    /** An upper bound on the plan distance from this point to its nearest lane (+inf outside). */
    public double upperBound(double x, double z) {
        int c = cellOf(x, z);
        return c < 0 ? Double.POSITIVE_INFINITY : upper[c];
    }

    /** The lane list the cell entries index into (the graph's order when built). */
    List<RoadGraph.Lane> lanes() { return lanes; }

    static double planDistance(RoadGraph.Lane l, double px, double pz) {
        double best = Double.MAX_VALUE;
        for (int i = 0; i + 1 < l.x.length; i++) {
            double ax = l.x[i], az = l.z[i];
            double dx = l.x[i + 1] - ax, dz = l.z[i + 1] - az;
            double l2 = dx * dx + dz * dz;
            double t = l2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / l2));
            double qx = ax + dx * t - px, qz = az + dz * t - pz;
            best = Math.min(best, qx * qx + qz * qz);
        }
        return Math.sqrt(best);
    }
}
