package com.character;

import godot.annotation.RegisterClass;
import godot.api.Node;

/**
 * Generates a UserCommand each physics tick for the Controllable that owns it.
 *
 * Equivalent to Unreal's AController / Source Engine's CBotController.
 * The owning Controllable calls gatherInput() when isAuthority() is true and
 * feeds the result into applyCommand() — same simulation path regardless of
 * whether the source is a human, AI, or network peer.
 *
 * Single-player: isAuthority() always returns true.
 * Network (Phase 4): isAuthority() delegates to Godot's multiplayer authority
 *   system — true on the owning client (PlayerController) or server (AIController).
 *   Non-authority peers receive state via MultiplayerSynchronizer instead.
 *
 * Hot-swap (Phase 5): call setTarget() before reparenting to a new body so
 * gatherInput() immediately generates the right command type.
 */
@RegisterClass(className = "Controller")
public class Controller extends Node {

    // Explicit target override — set during hot-swap before reparenting.
    // When null, getControllable() falls back to the parent node.
    private Controllable explicitTarget;

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

    /**
     * Override the driven body explicitly for hot-swap transitions.
     * Once the controller is reparented and getParent() reflects the new body,
     * call setTarget(null) to clear the override.
     */
    public void setTarget(Controllable target) {
        this.explicitTarget = target;
    }

    /**
     * Returns the Controllable this controller is driving.
     * Prefers the explicit target set via setTarget(); falls back to the
     * parent node (which is the body when the controller is a scene child).
     */
    public Controllable getControllable() {
        if (explicitTarget != null) return explicitTarget;
        Node parent = getParent();
        return (parent instanceof Controllable c) ? c : null;
    }
}
