package com.openworld.ui;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.HBoxContainer;
import godot.api.StyleBox;
import godot.core.Color;
import godot.core.Rect2;
import godot.global.GD;

/**
 * Base class for all feed rows managed by {@link Feed}.
 *
 * Owns only the self-removal lifecycle: a countdown timer that calls
 * {@code queueFree()} when it expires, with an alpha fade-out over the
 * last {@link #FADE_DURATION} seconds.
 *
 * Subclasses add the visual layout and a typed {@code populate()} method
 * for their specific event data.  Example: {@link DefeatedFeedEntry}.
 */
@Script(className = "FeedEntry")
public class FeedEntry extends HBoxContainer {

    @Export
    public float lifespan = 4.0f;

    private static final float FADE_DURATION = 0.6f;

    private double timer = 0.0;

    /** The shared HUD panel style (ui/hud_panel.tres), drawn behind the row so every feed matches the HUD. */
    private static final String PANEL = "res://src/main/resources/com/openworld/ui/hud_panel.tres";
    private StyleBox panel;
    private godot.core.Vector2 drawnSize = new godot.core.Vector2();

    @Register
    @Override
    public void _ready() {
        timer = lifespan;
        if (GD.load(PANEL) instanceof StyleBox sb) panel = sb;
    }

    @Register
    @Override
    public void _draw() {
        if (panel == null) return;
        // 6 px of margin either side so the text does not sit on the panel's edge
        drawStyleBox(panel, new Rect2(-6.0, -1.0, getSize().getX() + 12.0, getSize().getY() + 2.0));
    }

    @Register
    @Override
    public void _process(double delta) {
        if (panel != null && !getSize().equals(drawnSize)) { drawnSize = getSize(); queueRedraw(); }
        timer -= delta;
        if (timer <= 0.0) {
            queueFree();
            return;
        }
        if (timer < FADE_DURATION) {
            setModulate(new Color(1f, 1f, 1f, (float)(timer / FADE_DURATION)));
        }
    }
}
