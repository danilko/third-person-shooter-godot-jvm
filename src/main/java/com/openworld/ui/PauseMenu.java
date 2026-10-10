package com.openworld.ui;

import com.openworld.game.GameManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;

/**
 * The pause menu: the in-game form of the full-screen {@link GameMenu} (STATUS / CONTROLS / DISPLAY / GAME).
 *
 * All state transitions (Esc toggle, mouse mode, SceneTree pause) are owned by the parent {@link MenuManager}. This
 * node shows / hides itself and forwards the session buttons upward.
 */
@Script(className = "PauseMenu")
public class PauseMenu extends GameMenu {

    @Register
    @Override
    public void _ready() {
        inGame = true;
        hide();
        build();
    }

    @Register
    @Override
    public void onQuitToTitlePressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        hide();
        com.openworld.game.FrontEnd.toTitle(this);
    }

    @Register
    @Override
    public void onResumePressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        MenuManager mm = menuManager();
        if (mm != null) mm.resume();
    }

    @Register
    @Override
    public void onRestartPressed() {
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        MenuManager mm = menuManager();
        if (mm != null) mm.restart();
    }

    @Register
    @Override
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
