package com.ui;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Control;

/**
 * Game-over overlay — display only.
 *
 * Shown by the parent {@link MenuManager} when {@code EventBus.playerDied}
 * fires.  This node just displays itself and forwards button signals upward.
 * All state transitions (pause, mouse mode) are owned by MenuManager.
 */
@RegisterClass(className = "GameOverMenu")
public class GameOverMenu extends Control {

    @RegisterFunction
    @Override
    public void _ready() {
        hide();
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
