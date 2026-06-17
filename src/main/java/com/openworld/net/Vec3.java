package com.openworld.net;

import com.openworld.control.PlayerController;

/**
 * Minimal immutable 3D vector — deliberately engine-free (no {@code godot.core.Vector3}
 * import) so every class in {@code com.openworld.game.net} can be unit-tested headless without the
 * Godot runtime, which can't instantiate native types like {@code StreamPeerBuffer} or
 * {@code CharacterBody3D}.
 *
 * The Godot adapters ({@link com.openworld.net.NetworkController}, {@link com.openworld.control.PlayerController})
 * translate {@code godot.core.Vector3} ↔ {@link Vec3} at the boundary — the same "wire-format
 * isolated from carrier" split {@code NetMessageCodec} already uses for byte layout.
 */
public record Vec3(double x, double y, double z) {

    public static final Vec3 ZERO = new Vec3(0, 0, 0);

    /** Linear interpolation toward {@code other} by {@code t} in [0,1] (not clamped — caller controls range). */
    public Vec3 lerp(Vec3 other, double t) {
        return new Vec3(x + (other.x - x) * t,
                        y + (other.y - y) * t,
                        z + (other.z - z) * t);
    }

    public Vec3 plus(Vec3 other) {
        return new Vec3(x + other.x, y + other.y, z + other.z);
    }

    public Vec3 scaled(double s) {
        return new Vec3(x * s, y * s, z * s);
    }

    public double length() {
        return Math.sqrt(x * x + y * y + z * z);
    }

    public double distanceTo(Vec3 other) {
        double dx = other.x - x;
        double dy = other.y - y;
        double dz = other.z - z;
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }
}
