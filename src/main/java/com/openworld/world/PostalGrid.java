package com.openworld.world;

/**
 * THE POSTAL CODE (PLAN.md 3.26): a uniform grid over the 4 608 m world square, and the code IS the cell's x-y.
 *
 * <p>24 x 24 cells of 192 m: {@code x} is the column 1-24 from west to east, {@code y} the row 1-24 from the TOP
 * (north, -Z) down, so {@code 12-7} reads straight off the map's edges. An optional third number is the keypad
 * sub-cell 1-9 (64 m), counted like a phone keypad from the top-left, so {@code 5} is the cell's centre:
 * {@code 12-7-5}.
 *
 * <p>Chosen over a code numbered from city blocks (user, 2026-09-21) because a grid is a pure function of x/z: it
 * never renumbers when the roads change, so an old bug report still points at the right place; it has the same
 * precision everywhere; and it can be computed from the coordinates in any log with no data file. Every cell is
 * numbered, sea included. Engine-free and the ONE owner, so the HUD, the map, the console and the bug report
 * cannot disagree ({@code PostalGridTest}).
 */
public final class PostalGrid {
    public static final double HALF = 2304.0;
    public static final int CELLS = 24;
    public static final double CELL = 2.0 * HALF / CELLS;        // 192 m
    public static final double SUB = CELL / 3.0;                 // 64 m

    private PostalGrid() {}

    /** A cell, and optionally its keypad sub-cell (0 = the whole cell). */
    public record Code(int x, int y, int sub) {
        @Override
        public String toString() {
            return sub == 0 ? x + "-" + y : x + "-" + y + "-" + sub;
        }
    }

    private static int clampCell(int v) { return Math.max(1, Math.min(CELLS, v)); }

    /** The code at world (X, Z), with its sub-cell. Points off the square clamp to the edge cell. */
    public static Code of(double x, double z) {
        double u = x + HALF, v = z + HALF;
        int cx = clampCell((int) Math.floor(u / CELL) + 1);
        int cy = clampCell((int) Math.floor(v / CELL) + 1);
        double ux = u - (cx - 1) * CELL, vz = v - (cy - 1) * CELL;
        int col = Math.max(0, Math.min(2, (int) Math.floor(ux / SUB)));
        int row = Math.max(0, Math.min(2, (int) Math.floor(vz / SUB)));
        return new Code(cx, cy, row * 3 + col + 1);
    }

    /** "12-7-5" -- the code at (X, Z) in its full, reportable form. */
    public static String label(double x, double z) { return of(x, z).toString(); }

    /** The world (X, Z) at the centre of a code: the cell's centre, or its sub-cell's when one is given. */
    public static double[] centre(Code c) {
        double x0 = -HALF + (c.x() - 1) * CELL, z0 = -HALF + (c.y() - 1) * CELL;
        if (c.sub() == 0) return new double[] {x0 + CELL / 2.0, z0 + CELL / 2.0};
        int col = (c.sub() - 1) % 3, row = (c.sub() - 1) / 3;
        return new double[] {x0 + (col + 0.5) * SUB, z0 + (row + 0.5) * SUB};
    }

    /** "12-7" or "12-7-5" -> a code, or null when it is not one (out of range, not numbers). */
    public static Code parse(String s) {
        if (s == null) return null;
        String[] p = s.trim().split("[-\\s]+");
        if (p.length < 2 || p.length > 3) return null;
        try {
            int x = Integer.parseInt(p[0]), y = Integer.parseInt(p[1]);
            int sub = p.length == 3 ? Integer.parseInt(p[2]) : 0;
            if (x < 1 || x > CELLS || y < 1 || y > CELLS || sub < 0 || sub > 9) return null;
            return new Code(x, y, sub);
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
