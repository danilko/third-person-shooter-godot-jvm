package com.ui;

import com.game.EventBus;
import com.game.GameManager;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.CanvasLayer;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.Node;
import godot.core.Callable;
import godot.core.StringNames;

/**
 * Central menu controller — owns all in-game overlay screens.
 *
 * Extends CanvasLayer so its children render on a dedicated 2D layer above
 * the 3D viewport.  This is the standard fix for Control nodes that appear
 * but do not respond to clicks inside a 3D scene: a CanvasLayer gives them
 * their own input pass before 3D input is processed.
 *
 * Responsibilities:
 *   - Toggle PauseMenu on Esc (when not in GAME_OVER state)
 *   - Show GameOverMenu on EventBus.playerDied
 *   - Own mouse-mode + SceneTree pause transitions
 *   - Expose restart() and quit() for child menus to call
 *
 * Placement: add MenuManager.tscn as a child of World.tscn.
 * Children PauseMenu and GameOverMenu are wired inside MenuManager.tscn.
 */
@RegisterClass(className = "MenuManager")
public class MenuManager extends CanvasLayer {

    private PauseMenu    pauseMenu;
    private GameOverMenu gameOverMenu;

    @RegisterFunction
    @Override
    public void _ready() {
        pauseMenu    = (PauseMenu)    getNodeOrNull("PauseMenu");
        gameOverMenu = (GameOverMenu) getNodeOrNull("GameOverMenu");

        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.playerDied.connectUnsafe(
                    Callable.createUnsafe(this, StringNames.toGodotName("onPlayerDied")),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    @RegisterFunction
    @Override
    public void _input(InputEvent event) {
        if (event.isActionPressed("ui_cancel", false)) {
            // Esc is only a pause toggle when the game-over screen is not up
            if (gameOverMenu == null || !gameOverMenu.isVisible()) {
                togglePause();
                getViewport().setInputAsHandled();
            }
        }
    }

    // ── EventBus listener ─────────────────────────────────────────────────────

    @RegisterFunction
    public void onPlayerDied() {
        showGameOver();
    }

    // ── Public API for child menus ────────────────────────────────────────────

    public void resume() {
        if (pauseMenu != null) pauseMenu.hide();
        Input.INSTANCE.setMouseMode(Input.MouseMode.CAPTURED);
        getTree().setPause(false);
    }

    public void showGameOver() {
        if (pauseMenu != null) pauseMenu.hide();
        getTree().setPause(true);
        Input.INSTANCE.setMouseMode(Input.MouseMode.VISIBLE);
        if (gameOverMenu != null) gameOverMenu.show();
    }

    public void restart() {
        if (pauseMenu    != null) pauseMenu.hide();
        if (gameOverMenu != null) gameOverMenu.hide();
        // GameManager.restartLevel() unpauses tree + resets mouse + reloads scene
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof GameManager manager) {
            manager.restartLevel();
        } else {
            getTree().setPause(false);
            Input.INSTANCE.setMouseMode(Input.MouseMode.CAPTURED);
            getTree().reloadCurrentScene();
        }
    }

    public void quit() {
        getTree().quit();
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private void togglePause() {
        if (pauseMenu != null && pauseMenu.isVisible()) {
            resume();
        } else {
            getTree().setPause(true);
            Input.INSTANCE.setMouseMode(Input.MouseMode.VISIBLE);
            if (pauseMenu != null) pauseMenu.show();
        }
    }
}
