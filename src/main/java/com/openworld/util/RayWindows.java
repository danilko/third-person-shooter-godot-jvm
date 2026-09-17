package com.openworld.util;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Short query windows along a long ray, around the bodies near it (PLAN.md P0 0.4, 2026-09-17).
 *
 * <p><b>Why this exists: Jolt's ray test against a small capsule is not precise when the ray STARTS far
 * from it.</b> A ray aimed exactly at a capsule's centre reports nothing once the capsule's radius is under
 * about {@code 2.4e-4 x} the distance from the ray's start: measured with {@code
 * tools/godot/probe_ray_capsule.gd}, 28 of 400 rays at a thigh hitbox (radius 5.6 cm) from 250 m, 0 of 400
 * from 5 m, and 0 of 400 from 5 m with the same ray carried 500 m PAST it, so it is the start distance, not
 * the length (a float32 discriminant cancelling in the analytic ray-capsule solve fits every case). This
 * character's hitboxes go unsafe from 60 m (hand_l) to 540 m (spine_03). In play it was the reported "a still
 * enemy, the first scoped shot does not hit": the scope line was on the thigh and the bullet went on to the
 * terrain 490 m out.
 *
 * <p>The fix is the Source/CS split: the long ray still answers the WORLD, and the bodies that carry small
 * shapes are asked again with short rays that start a few metres before them. This class is the engine-free
 * half — which windows to ask; {@code WeaponItem} runs them.
 */
public final class RayWindows {

    private RayWindows() {}

    /** A candidate whose shapes all lie nearer than this was already resolved precisely by the long ray
     *  (the smallest hitbox, r 1.4 cm, is safe to 60 m; a third of that). */
    public static final double SAFE_START = 20.0;
    /** A body's root to the furthest shape it carries: a prone or seated character, an occupant beside a
     *  vehicle's origin. */
    public static final double REACH = 3.5;
    /** A window starts this far before a candidate's root along the ray and ends as far past it, so a
     *  window never starts more than LEAD + REACH (8 m) from the shape it is for: safe for r > 6 mm. */
    public static final double LEAD = 4.5;
    /** Overlapping windows are coalesced only while the result stays this short, so a crowd along the
     *  line does not become one long, imprecise query again. */
    public static final double MAX_WINDOW = 12.0;

    /**
     * Sorted windows {from, to} (distances along the ray) for the candidate roots near a ray.
     *
     * @param o     ray origin (x, y, z)
     * @param dir   UNIT direction (x, y, z)
     * @param limit how far the long ray reached (its hit distance, or its range)
     * @param roots candidate root positions, each (x, y, z)
     */
    public static List<double[]> windows(double[] o, double[] dir, double limit, List<double[]> roots) {
        List<double[]> raw = new ArrayList<>();
        for (double[] r : roots) {
            double vx = r[0] - o[0], vy = r[1] - o[1], vz = r[2] - o[2];
            double t = vx * dir[0] + vy * dir[1] + vz * dir[2];
            if (t + REACH < SAFE_START || t - REACH >= limit) continue;
            double px = vx - dir[0] * t, py = vy - dir[1] * t, pz = vz - dir[2] * t;
            if (px * px + py * py + pz * pz > REACH * REACH) continue;
            double from = Math.max(0.0, t - LEAD);
            double to = Math.min(limit, t + LEAD);
            if (to > from) raw.add(new double[] {from, to});
        }
        raw.sort(Comparator.comparingDouble(w -> w[0]));
        List<double[]> out = new ArrayList<>();
        for (double[] w : raw) {
            double[] last = out.isEmpty() ? null : out.get(out.size() - 1);
            if (last != null && w[0] <= last[1] && Math.max(last[1], w[1]) - last[0] <= MAX_WINDOW) {
                last[1] = Math.max(last[1], w[1]);
            } else {
                out.add(w);
            }
        }
        return out;
    }
}
