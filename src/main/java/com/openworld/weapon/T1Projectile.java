package com.openworld.weapon;

import com.openworld.world.manager.ExplosionManager;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
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
@RegisterClass(className = "T1Projectile")
public class T1Projectile extends RigidBody3D implements Detonatable {

    @Export @RegisterProperty public float fuseTime          = 3f;
    @Export @RegisterProperty public float explosionRadius    = 5f;
    @Export @RegisterProperty public float explosionMaxDamage = 80f;
    @Export @RegisterProperty public float explosionPushForce = 15f;

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

    @RegisterFunction
    @Override
    public void _ready() {
        fuseCountdown = fuseTime;
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (detonated) return;
        fuseCountdown -= (float) delta;
        if (fuseCountdown <= 0f) detonate();
    }

    @Override
    @RegisterFunction
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
                                     weaponDisplayName, weaponIcon, null);
            }
        }
        queueFree();
    }
}
