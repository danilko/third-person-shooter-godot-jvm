package com.openworld.world;

/**
 * Where a train set is on its track at a given moment (PLAN.md "NEXT" piece 5, user 2026-09-29: "running trains, one
 * or two sets per line") -- engine-free, so it is unit-tested ({@code TrainTimetableTest}) and every peer derives the
 * same train from the same clock with NO network message (the {@link SignalTiming} rule).
 *
 * <p>Two shapes:
 * <ul>
 *   <li><b>A CIRCUIT</b> ({@link #circuit}, the double-track line, user 2026-10-02): the set runs the whole of one
 *       track, stopping at every stop, then the whole of the next, and back to the first -- keep-left double-track
 *       running, each track one direction. At a terminus it dwells {@link #TERMINAL_DWELL}, the first half on the
 *       track it arrived on and the second half on the one it leaves on: the change of track is instantaneous, in
 *       the middle of the stop (the cheap turn, user decision; a rider moves with their car).</li>
 *   <li><b>A SHUTTLE</b> ({@code new TrainTimetable(stops, caps)}, a single track): out to the last stop and back
 *       through every stop on the same track.</li>
 * </ul>
 * The run between two stops is a trapezoid (accelerate at {@link #ACCEL}, cruise at the leg's speed cap, brake at
 * {@link #DECEL} to stop with its centre at the platform's centre). Arclengths ({@code s}) are the train's centre along
 * its track. Several sets share a circuit by running the same timetable at different phases, so they never meet as
 * long as they are further apart in time than one leg.
 */
public final class TrainTimetable {

    /** m/s² a set accelerates and brakes at (a commuter EMU: ~0.9-1.0). */
    public static final double ACCEL = 0.9, DECEL = 0.9;
    /** s the doors stand open at a station, and at a terminus (the driver changes ends). */
    public static final double DWELL = 25.0, TERMINAL_DWELL = 45.0;

    /** A piece of the cycle: a dwell (s0 == s1) or a run from s0 to s1, on track {@code track}. */
    public record Leg(double t0, double t1, double s0, double s1, double vmax, boolean dwell, int stop, int track) { }

    /** The set at one moment: its centre's arclength on {@code track}, signed speed (+ along the track's arclength),
     *  whether it stands at a platform, the stop it stands at (or last left), and the seconds until it next moves
     *  (0 while moving). */
    public record State(double s, double v, boolean dwell, int stop, double untilDepart, int track) {
        public int dir() { return v < 0 ? -1 : 1; }
    }

    /** A call at a stop: arrival and departure (absolute), the stop and track, and the way it leaves (+1 / -1). */
    public record Call(double arrive, double depart, int stop, int dir, int track) { }

    private final Leg[] legs;
    private final double period;
    private final boolean circuit;
    private final int[] stopsPerTrack;

    /**
     * A SHUTTLE on one track.
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
            out.add(new Leg(t, t + dw, stops[a], stops[a], 0.0, true, a, 0));
            t += dw;
            double cap = capOf[Math.min(a, b)];
            double d = Math.abs(stops[b] - stops[a]);
            double rt = runTime(d, cap);
            out.add(new Leg(t, t + rt, stops[a], stops[b], cap, false, a, 0));
            t += rt;
        }
        legs = out.toArray(new Leg[0]);
        period = t;
        circuit = false;
        stopsPerTrack = new int[]{n};
    }

    private TrainTimetable(Leg[] legs, double period, int[] stopsPerTrack) {
        this.legs = legs;
        this.period = period;
        this.circuit = true;
        this.stopsPerTrack = stopsPerTrack;
    }

    /**
     * A CIRCUIT over several tracks, each run end to end in order and the last back to the first.
     * @param stops  per track, its stops' arclengths ascending along that track (at least two each)
     * @param caps   per track, the cap (m/s) of each leg between its stops (length stops - 1)
     */
    public static TrainTimetable circuit(double[][] stops, double[][] caps) {
        java.util.List<Leg> out = new java.util.ArrayList<>();
        int[] per = new int[stops.length];
        double t = 0.0;
        for (int tr = 0; tr < stops.length; tr++) {
            double[] st = stops[tr];
            if (st.length < 2) throw new IllegalArgumentException("each track of a circuit needs two stops");
            per[tr] = st.length;
            for (int i = 0; i < st.length; i++) {
                boolean terminal = i == 0 || i == st.length - 1;
                double dw = terminal ? TERMINAL_DWELL / 2.0 : DWELL;
                out.add(new Leg(t, t + dw, st[i], st[i], 0.0, true, i, tr));
                t += dw;
                if (i + 1 < st.length) {
                    double cap = caps[tr][i];
                    double rt = runTime(st[i + 1] - st[i], cap);
                    out.add(new Leg(t, t + rt, st[i], st[i + 1], cap, false, i, tr));
                    t += rt;
                }
            }
        }
        return new TrainTimetable(out.toArray(new Leg[0]), t, per);
    }

