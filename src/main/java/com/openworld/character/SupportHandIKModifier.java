package com.openworld.character;

import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.NodePath;
import godot.core.Transform3D;
import godot.core.Vector3;

/**
 * Two-bone IK putting the SUPPORT HAND on the weapon it is holding.
 *
 * <h2>Why this exists: it is what stops grip archetypes multiplying</h2>
 *
 * A grip archetype ({@code WeaponItem.weaponPoseIndex}, CLAUDE.md W12) animates the CLASS of hold —
 * one-handed, two-handed, shoulder-carried. What it cannot express is that an SMG's foregrip is 12 cm
 * from the trigger and a long rifle's is 30, because that is a fact about the WEAPON. Without IK the
 * only way to place the off hand correctly is one clip per weapon, which is exactly the explosion
 * the archetype split exists to avoid. With it, one {@code rifle} pose serves an SMG, a shotgun, a
 * carbine and a foregrip variant, and a new weapon costs one marker and no animation.
 *
 * <h2>Self-managed, deliberately</h2>
 *
 * It asks the character's {@link WeaponController} for the weapon actually in hand and looks for a
 * child marker named {@link #supportPointName}. No equip path pushes anything here, so there is no
 * wiring to forget on one of the four {@code onWeaponEquip} call sites and nothing that can go stale
 * when a weapon is switched, dropped or replicated. A weapon that declares no support point leaves
 * the arm exactly as the clip authored it — which is the correct answer for a pistol.
 *
 * <h2>The solve</h2>
 *
 * {@link TwoBoneIK} on {@code upperarm_l -> lowerarm_l -> hand_l} (shared with
 * {@link StockMountIKModifier}): elbow plane from the current pose, reach clamped to the arm.
 *
 * <p><b>The marker is where the hand GRIPS, not where the wrist is</b> (PLAN.md A2.4, CLAUDE.md W24). A
 * hand closes round a handguard at its knuckle line, {@link #gripFraction} of the way from the wrist
 * ({@code hand_l}'s origin) to the middle knuckle, so the wrist target is the marker pulled back through
 * the hand. And the hand KEEPS its orientation through the solve: the clip authors how the hand sits on
 * the gun, and the aim modifiers turn hand and gun together, so the pre-solve rotation is already the
 * right one. Without it the forearm's swing turned the hand with it, and a hand that reached the marker
 * still did not wrap the handguard.
 *
 * <p>Ordering matters: this must sit AFTER {@link ShoulderAimModifier} and {@link StockMountIKModifier}
 * among the skeleton's children, because both move the weapon and the hand has to be placed on the
 * weapon as it ends up, not as the clip left it.
 */
@Script(className = "SupportHandIKModifier")
public class SupportHandIKModifier extends SkeletonModifier3D {

    /** Shoulder end of the chain. */
    @Export public String upperBone = "upperarm_l";
    /** Elbow. */
    @Export public String lowerBone = "lowerarm_l";
    /** The bone actually placed on the target. */
    @Export public String endBone = "hand_l";

    /**
     * Child marker on the HELD WEAPON that the support hand should sit on. A weapon with no such
     * child is left alone, which is how a pistol (or any one-handed weapon) opts out — no flag, no
     * per-weapon table.
     */
    @Export public String supportPointName = "SupportPoint";

    /** The bone that, with {@link #gripFraction}, defines where along the hand it closes on the weapon. */
    @Export public String gripBone = "middle_01_l";

    /**
     * Where the hand grips, as a fraction of the rest-pose offset from {@link #endBone} to {@link #gripBone}
     * (0 = the wrist, the pre-A2.4 behaviour). Kept in step with {@code blender/tools/pose_weapon_hold.py}'s
     * {@code GRIP_FRACTION}, which authors the clips against the same point.
     */
    @Export public float gripFraction = 0.75f;

    /** Keep the hand's pre-solve orientation (the clip's grip on the gun) instead of letting the forearm turn it. */
    @Export public boolean keepHandRotation = true;

    /**
     * How much of the solve to apply, 0..1. Exists for blending the hand OFF the weapon — a reload
     * takes the support hand to the magazine, and a throw takes it away entirely — rather than for
     * dialling the solve down permanently.
     */
    @Export public float weight = 1.0f;

    /**
     * The support shoulder. Protracting it is how a human extends reach, and it is FREE here: the
     * weapon hangs off {@code hand_r} under {@code clavicle_r}, so swinging {@code clavicle_l}
     * moves the support shoulder toward a gun that does not move at all — no re-aim, no feedback
     * loop with {@link ShoulderAimModifier} or {@link StockMountIKModifier}.
     */
    @Export public String shoulderBone = "clavicle_l";

