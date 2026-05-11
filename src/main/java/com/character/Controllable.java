package com.character;

/**
 * Anything a Controller can possess — a Character on foot or a VehicleBody.
 *
 * Equivalent to Unreal's APawn interface for controller possession.
 * The two implementations diverge in what fields of UserCommand they consume:
 *   Character.applyCommand() reads movement/combat/weapon fields.
 *   Vehicle.applyCommand() reads throttle/steering/handbrake/drift.
 */
public interface Controllable {

    /** Apply one physics-tick command to this body. */
    void applyCommand(UserCommand cmd, double delta);

    /** Identity and faction data for targeting and kill-feed display. */
    CharacterInfo getCharacterInfo();
}
