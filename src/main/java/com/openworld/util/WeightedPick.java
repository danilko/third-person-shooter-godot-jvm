package com.openworld.util;

/**
 * Engine-free weighted random selection (traffic junction turning, PLAN.md roads-v2 Phase 1).
 *
 * <p>{@link com.openworld.world.VehicleRoute#pickNextRoute} feeds it the parsed
 * {@code next_weights} baked next to {@code next_routes} (straight-biased turn choice at a
 * junction), and {@link com.openworld.ai.vehicle.VehicleAIController} feeds it straightness
 * scores for the legacy {@code LaneGraph} fallback. Pure static functions so the pick logic is
 * unit-testable without the engine (same convention as the {@code com.openworld.net} codecs).
 */
public final class WeightedPick {

    private WeightedPick() {}

    /**
     * Index in {@code [0, n)} chosen by {@code weights}, driven by one uniform random draw
     * {@code r} in {@code [0, 1)}. Degrades to a uniform pick when {@code weights} is null,
     * length-mismatched, or sums to nothing — a candidate list must never become unreachable
     * because its baked weights are missing or malformed. Returns -1 only for {@code n <= 0}.
     */
    public static int pick(int n, float[] weights, double r) {
        if (n <= 0) return -1;
        r = Math.min(Math.max(r, 0.0), Math.nextDown(1.0));
        if (weights == null || weights.length != n) return (int) (r * n);
        double total = 0;
        for (float w : weights) total += Math.max(0f, w);
        if (total <= 0) return (int) (r * n);
        double target = r * total;
        double acc = 0;
        for (int i = 0; i < n; i++) {
            acc += Math.max(0f, weights[i]);
            if (target < acc) return i;
        }
        return n - 1;   // float round-off on the last bucket
    }

    /**
     * Parse a baked {@code "0.6,0.2,0.2"} weight list (the {@code next_weights} meta).
     * Null/blank input or any unparsable entry returns null — meaning "uniform" to
     * {@link #pick}, never an exception at spawn time from a bad bake.
     */
    public static float[] parseWeights(String csv) {
        if (csv == null || csv.isBlank()) return null;
        String[] parts = csv.split(",");
        float[] out = new float[parts.length];
        for (int i = 0; i < parts.length; i++) {
            try {
                out[i] = Float.parseFloat(parts[i].trim());
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return out;
    }
}
