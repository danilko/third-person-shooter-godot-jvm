package com.openworld.movement.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

/**
 * Tunables for the SWIM stance (PLAN.md I1 — water traversal). Assigned to
 * {@link MovementController#swimState}; mirrors the {@link JumpState} config-object idiom.
 *
 * <p>While swimming, {@link MovementController} replaces normal gravity with a buoyancy spring
 * that drives the body toward the water surface (passed in from the {@code WaterVolume}) and
 * holds it there — the body settles a small {@link #submersionDepth} below the surface and never
 * pops out the top, so the stance only reverts when the character leaves the volume horizontally.
 * Placeholder model: a single surface line, no per-vertex water sampling.
 */
@Script(className = "SwimState")
public class SwimState extends Resource {

  /** Reduced downward gravity while swimming (m/s²). Retained for tuning; the surface spring dominates. */
  @Export
  public double swimGravity = 4.0;

  /** Buoyancy spring stiffness — vertical velocity ≈ buoyancy × (targetY − bodyY), clamped. */
  @Export
  public double buoyancy = 6.0;

  /** How far below the water surface the body origin settles (m) — small so the head pokes out. */
  @Export
  public double submersionDepth = 0.7;

  /**
   * A shallower settle line (m) used while the swimmer is aiming/in combat, so the body lifts and
   * the weapon clears the waterline for a clean "tread-water" gunline (GTA/PUBG surface shooting).
   */
  @Export
  public double aimSubmersionDepth = 0.53;

  /**
   * Water depth at the feet (while grounded) required to START swimming (m) — represents chest
   * height on the standing capsule. Below this the character wades/walks upright; above it, swims.
   * Shallow puddles never reach it. Defaulted from the upright capsule height at runtime, but a
   * value set here in the {@code .tres} wins.
   */
  @Export
  public double swimEnterDepth = 1.4;

  /**
   * Water depth (surface − floor, from the downward floor probe) at or below which a swimmer stands
   * up. Must be {@code < swimEnterDepth} for hysteresis (no SWIM⇄UPRIGHT flicker at the boundary).
   */
  @Export
  public double swimExitDepth = 0.93;

  /** How far down (m) the floor probe casts to find the bottom; beyond this is treated as deep water. */
  @Export
  public double floorProbeLength = 8.0;

  /** Physics layer mask the floor probe collides with (default layer 1 = world/static geometry). */
  @Export
  public long floorProbeMask = 1;

  /** Clamp on the PASSIVE buoyancy-driven vertical velocity (m/s) — the gentle auto-settle speed. */
  @Export
  public double maxVerticalSpeed = 2.0;

  /**
   * MANUAL ascend speed (m/s) while holding jump — intentionally faster than {@link #maxVerticalSpeed}
   * so powering to the surface beats waiting for buoyancy. Eases to a stop at the settle line.
   */
  @Export
  public double swimAscendSpeed = 4.0;

  /** MANUAL dive speed (m/s) while holding crouch/crawl. */
  @Export
  public double swimDiveSpeed = 3.0;

  /**
   * Upward impulse (m/s) of a swim-jump "breach" — a tap of jump near the surface launches the
   * swimmer up and (with forward momentum) onto a low ledge/harbor at or just above the waterline
   * (PLAN.md I1; the GTA/PUBG "hop out of water onto a low edge"). Only fires near the surface, not
   * from the depths. A tall dock above this reach still can't be cleared (mantle climb is future work).
   */
  @Export
  public double swimJumpSpeed = 4.5;

  /**
   * How long (s) the breach stays ballistic before buoyancy resumes. During this window the body
   * arcs up under {@link #swimGravity} (instead of the surface spring) so it can clear the lip; once
   * it expires the passive buoyancy gently settles it back to the surface if it fell short.
   */
  @Export
  public double swimJumpDuration = 0.45;

  // ── Breath / oxygen (PLAN.md I1) ────────────────────────────────────────────
  // Swimming at the surface is safe; diving fully under starts an oxygen countdown that, when it
  // hits zero, deals drowning damage — forcing the player to periodically surface (tactical play,
  // and a hedge for a future murky-underwater water shader).

  /** Lung capacity in seconds — how long a fully-submerged swimmer lasts before drowning starts. */
  @Export
  public double maxOxygen = 12.0;

  /**
   * Depth below the water surface (m) at which the head is considered underwater and oxygen begins
   * to drain. Must be deeper than {@link #submersionDepth} so ordinary surface swimming never drains.
   */
  @Export
  public double submergeDepth = 1.4;

  /** Oxygen recovery rate (s of air per real second) once the head is back above water. */
  @Export
  public double oxygenRecoverRate = 4.0;

  /** Drowning damage applied per {@link #drowningInterval} once oxygen is depleted. */
  @Export
  public double drowningDamage = 8.0;

