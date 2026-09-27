package com.openworld.world;

/**
 * Where a shot meets a LIGHT crowd ped (world.PedCrowd): a ped is Java state drawn by a MultiMesh, with no
 * collider, so a shot asks the crowds and this is the geometry. Engine-free (PedCrowdShotTest).
 */
public final class CrowdShot {

    private CrowdShot() { }

    /**
     * Distance along a ray (origin o, unit direction d) to where it enters an upright cylinder standing on
     * ({@code fx}, {@code fy}, {@code fz}) -- a ped's body -- or -1. Engine-free (PedCrowdShotTest).
     */
    public static double rayBody(double ox, double oy, double oz, double dx, double dy, double dz,
                          double fx, double fy, double fz, double height, double radius) {
        double hx = ox - fx, hz = oz - fz;
        double a = dx * dx + dz * dz;
        double t;
        if (a < 1e-9) {                          // straight up or down: inside the circle or never
            if (hx * hx + hz * hz > radius * radius) return -1.0;
            t = dy > 0 ? fy - oy : oy - (fy + height);
            t = Math.max(0.0, t);
        } else {
            double b = hx * dx + hz * dz;        // |o_h + t d_h - f_h|^2 = r^2  ->  a t^2 + 2 b t + c = 0
            double c = hx * hx + hz * hz - radius * radius;
            double disc = b * b - a * c;
            if (disc < 0.0) return -1.0;
            double sq = Math.sqrt(disc);
            double t0 = (-b - sq) / a, t1 = (-b + sq) / a;
            if (t1 < 0.0) return -1.0;
            t = Math.max(0.0, t0);
            // the ray must be within the body's height somewhere in [t, t1]
            double y0 = oy + dy * t, y1 = oy + dy * t1;
            if (Math.max(y0, y1) < fy || Math.min(y0, y1) > fy + height) return -1.0;
            if (y0 < fy || y0 > fy + height) {    // enters through the top or the bottom instead
                double tp = dy != 0.0 ? ((y0 < fy ? fy : fy + height) - oy) / dy : t;
                t = Math.max(t, tp);
            }
        }
        return t;
    }
}
