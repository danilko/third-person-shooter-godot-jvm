package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;

/**
 * A weapon's scope, as DATA (PLAN.md 2.8 item 4). Any {@link FirearmItem} that references one is a
 * scoped weapon — a bolt sniper, a scoped DMR, a magnified AR — with no subclass. Read-only shared
 * config (the {@code VehicleConfig} precedent), so embedding it in a weapon scene is safe under godot-jvm.
 *
 * <p>The weapon owns the numbers; the owners of each EFFECT stay where they were: the camera writes the
 * FOV ({@code TPSCameraController}), {@code camera.ScopeSway} owns the drift and the breath,
 * {@code WeaponController.scopedNow} owns whether the zoom is up, and {@code MovementController} owns
 * movement — it asks the body ({@code Character.scopeMoveSpeedFactor}), which asks this.
 */
@Script(className = "ScopeConfig")
public class ScopeConfig extends Resource {

    /** Camera FOV while scoped, degrees. 0 turns the scope off. 20 against ~75 is ~3.75x, the AWP's. */
    @Export public float fov = 20.0f;

    /** Seconds to zoom in, and back out. Short: a scope that lags the button reads as input lag. */
    @Export public float zoomSeconds = 0.12f;

    /** Peak drift of the scoped view, degrees (0 = still, CS). The breath is the body's. */
    @Export public float sway = 0.0f;

    /** Leave the zoom for the bolt cycle and the reload, back by itself while aim is held (CS AWP). */
    @Export public boolean unscopeToCycle = false;

    /**
     * Max move speed while the scope is RAISED, as a fraction of the holder's normal max. CS reference:
     * the AWP moves at 200 u/s and 100 scoped, which is 40% of the 250 u/s knife speed; this game's
     * weapons do not slow the runner, so 0.4 of the unarmed max is the CS number. 1 = no slowdown.
     */
    @Export public float moveSpeedFactor = 0.4f;

    /**
     * Ground deceleration multiplier while the scope is raised and the holder is stopping (no move input)
     * — CS's counter-strafe: a scoped player who lets go is accurate again in ~0.1 s instead of the
     * ~0.5 s the ordinary idle slide takes. 1 = the ordinary stop.
     */
    @Export public float stopAccelerationFactor = 3.0f;

    public float getFov() { return fov; }
    public void setFov(float v) { fov = v; }
    public float getZoomSeconds() { return zoomSeconds; }
    public void setZoomSeconds(float v) { zoomSeconds = v; }
    public float getSway() { return sway; }
    public void setSway(float v) { sway = v; }
    public boolean getUnscopeToCycle() { return unscopeToCycle; }
    public void setUnscopeToCycle(boolean v) { unscopeToCycle = v; }
    public float getMoveSpeedFactor() { return moveSpeedFactor; }
    public void setMoveSpeedFactor(float v) { moveSpeedFactor = v; }
    public float getStopAccelerationFactor() { return stopAccelerationFactor; }
    public void setStopAccelerationFactor(float v) { stopAccelerationFactor = v; }
}
