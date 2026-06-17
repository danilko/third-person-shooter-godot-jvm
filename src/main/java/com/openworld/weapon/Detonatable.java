package com.openworld.weapon;

import com.openworld.world.manager.ImpactManager;

/**
 * Marks a world object (grenade pickup, explosive barrel, mine) that detonates
 * when struck by a bullet. ImpactManager walks the hit node's parent chain to
 * find the first Detonatable and calls {@link #detonate()} after spawning VFX.
 */
public interface Detonatable {
    void detonate();
}
