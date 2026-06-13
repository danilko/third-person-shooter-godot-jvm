package com.game.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Regression guards for the near-time snapshot smoothing. Core properties: a constant-velocity
 * stream renders at the SAME constant real speed and stays ~present (no accumulating delay, the
 * "1–2 s lag" regression); a stop settles promptly with no lingering overshoot (the "moves too far
 * then scrolls back" regression); a delivery gap holds without running away; a teleport snaps.
 */
class SnapshotInterpolatorTest {

    private static final double FRAME_DT = 1.0 / 60.0;   // 60 fps render
    private static final int    SNAP_EVERY_FRAMES = 2;   // ~30 Hz snapshot cadence
    private static final double VX = 2.0;                 // m/s along +X

    private SnapshotInterpolator newInterp() {
        return new SnapshotInterpolator();   // default near-time tuning
    }

    private static double timeAtFrame(int frame) { return frame * FRAME_DT; }
    private static Vec3   posAtFrame(int frame)  { return new Vec3(VX * frame * FRAME_DT, 0, 0); }

    @Test
    void constantVelocityTracksTruthAtConstantSpeed() {
        SnapshotInterpolator interp = newInterp();
        Vec3 vel = new Vec3(VX, 0, 0);
        double prevX = Double.NaN;

        for (int frame = 0; frame <= 600; frame++) {
            if (frame % SNAP_EVERY_FRAMES == 0) {
                interp.addSample(frame, timeAtFrame(frame), posAtFrame(frame), vel, 0.0, Vec3.ZERO);
            }
            SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null) continue;

            // Monotonic: never visually steps backward.
            if (!Double.isNaN(prevX)) {
                assertTrue(out.position().x() >= prevX - 1e-9,
                        "render stepped backward at frame " + frame);
            }
            prevX = out.position().x();

            // Near-time: after warmup the render stays locked to present truth (no growing delay).
            if (frame > 60) {
                double truth = VX * timeAtFrame(frame);
                assertTrue(Math.abs(out.position().x() - truth) < 0.1,
                        "render drifted from present truth at frame " + frame
                                + " (render=" + out.position().x() + ", truth=" + truth + ")");
            }
        }
    }

    @Test
    void noAccumulatingDelayUnderSubSixtyHzSender() {
        // THE 1–2 s-delay guard. Sender emits at 15 Hz (well below render rate) with a frozen tick —
        // the near-time model projects off local frame delta, so it must stay ~present, never crawl
        // behind. (The old delayed-clock model fell behind and caught up at half real-time.)
        SnapshotInterpolator interp = newInterp();
        Vec3 vel = new Vec3(VX, 0, 0);
        double nextEmit = 0.0;
        double maxLag = 0.0;

        for (int frame = 1; frame <= 1200; frame++) {   // 20 s
            double realTime = frame * FRAME_DT;
            while (nextEmit <= realTime) {
                interp.addSample(7, nextEmit, new Vec3(VX * nextEmit, 0, 0), vel, 0.0, Vec3.ZERO);
                nextEmit += 1.0 / 15.0;                 // 15 Hz, frozen tick
            }
            SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null) continue;
            if (frame > 120) maxLag = Math.max(maxLag, Math.abs(VX * realTime - out.position().x()));
        }
        // One 15 Hz interval of projection (~0.13 m at VX=2) plus easing slack — never seconds/metres.
        assertTrue(maxLag < 0.4, "render delay grew under a sub-60Hz sender (lag=" + maxLag + "m)");
    }

    @Test
    void stoppedBodySettlesPromptlyWithoutOvershoot() {
        // Guards "moves too far then scrolls back": once stopped, output velocity is zero and the
        // rendered position settles to the stop point within a few frames, not seconds.
        SnapshotInterpolator interp = newInterp();
        Vec3 moving = new Vec3(VX, 0, 0);
        final double stopTime = 1.0;
        final double stopX = VX * stopTime;
        double nextEmit = 0.0;
        double settleTime = Double.NaN;

        for (int frame = 1; frame <= 600; frame++) {
            double realTime = frame * FRAME_DT;
            while (nextEmit <= realTime) {
                boolean stillMoving = nextEmit < stopTime;
                Vec3 pos = new Vec3(stillMoving ? VX * nextEmit : stopX, 0, 0);
                Vec3 vel = stillMoving ? moving : Vec3.ZERO;
                interp.addSample(frame, nextEmit, pos, vel, 0.0, Vec3.ZERO);
                nextEmit += 1.0 / 30.0;
            }
            SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null) continue;
            if (realTime > stopTime + 0.05 && Double.isNaN(settleTime)
                    && Math.abs(out.velocity().x()) < 1e-9
                    && Math.abs(out.position().x() - stopX) < 0.02) {
                settleTime = realTime;
            }
        }
        assertTrue(!Double.isNaN(settleTime), "never settled to the stop point");
        assertTrue(settleTime <= stopTime + 0.35,
                "took too long to settle after stop (settled at " + settleTime + "s)");
    }

    @Test
    void gapHoldsThenResumesWithoutTeleport() {
        // Snapshots stop for ~0.5 s then resume. Projection caps during the gap (no runaway) and the
        // body eases back to truth on resume — no single-frame teleport-sized jump.
        SnapshotInterpolator interp = newInterp();
        Vec3 vel = new Vec3(VX, 0, 0);
        int gapStart = 60, gapEnd = 90;   // ~0.5 s without samples
        double prevX = Double.NaN;
        double maxStep = 0;

        for (int frame = 0; frame <= 300; frame++) {
            boolean inGap = frame >= gapStart && frame < gapEnd;
            if (frame % SNAP_EVERY_FRAMES == 0 && !inGap) {
                interp.addSample(frame, timeAtFrame(frame), posAtFrame(frame), vel, 0.0, Vec3.ZERO);
            }
            SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
            if (out == null) continue;
            if (!Double.isNaN(prevX)) maxStep = Math.max(maxStep, Math.abs(out.position().x() - prevX));
            prevX = out.position().x();
        }
        // The 0.5 s-gap error is bounded (projection cap), eased out — not snapped. A teleport would
        // be the full catch-up distance (~1 m) in one frame.
        assertTrue(maxStep < 0.5, "gap recovery produced a teleport-sized jump: " + maxStep + "m");
        assertTrue(prevX > VX * 4.0, "did not advance/converge after the gap (x=" + prevX + ")");
    }

    @Test
    void teleportSnaps() {
        SnapshotInterpolator interp = newInterp();
        interp.addSample(0, 0.0, new Vec3(0, 0, 0), Vec3.ZERO, 0.0, Vec3.ZERO);
        interp.advance(FRAME_DT);
        // A 50 m jump (spawn / respawn / teleport) must land immediately, not crawl across the map.
        interp.addSample(1, 0.05, new Vec3(50, 0, 0), Vec3.ZERO, 0.0, Vec3.ZERO);
        SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
        assertEquals(50.0, out.position().x(), 0.001, "large jump must snap, not ease");
    }

    @Test
    void reorderedSnapshotIsDropped() {
        SnapshotInterpolator interp = newInterp();
        interp.addSample(0, 1.00, new Vec3(10, 0, 0), Vec3.ZERO, 0.0, Vec3.ZERO);
        interp.advance(FRAME_DT);
        // An older (reordered) snapshot must not roll the body back.
        interp.addSample(0, 0.90, new Vec3(0, 0, 0), Vec3.ZERO, 0.0, Vec3.ZERO);
        SnapshotInterpolator.Output out = interp.advance(FRAME_DT);
        assertTrue(out.position().x() > 9.9, "a stale snapshot rolled the body backward");
    }

    @Test
    void lerpAngleTakesShortestPath() {
        // 3.0 → -3.0 is a short +0.283 rad hop through ±π (not a -6 rad sweep back through 0). The
        // result is the forward representative 3.283 (≡ -3.0 mod 2π).
        double full = SnapshotInterpolator.lerpAngle(3.0, -3.0, 1.0);
        assertEquals(3.0 + (2 * Math.PI - 6.0), full, 1e-6);
        double mid = SnapshotInterpolator.lerpAngle(3.0, -3.0, 0.5);
        assertTrue(Math.abs(mid) > 3.0, "midpoint should pass through ±π, not 0");
    }
}
