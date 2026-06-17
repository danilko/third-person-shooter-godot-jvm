package com.openworld.carrier.vehicle;

import com.openworld.weapon.FirearmItem;

/**
 * Determines what weapon capability is available while a character occupies a vehicle.
 *
 *   NONE             — no shooting allowed (transport, heavy carrier)
 *   PASSENGER_WEAPON — character fires their own equipped weapon; vehicle camera is used
 *                      for aim; combat state is forced on while occupied (car, boat)
 *   VEHICLE_WEAPON   — vehicle has its own FirearmItem; character weapon is disabled;
 *                      fire button triggers the vehicle's weapon (tank, turret)
 *
 * Exported on Vehicle as an int (0/1/2) to avoid Godot-Kotlin enum-registration
 * complexity.  Use Vehicle.getWeaponMode() to get the typed value.
 */
public enum VehicleWeaponMode {
    NONE,
    PASSENGER_WEAPON,
    VEHICLE_WEAPON
}
