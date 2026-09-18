package com.openworld.ui;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.Character;
import com.openworld.game.mission.RaceDirector;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Font;
import godot.api.Node;
import godot.api.ThemeDB;
import godot.core.Color;
import godot.core.Rect2;
import godot.core.Vector2;
import godot.core.HorizontalAlignment;
import godot.global.GD;


/**
 * The race readout (PLAN.md 4.5 / R2): the countdown, then the clock, the placing, the lap and
 * checkpoint count, and the boost meter while driving.
 *
 * <h3>Self-gated, not table-managed, and it POLLS</h3>
 * A race is not a {@code HUDManager.Situation} — it is orthogonal to ON_FOOT / VEHICLE_DRIVE (you
 * can be on foot for the last 50 m of one), so {@code BASE_LAYOUT} could only ever hold a stale
 * answer. It polls {@link RaceDirector} each frame the way {@link WeaponProgress} polls the weapon
 * controller, which is also why a race needs no {@code EventBus} signal of its own: the one event a
 * race produces that anything else cares about is the mission completing, and that already exists.
 *
 * <p>Drawn procedurally, so it needs no texture and no second scene; the boost bar reads
 * {@code Vehicle.getBoostFraction()}, which has been exposed since the vehicle overhaul and until
 * now had no gauge.
 */
@Script(className = "RaceHUD")
public class RaceHUD extends Control {

    @Export public Color panelColor  = new Color(0f, 0f, 0f, 0.45f);
    @Export public Color textColor   = new Color(1f, 1f, 1f, 0.95f);
    @Export public Color accentColor = new Color(1.0f, 0.78f, 0.1f, 1f);
    @Export public Color boostColor  = new Color(0.25f, 0.8f, 1.0f, 0.9f);
    /** Font size at 1080p; scaled by viewport height like {@link AreaWarning}. */
    @Export public int fontSize = 22;
    @Export public int countdownFontSize = 96;

    private Character character;

