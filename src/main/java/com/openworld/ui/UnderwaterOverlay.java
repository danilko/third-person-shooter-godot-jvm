package com.openworld.ui;

import com.openworld.world.WaterVolume;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.ColorRect;
import godot.core.Color;

/**
 * The screen's blue tint while the camera ON SCREEN is under water: on foot, in first person, in a car's chase or
 * cockpit view, whoever owns the camera. Asks {@link WaterVolume#isUnderwater} of the viewport's current camera
 * each frame; the water mesh is single-sided, so under the surface nothing in the world says so and this does.
 *
 * It replaces a tint the CHARACTER drew from its own physics tick and its own camera: that tick is switched off in
 * a driver's seat and the car's camera is another node, so driving into the sea left the screen clear. The first
 * child of HUDManager, so the HUD panels draw over it.
 */
@Script(className = "UnderwaterOverlay")
public class UnderwaterOverlay extends ColorRect {

    public static final Color TINT = new Color(0.05, 0.32, 0.55, 0.45);

    @Register
    @Override
    public void _ready() {
        setColor(TINT);
        setMouseFilter(MouseFilter.IGNORE);
        setVisible(false);
    }

    @Register
    @Override
    public void _process(double delta) {
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        boolean under = cam != null && WaterVolume.isUnderwater(getTree(), cam.getGlobalPosition());
        if (under != isVisible()) setVisible(under);
    }

    @Register
    public boolean underwaterNow() { return isVisible(); }
}
