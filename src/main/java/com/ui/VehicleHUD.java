package com.ui;

import com.character.Health;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.RigidBody3D;
import godot.core.NodePath;

/**
 * In-vehicle HUD — shown by HUDManager when the player boards a vehicle.
 *
 * Polls the vehicle node each _process frame (no signals needed — speed
 * changes continuously). HUDManager calls setVehicle() before activating
 * this HUD and passes null on exit.
 *
 * Scene layout (VehicleHUD.tscn):
 *   Speed panel  — bottom-centre, large km/h reading
 *   Health panel — bottom-left,   vehicle HP
 */
@RegisterClass(className = "VehicleHUD")
public class VehicleHUD extends Control {

    @RegisterProperty @Export
    public NodePath speedLabelPath = new NodePath("Speed/ColorRect/SpeedValue");

    @RegisterProperty @Export
    public NodePath healthLabelPath = new NodePath("Health/ColorRect/Health");

    private Label speedLabel;
    private Label healthLabel;
    private Node3D vehicle;

    @RegisterFunction
    @Override
    public void _ready() {
        Node s = getNodeOrNull(speedLabelPath);
        if (s instanceof Label l) speedLabel = l;
        Node h = getNodeOrNull(healthLabelPath);
        if (h instanceof Label l) healthLabel = l;
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
        if (vehicle == null) return;

        if (speedLabel != null && vehicle instanceof RigidBody3D rb) {
            float ms  = (float) rb.getLinearVelocity().length();
            float kmh = ms * 3.6f;
            speedLabel.setText(String.format("%3.0f", kmh));
        }

        if (healthLabel != null) {
            Node healthNode = vehicle.getNodeOrNull("Health");
            if (healthNode instanceof Health h) {
                healthLabel.setText(String.valueOf((int) h.getCurrentHealth()));
            }
        }
    }

    /** Called by HUDManager when the player enters/exits a vehicle. */
    public void setVehicle(Node3D v) {
        vehicle = v;
        if (v == null) {
            if (speedLabel  != null) speedLabel.setText("---");
            if (healthLabel != null) healthLabel.setText("---");
        }
    }
}
