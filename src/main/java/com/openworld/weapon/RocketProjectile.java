package com.openworld.weapon;

import com.openworld.world.manager.ExplosionManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.api.Node3D;
import godot.core.Vector3;

/**
 * Self-propelled projectile spawned by ProjectileItem. Flies straight (gravity_scale = 0)
 * at constant speed and detonates on any body contact via the body_entered signal.
 *
 * Explosion parameters and attacker identity are injected by ProjectileItem at spawn time.
 * All blast effects (VFX + AOE damage + push) are delegated to ExplosionManager.
 *
 * Scene setup (RocketProjectile.tscn):
 *   RigidBody3D + RocketProjectile script
 *     gravity_scale = 0, continuous_cd = true
 *     contact_monitor = true, max_contacts_reported = 1
 *     collision_layer = 4, collision_mask = 1
 *     CollisionShape3D
 *     Mesh (MeshInstance3D)
 *   Connection: body_entered → on_body_entered (from "." to ".")
 */
@Script(className = "RocketProjectile")
public class RocketProjectile extends RigidBody3D implements Detonatable {

    /** Forward speed in m/s; overridden at spawn by ProjectileItem.projectileSpeed. */
    @Export public float speed = 25f;

    /** Blast radius (metres); overridden at spawn. */
    @Export public float explosionRadius = 8f;

    /** Max damage at epicentre; overridden at spawn. */
    @Export public float explosionMaxDamage = 120f;

    /** Radial push force; overridden at spawn. */
    @Export public float explosionPushForce = 20f;

    // Injected by ProjectileItem before the node enters the tree.
    public String    attackerName      = "";
    public String    attackerFaction   = "";
    public String    weaponDisplayName = "ATL-4";
    public Texture2D weaponIcon;

    /** Cosmetic puppet-replay copy: VFX only, no damage (see WeaponController.playRemoteFireCue). */
    public boolean cosmetic = false;

    private boolean detonated = false;

    // ── Physics ───────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (detonated) return;
        // Maintain constant forward speed along current facing direction.
        // Using globalBasis.getZ() * -speed keeps thrust stable after any deflection.
        setLinearVelocity(getGlobalBasis().getZ().times(-speed));
    }

    // ── Signal callback ───────────────────────────────────────────────────────

    /** Connected in RocketProjectile.tscn: body_entered from "." to "." method on_body_entered. */
    @Register
    public void onBodyEntered(Node3D body) {
        detonate();
    }

    // ── Detonatable ───────────────────────────────────────────────────────────

    @Override
    @Register
    public void detonate() {
        if (detonated || !isInsideTree()) return;
        detonated = true;
        Node m = getTree().getFirstNodeInGroup("explosion_manager");
        if (m instanceof ExplosionManager mgr) {
            if (cosmetic) {
                mgr.spawnExplosion(getGlobalPosition());   // VFX only — damage is authority-side
            } else {
                mgr.triggerExplosion(getGlobalPosition(), explosionRadius, explosionMaxDamage,
                                     explosionPushForce, attackerName, attackerFaction,
                                     weaponDisplayName, weaponIcon, this);
            }
        }
        queueFree();
    }
}
