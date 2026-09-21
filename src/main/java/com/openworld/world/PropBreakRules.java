package com.openworld.world;

/**
 * The rules of a knock-down street pole (PLAN.md 3.11), engine-free so they can be unit-tested
 * ({@code PropBreakRulesTest}). {@link BreakableProps} is the thin Godot node that applies them.
 *
 * <p>The shape is GTA's: a pole is a static collider until a vehicle reaches it fast enough, a physics body only
 * while it falls, and it comes back where no one is looking. Three decisions live here:
 * <ul>
 *   <li><b>Will this car reach this pole in the coming physics step?</b> ({@link #reachesPole}) — asked BEFORE the
 *       step, in the car's own frame, so the pole's collider can be switched off before the car touches it. A car
 *       that touched the collider first would already have lost its speed to the contact solver, and giving it back
 *       afterwards is a guess at what the solver took.</li>
 *   <li><b>How much speed does the car keep?</b> ({@link #keepFraction}) — a perfectly inelastic hit of the car's
 *       mass against the pole's effective mass: {@code m_car / (m_car + m_pole)}. A signal pole is heavier than a
 *       lamp, so it costs more.</li>
 *   <li><b>May it come back yet?</b> ({@link #mayRestore}) — only after its respawn time, and only where no viewer
 *       can see the spot (farther than the hide distance, or outside a camera's view cone).</li>
 * </ul>
 */
public final class PropBreakRules {
    private PropBreakRules() {}

    /** Metres of margin added to the car's footprint, so a pole a hair outside it is caught before it is touched. */
    public static final double REACH_MARGIN = 0.35;
    /** Physics steps of travel looked ahead ALONG THE MOTION: a car can come into contact within the step after this one. */
    public static final double LOOKAHEAD_STEPS = 2.0;

    /**
     * True when a pole at {@code (localX, localZ)} in the CAR's frame (metres from its centre, any horizontal axes the
     * caller keeps consistent) lies in the car's plan rectangle — grown by the pole's radius and {@link #REACH_MARGIN}
     * — SWEPT along the car's motion by this step's travel, and ahead of that motion. {@code (velX, velZ)} is the
     * car's velocity in the same frame.
     *
     * <p><b>The travel is added ALONG THE MOTION ONLY, never sideways</b> (PLAN.md 0.8). Growing the rectangle by the
     * travel on both axes made the car wider the faster it went — at 31 m/s it reached 1.05 m further to each side
     * than its own body, so a car driving dead centre down an expressway lane knocked down a barrier lamp every
     * ~36 m without ever touching one (measured: 16 poles over a 2.7 km drive, 0 contacts). A car does not get
     * wider with speed; it gets LONGER within a step, which is what the look-ahead is for.
     */
    public static boolean reachesPole(double localX, double localZ, double halfWidth, double halfLength,
                                      double poleRadius, double velX, double velZ, double dt) {
        double speed = Math.hypot(velX, velZ);
        if (speed < 1e-6) return false;
        double hw = halfWidth + poleRadius + REACH_MARGIN;
        double hl = halfLength + poleRadius + REACH_MARGIN;
        // A pole ALREADY inside the grown rectangle that the car is moving away from has been passed, not hit.
        // The test is asked only of that case: a pole the car has not reached yet is decided by the sweep, so a
        // FLANK that is about to slide into one (a car scraping a kerb, where the pole is nearly abeam and the
        // dot product is nearly zero) is caught rather than refused.
        if (Math.abs(localX) <= hw && Math.abs(localZ) <= hl && localX * velX + localZ * velZ <= 0.0) return false;
        double travel = speed * dt * LOOKAHEAD_STEPS;
        // the rectangle translated by t along the unit motion contains the pole for t in each axis's slab; the
        // sweep reaches it when those slabs and [0, travel] share a t
        double[] sx = slab(localX, velX / speed, hw);
        if (sx == null) return false;
        double[] sz = slab(localZ, velZ / speed, hl);
        if (sz == null) return false;
        return Math.max(0.0, Math.max(sx[0], sz[0])) <= Math.min(travel, Math.min(sx[1], sz[1]));
    }

    /** The t interval over which {@code |p - t*d| <= h} holds, or null when it never does. */
    private static double[] slab(double p, double d, double h) {
        if (Math.abs(d) < 1e-9) {
            return Math.abs(p) <= h ? new double[]{Double.NEGATIVE_INFINITY, Double.POSITIVE_INFINITY} : null;
        }
        double a = (p - h) / d, b = (p + h) / d;
        return a <= b ? new double[]{a, b} : new double[]{b, a};
    }

    /** True when {@code speed} (m/s) knocks a pole down: at or above its break speed, which must be positive. */
    public static boolean breaks(double speed, double breakSpeed) {
        return breakSpeed > 0.0 && speed >= breakSpeed;
    }

    /** The fraction of its speed a car of mass {@code carMass} keeps after knocking down a pole of {@code poleMass}. */
    public static double keepFraction(double carMass, double poleMass) {
        if (carMass <= 0.0) return 0.0;
        return carMass / (carMass + Math.max(0.0, poleMass));
    }

    /**
     * The impulse (N·s) handed to the falling pole: the momentum the car lost, along the car's motion. Returned as
     * a scale on the car's velocity vector: {@code impulse = velocity * poleImpulseScale(...)}.
     */
    public static double poleImpulseScale(double carMass, double poleMass) {
        return carMass * (1.0 - keepFraction(carMass, poleMass));
    }

    /**
     * True when a viewer at {@code viewer} (x, y, z) looking along the unit vector {@code forward} can see the point
     * {@code p}: nearer than {@code hideDistance} and inside the cone of half-angle {@code halfFovRad}. A viewer
     * whose facing is unknown passes {@code forward == null} and sees every direction.
     */
    public static boolean sees(double[] viewer, double[] forward, double halfFovRad, double[] p, double hideDistance) {
        double dx = p[0] - viewer[0], dy = p[1] - viewer[1], dz = p[2] - viewer[2];
        double d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (d > hideDistance) return false;
        if (forward == null || d < 1e-6) return true;
        double cos = (dx * forward[0] + dy * forward[1] + dz * forward[2]) / d;
        return cos >= Math.cos(halfFovRad);
    }

    /** True when a pole broken {@code brokenFor} seconds ago may come back: its time is up and nobody sees it. */
    public static boolean mayRestore(double brokenFor, double respawnSeconds, boolean anyViewerSees, boolean occupied) {
        return brokenFor >= respawnSeconds && !anyViewerSees && !occupied;
    }
}
