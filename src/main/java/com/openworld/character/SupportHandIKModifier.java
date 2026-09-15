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

    /**
     * How much of the solve to apply, 0..1. Exists for blending the hand OFF the weapon — a reload
     * takes the support hand to the magazine, and a throw takes it away entirely — rather than for
     * dialling the solve down permanently.
     */
    @Export public float weight = 1.0f;

    /** Path to the character owning this skeleton; empty resolves the scene owner. */
    @Export public NodePath characterPath = new NodePath();

    private WeaponController weaponController;
    private boolean controllerResolved = false;

    public String getUpperBone() { return upperBone; }
    public void setUpperBone(String v) { this.upperBone = v; }
    public String getLowerBone() { return lowerBone; }
    public void setLowerBone(String v) { this.lowerBone = v; }
    public String getEndBone() { return endBone; }
    public void setEndBone(String v) { this.endBone = v; }
    public String getSupportPointName() { return supportPointName; }
    public void setSupportPointName(String v) { this.supportPointName = v; }
    public float getWeight() { return weight; }
    public void setWeight(float v) { this.weight = v; }
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
        TwoBoneIK.solve(skel, iu, il, ie, t, weight);
    }

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
