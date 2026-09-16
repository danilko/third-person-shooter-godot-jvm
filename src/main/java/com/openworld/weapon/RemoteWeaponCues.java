package com.openworld.weapon;

import com.openworld.net.NetStats;
import godot.global.GD;

/**
 * A PUPPET's replayed weapon cosmetics — fire and reload cues driven by the replicated {@code fireSeq} /
 * {@code reloadSeq} counters (N3), split out of {@link WeaponController} as a plain-Java collaborator
 * (PLAN.md 2.8 item 5). Cosmetic only: no ammo, no hitscan, no damage. Behaviour unchanged.
 */
final class RemoteWeaponCues {

  private final WeaponController wc;

  RemoteWeaponCues(WeaponController wc) { this.wc = wc; }

  void tick(double delta) {
    if (pendingRemoteCues > 0) {
      remoteCueCountdown -= delta;
      if (remoteCueCountdown <= 0.0) {
        pendingRemoteCues--;
        remoteCueCountdown = remoteCueGap();
        playRemoteFireCue();
      }
    }
  }

  /**
   * Network replay hook — plays the reload cosmetics (animation + audio) without running the reload
   * timer or refilling the magazine (ammo arrives via the replicated activeMagazine). Lets every
   * peer see a character is reloading. No-op when there's no active weapon (e.g. fist/diverged slot).
   */
  void playRemoteReloadCue() {
    WeaponItem w = wc.getCurrentWeaponItem();
    if (w == null || !wc.isArmed()) return;
    w.playMotion(w.reloadAnimation);
    if (w.getReloadAudio() != null) {
      wc.weaponAudio.setStream(w.getReloadAudio());
      wc.weaponAudio.play();
    }
    if (wc.animationController != null) wc.animationController.onWeaponReload();
  }

  // One-shot guard for the cue-divergence diagnostic below — the cue fires per shot (up to
  // ~10/s under sustained fire), so an unguarded print would flood the console.
  private boolean loggedCueNoFirearm = false;

  /** N3: remote cues still to play from the last replicated counter change, and the time to the next one. */
  private int pendingRemoteCues = 0;
  private double remoteCueCountdown = 0.0;

  /**
   * Network replay: the owner fired {@code count} times since the last snapshot this puppet saw
   * ({@code net.FireCuePolicy} reads that off the wrapping counter). The first cue plays now and the rest at the
   * weapon's own fire interval, so a burst a dropped snapshot collapsed is still heard as a burst. A melee weapon
   * replays only its latest swing: a swing restarts the one before it, and the step that rides the snapshot is
   * the latest one.
   */
  void playRemoteFireCues(int count) {
    if (count <= 0) return;
    if (wc.getCurrentWeaponItem() instanceof MeleeItem) count = 1;
    playRemoteFireCue();
    if (count > 1) {
      NetStats.increment("fire_cue_burst_replayed");
      pendingRemoteCues = Math.min(com.openworld.net.FireCuePolicy.MAX_CUES - 1, pendingRemoteCues + count - 1);
      remoteCueCountdown = remoteCueGap();
    }
  }

  /** Seconds between replayed cues: the held weapon's fire interval, kept between two frames and 0.12 s. */
  private double remoteCueGap() {
    WeaponItem w = wc.getCurrentWeaponItem();
    double gap = w != null ? w.fireInterval() : 0.1;
    return Math.max(0.033, Math.min(0.12, gap));
  }

  /** Network replay hook — plays the firing cosmetics (flash/audio + tracer) without consuming ammo or running hitscan. */
  void playRemoteFireCue() {
    // G4-2 (puppet fire-gate): never render a shot before the weapon is up. Mirror the owner's own
    // onWeaponFire gate — suppress while the holster→draw transition runs OR through the draw-settle
    // fireTimer that onWeaponTransitionComplete starts. A cue inside that window is the
    // fire-precedes-draw race (rare once G4-1 aligns the switch). The owner self-gates its real fire
    // on the same condition, so nothing authoritative is lost.
    if (wc.isWeaponTransitioning() || wc.fireLocked()) {
      NetStats.increment("fire_cue_predraw_suppressed");
      return;
    }
    WeaponItem w = wc.getCurrentWeaponItem();
    if (w != null && wc.isArmed()) {
      w.playMotion(w.fireAnimation);   // the weapon's own moving parts, on the remote peer too
      wc.kickWeapon(w);                   // and the visible arm kick (A3) -- cosmetic, so a puppet runs it too
      // Polymorphic cosmetic replay: firearms draw muzzle/tracer, throwable/projectile
      // weapons spawn a non-damaging projectile so the grenade/rocket arc + explosion is
      // seen on every peer (damage stays authority-side). Default no-op for the fist.
      w.playRemoteFireCue();
      return;
    }
    // The authority fired (its fireSeq advanced) but this puppet has no real active weapon to
    // render it — the puppet's inventory/slot diverged from the owner's (the "host does not do
    // any fire" symptom). Round 11 N1: count + log once so the divergence is visible; the
    // MSG_INVENTORY sweep is what actually heals it.
    com.openworld.net.NetStats.increment("cue_no_weapon");
    if (!loggedCueNoFirearm) {
      loggedCueNoFirearm = true;
      GD.print("WeaponController: remote fire cue on '" + wc.getOwner().getName()
          + "' landed on empty/fist slot " + wc.activeSlotIndex
          + " — puppet inventory diverged (MSG_INVENTORY will reconcile)");
    }
  }

}
