package com.openworld.control;

import com.openworld.net.NetworkManager;
import godot.annotation.RegisterClass;
import godot.api.Node;
import com.openworld.ai.AIController;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.net.NetworkController;

/**
 * Generates a UserCommand each physics tick for the Controllable that owns it.
 *
 * Equivalent to Unreal's AController / Source Engine's CBotController.
 * The owning Controllable calls gatherInput() when isAuthority() is true and
 * feeds the result into applyCommand() — same simulation path regardless of
 * whether the source is a human, AI, or network peer.
 *
 * Single-player: isAuthority() always returns true.
 * Network: isAuthority() resolves CharacterInfo.ownerPeerId against
 *   NetworkManager's localPeerId — true on the owning client (PlayerController)
 *   or server (AIController). Non-authority peers run NetworkController instead —
 *   it buffers and interpolates the MSG_SNAPSHOT frames NetworkManager decodes
 *   off the wire, driving the body's transform/combat/stance/health/weapon-slot
 *   directly (gatherInput/applyInput/physics never run for them).
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
     * Resolves CharacterInfo.ownerPeerId against NetworkManager.localPeerId —
     * always true in single-player (no peer assigned, or no CharacterInfo to check).
     */
    public boolean isAuthority() {
        // getParent(), not getOwner(): owner is Godot's scene-serialization metadata,
        // populated only for nodes that ship inside a .tscn — every controller
        // attachController() ever attaches at runtime (NetworkController,
        // ServerProxyController, bot-fill CharacterController) is a plain addChild()
        // with no setOwner(), so getOwner() is null for them and this check would
        // silently bypass to `true`. The driven Controllable is always the
        // controller's direct parent (Character._ready()'s own getChildren() scan
        // relies on exactly that), for both scene-defined and dynamic controllers.
        Node owner = getParent();
        if (!(owner instanceof Controllable c) || c.getCharacterInfo() == null) return true;
        Node netNode = getNodeOrNull("/root/NetworkManager");
        if (!(netNode instanceof NetworkManager net) || !net.isNetworked()) return true;
        return net.isAuthorityFor(c.getCharacterInfo());
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
