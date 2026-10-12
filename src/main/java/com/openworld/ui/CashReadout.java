package com.openworld.ui;

import com.openworld.game.profile.Profiles;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Font;
import godot.core.Color;
import godot.core.HorizontalAlignment;
import godot.core.Vector2;
import godot.global.GD;

/**
 * The local player's money, one row under the clock and the star rows (user, 2026-10-10: "no direct way to show the
 * money amount"; the hospital / arrest card no longer carries the bill). The balance is this install's own
 * {@link Profiles#local()} -- on a co-op client the host's deltas land there.
 *
 * <p>When the balance changes the amount moved is drawn left of it for {@link #DELTA_SECONDS} (red for money out,
 * green for money in), which is where a hospital bill or a bail is told now. A debt (a negative balance, CR4) is drawn
 * in red. Self-gated and built in code by HUDManager like the clock; in the minimal HUD it is shown on change and
 * fades (HUDManager.tickMinimal, id "cash"), and stays up while in debt.
 */
@Script(className = "CashReadout")
public class CashReadout extends Control {

    public static final float H = 24f, W = 320f;
    public static final double DELTA_SECONDS = 4.0;
    private static final Color GAIN = new Color(0.45, 0.9, 0.5, 1.0);
    private static final int FONT_SIZE = 20;

    private Font font;
    private long shown;
    private boolean seeded;
    private long delta;
    private double deltaLeft, pollIn;

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        if (GD.load(GameClock.FONT) instanceof Font f) font = f;
        setAnchor(godot.core.Side.LEFT, 1f, false, true);
        setAnchor(godot.core.Side.RIGHT, 1f, false, true);
        setAnchor(godot.core.Side.TOP, 0f, false, true);
        setAnchor(godot.core.Side.BOTTOM, 0f, false, true);
        setOffset(godot.core.Side.LEFT, -W - GameClock.MARGIN);
        setOffset(godot.core.Side.RIGHT, -GameClock.MARGIN);
        setOffset(godot.core.Side.TOP, HUDManager.cashTop());
        setOffset(godot.core.Side.BOTTOM, HUDManager.cashTop() + H);
    }

    @Register
    @Override
    public void _process(double dt) {
        if (deltaLeft > 0 && (deltaLeft -= dt) <= 0) { delta = 0; queueRedraw(); }
        if ((pollIn -= dt) > 0) return;
        pollIn = 0.1;
        long now = Profiles.local().balance;
        if (!seeded) { seeded = true; shown = now; queueRedraw(); return; }
        if (now == shown) return;
        delta = (deltaLeft > 0 ? delta : 0) + (now - shown);   // two bills in a row read as their sum
        deltaLeft = DELTA_SECONDS;
        shown = now;
        queueRedraw();
    }

    public static String dollars(long v) { return (v < 0 ? "-$" : "$") + String.format("%,d", Math.abs(v)); }

    /** "$5,000", or "-$15,000  $5,000" while a change is being told (probe readout). */
    @Register public String cashTextNow() { return (delta != 0 ? (delta > 0 ? "+" : "") + dollars(delta) + "  " : "") + dollars(shown); }
    public long balanceShown() { return shown; }
    public boolean inDebt() { return seeded && shown < 0; }

    @Register
    @Override
    public void _draw() {
        if (font == null || !seeded) return;
        float base = H * 0.5f + FONT_SIZE * 0.36f;
        String bal = dollars(shown);
        float bw = (float) font.getStringSize(bal, HorizontalAlignment.LEFT, -1f, FONT_SIZE).getX();
        text(new Vector2(W - bw, base), bal, shown < 0 ? HudPalette.CRITICAL : HudPalette.TEXT);
        if (delta == 0) return;
        String d = (delta > 0 ? "+" : "") + dollars(delta);
        float dw = (float) font.getStringSize(d, HorizontalAlignment.LEFT, -1f, FONT_SIZE).getX();
        text(new Vector2(W - bw - 14f - dw, base), d, delta > 0 ? GAIN : HudPalette.CRITICAL);
    }

    private void text(Vector2 at, String s, Color c) {
        drawStringOutline(font, at, s, HorizontalAlignment.LEFT, -1f, FONT_SIZE, HudPalette.OUTLINE_PX, HudPalette.OUTLINE);
        drawString(font, at, s, HorizontalAlignment.LEFT, -1f, FONT_SIZE, c);
    }
}
