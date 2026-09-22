package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Health;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node3D;
import godot.core.NodePath;

/**
 * In-vehicle HUD, bottom-right where the weapon panel sits on foot: the speed, and beside it a small top-down
 * damage diagram ({@link VehicleStatus}: body coloured by health, a square per wheel for its tire) and the car's
 * health as a percentage in the same colour ramp (user, 2026-09-22: the colours alone did not say how close the car
 * was to burning). The car also smokes and burns ({@code Vehicle}'s damage tiers). The player's own health stays
 * under the minimap.
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

    @Export public NodePath healthLabelPath = new NodePath("Speed/Health");

    private Label speedLabel;
    private Label healthLabel;
    private int shownHealth = Integer.MIN_VALUE;
    private VehicleStatus status;
    private Vehicle vehicle;
    private int shown = Integer.MIN_VALUE;

    @Register
    @Override
    public void _ready() {
        if (getNodeOrNull(speedLabelPath) instanceof Label l) speedLabel = l;
        if (getNodeOrNull(unitLabelPath) instanceof Label u) u.setText(imperial ? "mph" : "km/h");
        if (getNodeOrNull("Speed/Status") instanceof VehicleStatus vs) status = vs;
        if (getNodeOrNull(healthLabelPath) instanceof Label h) healthLabel = h;
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
        refreshHealth();
    }

    /** The car's health as a whole percentage, coloured like the diagram's body; rounded UP so a car at 0.4% reads 1%. */
    private void refreshHealth() {
        if (healthLabel == null) return;
        double f = vehicle.getNodeOrNull("Health") instanceof Health h && h.maxHealth > 0f
                ? Math.max(0.0, Math.min(1.0, h.getCurrentHealth() / h.maxHealth)) : 1.0;
        int pct = (int) Math.ceil(f * 100.0 - 0.01);
        if (pct == shownHealth) return;
        shownHealth = pct;
        healthLabel.setText(pct + "%");
        healthLabel.setModulate(HudPalette.forFraction(f));
    }

    /** Called by HUDManager when the player enters/exits a vehicle. */
    public void setVehicle(Node3D v) {
        vehicle = v instanceof Vehicle car ? car : null;
        shown = Integer.MIN_VALUE;
        shownHealth = Integer.MIN_VALUE;
        if (status != null) status.setVehicle(vehicle);
        if (vehicle == null && speedLabel != null) speedLabel.setText("0");
    }

    /** Readout for probes. */
    @Register
    public String speedTextNow() { return speedLabel != null ? speedLabel.getText() : ""; }

    /** Readout for probes: the health percentage shown, e.g. "72%". */
    @Register
    public String healthTextNow() { return healthLabel != null ? healthLabel.getText() : ""; }

}
