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
        // Walk the parent chain once to resolve surface type, health owner, and
        // character — previously done by three independent traversals per hit.
        HitContext ctx = resolveHitContext(info.hitNode);

        ParticleManager pm = getParticleManager();
        if (pm != null) pm.spawn(ctx.surface, info.hitPoint);

        DecalManager dm = getDecalManager();
        if (dm != null && info.hitNormal != null) dm.spawn(info.hitPoint, info.hitNormal);

        if (ctx.healthOwner != null) {
            Health health = (Health) ctx.healthOwner.getNode(new NodePath("Health"));
            health.takeDamage(info.hitNode, damage, weaponName, weaponIcon, attackerName, attackerFaction);
        }

        if (ctx.character != null && info.hitNormal != null) {
            ctx.character.applyHitImpulse(info.hitNode, info.hitNormal.times(-1f), damage);
        }
    }

    // ── Hit context resolution ────────────────────────────────────────────────

    private static class HitContext {
        final Character character;
        final Node                    healthOwner;
        final SurfaceType             surface;
        HitContext(Character c, Node h, SurfaceType s) {
            character = c; healthOwner = h; surface = s;
        }
    }

    /**
     * Walks the parent chain once to collect surface type, health owner, and character.
     * On a character hit all three resolve to the same ancestor — previously done by
     * three independent traversals in resolveSurfaceType / walkToHealthOwner / applyHitImpulse.
     *
     * getOwner() is not used because CharacterVisuals is added at runtime (addChild),
     * so bones inside it report CharacterVisuals as their owner, not the Character body.
     */
    private static HitContext resolveHitContext(Node hitNode) {
        if (hitNode == null) return new HitContext(null, null, SurfaceType.DEFAULT);
        Character character = null;
        Node healthOwner = null;
        SurfaceType surface = SurfaceType.DEFAULT;

        Node current = hitNode;
        while (current != null) {
            if (surface == SurfaceType.DEFAULT) {
                if (current instanceof Character c) {
                    surface = SurfaceType.FLESH;
                    character = c;
                } else if (current instanceof HittableBody hb) {
                    surface = hb.getSurfaceType();
                }
            } else if (character == null && current instanceof Character c) {
                character = c;
            }
            if (healthOwner == null && current.hasNode(new NodePath("Health"))) {
                healthOwner = current;
            }
            if (character != null && healthOwner != null && surface != SurfaceType.DEFAULT) break;
            current = current.getParent();
        }
        return new HitContext(character, healthOwner, surface);
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
