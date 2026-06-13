package com.game.net;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Guards the quaternion math RigidSnapshotInterpolator leans on: shortest-path slerp through
 * the q/−q double cover, angular-velocity integration converging on the analytic rotation, and
 * degenerate-input normalization falling back to identity instead of NaN.
 */
class QuatTest {

    private static final double EPS = 1e-6;

    /** Rotation of {@code angle} radians about the +Y axis. */
    private static Quat yaw(double angle) {
        return new Quat(0, Math.sin(angle / 2), 0, Math.cos(angle / 2));
    }

    private static void assertSameRotation(Quat expected, Quat actual, double eps, String msg) {
        assertTrue(expected.angleTo(actual) < eps, msg + " (angle off by " + expected.angleTo(actual) + " rad)");
    }

    @Test
    void normalizedRestoresUnitLengthAndDegenerateFallsBackToIdentity() {
        Quat scaled = new Quat(0, 2, 0, 0).normalized();
        assertEquals(1.0, scaled.length(), EPS);
        assertEquals(Quat.IDENTITY, new Quat(0, 0, 0, 0).normalized());
        assertEquals(Quat.IDENTITY, new Quat(1e-12, 0, 0, 1e-12).normalized());
    }

    @Test
    void slerpEndpointsAndMidpoint() {
        Quat a = yaw(0);
        Quat b = yaw(Math.PI / 2);
        assertSameRotation(a, a.slerp(b, 0.0), EPS, "t=0 must return start");
        assertSameRotation(b, a.slerp(b, 1.0), EPS, "t=1 must return end");
        assertSameRotation(yaw(Math.PI / 4), a.slerp(b, 0.5), EPS, "midpoint must be the half rotation");
    }

    @Test
    void slerpTakesShortestPathThroughNegatedQuaternion() {
        // −b encodes the same rotation as b; slerp must converge on it without a long-way spin.
        Quat a = yaw(0.1);
        Quat b = yaw(0.3);
        Quat negB = new Quat(-b.x(), -b.y(), -b.z(), -b.w());
        Quat viaB = a.slerp(b, 0.5);
        Quat viaNegB = a.slerp(negB, 0.5);
        assertSameRotation(viaB, viaNegB, EPS, "slerp through q and −q must agree");
        // And the step must stay small (shortest arc), not swing toward the far side.
        assertTrue(a.angleTo(viaNegB) < 0.2, "slerp went the long way around");
    }

    @Test
    void slerpHandlesNearlyParallelInputs() {
        Quat a = yaw(0.1);
        Quat b = yaw(0.1 + 1e-7);
        Quat out = a.slerp(b, 0.5);
        assertEquals(1.0, out.length(), EPS);
        assertSameRotation(a, out, 1e-5, "near-parallel slerp must stay put");
    }

    @Test
    void integrateConvergesOnAnalyticRotationOverSmallSteps() {
        // Spin at 1 rad/s about +Y for 1 s in 60 Hz steps — should land within a degree of yaw(1).
        Vec3 omega = new Vec3(0, 1, 0);
        Quat q = Quat.IDENTITY;
        for (int i = 0; i < 60; i++) q = q.integrate(omega, 1.0 / 60.0);
        assertSameRotation(yaw(1.0), q, 0.02, "integrated spin diverged from analytic rotation");
        assertEquals(1.0, q.length(), EPS);
    }

    @Test
    void angleToIsSignInsensitiveAndBounded() {
        Quat a = yaw(0.5);
        Quat negA = new Quat(-a.x(), -a.y(), -a.z(), -a.w());
        assertEquals(0.0, a.angleTo(negA), EPS);
        assertEquals(Math.PI / 2, yaw(0).angleTo(yaw(Math.PI / 2)), 1e-6);
    }
}
