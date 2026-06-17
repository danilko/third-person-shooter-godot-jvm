package com.openworld.net;

/**
 * Near-time snapshot smoothing for remote (non-authority) bodies. Renders the body at ~present
 * time by dead-reckoning the most recent authoritative snapshot forward by local elapsed time and
 * easing the rendered transform toward that projection. Replaces the old "delayed entity
 * interpolation" (render ~100 ms in the past, bracket two buffered samples, advance a drifting
 * render clock that caught up at half real-time): under two-instance timing jitter that clock fell
 * behind and crawled to catch up over <em>seconds</em>, and during a stall it kept dead-reckoning
 * forward (overshoot) before scrolling back — the "1–2 s delay / moves too far then snaps back"
 * symptom. There is no render-clock here, so there is nothing to fall behind.
 *
 * <h2>Model</h2>
 * On each snapshot we store it as {@code latest} and reset {@code secondsSinceLatest} to 0. Each
 * frame:
 * <pre>
 *   secondsSinceLatest += delta
 *   target   = latest.pos + latest.vel * min(secondsSinceLatest, maxProjectionSeconds)
 *   predicted = rendered + latest.vel * delta          // dead-reckon: no steady-state lag
 *   rendered  = predicted + (target - predicted) * (1 - e^(-gain*delta))   // ease residual
 * </pre>
 * Because both {@code target} and {@code predicted} advance at the body's own velocity, steady-state
 * tracking error is ~0 (no rubber-band lag). When the body stops, the next snapshot reports zero
 * velocity and {@code target} stops; the small forward over-projection (≤ vel·oneInterval) eases out
 * in a few frames instead of seconds. A gap simply freezes the projection at the cap until the next
 * snapshot re-targets. An error larger than {@code snapDistance} (spawn / teleport) snaps instantly.
 *
 * <p>Engine-free (operates on {@link Vec3}/primitives, no Godot types) so the smoothing is
 * unit-testable headless. The per-sample wall-clock timestamp is used only to drop reordered
 * snapshots — the projection is driven by local frame delta, so cross-machine clock offset and a
 * sub-60 Hz / frozen-tick sender are all harmless.
 */
public final class SnapshotInterpolator {

    /** Interpolated render state for the current frame. */
    public record Output(Vec3 position, Vec3 velocity, double yaw, Vec3 aim) { }

    /** Cap on forward dead-reckoning when snapshots stop arriving — bounds runaway during a gap. */
    private final double maxProjectionSeconds;
    /** Exponential gain (1/s) easing the rendered position toward the projected target. ~12 ⇒ ~83 ms time constant. */
    private final double correctionGain;
    /** Positional error above which we snap instead of easing — a real teleport/spawn, not jitter. */
    private final double snapDistance;
    /** Bounded yaw follow rate (rad/s) — well above any real turn, so normal facing tracks 1:1 and only a flip eases. */
    private final double maxYawRate;

    // ── Latest authoritative snapshot ─────────────────────────────────────────
    private boolean haveLatest;
    private double  latestTimeSeconds;   // sender wall-clock — ordering/stale-drop only
    private Vec3    latestPos;
    private Vec3    latestVel;
    private double  latestYaw;
    private Vec3    latestAim;
    private double  secondsSinceLatest;

    // ── Smoothed render state ─────────────────────────────────────────────────
    private boolean haveRender;
    private Vec3    renderedPos;
    private double  renderedYaw;
    private Vec3    renderedAim;

    public SnapshotInterpolator(double maxProjectionSeconds, double correctionGain,
            double snapDistance, double maxYawRate) {
        this.maxProjectionSeconds = maxProjectionSeconds;
        this.correctionGain = correctionGain;
        this.snapDistance = snapDistance;
        this.maxYawRate = maxYawRate;
    }

    /** Default near-time tuning: project ≤150 ms during a gap, ~83 ms ease time constant, snap past 5 m. */
    public SnapshotInterpolator() {
        this(0.15, 12.0, 5.0, 12.0);
    }

    /**
     * Insert a freshly-decoded snapshot tagged with the sender's (unwrapped, monotonic) wall-clock.
     * Stale/reordered samples are dropped by timestamp; the accepted one becomes the new projection
     * anchor and resets the forward-projection clock.
     */
    public void addSample(long tick, double timeSeconds, Vec3 position, Vec3 velocity, double yaw, Vec3 aim) {
        if (haveLatest && timeSeconds <= latestTimeSeconds) return;
        haveLatest = true;
        latestTimeSeconds = timeSeconds;
        latestPos = position;
        latestVel = velocity;
        latestYaw = yaw;
        latestAim = aim;
        secondsSinceLatest = 0.0;
    }

    public boolean hasData() { return haveLatest; }

    /** Resets all state — used when a body's controller is (re)attached. */
    public void reset() {
        haveLatest = false;
        haveRender = false;
        secondsSinceLatest = 0.0;
        renderedPos = null;
        renderedAim = null;
        renderedYaw = 0.0;
    }

    /**
     * Advance by {@code delta} (real seconds) and return the smoothed near-time transform, or
     * {@code null} if no snapshot has arrived yet.
     */
    public Output advance(double delta) {
        if (!haveLatest) return null;
        secondsSinceLatest += delta;

        double proj = Math.min(secondsSinceLatest, maxProjectionSeconds);
        Vec3 target = latestPos.plus(latestVel.scaled(proj));

        if (!haveRender) {
            haveRender = true;
            renderedPos = target;
            renderedYaw = latestYaw;
            renderedAim = latestAim;
            return new Output(renderedPos, latestVel, renderedYaw, renderedAim);
        }

        // Dead-reckon by the body's own velocity (keeps up with motion → no steady-state lag), then
        // ease the residual toward the projected target. A large error is a teleport/spawn → snap.
        Vec3 predicted = renderedPos.plus(latestVel.scaled(delta));
        Vec3 error = new Vec3(target.x() - predicted.x(), target.y() - predicted.y(), target.z() - predicted.z());
        if (error.length() > snapDistance) {
            renderedPos = target;
        } else {
            double ease = 1.0 - Math.exp(-correctionGain * delta);
            renderedPos = predicted.plus(error.scaled(ease));
        }

        // Yaw: bounded shortest-path follow. Aim: same exponential ease as position (no velocity).
        double yawErr = lerpAngle(renderedYaw, latestYaw, 1.0) - renderedYaw;
        double yawStep = maxYawRate * delta;
        renderedYaw += Math.max(-yawStep, Math.min(yawStep, yawErr));

        double aimEase = 1.0 - Math.exp(-correctionGain * delta);
        renderedAim = renderedAim.plus(new Vec3(latestAim.x() - renderedAim.x(),
                latestAim.y() - renderedAim.y(), latestAim.z() - renderedAim.z()).scaled(aimEase));

        return new Output(renderedPos, latestVel, renderedYaw, renderedAim);
    }

    /** Shortest-path angular interpolation (radians) — mirrors GD.lerpAngle so facing never spins the long way. */
    static double lerpAngle(double a, double b, double t) {
        double d = b - a;
        while (d >  Math.PI) d -= 2 * Math.PI;
        while (d < -Math.PI) d += 2 * Math.PI;
        return a + d * t;
    }
}
