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
public class RocketProjectile extends RigidBody3D implements Detonatable, CosmeticProjectile {

    /** Forward speed in m/s; overridden at spawn by ProjectileItem.projectileSpeed. */
    @Export public float speed = 25f;

    /** Blast radius (metres); overridden at spawn. */
    @Export public float explosionRadius = 8f;

    /** Max damage at epicentre; overridden at spawn. */
    @Export public float explosionMaxDamage = 120f;

    /** Radial push force; overridden at spawn. */
    @Export public float explosionPushForce = 20f;

    /** The blast effect this explosive draws (a scene under assets/vfx/explosion/effects/; null = the manager's). */
    @Export public godot.api.PackedScene explosionVfx;
    /** Extra size multiplier on the blast effect; at 1 its shockwave ends exactly at the damage radius (ExplosionManager.playBlast). */
    @Export public float explosionVfxScale = 1.0f;

    // Injected by ProjectileItem before the node enters the tree.
    public String    attackerName      = "";
    public String    attackerFaction   = "";
    public String    weaponDisplayName = "ATL-4";
    public Texture2D weaponIcon;

    /** Cosmetic puppet-replay copy: VFX only, no damage (see WeaponController.playRemoteFireCue). */
    public boolean cosmetic = false;

    private boolean detonated = false;

    /** The attacker's character id — what a host detonation names, and what a cosmetic copy is filed under. */
    public String attackerId = "";

    /** How long a cosmetic copy that detonated first waits for the host's point (PLAN.md N4). */
    private static final float HOST_WAIT_SECONDS = 0.5f;
    private float hostWaitLeft = -1f;
    private boolean exploded = false;

    // ── Physics ───────────────────────────────────────────────────────────────

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (tickHostWait(delta) || detonated) return;
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
        if (cosmetic) {
            // N4: a copy never explodes on its own word first — the host's point is what the damage used.
            awaitHostDetonation();
            return;
        }
        Node m = getTree().getFirstNodeInGroup("explosion_manager");
        if (m instanceof ExplosionManager mgr) {
            mgr.triggerExplosion(getGlobalPosition(), explosionRadius, explosionMaxDamage,
                                 explosionPushForce, attackerName, attackerFaction,
                                 weaponDisplayName, weaponIcon, this, explosionVfx, explosionVfxScale);
        }
        broadcastDetonation(getGlobalPosition());
        exploded = true;
        queueFree();
    }

    // ── N4: cosmetic copies explode where the HOST's projectile did ───────────

    /** A cosmetic copy reached its own detonation: hide, stop, and wait briefly for the host's point. */
    private void awaitHostDetonation() {
        setVisible(false);
        setFreezeEnabled(true);
        hostWaitLeft = HOST_WAIT_SECONDS;
    }

    /** The waiting copy's clock; on timeout it explodes where it is (a lost or late host detonation). */
    private boolean tickHostWait(double delta) {
        if (hostWaitLeft < 0f) return false;
        hostWaitLeft -= (float) delta;
        if (hostWaitLeft <= 0f && !exploded) {
            com.openworld.net.NetStats.increment("detonation_local_timeout");
            explodeVisual(getGlobalPosition());
        }
        return true;
    }

    @Override
    public void snapDetonate(Vector3 point) {
        if (exploded || !isInsideTree()) return;
        com.openworld.net.NetStats.increment("detonation_snapped");
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof com.openworld.net.NetworkManager net && net.debugShots) {
            godot.global.GD.INSTANCE.print(String.format("[launch] snapped %s by %.2f m", attackerId, getGlobalPosition().distanceTo(point)));
        }
        detonated = true;
        explodeVisual(point);
    }

    private void explodeVisual(Vector3 point) {
        exploded = true;
        Node m = getTree().getFirstNodeInGroup("explosion_manager");
        if (m instanceof ExplosionManager mgr) mgr.playBlast(point, explosionVfx, explosionRadius, explosionVfxScale);
        queueFree();
    }

    /** Host: tell every peer where this projectile went off, so their copies explode there too. */
    private void broadcastDetonation(Vector3 point) {
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof com.openworld.net.NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastDetonation(attackerId, point);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        ProjectileLedger.forget(this);
    }
}
