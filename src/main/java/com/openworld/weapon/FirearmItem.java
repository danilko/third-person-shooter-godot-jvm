package com.openworld.weapon;

import com.openworld.world.manager.BulletTracerManager;
import com.openworld.world.HitInfo;
import com.openworld.net.NetworkManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.api.Object;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.item.Pickup;
import com.openworld.movement.character.Stance;
import com.openworld.movement.character.StanceName;
import com.openworld.world.manager.ImpactManager;
import com.openworld.world.StimulusManager;
import com.openworld.world.SurfaceType;
import com.openworld.net.NetStats;

/**
 * Hitscan firearm. Owns: spread calculation, recoil, muzzle flash, fire audio,
 * and semi-auto lock.
 *
 * WeaponController injects character-level references via setup() during _ready(),
 * then orchestrates rate-limiting, reload timing, and HUD signals.
 */
@Script(className = "FirearmItem")
public class FirearmItem extends WeaponItem {

  private GPUParticles3D muzzleFlashFx;
  private AnimationPlayer muzzleFlashAnimPlayer;

  /** How far this shot is audible to AI (PLAN.md E2 — ~150 m urban, raise toward ~400 m for open terrain). */
  @Export public float gunshotHearingRadius = 150f;

  // Lazy-resolved world manager (ImpactManager is in WeaponItem base)
  private BulletTracerManager bulletTracerManager;

  private float currentBloom = 0f;
  /** Pellets per shot. 1 = single bullet (default). Set > 1 for shotguns — each
   *  pellet samples the spread cone independently; audio/bloom/recoil fire once. */
  @Export public int pelletCount = 1;

  /**
   * Two-stage ("2-way") hit resolution. When true (the default) a bullet is traced from the weapon's
   * own {@code Muzzle} marker toward the point the sight ray is on, instead of straight out of the
   * camera. In third person the camera sits above/behind the shoulder, so a single camera-origin
   * trace let a character standing fully behind cover hit anything the camera could peek at over it.
   * The second leg starts at the gun, so the cover the character is visibly hiding behind blocks the
   * shot — while the bullet still converges on the crosshair. Set false for the legacy
   * camera-origin trace.
   */
  @Export public boolean muzzleTrace = true;

  private StanceName currentStance = StanceName.UPRIGHT;

  // Added to spread per m/s of horizontal+vertical speed before the stance multiplier,
  // so crouching/crawling reduces the movement penalty the same way it reduces base spread.
  private static final float MOVEMENT_SPREAD_PER_MPS = 0.03f;

  private static final float CROUCH_SPREAD_MULT = 0.7f;
  private static final float CRAWL_SPREAD_MULT  = 0.5f;
  private static final float JUMP_SPREAD_MULT   = 2.0f;
  // Treading water is unstable — surface shooting is deliberately less accurate than on land
  // (GTA/PUBG). Explicit so it no longer relies on the incidental !isOnFloor() airborne branch.
  private static final float SWIM_SPREAD_MULT   = 1.8f;

  /**
   * Discovers weapon-local VFX nodes from the weapon scene. Called once on _ready();
   * VFX live under Muzzle/MuzzleVFX and never change regardless of equip state.
   */
  @Register
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

  @Register
  @Override
  public void _physicsProcess(double delta) {
    currentBloom = Math.max(0f, currentBloom - bloomDecaySpeed * (float) delta);
    if (fallbackTracerAtMs > 0 && Time.INSTANCE.getTicksMsec() >= fallbackTracerAtMs) {
      fallbackTracerAtMs = 0;
      drawAimTracer();
    }
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
    fireShot();
    postGunshotStimulus();
  }

