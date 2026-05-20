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
  private CharacterBody3D owningCharacter;
  private RayCast3D aimRay3D;
  private CameraController cameraController;
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
   * Called by WeaponController after weapon discovery or pickup.
   * Provides all character-level references that cannot be resolved from inside the
   * weapon sub-scene. Pass null for all arguments to clear refs when returning to a pickup.
   */
  public void setup(CharacterBody3D character, RayCast3D aimRay, CameraController cam,
                    BoneAttachment3D neckAttachment, AudioStreamPlayer3D audio) {
    this.owningCharacter = character;
    this.aimRay3D = aimRay;
    this.cameraController = cam;
    this.muzzleFlashFx = neckAttachment != null ? (GPUParticles3D) neckAttachment.getNode("MuzzleFlash") : null;
    this.muzzleFlashAnimPlayer = neckAttachment != null ? (AnimationPlayer) neckAttachment.getNode("AnimationPlayer") : null;
    this.weaponAudio = audio;
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
    muzzleFlashFx.setSpeedScale(fireRate);
    muzzleFlashFx.setGlobalPosition(weaponMuzzle().getGlobalPosition());
    muzzleFlashAnimPlayer.setSpeedScale((float) GD.clamp(fireRate, 5, 10));
    muzzleFlashAnimPlayer.play("MuzzleFlash");
  }

  private void applyRecoil() {
    if (cameraController == null) return;
    float horizRecoil = (float) GD.randfRange(-recoil * 0.3f, recoil * 0.3f);
    cameraController.applyRecoil(recoil, horizRecoil);
  }

  private void performHitscan() {
    if (aimRay3D == null) return;

    // Player: apply angular spread + force update. Enemy: snapAimRay already
    // positioned the ray (with scatter baked in) — rotating it again would override that.
    boolean applySpread = owningCharacter instanceof Character c && c.useWeaponSpread;
    Vector3 savedRot = null;
    if (applySpread && spread > 0f) {
      savedRot = aimRay3D.getRotationDegrees();
      float halfSpread = getCurrentSpreadDeg() * 0.5f;
      // Circular cone: pick a random angle and a sqrt-distributed radius so
      // shots fill the disk uniformly (no diagonal bulge from a square pattern).
      double coneAngle  = GD.randfRange(0, (float)(2.0 * Math.PI));
      double coneRadius = Math.sqrt(GD.randf()) * halfSpread;
      float pitchOff = (float)(Math.cos(coneAngle) * coneRadius);
      float yawOff   = (float)(Math.sin(coneAngle) * coneRadius);
      aimRay3D.setRotationDegrees(new Vector3(savedRot.getX() + pitchOff, savedRot.getY() + yawOff, 0f));
      aimRay3D.forceRaycastUpdate();
    }

    if (aimRay3D.isColliding() &&
        aimRay3D.getCollisionPoint().minus(aimRay3D.getGlobalTransform().getOrigin()).length() > 0.1) {
      Object collider = aimRay3D.getCollider();
      Node hitNode = (collider instanceof Node n) ? n : null;
      ImpactManager im = getImpactManager();
      if (im != null) {
        HitInfo info = new HitInfo(hitNode, aimRay3D.getCollisionPoint(), aimRay3D.getCollisionNormal());
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
      aimRay3D.setRotationDegrees(savedRot);
    }

    spawnBulletTracer();
  }

  private void spawnBulletTracer() {
    Vector3 muzzlePos = weaponMuzzle().getGlobalPosition();
    Vector3 tracerEnd;
    if (aimRay3D.isColliding()) {
      tracerEnd = aimRay3D.getCollisionPoint();
    } else {
      Vector3 rayDir = aimRay3D.toGlobal(aimRay3D.getTargetPosition())
          .minus(aimRay3D.getGlobalPosition()).normalized();
      tracerEnd = muzzlePos.plus(rayDir.times(200f));
    }
    BulletTracerManager tm = getBulletTracerManager();
    if (tm != null) tm.spawnTracer(muzzlePos, tracerEnd);
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
