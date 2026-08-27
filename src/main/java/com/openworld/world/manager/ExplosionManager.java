package com.openworld.world.manager;

import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.util.ObjectPool;
import com.openworld.world.StimulusManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.NodePath;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.List;

/**
 * World-level explosion manager: AOE damage + multi-layer VFX (flash, fireball, smoke).
 *
 * Call triggerExplosion() from any projectile or vehicle — no intermediate scene node needed.
 *
 * Scene setup (Godot editor):
 *   ExplosionManager (Node + this script)
 *     FLASH/    ← Node; one GPUParticles3D template (one_shot=true, ~0.3 s lifetime)
 *     FIREBALL/ ← Node; one GPUParticles3D template (one_shot=true, ~1.5 s lifetime)
 *     SMOKE/    ← Node; one GPUParticles3D template (one_shot=true, ~7–8 s lifetime)
 *
 * _ready() auto-duplicates each template to poolSizePerLayer instances.
 * Discovery group: "explosion_manager".
 */
@Script(className = "ExplosionManager")
public class ExplosionManager extends Node {

    @Export public int   poolSizePerLayer = 8;
    @Export public float flashLifetime    = 0.3f;
    @Export public float fireballLifetime = 1.5f;
    @Export public float smokeLifetime    = 8.0f;

    private static class ParticleEntry {
        final GPUParticles3D particle;
        double  age    = 0.0;
        boolean active = false;
        ParticleEntry(GPUParticles3D p) { this.particle = p; }
    }

    private final List<ParticleEntry> flashEntries    = new ArrayList<>();
    private final List<ParticleEntry> fireballEntries = new ArrayList<>();
    private final List<ParticleEntry> smokeEntries    = new ArrayList<>();

    private ObjectPool<ParticleEntry> flashPool;
    private ObjectPool<ParticleEntry> fireballPool;
    private ObjectPool<ParticleEntry> smokePool;

    private int activeCount = 0;

    @Register
    @Override
    public void _ready() {
        addToGroup("explosion_manager");
        flashPool    = buildPool("FLASH",    flashEntries);
        fireballPool = buildPool("FIREBALL", fireballEntries);
        smokePool    = buildPool("SMOKE",    smokeEntries);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (activeCount == 0) return;
        ageLayer(flashEntries,    flashPool,    flashLifetime,    delta);
        ageLayer(fireballEntries, fireballPool, fireballLifetime, delta);
        ageLayer(smokeEntries,    smokePool,    smokeLifetime,    delta);
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
        spawnExplosion(center);

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

    /** Spawn all three VFX layers at the given world position. */
    public void spawnExplosion(Vector3 center) {
        spawnLayer(flashPool,    center);
        spawnLayer(fireballPool, center);
        spawnLayer(smokePool,    center.plus(new Vector3(0f, 0.2f, 0f)));
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private void applyToCharacter(Character c, Vector3 center, float radius, float maxDamage,
                                   float pushForce, String attackerName, String attackerFaction,
                                   String weaponDisplayName, Texture2D weaponIcon) {
        float dist = (float) c.getGlobalPosition().distanceTo(center);
        if (dist >= radius) return;
        float t      = 1f - (dist / radius);
        float damage = maxDamage * t * t;
        Node h = c.getNodeOrNull(new NodePath("Health"));
        if (h instanceof Health health && !health.isDead()) {
            // Blast center is the damage source for the HUD direction indicator.
            health.takeDamage(c, damage, weaponDisplayName, weaponIcon, attackerName, attackerFaction, center);
        }
        if (c.isAlive()) {
            Vector3 pushDir = c.getGlobalPosition().minus(center).normalized();
            c.applyHitImpulse(c, pushDir, pushForce * t);
        }
    }

    private void applyToRigidBody(RigidBody3D rb, Vector3 center, float radius, float maxDamage,
                                   float pushForce, String attackerName, String attackerFaction,
                                   String weaponDisplayName, Texture2D weaponIcon) {
        float dist = (float) rb.getGlobalPosition().distanceTo(center);
        if (dist >= radius) return;
        float t      = 1f - (dist / radius);
        float damage = maxDamage * t * t;
        Node h = rb.getNodeOrNull(new NodePath("Health"));
        if (h instanceof Health health && !health.isDead()) {
            health.takeDamage(rb, damage, weaponDisplayName, weaponIcon, attackerName, attackerFaction);
        }
        rb.applyCentralImpulse(rb.getGlobalPosition().minus(center).normalized().times(pushForce * t));
    }

    private ObjectPool<ParticleEntry> buildPool(String containerName, List<ParticleEntry> entries) {
        Node container = getNodeOrNull(containerName);
        if (container == null || container.getChildCount() == 0) return null;
        Node first = container.getChild(0);
        if (!(first instanceof GPUParticles3D template)) return null;
        template.setEmitting(false);
        entries.add(new ParticleEntry(template));
        for (int i = 1; i < poolSizePerLayer; i++) {
            GPUParticles3D copy = (GPUParticles3D) template.duplicate(15);
            container.addChild(copy);
            entries.add(new ParticleEntry(copy));
        }
        int[] idx = {0};
        return new ObjectPool<>(entries.size(),
                () -> entries.get(idx[0]++),
                e -> { e.particle.setEmitting(false); e.age = 0.0; e.active = false; });
    }

    private void ageLayer(List<ParticleEntry> entries, ObjectPool<ParticleEntry> pool,
                           float lifetime, double delta) {
        if (pool == null) return;
        for (ParticleEntry e : entries) {
            if (!e.active) continue;
            e.age += delta;
            if (e.age >= lifetime) { activeCount--; pool.release(e); }
        }
    }

    private void spawnLayer(ObjectPool<ParticleEntry> pool, Vector3 position) {
        if (pool == null || pool.available() == 0) return;
        ParticleEntry e = pool.acquire();
        e.age = 0.0; e.active = true; activeCount++;
        e.particle.setGlobalPosition(position);
        e.particle.setEmitting(true);
    }
}
