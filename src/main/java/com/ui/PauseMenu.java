package com.ui;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Control;

/**
 * Pause-menu visual node — display only.
 *
 * All state transitions (Esc toggle, mouse mode, SceneTree pause) are owned
 * by the parent {@link MenuManager}.  This node just shows/hides itself and
 * forwards button signals upward.
 */
@RegisterClass(className = "PauseMenu")
public class PauseMenu extends Control {

    @RegisterFunction
    @Override
    public void _ready() {
        hide();
    }

    @RegisterFunction
    public void onResumePressed() {
        MenuManager mm = menuManager();
        if (mm != null) mm.resume();
    }

    @RegisterFunction
    public void onRestartPressed() {
        MenuManager mm = menuManager();
        if (mm != null) mm.restart();
    }

    @RegisterFunction
    public void onQuitPressed() {
        getTree().quit();
    }

    private MenuManager menuManager() {
        return (getParent() instanceof MenuManager m) ? m : null;
    }
}
