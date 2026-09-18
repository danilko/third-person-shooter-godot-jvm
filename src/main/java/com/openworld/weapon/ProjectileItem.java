package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.character.Character;
import com.openworld.item.Pickup;
import com.openworld.world.manager.ExplosionManager;

/**
 * Weapon that fires a physical projectile scene instead of hitscan.
 * Semi-auto only: one shot per trigger pull (auto = false in scene).
 *
 * Explosion radius/damage/pushForce are configured here and injected into each
 * RocketProjectile at spawn time. All blast logic (VFX + damage) is handled by
 * ExplosionManager — this class only spawns the projectile and plays weapon feedback.
 *
 * Scene setup (e.g. ATL1.tscn):
 *   Node3D + ProjectileItem script
 *     CollisionShape3D   (the WORLD body's shape — lent to the PickupBody built at drop time;
 *                         the layer/mask live on that body, not here)
 *     PickupArea (Area3D)
 *       CollisionShape3D (detection sphere, layer 0 / mask character layer 2)
 *     Muzzle (Marker3D)
 *       MuzzleVFX (a muzzle flash from assets/vfx/muzzle_flash/effects, MuzzleFlashVfx)
 *   projectile_scene → RocketProjectile.tscn
 *   auto = false (semi-auto), magazine = 1, reserve = 3
 */
@Script(className = "ProjectileItem")
public class ProjectileItem extends WeaponItem {

    /** Physics scene to spawn on each shot. */
    @Export public PackedScene projectileScene;

    /** Speed injected into each spawned projectile (m/s). */
    @Export public float projectileSpeed = 25f;

    /** Explosion blast radius injected into each spawned projectile (metres). */
    @Export public float explosionRadius = 8f;

    /** Max damage at the epicentre injected into each spawned projectile. */
    @Export public float explosionMaxDamage = 120f;

    /** Push force applied to bodies in the blast, injected into each spawned projectile. */
    @Export public float explosionPushForce = 20f;



    // ── WeaponAction ──────────────────────────────────────────────────────────

    @Override public WeaponType getWeaponType()    { return WeaponType.RANGED; }
    @Override public float getCurrentSpreadDeg()   { return 0f; }

    /** A rocket leaves the muzzle toward the aim point, so the launcher must be pointing at it. */
    @Override protected boolean launchesTowardAim() { return true; }

    /** Semi-auto lock: one shot per trigger pull. */
    @Override
    public boolean canUse() {
        return isSemiAutoReady();
    }

    @Override
    public void useWeapon() {
        isWeaponFired = true;
        decrementMagazine();
        playFireAudio();
        playMuzzleFlash();
        applyRecoil();
        Vector3[] in = launchInputs();
        if (in == null) return;
        // N4: a client predicts a cosmetic rocket and the host flies the one that damages.
        if (NetRole.client(this)) {
            sendLaunchToHost(in[0], in[1]);
            launch(in[0], in[1], true);
        } else {
            launch(in[0], in[1], false);
        }
    }

    /**
     * Puppet replay of a remote launch (Round 11 — WeaponController.playRemoteFireCue):
     * fire audio + muzzle flash + a COSMETIC rocket aimed at the replicated aim point, so
     * every peer sees the rocket fly and explode. No ammo, no recoil, no damage — all
     * authority-side.
     */
    @Override
    public void playRemoteFireCue() {
        playFireAudio();
        playMuzzleFlash();
        // N4: on the host this puppet's real rocket arrives as MSG_LAUNCH — a cue copy would be a second rocket.
        if (NetRole.host(this)) { com.openworld.net.NetStats.increment("launch_cue_host_skipped"); return; }
        Vector3[] in = launchInputs();
        if (in != null) launch(in[0], in[1], true);
    }

    /** Host: fly a client's validated launch as the authoritative rocket (PLAN.md N4). */
    public void launchFrom(Vector3 origin, Vector3 aim) {
        launch(origin, aim, false);
    }

    private void sendLaunchToHost(Vector3 origin, Vector3 aim) {
        com.openworld.net.NetworkManager net = NetRole.net(this);
        if (net == null || weaponController == null || !(owningCharacter instanceof Character c) || c.characterInfo == null) return;
        net.sendLaunch(c.characterInfo.characterId, weaponController.getWeapon(), weaponController.nextShotSeq(), origin, aim);
    }

