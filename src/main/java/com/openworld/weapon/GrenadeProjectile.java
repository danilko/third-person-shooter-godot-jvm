package com.openworld.weapon;

import com.openworld.world.manager.ExplosionManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.RID;
import godot.core.Vector3;

/**
 * Every thrown projectile, spawned by ThrowableItem. It flies by {@link GrenadeFlight} -- CS 1.6's bounce,
 * not rigid-body physics (W38) -- as a KINEMATIC body, so it follows exactly the path the trajectory
 * preview drew, and goes off after fuseTime seconds. WHAT it does then is its scene's {@link #effect}
 * ({@link GrenadeEffect}): a frag blast (FRG1, PIB1), a flash (FLA1), a smoke cloud (SMO1), or -- for a remote
 * charge (REC1) -- nothing until its thrower's detonator: it sticks to the first surface it touches, has no fuse,
 * and waits in {@link RemoteCharges}.
 *
 * Parameters are scene-configured in each weapon's projectile scene (FRG1Projectile.tscn, FLA1Projectile.tscn, ...).
 * Attacker identity is injected by ThrowableItem at throw-time.
 * Detonation delegates to ExplosionManager (group "explosion_manager").
 *
 * Scene setup (FRG1Projectile.tscn):
 *   RigidBody3D + GrenadeProjectile script
 *     CollisionShape3D   (layer 3 / mask world(1); CCD enabled)
 *     MeshInstance3D     (optional visible mesh)
 */
@Script(className = "GrenadeProjectile")
public class GrenadeProjectile extends RigidBody3D implements Detonatable, CosmeticProjectile {

    @Export public float fuseTime          = 3f;
    @Export public float explosionRadius    = 5f;
    @Export public float explosionMaxDamage = 80f;
    @Export public float explosionPushForce = 15f;

    /** The blast effect this explosive draws (a scene under assets/vfx/explosion/effects/; null = the manager's). */
    @Export public godot.api.PackedScene explosionVfx;
    /** Extra size multiplier on the blast effect; at 1 its shockwave ends exactly at the damage radius (ExplosionManager.playBlast). */
    @Export public float explosionVfxScale = 1.0f;

    /** What it does when it goes off: "frag" (default), "flash", "smoke" or "remote" ({@link GrenadeEffect}). */
    @Export public String effect = "frag";
    /** FLASH: how far the flash blinds, metres, and the longest blindness (at point-blank, looking at it). */
    @Export public float flashRadius = DEFAULT_FLASH_RADIUS;
    @Export public float flashMaxSeconds = DEFAULT_FLASH_SECONDS;
    /** SMOKE: the cloud's radius, metres, and how long it lasts. */
    @Export public float smokeRadius = DEFAULT_SMOKE_RADIUS;
    @Export public float smokeSeconds = DEFAULT_SMOKE_SECONDS;

    public static final float DEFAULT_FLASH_RADIUS = 20f, DEFAULT_FLASH_SECONDS = 5f;
    public static final float DEFAULT_SMOKE_RADIUS = 5f, DEFAULT_SMOKE_SECONDS = 18f;

    public String getEffect() { return effect; }
    public void setEffect(String v) { effect = v; }
    public float getFlashRadius() { return flashRadius; }
    public void setFlashRadius(float v) { flashRadius = v; }
    public float getFlashMaxSeconds() { return flashMaxSeconds; }
    public void setFlashMaxSeconds(float v) { flashMaxSeconds = v; }
    public float getSmokeRadius() { return smokeRadius; }
    public void setSmokeRadius(float v) { smokeRadius = v; }
    public float getSmokeSeconds() { return smokeSeconds; }
    public void setSmokeSeconds(float v) { smokeSeconds = v; }

    /** The weapon id that threw it: the ledger's kind ({@link ProjectileLedger}). */
    public String kind = "";
    GrenadeEffect kindOfEffect() { return GrenadeEffect.parse(effect); }

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

    /** The launch velocity, set by ThrowableItem before the grenade enters the tree. */
    public Vector3 launchVelocity = new Vector3();
    /** The thrower, whom the flight never collides with. */
    public RID ignoreRid = null;
    private GrenadeFlight flight;

    @Register
    @Override
    public void _ready() {
        fuseCountdown = fuseTime;
        setFreezeMode(FreezeMode.KINEMATIC);
        setFreezeEnabled(true);
        if (kindOfEffect() == GrenadeEffect.REMOTE && !cosmetic) RemoteCharges.arm(attackerId, this);
    }

