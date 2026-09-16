package com.openworld.weapon;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class WeaponStateTest {
    @Test
    void precedence() {
        assertEquals(WeaponState.SWITCHING, WeaponState.resolve(true, true, true, WeaponState.CYCLING));
        assertEquals(WeaponState.RELOADING, WeaponState.resolve(false, true, true, WeaponState.CYCLING));
        assertEquals(WeaponState.CYCLING, WeaponState.resolve(false, false, true, WeaponState.CYCLING));
        assertEquals(WeaponState.SETTLING, WeaponState.resolve(false, false, true, WeaponState.SETTLING));
        assertEquals(WeaponState.IDLE, WeaponState.resolve(false, false, false, WeaponState.SETTLING));
    }

    @Test
    void anUnnamedLockIsACycle() {
        assertEquals(WeaponState.CYCLING, WeaponState.resolve(false, false, true, null));
    }
}
