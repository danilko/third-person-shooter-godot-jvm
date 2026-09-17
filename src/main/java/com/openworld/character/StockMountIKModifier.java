package com.openworld.character;

import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.api.SkeletonModifier3D;
import godot.core.Basis;
import godot.core.NodePath;
import godot.core.Transform3D;
import godot.core.VariantArray;
import godot.core.Vector3;

/**
 * Two-bone IK on the FIRING arm that puts a weapon's MOUNT marker on a body ANCHOR while aiming (PLAN.md A2.2;
 * generalised in W25): a long gun's butt pad ({@code StockPoint}) in the shoulder pocket, a launcher tube
 * ({@code ShoulderRestPoint}) on top of the shoulder. The table is {@link #mountMarkers} /
 * {@link #mountOffsets}, index-parallel; a held weapon uses the FIRST marker it declares, and a weapon that
 * declares none (a pistol) is left alone. A new mount kind is one row, set per body in the visuals scene
 * (the anchors are facts about the body's skin) -- {@code blender/tools/pose_weapon_hold.py --apply-anchor}
 * writes them from a weapon model the artist placed in the pose.
 *
 * <h2>Why it exists</h2>
 *
 * W20 put every long gun's GRIP on the palm and left the stock wherever the arm pose happens to put
 * it. A1 measured where that is: laterally exact, but 17-19 cm BEHIND the pocket, because the aim clip
 * holds the hand ~0.2 m in front of the shoulder joint where a shouldered stock needs ~0.38 m. That is
 * a fact about the WEAPON (grip-to-butt differs per gun: ASR1 0.281, ASR2 0.259, SHG1 0.265), so one
 * authored pose cannot be right for all of them -- the same argument that made the off hand an IK
 * target ({@link SupportHandIKModifier}, W14). The clip supplies the class of hold; this puts each
 * gun's own stock where a stock goes.
 *
 * <h2>What it moves, and what it deliberately does not</h2>
 *
 * The gun is TRANSLATED, never turned: the aim modifiers before this one have already put the bore on
 * the aim (and inside the stance's limits), so the hand keeps its rotation and only its position moves,
 * by exactly the offset from the weapon's {@code StockPoint} to the pocket. The upper arm and forearm
 * are solved to it ({@link TwoBoneIK}: clip elbow plane, reach clamped). A target past the arm's length
 * straightens the arm and leaves the stock short -- reported as {@link #lastShortfall()}, never hidden
 * by stretching.
 *
 * <p>The POCKET is a fixed offset from {@link #upperBone}'s origin, carried in {@link #pocketBone}'s
 * orthonormalised frame so it rolls with the shoulder when an aim modifier moves the collarbone. The
 * value was derived off the character's own skinned mesh ({@code tools/godot/probe_weapon_fit.gd},
 * which reads it from here and re-derives it from the skin every run).
 *
 * <h2>When</h2>
 *
 * Only while {@link #engaged} (set by {@code AnimationController}: combat, in a stance with
 * {@code Stance.stockMountEnabled}) AND the weapon in hand declares one of {@link #mountMarkers} AND
 * hangs from {@link #endBone}. The weight eases in and out over {@link #blendSeconds}, so leaving the
 * aim returns the arm to the clip's hold pose instead of snapping.
 *
 * <p>Order among the skeleton's children: spine aim, shoulder aim, THIS, recoil (A3), support hand --
 * the aim decides where the gun points, this decides where it sits, and the off hand follows the gun
 * wherever it ends up.
 */
@Script(className = "StockMountIKModifier")
public class StockMountIKModifier extends SkeletonModifier3D {

    /** Shoulder end of the firing arm. */
    @Export public String upperBone = "upperarm_r";
    /** Elbow. */
    @Export public String lowerBone = "lowerarm_r";
    /** The hand the weapon hangs from. */
    @Export public String endBone = "hand_r";
    /** The bone whose frame carries {@link #mountOffsets} (the collarbone, so the pocket follows the shoulder). */
    @Export public String pocketBone = "clavicle_r";

    /** Defaults for {@link #mountMarkers}; parsed by {@code pose_weapon_hold.py}, keep the literal shape. */
    static final String[] DEFAULT_MOUNT_MARKERS = {"StockPoint", "ShoulderRestPoint"};
    /**
     * Defaults for {@link #mountOffsets}: each anchor relative to {@link #upperBone}'s origin, in
     * {@link #pocketBone}'s orthonormalised basis, metres. The pocket was derived off the skin (W22); the body
     * scenes override both with the values the placed-model solve wrote (W25).
     */
    static final Vector3[] DEFAULT_MOUNT_OFFSETS = {
            new Vector3(-0.0280, -0.0419, 0.0880),
            new Vector3(0.0582, 0.0246, -0.0002),
    };

    /** Weapon marker names, index-parallel with {@link #mountOffsets}. The held weapon's FIRST match mounts. */
    @Export public VariantArray<String> mountMarkers = defaultMarkers();

    /** Body anchors for {@link #mountMarkers}, index-parallel. */
    @Export public VariantArray<Vector3> mountOffsets = defaultOffsets();

    private static VariantArray<String> defaultMarkers() {
        VariantArray<String> a = new VariantArray<>(String.class);
        for (String m : DEFAULT_MOUNT_MARKERS) a.append(m);
        return a;
    }

