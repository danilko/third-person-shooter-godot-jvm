package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.Script;
import godot.api.Resource;
import com.openworld.net.NetworkManager;

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
@Script(className = "CharacterInfo")
public class CharacterInfo extends Resource {

    /** UUID assigned at spawn. Auto-generated for local play; pre-set by network authority. */
    @Export public String characterId = "";

    /** Human-readable name shown in kill feed, HUD prompts, and pickup notifications. */
    @Export public String displayName = "Unknown";

    /** Faction membership. Use Faction constants or a custom string for new factions. */
    @Export public String faction = Faction.NEUTRAL;

    /**
     * The peer that owns/drives this character — replaces Godot's
     * {@code setMultiplayerAuthority} now that NetworkManager owns its own
     * ENet transport instead of MultiplayerAPI. Defaults to
     * {@code NetworkManager.SERVER_PEER_ID} (1), matching the convention that
     * every node is its own authority in single-player (where localPeerId is
     * also 1). The server stamps the real peer id at spawn time.
     */
    @Export public int ownerPeerId = 1;

    /**
     * A fresh instance carrying the same field values — used to <b>privatize</b> a
     * scene-embedded CharacterInfo in {@code _ready()}. A Godot sub-resource embedded in a
     * {@code .tscn} is <b>shared</b> across every instantiation of that scene unless
     * {@code resource_local_to_scene = true}; stamping a per-instance id onto that shared
     * object rewrites the identity of every sibling instance (the traffic-vehicle aliasing
     * bug). We privatize by copying fields into a brand-new instance rather than relying on
     * {@code resource_local_to_scene} (whose instantiate-time {@code duplicate()} reenters the
     * godot-kotlin-jvm TransferContext and throws a {@code Shared Buffer Error}).
     */
    public static CharacterInfo copyOf(CharacterInfo src) {
        CharacterInfo c = new CharacterInfo();
        if (src != null) {
            c.characterId = src.characterId;
            c.displayName = src.displayName;
            c.faction = src.faction;
            c.ownerPeerId = src.ownerPeerId;
        }
        return c;
    }
}
