package com.openworld.weapon;

import godot.api.Texture2D;

import java.util.HashMap;
import java.util.Map;
import com.openworld.carrier.vehicle.Vehicle;

/**
 * Process-global key → UI icon lookup, shared by every networked feed.
 *
 * Networked feeds (kill feed via {@code MSG_ELIMINATION}, pickup toasts) carry only a
 * short String key — the damage-source / display name (a weapon name like {@code "AR4"},
 * a vehicle source like {@code "Vehicle"}). Textures never cross the wire. Each peer
 * registers its own {@code key → icon} locally in {@code _ready()} (weapons via
 * {@link WeaponItem}, vehicles via {@code Vehicle}), so by the time an event arrives the
 * replicated source has already populated the entry and any peer can resolve the icon
 * without shipping image bytes.
 *
 * Generalized from the former weapon-only registry: any entity that can be a damage
 * source / feed subject registers here under the same key it stamps onto the event,
 * which is what lets a *vehicle* kill resolve its icon on a remote peer (previously
 * null — vehicles never registered). Plain static state, not a Godot node — the
 * textures are already resident in this process.
 */
public final class IconRegistry {

    private static final Map<String, Texture2D> ICONS = new HashMap<>();

    private IconRegistry() { }

    /** Idempotent — re-registering the same key just refreshes it. No-op for a blank key or null icon. */
    public static void register(String key, Texture2D icon) {
        if (key == null || key.isEmpty() || icon == null) return;
        ICONS.put(key, icon);
    }

    /** Returns the icon for a key, or null when none was ever registered (feeds tolerate a null icon). */
    public static Texture2D get(String key) {
        return key == null ? null : ICONS.get(key);
    }
}
