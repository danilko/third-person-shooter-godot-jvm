package com.openworld.debug;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Rect2;
import godot.core.Vector2;

/**
 * The frame-time strip of the debug HUD ({@code PerfDebugOverlay} level 2+): the last {@link #SAMPLES} frames as a
 * line, with the 16.7 ms (60 fps) and 33.3 ms (30 fps) budgets drawn across it, the way CS's net_graph and the
 * Steam / Godot profilers show a frame budget. A spike reads as a hitch in time rather than as a changed average.
 */
@Script(className = "FrameTimeGraph")
public class FrameTimeGraph extends Control {

    static final int SAMPLES = 240;
    private static final double TOP_MS = 50.0;          // the strip's height stands for 0..50 ms
    private final double[] ms = new double[SAMPLES];
    private int head = 0;
    private int filled = 0;

    @Register
    @Override
    public void _process(double delta) {
        if (!isVisibleInTree()) return;
        ms[head] = delta * 1000.0;
        head = (head + 1) % SAMPLES;
        filled = Math.min(filled + 1, SAMPLES);
        queueRedraw();
    }

    /** {avg, 1% low as a frame time (the 99th percentile), max} over the window, in ms. */
    public double[] stats() {
        if (filled == 0) return new double[] {0, 0, 0};
        double[] s = new double[filled];
        double sum = 0;
        for (int i = 0; i < filled; i++) { s[i] = ms[i]; sum += ms[i]; }
        java.util.Arrays.sort(s);
        return new double[] {sum / filled, s[(int) Math.min(filled - 1, Math.floor(filled * 0.99))], s[filled - 1]};
    }

    @Register
    @Override
    public void _draw() {
        Vector2 size = getSize();
        double w = size.getX(), h = size.getY();
        drawRect(new Rect2(0, 0, w, h), new Color(0, 0, 0, 0.45), true, -1.0f, false);
        for (double budget : new double[] {1000.0 / 60.0, 1000.0 / 30.0}) {
            double y = h - h * budget / TOP_MS;
            drawLine(new Vector2(0, y), new Vector2(w, y), new Color(1, 1, 1, 0.25), 1.0f, false);
        }
        if (filled < 2) return;
        PackedVector2Array pts = new PackedVector2Array();
        for (int i = 0; i < filled; i++) {
            int idx = (head - filled + i + SAMPLES) % SAMPLES;
            double y = h - h * Math.min(ms[idx], TOP_MS) / TOP_MS;
            pts.append(new Vector2(w * i / (SAMPLES - 1.0), y));
        }
        drawPolyline(pts, new Color(0.45, 1.0, 0.45, 0.9), 1.0f, false);
    }
}
