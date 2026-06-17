package com.openworld.net.session;

import com.openworld.game.mission.MissionManager;

/**
 * Server-side bookkeeping for a connected (or disconnected-but-rejoinable) player.
 * Plain data holder — never sent whole over the wire, so it carries no Godot-object
 * overhead. Lives in {@link MissionManager#activeSessions}, keyed by peer id.
 *
 * Note: {@link #faction} is the player's base faction. Per-mission opposition is a
 * runtime override applied via D3's setRelationship() — never a mutation of this field.
 */
public class PlayerSession {
    public int peerId;
    public String characterId;
    public String faction;
    public boolean isConnected;
    public boolean isSpectating;

    public PlayerSession(int peerId, String characterId, String faction) {
        this.peerId = peerId;
        this.characterId = characterId;
        this.faction = faction;
        this.isConnected = true;
        this.isSpectating = false;
    }
}
