package com.openworld.world.manager;

import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.vfx.VfxEffect;
import com.openworld.world.BlastFalloff;
import com.openworld.world.StimulusManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.NodePath;
import godot.core.PackedVector3Array;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * World-level explosion manager: AOE damage + the blast VFX.
 *
 * Call triggerExplosion() from any projectile or vehicle — no intermediate scene node needed.
 *
 * The VFX is a Binbun3D explosion scene (CC0, {@code assets/vfx/explosion/effects/}, a {@link VfxEffect}).
 * Each explosive names its own ({@code explosion_vfx} + {@code explosion_vfx_scale} on the rocket, the grenade and
 * {@code VehicleConfig}), so the look follows its punch; one that names none gets {@link #explosionScene}.
 * Every effect scene has its own pool of up to {@link #poolSize}, grown on first use (the default one is warmed
 * in {@code _ready}); a blast plays the next idle instance or, if all are busy, the one that started longest ago,
 * so a burst of rockets never drops a blast.
 * Discovery group: "explosion_manager".
 */
@Script(className = "ExplosionManager")
public class ExplosionManager extends Node {

    /** The blast effect for an explosive that names none: any scene under assets/vfx/explosion/effects/. */
    @Export public PackedScene explosionScene;
    @Export public int poolSize = 8;
    /** Global multiplier on every blast's size (1 = each shockwave ends exactly at its damage radius). */
    @Export public float vfxScale = 1.0f;

    /** The fireball covers this share of the damage radius (the zone taking at least 25% of the maximum). */
    static final float FIREBALL_SHARE = 0.5f;

    private static final class Pool {
        final List<VfxEffect> fx = new ArrayList<>();
        int next = 0;
    }
    private final Map<PackedScene, Pool> pools = new HashMap<>();

    @Register
    @Override
    public void _ready() {
        addToGroup("explosion_manager");
        if (explosionScene == null) return;
        Pool p = pools.computeIfAbsent(explosionScene, k -> new Pool());
        for (int i = 0; i < poolSize; i++) {
            if (grow(explosionScene, p) == null) return;
        }
    }

    /**
     * Apply AOE damage/push to all characters within radius, then spawn VFX.
     * excludeNode is skipped in the damage scan (pass the vehicle or projectile
     * that triggered the explosion to prevent self-damage).
     */
    public void triggerExplosion(Vector3 center, float radius, float maxDamage, float pushForce,
                                 String attackerName, String attackerFaction,
                                 String weaponDisplayName, Texture2D weaponIcon,
                                 Node excludeNode) {
        triggerExplosion(center, radius, maxDamage, pushForce, attackerName, attackerFaction,
                         weaponDisplayName, weaponIcon, excludeNode, null, 1.0f);
    }

    /** As above, drawing {@code vfx} (null = {@link #explosionScene}) at {@code vfxScale}. */
    public void triggerExplosion(Vector3 center, float radius, float maxDamage, float pushForce,
                                 String attackerName, String attackerFaction,
                                 String weaponDisplayName, Texture2D weaponIcon,
                                 Node excludeNode, PackedScene vfx, float vfxScale) {
        for (Node node : getTree().getNodesInGroup("characters")) {
            if (node == excludeNode) continue;
            if (node instanceof Character c) {
                applyToCharacter(c, center, radius, maxDamage, pushForce,
                                 attackerName, attackerFaction, weaponDisplayName, weaponIcon);
            } else if (node instanceof RigidBody3D rb) {
                applyToRigidBody(rb, center, radius, maxDamage, pushForce,
                                 attackerName, attackerFaction, weaponDisplayName, weaponIcon);
            }
        }
        playBlast(center, vfx, radius, vfxScale);

        // EXPLOSION stimulus so nearby AI investigate the blast (PLAN.md E2). triggerExplosion is the
        // authority blast path, so this fires once on the simulating peer. Audible well past the blast
        // radius; faction "" means hostile-to-all (everyone reacts to an explosion).
        StimulusManager sm = StimulusManager.get();
        if (sm != null) {
            sm.post(StimulusManager.Type.EXPLOSION, center,
                    Math.max(radius * 3f, EXPLOSION_HEARING_RADIUS), excludeNode, attackerFaction);
        }
    }

    /** Default audible range of an explosion to AI (m) when 3× the blast radius is smaller. */
    private static final float EXPLOSION_HEARING_RADIUS = 300f;

    /** Play the default blast effect at the given world position. */
    @Register
    public void spawnExplosion(Vector3 center) {
        playBlast(center, null, 0f, 1.0f);
    }

    /**
     * Play {@code vfx} (null = {@link #explosionScene}) at {@code center}, sized to the blast from its damage radius
     * and the effect's MEASURED reach at scale 1 ({@link VfxEffect#fireballRadius} / {@link VfxEffect#blastRadius},
     * {@code tools/godot/measure_explosion_radii.gd}):
     * <ul>
     *   <li>the whole effect is scaled so the FIREBALL covers half the damage radius — the zone where a target
     *       still takes at least a quarter of the maximum damage (quadratic falloff);</li>
     *   <li>its shockwave layer ({@code Rings}) is scaled on its own on top of that, so the ring expands to exactly
     *       the damage radius: the player sees where the blast stops hurting.</li>
     * </ul>
     * Times {@code multiplier} and {@link #vfxScale}. A radius of 0 or an unmeasured effect plays at the multiplier
     * alone. The effect's particles are in local space, so node scale scales them (world-space particles ignore it).
     * The cosmetic path every peer runs: one per blast, never two.
     */
    public void playBlast(Vector3 center, PackedScene vfx, float damageRadius, float multiplier) {
        com.openworld.net.NetStats.increment("explosion_vfx");   // N4: one per blast on every peer, never two
        PackedScene scene = vfx != null ? vfx : explosionScene;
        if (scene == null) return;
        Pool p = pools.computeIfAbsent(scene, k -> new Pool());
        VfxEffect fx = null;
        for (int i = 0; i < p.fx.size() && fx == null; i++) {
            VfxEffect c = p.fx.get((p.next + i) % p.fx.size());
            if (!c.playingNow()) { fx = c; p.next = (p.next + i + 1) % p.fx.size(); }
        }
        if (fx == null && p.fx.size() < poolSize) fx = grow(scene, p);
        if (fx == null && !p.fx.isEmpty()) { fx = p.fx.get(p.next); p.next = (p.next + 1) % p.fx.size(); }
        if (fx == null) return;
        float s = vfxScale * multiplier;
        float ring = 1f;
        if (damageRadius > 0f && fx.fireballRadius > 0f) {
            s *= FIREBALL_SHARE * damageRadius / fx.fireballRadius;
            if (fx.blastRadius > 0f) ring = (damageRadius / fx.blastRadius) / (s / (vfxScale * multiplier));
        }
        fx.setScale(new Vector3(s, s, s));
        if (fx.getNodeOrNull("Rings") instanceof Node3D rings) rings.setScale(new Vector3(ring, ring, ring));
        fx.setGlobalPosition(center);
        fx.play();
    }


    /** Pool one more instance of {@code scene}; null if its root is not a VfxEffect. */
    private VfxEffect grow(PackedScene scene, Pool p) {
        if (!(scene.instantiate() instanceof VfxEffect fx)) {
            GD.pushWarning("ExplosionManager: " + scene.getPath() + "'s root is not a VfxEffect");
            return null;
        }
        addChild(fx);
        p.fx.add(fx);
        return fx;
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private void applyToCharacter(Character c, Vector3 center, float radius, float maxDamage,
                                   float pushForce, String attackerName, String attackerFaction,
                                   String weaponDisplayName, Texture2D weaponIcon) {
        double dist = distanceToBody(c, center);
        float t = BlastFalloff.strength(radius, dist);
        if (t <= 0f) return;
        Node h = c.getNodeOrNull(new NodePath("Health"));
        if (h instanceof Health health && !health.isDead()) {
            float damage = BlastFalloff.damage(maxDamage, radius, dist) * health.explosionDamageMultiplier;
            // Blast center is the damage source for the HUD direction indicator.
            health.takeDamage(c, damage, weaponDisplayName, weaponIcon, attackerName, attackerFaction, center);
        }
        // Alive: a stagger. Dead (including killed by THIS blast -- takeDamage above ragdolls the body
        // synchronously): the push goes into the ragdoll's bones, lifted a little so a blast throws
        // a body rather than sliding it along the floor (W35).
        Vector3 pushDir = c.getGlobalPosition().minus(center).normalized();
        if (!c.isAlive()) pushDir = pushDir.plus(new Vector3(0.0, 0.6, 0.0)).normalized();
        c.applyHitImpulse(c, pushDir, pushForce * t);
    }

    private void applyToRigidBody(RigidBody3D rb, Vector3 center, float radius, float maxDamage,
                                   float pushForce, String attackerName, String attackerFaction,
                                   String weaponDisplayName, Texture2D weaponIcon) {
        double dist = distanceToBody(rb, center);
        float t = BlastFalloff.strength(radius, dist);
        if (t <= 0f) return;
        Node h = rb.getNodeOrNull(new NodePath("Health"));
        if (h instanceof Health health && !health.isDead()) {
            float damage = BlastFalloff.damage(maxDamage, radius, dist) * health.explosionDamageMultiplier;
            health.takeDamage(rb, damage, weaponDisplayName, weaponIcon, attackerName, attackerFaction);
        }
        rb.applyCentralImpulse(rb.getGlobalPosition().minus(center).normalized().times(pushForce * t));
    }

    /**
     * Distance from the blast to the body's nearest SURFACE (0 inside it): the smallest distance to the box
     * of any of its own collision shapes (a BoxShape3D's box, a convex hull's point bounds), each in that
     * shape's frame. A body with neither falls back to its origin.
     */
    static double distanceToBody(Node3D body, Vector3 center) {
        double best = Double.MAX_VALUE;
        for (Node n : body.getChildren()) {
            if (!(n instanceof CollisionShape3D cs) || cs.isDisabled() || cs.getShape() == null) continue;
            Vector3 lo, hi;
            if (cs.getShape() instanceof BoxShape3D box) {
                Vector3 half = box.getSize().times(0.5);
                lo = half.times(-1.0);
                hi = half;
            } else if (cs.getShape() instanceof ConvexPolygonShape3D hull && hull.getPoints().getSize() > 0) {
                PackedVector3Array pts = hull.getPoints();
                lo = pts.get(0);
                hi = pts.get(0);
                for (int i = 1; i < pts.getSize(); i++) {
                    Vector3 v = pts.get(i);
                    lo = new Vector3(Math.min(lo.getX(), v.getX()), Math.min(lo.getY(), v.getY()), Math.min(lo.getZ(), v.getZ()));
                    hi = new Vector3(Math.max(hi.getX(), v.getX()), Math.max(hi.getY(), v.getY()), Math.max(hi.getZ(), v.getZ()));
                }
            } else {
                continue;
            }
            Vector3 p = cs.getGlobalTransform().affineInverse().times(center);
            best = Math.min(best, BlastFalloff.distanceToBox(p.getX(), p.getY(), p.getZ(),
                    lo.getX(), lo.getY(), lo.getZ(), hi.getX(), hi.getY(), hi.getZ()));
        }
        return best != Double.MAX_VALUE ? best : body.getGlobalPosition().distanceTo(center);
    }
}
