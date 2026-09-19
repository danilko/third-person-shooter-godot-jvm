package com.openworld.world;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Light3D;
import godot.api.OmniLight3D;

/** The flash of a flashbang ({@link FlashBang}): a bright white light that fades out over {@link #SECONDS}, then frees itself. */
@Script(className = "FlashLight")
public class FlashLight extends OmniLight3D {

    public static final double SECONDS = 0.35;
    public static final float ENERGY = 12f;
    private double age = 0.0;

    @Register
    @Override
    public void _ready() {
        setShadow(false);
        setParam(Light3D.Param.ENERGY, ENERGY);
    }

    @Register
    @Override
    public void _process(double delta) {
        age += delta;
        setParam(Light3D.Param.ENERGY, (float) (ENERGY * Math.max(0.0, 1.0 - age / SECONDS)));
        if (age >= SECONDS) queueFree();
    }
}