    public double period() { return period; }

    public boolean isCircuit() { return circuit; }

    public int trackCount() { return stopsPerTrack.length; }

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

    private int legAt(double tt) {
        int lo = 0, hi = legs.length - 1;
        while (lo < hi) {
            int mid = (lo + hi + 1) >>> 1;
            if (legs[mid].t0 <= tt) lo = mid; else hi = mid - 1;
        }
        return lo;
    }

    private double wrap(double t) { return ((t % period) + period) % period; }

    /** The set at time {@code t} (s since any fixed epoch; the cycle repeats every {@link #period()}). */
    public State at(double t) {
        double tt = wrap(t);
        int k = legAt(tt);
        Leg l = legs[k];
        if (l.dwell) {
            // a circuit's terminus is two dwells back to back: the train departs at the end of the SECOND
            double until = l.t1 - tt;
            Leg nx = legs[(k + 1) % legs.length];
            if (nx.dwell) until += nx.t1 - nx.t0;
            return new State(l.s0, 0.0, true, l.stop, until, l.track);
        }
        double d = Math.abs(l.s1 - l.s0);
        double sg = Math.signum(l.s1 - l.s0);
        double tau = tt - l.t0;
        return new State(l.s0 + sg * runDistance(d, l.vmax, tau), sg * runSpeed(d, l.vmax, tau), false, l.stop, 0.0,
                l.track);
    }

    /** The first moving leg after the leg at {@code k} (wrapping). */
    private Leg nextRun(int k) {
        for (int i = 1; i <= legs.length; i++) {
            Leg l = legs[(k + i) % legs.length];
            if (!l.dwell) return l;
        }
        return legs[k];
    }

    /** Shuttle: is a level crossing at arclength {@code c} (track 0) closed at {@code t}? See the track overload. */
    public boolean crossingClosed(double c, double t, double length, double warn, double margin, double prewarn) {
        return crossingClosed(0, c, t, length, warn, margin, prewarn);
    }

    /**
     * Is a level crossing at arclength {@code c} on track {@code track} closed at time {@code t} for a set {@code length}
     * m long? Closed while the set overlaps it (+ {@code margin}), while it runs TOWARD it within {@code warn} m of its
     * front, and in the last {@code prewarn} s of a dwell when its next run heads toward it within {@code warn} m. A set
     * on another track of a circuit closes it only once it is standing on this one.
     */
    public boolean crossingClosed(int track, double c, double t, double length, double warn, double margin,
                                  double prewarn) {
        double tt = wrap(t);
        int k = legAt(tt);
        Leg l = legs[k];
        State st = at(t);
        double half = length / 2.0;
        if (l.track != track) return false;
        if (Math.abs(c - st.s()) <= half + margin) return true;
        int dir;
        if (st.dwell()) {
            if (st.untilDepart() > prewarn) return false;
            Leg nr = nextRun(k);
            if (nr.track != track) return false;
            dir = nr.s1 >= nr.s0 ? 1 : -1;
        } else {
            dir = st.dir();
        }
        double ahead = (c - st.s()) * dir;
        return ahead >= 0.0 && ahead <= half + warn;
    }

