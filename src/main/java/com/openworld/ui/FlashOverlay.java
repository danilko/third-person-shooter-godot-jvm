package com.openworld.ui;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.Node;
import godot.core.Color;

/**
 * The local player's flashbang blindness (FLA1): the whole screen white, held, then fading over the last
 * {@link #FADE_SECONDS}. Built in code on first use, like PerfDebugOverlay, so no scene wiring; drawn above the
 * HUD on purpose (a blinded player cannot read their ammo either, which is CS's rule too).
 *
 * <p>Local and cosmetic on every peer: each peer runs the flash for its own player from the detonation point
 * ({@code world.FlashBang}); nothing is sent.
 */
@Script(className = "FlashOverlay")
public class FlashOverlay extends CanvasLayer {

    public static final String NODE_NAME = "FlashOverlay";
    /** The white holds until this long before the end, then fades out. */
    public static final double FADE_SECONDS = 1.5;

    private double remaining = 0.0;
    private ColorRect rect;

    /** Blind the local screen for at least {@code seconds}. */
    public static void flash(Node context, double seconds) {
        if (context == null || context.getTree() == null || seconds <= 0) return;
        Node root = context.getTree().getRoot();
        FlashOverlay o = root.getNodeOrNull(NODE_NAME) instanceof FlashOverlay f ? f : null;
        if (o == null) {
            o = new FlashOverlay();
            o.setName(NODE_NAME);
            root.addChild(o);
        }
        o.remaining = Math.max(o.remaining, seconds);
    }

    /** Seconds of blindness left on this peer's screen (probe readout). */
    public static double remainingOf(Node context) {
        if (context == null || context.getTree() == null) return 0.0;
        return context.getTree().getRoot().getNodeOrNull(NODE_NAME) instanceof FlashOverlay f ? f.remaining : 0.0;
    }

    @Register
    public double remainingNow() { return remaining; }

    @Register
    @Override
    public void _ready() {
        setLayer(100);
        rect = new ColorRect();
        rect.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        rect.setMouseFilter(Control.MouseFilter.IGNORE);
        rect.setColor(new Color(1, 1, 1, 0));
        addChild(rect);
    }

    @Register
    @Override
    public void _process(double delta) {
        remaining = Math.max(0.0, remaining - delta);
        if (rect != null) {
            double a = Math.min(1.0, remaining / FADE_SECONDS);
            rect.setColor(new Color(1, 1, 1, a));
            rect.setVisible(a > 0.0);
        }
    }
}
