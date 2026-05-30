package com.environment;

import com.character.Character;
import com.character.Health;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Node;
import godot.api.Texture2D;
import godot.core.NodePath;

/**
 * World-level singleton that resolves every bullet impact into its full consequences.
 *
 * WeaponController detects the hit (raycast → HitInfo) and calls processHit().
 * It knows nothing about surfaces, Health, particles, or decals.
 *
 * To add a new hit effect (sound, physics impulse, screen shake …):
 *   add a private method here and call it from processHit(). Nothing else changes.
 *
 * Network note: processHit() is a pure function of its arguments. With
 * CharacterInput.aimTargetPosition baked on the originating client (spread already
 * applied), every client replays the same call and reaches the same result.
 *
 * Discovery: registers itself in group "impact_manager".
 */
@RegisterClass(className = "ImpactManager")
public class ImpactManager extends Node {

    private ParticleManager particleManager;
    private DecalManager    decalManager;

    @RegisterFunction
    @Override
    public void _ready() {
        addToGroup("impact_manager");
    }

    /**
     * Resolve one bullet impact into all its consequences.
     *
     * @param info         hit geometry: node, world point, surface normal
     * @param damage       base damage from WeaponStats
     * @param weaponName   display name for kill notifications
     * @param weaponIcon   icon shown in kill feed (may be null)
     * @param attackerName display name for kill notifications
     */
    public void processHit(HitInfo info, float damage,
                           String weaponName, Texture2D weaponIcon,
                           String attackerName, String attackerFaction) {
        spawnImpactParticles(info);
        spawnDecal(info);
        applyDamage(info, damage, weaponName, weaponIcon, attackerName, attackerFaction);
        applyHitImpulse(info, damage);
    }

    // ── Private helpers (one per effect type) ────────────────────────────────

    private void spawnImpactParticles(HitInfo info) {
        ParticleManager pm = getParticleManager();
        if (pm == null) return;
        pm.spawn(resolveSurfaceType(info.hitNode), info.hitPoint);
    }

    private void spawnDecal(HitInfo info) {
        DecalManager dm = getDecalManager();
        if (dm == null || info.hitNormal == null) return;
        dm.spawn(info.hitPoint, info.hitNormal);
    }

    private void applyDamage(HitInfo info, float damage,
                             String weaponName, Texture2D weaponIcon,
                             String attackerName, String attackerFaction) {
        if (info.hitNode == null) return;
        // Walk up the parent chain looking for a node that owns a Health child.
        // getOwner() is not used here because CharacterVisuals is instantiated at
        // runtime (addChild), so bones inside it report CharacterVisuals as owner,
        // not the Character body that contains it.
        Node healthOwner = walkToHealthOwner(info.hitNode);
        if (healthOwner == null) return;
        Health health = (Health) healthOwner.getNode(new NodePath("Health"));
        health.takeDamage(info.hitNode, damage, weaponName, weaponIcon, attackerName, attackerFaction);
    }

    /**
     * Surface type priority:
     *   1. Character subclass        → FLESH  (automatic)
     *   2. HittableBody script       → reads surfaceType property directly
     *   3. Everything else           → DEFAULT
     *
     * Walks the parent chain instead of using getOwner() because CharacterVisuals
     * is instantiated at runtime, making getOwner() point to CharacterVisuals root
     * rather than the Character body.
     */
    private SurfaceType resolveSurfaceType(Node hitNode) {
        if (hitNode == null) return SurfaceType.DEFAULT;
        Node current = hitNode;
        while (current != null) {
            if (current instanceof Character)       return SurfaceType.FLESH;
            if (current instanceof HittableBody hb) return hb.getSurfaceType();
            current = current.getParent();
        }
        return SurfaceType.DEFAULT;
    }

    /**
     * Applies directional physics to the hit character.
     * hitNormal points from the surface toward the shooter, so negating it gives the
     * bullet travel direction — the direction the character should be pushed.
     * applyDamage() is called first, so if this hit killed the character the ragdoll
     * simulation is already running (died signal fires synchronously in takeDamage).
     */
    private void applyHitImpulse(HitInfo info, float damage) {
        if (info.hitNode == null || info.hitNormal == null) return;
        Node current = info.hitNode;
        while (current != null) {
            if (current instanceof Character character) {
                character.applyHitImpulse(info.hitNode, info.hitNormal.times(-1f), damage);
                return;
            }
            current = current.getParent();
        }
    }

    // Walk up the parent chain looking for the first node that has a direct "Health" child.
    private static Node walkToHealthOwner(Node start) {
        Node current = start;
        while (current != null) {
            if (current.hasNode(new NodePath("Health"))) return current;
            current = current.getParent();
        }
        return null;
    }

    // ── Lazy singleton lookups ────────────────────────────────────────────────

    private ParticleManager getParticleManager() {
        if (particleManager != null) return particleManager;
        Node found = getTree().getFirstNodeInGroup("particle_manager");
        if (found instanceof ParticleManager pm) particleManager = pm;
        return particleManager;
    }

    private DecalManager getDecalManager() {
        if (decalManager != null) return decalManager;
        Node found = getTree().getFirstNodeInGroup("decal_manager");
        if (found instanceof DecalManager dm) decalManager = dm;
        return decalManager;
    }
}
