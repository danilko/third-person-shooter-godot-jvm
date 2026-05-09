package com.character;

import godot.annotation.RegisterClass;
import godot.api.Node;

/**
 * Generates a UserCommand each physics tick for the Character that owns it.
 *
 * Equivalent to Unreal's AController / Source Engine's CBotController.
 * The owning Character calls gatherInput() when isAuthority() is true and
 * feeds the result into applyInput() — same simulation path regardless of
 * whether the source is a human, AI, or network peer.
 *
 * Single-player: isAuthority() always returns true.
 * Network (Phase 4): isAuthority() delegates to Godot's multiplayer authority
 *   system — true on the owning client (PlayerController) or server (AIController).
 *   Non-authority peers receive state via MultiplayerSynchronizer instead.
 */
@RegisterClass(className = "Controller")
public class Controller extends Node {

    /** Produce a UserCommand for the current tick. Only called when isAuthority(). */
    public UserCommand gatherInput(double delta) { return new UserCommand(); }

    /**
     * Whether this peer may run the simulation for the owned entity.
     * Defaults to isMultiplayerAuthority() on the owner node, which is always
     * true in single-player (every node is its own authority).
     */
    public boolean isAuthority() {
        Node owner = getOwner();
        return owner == null || owner.isMultiplayerAuthority();
    }
}
