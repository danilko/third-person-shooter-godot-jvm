package com.openworld.weapon;

/**
 * Deterministic bullet spread (PLAN.md N1): the pellets of one trigger pull as a pure function of
 * {@code (aim direction, half-angle, seed, pellet index)}.
 *
 * <p>Spread used to be sampled from the engine's global RNG ({@code GD.randf}), so a pellet could not
 * be reproduced anywhere else, and a networked client had to send the host one post-spread ray PER
 * PELLET (eight reliable messages per SG1 pull). With a seed both sides derive the same cone, so the
 * client sends the pre-spread aim, the half-angle and the seed once, and the host regenerates every
 * pellet itself — and can refuse a cone narrower than the weapon allows.
 *
 * <p>Engine-free (plain doubles, own PRNG) so it is unit-tested headless and cannot drift with an
 * engine RNG or a float {@code Vector3} implementation: host and client run exactly this arithmetic.
 * The sample is the same one {@code FirearmItem.applySpread} always drew — a uniform point on the
 * disk of the cone (random axis perpendicular to the shot, {@code sqrt(u)}-distributed angle).
 */
public final class SpreadPattern {

    private SpreadPattern() {}

    /** SplitMix64 finaliser: a well-mixed 64-bit output for any 64-bit input. */
    static long mix(long z) {
        z += 0x9E3779B97F4A7C15L;
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }

    /** Uniform double in {@code [0, 1)} from the top 53 bits of a mixed value. */
    private static double unit(long bits) {
        return (bits >>> 11) * 0x1.0p-53;
    }

    /**
     * The seed of one trigger pull: a shooter identity hash and that shooter's shot counter.
     * {@code String.hashCode} is specified by the Java language, so every JVM on every peer
     * derives the same value from the same character id.
     */
    public static long seedFor(String shooterId, long shotSeq) {
        long idHash = shooterId == null ? 0 : shooterId.hashCode();
        return mix((idHash << 32) ^ (shotSeq & 0xFFFFFFFFL));
    }

    /**
     * Unit direction of pellet {@code pellet} of a pull aimed along {@code (dx, dy, dz)} with a cone
     * of half-angle {@code halfAngleDeg}, as {@code {x, y, z}}. Zero spread (or a degenerate aim)
     * returns the normalised aim exactly.
     */
    public static double[] direction(double dx, double dy, double dz, double halfAngleDeg, long seed, int pellet) {
        double len = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (len < 1e-9) return new double[] {0, 0, 0};
        dx /= len; dy /= len; dz /= len;
        if (!(halfAngleDeg > 0)) return new double[] {dx, dy, dz};

        long a = mix(seed ^ mix(pellet * 2L + 1));
        long b = mix(a);
        double coneAngle = unit(a) * 2.0 * Math.PI;
        double coneRadius = Math.toRadians(Math.sqrt(unit(b)) * halfAngleDeg);

        // side = dir x UP (fallback dir x RIGHT when the shot is vertical), lift = side x dir.
        double sx = -dz, sy = 0, sz = dx;                      // dir x (0,1,0)
        double sl = Math.sqrt(sx * sx + sz * sz);
        if (sl < 1e-6) { sx = 0; sy = dz; sz = -dy; sl = Math.sqrt(sy * sy + sz * sz); }  // dir x (1,0,0)
        sx /= sl; sy /= sl; sz /= sl;
        double lx = sy * dz - sz * dy, ly = sz * dx - sx * dz, lz = sx * dy - sy * dx;
        double ll = Math.sqrt(lx * lx + ly * ly + lz * lz);
        lx /= ll; ly /= ll; lz /= ll;

        double ca = Math.cos(coneAngle), sa = Math.sin(coneAngle);
        double ax = sx * ca + lx * sa, ay = sy * ca + ly * sa, az = sz * ca + lz * sa;   // rotation axis, unit

        // Rodrigues: v cos r + (k x v) sin r + k (k.v)(1 - cos r); k is perpendicular to v, so k.v = 0.
        double cr = Math.cos(coneRadius), sr = Math.sin(coneRadius);
        double kx = ay * dz - az * dy, ky = az * dx - ax * dz, kz = ax * dy - ay * dx;
        double rx = dx * cr + kx * sr, ry = dy * cr + ky * sr, rz = dz * cr + kz * sr;
        double rl = Math.sqrt(rx * rx + ry * ry + rz * rz);
        return new double[] {rx / rl, ry / rl, rz / rl};
    }
}
