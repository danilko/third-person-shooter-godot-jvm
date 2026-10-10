package com.openworld.camera;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.InputEventMouseMotion;
import godot.core.Vector2;
import godot.global.GD;
import com.openworld.character.Character;
import com.openworld.control.Controller;
import com.openworld.control.PlayerController;
import com.openworld.net.NetworkController;

@Script(className = "PlayerCameraController")
public class PlayerCameraController extends TPSCameraController {

  // Accumulated raw pixel deltas from all mouse-motion events since last physics step.
  // Using _input + getRelative() (the same pattern as VehicleCameraController) captures
  // every mouse event between physics frames; getLastMouseVelocity()*delta only reads
  // the last event velocity and drops all intermediate events.
  private double pendingYaw   = 0;
  private double pendingPitch = 0;

  // ── Gamepad look (PLAN.md 1.1 / F1) ── the right stick is a RATE, not a delta: degrees per second at full
  // deflection, shaped by a response curve (fine aim near the centre, CoD / Halo practice), with a turn boost once the
  // stick has been held fully over for a beat (a 180 should not take two seconds). All of it scaled by the scope ratio
  // like the mouse, and slowed while aiming down the sights.
  @Export public double padYawRate = 220.0;
  @Export public double padPitchRate = 150.0;
  @Export public double padCurve = 2.0;
  @Export public double padAimScale = 0.55;
  @Export public double padTurnBoost = 0.7;
  @Export public double padBoostDelay = 0.25;
  @Export public double padBoostRamp = 0.35;
  @Export public boolean padInvertY = false;
  // Aim assist (pad only): the look rate drops over a body (friction), and pressing aim pulls the view onto the
  // nearest body within assistSnapCone over assistSnapTime (the ADS snap). Never on a mouse.
  @Export public boolean aimAssist = true;
  @Export public double assistSlowdown = 0.45;
  @Export public double assistSnapCone = 7.0;
  @Export public double assistSnapTime = 0.14;
  @Export public double assistRange = 70.0;

  public double getPadYawRate() { return padYawRate; }
  public void setPadYawRate(double v) { padYawRate = v; }
  public double getPadPitchRate() { return padPitchRate; }
  public void setPadPitchRate(double v) { padPitchRate = v; }
  public double getPadCurve() { return padCurve; }
  public void setPadCurve(double v) { padCurve = v; }
  public double getPadAimScale() { return padAimScale; }
  public void setPadAimScale(double v) { padAimScale = v; }
  public double getPadTurnBoost() { return padTurnBoost; }
  public void setPadTurnBoost(double v) { padTurnBoost = v; }
  public double getPadBoostDelay() { return padBoostDelay; }
  public void setPadBoostDelay(double v) { padBoostDelay = v; }
  public double getPadBoostRamp() { return padBoostRamp; }
  public void setPadBoostRamp(double v) { padBoostRamp = v; }
  public boolean isPadInvertY() { return padInvertY; }
  public void setPadInvertY(boolean v) { padInvertY = v; }
  public boolean isAimAssist() { return aimAssist; }
  public void setAimAssist(boolean v) { aimAssist = v; }
  public double getAssistSlowdown() { return assistSlowdown; }
  public void setAssistSlowdown(double v) { assistSlowdown = v; }
  public double getAssistSnapCone() { return assistSnapCone; }
  public void setAssistSnapCone(double v) { assistSnapCone = v; }
  public double getAssistSnapTime() { return assistSnapTime; }
  public void setAssistSnapTime(double v) { assistSnapTime = v; }
  public double getAssistRange() { return assistRange; }
  public void setAssistRange(double v) { assistRange = v; }

  private double fullHeld = 0;
  private double snapYaw, snapPitch, snapLeft;
  private boolean assistOnTarget;
  private int assistSnaps;

  /** Probe readouts: whether the last frame's stick look was slowed over a body, and how many ADS snaps ran. */
  @Register public boolean assistOnTargetNow() { return assistOnTarget; }
  @Register public int assistSnapsNow() { return assistSnaps; }

  @Register
  @Override
  public void _ready() {
    super._ready();
    // Mouse capture is NOT decided here: same lifecycle problem as camera activation
    // (see the comment below) — `player.getController()` is still null at this point,
    // since Character._ready() resolves it bottom-up *after* this node's _ready() runs.
    // isLocallyControlled() (called lazily from gatherLookInput, every physics frame)
    // owns that decision instead, mirroring Character.activateCameraIfOwned().
    //
    // Camera activation is NOT decided here either: at this point activeCamera is still
    // null (this _ready() runs bottom-up, before Character._ready() resolves it —
    // see TPSCameraController.setCameraFov's comment for the canonical explanation).
    // Character.activateCameraIfOwned() — deferred from Character._ready() once
    // activeCamera/characterInfo are populated — owns this decision instead.
  }

  /**
   * True only for the single body this machine's human is actually playing —
   * i.e. the body whose Controller child is a PlayerController (not
   * ServerProxyController, which drives a *remote* human's body on the server,
   * nor NetworkController, which drives a replica). Godot delivers every _input
   * event and global Input.isAction()/Input.MouseMode change to every node that
   * processes them, regardless of which body's camera is active — without this
   * gate, a listen-server host with a connected client ends up with two
   * PlayerCameraControllers (its own + the client's ServerProxyController-driven
   * proxy) both consuming the host's mouse, so the proxy body's mesh silently
   * tracks wherever the *host* is looking instead of the remote client's actual
   * aim — exactly the "wrong direction" replication symptom (round 5c report).
   */
  private boolean isLocallyControlled() {
    // `character`, not `player`: the runtime-resolved reference (TPSCameraController._ready).
    // A stale export wrapper's controller field is null, which would silently make every body
    // non-local and swallow all mouse look.
    return character != null && character.getController() instanceof PlayerController;
  }

