package com.character;

import godot.annotation.RegisterClass;

/**
 * Placeholder controller for non-authority peers (Phase 4).
 *
 * On remote peers the character body exists but input must NOT be generated
 * locally — authoritative state arrives via MultiplayerSynchronizer.
 * isAuthority() returns false, so Character._physicsProcess skips gatherInput
 * entirely and lets the synchronizer drive position/animation/health.
 *
 * Phase 4 implementation:
 *   - Add receiveCommand(UserCommand cmd) for server-side replay
 *   - Add a ring buffer (size = max RTT in ticks) for client-side prediction
 *   - Connect to MultiplayerSynchronizer for state reconciliation
 */
@RegisterClass(className = "NetworkController")
public class NetworkController extends Controller {

    @Override
    public boolean isAuthority() { return false; }

    @Override
    public UserCommand gatherInput(double delta) {
        return new UserCommand();
    }
}
