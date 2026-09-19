package com.openworld.world;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.GPUParticles3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.api.ParticleProcessMaterial;
import godot.api.ResourceLoader;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * A smoke grenade's cloud (SMO1): a thick, slow Binbun3D smoke emitter shaped into a dome, that also BLOCKS AI
 * sight for its life ({@link #blocksSight}, asked by {@code AICharacter.hasLineOfSight}). The shape over time is
 * {@link SmokeRules}.
 *
 * <p>Every peer spawns its own at the detonation point (the host from its projectile, a client from the host's
 * MSG_DETONATION), so it needs no message of its own: the picture is local, and only the host's AI think. The
 * registry is process-local static state holding NODES, cleared when a cloud leaves the tree.
 */
@Script(className = "SmokeCloud")
public class SmokeCloud extends Node3D {

    public static final String VFX = "res://assets/vfx/smoke/effects/smoke_big/smoke_big_vfx_01.tscn";

    public double radius = 5.0;
    public double lifeSeconds = 18.0;
    public double growSeconds = 2.0;
    public double fadeSeconds = 3.0;

    private double age = 0.0;
    private GPUParticles3D smoke;

    private static final List<SmokeCloud> LIVE = new ArrayList<>();

    /** Spawn a cloud at {@code point} under {@code parent}'s scene. */
    public static SmokeCloud spawn(Node context, Vector3 point, double radius, double lifeSeconds) {
        if (context == null || context.getTree() == null || context.getTree().getCurrentScene() == null) return null;
        SmokeCloud c = new SmokeCloud();
        c.radius = radius;
        c.lifeSeconds = lifeSeconds;
        c.setName("SmokeCloud");
        context.getTree().getCurrentScene().addChild(c);
        c.setGlobalPosition(point);
        return c;
    }

    /** Does any live cloud's core stand between {@code a} and {@code b}? */
    public static boolean blocksSight(Vector3 a, Vector3 b) {
        for (SmokeCloud c : LIVE) {
            if (!GD.INSTANCE.isInstanceValid(c)) continue;
            double r = c.currentRadius() * SmokeRules.CORE_FRACTION;
            Vector3 o = c.centre();
            if (SmokeRules.segmentHitsSphere(a.getX(), a.getY(), a.getZ(), b.getX(), b.getY(), b.getZ(),
                                             o.getX(), o.getY(), o.getZ(), r)) return true;
        }
        return false;
    }

    public static int liveCount() { return LIVE.size(); }

    public double currentRadius() {
        return SmokeRules.radiusAt(age, radius, growSeconds, lifeSeconds, fadeSeconds);
    }

    public Vector3 centre() {
        return getGlobalPosition().plus(new Vector3(0.0, SmokeRules.CENTRE_LIFT, 0.0));
    }

    /** Probe readouts. */
    @Register
    public double radiusNow() { return currentRadius(); }
    @Register
    public boolean blocksSightNow(Vector3 a, Vector3 b) { return blocksSight(a, b); }

    @Register
    @Override
    public void _ready() {
        LIVE.add(this);
        if (ResourceLoader.load(VFX) instanceof PackedScene ps && ps.instantiate() instanceof Node3D fx) {
            addChild(fx);
            for (Node n : fx.getChildren()) {
                if (!(n instanceof GPUParticles3D p)) continue;
                if (!"Smoke".equals(p.getName().toString())) { p.queueFree(); continue; }   // no shadow caster: cost
                smoke = p;
            }
            if (smoke != null) shapeIntoCloud(smoke);
        }
    }

    /** The plume emitter turned into a dome: emitted through a sphere, drifting, long-lived, many particles. */
    private void shapeIntoCloud(GPUParticles3D p) {
        if (p.getProcessMaterial() instanceof ParticleProcessMaterial src
                && src.duplicate(false) instanceof ParticleProcessMaterial m) {
            m.setEmissionShape(ParticleProcessMaterial.EmissionShape.SPHERE);
            m.setEmissionSphereRadius((float) (radius * 0.55));
            m.setDirection(new Vector3(0.0, 1.0, 0.0));
            m.setSpread(180f);
            m.setParam(ParticleProcessMaterial.Parameter.INITIAL_LINEAR_VELOCITY, new godot.core.Vector2(0.2, 0.6));
            m.setGravity(new Vector3(0.0, 0.08, 0.0));
            p.setProcessMaterial(m);
        }
        // The pack's big plume is FIRE smoke (dark grey); a smoke grenade's is near-white. The material is shared
        // with the vehicle damage smoke, so this cloud tints its own copy.
        if (p.getMaterialOverride() instanceof godot.api.ShaderMaterial sm
                && sm.duplicate(false) instanceof godot.api.ShaderMaterial mine) {
            mine.setShaderParameter(new godot.core.StringName("primary_color"), new godot.core.Color(0.86, 0.86, 0.86, 1.0));
            mine.setShaderParameter(new godot.core.StringName("secondary_color"), new godot.core.Color(0.78, 0.78, 0.78, 1.0));
            mine.setShaderParameter(new godot.core.StringName("tertiary_color"), new godot.core.Color(0.58, 0.58, 0.58, 1.0));
            p.setMaterialOverride(mine);
        }
        p.setPosition(new Vector3(0.0, SmokeRules.CENTRE_LIFT, 0.0));
        p.setAmount(64);
        p.setLifetime(4.0);
        p.setEmitting(true);
    }

    @Register
    @Override
    public void _process(double delta) {
        age += delta;
        if (smoke != null) {
            double k = Math.max(0.15, currentRadius() / radius);
            smoke.setScale(new Vector3(k, k, k));
            if (age >= lifeSeconds - 1.0 && smoke.isEmitting()) smoke.setEmitting(false);
        }
        if (age >= lifeSeconds + 4.0) queueFree();   // the last particles drift out first
    }

    @Register
    @Override
    public void _exitTree() {
        LIVE.remove(this);
    }
}
