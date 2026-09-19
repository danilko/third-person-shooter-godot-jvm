package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.carrier.vehicle.VehicleWheel;
import com.openworld.character.Health;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.core.Color;
import godot.core.Rect2;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

import java.util.List;

/**
 * The vehicle's damage diagram, left of the speed in {@link VehicleHUD}: the car seen from above, a body box
 * coloured by the vehicle's health and one square per wheel, placed where the wheels really are (so a motorcycle
 * shows two, a boat none). Colours are {@link HudPalette}'s state ramp:
 * <ul>
 *   <li>body: white, amber under half health, red under a quarter;</li>
 *   <li>wheel: white when sound, amber when the tire is damaged, red when flat, and pulsing while the car is
 *       sliding (the tires are over their grip).</li>
 * </ul>
 * Front is up. Polled every frame (cheap: a handful of rects).
 */
@Script(className = "VehicleStatus")
public class VehicleStatus extends Control {

    private Vehicle vehicle;
    private double pulse;

    public void setVehicle(Vehicle v) { vehicle = v; queueRedraw(); }

    @Register
    @Override
    public void _process(double delta) {
        if (vehicle == null) return;
        pulse += delta;
        queueRedraw();
    }

    /** "body 1.00 | FL 1.00 FR 0.00(flat) ..." for probes. */
    @Register
    public String stateNow() {
        if (vehicle == null || !GD.isInstanceValid(vehicle)) return "";
        StringBuilder sb = new StringBuilder(String.format("body %.2f |", bodyFraction()));
        for (VehicleWheel w : vehicle.getWheels()) sb.append(String.format(" %.2f%s", w.tireFraction(), w.isFlat() ? "(flat)" : ""));
        return sb.toString();
    }

    private double bodyFraction() {
        return vehicle.getNodeOrNull("Health") instanceof Health h && h.maxHealth > 0f
                ? Math.max(0.0, h.getCurrentHealth() / h.maxHealth) : 1.0;
    }

    @Register
    @Override
    public void _draw() {
        if (vehicle == null || !GD.isInstanceValid(vehicle)) return;
        Vector2 size = getSize();
        double w = size.getX(), h = size.getY();
        List<VehicleWheel> wheels = vehicle.getWheels();
        // wheel positions in the car's own frame (x right, -z forward), fitted into this control
        double minX = -1, maxX = 1, minZ = -2, maxZ = 2;
        if (!wheels.isEmpty()) {
            minX = minZ = Double.MAX_VALUE; maxX = maxZ = -Double.MAX_VALUE;
            for (VehicleWheel wh : wheels) {
                Vector3 p = vehicle.getGlobalTransform().affineInverse().times(wh.getGlobalPosition());
                minX = Math.min(minX, p.getX()); maxX = Math.max(maxX, p.getX());
                minZ = Math.min(minZ, p.getZ()); maxZ = Math.max(maxZ, p.getZ());
            }
            if (maxX - minX < 0.2) { minX -= 0.4; maxX += 0.4; }      // a single track (motorcycle): give it width
        }
        double spanX = maxX - minX, spanZ = maxZ - minZ;
        double k = Math.min((w - 8) / Math.max(spanX, 0.1), (h - 8) / Math.max(spanZ, 0.1));
        double cx = w / 2, cy = h / 2, mx = (minX + maxX) / 2, mz = (minZ + maxZ) / 2;
        double sq = Math.max(6.0, Math.min(10.0, w * 0.24));

        // body: between the wheels, a touch inset
        double bw = Math.max(sq, spanX * k - sq * 0.6), bh = Math.max(sq * 2, spanZ * k + sq * 0.6);
        Color body = HudPalette.forFraction(bodyFraction());
        drawRect(new Rect2(cx - bw / 2, cy - bh / 2, bw, bh), new Color(body.getR(), body.getG(), body.getB(), 0.85), true, -1f, false);

        boolean sliding = vehicle.isSlipping();
        double a = sliding ? 0.45 + 0.55 * Math.abs(Math.sin(pulse * 8.0)) : 1.0;
        for (VehicleWheel wh : wheels) {
            Vector3 p = vehicle.getGlobalTransform().affineInverse().times(wh.getGlobalPosition());
            double x = cx + (p.getX() - mx) * k, y = cy + (p.getZ() - mz) * k;     // +z (back) is down: front up
            float f = wh.tireFraction();
            Color c = wh.isFlat() ? HudPalette.CRITICAL : f < 1f ? HudPalette.WARN : HudPalette.TEXT;
            drawRect(new Rect2(x - sq / 2, y - sq / 2, sq, sq), new Color(0, 0, 0, 0.6), true, -1f, false);
            drawRect(new Rect2(x - sq / 2 + 1, y - sq / 2 + 1, sq - 2, sq - 2),
                    new Color(c.getR(), c.getG(), c.getB(), a), true, -1f, false);
        }
    }
}
