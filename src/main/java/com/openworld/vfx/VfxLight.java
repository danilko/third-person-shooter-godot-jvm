/*
 * Origin: a Java port of Binbun3D's GDScript (https://bun3d.com), licensed CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/:
 *   vfx_light.gd from "Godot Muzzle Flash", https://binbun3d.itch.io/muzzle-flash-vfx
 *   VFXOmniLightBB.gd from "Stylized Explosion FX", https://binbun3d.itch.io/explosion-fx
 * The pack licence text is in assets/vfx/LICENSE.txt; credited in CREDITS.md ("Visual effects").
 */
package com.openworld.vfx;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Light3D;
import godot.api.OmniLight3D;

/**
 * The flash light of a Binbun3D effect (CC0, see {@code assets/vfx/README.md}): an {@link OmniLight3D} whose
 * energies are {@code base × lightMultiplier}, so an effect's AnimationPlayer fades the light with ONE track
 * ({@code Light:light_multiplier}) whatever the base values are. Port of the packs' {@code vfx_light.gd} and
 * {@code VFXOmniLightBB.gd}, which were the same idea under two property names.
 *
 * Every export is a real property with an accessor pair, so an animation track writing
 * {@code light_multiplier} goes through {@link #setLightMultiplier} (godot-jvm binds an exported field through
 * its JavaBean accessors).
 */
@Script(className = "VfxLight")
public class VfxLight extends OmniLight3D {

    @Export public float baseEnergy = 2.0f;
    @Export public float baseIndirectEnergy = 1.0f;
    @Export public float baseFogEnergy = 1.0f;
    /** 0..1, animated by the effect. */
    @Export public float lightMultiplier = 1.0f;

    public float getBaseEnergy() { return baseEnergy; }
    public void setBaseEnergy(float v) { baseEnergy = v; apply(); }
    public float getBaseIndirectEnergy() { return baseIndirectEnergy; }
    public void setBaseIndirectEnergy(float v) { baseIndirectEnergy = v; apply(); }
    public float getBaseFogEnergy() { return baseFogEnergy; }
    public void setBaseFogEnergy(float v) { baseFogEnergy = v; apply(); }
    public float getLightMultiplier() { return lightMultiplier; }
    public void setLightMultiplier(float v) { lightMultiplier = v; apply(); }

    private void apply() {
        setParam(Light3D.Param.ENERGY, baseEnergy * lightMultiplier);
        setParam(Light3D.Param.INDIRECT_ENERGY, baseIndirectEnergy * lightMultiplier);
        setParam(Light3D.Param.VOLUMETRIC_FOG_ENERGY, baseFogEnergy * lightMultiplier);
    }
}
