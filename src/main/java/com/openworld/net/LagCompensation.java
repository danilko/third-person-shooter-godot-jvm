package com.openworld.net;

/**
 * Engine-free rules for host-side lag compensation of hitscan (PLAN.md N5). A client renders a remote
 * body from the host's snapshots: the snapshot's own host timestamp plus how long it has been
 * dead-reckoned forward ({@link SnapshotInterpolator}). That sum is the host time the client was LOOKING
 * AT when it pulled the trigger, and it rides the shot ({@code MSG_SHOT viewTimeMs}). The host looks up
 * where each body was at that time in its own recent history, moves the hitboxes there for the one
 * trace, and puts them back.
 *
 * <p>Times are the host's truncated {@code Time.getTicksMsec()} as an {@code int}, compared with
 * two's-complement subtraction so a wrap after ~24.8 days is harmless (the {@link TimestampUnwrapper}
 * rule).
 */
public final class LagCompensation {

    private LagCompensation() { }

    /**
     * Longest the host will rewind (Source's {@code sv_maxunlag} is 1 s; 200 ms covers a LAN and a
     * fair internet link). The view time is the client's word, so this cap is also the whole of what a
     * forged one can buy.
     */
    public static final int MAX_REWIND_MS = 200;
    /** How much history each body keeps — comfortably past {@link #MAX_REWIND_MS}. */
    public static final int HISTORY_MS = 1000;

    /**
     * How many milliseconds before {@code hostNowMs} to resolve a shot the client saw at
     * {@code viewMs}: 0 for a view in the future (a clock the client cannot have), capped at
     * {@code maxRewindMs}.
     */
    public static int rewindMs(int hostNowMs, int viewMs, int maxRewindMs) {
        int age = hostNowMs - viewMs;   // wrap-safe
        if (age <= 0) return 0;
        return Math.min(age, maxRewindMs);
    }

    /** One body's recent root positions, a ring buffer keyed by host time. */
    public static final class History {
        private final int[] times;
        private final double[] xs, ys, zs;
        private int head;   // index of the newest sample
        private int size;

        public History(int capacity) {
            times = new int[capacity];
            xs = new double[capacity];
            ys = new double[capacity];
            zs = new double[capacity];
        }

        /** Default: a second of samples at 60 Hz, with headroom for a faster physics tick. */
        public History() { this(128); }

        public int size() { return size; }

        /** Appends a sample; a time not after the newest replaces the newest (two records in one tick). */
        public void record(int timeMs, double x, double y, double z) {
            if (size > 0 && timeMs - times[head] <= 0) {
                xs[head] = x; ys[head] = y; zs[head] = z;
                return;
            }
            head = (head + 1) % times.length;
            times[head] = timeMs; xs[head] = x; ys[head] = y; zs[head] = z;
            if (size < times.length) size++;
        }

        /**
         * Where the body was at {@code timeMs}: interpolated between the two samples around it, clamped
         * to the oldest and newest. {@code null} with no samples.
         */
        public Vec3 at(int timeMs) {
            if (size == 0) return null;
            if (timeMs - times[head] >= 0) return new Vec3(xs[head], ys[head], zs[head]);
            int newer = head;
            for (int n = 1; n < size; n++) {
                int older = (head - n + times.length) % times.length;
                if (timeMs - times[older] >= 0) {
                    int span = times[newer] - times[older];
                    double t = span <= 0 ? 1.0 : (double) (timeMs - times[older]) / span;
                    return new Vec3(xs[older] + (xs[newer] - xs[older]) * t,
                            ys[older] + (ys[newer] - ys[older]) * t,
                            zs[older] + (zs[newer] - zs[older]) * t);
                }
                newer = older;
            }
            return new Vec3(xs[newer], ys[newer], zs[newer]);   // older than the buffer: the oldest
        }
    }

    /**
     * Distance from point {@code p} to the segment {@code from + aim·[0, range]} ({@code aim} unit length) —
     * which bodies are near enough to the shot to be worth moving.
     */
    public static double distanceToSegment(Vec3 p, Vec3 from, Vec3 aim, double range) {
        double dx = p.x() - from.x(), dy = p.y() - from.y(), dz = p.z() - from.z();
        double t = Math.max(0.0, Math.min(range, dx * aim.x() + dy * aim.y() + dz * aim.z()));
        double cx = from.x() + aim.x() * t - p.x(), cy = from.y() + aim.y() * t - p.y(), cz = from.z() + aim.z() * t - p.z();
        return Math.sqrt(cx * cx + cy * cy + cz * cz);
    }
}