    /**
     * How far {@link #shoulderBone} may protract to close a reach deficit, in degrees. **0 is the
     * control and reproduces the two-bone-only behaviour exactly.**
     *
     * <p>It engages ONLY when the target is past the arm's own reach, and the angle is solved to
     * close exactly the deficit — so a body and weapon that already fit get 0 and are bit-identical.
     * Measured 2026-09-20 on the three shipped bodies: Godot-chan and Fumiriya reach every weapon
     * unaided, and Shino (shoulders 0.2174 m against their 0.2955) is the only one that protracts.
     *
     * <p>Capped because protraction moves the skin over the clavicle, and past ~40 deg that reads as
     * a shrug rather than a reach. Where the cap is not enough the hand stops short and
     * {@link #lastGripMiss()} says by how much — which is what GTA does with its own hand IK rather
     * than distorting the shoulder to force a contact.
     */
    @Export public float maxClavicleDeg = 40.0f;

    /** Path to the character owning this skeleton; empty resolves the scene owner. */
    @Export public NodePath characterPath = new NodePath();

    private WeaponController weaponController;
    private boolean controllerResolved = false;
    private double gripMiss = -1.0;
    private double armReach = -1.0;
    private double targetReach = -1.0;
    private double clavicleDeg = 0.0;

    /** Distance (m) from the hand's grip point to the marker after the last solve; -1 when nothing was solved. */
    @Register
    public double lastGripMiss() { return gripMiss; }

    /**
     * How far this arm can reach: shoulder to wrist with the elbow straight, from the REST skeleton.
     * A fact about the BODY, and half of why a support hand misses.
     */
    @Register
    public double armReach() { return armReach; }

    /**
     * How far the last solve was ASKED to reach: shoulder to the wrist the weapon's support point
     * implies. Past {@link #armReach} the arm straightens and the rest of the distance is the miss,
     * so `targetReach - armReach` says whether a miss is the SOLVE or simply the weapon being out
     * of reach -- which is a fact about the body's proportions, not about the IK.
     */
    @Register
    public double lastTargetReach() { return targetReach; }

    /** Degrees {@link #shoulderBone} protracted on the last solve; 0 when the arm reached unaided. */
    @Register
    public double lastClavicleDeg() { return clavicleDeg; }

    public String getUpperBone() { return upperBone; }
    public void setUpperBone(String v) { this.upperBone = v; }
    public String getLowerBone() { return lowerBone; }
    public void setLowerBone(String v) { this.lowerBone = v; }
    public String getEndBone() { return endBone; }
    public void setEndBone(String v) { this.endBone = v; }
    public String getSupportPointName() { return supportPointName; }
    public void setSupportPointName(String v) { this.supportPointName = v; }
    public String getGripBone() { return gripBone; }
    public void setGripBone(String v) { this.gripBone = v; }
    public float getGripFraction() { return gripFraction; }
    public void setGripFraction(float v) { this.gripFraction = v; }
    public boolean getKeepHandRotation() { return keepHandRotation; }
    public void setKeepHandRotation(boolean v) { this.keepHandRotation = v; }
    public float getWeight() { return weight; }
    public void setWeight(float v) { this.weight = v; }
    public String getShoulderBone() { return shoulderBone; }
    public void setShoulderBone(String v) { this.shoulderBone = v; }
    public float getMaxClavicleDeg() { return maxClavicleDeg; }
    public void setMaxClavicleDeg(float v) { this.maxClavicleDeg = v; }
    public NodePath getCharacterPath() { return characterPath; }
    public void setCharacterPath(NodePath v) { this.characterPath = v; }

    /** The character's WeaponController (explicit {@link #characterPath}, else walked up to). */
    private WeaponController resolveController() {
        if (!controllerResolved) {
            controllerResolved = true;
            Node explicit = (characterPath == null || characterPath.isEmpty())
                    ? null : getNodeOrNull(characterPath);
            if (explicit != null
                    && explicit.getNodeOrNull("WeaponController") instanceof WeaponController wc) {
                weaponController = wc;
            } else {
                // WALK UP, rather than trusting getOwner(). This node lives inside the CharacterVisuals
                // sub-scene, so its owner is that sub-scene's root -- and `WeaponController` is a child
                // of the CHARACTER, one level further out. getOwner() therefore resolves to a node that
                // has no such child, and the modifier is silently inert with a correct-looking scene
                // (measured: the arm moved 0.006 m).
                weaponController = HeldWeaponPose.findController(this);
            }
        }
        return weaponController;
    }

