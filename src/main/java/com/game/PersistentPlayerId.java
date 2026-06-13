package com.game;

import godot.api.ConfigFile;
import godot.core.Error;

import java.util.UUID;

/**
 * Stable client identity for rejoin (Part G — Step 6).
 *
 * ENet reassigns peer ids on every (re)connection, so they can't key a
 * {@link PlayerSession} across disconnects. This generates a UUID once per
 * install, caches it in {@code user://player_id.cfg}, and hands it back on
 * every later launch — the client sends it via NetworkManager.identifyPeer
 * immediately after connecting so the server can match it against an existing
 * (disconnected) session and restore the same body instead of spawning a new one.
 */
public final class PersistentPlayerId {

    private static final String PATH    = "user://player_id.cfg";
    private static final String SECTION = "player";
    private static final String KEY     = "id";

    private static String cached;

    private PersistentPlayerId() {
    }

    public static String getOrCreate() {
        if (cached != null) return cached;

        ConfigFile config = new ConfigFile();
        if (config.load(PATH) == Error.OK) {
            Object existing = config.getValue(SECTION, KEY, "");
            if (existing instanceof String s && !s.isEmpty()) {
                cached = s;
                return cached;
            }
        }

        cached = UUID.randomUUID().toString();
        config.setValue(SECTION, KEY, cached);
        config.save(PATH);
        return cached;
    }
}