    /** The direction (+1 / -1 along its track) of the next run after the dwell in progress at {@code t}. */
    public int nextDir(double t) {
        Leg nr = nextRun(legAt(wrap(t)));
        return nr.s1 >= nr.s0 ? 1 : -1;
    }

    /**
     * When a set put out of service at time {@code t} comes back (PLAN.md NEXT item 11, user 2026-10-02: "destructible,
     * and re-spawn in next station"): the START of the first dwell beginning at least {@code minGap} s after {@code t}
     * -- it reappears standing at that platform with its doors open. Absolute time (same epoch as {@code t}).
     */
    public double nextDwellStart(double t, double minGap) {
        double base = Math.floor(t / period) * period;
        double earliest = t + minGap;
        for (int cycle = 0; cycle < 3; cycle++) {
            double c0 = base + cycle * period;
            for (Leg l : legs) {
                if (l.dwell && c0 + l.t0 >= earliest) return c0 + l.t0;
            }
        }
        return earliest;
    }

    /** The stop index of the dwell that begins at absolute time {@code t} (from {@link #nextDwellStart}), or -1. */
    public int stopAt(double t) {
        State st = at(t + 1e-6);
        return st.dwell() ? st.stop() : -1;
    }

    public int stopCount() { return stopsPerTrack[0]; }

    public int stopCount(int track) { return stopsPerTrack[Math.max(0, Math.min(stopsPerTrack.length - 1, track))]; }

    /** Shuttle: the stop a train runs toward when it leaves `dir` (+1 the last stop, -1 the first). */
    public int terminalFor(int dir) { return dir > 0 ? stopCount() - 1 : 0; }

    /** Where a call's train goes (行き): the stop index, on {@link Call#track}, of its terminus. On a circuit that is the
     *  last stop of the track it leaves on; at that very terminus it is the far end of the next track. */
    public int destinationStop(Call c) {
        if (!circuit) return terminalFor(c.dir());
        return stopCount(c.track()) - 1;
    }

    /** The track a call's train leaves on (a circuit's terminus hands the train to the next track). */
    public int departureTrack(Call c) {
        if (!circuit || c.stop() < stopCount(c.track()) - 1) return c.track();
        return (c.track() + 1) % trackCount();
    }

    /** Shuttle: calls at {@code stop} of track 0 (-1 = any stop). */
    public java.util.List<Call> calls(double t, int stop, int max) { return calls(t, 0, stop, max); }

    /**
     * The calls after time {@code t} (one in progress included), up to {@code max}, at stop {@code stop} (-1 = any)
     * of track {@code track} (-1 = any). A circuit's terminus (two dwells back to back) is ONE call, on the track
     * the train ARRIVES on, departing at the end of the second dwell.
     */
    public java.util.List<Call> calls(double t, int track, int stop, int max) {
        java.util.List<Call> out = new java.util.ArrayList<>();
        double base = Math.floor(t / period) * period;
        for (int cycle = 0; cycle < 3 && out.size() < max; cycle++) {
            double c0 = base + cycle * period;
            for (int k = 0; k < legs.length && out.size() < max; k++) {
                Leg l = legs[k];
                if (!l.dwell) continue;
                Leg prev = legs[(k - 1 + legs.length) % legs.length];
                if (circuit && prev.dwell) continue;           // the second half of a terminus belongs to the first
                if ((stop >= 0 && l.stop != stop) || (track >= 0 && l.track != track)) continue;
                double depart = c0 + l.t1;
                Leg nx = legs[(k + 1) % legs.length];
                if (nx.dwell) depart += nx.t1 - nx.t0;
                if (depart <= t) continue;                     // already left
                Leg nr = nextRun(k);
                out.add(new Call(c0 + l.t0, depart, l.stop, nr.s1 >= nr.s0 ? 1 : -1, l.track));
            }
        }
        return out;
    }

    /** The train's next (or current) call. */
    public Call nextCall(double t) {
        java.util.List<Call> c = calls(t, -1, -1, 1);
        return c.isEmpty() ? null : c.get(0);
    }
}
