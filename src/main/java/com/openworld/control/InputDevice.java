package com.openworld.control;

import godot.api.InputEvent;
import godot.api.InputEventJoypadButton;
import godot.api.InputEventJoypadMotion;
import godot.api.InputEventKey;
import godot.api.InputEventMouseButton;
import godot.api.InputEventMouseMotion;

/**
 * Which device the human used LAST (PLAN.md 1.1 / F1): keyboard + mouse or a gamepad. The one owner of the question
 * "is this a pad player?" -- prompt glyphs, aim assist and the analog walk read it; nothing else decides it. Fed every
 * input event by {@code game.GameManager._input} (an AutoLoad that processes while paused, so menus count too).
 * A stick has to move past {@link #STICK_WAKE} and a mouse past {@link #MOUSE_WAKE} pixels to switch, so a resting
 * pad's drift or a nudged desk mouse does not flip the glyphs back and forth.
 */
public final class InputDevice {
    private InputDevice() {}

    public enum Kind { KEYBOARD_MOUSE, PAD }

    public static final double STICK_WAKE = 0.35;
    public static final double MOUSE_WAKE = 4.0;

    private static Kind last = Kind.KEYBOARD_MOUSE;
    private static int switches = 0;

    public static Kind last() { return last; }

    public static boolean pad() { return last == Kind.PAD; }

    /** Times the device changed (probe readout). */
    public static int switches() { return switches; }

    public static void note(InputEvent e) {
        Kind k = null;
        if (e instanceof InputEventJoypadButton b && b.isPressed()) k = Kind.PAD;
        else if (e instanceof InputEventJoypadMotion m && Math.abs(m.getAxisValue()) > STICK_WAKE) k = Kind.PAD;
        else if (e instanceof InputEventKey key && key.isPressed()) k = Kind.KEYBOARD_MOUSE;
        else if (e instanceof InputEventMouseButton mb && mb.isPressed()) k = Kind.KEYBOARD_MOUSE;
        else if (e instanceof InputEventMouseMotion mm && mm.getRelative().length() > MOUSE_WAKE) k = Kind.KEYBOARD_MOUSE;
        if (k != null && k != last) {
            last = k;
            switches++;
        }
    }

    /** Set the device outright (probes, a settings override). */
    public static void force(Kind k) {
        if (k != null && k != last) { last = k; switches++; }
    }
}