    private String attackerId() {
        return owningCharacter instanceof Character c && c.characterInfo != null ? c.characterInfo.characterId : "";
    }

    // stopUseWeapon() (clears the semi-auto lock) is inherited from WeaponItem.

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


    private void applyRecoil() {
        if (!(owningCharacter instanceof Character c)) return;
        float horizRecoil = (float) GD.randfRange(-recoil * 0.3f, recoil * 0.3f);
        c.applyRecoil(recoil, horizRecoil);
    }

    /** `[origin, aim]` of a launch from this weapon now, or null when there is no aim — derived identically on
     *  every peer (see below), and what a client reports in MSG_LAUNCH. */
    private Vector3[] launchInputs() {
        if (projectileScene == null || owningCharacter == null) return null;

        // Spawn geometry is derived IDENTICALLY on every peer — authority and puppet alike — so the
        // rocket leaves the barrel along the same line for the shooter and every observer. Origin is
        // the weapon's own Muzzle marker; direction is the replicated aim point (getAimTargetPosition,
        // the same value that drives spine IK and rides in every snapshot). This matches
        // FirearmItem.playRemoteFireCue's convention. Only damage differs by `cosmetic`, never the
        // trajectory — previously authority used Muzzle+aimRay while the puppet used chest+aimTarget,
        // and that divergence (not the collision layer) is what made the sync-side rocket misbehave.
        Node muzzle = getNodeOrNull("Muzzle");
        Vector3 spawnPos = (muzzle instanceof Node3D m3d)
                ? m3d.getGlobalPosition()
                : owningCharacter.getGlobalPosition().plus(new Vector3(0f, 1.4f, 0f));

        Vector3 aimDir;
        if (owningCharacter instanceof Character c) {
            Vector3 dir = c.getAimTargetPosition().minus(spawnPos);
            if (dir.lengthSquared() < 1e-6f) return null;
            aimDir = dir.normalized();
        } else if (muzzle instanceof Node3D m3d) {
            aimDir = m3d.getGlobalBasis().getZ().times(-1f).normalized();  // muzzle forward (-Z)
        } else {
            return null;
        }
        return new Vector3[] {spawnPos, aimDir};
    }

    private void launch(Vector3 spawnPos, Vector3 aimDir, boolean cosmetic) {
        if (projectileScene == null || owningCharacter == null || aimDir.lengthSquared() < 1e-6f) return;
        aimDir = aimDir.normalized();
        Node projectile = projectileScene.instantiate();

        // Inject all parameters before the node enters the tree.
        if (projectile instanceof RocketProjectile rp) {
            rp.speed              = projectileSpeed;
            rp.cosmetic           = cosmetic;
            rp.explosionRadius    = explosionRadius;
            rp.explosionMaxDamage = explosionMaxDamage;
            rp.explosionPushForce = explosionPushForce;
            rp.attackerId         = attackerId();
            if (!cosmetic) {
                rp.attackerName       = resolveAttackerName();
                rp.attackerFaction    = resolveAttackerFaction();
                rp.weaponDisplayName  = getDisplayName();
                rp.weaponIcon         = weaponIcon;
            }
        }

        getTree().getCurrentScene().addChild(projectile);
        if (cosmetic) ProjectileLedger.register(attackerId(), projectile);

        if (projectile instanceof Node3D n3d) {
            n3d.setGlobalPosition(spawnPos);
            // Orient -Z (Godot forward) toward aim direction so _physicsProcess
            // constant-thrust formula globalBasis.getZ() * -speed stays aligned.
            n3d.lookAt(spawnPos.plus(aimDir));
        }
        // Initial velocity to start moving immediately before first _physicsProcess tick.
        if (projectile instanceof RigidBody3D rb) {
            rb.setLinearVelocity(aimDir.times(projectileSpeed));
            // Correctness guard (secondary to the unified spawn above): a weapon never collides
            // with / detonates on its own shooter. The rocket's mask includes the character layer,
            // so this covers point-blank / against-a-wall edges where the muzzle sits near the body.
            if (owningCharacter != null) rb.addCollisionExceptionWith(owningCharacter);
        }
    }
}
