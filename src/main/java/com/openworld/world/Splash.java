package com.openworld.world;

import com.openworld.audio.Sound;
import com.openworld.audio.Sounds;
import com.openworld.world.manager.ParticleManager;
import godot.api.Camera3D;
import godot.api.Node;
import godot.core.StringName;
import godot.core.Vector3;

/**
 * A splash on the water surface (PLAN.md P2b): the ParticleManager's WATER pool (droplet spray + a ripple ring,
 * WorldSystems.tscn) scaled by how hard the water was hit, and a splash sound. Cosmetic and local per peer: every
 * peer sees the body / bullet / grenade cross the surface and splashes it itself, no message.
 *
 * <p>Callers: {@code Character.setInWater} (a body entering), {@code CharacterAudio} (swim strokes, wading steps),
 * {@code BulletTracerManager.spawnTracer} (a shot crossing the surface), {@code GrenadeProjectile} (a throwable
 * dropping in).
 */
public final class Splash {
    private Splash() {}

    /** Splashes are drawn and heard this far from the camera (m). */
    public static final double RANGE = 90.0;

    /**
     * One splash at {@code at} (on the surface) of size {@code scale} (1 = a body jumping in), with {@code sound}
     * (null = silent) at {@code volumeDb}. Returns false when out of range or there is no particle pool.
     */
    public static boolean at(Node ctx, Vector3 at, double scale, Sound sound, float volumeDb) {
        if (ctx == null || at == null || !ctx.isInsideTree()) return false;
        var vp = ctx.getViewport();
        Camera3D cam = vp == null ? null : vp.getCamera3d();
        if (cam != null && cam.getGlobalPosition().distanceTo(at) > RANGE) return false;
        Node pmNode = ctx.getTree().getFirstNodeInGroup(new StringName("particle_manager"));
        if (pmNode instanceof ParticleManager pm) pm.spawn(SurfaceType.WATER, at, Vector3.Companion.getUP(), scale);
        if (sound != null) {
            Node parent = ctx.getTree().getCurrentScene() != null ? ctx.getTree().getCurrentScene() : ctx;
            Sounds.play3D(parent, sound, at, 3f, 0.1f, volumeDb);
        }
        return pmNode instanceof ParticleManager;
    }

    /**
     * Where the segment {@code from} -> {@code to} goes DOWN through a water surface (any WaterVolume of the tree),
     * or null. A shot, a falling grenade: the water is an Area3D, so no ray ever stops on it.
     */
    public static Vector3 crossing(godot.api.SceneTree tree, Vector3 from, Vector3 to) {
        if (tree == null || from == null || to == null || to.getY() >= from.getY()) return null;
        for (Node n : tree.getNodesInGroup(new StringName(WaterVolume.WATER_GROUP))) {
            if (!(n instanceof WaterVolume w) || !w.isInsideTree()) continue;
            double sy = w.getSurfaceY();
            if (from.getY() < sy || to.getY() > sy) continue;
            double t = (from.getY() - sy) / (from.getY() - to.getY());
            Vector3 p = from.plus(to.minus(from).times(t));
            if (w.containsPoint(p.minus(new Vector3(0, 0.05, 0)))) return new Vector3(p.getX(), sy, p.getZ());
        }
        return null;
    }
}
