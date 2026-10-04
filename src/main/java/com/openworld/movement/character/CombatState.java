package com.openworld.movement.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

@Script(className = "CombatState")
public class CombatState extends Resource {

  @Export
  public boolean combat = false;

  @Export
  public double speedFactor = 1.0f;

  @Export
  public double accelerationFactor = 1.0f;

  @Export
  public double cameraDistance = 2.0f;

  /**
   * Sideways camera offset in metres, along the CAMERA's own right — so positive is the right
   * shoulder and negative the left. The game ships RIGHT (2026-10-04: the gun is on the right, so the
   * camera is over the right shoulder by default; the shoulder key mirrors it).
   *
   * <p>The sign only started meaning anything with AIM_PLAN.md W3. Before it, the offset was
   * applied along the Yaw node's X under a rig carrying an uncancelled 180-degree flip, so it went
   * the opposite way from the camera's right and a positive number produced a left-shoulder camera.
   * Removing the flip made the axis honest, which mirrors the framing — so the authored values were
   * negated to keep the shipped side. Flipping them back is now a one-character change per state,
   * and it means what it says.
   */
  @Export
  public double cameraShoulderOffset = 0.1f;

  /**
   * EXTRA sideways metres added only while the camera is over the LEFT shoulder (the gun is on the
   * right). Mirrored to the left, the boom looks across the head at the gun, and a long-haired body's
   * hair covers the shot; the industry answer is to sit the off-side camera wider and higher, not to
   * mirror it exactly. tools/godot/probe_shoulder_view.gd measures it (how much of the held gun the body
   * hides from the camera, per shoulder).
   *
   * <p>MEASURED on Shino (long straight hair), ASR1, aim held, 2026-10-04: the right shoulder shows 55% of
   * the gun, the left 12%, and NO value here helps -- 0.2-0.5 m wider stays at 10-12% (the hair hangs
   * straight between the camera and a gun held at the right shoulder), and +0.6 m higher only reaches 33%
   * once she is half out of the bottom of a level view. Both ship 0; the knobs stay for a shorter-haired
   * body or a camera that pitches down when raised. The real answers are fading the hair where it covers
   * the gun, or a left-handed stance on the left shoulder.
   */
  @Export
  public double cameraLeftShoulderExtra = 0.0f;

  /** EXTRA metres of camera height only while over the LEFT shoulder; see {@link #cameraLeftShoulderExtra}. */
  @Export
  public double cameraLeftHeightExtra = 0.0f;

  /**
   * Vertical camera adjustment applied ON TOP of the current stance's camera height while in
   * this combat state. An OFFSET (not an absolute height) so it composes with stances —
   * crouch-aim stays lower than stand-aim. Negative lowers the camera toward the gun line for
   * a tight over-the-shoulder aim (RE4/PUBG style); 0 leaves the stance height unchanged.
   */
  @Export
  public double cameraHeightOffset = 0.0f;

  @Export
  public double cameraFov = 70.0f;


  // Default constructor is required for Godot to instantiate the Resource
  public CombatState() {
    super();
  }

  public boolean isCombat() {
    return combat;
  }

  /** Setter half of the exported {@code combat} property. */
  public void setCombat(boolean value) {
    this.combat = value;
  }

  public double getSpeedFactor() {
    return speedFactor;
  }

  /** Setter half of the exported {@code speedFactor} property. */
  public void setSpeedFactor(double value) {
    this.speedFactor = value;
  }

  public double getAccelerationFactor() {
    return accelerationFactor;
  }

  /** Setter half of the exported {@code accelerationFactor} property. */
  public void setAccelerationFactor(double value) {
    this.accelerationFactor = value;
  }
}
