package com.vehicle;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Camera3D;
import godot.api.Node3D;
import godot.core.Vector3;


@RegisterClass(className = "VehicleCameraController")
public class VehicleCameraController extends Node3D {
    @RegisterProperty @Export public float minDistance = 4.0f;
    @RegisterProperty @Export public float maxDistance = 8.0f;
    @RegisterProperty @Export public float height = 3.0f;

    @RegisterProperty @Export public float cameraSensitivty = 0.001f;


    private Node3D target;
    private Camera3D camera3D;

    @RegisterFunction
    @Override
    public void _ready() {
        target = (Node3D) getOwner();
        camera3D = (Camera3D) getNode("Camera3D");
        // Decouple from the vehicle's rotation so physics angular velocity
        // is not transmitted directly to the camera (prevents hard-turn motion sickness).
        setAsTopLevel(true);
    }

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        Vector3 fromTarget = camera3D.getGlobalPosition().minus(target.getGlobalPosition());

        if (fromTarget.length() < minDistance) {
            fromTarget = fromTarget.normalized().times(minDistance);
        } else if (fromTarget.length() > maxDistance) {
            fromTarget = fromTarget.normalized().times(maxDistance);
        }

        fromTarget.setY(height);
        camera3D.setGlobalPosition(target.getGlobalPosition().plus(fromTarget));

        // Guard: skip lookAt when camera is nearly directly above the target (gimbal lock).
        Vector3 lookDir = camera3D.getGlobalPosition().directionTo(target.getGlobalPosition()).abs().minus(Vector3.Companion.getUP());
        if (!lookDir.isZeroApprox()) {
            camera3D.lookAtFromPosition(camera3D.getGlobalPosition(), target.getGlobalPosition(), Vector3.Companion.getUP());
        }
    }
}
