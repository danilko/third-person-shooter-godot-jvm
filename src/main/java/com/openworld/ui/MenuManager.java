package com.openworld.ui;

import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.net.NetworkManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.Node;
import godot.core.Callable;
import godot.core.MethodCallable;
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
 *   - Show GameOverMenu on EventBus.allPlayersDied (the co-op "all players down"
 *     condition — NOT the per-body playerDied, which fires on any single teammate's death)
 *   - Own mouse-mode + SceneTree pause transitions
 *   - Expose restart() and quit() for child menus to call
 *
 * Placement: add MenuManager.tscn as a child of World.tscn.
 * Children PauseMenu and GameOverMenu are wired inside MenuManager.tscn.
 */
@Script(className = "MenuManager")
public class MenuManager extends CanvasLayer {

    private PauseMenu    pauseMenu;
    private GameOverMenu gameOverMenu;

    @Register
    @Override
    public void _ready() {
        pauseMenu    = (PauseMenu)    getNodeOrNull("PauseMenu");
        gameOverMenu = (GameOverMenu) getNodeOrNull("GameOverMenu");

        Node busNode = getNodeOrNull("/root/EventBus");
        if (busNode instanceof EventBus bus) {
            bus.allPlayersDied.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onAllPlayersDied"),
                    godot.api.Object.ConnectFlags.DEFAULT);
            bus.connectionLost.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onConnectionLost"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    @Register
    @Override
    public void _input(InputEvent event) {
        // "pause" (Esc / Start) opens and closes the pause menu; "ui_cancel" (Esc / pad B) only ever BACKS OUT -- of the
        // store, of the pause menu. Pad B is crouch in play, so it must never open a menu (PLAN.md 1.1 / F1).
        if (getNodeOrNull("SettingsMenu") != null) return;   // the settings page owns the keys until it closes
        boolean pausePressed = event.isActionPressed("pause", false);
        boolean backPressed = event.isActionPressed("ui_cancel", false)
                && (ShopMenu.isOpen() || (pauseMenu != null && pauseMenu.isVisible()));
        if (pausePressed || backPressed) {
            // an open store menu takes Esc first: it closes the menu, and the game does not pause (user, 2026-10-05)
            if (ShopMenu.isOpen()) {
                ShopMenu.current().close();
                getViewport().setInputAsHandled();
                return;
            }
            // Esc is only a pause toggle when the game-over screen is not up
            if (gameOverMenu == null || !gameOverMenu.isVisible()) {
                togglePause();
                getViewport().setInputAsHandled();
            }
        }
    }

    // ── EventBus listener ─────────────────────────────────────────────────────

    @Register
    public void onAllPlayersDied() {
        showGameOver();
    }

    /**
     * Client-side host-loss recovery (EventBus.connectionLost). Reuses the game-over overlay —
     * its Restart button reloads into a fresh single-player world and Quit exits — which is the
     * "notify and let the player restart the whole session" behaviour. The session is already
     * torn down by the time this fires (NetworkManager.onHostLost → leaveSession).
     */
    @Register
    public void onConnectionLost(String reason) {
        if (gameOverMenu != null) gameOverMenu.setBanner("Connection lost — " + reason);
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
        if (gameOverMenu != null) { gameOverMenu.show(); focusFirstButton(gameOverMenu); }
    }

    /**
     * A menu opened from a pad needs a focused control, or the D-pad / A (Godot's ui_up / ui_down / ui_accept, which
     * carry the pad by default) do nothing (F1). The first visible, enabled Button, depth first.
     */
    static boolean focusFirstButton(Node n) {
        if (n instanceof godot.api.BaseButton b && b.isVisibleInTree() && !b.isDisabled()
                && b.getFocusMode() != godot.api.Control.FocusMode.NONE) {
            b.grabFocus();
            return true;
        }
        for (Node c : n.getChildren()) if (focusFirstButton(c)) return true;
        return false;
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
            // Mirror restartLevel's session teardown for the no-GameManager fallback — otherwise
            // a restart here would reload the scene on top of a live ENet session (AutoLoad survives).
            Node netNode = getNodeOrNull("/root/NetworkManager");
            if (netNode instanceof NetworkManager net) net.leaveSession();
            getTree().reloadCurrentScene();
        }
    }

    public void quit() {
        // See GameManager.prepareForQuit() javadoc: SceneTree.quit() does not emit
        // Window.close_requested, so the audio-stop-on-quit sweep must be called explicitly here.
        Node gm = getNodeOrNull("/root/GameManager");
        if (gm instanceof GameManager manager) manager.prepareForQuit();
        getTree().quit();
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private void togglePause() {
        if (pauseMenu != null && pauseMenu.isVisible()) {
            resume();
        } else {
            getTree().setPause(true);
            Input.INSTANCE.setMouseMode(Input.MouseMode.VISIBLE);
            if (pauseMenu != null) { pauseMenu.show(); focusFirstButton(pauseMenu); }
            com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        }
    }
}
