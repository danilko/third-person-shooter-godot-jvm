package com.openworld.ui;

import godot.core.Color;

/**
 * The HUD's colours, in one place. Colour carries MEANING and nothing else; selection is carried by LUMINANCE:
 * <ul>
 *   <li>panels are the minimap's translucent black ({@code ui/hud_panel.tres}); text is white with a thin
 *       {@link #OUTLINE}, secondary text {@link #TEXT_DIM};</li>
 *   <li>the SELECTED item is marked by a white ▶ and full brightness, the others are {@link #TEXT_DIM} — a
 *       difference in shape and brightness, not hue, so it reads for colour-blind players too;</li>
 *   <li>state runs white → {@link #WARN} amber → {@link #CRITICAL} red (health under 50% / 25%, a low / empty
 *       magazine). Red is kept for danger only (damage, critical, empty), never for selection, so it keeps its
 *       meaning; every state also changes something other than hue (bar length, the number itself).</li>
 * </ul>
 */
public final class HudPalette {
    private HudPalette() {}

    public static final Color TEXT = new Color(1.0, 1.0, 1.0, 1.0);
    public static final Color TEXT_DIM = new Color(1.0, 1.0, 1.0, 0.7);
    public static final Color WARN = new Color(1.0, 0.71, 0.25, 1.0);
    public static final Color CRITICAL = new Color(0.95, 0.33, 0.29, 1.0);
    public static final Color AIR = new Color(0.45, 0.8, 1.0, 0.95);
    /**
     * The ONE text outline: 2 px of 55% black at every font size (ui/game_theme.tres and every HUD LabelSettings
     * say the same). An outline's width is in pixels, so a constant size gives large and small text the same thin
     * edge; a heavy, opaque one reads as bold, smeared lettering.
     */
    public static final Color OUTLINE = new Color(0.0, 0.0, 0.0, 0.55);
    public static final int OUTLINE_PX = 2;

    /** White, amber under half, red under a quarter. */
    public static Color forFraction(double f) {
        return f < 0.25 ? CRITICAL : f < 0.5 ? WARN : TEXT;
    }
}
