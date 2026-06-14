package com.character;

import godot.api.Texture2D;

import java.util.HashMap;
import java.util.Map;

/**
 * Process-global weaponName → kill-feed icon lookup.
 *
 * The networked kill feed (MSG_ELIMINATION) carries the weapon's {@code weaponName}
 * String but never the {@link Texture2D} icon — textures don't serialize, and shipping
 * image bytes per kill would be wasteful and fragile. Instead every peer resolves the
 * icon LOCALLY from this registry: each {@link WeaponItem} registers its own
 * {@code weaponName → weaponIcon} in {@code _ready()}, so by the time a kill arrives the
 * attacker's replicated weapon body has already populated the entry. The host path is
 * unaffected (it passes the real icon directly); only the client elimination path looks
 * up here — see {@code GameManager.applyReplicatedElimination}.
 *
 * This is the "replicate ids, resolve assets locally, never send bytes" precedent every
 * future replicated cosmetic follows. Plain static state (not a Godot node) — the textures
 * are already resident in this process, so there is nothing to free or scope to a scene.
 */
public final class WeaponIconRegistry {

    private static final Map<String, Texture2D> ICONS_BY_NAME = new HashMap<>();

    private WeaponIconRegistry() { }

    /** Idempotent — re-registering the same name (every scene-instanced copy of a weapon) just refreshes it. No-op for a blank name or null icon. */
    public static void register(String weaponName, Texture2D icon) {
        if (weaponName == null || weaponName.isEmpty() || icon == null) return;
        ICONS_BY_NAME.put(weaponName, icon);
    }

    /** Returns the icon for a weaponName, or null when none was ever registered (the kill feed tolerates a null icon). */
    public static Texture2D get(String weaponName) {
        return weaponName == null ? null : ICONS_BY_NAME.get(weaponName);
    }
}
