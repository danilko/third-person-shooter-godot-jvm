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
 * The ring buffer stores the last BUFFER_SIZE server-broadcast UserCommands.
 * The server calls receiveCommand() to push authoritative state; the client
 * can retrieve buffered commands for replay via getBufferedCommand(tick).
 *
 * Phase 4 TODO (actual transport):
 *   - Wire receiveCommand() to an RPC sent by the server after each applyInput()
 *   - Connect MultiplayerSynchronizer sync_started / peer_synced to trigger
 *     reconciliation in the owning PlayerController
 */
@RegisterClass(className = "NetworkController")
public class NetworkController extends Controller {

    private static final int BUFFER_SIZE = 64;

    private final UserCommand[] buffer = new UserCommand[BUFFER_SIZE];

    @Override
    public boolean isAuthority() { return false; }

    @Override
    public UserCommand gatherInput(double delta) {
        return new UserCommand();
    }

    /**
     * Store a server-broadcast UserCommand in the ring buffer.
     * Called by the network layer when the server sends an authoritative command.
     * Keyed by tick so replay can retrieve the exact command at any past tick.
     */
    public void receiveCommand(UserCommand cmd) {
        buffer[(int)(cmd.tick % BUFFER_SIZE)] = cmd.copy();
    }

    /**
     * Retrieve the buffered command for a specific tick, or null if not present.
     * Used by reconciliation replay: iterate from lastServerAck+1 forward, calling
     * applyInput() on the body for each retrieved command.
     */
    public UserCommand getBufferedCommand(long tick) {
        UserCommand cmd = buffer[(int)(tick % BUFFER_SIZE)];
        return (cmd != null && cmd.tick == tick) ? cmd : null;
    }
}
