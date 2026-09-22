package com.openworld.world;

/**
 * Where an ambient car may NOT be born, relative to one player (user, 2026-09-22: "a vehicle spawns right in front
 * of me while driving and I crash into it, especially at high speed"). Engine-free, the ONE owner
 * ({@code TrafficSpawnRulesTest}); {@link ZoneManager} asks it for every player before it places a car.
 *
 * <p>GTA's rules, two of the three (the third, "not in the camera's view", needs the camera and lives in the
 * caller):
 * <ul>
 *   <li><b>never close</b>: nothing within {@code minDist} of the player, whichever way they face;</li>
 *   <li><b>never where they are going</b>: a moving player will cover {@code speed x leadSeconds} metres in the next
 *       few seconds, so the corridor ahead of them -- out to that distance plus {@code minDist}, and wide enough to
 *       take the road they are on and the side streets entering it -- is refused. At 40 m/s that is 320 m, i.e. the
 *       whole traffic ring ahead: a fast driver meets only cars that were ALREADY there.</li>
 * </ul>
 */
public final class TrafficSpawnRules {
    /** Below this speed (m/s) a player has no "ahead": walking pace is covered by the minimum distance. */
    public static final double MOVING = 3.0;
    /** Half-width of the refused corridor at the player; it widens with distance ahead ({@link #WIDEN}). */
    public static final double CORRIDOR = 40.0;
    public static final double WIDEN = 0.5;

    private TrafficSpawnRules() {}

    /** True when a car at (x, z) would appear too near, or in the path of, a player at (px, pz) moving (vx, vz). */
    public static boolean refuses(double x, double z, double px, double pz, double vx, double vz,
                                  double minDist, double leadSeconds) {
        double dx = x - px, dz = z - pz;
        double d = Math.hypot(dx, dz);
        if (d < minDist) return true;
        double speed = Math.hypot(vx, vz);
        if (speed < MOVING || leadSeconds <= 0) return false;
        double fx = vx / speed, fz = vz / speed;
        double along = dx * fx + dz * fz;
        if (along <= 0) return false;
        double lateral = Math.abs(dx * fz - dz * fx);
        return along < speed * leadSeconds + minDist && lateral < CORRIDOR + along * WIDEN;
    }
}
