package com.openworld.world;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

/**
 * A building's baked walk window (PLAN.md 1g f; tools/building_door_paths.py `walk_grid`): a 0.5 m grid over 70 m
 * round an enterable building, a cell occupied where a building's plinth (grown by a body's radius) stands. A breaching
 * unit searches it from where it stands to a door's outside, so it walks round the NEIGHBOURS -- the live route only
 * knew the building's own corners and ran into a touching neighbour (probe_breach: 26 give-ups of 28). Engine-free
 * ({@code WalkGridTest}).
 */
public final class WalkGrid {

    public final double x0, z0, res;
    public final int n;
    private final byte[] bits;

    public WalkGrid(double x0, double z0, int n, double res, byte[] bits) {
        this.x0 = x0; this.z0 = z0; this.n = n; this.res = res; this.bits = bits;
    }

    public static WalkGrid parse(double x0, double z0, int n, double res, String base64) {
        return new WalkGrid(x0, z0, n, res, Base64.getDecoder().decode(base64));
    }

    public boolean occupied(int gx, int gz) {
        if (gx < 0 || gz < 0 || gx >= n || gz >= n) return true;
        int k = gx * n + gz;
        return ((bits[k >> 3] >> (7 - (k & 7))) & 1) != 0;
    }

    public int cellX(double x) { return (int) Math.floor((x - x0) / res); }

    public int cellZ(double z) { return (int) Math.floor((z - z0) / res); }

    public boolean holds(double x, double z) {
        int gx = cellX(x), gz = cellZ(z);
        return gx >= 0 && gz >= 0 && gx < n && gz < n;
    }

    /** The nearest free cell within {@code reach} cells of (gx, gz), or null. */
    private int[] free(int gx, int gz, int reach) {
        gx = Math.max(0, Math.min(n - 1, gx));
        gz = Math.max(0, Math.min(n - 1, gz));
        if (!occupied(gx, gz)) return new int[] {gx, gz};
        int[] best = null;
        int bd = Integer.MAX_VALUE;
        for (int dx = -reach; dx <= reach; dx++)
            for (int dz = -reach; dz <= reach; dz++) {
                int d = dx * dx + dz * dz;
                if (d < bd && !occupied(gx + dx, gz + dz)) { bd = d; best = new int[] {gx + dx, gz + dz}; }
            }
        return best;
    }

    /**
     * A walk from (fx, fz) to (tx, tz) round every occupied cell, as string-pulled waypoints [x, z] (the start not
     * included, the goal last), or null when no walk exists. A start outside the window starts at the window's
     * nearest free cell.
     */
    public List<double[]> path(double fx, double fz, double tx, double tz) {
        int[] a = free(cellX(fx), cellZ(fz), 6), b = free(cellX(tx), cellZ(tz), 3);
        if (a == null || b == null) return null;
        int[] parent = new int[n * n];
        java.util.Arrays.fill(parent, -2);
        int start = a[0] * n + a[1], goal = b[0] * n + b[1];
        parent[start] = -1;
        ArrayDeque<Integer> q = new ArrayDeque<>();
        q.add(start);
        int[][] steps = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
        while (!q.isEmpty() && parent[goal] == -2) {
            int c = q.poll(), cx = c / n, cz = c % n;
            for (int[] s : steps) {
                int ux = cx + s[0], uz = cz + s[1];
                if (ux < 0 || uz < 0 || ux >= n || uz >= n) continue;
                int u = ux * n + uz;
                if (parent[u] != -2 || occupied(ux, uz)) continue;
                parent[u] = c;
                q.add(u);
            }
        }
        if (parent[goal] == -2) return null;
        List<Integer> chain = new ArrayList<>();
        for (int c = goal; c != -1; c = parent[c]) chain.add(0, c);
        List<double[]> out = new ArrayList<>();
        int k = 0;
        while (k < chain.size() - 1) {
            int far = chain.size() - 1;
            while (far > k + 1 && !clear(chain.get(k), chain.get(far))) far--;
            int c = chain.get(far);
            out.add(new double[] {x0 + (c / n + 0.5) * res, z0 + (c % n + 0.5) * res});
            k = far;
        }
        if (out.isEmpty()) out.add(new double[] {tx, tz});
        else out.set(out.size() - 1, new double[] {tx, tz});
        return out;
    }

    /** Length of a walk (start excluded from the list), metres. */
    public static double length(double fx, double fz, List<double[]> way) {
        double len = 0, x = fx, z = fz;
        for (double[] p : way) { len += Math.hypot(p[0] - x, p[1] - z); x = p[0]; z = p[1]; }
        return len;
    }

    private boolean clear(int a, int b) {
        double ax = a / n, az = a % n, bx = b / n, bz = b % n;
        int steps = (int) (Math.max(Math.abs(bx - ax), Math.abs(bz - az)) * 2) + 1;
        for (int t = 0; t <= steps; t++) {
            double u = ax + (bx - ax) * t / steps, v = az + (bz - az) * t / steps;
            if (occupied((int) Math.round(u), (int) Math.round(v))) return false;
        }
        return true;
    }
}