    /** Wired by {@code HUDManager.wirePlayer} — the local player, whose race this displays. */
    @Register
    public void wireCharacter(Node c) {
        character = (c instanceof Character ch) ? ch : null;
    }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        setVisible(false);
    }

    @Register
    @Override
    public void _process(double delta) {
        RaceDirector race = RaceDirector.get();
        String id = racerId();
        boolean show = race != null && !id.isEmpty() && race.isRacer(id)
                && (race.raceActiveNow() || race.racerFinished(id));
        if (show != isVisible()) setVisible(show);
        if (show) queueRedraw();
    }

    private String racerId() {
        return character != null && GD.isInstanceValid(character) && character.characterInfo != null
                ? character.characterInfo.characterId : "";
    }

    @Register
    @Override
    public void _draw() {
        RaceDirector race = RaceDirector.get();
        String id = racerId();
        if (race == null || id.isEmpty()) return;
        Vector2 size = getSize();
        float w = (float) size.getX(), h = (float) size.getY();
        if (w <= 1f || h <= 1f) return;
        Font font = ThemeDB.getFallbackFont();
        if (font == null) return;
        float scale = h / 1080f;

        if (RaceDirector.PHASE_COUNTDOWN.equals(race.racePhaseNow())) {
            int fs = Math.max(24, Math.round(countdownFontSize * scale));
            int n = (int) Math.ceil(race.raceCountdownLeft());
            String line = n > 0 ? String.valueOf(n) : "GO";
            drawStringOutline(font, new Vector2(0f, h * 0.42f), line, HorizontalAlignment.CENTER, w, fs,
                    Math.max(3, Math.round(5 * scale)), new Color(0f, 0f, 0f, 0.85f));
            drawString(font, new Vector2(0f, h * 0.42f), line, HorizontalAlignment.CENTER, w, fs, accentColor);
            return;
        }

        int fs = Math.max(11, Math.round(fontSize * scale));
        float pad = 10f * scale;
        float lineH = fs * 1.35f;
        int rows = 3;
        float boostFraction = boostFraction();
        if (boostFraction >= 0f) rows++;
        float panelW = 250f * scale;
        float panelH = rows * lineH + pad * 2f;
        // Top-right, under the minimap (which sits at 24..212 px from the right edge at 1080p).
        float x = w - panelW - 24f * scale;
        float y = 232f * scale;
        drawRect(new Rect2(x, y, panelW, panelH), panelColor, true, -1f, false);

        float ty = y + pad + fs;
        drawRow(font, fs, x + pad, ty, panelW - pad * 2f, "TIME", clock(race.raceElapsed()), textColor);
        ty += lineH;
        float remaining = race.raceTimeRemaining();
        if (remaining >= 0f) {
            drawRow(font, fs, x + pad, ty, panelW - pad * 2f, "LEFT", clock(remaining),
                    remaining < 10f ? accentColor : textColor);
        } else {
            drawRow(font, fs, x + pad, ty, panelW - pad * 2f, "POS",
                    race.racerPlace(id) + "/" + race.racerCount(), textColor);
        }
        ty += lineH;
        int cps = race.raceCheckpointCount();
        String progress = "CP " + (race.racerNextIndex(id) + 1) + "/" + Math.max(1, cps)
                + "   LAP " + Math.min(race.raceLapCount(), race.racerLap(id) + 1) + "/" + race.raceLapCount();
        if (race.racerFinished(id)) {
            progress = "FINISHED  " + ordinal(race.racerPlace(id)) + "  " + clock(race.racerFinishTime(id));
        }
        drawString(font, new Vector2(x + pad, ty), progress, HorizontalAlignment.LEFT,
                panelW - pad * 2f, fs, race.racerFinished(id) ? accentColor : textColor);

        if (boostFraction >= 0f) {
            ty += lineH;
            float barW = panelW - pad * 2f;
            float barH = fs * 0.5f;
            drawRect(new Rect2(x + pad, ty - barH, barW, barH), new Color(1f, 1f, 1f, 0.15f), true, -1f, false);
            drawRect(new Rect2(x + pad, ty - barH, barW * boostFraction, barH), boostColor, true, -1f, false);
        }
    }

    private void drawRow(Font font, int fs, float x, float y, float w, String label, String value, Color c) {
        drawString(font, new Vector2(x, y), label, HorizontalAlignment.LEFT, w, fs,
                new Color(1f, 1f, 1f, 0.55f));
        drawString(font, new Vector2(x, y), value, HorizontalAlignment.RIGHT, w, fs, c);
    }

    /** 0..1 while the local racer is in a carrier that has a booster, else -1 (no bar). */
    private float boostFraction() {
        if (character == null || !GD.isInstanceValid(character)) return -1f;
        Node v = character.currentVehicleNode;
        return v instanceof Vehicle vehicle ? vehicle.getBoostFraction() : -1f;
    }

    private static String clock(float seconds) {
        int m = (int) (seconds / 60f);
        float s = seconds - m * 60f;
        return String.format("%d:%05.2f", m, s);
    }

    private static String ordinal(int place) {
        if (place <= 0) return "-";
        int mod100 = place % 100;
        if (mod100 >= 11 && mod100 <= 13) return place + "th";
        return switch (place % 10) {
            case 1 -> place + "st";
            case 2 -> place + "nd";
            case 3 -> place + "rd";
            default -> place + "th";
        };
    }

    public Color getPanelColor() { return panelColor; }
    public void setPanelColor(Color v) { panelColor = v; }
    public Color getTextColor() { return textColor; }
    public void setTextColor(Color v) { textColor = v; }
    public Color getAccentColor() { return accentColor; }
    public void setAccentColor(Color v) { accentColor = v; }
    public Color getBoostColor() { return boostColor; }
    public void setBoostColor(Color v) { boostColor = v; }
    public int getFontSize() { return fontSize; }
    public void setFontSize(int v) { fontSize = v; }
    public int getCountdownFontSize() { return countdownFontSize; }
    public void setCountdownFontSize(int v) { countdownFontSize = v; }
}
