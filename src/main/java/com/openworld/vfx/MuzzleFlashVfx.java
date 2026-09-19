/*
 * Origin: a Java port of Binbun3D's GDScript (https://bun3d.com), licensed CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/:
 *   vfx_controller.gd from "Godot Muzzle Flash", https://binbun3d.itch.io/muzzle-flash-vfx
 * The pack licence text is in assets/vfx/LICENSE.txt; credited in CREDITS.md ("Visual effects").
 */
package com.openworld.vfx;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.core.Color;

/**
 * A Binbun3D muzzle flash (CC0, {@code assets/vfx/muzzle_flash/}), instanced as {@code Muzzle/MuzzleVFX} in
 * each weapon scene and played by the weapon on every shot. The effect points down its local −Z (the
 * {@code Muzzle} marker's forward), so the instance carries no transform.
 *
 * Unlike an explosion, a flash's colours live HERE rather than in its materials: the pack shares one
 * {@code .tres} between several variants (e.g. {@code flash_03_front} is in two flashes of different colour)
 * and animates the glow's {@code alpha_multiplier} on it. So each instance copies its materials in
 * {@link #_ready} and writes its own colours into them — the port of {@code vfx_controller.gd}'s setters,
 * which only ever ran in the editor.
 */
@Script(className = "MuzzleFlashVfx")
public class MuzzleFlashVfx extends VfxEffect {

    @Export public Color primaryColor = new Color(1.0, 0.69, 0.0, 1.0);
    @Export public Color secondaryColor = new Color(1.0, 0.376, 0.0, 1.0);
    @Export public Color lightColor = new Color(1.0, 0.69, 0.0, 1.0);
    /** Peak energy of the flash light (faded to 0 by the animation). */
    @Export public float lightEnergy = 4.0f;

    public Color getPrimaryColor() { return primaryColor; }
    public void setPrimaryColor(Color v) { primaryColor = v; }
    public Color getSecondaryColor() { return secondaryColor; }
    public void setSecondaryColor(Color v) { secondaryColor = v; }
    public Color getLightColor() { return lightColor; }
    public void setLightColor(Color v) { lightColor = v; }
    public float getLightEnergy() { return lightEnergy; }
    public void setLightEnergy(float v) { lightEnergy = v; }

    @Register
    @Override
    public void _ready() {
        super._ready();
        makeMaterialsLocal();
        setShaderParam("primary_color", primaryColor);
        setShaderParam("secondary_color", secondaryColor);
        // Rest dark until the first shot: the glow's material rests at alpha 1 and only the "main" animation
        // fades it (the pack's script looped that animation, so nobody saw the resting glow).
        if (getNodeOrNull("Glow") instanceof godot.api.GeometryInstance3D glow
                && glow.getMaterialOverride() instanceof godot.api.ShaderMaterial m) {
            m.setShaderParameter("alpha_multiplier", 0.0);
        }
        if (getNodeOrNull("Light") instanceof VfxLight light) {
            light.setColor(lightColor);
            light.setBaseEnergy(lightEnergy);
            light.setLightMultiplier(0f);   // dark until the first shot
        }
    }
}
