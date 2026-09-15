package com.openworld.character;

import godot.api.Skeleton3D;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;

/**
 * Two-bone IK in SKELETON space -- the solve shared by {@link SupportHandIKModifier} (the off hand onto
 * the weapon) and {@link StockMountIKModifier} (the firing hand so the stock sits in the shoulder).
 *
 * <p>Law of cosines on {@code upper -> lower -> end}, with the bend plane taken from the CURRENT pose so
 * the animator's elbow direction survives -- a pole vector would override that and is not wanted here,
 * where the clip already knows where the elbow belongs. Reach is clamped to the arm's own length, so a
 * target further away than the arm straightens the arm rather than dislocating it (W14).
 */
final class TwoBoneIK {
    private TwoBoneIK() {}

    /**
     * Swings {@code upper} and {@code lower} so {@code end}'s origin moves toward {@code target}
     * (skeleton space) by {@code weight}. Returns the end bone's new origin, or null when nothing was
     * written (degenerate chain or target). The end bone's own rotation is left to its parents.
     */
    static Vector3 solve(Skeleton3D skel, int iu, int il, int ie, Vector3 t, float weight) {
        Transform3D gu = skel.getBoneGlobalPose(iu);
        Transform3D gl = skel.getBoneGlobalPose(il);
        Transform3D ge = skel.getBoneGlobalPose(ie);
        Vector3 u = gu.getOrigin();
        Vector3 l = gl.getOrigin();
        Vector3 e = ge.getOrigin();

        double a = l.minus(u).length();          // upper arm
        double b = e.minus(l).length();          // forearm
        Vector3 toTarget = t.minus(u);
        double reach = toTarget.length();
        if (a < 1e-5 || b < 1e-5 || reach < 1e-5) return null;

        // Clamped to what the arm can actually do: past a+b it straightens instead of stretching,
        // and inside |a-b| it folds instead of inverting.
        double c = Math.max(Math.abs(a - b) + 1e-4, Math.min(a + b - 1e-4, reach));
        Vector3 dir = toTarget.normalized();

        // Bend plane from the CURRENT pose, so the elbow keeps the direction the clip gave it.
        // Order is (end-upper) x (lower-upper): rotating `dir` by +alpha about that axis puts the
        // elbow back on the side it is already on, which the opposite order does not.
        Vector3 axis = e.minus(u).cross(l.minus(u));
        if (axis.lengthSquared() < 1e-10) {
            axis = dir.cross(gu.getBasis().getColumn(2));   // straight arm: any stable perpendicular
            if (axis.lengthSquared() < 1e-10) return null;
        }
        axis = axis.normalized();

        double cosAlpha = (a * a + c * c - b * b) / (2.0 * a * c);
        double alpha = Math.acos(Math.max(-1.0, Math.min(1.0, cosAlpha)));

        Vector3 elbowSolved = u.plus(new Basis(axis, alpha).times(dir).times((float) a));
        Vector3 handSolved  = u.plus(dir.times((float) c));

        // Upper: swing the shoulder so the elbow lands where the solve wants it. Children (the
        // forearm and hand) follow, which is why the elbow is written first and read back below.
        Basis ru = arc(l.minus(u), elbowSolved.minus(u), weight);
        if (ru == null) return null;
        skel.setBoneGlobalPose(iu, new Transform3D(ru.times(gu.getBasis()), u));

        // Lower: close the elbow onto the hand target, measured from where the forearm now points.
        Vector3 elbowActual = u.plus(ru.times(l.minus(u)));
        Basis rl = arc(ru.times(e.minus(l)), handSolved.minus(elbowSolved), weight);
        if (rl == null) return null;
        skel.setBoneGlobalPose(il,
                new Transform3D(rl.times(ru).times(gl.getBasis()), elbowActual));
        return skel.getBoneGlobalPose(ie).getOrigin();
    }

    /**
     * Shortest-arc rotation from {@code from} onto {@code to}, scaled by {@code w}.
     *
     * <p>Scaling the ANGLE about the shared axis, not lerping two bases: that is the slerp from
     * identity along the shortest arc, and it is the same partial-rotation rule
     * {@link ShoulderAimModifier} uses for its driven-bone weights. Null when the vectors are degenerate.
     */
    static Basis arc(Vector3 from, Vector3 to, float w) {
        if (from.lengthSquared() < 1e-12 || to.lengthSquared() < 1e-12) return null;
        Vector3 f = from.normalized();
        Vector3 g = to.normalized();
        Vector3 axis = f.cross(g);
        double dot = Math.max(-1.0, Math.min(1.0, f.dot(g)));
        if (axis.lengthSquared() < 1e-12) {
            // Parallel: nothing to do. Anti-parallel is not reachable here -- both vectors are
            // derived from the same arm, so they can never be a full turn apart.
            return new Basis();
        }
        return new Basis(axis.normalized(), Math.acos(dot) * w);
    }
}
