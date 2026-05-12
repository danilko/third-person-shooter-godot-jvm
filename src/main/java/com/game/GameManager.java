package com.game;

import com.character.CharacterController;
import com.character.Player;
import com.character.PlayerController;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Input;
import godot.api.Node;
import godot.core.Callable;
import godot.core.StringNames;
import godot.global.GD;

/**
 * Central game state machine — registered as an AutoLoad singleton named "GameManager".
 *
 * Responsibilities:
 *  - Track current GameState (PLAYING, PAUSED, GAME_OVER)
 *  - Respond to player death (show game-over screen, restart, quit)
 *  - Provide a single entry point for scene transitions
 *
 * AutoLoad entry (add to project.godot after running ./gradlew build):
 *   [autoload]
 *   GameManager="*res://gdj/com/game/GameManager.gdj"
 *
 * Wire EventBus.playerDied → GameManager.onPlayerDied() in the scene or in _ready().
 */
@RegisterClass(className = "GameManager")
public class GameManager extends Node {

    public enum GameState {
        PLAYING,
        PAUSED,
        GAME_OVER
    }

    private GameState currentState = GameState.PLAYING;

    @RegisterFunction
    @Override
    public void _ready() {
        // Connect to EventBus once it is available as a sibling AutoLoad.
        // AutoLoads are added in order, so EventBus must be listed first in project.godot.
        Node eventBusNode = getNodeOrNull("/root/EventBus");
        if (eventBusNode instanceof EventBus) {
            EventBus bus = (EventBus) eventBusNode;
            bus.playerDied.connectUnsafe(Callable.createUnsafe(this, StringNames.toGodotName("onPlayerDied")), godot.api.Object.ConnectFlags.DEFAULT);
        }
    }

    // ── State transitions ─────────────────────────────────────────────────────

    @RegisterFunction
    public void onPlayerDied() {
        if (currentState != GameState.PLAYING) return;
        transitionTo(GameState.GAME_OVER);
        // MenuManager.onPlayerDied() (same signal) owns the pause + game-over UI.
    }

    public void pauseGame() {
        if (currentState != GameState.PLAYING) return;
        transitionTo(GameState.PAUSED);
        if (getTree() != null) getTree().setPause(true);
    }

    public void resumeGame() {
        if (currentState != GameState.PAUSED) return;
        transitionTo(GameState.PLAYING);
        if (getTree() != null) getTree().setPause(false);
    }

    public void restartLevel() {
        if (getTree() != null) getTree().setPause(false);
        Input.INSTANCE.setMouseMode(Input.MouseMode.CAPTURED);
        transitionTo(GameState.PLAYING);
        if (getTree() != null) getTree().reloadCurrentScene();
    }

    public void loadLevel(String scenePath) {
        transitionTo(GameState.PLAYING);
        if (getTree() != null) getTree().changeSceneToFile(scenePath);
    }

    // ── Getters ───────────────────────────────────────────────────────────────

    public GameState getCurrentState() {
        return currentState;
    }

    public boolean isPlaying() {
        return currentState == GameState.PLAYING;
    }

    // ── Bot-fill / L4D controller swap (Phase 4, Step 5) ─────────────────────

    /**
     * Called when the owning player disconnects.
     * Replaces the PlayerController with a CharacterController (AI bot) so the
     * game continues without a human driver.
     */
    public void onPlayerLeft(Player body) {
        Node ctrl = body.getNodeOrNull("PlayerController");
        if (ctrl != null) ctrl.queueFree();
        CharacterController bot = new CharacterController();
        body.addChild(bot);
        GD.print("GameManager: player left — bot attached to " + body.getName());
    }

    /**
     * Called when a player reconnects or takes control of a body.
     * Removes the AI CharacterController and reattaches a PlayerController so
     * the human drives the body again.
     */
    public void onPlayerJoined(Player body) {
        Node ctrl = body.getNodeOrNull("CharacterController");
        if (ctrl != null) ctrl.queueFree();
        PlayerController human = new PlayerController();
        body.addChild(human);
        GD.print("GameManager: player joined — PlayerController attached to " + body.getName());
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void transitionTo(GameState next) {
        GD.print("GameManager: " + currentState + " → " + next);
        currentState = next;
    }
}
