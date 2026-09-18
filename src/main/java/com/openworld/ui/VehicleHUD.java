package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node3D;
import godot.core.NodePath;

/**
 * In-vehicle HUD, bottom-right where the weapon panel sits on foot: the speed, and beside it a small top-down
 * damage diagram ({@link VehicleStatus}: body coloured by health, a square per wheel for its tire). No health
 * NUMBER — the diagram's colours say how bad it is, and the car itself smokes and burns ({@code Vehicle}'s damage
 * tiers). The player's own health stays under the minimap.
 *
 * Polls the vehicle each frame (speed changes continuously); HUDManager calls {@link #setVehicle} on enter
 * and passes null on exit.
 */
@Script(className = "VehicleHUD")
public class VehicleHUD extends Control {

    @Export public NodePath speedLabelPath = new NodePath("Speed/Value");
    @Export public NodePath unitLabelPath = new NodePath("Speed/Unit");
    /** Show mph instead of km/h. */
    @Export public boolean imperial = false;

    private Label speedLabel;
    private VehicleStatus status;
    private Vehicle vehicle;
    private int shown = Integer.MIN_VALUE;

    @Register
    @Override
    public void _ready() {
        if (getNodeOrNull(speedLabelPath) instanceof Label l) speedLabel = l;
        if (getNodeOrNull(unitLabelPath) instanceof Label u) u.setText(imperial ? "mph" : "km/h");
        if (getNodeOrNull("Speed/Status") instanceof VehicleStatus vs) status = vs;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (vehicle == null || speedLabel == null) return;
        var v = vehicle.getLinearVelocity();
        double ms = Math.hypot(v.getX(), v.getZ());           // ground speed, sign-free (reversing reads positive)
        int value = (int) Math.round(ms * (imperial ? 2.23694 : 3.6));
        if (value != shown) {
            shown = value;
            speedLabel.setText(String.valueOf(value));
        }
    }

    /** Called by HUDManager when the player enters/exits a vehicle. */
    public void setVehicle(Node3D v) {
        vehicle = v instanceof Vehicle car ? car : null;
        shown = Integer.MIN_VALUE;
        if (status != null) status.setVehicle(vehicle);
        if (vehicle == null && speedLabel != null) speedLabel.setText("0");
    }

    /** Readout for probes. */
    @Register
    public String speedTextNow() { return speedLabel != null ? speedLabel.getText() : ""; }

}
