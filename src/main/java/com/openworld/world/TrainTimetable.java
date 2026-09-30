package com.openworld.world;

/**
 * Where a train set is on its track at a given moment (PLAN.md "NEXT" piece 5, user 2026-09-29: "running trains, one
 * or two sets per line") — engine-free, so it is unit-tested ({@code TrainTimetableTest}) and every peer derives the
 * same train from the same clock with NO network message (the {@link SignalTiming} rule).
 *
 * <p>A set SHUTTLES on one track (a chain of rail lanes from one end to the other): it dwells at the first stop,
 * runs to the next with a trapezoid speed profile (accelerate at {@link #ACCEL}, cruise at the leg's speed cap, brake
 * at {@link #DECEL} to stop with its centre at the platform's centre), dwells {@link #DWELL} s with its doors open,
 * and so on to the last stop, where it dwells {@link #TERMINAL_DWELL} s and runs back through every stop to the
 * first. One track carries one set, so two sets on a line (one on each track) can never meet.
 *
 * <p>Arclengths ({@code s}) are the train's CENTRE along the track, from the track's start. A leg's speed cap is the
 * slowest cap anywhere between its two stops (the lane speed limit, and a curve's comfort limit) — a simplification a
 * stage-1 train can afford: it never brakes mid-leg.
 */
public final class TrainTimetable {

    /** m/s² a set accelerates and brakes at (a commuter EMU: ~0.9-1.0). */
    public static final double ACCEL = 0.9, DECEL = 0.9;
    /** s the doors stand open at a station, and at a terminus (the driver changes ends). */
    public static final double DWELL = 25.0, TERMINAL_DWELL = 45.0;

    /** A piece of the cycle: a dwell (s0 == s1) or a run from s0 to s1. */
    public record Leg(double t0, double t1, double s0, double s1, double vmax, boolean dwell, int stop) { }

    /** The set at one moment: its centre's arclength, signed speed (+ out, - back), whether it stands at a platform
     *  with its doors open, the stop it stands at (or last left), and the seconds until it next moves (0 while
     *  moving). */
    public record State(double s, double v, boolean dwell, int stop, double untilDepart) {
        public int dir() { return v < 0 ? -1 : 1; }
    }

    private final Leg[] legs;
    private final double period;

    /**
     * @param stops  the stops' arclengths, ascending (at least two)
     * @param capOf  the speed cap (m/s) of the leg between stop i and i+1, per i (length stops - 1)
     */
    public TrainTimetable(double[] stops, double[] capOf) {
        if (stops.length < 2) throw new IllegalArgumentException("a train needs two stops");
        int n = stops.length;
        java.util.List<Leg> out = new java.util.ArrayList<>();
        double t = 0.0;
        // out: dwell at stop 0 (a terminus), run 0 -> 1, dwell, ..., run to n-1; back: dwell at n-1, run to n-2, ...
        int[] order = new int[2 * n - 2];
        for (int i = 0; i < n; i++) order[i] = i;
        for (int i = n - 2; i >= 1; i--) order[2 * n - 2 - i] = i;
        for (int k = 0; k < order.length; k++) {
            int a = order[k], b = order[(k + 1) % order.length];
            double dw = (a == 0 || a == n - 1) ? TERMINAL_DWELL : DWELL;
            out.add(new Leg(t, t + dw, stops[a], stops[a], 0.0, true, a));
            t += dw;
            double cap = capOf[Math.min(a, b)];
            double d = Math.abs(stops[b] - stops[a]);
            double rt = runTime(d, cap);
            out.add(new Leg(t, t + rt, stops[a], stops[b], cap, false, a));
            t += rt;
        }
        legs = out.toArray(new Leg[0]);
        period = t;
    }

    public double period() { return period; }

    public Leg[] legs() { return legs.clone(); }

    /** Time to cover {@code d} m from rest to rest at cap {@code v} (trapezoid, or a triangle if too short). */
    public static double runTime(double d, double v) {
        if (d <= 0.0) return 0.0;
        v = Math.max(1.0, v);
        double da = v * v / (2 * ACCEL), db = v * v / (2 * DECEL);
        if (d >= da + db) return v / ACCEL + v / DECEL + (d - da - db) / v;
        double vp = Math.sqrt(2.0 * d * ACCEL * DECEL / (ACCEL + DECEL));
        return vp / ACCEL + vp / DECEL;
    }

