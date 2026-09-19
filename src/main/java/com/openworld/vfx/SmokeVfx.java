/*
 * Origin: a Java port of Binbun3D's GDScript (https://bun3d.com), licensed CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/:
 *   vfx_smoke_controller.gd from "Godot 4.x Smoke VFX Effects", https://binbun3d.itch.io/smoke-vfx
 * The pack licence text is in assets/vfx/LICENSE.txt; credited in CREDITS.md ("Visual effects").
 */
package com.openworld.vfx;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.GPUParticles3D;
import godot.api.Node;
import godot.api.Node3D;

/**
 * A continuous Binbun3D smoke plume (CC0, {@code assets/vfx/smoke/}): a {@code Smoke} emitter plus an
 * invisible {@code ShadowCaster} emitter whose spheres give the plume a shadow. {@link #setEmitting} turns
 * both on or off; a vehicle toggles it from its damage tier, a wreck leaves it on.
 *
 * Port of {@code vfx_smoke_controller.gd}. Its colour/shading/alpha exports are gone: each smoke effect has
 * its own material and the pack's editor script had already written those values into it, so at runtime
 * they were never read.
 */
@Script(className = "SmokeVfx")
public class SmokeVfx extends Node3D {

    @Export public boolean emitting = true;

    public boolean getEmitting() { return emitting; }
    public void setEmitting(boolean v) {
        if (v == emitting && isInsideTree()) return;
        emitting = v;
        if (isInsideTree()) applyEmitting();
    }

    @Register
    public boolean emittingNow() { return emitting; }

    @Register
    @Override
    public void _ready() {
        applyEmitting();
    }

    private void applyEmitting() {
        for (Node c : getChildren()) {
            if (c instanceof GPUParticles3D p) p.setEmitting(emitting);
        }
    }
}
