package com.openworld.weapon;

import godot.api.PhysicsDirectSpaceState3D;
import godot.api.PhysicsShapeQueryParameters3D;
import godot.api.SphereShape3D;
import godot.core.Basis;
import godot.core.RID;
import godot.core.Transform3D;
import godot.core.VariantArray;
import godot.core.Vector3;

/**
 * One grenade's flight, stepped (W38). The ONE owner of how a thrown grenade moves: the grenade
 * ({@link GrenadeProjectile}, a kinematic body) steps it every physics frame and the trajectory preview
 * ({@link ThrowableItem}) steps a copy ahead, so the drawn path, bounces included, is the path flown.
 *
 * <p>Each step: gravity, then a sphere of the grenade's own size is swept along the step's motion
 * against {@link #MASK} ({@code castMotion}); on contact the sphere stops at the safe fraction and the
 * velocity is bounced by {@link ThrowArc#bounce} off the surface normal ({@code getRestInfo}). No
 * drag: CS 1.6 has none, and neither may the preview disagree with the flight.
 */
public final class GrenadeFlight {

    /** The grenade's collision radius, metres (a 56 x 112 mm grenade). */
    public static final double RADIUS = 0.06;
    /** What a grenade bounces off: the world layer (CollisionLayers.WORLD). */
    public static final long MASK = 1L;

    public Vector3 position;
    public Vector3 velocity;
    public boolean resting = false;
    /** How many surfaces it has touched. */
    public int contacts = 0;

    private final PhysicsShapeQueryParameters3D query = new PhysicsShapeQueryParameters3D();

    public GrenadeFlight(Vector3 position, Vector3 velocity, VariantArray<RID> exclude) {
        this.position = position;
        this.velocity = velocity;
        SphereShape3D sphere = new SphereShape3D();
        sphere.setRadius((float) RADIUS);
        query.setShape(sphere);
        query.setCollisionMask(MASK);
        if (exclude != null) query.setExclude(exclude);
    }

    /** Advance one step of {@code dt} seconds under gravity {@code g} in {@code space}. */
    public void step(PhysicsDirectSpaceState3D space, double dt, double g) {
        if (resting) return;
        velocity = velocity.plus(new Vector3(0.0, -g * dt, 0.0));
        Vector3 motion = velocity.times(dt);
        query.setTransform(new Transform3D(Basis.Companion.getIDENTITY(), position));
        query.setMotion(motion);
        var frac = space.castMotion(query);
        double safe = frac.getSize() > 0 ? frac.get(0) : 1.0;
        double unsafe = frac.getSize() > 1 ? frac.get(1) : 1.0;
        if (unsafe >= 1.0) {
            position = position.plus(motion);
            return;
        }
        position = position.plus(motion.times(safe));
        query.setTransform(new Transform3D(Basis.Companion.getIDENTITY(), position.plus(motion.times(unsafe - safe))));
        query.setMotion(new Vector3());
        var rest = space.getRestInfo(query);
        Vector3 n = rest.containsKey("normal") && rest.get("normal") instanceof Vector3 nv && nv.lengthSquared() > 1e-6
                ? nv.normalized() : motion.normalized().times(-1.0);
        ThrowArc.Bounce b = ThrowArc.bounce(velocity.getX(), velocity.getY(), velocity.getZ(), n.getX(), n.getY(), n.getZ());
        velocity = new Vector3(b.vx(), b.vy(), b.vz());
        resting = b.rest();
        contacts++;
    }
}
