package com.vehicle;

import com.character.CameraMode;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.NodePath;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

import static godot.api.Input.INSTANCE;

/**
 * Vehicle follow/FPS camera — mirrors the character Yaw/Pitch/Pivot/SpringArm pattern.
 *
 * Scene hierarchy expected:
 *   CameraController (this node, 180°Y, setAsTopLevel)
 *     Yaw / Pitch / Pivot (180°Y) / SpringArm / Proxy   ← shared TPS rig
 *   FPSCameraMount (Marker3D sibling — driver head position)
 *   ActiveCamera (Camera3D sibling — written each frame)
 *     AimRay (RayCast3D)
 *
 * Four sub-modes:
 *   TPS follow  — yaw/pitch lerp to vehicle heading at independent speeds (yaw faster than
 *                 pitch). Slope is low-pass filtered so pitch never snaps on landings.
 *   TPS aim     — passengerAimMode + holding aim/fire. Mouse drives orientation only; spring
 *                 arm stays at followPitch so the camera position is stable. Pitch pivot is
 *                 effectively at the camera rather than the vehicle origin.
 *   FPS follow  — cockpit mode (Forza/NFS). Yaw locks to vehicle heading instantly; pitch
 *                 gently follows the vehicle nose angle. No mouse input in this sub-mode.
 *   FPS aim     — holding aim/fire in FPS mode. Mouse drives yaw/pitch freely.
 */
@RegisterClass(className = "VehicleCameraController")
public class VehicleCameraController extends Node3D {

    // ── Exports ───────────────────────────────────────────────────────────────

    @RegisterProperty @Export public double pitchMin            = -60.0;
    @RegisterProperty @Export public double pitchMax            =  80.0;
    @RegisterProperty @Export public double height              =  4.0;
    /** Degrees the TPS spring arm tilts downward at rest. Positive = arm extends upward-behind. */
    @RegisterProperty @Export public double followPitchDeg      =  15.0;

    /** Mouse sensitivity (degrees per raw pixel) — applies in FPS aim and TPS aim modes. */
    @RegisterProperty @Export public double yawSensitivity      =  0.07;
    @RegisterProperty @Export public double pitchSensitivity    =  0.07;
    /**
     * Extra sensitivity multiplier applied only in TPS aim mode.
     * TPS camera sits ~8-9 m behind the vehicle, so the same angular change feels smaller
     * than in FPS. Raise this value (default 2×) to compensate for the distance.
     */
    @RegisterProperty @Export public double tpsAimSensitivityMult = 2.0;

    /** TPS follow — lerp speed for yaw catching up to vehicle heading after releasing aim. */
    @RegisterProperty @Export public double yawRecoverySpeed    =  3.0;
    /**
     * TPS follow — lerp speed for pitch returning to the follow angle.
     * Intentionally slower than yaw to reduce motion sickness on sharp turns.
     */
    @RegisterProperty @Export public double pitchRecoverySpeed  =  1.5;
    /**
     * How fast the internal slope estimate tracks the vehicle's actual slope.
     * Lower values smooth out pitch spikes on landings and handbrake snap-yaws.
     */
    @RegisterProperty @Export public double slopeSmoothSpeed    =  2.0;

    /**
     * FPS cockpit — lerp speed for pitch following the vehicle nose angle.
     * Yaw always snaps instantly for direct steering feedback. Pitch is smoothed
     * to reduce vertigo on bumpy terrain.
     */
    @RegisterProperty @Export public double fpsPitchFollowSpeed =  5.0;

    @RegisterProperty @Export public double recoilRecoverySpeed =  8.0;

    @RegisterProperty @Export public NodePath fpsCameraMountPath = new NodePath("FPSCameraMount");

    // ── Node refs ─────────────────────────────────────────────────────────────

    private Node3D      target;
    private Camera3D    activeCamera;
    private RayCast3D   aimRay;
    private Node3D      fpsCameraMount;

    private Node3D      yawNode;
    private Node3D      pitchNode;
    private Node3D      pivotNode;
    private SpringArm3D tpsSpringArm;
    private Node3D      tpsProxyNode;

    // ── State ─────────────────────────────────────────────────────────────────

    private CameraMode cameraMode       = CameraMode.TPS;
    private boolean    passengerAimMode = false;

