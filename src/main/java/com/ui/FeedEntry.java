package com.ui;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.HBoxContainer;
import godot.core.Color;

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
@RegisterClass(className = "FeedEntry")
public class FeedEntry extends HBoxContainer {

    @RegisterProperty
    @Export
    public float lifespan = 4.0f;

    private static final float FADE_DURATION = 0.6f;

    private double timer = 0.0;

    @RegisterFunction
    @Override
    public void _ready() {
        timer = lifespan;
    }

    @RegisterFunction
    @Override
    public void _process(double delta) {
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