    /** A remote charge has stuck to what it hit. */
    private boolean stuck = false;

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (tickHostWait(delta) || detonated) return;
        if (flight == null) {
            godot.core.VariantArray<RID> ex = new godot.core.VariantArray<>(RID.class);
            ex.add(getRid());
            if (ignoreRid != null) ex.add(ignoreRid);
            flight = new GrenadeFlight(getGlobalPosition(), launchVelocity, ex);
        }
        if (stuck) return;                          // a stuck charge waits for its detonator
        flight.step(getWorld3d().getDirectSpaceState(), delta, gravity());
        setGlobalPosition(flight.position);
        if (kindOfEffect() == GrenadeEffect.REMOTE) {
            // Sticky: it stops on the first surface it touches (GTA's sticky bomb) and has no fuse.
            if (flight.contacts > 0) stuck = true;
            return;
        }
        fuseCountdown -= (float) delta;
        if (fuseCountdown <= 0f) detonate();
    }

    /** Surfaces touched so far, and whether it has stopped -- probe readouts. */
    @Register
    public int contactsNow() { return flight != null ? flight.contacts : 0; }
    @Register
    public boolean restingNow() { return flight != null && flight.resting; }
    @Register
    public boolean stuckNow() { return stuck; }

    /** The project's gravity: the one number the flight and the preview both fall under. */
    public static double gravity() {
        return ((Number) ProjectSettings.getSetting("physics/3d/default_gravity", 9.8)).doubleValue();
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
        GrenadeEffect fx = kindOfEffect();
        Vector3 at = getGlobalPosition();
        if (fx.blasts()) {
            Node m = getTree().getFirstNodeInGroup("explosion_manager");
            if (m instanceof ExplosionManager mgr) {
                mgr.triggerExplosion(at, explosionRadius, explosionMaxDamage,
                                     explosionPushForce, attackerName, attackerFaction,
                                     weaponDisplayName, weaponIcon, null, explosionVfx, explosionVfxScale);
            }
        } else {
            playEffect(fx, at, true);
        }
        broadcastDetonation(at);
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
        GrenadeEffect fx = kindOfEffect();
        if (fx.blasts()) {
            Node m = getTree().getFirstNodeInGroup("explosion_manager");
            if (m instanceof ExplosionManager mgr) mgr.playBlast(point, explosionVfx, explosionRadius, explosionVfxScale);
        } else {
            playEffect(fx, point, false);
        }
        queueFree();
    }

    /**
     * A flash or a smoke cloud at {@code point}. {@code authority}: this peer simulates the AI (the host, or single
     * player), so a flash blinds AI too; every peer blinds its own player and draws the light and the cloud.
     */
    private void playEffect(GrenadeEffect fx, Vector3 point, boolean authority) {
        if (fx == GrenadeEffect.FLASH) {
            com.openworld.world.FlashBang.detonate(this, point, flashRadius, flashMaxSeconds, authority);
        } else if (fx == GrenadeEffect.SMOKE) {
            com.openworld.world.SmokeCloud.spawn(this, point, smokeRadius, smokeSeconds);
        }
    }

    /**
     * A peer that received a host detonation with no local copy to snap (never spawned, or it already timed out)
     * still draws it, from the effect alone, at the default sizes.
     */
    public static void playEffectAt(Node context, GrenadeEffect fx, Vector3 point) {
        if (context == null || context.getTree() == null) return;
        Node scene = context.getTree().getCurrentScene();
        switch (fx) {
            case FLASH -> com.openworld.world.FlashBang.detonate(scene, point, DEFAULT_FLASH_RADIUS, DEFAULT_FLASH_SECONDS, false);
            case SMOKE -> com.openworld.world.SmokeCloud.spawn(context, point, DEFAULT_SMOKE_RADIUS, DEFAULT_SMOKE_SECONDS);
            default -> {
                if (context.getTree().getFirstNodeInGroup("explosion_manager") instanceof ExplosionManager mgr) mgr.spawnExplosion(point);
            }
        }
    }

    /** Host: tell every peer where this projectile went off, so their copies explode there too. */
    private void broadcastDetonation(Vector3 point) {
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (netNode instanceof com.openworld.net.NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastDetonation(attackerId, kind, kindOfEffect().ordinal(), point);
        }
    }

    @Register
    @Override
    public void _exitTree() {
        ProjectileLedger.forget(this);
        RemoteCharges.forget(this);
    }
}