    private double yaw          = 0.0;
    private double pitch        = 0.0;
    private double recoilPitch  = 0.0;
    private double recoilYaw    = 0.0;
    private double pendingYaw   = 0.0;
    private double pendingPitch = 0.0;
    /** Low-pass filtered slope — prevents pitch snap when the vehicle hits a slope abruptly. */
    private double smoothedSlope = 0.0;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        target = (Node3D) getOwner();

        Node ac = getParent().getNodeOrNull("ActiveCamera");
        if (ac instanceof Camera3D c) {
            activeCamera = c;
            Node ar = activeCamera.getNodeOrNull("AimRay");
            if (ar instanceof RayCast3D r) aimRay = r;
        }

        yawNode      = (Node3D)      getNode(new NodePath("Yaw"));
        pitchNode    = (Node3D)      getNode(new NodePath("Yaw/Pitch"));
        pivotNode    = (Node3D)      getNode(new NodePath("Yaw/Pitch/Pivot"));
        tpsSpringArm = (SpringArm3D) getNode(new NodePath("Yaw/Pitch/Pivot/SpringArm"));
        tpsProxyNode = (Node3D)      getNode(new NodePath("Yaw/Pitch/Pivot/SpringArm/Proxy"));

        Node m = getNodeOrNull(fpsCameraMountPath);
        if (m instanceof Node3D n) fpsCameraMount = n;

        if (target instanceof CollisionObject3D co) {
            if (tpsSpringArm != null) tpsSpringArm.addExcludedObject(co.getRid());
            if (aimRay != null)       aimRay.addException(co);
        }

        setAsTopLevel(true);
        yaw   = Math.toDegrees(target.getGlobalRotation().getY());
        pitch = followPitchDeg;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    public void setPassengerAimMode(boolean enabled) { passengerAimMode = enabled; }
    public void setCameraMode(CameraMode mode)        { cameraMode = mode; }

    public void applyRecoil(double pitchKick, double yawKick) {
        recoilPitch -= pitchKick;
        recoilYaw   += yawKick;
    }

    public Vector3 getAimTarget() {
        if (aimRay == null) return target.getGlobalPosition();
        if (aimRay.isColliding()) return aimRay.getCollisionPoint();
        return activeCamera.toGlobal(aimRay.getTargetPosition());
    }

    // ── Input ─────────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _input(InputEvent event) {
        if (activeCamera == null || !activeCamera.isCurrent()) return;
        if (!(event instanceof InputEventMouseMotion m)) return;
        // Accumulate only while actively aiming:
        //   FPS follow: camera locked to vehicle — mouse ignored outside aim.
        //   TPS follow: camera auto-follows vehicle heading — mouse ignored outside aim.
        boolean doAccumulate = isAimingOrFiring()
                && (cameraMode == CameraMode.FPS || passengerAimMode);
        if (!doAccumulate) return;

