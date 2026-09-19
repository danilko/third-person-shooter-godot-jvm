/*
 * Origin: a Java port of Binbun3D's GDScript (https://bun3d.com), licensed CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/:
 *   VFXControllerBB.gd / VFXExplosionBB.gd from "Stylized Explosion FX", https://binbun3d.itch.io/explosion-fx
 *   vfx_controller.gd from "Godot Muzzle Flash", https://binbun3d.itch.io/muzzle-flash-vfx
 * The pack licence text is in assets/vfx/LICENSE.txt; credited in CREDITS.md ("Visual effects").
 */
package com.openworld.vfx;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.AnimationPlayer;
import godot.api.GPUParticles3D;
import godot.api.GeometryInstance3D;
import godot.api.Material;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.ShaderMaterial;

import java.util.ArrayList;
import java.util.List;

/**
 * A one-shot Binbun3D effect (CC0, see {@code assets/vfx/README.md}): a Node3D whose child GPUParticles3D,
 * meshes and {@link VfxLight} are driven by an {@code AnimationPlayer} animation named {@code "main"} (it
 * switches the emitters on and fades the light). {@link #play()} restarts it from the top; the caller owns
 * WHEN — a weapon on each shot, {@code ExplosionManager} per blast. Port of the packs' {@code VFXControllerBB.gd}
 * / {@code vfx_controller.gd} minus their editor-preview looping: nothing here autoplays or loops.
 */
@Script(className = "VfxEffect")
public class VfxEffect extends Node3D {

    static final String MAIN = "main";

    /** Playback speed of the particles and the animation together. */
    @Export public float speedScale = 1.0f;

    /**
     * How far this effect's shockwave (its {@code Rings} layer) CLEARLY VISIBLY reaches at scale 1, in metres —
     * MEASURED by {@code tools/godot/measure_explosion_radii.gd}, never typed. {@code ExplosionManager.playBlast}
     * sizes the shockwave to the damage radius with it. 0 = unmeasured.
     */
    @Export public float blastRadius = 0f;
    /** The fireball's ({@code Core} layer) visible reach at scale 1, measured the same way; playBlast sizes the
     *  effect so it covers half the damage radius. */
    @Export public float fireballRadius = 0f;

    public float getBlastRadius() { return blastRadius; }
    public void setBlastRadius(float v) { blastRadius = v; }
    public float getFireballRadius() { return fireballRadius; }
    public void setFireballRadius(float v) { fireballRadius = v; }

    public float getSpeedScale() { return speedScale; }
    public void setSpeedScale(float v) {
        speedScale = v;
        if (isInsideTree()) applySpeedScale();
    }

    private AnimationPlayer anim;
    private final List<GPUParticles3D> particles = new ArrayList<>();

    @Register
    @Override
    public void _ready() {
        particles.clear();
        for (Node c : getChildren()) {
            if (c instanceof GPUParticles3D p) particles.add(p);
            else if (c instanceof AnimationPlayer a) anim = a;
        }
        applySpeedScale();
    }

    /** Restart the effect from its first frame. Safe to call while it is still playing. */
    @Register
    public void play() {
        for (GPUParticles3D p : particles) p.restart();
        if (anim == null || !anim.hasAnimation(MAIN)) return;
        anim.stop();
        anim.play(MAIN);
        anim.seek(0.0, true);
    }

    /** True while the "main" animation is running (the effect's own length, particles aside). */
    @Register
    public boolean playingNow() {
        return anim != null && anim.isPlaying();
    }

    /** Registered twin of {@link #mainLength} for tools (a probe measuring the effect over its run). */
    @Register
    public double mainLengthNow() { return mainLength(); }

    /** Length of the "main" animation in seconds (0 if the scene has none). */
    public double mainLength() {
        return anim != null && anim.hasAnimation(MAIN) ? anim.getAnimation(MAIN).getLength() : 0.0;
    }

    private void applySpeedScale() {
        for (GPUParticles3D p : particles) p.setSpeedScale(speedScale);
        if (anim != null) anim.setSpeedScale(speedScale);
    }

    /**
     * Give every child emitter/mesh its OWN copy of its ShaderMaterial. The packs share one {@code .tres}
     * between several effects (and animate shader parameters on it), so without this every instance would
     * fade and recolour together.
     */
    protected void makeMaterialsLocal() {
        for (Node c : getChildren()) {
            if (c instanceof GeometryInstance3D g && g.getMaterialOverride() instanceof ShaderMaterial m) {
                g.setMaterialOverride((Material) m.duplicate());
            }
        }
    }

    /** Set one shader parameter on every child's material override. */
    protected void setShaderParam(String name, Object value) {
        for (Node c : getChildren()) {
            if (c instanceof GeometryInstance3D g && g.getMaterialOverride() instanceof ShaderMaterial m) {
                m.setShaderParameter(name, value);
            }
        }
    }
}