  /**
   * Drop a GUNSHOT stimulus at the muzzle so nearby patrolling AI investigate (PLAN.md E2). Runs only
   * on the authority fire path ({@link #useWeapon}, not the puppet {@code playRemoteFireCue}), so the
   * host — which simulates the AI — sees the event. No-op without the StimulusManager AutoLoad.
   */
  private void postGunshotStimulus() {
    StimulusManager sm = StimulusManager.get();
    if (sm == null) return;
    String faction = (owningCharacter instanceof Character c && c.characterInfo != null)
        ? c.characterInfo.faction : "";
    sm.post(StimulusManager.Type.GUNSHOT, weaponMuzzle().getGlobalPosition(),
        gunshotHearingRadius, owningCharacter, faction);
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
    // E2 networked perception: this runs on every non-authority peer when a puppet's replicated
    // fireSeq bumps. On the HOST (which simulates the AI) a puppet is a remote *client's* character —
    // turn its shot into a GUNSHOT stimulus so host AI hear client gunfire too (the gap E2 left).
    // Other clients also run this but don't post (their AI are puppets that never poll). Reuses the
    // existing fire replication — no new network message.
    if (isServerPeer()) postGunshotStimulus();
    // The TRACER is no longer the cue's (N1b): the real pellets arrive as a shot result (a client) or
    // are resolved here (the host). The cue and the result travel on different channels and either
    // may land first, so the cue's single aim tracer is only a FALLBACK — drawn if no result has come
    // in RESULT_WAIT_MS, skipped if one came in just before.
    long now = Time.INSTANCE.getTicksMsec();
    if (now - lastShotResultMs < CUE_AFTER_RESULT_MS) {
      NetStats.increment("cue_tracer_superseded");
      return;
    }
    fallbackTracerAtMs = now + RESULT_WAIT_MS;
  }

  /** How long a fire cue waits for its shot result before drawing the aim tracer instead (N1b). */
  private static final long RESULT_WAIT_MS = 150;
  /**
   * How recent a result must be for an arriving cue to count as ITS cue, already drawn. Longer than
   * the wait: the cue rides the 30 Hz snapshot relay (client → host → peer) and was measured arriving
   * over 150 ms after its own result under a four-process headless load, which drew a spurious second
   * tracer. The cost is cosmetic and bounded — a result LOST within this window of the previous one
   * (sustained auto fire) draws no tracer for that one shot.
   */
  private static final long CUE_AFTER_RESULT_MS = 300;
  private long lastShotResultMs = -100_000;
  private long fallbackTracerAtMs = 0;

  /** The cue's fallback: one tracer from this puppet's muzzle toward its replicated aim point. */
  private void drawAimTracer() {
    if (!(owningCharacter instanceof Character c)) return;
    Vector3 origin = weaponMuzzle().getGlobalPosition();
    Vector3 dir = c.getAimTargetPosition().minus(origin);
    if (dir.lengthSquared() < 1e-6f) return;
    NetStats.increment("cue_fallback_tracer");
    BulletTracerManager tm = getBulletTracerManager();
    if (tm != null) {
      tm.spawnTracer(origin, origin.plus(dir.normalized().times(REMOTE_TRACER_LENGTH)));
    }
  }

