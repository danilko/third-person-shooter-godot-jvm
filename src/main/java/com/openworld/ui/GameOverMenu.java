package com.openworld.ui;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;

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

    /**
     * Sets the overlay's headline text — used to distinguish a host-loss recovery prompt from a
     * normal death. No-op when the scene has no "Title" Label child, so it never depends on a
     * specific .tscn layout (the default "Game Over" text simply stays).
     */
    public void setBanner(String text) {
        Node titleNode = getNodeOrNull("Title");
        if (titleNode instanceof Label label) label.setText(text);
    }

    @RegisterFunction
    public void onRestartPressed() {
        MenuManager mm = menuManager();
        if (mm != null) mm.restart();
    }

    @RegisterFunction
    public void onQuitPressed() {
        // See GameManager.prepareForQuit() javadoc: SceneTree.quit() does not emit
        // Window.close_requested, so the audio-stop-on-quit sweep must be called explicitly here.
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof GameManager manager) manager.prepareForQuit();
        getTree().quit();
    }

    private MenuManager menuManager() {
        return (getParent() instanceof MenuManager m) ? m : null;
    }
}
