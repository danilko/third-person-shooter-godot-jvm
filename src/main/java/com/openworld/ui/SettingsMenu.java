package com.openworld.ui;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Node;

/**
 * The settings from the TITLE screen: the full-screen {@link GameMenu} without the in-game tabs (CONTROLS / DISPLAY /
 * GAME). {@link #open} adds it over the title; Back (or Esc / pad B) saves settings.cfg and closes, and the focus goes
 * back to the button that opened it.
 */
@Script(className = "SettingsMenu")
public class SettingsMenu extends GameMenu {

    private Node returnFocusTo;
    private static int opens;

    public static SettingsMenu open(Node parent, Node returnFocusTo) {
        SettingsMenu m = new SettingsMenu();
        m.returnFocusTo = returnFocusTo;
        m.setName("SettingsMenu");
        parent.addChild(m);
        opens++;
        return m;
    }

    @Register
    @Override
    public void _ready() {
        build();
        selectTabNow("CONTROLS");
    }

    @Register
    @Override
    public void close() {
        super.close();
        if (returnFocusTo instanceof Control c && godot.global.GD.isInstanceValid(c) && c.isVisibleInTree()) c.grabFocus();
        queueFree();
    }

    public static int opensNow() { return opens; }
}