    /** Distance covered {@code tau} s into a rest-to-rest run of {@code d} m at cap {@code v}. */
    public static double runDistance(double d, double v, double tau) {
        v = Math.max(1.0, v);
        double da = v * v / (2 * ACCEL), db = v * v / (2 * DECEL);
        double vp = v;
        if (d < da + db) {
            vp = Math.sqrt(2.0 * d * ACCEL * DECEL / (ACCEL + DECEL));
            da = vp * vp / (2 * ACCEL);
            db = vp * vp / (2 * DECEL);
        }
        double ta = vp / ACCEL, tc = (d - da - db) / vp, total = ta + tc + vp / DECEL;
        if (tau <= 0.0) return 0.0;
        if (tau >= total) return d;
        if (tau < ta) return 0.5 * ACCEL * tau * tau;
        if (tau < ta + tc) return da + vp * (tau - ta);
        double tr = total - tau;
        return d - 0.5 * DECEL * tr * tr;
    }

    /** Speed {@code tau} s into the same run. */
    public static double runSpeed(double d, double v, double tau) {
        v = Math.max(1.0, v);
        double da = v * v / (2 * ACCEL), db = v * v / (2 * DECEL);
        double vp = v;
        if (d < da + db) vp = Math.sqrt(2.0 * d * ACCEL * DECEL / (ACCEL + DECEL));
        double ta = vp / ACCEL, total = runTime(d, v);
        if (tau <= 0.0 || tau >= total) return 0.0;
        if (tau < ta) return ACCEL * tau;
        if (total - tau < vp / DECEL) return DECEL * (total - tau);
        return vp;
    }

    /** The set at time {@code t} (s since any fixed epoch; the cycle repeats every {@link #period()}). */
    public State at(double t) {
        double tt = ((t % period) + period) % period;
        int lo = 0, hi = legs.length - 1;
        while (lo < hi) {
            int mid = (lo + hi + 1) >>> 1;
            if (legs[mid].t0 <= tt) lo = mid; else hi = mid - 1;
        }
        Leg l = legs[lo];
        if (l.dwell) return new State(l.s0, 0.0, true, l.stop, l.t1 - tt);
        double d = Math.abs(l.s1 - l.s0);
        double sg = Math.signum(l.s1 - l.s0);
        double tau = tt - l.t0;
        return new State(l.s0 + sg * runDistance(d, l.vmax, tau), sg * runSpeed(d, l.vmax, tau), false, l.stop, 0.0);
    }

    /**
     * Is a level crossing at arclength {@code c} closed at time {@code t} for a set {@code length} m long? Closed
     * while the set overlaps it (+ {@code margin}), while it is moving TOWARD it within {@code warn} m of its front,
     * and in the last {@code prewarn} s of a dwell when its next run heads toward it within {@code warn} m.
     */
    public boolean crossingClosed(double c, double t, double length, double warn, double margin, double prewarn) {
        State st = at(t);
        double half = length / 2.0;
        if (Math.abs(c - st.s()) <= half + margin) return true;
        int dir;
        if (st.dwell()) {
            if (st.untilDepart() > prewarn) return false;
            dir = nextDir(t);
        } else {
            dir = st.dir();
        }
        double ahead = (c - st.s()) * dir;
        return ahead >= 0.0 && ahead <= half + warn;
    }

    /** The direction (+1 out, -1 back) of the next run after the dwell in progress at {@code t}. */
    public int nextDir(double t) {
        double tt = ((t % period) + period) % period;
        for (int k = 0; k < legs.length * 2; k++) {
            Leg l = legs[k % legs.length];
            double t1 = l.t1 + (k >= legs.length ? period : 0.0);
            if (t1 <= tt || l.dwell) continue;
            return l.s1 >= l.s0 ? 1 : -1;
        }
        return 1;
    }
}
