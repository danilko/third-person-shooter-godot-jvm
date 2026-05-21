package com.ui;

import com.character.WeaponController;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.VariantArray;
import godot.core.Vector2;
import godot.global.GD;

/**
 * Standalone HUD reticle.
 *
 * Spread is self-managed: each tick the target arm-offset is read directly from
 * the linked {@link WeaponController} (no external push required).  Visibility is
 * controlled by {@link #showCrosshair} — set it to false to collapse the arms to
 * centre without touching scene visibility, so the node can stay active for other
 * purposes (e.g. a vehicle weapon that overrides it later).
 *
 * Previous callers that pushed spread via {@code setPositionX()} still work; the
 * self-managed read simply overwrites that value the next frame if
 * {@code weaponController} is set.
 */
@RegisterClass(className = "Crosshair")
public class Crosshair extends Control {

    /**
     * Lerp speed when arms move outward (bloom spike after a shot).
     * Default 60 ≈ instant snap at 60 fps.
     */
    @Export @RegisterProperty public double crosshairExpandSpeed  = 60.0;

    // Fast enough to track bloom recovery (~0.5s) so the player gets clear visual
    // feedback when they have first-shot accuracy again — same as CS crosshair behaviour.
    @Export @RegisterProperty public double crosshairContractSpeed = 8.0;

    /**
     * Optional weapon controller for self-managed spread.
     * When set, the crosshair reads {@code getCurrentSpreadDeg()} every frame
     * instead of requiring an external {@code setPositionX()} call.
     */
    @Export @RegisterProperty public WeaponController weaponController;

    /**
     * Master visibility flag.  When {@code false} the arms lerp back to centre
     * each frame.  Toggle this from combat-state handlers or vehicle enter/exit
     * instead of hiding the node so the lerp animation still plays.
     */
    @Export @RegisterProperty public boolean showCrosshair = true;

    /**
     * Pixels per degree of spread. Increase for small spread values (e.g. 0.015°)
     * so the arms move a visible distance. At 100 px/deg: 0.015° → 1.5 px at rest,
     * 0.265° at max bloom → 26.5 px open.
     */
    @Export @RegisterProperty public float spreadPixelsPerDeg = 100f;

    private VariantArray<Node> lines;
    private float positionX = 0f;

    /** External override — still usable but overwritten next frame if weaponController is set. */
    public void setPositionX(float positionX) {
        this.positionX = positionX;
    }

    public void setShowCrosshair(boolean show) {
        this.showCrosshair = show;
    }

    @RegisterFunction
    @Override
    public void _ready() {
        lines = getNode("Reticle/Lines").getChildren();
    }

    @RegisterFunction
    public void onWeaponFire(float speedScale) {
        // Bloom expansion is already captured by getCurrentSpreadDeg(), so no
        // separate per-shot animation is needed here.
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
        // Self-managed spread: read live from weapon controller when available.
        if (weaponController != null) {
            positionX = weaponController.getCurrentSpreadDeg() * spreadPixelsPerDeg;
        }

        // Target: 0 when hidden (arms collapse to centre), positionX when shown.
        float target = showCrosshair ? positionX : 0f;

        for (Node line : lines) {
            Node2D currentLine = (Node2D) line.getNode("LineBase");
            Vector2 currentPos = currentLine.getPosition();
            double speed  = currentPos.getX() < target ? crosshairExpandSpeed : crosshairContractSpeed;
            double weight = Math.min(1.0, speed * delta);
            float  newX   = (float) GD.lerp(currentPos.getX(), target, weight);
            currentLine.setPosition(new Vector2(newX, currentPos.getY()));
        }
    }
}
