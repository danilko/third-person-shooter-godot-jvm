package com.openworld.ui;

import com.openworld.world.GameTime;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Font;
import godot.api.StyleBox;
import godot.core.Color;
import godot.core.HorizontalAlignment;
import godot.core.Rect2;
import godot.core.Vector2;
import godot.global.GD;

/**
 * The game's time of day in the HUD's top-right corner (user, 2026-10-02: "so it aligns with the trains and other
 * in-game events"): the same clock the station boards and the train screens use ({@link GameTime}), on the shared HUD
 * panel, with a sun or moon mark. The kill feed sits under it (HUDManager moves it down).
 *
 * <p>Self-gated and built in code by HUDManager, like the status feed's move: it is not a SITUATION, it is always up.
 */
@Script(className = "GameClock")
public class GameClock extends Control {

    static final String PANEL = "res://src/main/resources/com/openworld/ui/hud_panel.tres";
    static final String FONT = "res://assets/ui/Aldrich-Regular.ttf";

    @Export public boolean show = true;
    @Export public int fontSize = 22;
    /** Panel size, px; it sits {@link #MARGIN} px in from the top-right corner. */
    public static final float W = 116f, H = 38f, MARGIN = 20f;

    private StyleBox panel;
    private Font font;
    private String text = "";
    private double redrawIn;

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        if (GD.load(PANEL) instanceof StyleBox sb) panel = sb;
        if (GD.load(FONT) instanceof Font f) font = f;
        // anchored to the top-right corner, offsets in from it
        setAnchor(godot.core.Side.LEFT, 1f, false, true);
        setAnchor(godot.core.Side.RIGHT, 1f, false, true);
        setAnchor(godot.core.Side.TOP, 0f, false, true);
        setAnchor(godot.core.Side.BOTTOM, 0f, false, true);
        setOffset(godot.core.Side.LEFT, -W - MARGIN);
        setOffset(godot.core.Side.RIGHT, -MARGIN);
        setOffset(godot.core.Side.TOP, MARGIN);
        setOffset(godot.core.Side.BOTTOM, MARGIN + H);
    }

    @Register
    @Override
    public void _process(double delta) {
        redrawIn -= delta;
        if (redrawIn > 0) return;
        redrawIn = 0.25;
        String t = show ? GameTime.format(GameTime.hours(getTree())) : "";
        if (!t.equals(text)) {
            text = t;
            queueRedraw();
        }
    }

    /** The time shown (probe readout). */
    @Register public String clockTextNow() { return text; }

    @Register
    @Override
    public void _draw() {
        if (text.isEmpty() || font == null) return;
        if (panel != null) drawStyleBox(panel, new Rect2(0.0, 0.0, W, H));
        double h = GameTime.hours(getTree());
        boolean day = h >= 6.0 && h < 18.5;
        Vector2 c = new Vector2(20f, H * 0.5f);
        if (day) {
            drawCircle(c, 6f, new Color(1f, 0.82f, 0.30f, 1f), true, -1f, true);
            for (int i = 0; i < 8; i++) {
                double a = Math.PI * i / 4;
                drawLine(c.plus(new Vector2((float) Math.cos(a) * 8.5f, (float) Math.sin(a) * 8.5f)),
                        c.plus(new Vector2((float) Math.cos(a) * 11f, (float) Math.sin(a) * 11f)),
                        new Color(1f, 0.82f, 0.30f, 1f), 1.6f, true);
            }
        } else {
            drawCircle(c, 7f, new Color(0.85f, 0.88f, 1f, 1f), true, -1f, true);
            drawCircle(c.plus(new Vector2(3.5f, -2.5f)), 6f, new Color(0.05f, 0.06f, 0.1f, 1f), true, -1f, true);
        }
        Vector2 at = new Vector2(36f, H * 0.5f + fontSize * 0.36f);
        drawStringOutline(font, at, text, HorizontalAlignment.LEFT, -1f, fontSize, HudPalette.OUTLINE_PX,
                HudPalette.OUTLINE);
        drawString(font, at, text, HorizontalAlignment.LEFT, -1f, fontSize, HudPalette.TEXT);
    }
}