    @Override
    public void _processModification() {
        gripMiss = -1.0;
        targetReach = -1.0;
        if (weight <= 0.0f) return;
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;
        WeaponController wc = resolveController();
        if (wc == null || supportPointName == null || supportPointName.isEmpty()) return;
        WeaponItem held = wc.getCurrentWeaponItem();
        if (held == null) return;
        if (!(held.getNodeOrNull(new NodePath(supportPointName)) instanceof Node3D marker)) {
            return;                                      // no support point: leave the clip alone
        }

        int iu = skel.findBone(upperBone);
        int il = skel.findBone(lowerBone);
        int ie = skel.findBone(endBone);
        if (iu < 0 || il < 0 || ie < 0) return;

        // The target where the weapon is IN THIS PASS -- after the aim modifiers and the stock mount
        // have moved the firing hand -- rather than the marker's global transform, which is last
        // frame's (HeldWeaponPose). A weapon that does not hang from a hand bone (holstered mid-switch)
        // falls back to the marker's own position.
        Transform3D gun = HeldWeaponPose.weaponInSkeleton(skel, held, weaponBone);
        Vector3 t = (gun != null)
                ? HeldWeaponPose.markerInSkeleton(gun, held, marker).getOrigin()
                : skel.getGlobalTransform().affineInverse().times(marker.getGlobalPosition());
        // The grip point in the hand's REST frame, carried by the hand's current (kept) rotation.
        Transform3D hand = skel.getBoneGlobalPose(ie);   // re-read after any protraction
        int ig = skel.findBone(gripBone);
        Vector3 grip = Vector3.Companion.getZERO();
        if (ig >= 0 && gripFraction != 0.0f) {
            grip = skel.getBoneGlobalRest(ie).affineInverse().times(skel.getBoneGlobalRest(ig).getOrigin())
                    .times(gripFraction);
        }
        Vector3 wrist = t.minus(hand.getBasis().orthonormalized().times(grip));
        // Reported, not used: the reach this solve was asked for against the reach this arm has.
        armReach = skel.getBoneGlobalRest(iu).getOrigin().minus(skel.getBoneGlobalRest(il).getOrigin()).length()
                 + skel.getBoneGlobalRest(il).getOrigin().minus(skel.getBoneGlobalRest(ie).getOrigin()).length();
        targetReach = wrist.minus(skel.getBoneGlobalPose(iu).getOrigin()).length();

        // PROTRACT THE SUPPORT SHOULDER when, and only when, the arm cannot reach. Swinging
        // clavicle_l about its own origin carries upperarm_l toward the target; the weapon hangs off
        // the OTHER clavicle, so nothing this does moves the gun or needs re-aiming.
        clavicleDeg = 0.0;
        int ic = skel.findBone(shoulderBone);
        if (maxClavicleDeg > 0.0f && ic >= 0 && targetReach > armReach) {
            Transform3D clav = skel.getBoneGlobalPose(ic);
            Vector3 pivot = clav.getOrigin();
            Vector3 toShoulder = skel.getBoneGlobalPose(iu).getOrigin().minus(pivot);
            Vector3 toTarget = wrist.minus(pivot);
            double r = toShoulder.length();
            double d = toTarget.length();
            if (r > 1.0e-5 && d > 1.0e-5) {
                Vector3 axis = toShoulder.cross(toTarget);
                if (axis.length() > 1.0e-6) {
                    // Rotating the shoulder toward the target by t closes the angle between them to
                    // (phi - t); solve the law of cosines for the t that leaves exactly armReach.
                    double phi = Math.acos(clamp(toShoulder.normalized().dot(toTarget.normalized())));
                    double want = clamp((r * r + d * d - armReach * armReach) / (2.0 * r * d));
                    double theta = phi - Math.acos(want);
                    double cap = Math.toRadians(maxClavicleDeg);
                    theta = Math.max(0.0, Math.min(theta, cap));
                    if (theta > 1.0e-5) {
                        Basis turn = new Basis(axis.normalized(), theta);
                        skel.setBoneGlobalPose(ic, new Transform3D(turn.times(clav.getBasis()), pivot));
                        clavicleDeg = Math.toDegrees(theta);
                        // The hand rode round with the clavicle, so the grip offset -- and therefore
                        // the wrist the solve aims at -- has to be re-read, not reused.
                        hand = skel.getBoneGlobalPose(ie);
                        wrist = t.minus(hand.getBasis().orthonormalized().times(grip));
                        targetReach = wrist.minus(skel.getBoneGlobalPose(iu).getOrigin()).length();
                    }
                }
            }
        }

        Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, wrist, weight);
        if (solved == null) return;
        if (keepHandRotation) {
            skel.setBoneGlobalPose(ie, new Transform3D(hand.getBasis(), solved));
        }
        Transform3D after = skel.getBoneGlobalPose(ie);
        gripMiss = after.getOrigin().plus(after.getBasis().orthonormalized().times(grip)).minus(t).length();
    }

    private static double clamp(double v) { return v < -1.0 ? -1.0 : (v > 1.0 ? 1.0 : v); }

    /** The bone the weapon hangs from, used to place {@link #supportPointName} in this pass's pose. */
    @Export public String weaponBone = "hand_r";

    public String getWeaponBone() { return weaponBone; }
    public void setWeaponBone(String v) { this.weaponBone = v; }

    @Register
    @Override
    public void _exitTree() {
        weaponController = null;
        controllerResolved = false;
    }
}
