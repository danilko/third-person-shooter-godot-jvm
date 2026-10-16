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

/**
 * A motorcycle RIDER's pose (PLAN.md 3.1b, option (b) of "rider poses from the clips we have"): there is no ride clip
 * (181 clips on shino and both UAL packs searched), so every bike plays the car's {@code drive_idle-loop} -- upright,
 * hands forward, feet forward -- and this bends it per bike AFTER the clip and BEFORE the aim modifiers:
 *
 * <ul>
 *   <li><b>lean forward</b> (deg): the spine tips toward the bars (spine_01..03 share it 30 / 30 / 40 %), and the neck
 *   and head take most of it back so the eyes stay on the road -- the sport bike's tuck;</li>
 *   <li><b>thighs</b> (deg, + = knees up / feet back): a Cub or a 白バイ puts the feet on pegs under the hips, the
 *   car clip has them out in front;</li>
 *   <li><b>knees</b> (deg, + = more bend);</li>
 *   <li><b>foot down</b>: at a stop the left foot is put on the ground beside the bike ({@link TwoBoneIK} on
 *   thigh_l -> calf_l -> foot_l to {@link #setFootTarget}), blended in and out.</li>
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
    private static final double[] SPINE_SHARE = {0.3, 0.3, 0.4};
    /** The neck and head give back this much of the lean between them, so the rider looks ahead, not at the tank. */
    private static final double LOOK_UP_SHARE = 0.75;
    /** Blend speed toward the foot-down weight (1/s): ~0.3 s to put a foot down. */
    private static final double FOOT_RATE = 3.5;

    private double leanForward, thighRaise, kneeBend;
    private double footWeight, footTarget;
    private Vector3 footWorld;

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

    @Register public double footWeightNow() { return footWeight; }
    @Register public double leanForwardNow() { return leanForward; }

    @Override
    public void _processModification() {
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;
        double dt = Math.min(0.1, getProcessDeltaTime());
        if (footWeight != footTarget) {
            double step = FOOT_RATE * dt;
            footWeight = Math.abs(footTarget - footWeight) <= step ? footTarget : footWeight + Math.signum(footTarget - footWeight) * step;
        }
        Vector3 rightSkel = bodyRight(skel);
        if (rightSkel == null) return;
        // about the body's RIGHT axis a positive angle tips +Y toward +Z, the BACK of a -Z-forward body
        // (CharacterRagdoll's slump), so "forward" is negative
        if (leanForward != 0.0) {
            for (int i = 0; i < SPINE.length; i++) bend(skel, SPINE[i], rightSkel, -leanForward * SPINE_SHARE[i]);
            bend(skel, "neck_01", rightSkel, leanForward * LOOK_UP_SHARE * 0.5);
            bend(skel, headBone(skel), rightSkel, leanForward * LOOK_UP_SHARE * 0.5);
        }
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