  /** Seconds between drowning damage ticks while oxygen is empty. */
  @Export
  public double drowningInterval = 1.0;

  /**
   * Lateral swim speed cap (m/s). The effective horizontal speed is driven by the SWIM
   * stance's {@link MovementState} resources; this value documents/serves as the intended
   * cap and is available for future explicit clamping.
   */
  @Export
  public double swimSpeed = 2.5;

  public double getSwimGravity() { return swimGravity; }

  /** Setter half of the exported {@code swimGravity} property. */
  public void setSwimGravity(double value) {
    this.swimGravity = value;
  }
  public double getBuoyancy() { return buoyancy; }

  /** Setter half of the exported {@code buoyancy} property. */
  public void setBuoyancy(double value) {
    this.buoyancy = value;
  }
  public double getSubmersionDepth() { return submersionDepth; }

  /** Setter half of the exported {@code submersionDepth} property. */
  public void setSubmersionDepth(double value) {
    this.submersionDepth = value;
  }
  public double getAimSubmersionDepth() { return aimSubmersionDepth; }

  /** Setter half of the exported {@code aimSubmersionDepth} property. */
  public void setAimSubmersionDepth(double value) {
    this.aimSubmersionDepth = value;
  }
  public double getSwimEnterDepth() { return swimEnterDepth; }

  /** Setter half of the exported {@code swimEnterDepth} property. */
  public void setSwimEnterDepth(double value) {
    this.swimEnterDepth = value;
  }
  public double getSwimExitDepth() { return swimExitDepth; }

  /** Setter half of the exported {@code swimExitDepth} property. */
  public void setSwimExitDepth(double value) {
    this.swimExitDepth = value;
  }
  public double getFloorProbeLength() { return floorProbeLength; }

  /** Setter half of the exported {@code floorProbeLength} property. */
  public void setFloorProbeLength(double value) {
    this.floorProbeLength = value;
  }
  public long getFloorProbeMask() { return floorProbeMask; }

  /** Setter half of the exported {@code floorProbeMask} property. */
  public void setFloorProbeMask(long value) {
    this.floorProbeMask = value;
  }
  public double getMaxVerticalSpeed() { return maxVerticalSpeed; }

  /** Setter half of the exported {@code maxVerticalSpeed} property. */
  public void setMaxVerticalSpeed(double value) {
    this.maxVerticalSpeed = value;
  }
  public double getSwimAscendSpeed() { return swimAscendSpeed; }

  /** Setter half of the exported {@code swimAscendSpeed} property. */
  public void setSwimAscendSpeed(double value) {
    this.swimAscendSpeed = value;
  }
  public double getSwimDiveSpeed() { return swimDiveSpeed; }

  /** Setter half of the exported {@code swimDiveSpeed} property. */
  public void setSwimDiveSpeed(double value) {
    this.swimDiveSpeed = value;
  }
  public double getSwimJumpSpeed() { return swimJumpSpeed; }

  /** Setter half of the exported {@code swimJumpSpeed} property. */
  public void setSwimJumpSpeed(double value) {
    this.swimJumpSpeed = value;
  }
  public double getSwimJumpDuration() { return swimJumpDuration; }

  /** Setter half of the exported {@code swimJumpDuration} property. */
  public void setSwimJumpDuration(double value) {
    this.swimJumpDuration = value;
  }
  public double getMaxOxygen() { return maxOxygen; }

  /** Setter half of the exported {@code maxOxygen} property. */
  public void setMaxOxygen(double value) {
    this.maxOxygen = value;
  }
  public double getSubmergeDepth() { return submergeDepth; }

  /** Setter half of the exported {@code submergeDepth} property. */
  public void setSubmergeDepth(double value) {
    this.submergeDepth = value;
  }
  public double getOxygenRecoverRate() { return oxygenRecoverRate; }

  /** Setter half of the exported {@code oxygenRecoverRate} property. */
  public void setOxygenRecoverRate(double value) {
    this.oxygenRecoverRate = value;
  }
  public double getDrowningDamage() { return drowningDamage; }

  /** Setter half of the exported {@code drowningDamage} property. */
  public void setDrowningDamage(double value) {
    this.drowningDamage = value;
  }
  public double getDrowningInterval() { return drowningInterval; }

  /** Setter half of the exported {@code drowningInterval} property. */
  public void setDrowningInterval(double value) {
    this.drowningInterval = value;
  }
  public double getSwimSpeed() { return swimSpeed; }

  /** Setter half of the exported {@code swimSpeed} property. */
  public void setSwimSpeed(double value) {
    this.swimSpeed = value;
  }

  // Default constructor is required for Godot to instantiate the Resource
  public SwimState() {
    super();
  }
}
