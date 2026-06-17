package com.character;

import com.environment.BulletTracerManager;
import com.environment.HitInfo;
import com.game.NetworkManager;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.api.Object;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Hitscan firearm. Owns: spread calculation, recoil, muzzle flash, fire audio,
 * and semi-auto lock.
 *
 * WeaponController injects character-level references via setup() during _ready(),
 * then orchestrates rate-limiting, reload timing, and HUD signals.
 */
@RegisterClass(className = "FirearmItem")
public class FirearmItem extends WeaponItem {

  private GPUParticles3D muzzleFlashFx;
  private AnimationPlayer muzzleFlashAnimPlayer;

  // Lazy-resolved world manager (ImpactManager is in WeaponItem base)
  private BulletTracerManager bulletTracerManager;

  private float currentBloom = 0f;
  /** Pellets per shot. 1 = single bullet (default). Set > 1 for shotguns — each
   *  pellet samples the spread cone independently; audio/bloom/recoil fire once. */
  @Export @RegisterProperty public int pelletCount = 1;

  private StanceName currentStance = StanceName.UPRIGHT;

  // Added to spread per m/s of horizontal+vertical speed before the stance multiplier,
  // so crouching/crawling reduces the movement penalty the same way it reduces base spread.
  private static final float MOVEMENT_SPREAD_PER_MPS = 0.03f;

  private static final float CROUCH_SPREAD_MULT = 0.7f;
  private static final float CRAWL_SPREAD_MULT  = 0.5f;
  private static final float JUMP_SPREAD_MULT   = 2.0f;

  /**
   * Discovers weapon-local VFX nodes from the weapon scene. Called once on _ready();
   * VFX live under Muzzle/MuzzleVFX and never change regardless of equip state.
   */
  @RegisterFunction
  @Override
  public void _ready() {
    super._ready();  // Pickup._ready — group + pickupId registration for replication
    Node muzzle = getNodeOrNull("Muzzle");
    Node vfx    = (muzzle != null) ? muzzle.getNodeOrNull("MuzzleVFX") : null;
    if (vfx != null) {
      muzzleFlashFx         = (GPUParticles3D)  vfx.getNodeOrNull("MuzzleFlash");
      muzzleFlashAnimPlayer = (AnimationPlayer) vfx.getNodeOrNull("AnimationPlayer");
    }
  }

  @RegisterFunction
  @Override
  public void _physicsProcess(double delta) {
    currentBloom = Math.max(0f, currentBloom - bloomDecaySpeed * (float) delta);
  }

  // -------------------------------------------------------------------------
  // WeaponAction
  // -------------------------------------------------------------------------

  @Override
  public void useWeapon() {
    isWeaponFired = true;
    decrementMagazine();
    playFireCue();
    applyRecoil();
    currentBloom = Math.min(currentBloom + bloomPerShot, bloomMax);
    for (int i = 0; i < pelletCount; i++) performHitscan();
  }

  /**
   * Cosmetic fire feedback only — audio + muzzle flash, no ammo/hitscan side effects.
   * Split out of {@link #useWeapon} so {@code WeaponController.playRemoteFireCue}
   * can replay the same cue on non-authority peers via NetworkManager.broadcastWeaponFire
   * without re-running hit detection (which stays local to the firing/authoritative peer).
   */
  public void playFireCue() {
    playFireAudio();
    triggerMuzzleFlash();
  }

  /** Visual length of a remote tracer when the peer has no local hit point — matches the no-collision fallback in {@link #spawnBulletTracer}. */
  private static final float REMOTE_TRACER_LENGTH = 200f;

  /**
   * Remote cosmetic replay (non-authority peers): muzzle flash + fire audio + a tracer drawn from
   * this puppet's own muzzle toward its replicated aim point. Triggered when the snapshot's fireSeq
   * counter changes (fire is replicated as state — see DecodedSnapshot.fireSeq). Never consumes ammo
   * or runs hitscan; damage is authority-only and resolved separately. Both the muzzle position and
   * the aim point are already replicated onto this puppet, so no per-shot origin/direction is sent.
   */
  public void playRemoteFireCue() {
    playFireCue();
    if (!(owningCharacter instanceof Character c)) return;
    Vector3 origin = weaponMuzzle().getGlobalPosition();
    Vector3 dir = c.getAimTargetPosition().minus(origin);
    if (dir.lengthSquared() < 1e-6f) return;
    BulletTracerManager tm = getBulletTracerManager();
    if (tm != null) {
      tm.spawnTracer(origin, origin.plus(dir.normalized().times(REMOTE_TRACER_LENGTH)));
    }
  }