  /**
   * A peer replaying a host-resolved pull (PLAN.md N1b): one tracer per pellet from this puppet's own
   * muzzle to where the host found that pellet stopped, and the impact visuals for each hit on the
   * surface the host reported. Cancels the fire cue's pending fallback tracer.
   */
  public void playRemoteShotResult(com.openworld.net.NetMessageCodec.ShotResult result) {
    lastShotResultMs = Time.INSTANCE.getTicksMsec();
    if (fallbackTracerAtMs > 0) NetStats.increment("cue_tracer_waited_for_result");
    fallbackTracerAtMs = 0;
    Vector3 muzzle = weaponMuzzle().getGlobalPosition();
    BulletTracerManager tm = getBulletTracerManager();
    var im = getImpactManager();
    SurfaceType[] surfaces = SurfaceType.values();
    for (var p : result.pellets()) {
      NetStats.increment("shot_result_tracer");
      if (tm != null) tm.spawnTracer(muzzle, p.end());
      if (p.kind() > 0 && im != null) {
        im.processVisualImpact(surfaces[Math.min(p.kind() - 1, surfaces.length - 1)], p.end(), p.normal());
      }
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

  /**
   * The narrowest cone this weapon can have in its holder's current stance: base spread × the stance
   * multiplier, with no movement, no bloom and no airborne penalty (PLAN.md N1). The host validates a
   * client's reported cone against THIS rather than {@link #getCurrentSpreadDeg()}: a host puppet is
   * never simulated onto the floor, so the live estimate carries the airborne ×2 and would refuse an
   * honest crouched shot, while bloom — the one term that only widens — never exists on the host copy.
   */
  public float minimumSpreadDeg() {
    if (currentStance == StanceName.SWIM) return spread * SWIM_SPREAD_MULT;
    return switch (currentStance) {
      case CROUCH -> spread * CROUCH_SPREAD_MULT;
      case CRAWL  -> spread * CRAWL_SPREAD_MULT;
      default     -> spread;
    };
  }

  /** Reference movement speed (m/s ≈ sprint) defining the top of the crosshair spread envelope. */
  private static final float CROSSHAIR_REF_SPEED = 6.0f;

  @Override
  public float getCrosshairFraction() {
    // Worst realistic on-ground spread for THIS weapon: full bloom + reference movement, upright. The
    // current spread is shown as a fraction of this, so every weapon shares one fixed crosshair pixel
    // range (no per-weapon tuning) and a wide-cone weapon (shotgun) caps at the top instead of running
    // off-screen — while movement/bloom still move the reticle visibly across the range. Airborne /
    // jumping spread exceeds this envelope and simply clamps to 1 (max openness — you're least accurate).
    float worst = spread + bloomMax + CROSSHAIR_REF_SPEED * MOVEMENT_SPREAD_PER_MPS;
    if (worst <= 0f) return 0f;
    float frac = getCurrentSpreadDeg() / worst;
    return frac < 0f ? 0f : (frac > 1f ? 1f : frac);
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

  // ── Two-stage ("2-way") hit resolution ─────────────────────────────────────
  // Stage 1 (sight)  — the camera AimRay (player) or the ray AttackState already snapped onto its
  //                    scatter point (AI) says WHERE this shot is aimed.
  // Stage 2 (muzzle) — the bullet is traced from the gun to that point, so geometry between the
  //                    weapon and the target stops it. A shot the shooter's own cover blocks now
  //                    hits that cover, instead of leaving the camera on the free side of the wall.

  /** Below this the muzzle counts as co-located with the body and the clearance trace is skipped. */
  private static final float MUZZLE_CLEARANCE_MIN = 0.05f;
  /** Tracer length when the shot hits nothing (matches REMOTE_TRACER_LENGTH's convention). */
  private static final float TRACER_MISS_LENGTH = 200f;

  /**
   * One trigger pull (PLAN.md N1): resolve the sight point, the origin, the PRE-spread aim and the cone
   * once, then derive every pellet from a seed ({@link SpreadPattern}). A networked client predicts the
   * cosmetics and sends the host ONE message carrying exactly those inputs; the host regenerates the
   * same pellets from them ({@link #resolveServerShot}). It used to send one post-spread ray per pellet —
   * eight reliable messages per SG1 pull, sharing channel 0 with damage, pickups and spawns.
   */
  private void fireShot() {
    RayCast3D ray = getEffectiveAimRay();
    if (ray == null) return;

    Vector3 sightPoint = resolveSightPoint(ray);
    // Origin and aim are rounded to float32 BEFORE the pellets are generated, because float32 is what
    // MSG_SHOT carries: the host regenerates from the decoded values, so the client must generate from
    // the very same ones. Generating from the double first made 1 pull in 10 differ in the fifth
    // decimal of its pellet directions (measured, tools/net/run_net_shot_test.sh).
    Vector3 origin = wireRounded(useMuzzleTrace() ? resolveShotOrigin(ray) : ray.getGlobalPosition());
    Vector3 toTarget = sightPoint.minus(origin);
    if (toTarget.lengthSquared() < 1e-6f) return;
    Vector3 aim = wireRounded(toTarget.normalized());
    // Player: sample the spread cone around the muzzle→target line. AI: AttackState already baked its
    // scatter into the sight point via snapAimRay — scattering again would override that.
    float spreadDeg = (owningCharacter instanceof Character c && c.useWeaponSpread) ? getCurrentSpreadDeg() : 0f;
    long shotSeq = weaponController != null ? weaponController.nextShotSeq() : 0L;
    // Reach at least as far as the ray's own resting length, so a shot that misses (spread / AI
    // scatter) keeps travelling past the aim point instead of stopping in mid-air.
    float range = (float) Math.max(ray.getTargetPosition().length(), toTarget.length());

    boolean client = isNetworkedClient();
    // Host-resolved bullets: a client predicts the cosmetics but applies no damage — the host re-traces
    // the same pellets against authoritative positions. The origin reported is the muzzle, so the host
    // re-runs the very same cover test rather than a camera-origin one.
    if (client) sendShotToHost(origin, aim, spreadDeg, shotSeq);
    lastShotPelletHits = resolvePellets(ray, origin, aim, spreadDeg, shotSeq, shooterId(), range, !client, true);
    // The host's own shooters (host player, AI): every client sees them only as puppets, so send what
    // the pull hit to all of them (N1b).
    if (!client) queueResultForPeers(shotSeq, -1);
  }

  /** {@code v} as float32 components — the precision MSG_SHOT carries. */
  private static Vector3 wireRounded(Vector3 v) {
    return new Vector3((double) (float) v.getX(), (double) (float) v.getY(), (double) (float) v.getZ());
  }

  /** The id this weapon's shots are seeded with — the holder's character id, "" when there is none. */
  private String shooterId() {
    return owningCharacter instanceof Character c && c.characterInfo != null ? c.characterInfo.characterId : "";
  }

  /**
   * Pellet hits of the most recent pull this weapon resolved, one entry per pellet ("-" for a miss) —
   * the hit node's name. Read by the N1 two-instance check to compare the client's prediction with the
   * host's resolution of the same pull; not gameplay state.
   */
  public java.util.List<String> lastShotPelletHits = java.util.List.of();

  /** Digest of the pellet DIRECTIONS of that pull — equal on client and host when both regenerated the
   *  same cone from the same seed, whatever the hitboxes were doing. Diagnostic, like the hits. */
  public String lastShotDirectionDigest = "";

  /** Where each pellet of the last resolved pull stopped — what a host broadcasts to peers (N1b). */
  private java.util.List<com.openworld.net.NetMessageCodec.PelletResult> lastShotPellets = java.util.List.of();

  /**
   * Trace every pellet of one pull through {@code origin} along its seeded direction. {@code applyDamage}
   * is the authority (server / single-player) path; otherwise only the impact visuals play.
   * Returns the per-pellet hit names (see {@link #lastShotPelletHits}).
   */
  private java.util.List<String> resolvePellets(RayCast3D ray, Vector3 origin, Vector3 aim, float spreadDeg,
                                                long shotSeq, String shooter, float range,
                                                boolean applyDamage, boolean drawTracers) {
    long seed = SpreadPattern.seedFor(shooter, shotSeq);
    int pellets = Math.max(1, pelletCount);
    java.util.List<String> hits = new java.util.ArrayList<>(pellets);
    java.util.List<com.openworld.net.NetMessageCodec.PelletResult> results = new java.util.ArrayList<>(pellets);
    var im = getImpactManager();
    double digest = 0;
    for (int i = 0; i < pellets; i++) {
      double[] d = SpreadPattern.direction(aim.getX(), aim.getY(), aim.getZ(), spreadDeg * 0.5, seed, i);
      digest += (i + 1) * (d[0] + 3 * d[1] + 7 * d[2]);
      Vector3 dir = new Vector3(d[0], d[1], d[2]);
      TraceHit hit = trace(ray, origin, dir, range);
      hits.add(hit != null && hit.node != null ? hit.node.getName().toString() : "-");
      if (hit != null) {
        SurfaceType s = im != null ? im.surfaceOf(hit.node) : SurfaceType.DEFAULT;
        results.add(new com.openworld.net.NetMessageCodec.PelletResult(s.ordinal() + 1, hit.point, hit.normal));
      } else {
        results.add(new com.openworld.net.NetMessageCodec.PelletResult(0,
            origin.plus(dir.times(Math.min(range, TRACER_MISS_LENGTH))), null));
      }
      if (hit != null && im != null) {
        HitInfo info = new HitInfo(hit.node, hit.point, hit.normal);
        if (applyDamage) {
          im.processHit(info, damage, getDisplayName(), weaponIcon, resolveAttackerName(), resolveAttackerFaction(),
                        resolveAttackerPosition());
        } else {
          im.processVisualHit(info);
        }
      }
      if (drawTracers) {
        spawnBulletTracer(hit != null ? hit.point : origin.plus(dir.times(Math.min(range, TRACER_MISS_LENGTH))));
      }
    }
    lastShotDirectionDigest = String.format(java.util.Locale.ROOT, "%.5f", digest);
    lastShotPellets = results;
    return hits;
  }

  @Override protected boolean launchesTowardAim() { return muzzleTrace; }

  /**
   * True when this shot should leave the muzzle rather than the camera. On-foot characters only:
   * a seated occupant's gun (and a vehicle's own mounted weapon) sits inside/against the carrier's
   * collision, where a muzzle-origin trace would be blocked by the vehicle itself — and a passenger
   * shooting from a car is not the cover exploit this guards against.
   */
  private boolean useMuzzleTrace() {
    return muzzleTrace && owningCharacter instanceof Character c && c.currentVehicleNode == null;
  }


  /**
   * Stage-2 origin: the weapon's muzzle — pulled back to the shooter's own chest when the barrel has
   * clipped THROUGH geometry (standing flush against a wall). Without that guard the two-stage trace
   * is bypassed by hugging the cover: the muzzle ends up on the far side and its trace then starts
   * past the very wall that should have stopped the shot.
   */
  private Vector3 resolveShotOrigin(RayCast3D ray) {
    Vector3 muzzle = weaponMuzzle().getGlobalPosition();
    if (owningCharacter == null) return muzzle;
    Vector3 body  = owningCharacter.getGlobalPosition();
    Vector3 chest = new Vector3(body.getX(), muzzle.getY(), body.getZ());
    Vector3 toMuzzle = muzzle.minus(chest);
    float reach = (float) toMuzzle.length();
    if (reach < MUZZLE_CLEARANCE_MIN) return muzzle;
    // The AimRay excepts our own body + ragdoll bones (Character._ready), so this only reports world
    // geometry — an obstruction here means the gun is on the other side of something.
    return trace(ray, chest, toMuzzle.normalized(), reach) != null ? chest : muzzle;
  }

  /**
   * Host-side resolution of a client's MSG_SHOT (PLAN.md N1). The pull arrives as its inputs — origin,
   * PRE-spread aim, cone and counter — already validated by {@code ShotValidationPolicy}, and the host
   * regenerates the very pellets the client predicted and resolves them authoritatively (damage +
   * impact). Two things are the host's own, never the client's: the pellet count and damage (this
   * weapon's), and the cover test — the chest→origin clearance is re-run against the host copy, so a
   * client reporting a muzzle on the far side of a wall is pulled back to its chest exactly as a local
   * shot would be. The result goes to every peer except the shooter's owner (N1b).
   */
  public java.util.List<String> resolveServerShot(Vector3 origin, Vector3 aim, float spreadDeg, long shotSeq,
                                                  String shooter, int weaponSlot, int ownerPeerId) {
    RayCast3D ray = getEffectiveAimRay();
    if (ray == null || aim.lengthSquared() < 1e-6f) return java.util.List.of();
    Vector3 from = clearOriginOnHost(ray, origin);
    float range = (float) Math.max(50.0, ray.getTargetPosition().length());
    // The host draws this pull's real tracers itself and marks the result as in, so the shooter's
    // fireSeq cue on this puppet does not add its own aim tracer on top (N1b).
    lastShotResultMs = Time.INSTANCE.getTicksMsec();
    fallbackTracerAtMs = 0;
    // `aim` exactly as decoded — SpreadPattern normalises it the same way the client's copy was.
    lastShotPelletHits = resolvePellets(ray, from, aim, spreadDeg, shotSeq, shooter, range, true, true);
    queueResultForPeers(shotSeq, ownerPeerId, shooter, weaponSlot);
    return lastShotPelletHits;
  }

  /** Host: hand the last resolved pull's pellets to the NetworkManager for every peer but {@code exclude}. */
  private void queueResultForPeers(long shotSeq, int excludePeerId) {
    if (weaponController == null) return;
    queueResultForPeers(shotSeq, excludePeerId, shooterId(), weaponController.getWeapon());
  }

  private void queueResultForPeers(long shotSeq, int excludePeerId, String shooter, int weaponSlot) {
    if (shooter == null || shooter.isEmpty()) return;
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (netNode instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
      net.queueShotResult(new com.openworld.net.NetMessageCodec.ShotResult(shooter, weaponSlot, shotSeq,
          lastShotPellets), excludePeerId);
    }
  }

  /** {@link #resolveShotOrigin}'s cover test, run from the host copy's chest to a REPORTED origin. */
  private Vector3 clearOriginOnHost(RayCast3D ray, Vector3 reported) {
    if (owningCharacter == null) return reported;
    Vector3 body  = owningCharacter.getGlobalPosition();
    Vector3 chest = new Vector3(body.getX(), reported.getY(), body.getZ());
    Vector3 toOrigin = reported.minus(chest);
    float reach = (float) toOrigin.length();
    if (reach < MUZZLE_CLEARANCE_MIN) return reported;
    return trace(ray, chest, toOrigin.normalized(), reach) != null ? chest : reported;
  }

  /** The host copy's muzzle — what a reported origin is validated against. */
  public Vector3 muzzlePosition() { return weaponMuzzle().getGlobalPosition(); }

  /** True on a networked non-host peer — its firearm shots are predicted locally but resolved by the host. */
  private boolean isNetworkedClient() {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    return netNode instanceof NetworkManager net && net.isNetworked() && !net.isServer();
  }

  /** True on the host of a networked session (the peer that simulates the AI, so the one whose
   *  StimulusManager AI poll). Used to turn a *remote* player's replicated shot into a host stimulus. */
  private boolean isServerPeer() {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    return netNode instanceof NetworkManager net && net.isNetworked() && net.isServer();
  }

  /** Sends this pull's inputs to the host for authoritative resolution — one message per pull (N1). */
  private void sendShotToHost(Vector3 origin, Vector3 aim, float spreadDeg, long shotSeq) {
    if (!(owningCharacter instanceof Character c) || c.characterInfo == null || weaponController == null) return;
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (netNode instanceof NetworkManager net) {
      net.sendShot(c.characterInfo.characterId, weaponController.getWeapon(), shotSeq, origin, aim, spreadDeg);
    }
  }

  /** Draws the visible round from the barrel to where the bullet actually stopped. */
  private void spawnBulletTracer(Vector3 end) {
    BulletTracerManager tm = getBulletTracerManager();
    if (tm != null) tm.spawnTracer(weaponMuzzle().getGlobalPosition(), end);
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
    // SWIM is checked before the airborne branch: a swimmer floats off the floor, so the
    // !isOnFloor() check would otherwise mislabel it as airborne. Treading water has its own value.
    if (currentStance == StanceName.SWIM) return SWIM_SPREAD_MULT;
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
