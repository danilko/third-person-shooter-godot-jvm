package com.openworld.character;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.Quaternion;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * A motorcycle RIDER's pose (PLAN.md 3.1b, option (b) of "rider poses from the clips we have"): there is no ride clip
 * (181 clips on shino and both UAL packs searched), so every bike plays the car's {@code drive_idle-loop} -- upright,
 * hands forward, feet forward -- and this bends it per bike AFTER the clip and BEFORE the aim modifiers:
 *
 * <ul>
 *   <li><b>lean forward</b> (deg): the back tips toward the bars (a hip hinge takes 40 %, spine_01..03 20 % each), and the neck
 *   and head take most of it back so the eyes stay on the road -- the sport bike's tuck;</li>
 *   <li><b>thighs</b> (deg, + = knees up / feet back): a Cub or a 白バイ puts the feet on pegs under the hips, the
 *   car clip has them out in front;</li>
 *   <li><b>knees</b> (deg, + = more bend);</li>
 *   <li><b>foot down</b>: at a stop the left foot is put on the ground beside the bike ({@link TwoBoneIK} on
 *   thigh_l -> calf_l -> foot_l to {@link #setFootTarget}), blended in and out;</li>
 *   <li><b>the back follows the reach</b>: the lean above is the artist's base; if a bar grip is still past
 *   {@link #REACH_SLACK} of an arm's length after it, the spine leans further, a degree at a time, until both are in
 *   reach (at most {@link #MAX_REACH_LEAN} more) -- so a low clip-on bar pulls a short body into the tuck and a tall
 *   one needs none of it. The hands themselves are put on the bars by {@link RiderHandsModifier}, LAST in the chain
 *   (after the aim modifiers have turned the torso), which this reads the grips and weights from.</li>
 * </ul>
 *
 * <p>Built and removed by {@code Motorcycle} as a rider gets on and off; every peer builds its own from the seat
 * occupancy it already replicates, so the pose needs no message. Visual only: hit boxes are the physical bones, which
 * follow the pose like they follow the clip.
 */
@Script(className = "RiderPoseModifier")
public class RiderPoseModifier extends SkeletonModifier3D {

    public static final String NAME = "RiderPoseModifier";

    private static final String[] SPINE = {"spine_01", "spine_02", "spine_03"};
    private static final double[] SPINE_SHARE = {0.2, 0.2, 0.2};
    /**
     * The rest of the lean is a HIP HINGE: the pelvis tips forward and the thighs are turned back by the same angle, so
     * the legs stay where the clip and the thigh / knee numbers put them. A rider leans from the hips; the spine bones
     * alone are too short to carry the shoulders anywhere (measured on Shino: spine_01 sits 5 cm over the pelvis and the
     * shoulders 0.31 m over it, so 40 deg of spine-only lean moved the shoulders ~0.13 m and the hands could not reach
     * an upright bike's bars).
     */
    private static final double HIP_SHARE = 0.4;
    /** The neck and head give back this much of the lean between them, so the rider looks ahead, not at the tank. */
    private static final double LOOK_UP_SHARE = 0.75;
    /** Blend speed toward the foot-down weight (1/s): ~0.3 s to put a foot down. */
    private static final double FOOT_RATE = 3.5;

    /** A grip further than this share of the arm's length from the shoulder pulls the back forward. */
    static final double REACH_SLACK = 0.98;
    /** The most the reach may add to the bike's own lean (deg), and the step it is found in. */
    static final double MAX_REACH_LEAN = 30.0;
    private static final double REACH_STEP = 1.0;

    private double leanForward, thighRaise, kneeBend;
    private double footWeight, footTarget;
    private Vector3 footWorld;
    private RiderHandsModifier hands;
    private double reachLean;

    /** The bike's pose numbers (VehicleConfig.rider*), degrees. */
    public void setPose(double leanForwardDeg, double thighRaiseDeg, double kneeBendDeg) {
        leanForward = leanForwardDeg;
        thighRaise = thighRaiseDeg;
        kneeBend = kneeBendDeg;
    }

    /** Where the left foot goes (world), or null to keep it on the peg. */
    public void setFootTarget(Vector3 world) {
        footWorld = world;
        footTarget = world != null ? 1.0 : 0.0;
    }

    /** The rider's hands modifier, whose grips the back leans toward; null = no reach to follow. */
    public void setHands(RiderHandsModifier h) { hands = h; }

    /** Degrees the reach added to the bike's lean on the last pass. */
    @Register public double reachLeanNow() { return reachLean; }

    @Register public double footWeightNow() { return footWeight; }
    @Register public double leanForwardNow() { return leanForward; }

    @Override
    public void _processModification() {
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;
        double dt = Math.min(0.1, getProcessDeltaTime());
        footWeight = ease(footWeight, footTarget, FOOT_RATE * dt);
        reachLean = 0.0;
        Vector3 rightSkel = bodyRight(skel);
        if (rightSkel == null) return;
        if (leanForward != 0.0) lean(skel, rightSkel, leanForward);
        followReach(skel, rightSkel);
        if (thighRaise != 0.0 || kneeBend != 0.0) {
            for (String side : new String[] {"_l", "_r"}) {
                // a thigh swings forward (knee up) about the right axis by a NEGATIVE angle, like the spine; the
                // calf folds back (foot toward the seat) by a positive one
                bend(skel, "thigh" + side, rightSkel, -thighRaise);
                bend(skel, "calf" + side, rightSkel, kneeBend);
            }
        }
        if (footWeight > 0.0 && footWorld != null) {
            int iu = skel.findBone("thigh_l"), il = skel.findBone("calf_l"), ie = skel.findBone("foot_l");
            if (iu >= 0 && il >= 0 && ie >= 0) {
                Vector3 t = skel.getGlobalTransform().affineInverse().times(footWorld);
                Transform3D foot = skel.getBoneGlobalPose(ie);
                Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, t, (float) footWeight);
                if (solved != null) skel.setBoneGlobalPose(ie, new Transform3D(foot.getBasis(), solved));
            }
        }
    }

    static double ease(double now, double target, double step) {
        return Math.abs(target - now) <= step ? target : now + Math.signum(target - now) * step;
    }

    /**
     * Tip the back forward by {@code degrees}: the hip hinge and the spine share it, the neck and head take most of it back. About the
     * body's RIGHT axis a positive angle tips +Y toward +Z, the BACK of a -Z-forward body (CharacterRagdoll's slump),
     * so "forward" is negative.
     */
    private static void lean(Skeleton3D skel, Vector3 rightSkel, double degrees) {
        bend(skel, "pelvis", rightSkel, -degrees * HIP_SHARE);
        bend(skel, "thigh_l", rightSkel, degrees * HIP_SHARE);
        bend(skel, "thigh_r", rightSkel, degrees * HIP_SHARE);
        for (int i = 0; i < SPINE.length; i++) bend(skel, SPINE[i], rightSkel, -degrees * SPINE_SHARE[i]);
        bend(skel, "neck_01", rightSkel, degrees * LOOK_UP_SHARE * 0.5);
        bend(skel, headBone(skel), rightSkel, degrees * LOOK_UP_SHARE * 0.5);
    }

    /** Lean further, a step at a time, while a hand on its way to a bar cannot reach it; stop when a step does not help. */
    private void followReach(Skeleton3D skel, Vector3 rightSkel) {
        if (hands == null || !GD.isInstanceValid(hands)) return;
        double deficit = reachDeficit(skel);
        while (deficit > 0.0 && reachLean < MAX_REACH_LEAN) {
            lean(skel, rightSkel, REACH_STEP);
            double after = reachDeficit(skel);
            if (after >= deficit) {                    // the bar is not in front of the shoulder: leaning cannot help
                lean(skel, rightSkel, -REACH_STEP);
                break;
            }
            reachLean += REACH_STEP;
            deficit = after;
        }
    }

    /** How far (m) the worst-placed hand that is reaching for a bar is beyond {@link #REACH_SLACK} of its arm; <= 0 = all reach. */
    private double reachDeficit(Skeleton3D skel) {
        double worst = Double.NEGATIVE_INFINITY;
        for (int s = 0; s < 2; s++) {
            double w = hands.weight(s);
            if (w <= 0.0) continue;
            String side = RiderHandsModifier.SIDES[s];
            int iu = skel.findBone("upperarm" + side), il = skel.findBone("lowerarm" + side), ie = skel.findBone("hand" + side);
            if (iu < 0 || il < 0 || ie < 0) continue;
            Vector3 wrist = hands.wristTarget(skel, s, ie);
            if (wrist == null) continue;
            double arm = skel.getBoneGlobalRest(iu).getOrigin().minus(skel.getBoneGlobalRest(il).getOrigin()).length()
                       + skel.getBoneGlobalRest(il).getOrigin().minus(skel.getBoneGlobalRest(ie).getOrigin()).length();
            double reach = wrist.minus(skel.getBoneGlobalPose(iu).getOrigin()).length();
            // weighted, so a hand still blending in pulls the back in with it rather than all at once
            worst = Math.max(worst, (reach - REACH_SLACK * arm) * w);
        }
        return worst == Double.NEGATIVE_INFINITY ? 0.0 : worst;
    }

    private static String headBone(Skeleton3D skel) { return skel.findBone("head") >= 0 ? "head" : "head_2"; }

    /** The body's right axis in skeleton space (the MeshRoot's +X, as CharacterRagdoll reads it), or null. */
    private Vector3 bodyRight(Skeleton3D skel) {
        Node n = skel;
        while (n != null && !"MeshRoot".equals(n.getName().toString())) n = n.getParent();
        Node3D ref = n instanceof Node3D mr ? mr : skel.getParent() instanceof Node3D p ? p : null;
        if (ref == null) return null;
        Vector3 rightWorld = ref.getGlobalTransform().getBasis().getColumn(0).normalized();
        return skel.getGlobalTransform().getBasis().inverse().times(rightWorld).normalized();
    }

    private static void bend(Skeleton3D skel, String bone, Vector3 axisSkel, double degrees) {
        int idx = skel.findBone(bone);
        if (idx < 0 || degrees == 0.0) return;
        Basis boneGlobal = skel.getBoneGlobalPose(idx).getBasis();
        Vector3 axisLocal = boneGlobal.inverse().times(axisSkel).normalized();
        Quaternion q = new Quaternion(axisLocal, Math.toRadians(degrees));
        skel.setBonePoseRotation(idx, skel.getBonePoseRotation(idx).times(q));
    }
}
