package com.openworld.movement.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;
import godot.annotation.Export;

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
@RegisterClass(className = "SwimState")
public class SwimState extends Resource {

  /** Reduced downward gravity while swimming (m/s²). Retained for tuning; the surface spring dominates. */
  @Export
  @RegisterProperty
  public double swimGravity = 4.0;

  /** Buoyancy spring stiffness — vertical velocity ≈ buoyancy × (targetY − bodyY), clamped. */
  @Export
  @RegisterProperty
  public double buoyancy = 6.0;

  /** How far below the water surface the body origin settles (m) — small so the head pokes out. */
  @Export
  @RegisterProperty
  public double submersionDepth = 0.6;

  /**
   * A shallower settle line (m) used while the swimmer is aiming/in combat, so the body lifts and
   * the weapon clears the waterline for a clean "tread-water" gunline (GTA/PUBG surface shooting).
   */
  @Export
  @RegisterProperty
  public double aimSubmersionDepth = 0.45;

  /**
   * Water depth at the feet (while grounded) required to START swimming (m) — represents chest
   * height on the standing capsule. Below this the character wades/walks upright; above it, swims.
   * Shallow puddles never reach it. Defaulted from the upright capsule height at runtime, but a
   * value set here in the {@code .tres} wins.
   */
  @Export
  @RegisterProperty
  public double swimEnterDepth = 1.2;

  /**
   * Water depth (surface − floor, from the downward floor probe) at or below which a swimmer stands
   * up. Must be {@code < swimEnterDepth} for hysteresis (no SWIM⇄UPRIGHT flicker at the boundary).
   */
  @Export
  @RegisterProperty
  public double swimExitDepth = 0.8;

  /** How far down (m) the floor probe casts to find the bottom; beyond this is treated as deep water. */
  @Export
  @RegisterProperty
  public double floorProbeLength = 8.0;

  /** Physics layer mask the floor probe collides with (default layer 1 = world/static geometry). */
  @Export
  @RegisterProperty
  public long floorProbeMask = 1;

  /** Clamp on the PASSIVE buoyancy-driven vertical velocity (m/s) — the gentle auto-settle speed. */
  @Export
  @RegisterProperty
  public double maxVerticalSpeed = 2.0;

  /**
   * MANUAL ascend speed (m/s) while holding jump — intentionally faster than {@link #maxVerticalSpeed}
   * so powering to the surface beats waiting for buoyancy. Eases to a stop at the settle line.
   */
  @Export
  @RegisterProperty
  public double swimAscendSpeed = 4.0;

  /** MANUAL dive speed (m/s) while holding crouch/crawl. */
  @Export
  @RegisterProperty
  public double swimDiveSpeed = 3.0;

  /**
   * Lateral swim speed cap (m/s). The effective horizontal speed is driven by the SWIM
   * stance's {@link MovementState} resources; this value documents/serves as the intended
   * cap and is available for future explicit clamping.
   */
  @Export
  @RegisterProperty
  public double swimSpeed = 2.5;

  public double getSwimGravity() { return swimGravity; }
  public double getBuoyancy() { return buoyancy; }
  public double getSubmersionDepth() { return submersionDepth; }
  public double getAimSubmersionDepth() { return aimSubmersionDepth; }
  public double getSwimEnterDepth() { return swimEnterDepth; }
  public double getSwimExitDepth() { return swimExitDepth; }
  public double getFloorProbeLength() { return floorProbeLength; }
  public long getFloorProbeMask() { return floorProbeMask; }
  public double getMaxVerticalSpeed() { return maxVerticalSpeed; }
  public double getSwimAscendSpeed() { return swimAscendSpeed; }
  public double getSwimDiveSpeed() { return swimDiveSpeed; }
  public double getSwimSpeed() { return swimSpeed; }

  // Default constructor is required for Godot to instantiate the Resource
  public SwimState() {
    super();
  }
}