  // stopUseWeapon() (clears the semi-auto lock) is inherited from WeaponItem.

  @Override
  public void onReloadComplete() {
    fillMagazine();
  }

  /** True when the trigger can produce another shot (semi-auto lock check only). */
  @Override
  public boolean canUse() {
    return isSemiAutoReady();
  }

  @Override
  public WeaponType getWeaponType() {
    return WeaponType.RANGED;
  }

  @Override
  public float getCurrentSpreadDeg() {
    if (owningCharacter == null) return 0f;
    float speed = (float) owningCharacter.getVelocity().length();
    return (spread + currentBloom + speed * MOVEMENT_SPREAD_PER_MPS) * stanceMultiplier(owningCharacter);
  }

  @Override
  public void onSetStance(Stance stance) {
    currentStance = StanceName.fromKey(String.valueOf(stance.getName()));
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  private void playFireAudio() {
    if (weaponAudio == null || fireAudio == null) return;
    weaponAudio.stop();
    weaponAudio.setStream(fireAudio);
    weaponAudio.play();
  }

  private void triggerMuzzleFlash() {
    if (muzzleFlashFx == null) return;
    // VFX nodes are children of the weapon's Muzzle marker — position is automatic.
    muzzleFlashFx.setSpeedScale(fireRate);
    muzzleFlashAnimPlayer.setSpeedScale((float) GD.clamp(fireRate, 5, 10));
    muzzleFlashAnimPlayer.play("MuzzleFlash");
  }

  private void applyRecoil() {
    if (!(owningCharacter instanceof Character c)) return;
    float horizRecoil = (float) GD.randfRange(-recoil * 0.3f, recoil * 0.3f);
    c.applyRecoil(recoil, horizRecoil);
  }

  private void performHitscan() {
    RayCast3D ray = getEffectiveAimRay();
    if (ray == null) return;

    // Player: apply angular spread + force update. Enemy: snapAimRay already
    // positioned the ray (with scatter baked in) — rotating it again would override that.
    boolean applySpread = owningCharacter instanceof Character c && c.useWeaponSpread;
    Vector3 savedRot = null;
    if (applySpread && spread > 0f) {
      savedRot = ray.getRotationDegrees();
      float halfSpread = getCurrentSpreadDeg() * 0.5f;
      // Circular cone: pick a random angle and a sqrt-distributed radius so
      // shots fill the disk uniformly (no diagonal bulge from a square pattern).
      double coneAngle  = GD.randfRange(0, (float)(2.0 * Math.PI));
      double coneRadius = Math.sqrt(GD.randf()) * halfSpread;
      float pitchOff = (float)(Math.cos(coneAngle) * coneRadius);
      float yawOff   = (float)(Math.sin(coneAngle) * coneRadius);
      ray.setRotationDegrees(new Vector3(savedRot.getX() + pitchOff, savedRot.getY() + yawOff, 0f));
      ray.forceRaycastUpdate();
    }

    boolean hit = ray.isColliding()
        && ray.getCollisionPoint().minus(ray.getGlobalTransform().getOrigin()).length() > 0.1;
    Node hitNode = (hit && ray.getCollider() instanceof Node n) ? n : null;

    if (isNetworkedClient()) {
      // Host-resolved bullets: predict the cosmetics here (muzzle/recoil/bloom/tracer already done),
      // but DON'T apply damage — send the post-spread ray to the host, which raycasts it against
      // authoritative positions and applies the damage. Show local impact VFX only (no Health touch).
      Vector3 origin = ray.getGlobalPosition();
      Vector3 dir = ray.toGlobal(ray.getTargetPosition()).minus(origin).normalized();
      sendShotToHost(origin, dir);
      if (hit) {
        var im = getImpactManager();
        if (im != null) im.processVisualHit(new HitInfo(hitNode, ray.getCollisionPoint(), ray.getCollisionNormal()));
      }
    } else if (hit) {
      // Server / single-player: resolve fully and locally (VFX + damage).
      var im = getImpactManager();
      if (im != null) {
        im.processHit(new HitInfo(hitNode, ray.getCollisionPoint(), ray.getCollisionNormal()),
                      damage, getDisplayName(), weaponIcon, resolveAttackerName(), resolveAttackerFaction());
      }
    }

    if (savedRot != null) {
      ray.setRotationDegrees(savedRot);
    }

    spawnBulletTracer(ray);
  }

  /**
   * Host-side resolution of a client's MSG_SHOT (Round 8 — "client-predicted + host-resolved").
   * Re-aims this weapon's AimRay along the client-reported world ray (post-spread already baked in,
   * so no extra spread here) and resolves the hit authoritatively — damage, impact VFX, tracer — then
   * restores the ray. Sign/rotation-agnostic: {@code toLocal} makes the cast land exactly on
   * {@code origin + dir*range} regardless of the ray's resting orientation. The AimRay already
   * excludes the shooter's own physical bones (Character._ready), so self-hits are impossible.
   */
  public void resolveServerShot(Vector3 origin, Vector3 direction) {
    RayCast3D ray = getEffectiveAimRay();
    if (ray == null || direction.lengthSquared() < 1e-6f) return;

    Vector3 savedPos = ray.getGlobalPosition();
    Vector3 savedTarget = ray.getTargetPosition();
    float range = (float) Math.max(50.0, savedTarget.length());

    ray.setGlobalPosition(origin);
    ray.setTargetPosition(ray.toLocal(origin.plus(direction.normalized().times(range))));
    ray.forceRaycastUpdate();

    if (ray.isColliding() && ray.getCollisionPoint().minus(origin).length() > 0.1) {
      Node hitNode = (ray.getCollider() instanceof Node n) ? n : null;
      var im = getImpactManager();
      if (im != null) {
        im.processHit(new HitInfo(hitNode, ray.getCollisionPoint(), ray.getCollisionNormal()),
                      damage, getDisplayName(), weaponIcon, resolveAttackerName(), resolveAttackerFaction());
      }
    }
    // No tracer here: this runs on the host for a client's shot, and the host's (and every other
    // viewer's) muzzle/tracer cue rides the shooter's snapshot fireSeq. Drawing one here too would
    // double the tracer on the host. Damage/impact above is the host's only job for a relayed shot.

    ray.setTargetPosition(savedTarget);
    ray.setGlobalPosition(savedPos);
  }

  /** True on a networked non-host peer — its firearm shots are predicted locally but resolved by the host. */
  private boolean isNetworkedClient() {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    return netNode instanceof NetworkManager net && net.isNetworked() && !net.isServer();
  }

  /** Sends this shot's post-spread ray to the host for authoritative resolution. */
  private void sendShotToHost(Vector3 origin, Vector3 direction) {
    if (!(owningCharacter instanceof Character c) || c.characterInfo == null || weaponController == null) return;
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (netNode instanceof NetworkManager net) {
      net.sendShot(c.characterInfo.characterId, origin, direction, weaponController.getWeapon());
    }
  }

  private void spawnBulletTracer(RayCast3D ray) {
    Vector3 muzzlePos = weaponMuzzle().getGlobalPosition();
    Vector3 rayOrigin = ray.getGlobalPosition();
    Vector3 rayDir    = ray.toGlobal(ray.getTargetPosition()).minus(rayOrigin).normalized();
    Vector3 tracerEnd = ray.isColliding() ? ray.getCollisionPoint()
                                          : rayOrigin.plus(rayDir.times(200f));
    BulletTracerManager tm = getBulletTracerManager();
    if (tm != null) tm.spawnTracer(muzzlePos, tracerEnd);
  }

  /**
   * Every weapon belongs to a WeaponController (character or vehicle) that owns the
   * authoritative AimRay. Reading it live means vehicle overrides, weapon switches,
   * and enter/exit transitions are all automatically transparent.
   */
  private RayCast3D getEffectiveAimRay() {
    return weaponController != null ? weaponController.getAimRay() : null;
  }

  private float stanceMultiplier(CharacterBody3D character) {
    if (!character.isOnFloor()) return JUMP_SPREAD_MULT;
    return switch (currentStance) {
      case CROUCH -> CROUCH_SPREAD_MULT;
      case CRAWL  -> CRAWL_SPREAD_MULT;
      default     -> 1.0f;
    };
  }

  private Marker3D weaponMuzzle() {
    return (Marker3D) getNode("Muzzle");
  }

  private BulletTracerManager getBulletTracerManager() {
    if (bulletTracerManager != null) return bulletTracerManager;
    Node found = getTree().getFirstNodeInGroup("bullet_tracer_manager");
    if (found instanceof BulletTracerManager tm) bulletTracerManager = tm;
    return bulletTracerManager;
  }
}
