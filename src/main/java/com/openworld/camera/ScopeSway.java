package com.openworld.camera;

/**
 * The drift of a scoped view, and the held breath that steadies it (PLAN.md 2.7 piece 2).
 * Engine-free, so the rules are unit-tested ({@code ScopeSwayTest}) and not only probed.
 *
 * <p><b>What it produces is an OFFSET on the view</b>, in degrees, written into
 * {@link ControlRotation#swayPitch}/{@link ControlRotation#swayYaw} and added by both rigs beside the
 * recoil offset. It moves the camera, so it moves the AimRay that hangs off it, so the shot goes where
 * the scope's centre is — the drift is a real aiming problem, not a picture that lies about the
 * bullet. Like recoil it never touches {@code controlRotation.yaw/pitch}, the mouse intent, so the
 * player never fights it through the mouse and letting go of the scope leaves the aim exactly where
 * they put it.
 *
 * <p><b>The shape is two incommensurate sines per axis</b> — a slow figure-eight with a faster,
 * smaller wander on top — so it does not read as a metronome and cannot be timed by counting. Peak
 * yaw is the weapon's amplitude, peak pitch 70% of it (a rifleman's drift is wider than it is tall).
 *
 * <p><b>The amplitude is a LEVEL eased toward a target</b>, never switched, so the view never steps:
 * <ul>
 *   <li>not scoped -> 0 (the scope coming up starts the drift from rest, going down lets it settle);</li>
 *   <li>scoped -> 1;</li>
 *   <li>holding breath -> {@link #HELD_LEVEL};</li>
 *   <li>WINDED -> {@link #WINDED_LEVEL} — the price of holding too long, which is what makes the held
 *       breath a resource rather than a button you keep down.</li>
 * </ul>
 * The level is then scaled by the body's steadiness (prone is steadier than standing), which the
 * caller supplies because the stance is the character's fact, not this helper's.
 *
 * <p><b>Breath</b> is a 0..1 reserve. Holding spends it over {@link #holdSeconds}; running out makes
 * the shooter winded until the reserve is back to {@link #WINDED_CLEARS_AT}; otherwise it refills over
 * {@link #recoverSeconds}. A hold needs a fresh PRESS — keeping the key down through a winded spell
 * does not silently start a second hold the moment the spell ends (CoD's rule, and the only one under
 * which "why is my aim wobbling again" has an answer the player can see).
 */
public final class ScopeSway {

    /** Sway level while the breath is held: nearly still, not perfectly still. */
    public static final double HELD_LEVEL = 0.1;
    /** Sway level while winded, after a hold ran the reserve out. */
    public static final double WINDED_LEVEL = 1.8;
    /** The reserve a winded shooter must recover to before the penalty ends and a hold is possible. */
    public static final double WINDED_CLEARS_AT = 0.5;
    /** How fast the level follows its target, 1/s (a ~0.2 s time constant). */
    public static final double FOLLOW_RATE = 5.0;

    /** Seconds a full reserve lasts while held. */
    public double holdSeconds = 4.0;
    /** Seconds an empty reserve takes to refill. */
    public double recoverSeconds = 5.0;

    private double clock  = 0.0;
    private double level  = 0.0;
    private double breath = 1.0;
    private boolean winded  = false;
    private boolean holding = false;
    private boolean wasPressed = false;
    private double pitch = 0.0;
    private double yaw   = 0.0;

    /**
     * Advance one tick.
     *
     * @param dt           seconds
     * @param scoped       whether the view is behind a scope this tick
     * @param holdPressed  the hold-breath input, raw
     * @param amplitudeDeg the held weapon's peak drift; 0 = a weapon that does not sway
     * @param steadiness   the body's multiplier on the drift (1 standing, less crouched/prone)
     */
    public void tick(double dt, boolean scoped, boolean holdPressed, double amplitudeDeg, double steadiness) {
        if (dt <= 0.0) return;
        clock += dt;

        boolean pressedEdge = holdPressed && !wasPressed;
        wasPressed = holdPressed;

        // A hold starts only on a press, only scoped, and only with breath to spend; it ends the moment
        // any of those stops being true.
        if (!holdPressed || !scoped || winded) holding = false;
        else if (pressedEdge && breath > 0.0) holding = true;

        if (holding) {
            breath -= dt / Math.max(holdSeconds, 1e-3);
            if (breath <= 0.0) {
                breath  = 0.0;
                winded  = true;
                holding = false;
            }
        } else {
            breath = Math.min(1.0, breath + dt / Math.max(recoverSeconds, 1e-3));
            if (winded && breath >= WINDED_CLEARS_AT) winded = false;
        }

        double target;
        if (!scoped || amplitudeDeg <= 0.0) target = 0.0;
        else if (winded)                    target = WINDED_LEVEL;
        else if (holding)                   target = HELD_LEVEL;
        else                                target = 1.0;

        level += (target - level) * (1.0 - Math.exp(-FOLLOW_RATE * dt));
        if (target == 0.0 && level < 1e-4) level = 0.0;

        double a = Math.max(0.0, amplitudeDeg) * level * Math.max(0.0, steadiness);
        double t = 2.0 * Math.PI * clock;
        yaw   = a * (0.80 * Math.sin(0.21 * t)       + 0.20 * Math.sin(0.53 * t + 1.3));
        pitch = a * (0.55 * Math.sin(0.42 * t + 0.7) + 0.15 * Math.sin(0.83 * t + 2.1));
    }

    /** View pitch offset this tick, degrees, positive up. */
    public double pitch() { return pitch; }

    /** View yaw offset this tick, degrees. */
    public double yaw() { return yaw; }

    /** The breath reserve, 0..1. */
    public double breath() { return breath; }

    /** Whether a hold is in progress. */
    public boolean holding() { return holding; }

    /** Whether the shooter is winded (a hold ran the reserve out and it has not recovered). */
    public boolean winded() { return winded; }

    /**
     * Nothing to advance: no drift, a full breath, not winded. A tick while unscoped and at rest
     * changes only the phase clock (which no one can observe) and the press-edge memory, so a caller
     * may skip it — as long as it hands the input to {@link #observeInput} instead.
     */
    public boolean atRest() { return level == 0.0 && breath >= 1.0 && !winded && !holding; }

    /**
     * Record the hold-breath key on a skipped tick. Without it, a key already held when the scope
     * comes up would read as a fresh press and start a hold nobody asked for.
     */
    public void observeInput(boolean holdPressed) { wasPressed = holdPressed; }

    /** The eased sway level (0 at rest, 1 scoped, see the class doc). */
    public double level() { return level; }
}
