package com.openworld.control;

/**
 * What owns a body's input right now (PLAN.md AR4, input half) -- one entry on {@link InputContextStack}. GAMEPLAY is
 * the empty stack and never pushed. On foot vs in a vehicle is NOT a context here: it is already derived from the seat
 * ({@code Character.currentVehicleNode}, one owner), and a second copy of it would be a latch to keep in step.
 */
public enum InputContext {
    /** An overlay that owns the keyboard and the pointer: the weapon wheel, a shop, the map, the console, the pause menu. */
    MENU(true, true),
    /** The body is held by the game, not by an overlay: arrested and being taken away. No commands, the view stays captured. */
    HELD(true, false);

    /** Whether the body's controller is skipped (an empty UserCommand) while this is on top. */
    public final boolean blocksGameplay;
    /** Whether the pointer is shown and free while this is on top (else captured for the look). */
    public final boolean showsCursor;

    InputContext(boolean blocksGameplay, boolean showsCursor) {
        this.blocksGameplay = blocksGameplay;
        this.showsCursor = showsCursor;
    }
}
