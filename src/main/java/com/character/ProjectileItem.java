package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Weapon that fires a physical projectile scene instead of hitscan.
 * Semi-auto only: one shot per trigger pull (auto = false in scene).
 *
 * Explosion radius/damage/pushForce are configured here and injected into each
 * RocketProjectile at spawn time. All blast logic (VFX + damage) is handled by
 * ExplosionManager — this class only spawns the projectile and plays weapon feedback.
 *
 * Scene setup (e.g. ATL4.tscn):
 *   RigidBody3D + ProjectileItem script
 *     CollisionShape3D   (layer 4, mask world layer 1)
 *     PickupArea (Area3D)
 *       CollisionShape3D (detection sphere, layer 0 / mask character layer 2)
 *     Muzzle (Marker3D)
 *       MuzzleVFX (instance MuzzleVFX.tscn)
 *   projectile_scene → RocketProjectile.tscn
 *   auto = false (semi-auto), magazine = 1, reserve = 3
 */
@RegisterClass(className = "ProjectileItem")
public class ProjectileItem extends WeaponItem {

    /** Physics scene to spawn on each shot. */
    @Export @RegisterProperty public PackedScene projectileScene;

    /** Speed injected into each spawned projectile (m/s). */
    @Export @RegisterProperty public float projectileSpeed = 25f;

    /** Explosion blast radius injected into each spawned projectile (metres). */
    @Export @RegisterProperty public float explosionRadius = 8f;

    /** Max damage at the epicentre injected into each spawned projectile. */
    @Export @RegisterProperty public float explosionMaxDamage = 120f;

    /** Push force applied to bodies in the blast, injected into each spawned projectile. */
    @Export @RegisterProperty public float explosionPushForce = 20f;

    private GPUParticles3D muzzleFlashFx;
    private AnimationPlayer muzzleFlashAnimPlayer;

    // Semi-auto lock: true while the trigger is held, cleared on stopUseWeapon.
    private boolean isWeaponFired = false;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        Node muzzle = getNodeOrNull("Muzzle");
        Node vfx    = (muzzle != null) ? muzzle.getNodeOrNull("MuzzleVFX") : null;
        if (vfx != null) {
            muzzleFlashFx         = (GPUParticles3D)  vfx.getNodeOrNull("MuzzleFlash");
            muzzleFlashAnimPlayer = (AnimationPlayer) vfx.getNodeOrNull("AnimationPlayer");
        }
    }

    // ── WeaponAction ──────────────────────────────────────────────────────────

    @Override public WeaponType getWeaponType()    { return WeaponType.RANGED; }
    @Override public float getCurrentSpreadDeg()   { return 0f; }

    /** Semi-auto lock: one shot per trigger pull. */
    @Override
    public boolean canUse() {
        return !isWeaponFired || auto;
    }

    @Override
    public void useWeapon() {
        isWeaponFired = true;
        decrementMagazine();
        playFireAudio();
        triggerMuzzleFlash();
        applyRecoil();
        spawnProjectile();
    }

    @Override
    public void stopUseWeapon() {
        isWeaponFired = false;
    }

    @Override
    public void onReloadComplete() {
        fillMagazine();
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private void playFireAudio() {
        if (weaponAudio == null || fireAudio == null) return;
        weaponAudio.stop();
        weaponAudio.setStream(fireAudio);
        weaponAudio.play();
    }

    private void triggerMuzzleFlash() {
        if (muzzleFlashFx == null || muzzleFlashAnimPlayer == null) return;
        muzzleFlashFx.setSpeedScale(fireRate);
        muzzleFlashAnimPlayer.setSpeedScale(5f);
        muzzleFlashAnimPlayer.play("MuzzleFlash");
    }

    private void applyRecoil() {
        if (!(owningCharacter instanceof Character c)) return;
        float horizRecoil = (float) GD.randfRange(-recoil * 0.3f, recoil * 0.3f);
        c.applyRecoil(recoil, horizRecoil);
    }

    private void spawnProjectile() {
        if (projectileScene == null || weaponController == null || owningCharacter == null) return;
        RayCast3D aimRay = weaponController.getAimRay();
        if (aimRay == null) return;

        // Spawn at Muzzle marker if present; fall back to character shoulder.
        Node muzzle = getNodeOrNull("Muzzle");
        Vector3 spawnPos = (muzzle instanceof Node3D m3d)
                ? m3d.getGlobalPosition()
                : owningCharacter.getGlobalPosition().plus(new Vector3(0f, 1.0f, 0f));

        // Aim direction: when the ray hits something, steer from muzzle → hit point so
        // the rocket converges exactly on the crosshair target (corrects muzzle offset).
        // When the ray misses (sky / max range), fall back to the raw ray direction.
        Vector3 aimDir;
        if (aimRay.isColliding()) {
            aimDir = aimRay.getCollisionPoint().minus(spawnPos).normalized();
        } else {
            Vector3 rayOrigin = aimRay.getGlobalPosition();
            Vector3 rayEnd    = aimRay.toGlobal(aimRay.getTargetPosition());
            aimDir = rayEnd.minus(rayOrigin).normalized();
        }

        Node projectile = projectileScene.instantiate();

        // Inject all parameters before the node enters the tree.
        if (projectile instanceof RocketProjectile rp) {
            rp.speed              = projectileSpeed;
            rp.explosionRadius    = explosionRadius;
            rp.explosionMaxDamage = explosionMaxDamage;
            rp.explosionPushForce = explosionPushForce;
            rp.attackerName       = resolveAttackerName();
            rp.attackerFaction    = resolveAttackerFaction();
            rp.weaponDisplayName  = getDisplayName();
            rp.weaponIcon         = weaponIcon;
        }

        getTree().getCurrentScene().addChild(projectile);

        if (projectile instanceof Node3D n3d) {
            n3d.setGlobalPosition(spawnPos);
            // Orient -Z (Godot forward) toward aim direction so _physicsProcess
            // constant-thrust formula globalBasis.getZ() * -speed stays aligned.
            n3d.lookAt(spawnPos.plus(aimDir));
        }
        // Initial velocity to start moving immediately before first _physicsProcess tick.
        if (projectile instanceof RigidBody3D rb) {
            rb.setLinearVelocity(aimDir.times(projectileSpeed));
        }
    }
}
