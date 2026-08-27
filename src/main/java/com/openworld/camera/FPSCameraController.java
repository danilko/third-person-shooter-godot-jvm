package com.openworld.camera;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node3D;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.character.Character;

/**
 * First-person camera controller — positions the shared ActiveCamera at the bone mount
 * each frame when isFpsMode is true.
 *
 * No Camera3D lives here. The single Character.activeCamera is written by whichever
 * controller is active: CameraController (TPS) writes when !isFpsMode, this node
 * writes when isFpsMode. AimRay and AimTarget follow ActiveCamera automatically.
 *
 * Expected child hierarchy:
 *   FPSCameraController
 *     Yaw  (Node3D)
 *       Pitch  (Node3D)
 */
@Script(className = "FPSCameraController")
public class FPSCameraController extends Node3D {

    /** World-space anchor — assign the NeckAttachment BoneAttachment3D in the inspector. */
    @Export
    public Node3D fpsCameraMount;

    private Character character;
    private Node3D    yawNode;
    private Node3D    pitchNode;
    private Node3D    pivotNode;

    @Register
    @Override
    public void _ready() {
        yawNode   = (Node3D) getNode("Yaw");
        pitchNode = (Node3D) getNode("Yaw/Pitch");
        pivotNode = (Node3D) getNode("Yaw/Pitch/Pivot");
        setAsTopLevel(true);
        if (getParent() instanceof Character c) character = c;
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (fpsCameraMount == null || character == null) return;

        // Position: directly at the bone mount — no Pivot/SpringArm offset.
        setGlobalPosition(fpsCameraMount.getGlobalPosition());

        // Orientation: read from the character's canonical ControlRotation.
        // pitchMin/pitchMax were seeded by CameraController._ready().
        ControlRotation cr = character.controlRotation;
        double effYaw   = cr.yaw + cr.recoilYaw;
        double effPitch = GD.clamp(cr.pitch + cr.recoilPitch, cr.pitchMin, cr.pitchMax);

        Vector3 yr = yawNode.getRotationDegrees();
        yr.setY(effYaw);
        yawNode.setRotationDegrees(yr);

        Vector3 pr = pitchNode.getRotationDegrees();
        pr.setX(effPitch);
        pitchNode.setRotationDegrees(pr);

        // Write the FPS view transform to the shared ActiveCamera when in FPS mode.
        // Pivot mirrors the TPS double-180°Y cancellation so both rigs share the
        // same pitch convention — no per-mode sign flip needed.
        if (character.isFpsMode && character.activeCamera != null) {
            character.activeCamera.setGlobalTransform(pivotNode.getGlobalTransform());
        }
    }
}
