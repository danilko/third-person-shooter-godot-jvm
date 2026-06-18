package com.openworld.character;

import godot.core.Color;
import godot.core.Signal0;

/**
 * Anything that can show a floating {@code Nameplate} (com.openworld.ui.Nameplate): a
 * {@link Character}, a {@code carrier.vehicle.Vehicle}, or a future entity type.
 *
 * The nameplate binds to its parent purely through this interface (name + effective colour +
 * a change signal) plus two conventionally-named sibling nodes it discovers itself —
 * {@code "Health"} and {@code "WeaponController"}. So all entity-specific semantics live in the
 * implementer:
 * <ul>
 *   <li>a {@link Character} returns its own faction colour;</li>
 *   <li>a Vehicle returns its <em>driver's</em> faction colour (neutral when empty/defeated) and
 *       its <em>own</em> weapon — see the carrier nameplate notes in CLAUDE.md.</li>
 * </ul>
 *
 * <p>Lives in the {@code character} package (not {@code ui}) only to avoid a package cycle:
 * {@code ui} already depends on {@code character}, so the interface must not depend back on
 * {@code ui}. It references nothing but godot value types, so any package can implement it.
 */
public interface NameplateTarget {

    /** Display name shown on the plate. */
    String getNameplateText();

    /** Effective tint for the name label (the implementer decides how it is derived). */
    Color getNameplateColor();

    /**
     * Signal the implementer emits whenever the name, colour, or active weapon changes
     * (faction swap, weapon switch, driver enter/exit). The nameplate re-reads the getters on it.
     * Health and ammo refresh independently via the sibling Health/WeaponController node signals.
     */
    Signal0 getNameplateChangedSignal();
}
