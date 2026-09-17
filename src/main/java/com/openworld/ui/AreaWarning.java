package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.game.EventBus;
import com.openworld.world.WorldBounds;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Font;
import godot.api.Node;
import godot.api.ThemeDB;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.HorizontalAlignment;
import godot.core.Rect2;
import godot.core.Vector2;

/**
 * "Leaving the area" — the world edge made VISIBLE (PLAN.md P0 0.6). {@code WorldBounds} no longer
 * pushes anything inside its wall; its warning band only raises {@code EventBus.leavingArea} /
 * {@code returnedToArea} for the local player, and this widget shows it: a line of text with the
 * distance to the wall and a red screen-edge vignette that deepens toward it.
 *
 * <p>Self-gated like {@link WeaponProgress}/{@link ScopeOverlay}, not in {@code HUDManager}'s
 * {@code BASE_LAYOUT}: being near the edge is not a SITUATION. The events decide shown/hidden; while
 * shown it reads the distance off {@link WorldBounds#distanceToWall} each frame (the one owner).
 */
@Script(className = "AreaWarning")
public class AreaWarning extends Control {

    @Export public Color vignetteColor = new Color(0.8f, 0.05f, 0.05f, 0.55f);

    @Export public Color textColor = new Color(1f, 0.85f, 0.2f, 1f);

    /** Vignette depth at full strength, as a fraction of the screen's shorter side. */
    @Export public float vignetteFraction = 0.18f;

    @Export public int fontSize = 30;

    private Character character;
    private boolean warned = false;
    private double distance = 0.0;
    private float strength = 0f;

    @Register
    public void wireCharacter(Node c) {
        character = (c instanceof Character ch) ? ch : null;
    }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        setVisible(false);
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) {
            bus.leavingArea.connectUnsafe(MethodCallable.createUnsafe(this, "onLeavingArea"),
                    godot.api.Object.ConnectFlags.DEFAULT);
            bus.returnedToArea.connectUnsafe(MethodCallable.createUnsafe(this, "onReturnedToArea"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    @Register
    public void onLeavingArea(float distanceToWall) {
        warned = true;
        distance = distanceToWall;
    }

    @Register
    public void onReturnedToArea() {
        warned = false;
    }

    /** True while the warning is on screen — gates read it. */
    @Register
    public boolean warningShown() { return isVisible(); }

    @Register
    @Override
    public void _process(double delta) {
        WorldBounds wb = WorldBounds.get();
        if (warned && wb != null && character != null && godot.global.GD.isInstanceValid(character)) {
            distance = wb.distanceToWall(character.getGlobalPosition());
            float band = Math.max(1f, wb.warnMargin);
            strength = (float) Math.max(0.0, Math.min(1.0, 1.0 - distance / band));
        }
        boolean show = warned;
        if (show != isVisible()) setVisible(show);
        if (show) queueRedraw();
    }

    @Register
    @Override
    public void _draw() {
        Vector2 size = getSize();
        float w = (float) size.getX(), h = (float) size.getY();
        if (w <= 1f || h <= 1f) return;
        float depth = Math.min(w, h) * vignetteFraction * (0.35f + 0.65f * strength);
        int steps = 12;
        for (int i = 0; i < steps; i++) {
            float t = i / (float) steps;
            float inset = depth * t;
            float a = (float) (vignetteColor.getA() * (1.0 - t) * (0.4 + 0.6 * strength)) / steps * 2f;
            Color c = new Color(vignetteColor.getR(), vignetteColor.getG(), vignetteColor.getB(), a);
            float band = depth / steps;
            drawRect(new Rect2(0f, inset, w, band), c, true, -1f, false);
            drawRect(new Rect2(0f, h - inset - band, w, band), c, true, -1f, false);
            drawRect(new Rect2(inset, 0f, band, h), c, true, -1f, false);
            drawRect(new Rect2(w - inset - band, 0f, band, h), c, true, -1f, false);
        }
        Font font = ThemeDB.getFallbackFont();
        if (font == null) return;
        float scale = h / 1080f;
        int fs = Math.max(10, Math.round(fontSize * scale));
        String line = "LEAVING THE AREA — turn back (" + Math.max(0L, Math.round(distance)) + " m)";
        // Drawn text gets the same dark outline the game theme gives every Label (game_theme.tres).
        drawStringOutline(font, new Vector2(0f, h * 0.22f), line, HorizontalAlignment.CENTER, w, fs,
                Math.max(2, Math.round(3 * scale)), new Color(0f, 0f, 0f, 0.85f));
        drawString(font, new Vector2(0f, h * 0.22f), line, HorizontalAlignment.CENTER, w, fs, textColor);
    }

    public Color getVignetteColor() { return vignetteColor; }
    public void setVignetteColor(Color v) { vignetteColor = v; }
    public Color getTextColor() { return textColor; }
    public void setTextColor(Color v) { textColor = v; }
    public float getVignetteFraction() { return vignetteFraction; }
    public void setVignetteFraction(float v) { vignetteFraction = v; }
    public int getFontSize() { return fontSize; }
    public void setFontSize(int v) { fontSize = v; }
}
