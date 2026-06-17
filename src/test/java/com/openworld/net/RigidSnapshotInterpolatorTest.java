package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Regression guards for the rigid-body (vehicle) near-time smoothing — the same core
 * properties SnapshotInterpolatorTest guards for characters (constant-velocity tracking,
 * gap freeze, teleport snap, stale-sample drop), plus the quaternion orientation channel:
 * constant spin tracks the analytic rotation and a flip past the snap angle snaps.
 */
class RigidSnapshotInterpolatorTest {

    private static final double FRAME_DT = 1.0 / 60.0;
    private static final int    SNAP_EVERY_FRAMES = 2;   // ~30 Hz snapshot cadence
    private static final double VX = 8.0;                 // m/s along +X — vehicle speed

    private static Quat yaw(double angle) {
        return new Quat(0, Math.sin(angle / 2), 0, Math.cos(angle / 2));
    }

    @Test
    void noOutputBeforeFirstSample() {
        assertNull(new RigidSnapshotInterpolator().advance(FRAME_DT));
        assertNull(new RigidSnapshotInterpolator().latestSample());
    }

    @Test
    void constantVelocityTracksTruthWithoutAccumulatingDelay() {
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        Vec3 vel = new Vec3(VX, 0, 0);
        double prevX = Double.NaN;

        for (int frame = 0; frame <= 600; frame++) {
            double t = frame * FRAME_DT;
            if (frame % SNAP_EVERY_FRAMES == 0) {
                interp.addSample(t, new Vec3(VX * t, 0, 0), Quat.IDENTITY, vel, Vec3.ZERO);
            }
            RigidSnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null) continue;

            if (!Double.isNaN(prevX)) {
                assertTrue(out.position().x() >= prevX - 1e-9, "render stepped backward at frame " + frame);
            }
            prevX = out.position().x();

            if (frame > 60) {
                assertTrue(Math.abs(out.position().x() - VX * t) < 0.3,
                        "render drifted from present truth at frame " + frame);
            }
        }
    }

    @Test
    void constantSpinTracksAnalyticOrientation() {
        // 1 rad/s yaw spin, sampled at 30 Hz: rendered orientation must stay within a few
        // degrees of the true rotation at every frame (dead-reckoned between samples).
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        Vec3 omega = new Vec3(0, 1, 0);

        for (int frame = 0; frame <= 600; frame++) {
            double t = frame * FRAME_DT;
            if (frame % SNAP_EVERY_FRAMES == 0) {
                interp.addSample(t, Vec3.ZERO, yaw(t), Vec3.ZERO, omega);
            }
            RigidSnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null || frame <= 60) continue;
            assertTrue(out.orientation().angleTo(yaw(t)) < 0.1,
                    "orientation drifted at frame " + frame
                            + " (off by " + out.orientation().angleTo(yaw(t)) + " rad)");
        }
    }

    @Test
    void deliveryGapFreezesAtProjectionCapInsteadOfRunningAway() {
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        Vec3 vel = new Vec3(VX, 0, 0);
        interp.addSample(0.0, Vec3.ZERO, Quat.IDENTITY, vel, Vec3.ZERO);

        // 2 s with no further snapshots: the projection target caps at maxProjectionSeconds
        // (0.15 s), and the render settles at a BOUNDED equilibrium slightly past it — the
        // dead-reckon step advances v·dt each frame while the ease pulls back toward the
        // frozen target, balancing at target + v·dt·(1−ease)/ease (same property as the
        // character SnapshotInterpolator). The guard is that this stays bounded — the body
        // must not keep coasting at full speed forever.
        double ease = 1.0 - Math.exp(-12.0 * FRAME_DT);
        double equilibrium = VX * 0.15 + VX * FRAME_DT * (1.0 - ease) / ease;
        double finalX = 0;
        for (int frame = 0; frame < 120; frame++) {
            RigidSnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            finalX = out.position().x();
        }
        assertTrue(finalX <= equilibrium + 0.1, "gap projection ran away: x=" + finalX
                + " (bounded equilibrium " + equilibrium + ")");
    }

    @Test
    void teleportSnapsPositionAndFlipSnapsOrientation() {
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        interp.addSample(0.0, Vec3.ZERO, Quat.IDENTITY, Vec3.ZERO, Vec3.ZERO);
        interp.advance(FRAME_DT);

        // 100 m jump + 180° flip in one sample (reset/respawn) — both channels snap.
        interp.addSample(0.1, new Vec3(100, 0, 0), yaw(Math.PI), Vec3.ZERO, Vec3.ZERO);
        RigidSnapshotInterpolator.Output out = interp.advance(FRAME_DT);
        assertEquals(100.0, out.position().x(), 0.5);
        assertTrue(out.orientation().angleTo(yaw(Math.PI)) < 0.05, "flip did not snap");
    }

    @Test
    void staleSamplesAreDroppedAndLatestSampleReflectsNewest() {
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        Vec3 vel = new Vec3(1, 2, 3);
        Vec3 omega = new Vec3(0.1, 0.2, 0.3);
        interp.addSample(1.0, new Vec3(5, 0, 0), Quat.IDENTITY, vel, omega);
        interp.addSample(0.5, new Vec3(99, 99, 99), Quat.IDENTITY, Vec3.ZERO, Vec3.ZERO);   // stale — dropped

        RigidSnapshotInterpolator.Sample latest = interp.latestSample();
        assertEquals(5.0, latest.position().x(), 1e-9);
        assertEquals(vel, latest.linearVelocity());
        assertEquals(omega, latest.angularVelocity());
    }

    @Test
    void resetClearsStateUntilNextSample() {
        RigidSnapshotInterpolator interp = new RigidSnapshotInterpolator();
        interp.addSample(0.0, Vec3.ZERO, Quat.IDENTITY, Vec3.ZERO, Vec3.ZERO);
        interp.reset();
        assertNull(interp.advance(FRAME_DT));
        assertNull(interp.latestSample());
        // And a pre-reset timestamp is accepted again (no stale-drop leak across reset).
        interp.addSample(0.0, new Vec3(1, 0, 0), Quat.IDENTITY, Vec3.ZERO, Vec3.ZERO);
        assertEquals(1.0, interp.advance(FRAME_DT).position().x(), 1e-9);
    }
}