        double tpsMult = (cameraMode == CameraMode.TPS) ? tpsAimSensitivityMult : 1.0;
        pendingYaw   -= m.getRelative().getX() * yawSensitivity   * tpsMult;
        pendingPitch += m.getRelative().getY() * pitchSensitivity * tpsMult;
        getViewport().setInputAsHandled();
    }

    // ── Physics ───────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        if (activeCamera != null && activeCamera.isCurrent()
                && INSTANCE.isActionJustPressed("view", false)) {
            setCameraMode(cameraMode == CameraMode.FPS ? CameraMode.TPS : CameraMode.FPS);
        }

        recoilPitch = GD.lerp(recoilPitch, 0.0, recoilRecoverySpeed * delta);
        recoilYaw   = GD.lerp(recoilYaw,   0.0, recoilRecoverySpeed * delta);

        Vector3 vehiclePos    = target.getGlobalPosition();
        double  vehicleYawDeg = Math.toDegrees(target.getGlobalRotation().getY());
        // Column 2 of the basis = vehicle local +Z (backward direction in world space).
        Vector3 vehicleZ      = target.getGlobalTransform().getBasis().getColumn(2);

        // Smooth the raw slope so the camera pitch target never jumps on abrupt landings
        // or handbrake snap-yaws. slopeSmoothSpeed controls how quickly the estimate catches up.
        double rawSlope      = Math.toDegrees(Math.asin(GD.clamp(-vehicleZ.getY(), -1.0, 1.0)));
        smoothedSlope        = GD.lerp(smoothedSlope, rawSlope, slopeSmoothSpeed * delta);
        double targetFollowPitch = GD.clamp(followPitchDeg - smoothedSlope, pitchMin, pitchMax);

        if (cameraMode == CameraMode.FPS) {
            if (fpsCameraMount != null) setGlobalPosition(fpsCameraMount.getGlobalPosition());

            if (isAimingOrFiring()) {
                // FPS aim: full mouse control, same as character FPS.
                yaw   += pendingYaw;
                pitch += pendingPitch;
                pitch  = GD.clamp(pitch, pitchMin, pitchMax);
            } else {
                // FPS cockpit (Forza/NFS style): yaw snaps to vehicle heading immediately
                // so the driver always sees where they are steering. Pitch follows the
                // vehicle's nose angle with a gentle lerp to reduce vertigo on bumpy terrain.
                yaw   = vehicleYawDeg;
                double vehiclePitchDeg = Math.toDegrees(
                        Math.asin(GD.clamp(vehicleZ.getY(), -1.0, 1.0)));
                pitch = GD.lerp(pitch, vehiclePitchDeg, fpsPitchFollowSpeed * delta);
            }

            applyYawPitch(yaw + recoilYaw, GD.clamp(pitch + recoilPitch, pitchMin, pitchMax));
            if (activeCamera != null && pivotNode != null) {
                activeCamera.setGlobalTransform(pivotNode.getGlobalTransform());
            }

        } else if (passengerAimMode && isAimingOrFiring()) {
            // TPS aim: camera stays at the stable follow position; pitch/yaw drive orientation only.
            // Pitch pivots at the camera (not at the vehicle origin): spring arm is locked to
            // followPitch for position stability; aim pitch rotates pivotNode (forward-facing)
            // so the player can look freely up/down without the camera orbiting the vehicle.
            setGlobalPosition(new Vector3(vehiclePos.getX(), vehiclePos.getY() + height, vehiclePos.getZ()));
            yaw   += pendingYaw;
            pitch += pendingPitch;
            pitch  = GD.clamp(pitch, pitchMin, pitchMax);
            double effYaw   = yaw + recoilYaw;
            double effPitch = GD.clamp(pitch + recoilPitch, pitchMin, pitchMax);

            // Pass 1: set aim pitch → capture pivotNode orientation (forward-facing aim direction).
            applyYawPitch(effYaw, effPitch);
            Transform3D aimXform = (pivotNode != null) ? pivotNode.getGlobalTransform() : null;

            // Pass 2: restore pitch to follow angle → spring arm holds camera at TPS position.
            if (pitchNode != null) {
                Vector3 pr = pitchNode.getRotationDegrees();
                pr.setX(targetFollowPitch);
                pitchNode.setRotationDegrees(pr);
            }

            if (activeCamera != null && aimXform != null && tpsProxyNode != null) {
                aimXform.setOrigin(tpsProxyNode.getGlobalPosition());
                activeCamera.setGlobalTransform(aimXform);
            }

        } else {
            // TPS follow: yaw and pitch lerp at independent speeds.
            // Yaw recovery is faster (3 s⁻¹ default) so the camera pivots back promptly after a
            // turn. Pitch recovery is gentler (1.5 s⁻¹ default) so sudden slope changes read as
            // smooth tilts rather than jarring snaps.
            setGlobalPosition(new Vector3(vehiclePos.getX(), vehiclePos.getY() + height, vehiclePos.getZ()));
            yaw   = Math.toDegrees(GD.lerpAngle(
                    Math.toRadians(yaw), Math.toRadians(vehicleYawDeg), yawRecoverySpeed * delta));
            pitch = GD.lerp(pitch, targetFollowPitch, pitchRecoverySpeed * delta);
            applyYawPitch(yaw + recoilYaw, GD.clamp(pitch + recoilPitch, pitchMin, pitchMax));
            if (activeCamera != null && tpsProxyNode != null) {
                activeCamera.setGlobalTransform(tpsProxyNode.getGlobalTransform());
            }
        }

        pendingYaw   = 0.0;
        pendingPitch = 0.0;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void applyYawPitch(double effYaw, double effPitch) {
        if (yawNode != null) {
            Vector3 yr = yawNode.getRotationDegrees();
            yr.setY(effYaw);
            yawNode.setRotationDegrees(yr);
        }
        if (pitchNode != null) {
            Vector3 pr = pitchNode.getRotationDegrees();
            pr.setX(effPitch);
            pitchNode.setRotationDegrees(pr);
        }
    }

    private boolean isAimingOrFiring() {
        return INSTANCE.isActionPressed("aim",  false)
            || INSTANCE.isActionPressed("fire", false);
    }
}
