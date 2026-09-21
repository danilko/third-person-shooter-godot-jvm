package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.DirectionalLight3D;
import godot.api.Light3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

/**
 * "How dark is it" — the ONE owner, registered as the AutoLoad "DayNight".
 *
 * <p>Sky3D owns the clock, the sky and the sun's transform; nothing owned "is it night", so the two
 * things that need it — {@code Vehicle}'s headlights and {@link StreetLights} — would each have had to
 * re-derive it, and a lamp lit on a different threshold from the headlight beside it is exactly the
 * kind of two-owner drift this codebase keeps closing.
 *
 * <p><b>It is MEASURED off the sun light, not read off a clock.</b> Sky3D's `TimeOfDay` can be driven by
 * a system clock, a scripted beat or an editor scrub, and its own `sun_altitude` is stored in a frame this
 * code would have to guess at; the one fact that is always true is where the key light points. The sun is
 * above the horizon exactly while it shines DOWNWARD, so the elevation is {@code asin(-forward.y)} of the
 * `DirectionalLight3D` (a light shines along its own −Z). {@link #nightFactor} then ramps 0 → 1 across
 * civil twilight ({@link #dayElevation} down to {@link #nightElevation}), so dusk fades the lamps up
 * instead of switching them.
 *
 * <p>The sun is found by the group {@code "sun_light"} (both world scenes put Sky3D's `SunLight` in it),
 * else the brightest `DirectionalLight3D` in the tree, re-resolved if it is freed by a scene change. With
 * no directional light at all — a bare probe stand — {@link #nightFactor} is 0 and every consumer behaves
 * exactly as it did before this existed.
 */
@Script(className = "DayNight")
public class DayNight extends Node {

    private static DayNight instance;

    /** The live manager, or null if the AutoLoad isn't present (test scenes). */
    public static DayNight get() { return instance; }

    /** Sun elevation (degrees) at or above which it is fully day. */
    @Export public float dayElevation = 2.0f;
    /** Sun elevation (degrees) at or below which it is fully night (civil twilight ends near −6°). */
    @Export public float nightElevation = -8.0f;

    /** 0 in daylight, 1 in full night, ramping across twilight. */
    @Visible public float night = 0.0f;
    /** Sun elevation in degrees, positive above the horizon (a readout; the probe asserts against it). */
    @Visible public float sunElevation = 90.0f;

    private DirectionalLight3D sun;

    @Register
    @Override
    public void _ready() {
        instance = this;
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
    }

    @Register
    @Override
    public void _process(double delta) {
        DirectionalLight3D s = sunLight();
        if (s == null) {
            sunElevation = 90.0f;
            night = 0.0f;
            return;
        }
        // a DirectionalLight3D shines along its own -Z; the sun is up while that points downward
        Vector3 forward = s.getGlobalTransform().getBasis().getZ().times(-1.0);
        double len = forward.length();
        double elevation = len < 1e-6 ? 90.0 : Math.toDegrees(Math.asin(Math.max(-1.0, Math.min(1.0,
                -forward.getY() / len))));
        sunElevation = (float) elevation;
        double t = (dayElevation - elevation) / Math.max(0.001, dayElevation - nightElevation);
        night = (float) Math.max(0.0, Math.min(1.0, t));
    }

    private DirectionalLight3D sunLight() {
        if (sun != null && GD.isInstanceValid(sun) && sun.isInsideTree()) return sun;
        sun = null;
        for (Node n : getTree().getNodesInGroup(new StringName("sun_light"))) {
            if (n instanceof DirectionalLight3D d) { sun = d; break; }
        }
        if (sun == null) sun = brightestDirectional(getTree().getRoot());
        return sun;
    }

    private DirectionalLight3D brightestDirectional(Node from) {
        DirectionalLight3D best = null;
        for (Node c : from.getChildren()) {
            if (c instanceof DirectionalLight3D d && (best == null || d.getParam(Light3D.Param.ENERGY) > best.getParam(Light3D.Param.ENERGY))) {
                best = d;
            }
            DirectionalLight3D deep = brightestDirectional(c);
            if (deep != null && (best == null || deep.getParam(Light3D.Param.ENERGY) > best.getParam(Light3D.Param.ENERGY))) best = deep;
        }
        return best;
    }

    /** 0 by day, 1 at night; 0 when the AutoLoad is absent, so a probe stand is unaffected. */
    public static float nightFactor() {
        DayNight d = get();
        return d == null ? 0.0f : d.night;
    }

    /** True once it is dark enough to want lights on (half way through the twilight ramp). */
    public static boolean lightsWanted() {
        return nightFactor() > 0.35f;
    }

    @Register public float nightFactorNow() { return night; }
    @Register public float sunElevationNow() { return sunElevation; }
    @Register public boolean lightsWantedNow() { return lightsWanted(); }

    /** Where the key light is, for a probe that wants to put the sun somewhere without a clock. */
    @Register public Node3D sunLightNow() { return sunLight(); }
}
