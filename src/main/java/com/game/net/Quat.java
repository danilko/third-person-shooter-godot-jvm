package com.game.net;

/**
 * Minimal immutable quaternion — engine-free (no {@code godot.core.Quaternion}) for the same
 * headless-testability reason as {@link Vec3}. Used by {@link RigidSnapshotInterpolator} to
 * smooth a replicated rigid body's full orientation (vehicles roll and pitch — one yaw float,
 * which is all the character path replicates, is not enough).
 *
 * The Godot adapter ({@code com.vehicle.VehicleNetworkController}) translates
 * {@code godot.core.Quaternion} ↔ {@code Quat} at the boundary.
 */
public record Quat(double x, double y, double z, double w) {

    public static final Quat IDENTITY = new Quat(0, 0, 0, 1);

    public double length() {
        return Math.sqrt(x * x + y * y + z * z + w * w);
    }

    /** Unit-length copy; a degenerate (near-zero) quaternion falls back to identity. */
    public Quat normalized() {
        double len = length();
        if (len < 1e-9) return IDENTITY;
        return new Quat(x / len, y / len, z / len, w / len);
    }

    public double dot(Quat other) {
        return x * other.x + y * other.y + z * other.z + w * other.w;
    }

    /**
     * Shortest-path spherical interpolation toward {@code other} by {@code t} in [0,1].
     * Negates {@code other} when the dot product is negative (q and −q encode the same
     * rotation) so interpolation never takes the long way around. Falls back to
     * normalized lerp for nearly-parallel inputs where sin(theta) degenerates.
     */
    public Quat slerp(Quat other, double t) {
        double d = dot(other);
        double ox = other.x, oy = other.y, oz = other.z, ow = other.w;
        if (d < 0) { d = -d; ox = -ox; oy = -oy; oz = -oz; ow = -ow; }
        if (d > 0.9995) {
            return new Quat(x + (ox - x) * t, y + (oy - y) * t,
                    z + (oz - z) * t, w + (ow - w) * t).normalized();
        }
        double theta = Math.acos(Math.min(1.0, d));
        double sinTheta = Math.sin(theta);
        double a = Math.sin((1 - t) * theta) / sinTheta;
        double b = Math.sin(t * theta) / sinTheta;
        return new Quat(a * x + b * ox, a * y + b * oy, a * z + b * oz, a * w + b * ow).normalized();
    }

    /**
     * First-order integration of a world-space angular velocity (rad/s) over {@code dt} seconds:
     * {@code q' = normalize(q + 0.5 * (omega ⊗ q) * dt)} — the standard rigid-body orientation
     * dead-reckoning step. Accurate for the small per-frame angles replication deals in.
     */
    public Quat integrate(Vec3 angularVelocity, double dt) {
        double hx = angularVelocity.x() * 0.5 * dt;
        double hy = angularVelocity.y() * 0.5 * dt;
        double hz = angularVelocity.z() * 0.5 * dt;
        // (0, hx, hy, hz) ⊗ (x, y, z, w), added to this.
        return new Quat(
                x + (hx * w + hy * z - hz * y),
                y + (hy * w + hz * x - hx * z),
                z + (hz * w + hx * y - hy * x),
                w - (hx * x + hy * y + hz * z)).normalized();
    }

    /**
     * Angular distance to {@code other} in radians (0..pi), sign-insensitive (q ≡ −q).
     * Used by the interpolator's teleport-snap check and by tests.
     */
    public double angleTo(Quat other) {
        double d = Math.min(1.0, Math.abs(dot(other)));
        return 2.0 * Math.acos(d);
    }
}
