package com.openworld.camera;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.util.CollisionLayers;
import godot.api.Camera3D;
import godot.api.Node;
import godot.api.PhysicsRayQueryParameters3D;
import godot.core.Dictionary;
import godot.core.RID;
import godot.core.StringName;
import godot.core.VariantArray;
import godot.core.Vector3;

/**
 * Gamepad aim assist (PLAN.md 1.1 / F1, 2026-10-09): which body the crosshair is near, and by how much. A stick
 * cannot make the small fast corrections a mouse makes, so every console shooter helps (CoD / Halo / GTA V: slowdown
 * over a target, a short snap when the aim button goes down); CS has none and a mouse gets none here either --
 * {@link PlayerCameraController} only asks while {@code InputDevice.pad()}.
 *
 * <p>A target is a living {@link Character} that is not the shooter and not another player (co-op: no help onto a
 * friend), whose CHEST is within {@code range} and has a clear line from the camera through world geometry. The angle
 * is measured the way {@code ControlRotation} counts: yaw = atan2(-x, -z), pitch positive UP, degrees.
 */
public final class AimAssist {
    private AimAssist() {}

    /** Chest height over a standing body's origin; a crouched / prone body scales it by its collider (see chest). */
    public static final double CHEST = 1.25;
    /** A body this wide counts as "on target" (its angular radius at range, slowdown), metres. */
    public static final double BODY_RADIUS = 0.35;

    /** The best target: the yaw / pitch that would centre it, how far off it is, and its angular radius. */
    public record Pick(Character body, Vector3 point, double dYaw, double dPitch, double offDeg, double radiusDeg) {}

    private static final StringName CHARACTERS = new StringName("characters");
    private static final String[] STANCE_SHAPES = {"UprightCollision", "CrouchCollision", "CrawlCollision"};

    public static Pick pick(Character self, Camera3D cam, double coneDeg, double range) {
        if (self == null || cam == null || self.getTree() == null) return null;
        Vector3 eye = cam.getGlobalPosition();
        Vector3 f = cam.getGlobalTransform().getBasis().getZ().times(-1.0);
        double fYaw = Math.toDegrees(Math.atan2(-f.getX(), -f.getZ()));
        double fPitch = Math.toDegrees(Math.asin(Math.max(-1.0, Math.min(1.0, f.getY()))));
        Pick best = null;
        for (Node n : self.getTree().getNodesInGroup(CHARACTERS)) {
            if (!(n instanceof Character c) || c == self || c instanceof Player || !c.isAlive()) continue;
            Vector3 p = chest(c);
            Vector3 to = p.minus(eye);
            double dist = to.length();
            if (dist < 1.0 || dist > range) continue;
            double yaw = Math.toDegrees(Math.atan2(-to.getX(), -to.getZ()));
            double pitch = Math.toDegrees(Math.atan2(to.getY(), Math.hypot(to.getX(), to.getZ())));
            double dy = wrap(yaw - fYaw), dp = pitch - fPitch;
            double off = Math.hypot(dy, dp);
            if (off > coneDeg || (best != null && off >= best.offDeg())) continue;
            if (!clear(self, eye, p)) continue;
            best = new Pick(c, p, dy, dp, off, Math.toDegrees(Math.atan2(BODY_RADIUS, dist)));
        }
        return best;
    }

    /** The point the assist centres on: the chest, lower for a crouched or prone body (its collider's height). */
    static Vector3 chest(Character c) {
        double h = CHEST;
        for (String name : STANCE_SHAPES)
            if (c.getNodeOrNull(name) instanceof godot.api.CollisionShape3D cs && !cs.isDisabled()
                    && cs.getShape() instanceof godot.api.CapsuleShape3D cap) {
                h = Math.min(CHEST, cs.getPosition().getY() + cap.getHeight() * 0.25);
                break;
            }
        return c.getGlobalPosition().plus(new Vector3(0.0, h, 0.0));
    }

    private static boolean clear(Character self, Vector3 from, Vector3 to) {
        var w = self.getWorld3d();
        var space = w == null ? null : w.getDirectSpaceState();
        if (space == null) return true;
        var q = PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD, new VariantArray<>(RID.class));
        Dictionary<Object, Object> hit = space.intersectRay(q);
        return hit == null || hit.isEmpty();
    }

    static double wrap(double deg) {
        double d = (deg + 180.0) % 360.0;
        if (d < 0) d += 360.0;
        return d - 180.0;
    }
}
