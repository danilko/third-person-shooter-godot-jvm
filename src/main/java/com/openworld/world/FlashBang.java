package com.openworld.world;

import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.ui.FlashOverlay;
import godot.api.Camera3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicsDirectSpaceState3D;
import godot.api.PhysicsRayQueryParameters3D;
import godot.core.Vector3;

/**
 * A flashbang going off (FLA1). Whoever has a clear line from the flash to their eyes is blinded by
 * {@link FlashRules}: an AI for real (it cannot see a target, {@code AICharacter.blind}), the local player by a
 * white screen ({@link FlashOverlay}). A wall between you and the flash protects you completely.
 *
 * <p>Runs on every peer at the same point: the host from its projectile (authority: it blinds the AI, which only
 * think on the host), each client from the host's MSG_DETONATION (its own player's screen, and the light). So the
 * flash needs no message of its own.
 */
public final class FlashBang {

    /** What blocks the flash: the world layer (CollisionLayers.WORLD). Characters do not shield each other. */
    public static final long MASK = 1L;

    private FlashBang() { }

    public static void detonate(Node context, Vector3 point, double radius, double maxSeconds, boolean authority) {
        if (context == null || !context.isInsideTree()) return;
        lightBurst(context, point, radius);
        if (!(context instanceof Node3D n3)) return;
        PhysicsDirectSpaceState3D space = n3.getWorld3d().getDirectSpaceState();
        Vector3 from = point.plus(new Vector3(0.0, 0.1, 0.0));
        for (Node n : context.getTree().getNodesInGroup("characters")) {
            if (!(n instanceof Character c) || !c.isAlive()) continue;
            boolean local = c.isLocallyOwnedPlayer();
            boolean ai = authority && c instanceof AICharacter;
            if (!local && !ai) continue;
            Vector3 eyes = eyesOf(c);
            double dist = eyes.distanceTo(from);
            if (dist >= radius) continue;
            PhysicsRayQueryParameters3D q = PhysicsRayQueryParameters3D.Companion.create(from, eyes, MASK, new godot.core.VariantArray<>(godot.core.RID.class));
            if (!space.intersectRay(q).isEmpty()) continue;                 // behind a wall: nothing
            Vector3 look = local ? cameraForward(c) : facingForward(c);
            Vector3 to = from.minus(eyes);
            double cos = to.lengthSquared() < 1e-6 ? 1.0 : look.normalized().dot(to.normalized());
            double s = FlashRules.strength(dist, radius, cos);
            double seconds = FlashRules.seconds(s, maxSeconds);
            if (seconds <= 0) continue;
            if (ai) ((AICharacter) c).blind(seconds);
            if (local) FlashOverlay.flash(context, seconds);
        }
    }

    private static Vector3 eyesOf(Character c) {
        Node3D head = c.getPhysicalBoneNode("head_2");
        return head != null ? head.getGlobalPosition() : c.getGlobalPosition().plus(new Vector3(0.0, 1.5, 0.0));
    }

    private static Vector3 cameraForward(Character c) {
        Camera3D cam = c.getViewport() != null ? c.getViewport().getCamera3d() : null;
        return cam != null ? cam.getGlobalTransform().getBasis().getZ().times(-1.0) : facingForward(c);
    }

    /** The mesh looks down -Z; its yaw is the character's facing. */
    private static Vector3 facingForward(Character c) {
        double yaw = c.getFacingYaw();
        return new Vector3(-Math.sin(yaw), 0.0, -Math.cos(yaw));
    }

    /** A short, bright white light: the flash itself, seen by everyone near it. */
    private static void lightBurst(Node context, Vector3 point, double radius) {
        if (context.getTree().getCurrentScene() == null) return;
        FlashLight l = new FlashLight();
        l.setParam(godot.api.Light3D.Param.RANGE, (float) radius);
        context.getTree().getCurrentScene().addChild(l);
        l.setGlobalPosition(point.plus(new Vector3(0.0, 0.3, 0.0)));
    }
}