    private static VariantArray<Vector3> defaultOffsets() {
        VariantArray<Vector3> a = new VariantArray<>(Vector3.class);
        for (Vector3 v : DEFAULT_MOUNT_OFFSETS) a.append(v);
        return a;
    }

    /** Seconds to ease the solve fully in or out. */
    @Export public float blendSeconds = 0.1f;

    /** The weight the solve eases to while engaged, 0..1. 0 is the A1 control (clip arm untouched). */
    @Export public float maxWeight = 1.0f;

    /** Set by {@code AnimationController}: combat in a stance that shoulders its long gun. */
    @Export public boolean engaged = false;

    public String getUpperBone() { return upperBone; }
    public void setUpperBone(String v) { this.upperBone = v; }
    public String getLowerBone() { return lowerBone; }
    public void setLowerBone(String v) { this.lowerBone = v; }
    public String getEndBone() { return endBone; }
    public void setEndBone(String v) { this.endBone = v; }
    public String getPocketBone() { return pocketBone; }
    public void setPocketBone(String v) { this.pocketBone = v; }
    public VariantArray<String> getMountMarkers() { return mountMarkers; }
    public void setMountMarkers(VariantArray<String> v) { this.mountMarkers = v; }
    public VariantArray<Vector3> getMountOffsets() { return mountOffsets; }
    public void setMountOffsets(VariantArray<Vector3> v) { this.mountOffsets = v; }
    public float getBlendSeconds() { return blendSeconds; }
    public void setBlendSeconds(float v) { this.blendSeconds = v; }
    public float getMaxWeight() { return maxWeight; }
    public void setMaxWeight(float v) { this.maxWeight = v; }
    public boolean getEngaged() { return engaged; }
    public void setEngaged(boolean v) { this.engaged = v; }

    private WeaponController weaponController;
    private boolean controllerResolved = false;
    private float weight = 0.0f;
    private double shortfall = 0.0;
    private double moved = 0.0;
    private String mountName = "";

    /** The mount marker the held weapon is using ("" when none) -- for probes. */
    @Register
    public String currentMount() { return mountName; }

    /** How far (m) the stock was still from the pocket after the last solve -- non-zero only when out of reach. */
    @Register
    public double lastShortfall() { return shortfall; }

    /** How far (m) the last solve moved the hand -- the IK delta A2.4's authored pose should keep small. */
    @Register
    public double lastHandMove() { return moved; }

    /** The current eased weight, 0..1. */
    @Register
    public float currentWeight() { return weight; }

    @Override
    public void _processModification() {
        Skeleton3D skel = getSkeleton();
        if (skel == null) return;
        if (!controllerResolved) {
            controllerResolved = true;
            weaponController = HeldWeaponPose.findController(this);
        }
        WeaponItem held = weaponController == null ? null : weaponController.getCurrentWeaponItem();
        Node3D stock = null;
        Vector3 anchorOffset = null;
        mountName = "";
        if (held != null && mountMarkers != null && mountOffsets != null) {
            int n = (int) Math.min(mountMarkers.size(), mountOffsets.size());
            for (int i = 0; i < n && stock == null; i++) {
                if (held.getNodeOrNull(new NodePath(mountMarkers.get(i))) instanceof Node3D m) {
                    stock = m;
                    anchorOffset = mountOffsets.get(i);
                    mountName = mountMarkers.get(i);
                }
            }
        }
        Transform3D gun = (stock != null) ? HeldWeaponPose.weaponInSkeleton(skel, held, endBone) : null;

        // Ease toward the wanted weight, on the frame delta (clamped, so a hitch cannot jump it).
        double dt = Math.min(0.1, getProcessDeltaTime());
        float goal = (engaged && gun != null) ? Math.max(0.0f, Math.min(1.0f, maxWeight)) : 0.0f;
        float step = blendSeconds <= 0.0f ? 1.0f : (float) (dt / blendSeconds);
        weight = (weight < goal) ? Math.min(goal, weight + step) : Math.max(goal, weight - step);
        shortfall = 0.0;
        moved = 0.0;
        if (weight <= 0.0f || gun == null) return;

        int iu = skel.findBone(upperBone);
        int il = skel.findBone(lowerBone);
        int ie = skel.findBone(endBone);
        int ip = skel.findBone(pocketBone);
        if (iu < 0 || il < 0 || ie < 0 || ip < 0) return;

        Vector3 stockPos = HeldWeaponPose.markerInSkeleton(gun, held, stock).getOrigin();
        Basis pocketFrame = skel.getBoneGlobalPose(ip).getBasis().orthonormalized();
        Vector3 pocket = skel.getBoneGlobalPose(iu).getOrigin().plus(pocketFrame.times(anchorOffset));

        Transform3D hand = skel.getBoneGlobalPose(ie);
        Vector3 target = hand.getOrigin().plus(pocket.minus(stockPos).times(weight));
        Vector3 solved = TwoBoneIK.solve(skel, iu, il, ie, target, 1.0f);
        if (solved == null) return;
        // Keep the hand's rotation: the aim modifiers already pointed the bore, and a translation must
        // not turn it. (TwoBoneIK moves the hand by rotating its parents, which also rotates the hand.)
        skel.setBoneGlobalPose(ie, new Transform3D(hand.getBasis(), solved));
        moved = solved.minus(hand.getOrigin()).length();
        shortfall = solved.minus(target).length();
    }

    @Register
    @Override
    public void _exitTree() {
        weaponController = null;
        controllerResolved = false;
        weight = 0.0f;
    }
}
