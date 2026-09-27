package com.openworld.world;

import java.util.zip.CRC32;

/**
 * The phase clock of a signalised junction (user, 2026-09-26: "enable both pedestrian + traffic light") —
 * engine-free, so it is unit-tested ({@code SignalTimingTest}) and every peer computes the same answer from the
 * same clock with no message.
 *
 * <p>A junction's arms are in {@code groups} phase groups (the arms facing each other move together:
 * {@code point_furniture.signal_plan}). The groups take turns: GREEN for {@code green} s, YELLOW (Japan's 黄) for
 * {@code yellow} s, then an ALL-RED clearance of {@code allRed} s before the next group's green. A PEDESTRIAN
 * crossing an arm walks while that arm's group is RED and another group is GREEN — the crosswalk parallel to the
 * moving traffic, as in Japan — its green man FLASHING for the last {@link #PED_FLASH} s of that green.
 *
 * <p>Each junction is offset in the cycle by a hash of its id, so a street is not a wave of simultaneous greens.
 * The clock is the SYSTEM clock (unix seconds): peers' clocks agree to well under a yellow, so a client's lamps
 * and the host's traffic agree without a message.
 */
public final class SignalTiming {

    public static final int GREEN = 0, YELLOW = 1, RED = 2;
    public static final int WALK = 0, FLASH = 1, STOP = 2;
    /** s at the end of a green that a pedestrian's green man flashes (Japan: 青点滅). */
    public static final double PED_FLASH = 4.0;

    private SignalTiming() {}

    public static double phaseLength(double green, double yellow, double allRed) {
        return green + yellow + allRed;
    }

    public static double cycle(int groups, double green, double yellow, double allRed) {
        return Math.max(1, groups) * phaseLength(green, yellow, allRed);
    }

    /** A stable per-junction offset into the cycle (s), from its id. */
    public static double offset(String junctionId, double cycle) {
        CRC32 c = new CRC32();
        c.update(junctionId.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return (c.getValue() % 100000L) / 100000.0 * cycle;
    }

    /** Which group holds the green phase at {@code t}, and how far into it (s): {group, within}. */
    public static double[] active(int groups, double t, double green, double yellow, double allRed) {
        double p = phaseLength(green, yellow, allRed);
        double cyc = cycle(groups, green, yellow, allRed);
        double tt = ((t % cyc) + cyc) % cyc;
        int g = (int) Math.floor(tt / p);
        return new double[]{Math.min(g, Math.max(1, groups) - 1), tt - g * p};
    }

    /** The vehicle light of an arm in {@code group}. */
    public static int vehicle(int groups, int group, double t, double green, double yellow, double allRed) {
        double[] a = active(groups, t, green, yellow, allRed);
        if ((int) a[0] != group) return RED;
        if (a[1] < green) return GREEN;
        if (a[1] < green + yellow) return YELLOW;
        return RED;
    }

    /** The pedestrian light of the crosswalk across an arm in {@code group}. */
    public static int pedestrian(int groups, int group, double t, double green, double yellow, double allRed) {
        double[] a = active(groups, t, green, yellow, allRed);
        if (groups <= 1) {
            // one group: the crosswalk walks during the all-red clearance and the yellow is its flash
            if (a[1] >= green + yellow) return WALK;
            return STOP;
        }
        if ((int) a[0] == group || a[1] >= green) return STOP;
        return a[1] >= green - PED_FLASH ? FLASH : WALK;
    }
}
