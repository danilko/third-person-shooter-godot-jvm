package com.character;

import com.environment.BulletTracerManager;
import com.environment.HitInfo;
import com.environment.ImpactManager;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
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

  // Injected by WeaponController after weapon discovery
  private WeaponController weaponController;
  private CharacterBody3D owningCharacter;
  private GPUParticles3D muzzleFlashFx;
  private AnimationPlayer muzzleFlashAnimPlayer;
  private AudioStreamPlayer3D weaponAudio;

  // Lazy-resolved world managers
  private ImpactManager impactManager;
  private BulletTracerManager bulletTracerManager;

  private float currentBloom = 0f;
  private boolean isWeaponFired = false;
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
    Node muzzle = getNodeOrNull("Muzzle");
    Node vfx    = (muzzle != null) ? muzzle.getNodeOrNull("MuzzleVFX") : null;
    if (vfx != null) {
      muzzleFlashFx         = (GPUParticles3D)  vfx.getNodeOrNull("MuzzleFlash");
      muzzleFlashAnimPlayer = (AnimationPlayer) vfx.getNodeOrNull("AnimationPlayer");
    }
  }

  /**
   * Called by WeaponController after weapon discovery or pickup.
   * Every weapon is always owned by a WeaponController — character or vehicle.
   * Pass nulls to clear refs when returning to a world pickup.
   */
  public void setup(WeaponController controller, CharacterBody3D character, AudioStreamPlayer3D audio) {
    this.weaponController = controller;
    this.owningCharacter  = character;
    this.weaponAudio      = audio;
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
    playFireAudio();
    triggerMuzzleFlash();
    applyRecoil();
    currentBloom = Math.min(currentBloom + bloomPerShot, bloomMax);
    performHitscan();
  }

  @Override
  public void stopUseWeapon() {
    isWeaponFired = false;
  }

  @Override
  public void onReloadComplete() {
    fillMagazine();
  }

  /** True when the trigger can produce another shot (semi-auto lock check only). */
  @Override
  public boolean canUse() {
    return !isWeaponFired || auto;
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

    if (ray.isColliding() &&
        ray.getCollisionPoint().minus(ray.getGlobalTransform().getOrigin()).length() > 0.1) {
      Object collider = ray.getCollider();
      Node hitNode = (collider instanceof Node n) ? n : null;
      ImpactManager im = getImpactManager();
      if (im != null) {
        HitInfo info = new HitInfo(hitNode, ray.getCollisionPoint(), ray.getCollisionNormal());
        String attackerName;
        String attackerFaction;
        if (owningCharacter instanceof Character c && c.characterInfo != null) {
          attackerName    = c.characterInfo.displayName;
          attackerFaction = c.characterInfo.faction;
        } else {
          attackerName    = owningCharacter != null ? owningCharacter.getName().toString() : "";
          attackerFaction = "";
        }
        im.processHit(info, damage, getDisplayName(), weaponIcon, attackerName, attackerFaction);
      }
    }

    if (savedRot != null) {
      ray.setRotationDegrees(savedRot);
    }

    spawnBulletTracer(ray);
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

  private ImpactManager getImpactManager() {
    if (impactManager != null) return impactManager;
    Node found = getTree().getFirstNodeInGroup("impact_manager");
    if (found instanceof ImpactManager im) impactManager = im;
    return impactManager;
  }

  private BulletTracerManager getBulletTracerManager() {
    if (bulletTracerManager != null) return bulletTracerManager;
    Node found = getTree().getFirstNodeInGroup("bullet_tracer_manager");
    if (found instanceof BulletTracerManager tm) bulletTracerManager = tm;
    return bulletTracerManager;
  }
}
