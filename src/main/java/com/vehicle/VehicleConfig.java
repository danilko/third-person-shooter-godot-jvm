package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Curve;
import godot.api.PackedScene;
import godot.api.Resource;
import godot.api.Texture2D;

/**
 * Per-vehicle-type tuning resource. Assign different .tres presets per vehicle scene.
 * New vehicle type = new .tres file only; no code or scene edits needed.
 *
 * Separation of concerns (GTA/Battlefield pattern):
 *   Vehicle.tscn  — structural (wheel positions, seat, model, collision mesh)
 *   VehicleConfig.tres — behavioural (how it drives, fights, and explodes)
 *
 * If no config is assigned, Vehicle.getConfig() returns a static DEFAULTS instance
 * so existing scenes without an assigned config continue to work unchanged.
 */
@RegisterClass(className = "VehicleConfig")
public class VehicleConfig extends Resource {

    // ── Suspension — applied to all wheels as shared defaults ─────────────

    /** Spring force per metre of compression (N/m). */
    @Export @RegisterProperty public float springStrength   = 10000f;

    /** Spring damping coefficient — resists oscillation. */
    @Export @RegisterProperty public float springDamping    = 4500f;

    /** Wheel visual and physics radius (metres). */
    @Export @RegisterProperty public float wheelRadius      = 0.4f;

    /** Natural rest position: distance from wheel centre to contact point when unloaded. */
    @Export @RegisterProperty public float restDistance     = 0.5f;

    /** How far the wheel can extend below rest position before the ray stops. */
    @Export @RegisterProperty public float overExtend       = 0.3f;

    // ── Traction ──────────────────────────────────────────────────────────

    /** Longitudinal rolling-friction coefficient (no throttle or brake). */
    @Export @RegisterProperty public float zTraction        = 0.05f;

    /** Longitudinal friction under braking or parking (≥ 5× zTraction). */
    @Export @RegisterProperty public float zBrakeTraction   = 0.25f;

    // ── Power ─────────────────────────────────────────────────────────────

    /** Top speed (m/s). Acceleration curve is sampled at (speed/maxSpeed). */
    @Export @RegisterProperty public float maxSpeed         = 20.0f;

    /** Peak motor force (N). Multiplied by accelerationCurve and throttle input. */
    @Export @RegisterProperty public float acceleration     = 9000.0f;

    /**
     * Force-vs-speed multiplier curve. X = speed ratio (0–1), Y = force multiplier (0–1).
     * Null = linear fallback: multiplier = max(0, 1 − speedRatio).
     */
    @Export @RegisterProperty public Curve accelerationCurve;

    // ── Steering ──────────────────────────────────────────────────────────

    /** Steering return speed (rad/s) when the player releases the stick. */
    @Export @RegisterProperty public float tireMaxTurnSpeed   = 2.0f;

    /** Maximum steering angle from straight-ahead (degrees). */
    @Export @RegisterProperty public float tireMaxTurnDegrees = 25.0f;

    // ── Combat / weapon ───────────────────────────────────────────────────

    /**
     * How the occupant fires while inside:
     *   0 = NONE             — no shooting
     *   1 = PASSENGER_WEAPON — occupant fires own weapon via vehicle camera
     *   2 = VEHICLE_WEAPON   — vehicle's own FirearmItem fires; occupant weapon disabled
     */
    @Export @RegisterProperty public int weaponModeIndex = 1;

    // ── Collision damage ──────────────────────────────────────────────────

    /** Minimum vehicle speed (m/s) needed to deal collision damage. 0 = disabled. */
    @Export @RegisterProperty public float vehicleCollisionMinSpeed    = 5.0f;

    /** Damage per m/s above vehicleCollisionMinSpeed. */
    @Export @RegisterProperty public float vehicleCollisionDamageScale = 100.0f;

    // ── Destruction explosion ─────────────────────────────────────────────

    /** Blast radius (metres) on destruction. 0 = no explosion. */
    @Export @RegisterProperty public float explosionRadius    = 6f;

    /** Maximum damage at blast centre; falls off quadratically to zero at radius. */
    @Export @RegisterProperty public float explosionMaxDamage = 100f;

    /** Physics push force applied to bodies caught in the blast. */
    @Export @RegisterProperty public float explosionPushForce = 25f;

    // ── Wreck ─────────────────────────────────────────────────────────────

    /**
     * Scene spawned at the vehicle's world transform on destruction.
     * Null = no wreck remains after the explosion.
     * Set per config preset so a sports car gets a different burnt shell than a tank.
     */
    @Export @RegisterProperty public PackedScene wreckScene;

    /** Seconds the wreck node stays in the scene before being removed. */
    @Export @RegisterProperty public float wreckDuration = 15f;

    // ── Identity ──────────────────────────────────────────────────────────

    /** Icon shown in the kill feed when this vehicle kills a character. */
    @Export @RegisterProperty public Texture2D vehicleIcon;

    public VehicleConfig() { super(); }
}
