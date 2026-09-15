package com.openworld.character;

import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.api.BoneAttachment3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.core.Transform3D;

/**
 * Where the held weapon (and a marker on it) is in SKELETON space, as a skeleton modifier's pass
 * sees the pose -- the one owner of that question for the three modifiers that ask it
 * ({@link ShoulderAimModifier}, {@link StockMountIKModifier}, {@link SupportHandIKModifier}).
 *
 * <p><b>Why a modifier cannot just read the weapon's global transform.</b> The weapon hangs off a
 * {@code BoneAttachment3D}, which is updated AFTER the modifiers run, so its global transform is last
 * frame's -- and, inside one pass, it also misses whatever the earlier modifiers just did to the arm.
 * What IS exact is the weapon RELATIVE to its attachment (the socket and item transforms, constant
 * while held, both nodes updated together); composed onto the bone's pose as the pass sees it, that
 * is the weapon where it really is right now.
 */
final class HeldWeaponPose {
    private HeldWeaponPose() {}

    /** The character's WeaponController, found by walking UP from {@code from} (never getOwner(), W14). */
    static WeaponController findController(Node from) {
        for (Node n = from.getParent(); n != null; n = n.getParent()) {
            if (n.getNodeOrNull("WeaponController") instanceof WeaponController wc) return wc;
        }
        return null;
    }

    /**
     * The held weapon's transform in skeleton space, or null when {@code held} is null, out of the
     * tree, or not hanging from {@code boneName} through a BoneAttachment3D child of {@code skel}
     * (a holstered weapon mid-switch hangs from a holster bone and is not "in hand").
     */
    static Transform3D weaponInSkeleton(Skeleton3D skel, WeaponItem held, String boneName) {
        if (held == null || skel == null || boneName == null || !held.isInsideTree()) return null;
        BoneAttachment3D attachment = null;
        for (Node n = held.getParent(); n != null && n != skel; n = n.getParent()) {
            if (n instanceof BoneAttachment3D a && a.getParent() == skel) { attachment = a; break; }
        }
        if (attachment == null || !boneName.equals(attachment.getBoneName())) return null;
        int bone = skel.findBone(boneName);
        if (bone < 0) return null;
        Transform3D rel = attachment.getGlobalTransform().affineInverse().times(held.getGlobalTransform());
        return skel.getBoneGlobalPose(bone).times(rel);
    }

    /** {@code marker} (a node under {@code held}) in skeleton space, given the weapon's own skeleton-space transform. */
    static Transform3D markerInSkeleton(Transform3D weaponInSkeleton, WeaponItem held, Node3D marker) {
        Transform3D rel = held.getGlobalTransform().affineInverse().times(marker.getGlobalTransform());
        return weaponInSkeleton.times(rel);
    }
}
