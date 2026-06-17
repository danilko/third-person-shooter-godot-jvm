package com.openworld.control;

import godot.api.Input;

/**
 * Hold-or-toggle modal input for a single named action.
 *
 * Pure Java helper (not a Godot node) used by {@link PlayerController} to drive
 * stance and the stealth modifier consistently. In HOLD mode the modal is active
 * only while the key is held; in TOGGLE mode each press flips it on/off. This is
 * the single place the "press vs. toggle" decision lives — the body's
 * {@code setStance} is now a pure idempotent setter with no toggle of its own.
 */
public class ModalInput {

    private final String action;
    private boolean toggled = false;

    public ModalInput(String action) {
        this.action = action;
    }

    /**
     * @param toggle {@code true} = TOGGLE (each press flips), {@code false} = HOLD (active while held).
     * @return whether the modal is active this tick.
     */
    public boolean poll(Input inp, boolean toggle) {
        if (toggle) {
            if (inp.isActionJustPressed(action, false)) toggled = !toggled;
            return toggled;
        }
        // HOLD: clear any latched toggle so switching modes at runtime stays clean.
        toggled = false;
        return inp.isActionPressed(action, false);
    }
}
