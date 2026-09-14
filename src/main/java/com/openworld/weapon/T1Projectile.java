package com.openworld.weapon;

import com.openworld.world.manager.ExplosionManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.Vector3;

/**
 * Physics projectile spawned by ThrowableItem. Bounces on world geometry via
 * RigidBody3D physics, then detonates after fuseTime seconds.
 *
 * Explosion parameters are scene-configured in T1Projectile.tscn.
 * Attacker identity is injected by ThrowableItem at throw-time.
 * Detonation delegates to ExplosionManager (group "explosion_manager").
 *
 * Scene setup (T1Projectile.tscn):
 *   RigidBody3D + T1Projectile script
 *     CollisionShape3D   (layer 3 / mask world(1); CCD enabled)
 *     MeshInstance3D     (optional visible mesh)
 */
@Script(className = "T1Projectile")
public class T1Projectile extends RigidBody3D implements Detonatable, CosmeticProjectile {

    @Export public float fuseTime          = 3f;
    @Export public float explosionRadius    = 5f;
    @Export public float explosionMaxDamage = 80f;
    @Export public float explosionPushForce = 15f;

    // Injected by ThrowableItem at throw-time
    public String    attackerName      = "";
    public String    attackerFaction   = "";
    public String    weaponDisplayName = "Grenade";
    public Texture2D weaponIcon;

    /**
     * Cosmetic copy spawned on non-authority peers (puppet replay of a remote throw — see
     * WeaponController.playRemoteFireCue): plays the explosion VFX but applies NO damage, so
     * every peer sees the grenade + blast while damage stays single-sourced on the authority.
     */
    public boolean cosmetic = false;

    private float   fuseCountdown = 0f;
    private boolean detonated     = false;

    /** The attacker's character id — what a host detonation names, and what a cosmetic copy is filed under. */
    public String attackerId = "";

    /** How long a cosmetic copy that detonated first waits for the host's point (PLAN.md N4). */
    private static final float HOST_WAIT_SECONDS = 0.5f;
    private float hostWaitLeft = -1f;
    private boolean exploded = false;

    @Register
    @Override
    public void _ready() {
        fuseCountdown = fuseTime;
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (tickHostWait(delta) || detonated) return;
        fuseCountdown -= (float) delta;
        if (fuseCountdown <= 0f) detonate();
    }

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
                                 weaponDisplayName, weaponIcon, null);
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
        if (m instanceof ExplosionManager mgr) mgr.spawnExplosion(point);
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
