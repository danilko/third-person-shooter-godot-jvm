package com.openworld.ui;

import com.openworld.character.Health;
import com.openworld.carrier.vehicle.Vehicle;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.NodePath;
import godot.global.GD;

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
@Script(className = "VehicleHUD")
public class VehicleHUD extends Control {

    @Export
    public NodePath speedLabelPath = new NodePath("Speed/ColorRect/SpeedValue");

    @Export
    public NodePath healthLabelPath = new NodePath("Health/ColorRect/Health");

    private RichTextLabel speedLabel;
    private Label healthLabel;
    private Vehicle vehicle;

    @Register
    @Override
    public void _ready() {
        Node s = getNodeOrNull(speedLabelPath);
        if (s instanceof RichTextLabel l) { speedLabel = l;}
        else {
            GD.print("speedLabelPath not found or not text label" + s.getName());
        }
        Node h = getNodeOrNull(healthLabelPath);
        if (h instanceof Label l) healthLabel = l;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (vehicle == null) return;

        if (speedLabel != null) {

            var speed = -vehicle.getGlobalBasis().getZ().dot(vehicle.getLinearVelocity());

            // Car motor
            var cfg = vehicle.getConfig();
            var speedRatio = speed / cfg.maxSpeed;
            var accelerationRatio = cfg.accelerationCurve != null
                    ? cfg.accelerationCurve.sampleBaked((float) speedRatio)
                    : Math.max(0.0, 1.0 - speedRatio);
            var accelerationForce = accelerationRatio * cfg.acceleration;

            speedLabel.setText(String.format("Speed: %4.1f m/s | %4.1f km/h | %4.1f mph\nMotoRatio: %.0f\nAccelForce: %.0f", speed, speed*3.6, speed*2.237, speedRatio * 100, accelerationForce));

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
        vehicle = (Vehicle) v;
        if (v == null) {
            if (speedLabel  != null) speedLabel.setText("---");
            if (healthLabel != null) healthLabel.setText("---");
        }
    }
}
