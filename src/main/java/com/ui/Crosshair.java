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

    /** Lerp speed when arms drift inward (bloom recovery between shots). */
    @Export @RegisterProperty public double crosshairContractSpeed = 1.0;

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

    private VariantArray<Node> lines;
    // Default matches weapon rest spread: 0.5° × 8 px/° = 4 px.
    private float positionX = 4.0f;

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
            positionX = weaponController.getCurrentSpreadDeg() * 8.0f;
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
