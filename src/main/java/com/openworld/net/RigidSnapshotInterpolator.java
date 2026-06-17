package com.openworld.net;

/**
 * Near-time snapshot smoothing for a remote (non-authority) rigid body — the vehicle
 * counterpart of {@link SnapshotInterpolator}, replacing its yaw-only facing with a full
 * quaternion orientation (vehicles roll and pitch) dead-reckoned by angular velocity.
 *
 * Same model as SnapshotInterpolator (see its class doc for the rationale): on each snapshot
 * store it as {@code latest} and reset the projection clock; each frame project the latest
 * sample forward by local elapsed time (capped), dead-reckon the rendered state by the body's
 * own velocities, and ease the residual toward the projection. Steady-state tracking error is
 * ~0; a gap freezes the projection at the cap; an error past {@code snapDistance} /
 * {@code snapAngleRadians} (spawn/teleport/flip) snaps instantly.
 *
 * Engine-free ({@link Vec3}/{@link Quat}/primitives only) so it is unit-tested headless in
 * {@code RigidSnapshotInterpolatorTest}, like every class in this package.
 */
public final class RigidSnapshotInterpolator {

    /** Smoothed render state for the current frame. */
    public record Output(Vec3 position, Quat orientation, Vec3 linearVelocity, Vec3 angularVelocity) { }

    /** Latest raw authoritative sample — exposed for authority handback (seed the live body's velocities so it coasts). */
    public record Sample(Vec3 position, Quat orientation, Vec3 linearVelocity, Vec3 angularVelocity) { }

    /** Cap on forward dead-reckoning when snapshots stop arriving — bounds runaway during a gap. */
    private final double maxProjectionSeconds;
    /** Exponential gain (1/s) easing the rendered state toward the projected target. */
    private final double correctionGain;
    /** Positional error above which we snap instead of easing — a real teleport/spawn, not jitter. */
    private final double snapDistance;
    /** Orientation error (radians) above which we snap — a reset/flip, not motion. */
    private final double snapAngleRadians;

    // ── Latest authoritative snapshot ─────────────────────────────────────────
    private boolean haveLatest;
    private double  latestTimeSeconds;   // sender wall-clock — ordering/stale-drop only
    private Vec3    latestPos;
    private Quat    latestQuat;
    private Vec3    latestLinVel;
    private Vec3    latestAngVel;
    private double  secondsSinceLatest;

    // ── Smoothed render state ─────────────────────────────────────────────────
    private boolean haveRender;
    private Vec3    renderedPos;
    private Quat    renderedQuat;

    public RigidSnapshotInterpolator(double maxProjectionSeconds, double correctionGain,
            double snapDistance, double snapAngleRadians) {
        this.maxProjectionSeconds = maxProjectionSeconds;
        this.correctionGain = correctionGain;
        this.snapDistance = snapDistance;
        this.snapAngleRadians = snapAngleRadians;
    }

    /** Default near-time tuning: matches SnapshotInterpolator's position model; snap past a half-turn flip. */
    public RigidSnapshotInterpolator() {
        this(0.15, 12.0, 5.0, Math.PI / 2);
    }

    /**
     * Insert a freshly-decoded snapshot tagged with the sender's (unwrapped, monotonic) wall-clock.
     * Stale/reordered samples are dropped by timestamp; the accepted one becomes the new projection
     * anchor and resets the forward-projection clock. The orientation is normalized on entry so a
     * wire-quantized quaternion can't accumulate drift.
     */
    public void addSample(double timeSeconds, Vec3 position, Quat orientation,
            Vec3 linearVelocity, Vec3 angularVelocity) {
        if (haveLatest && timeSeconds <= latestTimeSeconds) return;
        haveLatest = true;
        latestTimeSeconds = timeSeconds;
        latestPos = position;
        latestQuat = orientation.normalized();
        latestLinVel = linearVelocity;
        latestAngVel = angularVelocity;
        secondsSinceLatest = 0.0;
    }

    public boolean hasData() { return haveLatest; }

    /** The most recent raw sample, or null before the first one — see {@link Sample}. */
    public Sample latestSample() {
        if (!haveLatest) return null;
        return new Sample(latestPos, latestQuat, latestLinVel, latestAngVel);
    }

    /** Resets all state — used when a body's authority flips back and forth. */
    public void reset() {
        haveLatest = false;
        haveRender = false;
        secondsSinceLatest = 0.0;
        renderedPos = null;
        renderedQuat = null;
    }

    /**
     * Advance by {@code delta} (real seconds) and return the smoothed near-time transform, or
     * {@code null} if no snapshot has arrived yet.
     */
    public Output advance(double delta) {
        if (!haveLatest) return null;
        secondsSinceLatest += delta;

        double proj = Math.min(secondsSinceLatest, maxProjectionSeconds);
        Vec3 targetPos = latestPos.plus(latestLinVel.scaled(proj));
        Quat targetQuat = latestQuat.integrate(latestAngVel, proj);

        if (!haveRender) {
            haveRender = true;
            renderedPos = targetPos;
            renderedQuat = targetQuat;
            return new Output(renderedPos, renderedQuat, latestLinVel, latestAngVel);
        }

        // Dead-reckon by the body's own velocities (keeps up with motion → no steady-state
        // lag), then ease the residual toward the projected target. A large error is a
        // teleport/spawn/reset → snap.
        Vec3 predicted = renderedPos.plus(latestLinVel.scaled(delta));
        Vec3 error = new Vec3(targetPos.x() - predicted.x(), targetPos.y() - predicted.y(),
                targetPos.z() - predicted.z());
        double ease = 1.0 - Math.exp(-correctionGain * delta);
        if (error.length() > snapDistance) {
            renderedPos = targetPos;
        } else {
            renderedPos = predicted.plus(error.scaled(ease));
        }

        Quat predictedQuat = renderedQuat.integrate(latestAngVel, delta);
        if (predictedQuat.angleTo(targetQuat) > snapAngleRadians) {
            renderedQuat = targetQuat;
        } else {
            renderedQuat = predictedQuat.slerp(targetQuat, ease);
        }

        return new Output(renderedPos, renderedQuat, latestLinVel, latestAngVel);
    }
}
