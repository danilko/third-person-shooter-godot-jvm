package com.openworld.ui;

import com.openworld.game.GameManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Control;
import godot.api.Node;

/**
 * Pause-menu visual node — display only.
 *
 * All state transitions (Esc toggle, mouse mode, SceneTree pause) are owned
 * by the parent {@link MenuManager}.  This node just shows/hides itself and
 * forwards button signals upward.
 */
@Script(className = "PauseMenu")
public class PauseMenu extends Control {

    @Register
    @Override
    public void _ready() {
        hide();
    }

    @Register
    public void onResumePressed() {
        MenuManager mm = menuManager();
        if (mm != null) mm.resume();
    }

    @Register
    public void onRestartPressed() {
        MenuManager mm = menuManager();
        if (mm != null) mm.restart();
    }

    @Register
    public void onQuitPressed() {
        // GameManager.prepareForQuit() -- see its javadoc: SceneTree.quit() does NOT emit
        // Window.close_requested, so the audio-stop-on-quit sweep must be called explicitly here.
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof GameManager manager) manager.prepareForQuit();
        getTree().quit();
    }

    private MenuManager menuManager() {
        return (getParent() instanceof MenuManager m) ? m : null;
    }
}
