package com.openworld.character;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A motorcycle rider's HANDS ON THE BARS (PLAN.md 3.1b): {@link TwoBoneIK} on upperarm -> lowerarm -> hand puts each
 * hand's GRIP point -- the knuckle line, {@link #GRIP_FRACTION} of the way from the wrist to the middle knuckle, as
 * {@link SupportHandIKModifier} reads it -- on the bike's {@code grip_l} / {@code grip_r} marker. The markers are
 * Empties an artist places in the bike's .blend (make_placeholder_bikes.py writes the defaults), exported as nodes of
 * its .glb, so moving a bar in Blender moves the hands with no code.
 *
 * <ul>
 *   <li>The hand keeps the clip's rotation (the car clip's hands are already closed round a wheel); only the wrist
 *   moves.</li>
 *   <li>A grip still out of reach after {@link RiderPoseModifier}'s lean is closed by protracting the clavicle (at
 *   most {@link #MAX_CLAVICLE_DEG}), SupportHandIK's rule; what is left after that is reported, not forced.</li>
 *   <li>The right hand lets go while it holds a weapon (the one-handed drive-by: the aim modifiers have that arm), and
 *   each hand blends in and out over ~0.25 s, so the hands reach for the bars as the rider sits down.</li>
 * </ul>
 *
 * <p>LAST among the skeleton's modifiers, after the aim modifiers: a drive-by turns the torso, and the left hand must
 * stay on the bar as it ends up, not where it was before the turn (measured: 0.35-0.6 m off it when this ran first).
 * Built and removed by {@code Motorcycle} with the pose; visual only, every peer, no message.
 */
@Script(className = "RiderHandsModifier")
public class RiderHandsModifier extends SkeletonModifier3D {

    public static final String NAME = "RiderHandsModifier";

    /** Blend speed toward a hand's weight (1/s): ~0.25 s for a hand to reach the bar or let it go. */
    private static final double HAND_RATE = 4.0;
    /** Where a hand closes on a bar: this fraction of the way from the wrist to the middle knuckle (SupportHandIK's). */
    static final float GRIP_FRACTION = 0.75f;
    /** What is still out of reach after the lean is closed by protracting the clavicle, at most this far (deg). */
    static final double MAX_CLAVICLE_DEG = 30.0;
    /** The hand IK on / off for every rider: off is probe_rider_pose's control (the clip's hands, short of the bars). */
    public static boolean handsOnBars = true;

    static final String[] SIDES = {"_l", "_r"};

    private final Node3D[] grips = new Node3D[2];
    private final double[] handWeight = new double[2];
    private boolean rightOnBar = true;
    private final double[] gripMiss = {-1.0, -1.0};

    /** The bike's two grip markers (its model's {@code grip_l} / {@code grip_r}); null leaves that hand to the clip. */
    public void setGrips(Node3D left, Node3D right) {
        grips[0] = left;
        grips[1] = right;
    }

    /** False while the right hand holds a weapon: it lets go of the bar and the aim modifiers have the arm. */
    public void setRightHandOnBar(boolean on) { rightOnBar = on; }

    /** How far this hand is blended onto its bar now, 0..1. */
    double weight(int s) { return handWeight[s]; }

    /** Distance (m) from a hand's grip point to its marker after the last solve; -1 when that hand was not solved. */
    @Register public double gripMissNow(int side) { return side >= 0 && side < 2 ? gripMiss[side] : -1.0; }
    @Register public double handWeightNow(int side) { return side >= 0 && side < 2 ? handWeight[side] : 0.0; }

    @Override
    public void _processModification() {
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;
        double dt = Math.min(0.1, getProcessDeltaTime());
        for (int s = 0; s < 2; s++) {
            boolean on = handsOnBars && grips[s] != null && GD.isInstanceValid(grips[s]) && (s == 0 || rightOnBar);
            handWeight[s] = RiderPoseModifier.ease(handWeight[s], on ? 1.0 : 0.0, HAND_RATE * dt);
            gripMiss[s] = -1.0;
            if (handWeight[s] > 0.0) handOnGrip(skel, s);
        }
    }

    /** Skeleton-space point the WRIST must reach so this hand's grip point lands on its marker, with the hand as posed now. */
    Vector3 wristTarget(Skeleton3D skel, int s, int ie) {
        Vector3 grip = gripTarget(skel, s);
        return grip != null ? grip.minus(skel.getBoneGlobalPose(ie).getBasis().orthonormalized().times(gripOffset(skel, s, ie))) : null;
    }

    private Vector3 gripTarget(Skeleton3D skel, int s) {
        Node3D g = grips[s];
        if (g == null || !GD.isInstanceValid(g)) return null;
        return skel.getGlobalTransform().affineInverse().times(g.getGlobalPosition());
    }

    /** The grip point in the hand's REST frame: {@link #GRIP_FRACTION} of the way to the middle knuckle. */
    private static Vector3 gripOffset(Skeleton3D skel, int s, int ie) {
        int ig = skel.findBone("middle_01" + SIDES[s]);
        if (ig < 0) return Vector3.Companion.getZERO();
        return skel.getBoneGlobalRest(ie).affineInverse().times(skel.getBoneGlobalRest(ig).getOrigin()).times(GRIP_FRACTION);
    }

    /**
     * Swing the clavicle toward the grip by just enough to bring it into the arm's reach (SupportHandIKModifier's rule:
     * nothing when it already reaches, capped at {@link #MAX_CLAVICLE_DEG}), scaled by the hand's weight.
     */
    private void protract(Skeleton3D skel, int s, int iu, int il, int ie, Vector3 grip, Vector3 offset) {
        int ic = skel.findBone("clavicle" + SIDES[s]);
        if (ic < 0) return;
        double arm = skel.getBoneGlobalRest(iu).getOrigin().minus(skel.getBoneGlobalRest(il).getOrigin()).length()
                   + skel.getBoneGlobalRest(il).getOrigin().minus(skel.getBoneGlobalRest(ie).getOrigin()).length();
        arm *= RiderPoseModifier.REACH_SLACK;
        Vector3 wrist = grip.minus(skel.getBoneGlobalPose(ie).getBasis().orthonormalized().times(offset));
        Transform3D clav = skel.getBoneGlobalPose(ic);
        Vector3 pivot = clav.getOrigin();
        Vector3 toShoulder = skel.getBoneGlobalPose(iu).getOrigin().minus(pivot);
        Vector3 toTarget = wrist.minus(pivot);
        double r = toShoulder.length(), d = toTarget.length();
        if (r < 1.0e-5 || d < 1.0e-5 || wrist.minus(skel.getBoneGlobalPose(iu).getOrigin()).length() <= arm) return;
        Vector3 axis = toShoulder.cross(toTarget);
        if (axis.length() < 1.0e-6) return;
        double phi = Math.acos(clamp(toShoulder.normalized().dot(toTarget.normalized())));
        double theta = phi - Math.acos(clamp((r * r + d * d - arm * arm) / (2.0 * r * d)));
        theta = Math.max(0.0, Math.min(theta, Math.toRadians(MAX_CLAVICLE_DEG))) * handWeight[s];
        if (theta > 1.0e-5) skel.setBoneGlobalPose(ic, new Transform3D(new Basis(axis.normalized(), theta).times(clav.getBasis()), pivot));
    }

    private static double clamp(double v) { return v < -1.0 ? -1.0 : (v > 1.0 ? 1.0 : v); }

    private void handOnGrip(Skeleton3D skel, int s) {
        String side = SIDES[s];
        int iu = skel.findBone("upperarm" + side), il = skel.findBone("lowerarm" + side), ie = skel.findBone("hand" + side);
        if (iu < 0 || il < 0 || ie < 0) return;
        Vector3 grip = gripTarget(skel, s);
        if (grip == null) return;
        Vector3 offset = gripOffset(skel, s, ie);
        protract(skel, s, iu, il, ie, grip, offset);
        Transform3D hand = skel.getBoneGlobalPose(ie);
        Vector3 wrist = grip.minus(hand.getBasis().orthonormalized().times(offset));
        Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, wrist, (float) handWeight[s]);
        if (solved == null) return;
        // the hand keeps the clip's rotation: the solve only moves the wrist
        skel.setBoneGlobalPose(ie, new Transform3D(hand.getBasis(), solved));
        Transform3D after = skel.getBoneGlobalPose(ie);
        gripMiss[s] = after.getOrigin().plus(after.getBasis().orthonormalized().times(offset)).minus(grip).length();
    }
}