  @Register
  @Override
  public void _input(InputEvent event) {
    if (!isLocallyControlled()) return;
    if (event instanceof InputEventMouseMotion mm) {
      pendingYaw   -= mm.getRelative().getX() * yawSensitivity;
      // Godot's mouse Y grows DOWNWARD and positive pitch is UP, so this subtracts. It added
      // while Pivot's 180° flip negated the pitch downstream (AIM_PLAN.md W3); the two changed
      // together and the resulting view is identical.
      pendingPitch -= mm.getRelative().getY() * pitchSensitivity;
    }
  }

  @Override
  protected Vector2 gatherLookInput(double delta) {
    if (!isLocallyControlled()) return Vector2.Companion.getZERO();

    // While on-foot input is blocked by a UI overlay that owns the mouse (the radial weapon menu,
    // pause menu — they set Character.inputBlocked AND mouse mode VISIBLE), do NOT re-capture the
    // mouse or apply look. This runs in _physicsProcess, which setProcessInput(false) does not stop,
    // so without this guard the per-frame CAPTURED re-grab below immediately hides/locks the cursor
    // the overlay just made visible — making the radial menu impossible to navigate with the mouse.
    if (character != null && character.inputBlocked()) {
      pendingYaw   = 0;
      pendingPitch = 0;
      return Vector2.Companion.getZERO();
    }

    // Deferred from _ready() (see comment there) — idempotent, cheap to repeat.
    Input.setMouseMode(Input.MouseMode.CAPTURED);

    // The DERIVED view, not the preference: there is no boom to hang a shoulder offset on while
    // scoped either, so the swap key is refused for the same reason it is refused in FPS.
    boolean isFps = character != null && character.isFirstPersonView();

    if (Input.isActionJustPressed("shoulder", false) && !isFps) {
      changeShoulderDirection();
    }

    if (Input.isActionJustPressed("view", false)) {
      if (character != null) character.setCameraMode(!character.isFpsMode);
    }

    double scale = lookSensitivityScale();
    Vector2 pad = padLook(delta);
    Vector2 snap = assistSnap(delta);   // an absolute angle onto a body: not scaled by the scope ratio
    double dy = (pendingYaw + pad.getX()) * scale + snap.getX();
    double dp = (pendingPitch + pad.getY()) * scale + snap.getY();
    pendingYaw   = 0;
    pendingPitch = 0;
    return new Vector2((float) dy, (float) dp);
  }

  /** The right stick's look this frame, degrees (yaw, pitch up +), with the turn boost and the pad-only aim assist. */
  private Vector2 padLook(double delta) {
    Vector2 st = Input.getVector("look_left", "look_right", "look_up", "look_down", -1.0f);
    double x = st.getX(), y = padInvertY ? -st.getY() : st.getY();
    double mag = Math.min(1.0, Math.hypot(x, y));
    boolean aiming = combat || Input.isActionPressed("aim", false);
    boolean assist = aimAssist && com.openworld.control.InputDevice.pad() && character != null && activeCamera != null;
    double yaw = 0, pitch = 0;
    assistOnTarget = false;
    if (mag > 1e-4) {
      double shaped = Math.pow(mag, padCurve) / mag;
      fullHeld = Math.abs(x) > 0.95 ? fullHeld + delta : 0.0;
      double boost = aiming ? 1.0 : 1.0 + padTurnBoost * GD.clamp((fullHeld - padBoostDelay) / padBoostRamp, 0.0, 1.0);
      double rate = aiming ? padAimScale : 1.0;
      if (assist) {
        AimAssist.Pick p = AimAssist.pick(character, activeCamera, 6.0, assistRange);
        if (p != null && p.offDeg() <= Math.max(1.0, p.radiusDeg() * 1.5)) { rate *= assistSlowdown; assistOnTarget = true; }
      }
      yaw   = -x * shaped * padYawRate * boost * rate * delta;
      pitch = -y * shaped * padPitchRate * rate * delta;
    } else {
      fullHeld = 0.0;
    }
    return new Vector2((float) yaw, (float) pitch);
  }

  /** The ADS snap (pad only): on the aim press, pull onto the nearest body in the cone over assistSnapTime. */
  private Vector2 assistSnap(double delta) {
    boolean assist = aimAssist && com.openworld.control.InputDevice.pad() && character != null && activeCamera != null;
    if (assist && Input.isActionJustPressed("aim", false)) {
      AimAssist.Pick p = AimAssist.pick(character, activeCamera, assistSnapCone, assistRange);
      if (p != null) { snapYaw = p.dYaw(); snapPitch = p.dPitch(); snapLeft = assistSnapTime; assistSnaps++; }
    }
    if (snapLeft <= 0) return Vector2.Companion.getZERO();
    double k = Math.min(1.0, delta / snapLeft);
    double y = snapYaw * k, p = snapPitch * k;
    snapYaw -= y;
    snapPitch -= p;
    snapLeft -= delta;
    return new Vector2((float) y, (float) p);
  }
}
