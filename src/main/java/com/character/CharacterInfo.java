package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterProperty;
import godot.api.Resource;

/**
 * Identity data for a character instance.
 *
 * Attach as a Resource on the Character inspector field "characterInfo".
 * If characterId is left blank it is auto-assigned a UUID in Character._ready().
 * A network authority can pre-set characterId before _ready() fires to ensure
 * all peers share the same identifier for the same character.
 *
 * faction is a plain String — use Faction constants for the built-in values
 * (Faction.PLAYER, Faction.ENEMY, Faction.NEUTRAL) or any custom string for
 * future factions (e.g. "partyA", "civilian"). Hostility is resolved by
 * Faction.areHostile().
 */
@RegisterClass(className = "CharacterInfo")
public class CharacterInfo extends Resource {

    /** UUID assigned at spawn. Auto-generated for local play; pre-set by network authority. */
    @RegisterProperty @Export public String characterId = "";

    /** Human-readable name shown in kill feed, HUD prompts, and pickup notifications. */
    @RegisterProperty @Export public String displayName = "Unknown";

    /** Faction membership. Use Faction constants or a custom string for new factions. */
    @RegisterProperty @Export public String faction = Faction.NEUTRAL;

    /**
     * The peer that owns/drives this character — replaces Godot's
     * {@code setMultiplayerAuthority} now that NetworkManager owns its own
     * ENet transport instead of MultiplayerAPI. Defaults to
     * {@code NetworkManager.SERVER_PEER_ID} (1), matching the convention that
     * every node is its own authority in single-player (where localPeerId is
     * also 1). The server stamps the real peer id at spawn time.
     */
    @RegisterProperty @Export public int ownerPeerId = 1;
}
