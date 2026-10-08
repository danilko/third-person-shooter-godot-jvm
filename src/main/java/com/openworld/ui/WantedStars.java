package com.openworld.ui;

import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.WantedSystem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Vector2;

/**
 * The wanted level in the HUD (PLAN.md W5): six stars left of the game clock, the earned ones lit, flashing for a
 * moment when the level changes (GTA). Hidden at zero stars. Self-gated, built in code by HUDManager.
 */
@Script(className = "WantedStars")
public class WantedStars extends Control {

    public static final float STAR = 22f, GAP = 4f;
    private int stars;
    /** The gang the local player stands worst with, and its stars (a second row, under the police's). */
    private String gang = "";
    private int gangStars;
    private double flash, poll;

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        int n = com.openworld.game.WantedRules.MAX_STARS;
        float w = n * STAR + (n - 1) * GAP;
        setAnchor(godot.core.Side.LEFT, 1f, false, true);
        setAnchor(godot.core.Side.RIGHT, 1f, false, true);
        setOffset(godot.core.Side.RIGHT, -GameClock.W - GameClock.MARGIN - 10f);
        setOffset(godot.core.Side.LEFT, -GameClock.W - GameClock.MARGIN - 10f - w);
        setOffset(godot.core.Side.TOP, GameClock.MARGIN + (GameClock.H - STAR) * 0.5f);
        // two rows tall (police, then the worst gang), so the rect is what is drawn and the feed can sit below it
        setOffset(godot.core.Side.BOTTOM, GameClock.MARGIN + (GameClock.H - STAR) * 0.5f + 2f * STAR + 6f);
    }

    @Register
    @Override
    public void _process(double delta) {
        if (flash > 0) { flash -= delta; queueRedraw(); }
        poll -= delta;
        if (poll > 0) return;
        poll = 0.2;
        int s = 0, gs = 0;
        String g = "";
        WantedSystem w = WantedSystem.get();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!p.isLocallyOwnedPlayer() || p.getCharacterInfo() == null) continue;
            if (w != null) {
                WantedSystem.Shown h = w.hudOf(p.getCharacterInfo().characterId);
                s = h.stars();
                g = h.gang();
                gs = h.gangStars();
            }
            break;
        }
        if (s != stars || gs != gangStars || !g.equals(gang)) {
            if (s != stars || gs != gangStars) flash = 2.0;
            stars = s;
            gangStars = gs;
            gang = g;
            queueRedraw();
        }
    }

    /** Stars shown (probe readout). */
    @Register public int starsShownNow() { return stars; }
    @Register public int gangStarsShownNow() { return gangStars; }

    @Register
    @Override
    public void _draw() {
        boolean off = flash > 0 && ((int) (flash * 6)) % 2 == 0;
        // the police row; under it the gang the player stands worst with, in that gang's colour (they are separate:
        // police stars reset at a hospital or a cell, a gang's do not)
        if (stars > 0) row(0f, com.openworld.game.WantedRules.MAX_STARS, stars, off, new Color(1f, 0.85f, 0.25f, 1f));
        if (gangStars > 0) {
            int max = com.openworld.game.WantedRules.MAX_STARS;
            row(STAR + 6f, max, gangStars, off, com.openworld.character.Faction.color(gang));
        }
    }

    private void row(float y, int max, int lit, boolean off, Color on) {
        for (int i = 0; i < max; i++) {
            boolean l = i < lit && !off;
            float cx = (float) getSize().getX() - (i + 0.5f) * (STAR + GAP) + GAP * 0.5f;
            star(new Vector2(cx, y + STAR * 0.5f), STAR * 0.5f, l ? on : new Color(0f, 0f, 0f, 0.35f));
        }
    }

    private void star(Vector2 c, float r, Color col) {
        PackedVector2Array outline = new PackedVector2Array();
        for (int k = 0; k < 10; k++) {
            double a = -Math.PI / 2 + k * Math.PI / 5;
            float rr = (k % 2 == 0) ? r : r * 0.45f;
            outline.append(new Vector2(c.getX() + (float) Math.cos(a) * rr, c.getY() + (float) Math.sin(a) * rr));
        }
        // a concave star: fan from the centre so each triangle is convex
        for (int k = 0; k < 10; k++) {
            PackedVector2Array tri = new PackedVector2Array();
            tri.append(c);
            tri.append(outline.get(k));
            tri.append(outline.get((k + 1) % 10));
            godot.core.PackedColorArray cols = new godot.core.PackedColorArray();
            cols.append(col);
            drawPolygon(tri, cols);
        }
        outline.append(outline.get(0));
        drawPolyline(outline, new Color(0f, 0f, 0f, 0.55f), 2f, true);
    }
}
