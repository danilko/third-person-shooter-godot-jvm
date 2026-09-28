package com.openworld.world;

/**
 * What a station LIFT does, engine-free (user, 2026-09-27: a lift beside every hub platform stair; `ElevatorRulesTest`).
 * {@link Elevator} is the node that feeds it its sensors and draws its answer.
 *
 * <p>A two-or-more-stop car with NO buttons, the way a game lift has to work: it answers whoever walks up to a landing
 * (a CALL), takes whoever walked in (BOARDED) to the other stop, and otherwise waits with its doors shut.
 * <ul>
 *   <li><b>IDLE</b> (doors shut at {@link #stop}): a call here, or anybody in a doorway, opens the doors; a call at
 *       another stop sends the car there.</li>
 *   <li><b>OPENING / OPEN / CLOSING</b>: the doors take {@code doorSeconds} each way and stay open {@code dwellSeconds}
 *       -- held open while anybody stands in the doorway, and REOPENED if somebody steps into it (or calls) while they
 *       close, so they never shut on a body.</li>
 *   <li>Doors shut with somebody who BOARDED on board: the car goes to the next stop. A rider who stays on after
 *       arriving does NOT ride back (no ping-pong); they walk out and in again, or step into the doorway.</li>
 *   <li><b>MOVING</b>: a trapezoid, {@code speed} top, {@code accel} both ends, landing exactly on the stop.</li>
 * </ul>
 * A call is an EVENT (somebody arriving at a landing), not a level: somebody who stays standing at a landing after
 * the car has opened for them does not make it open and shut for ever.
 */
public final class ElevatorRules {
    public enum Phase { IDLE, OPENING, OPEN, CLOSING, MOVING }

    public final double[] stops;
    public double speed = 1.5;
    public double accel = 1.0;
    public double doorSeconds = 1.2;
    public double dwellSeconds = 3.0;
    /** how long the doors stay open after the doorway clears */
    public double holdSeconds = 1.5;

    public Phase phase = Phase.IDLE;
    public int stop;
    public int target;
    public double y;
    public double v;
    /** 0 = shut, 1 = fully open (the doors at {@link #stop}; every other landing is shut) */
    public double door;
    public double dwell;
    public boolean boarded;
    public final boolean[] call;
    /** the number of trips completed (probe readout) */
    public int trips;

    public ElevatorRules(double[] stops) {
        if (stops.length < 2) throw new IllegalArgumentException("a lift needs two stops");
        this.stops = stops.clone();
        this.call = new boolean[stops.length];
        this.y = stops[0];
    }

    /** Somebody arrived at stop {@code s}'s landing. */
    public void call(int s) { if (s >= 0 && s < call.length) call[s] = true; }

    /** Somebody stepped into the car. Only counts while the doors are open (or opening). */
    public void board() { if (phase == Phase.OPEN || phase == Phase.OPENING) boarded = true; }

    /** True while nothing can change without a sensor event (the node may stop ticking). */
    public boolean resting() {
        if (phase != Phase.IDLE) return false;
        for (boolean c : call) if (c) return false;
        return true;
    }

    /** Whether the landing at stop {@code s} is open enough to walk through. */
    public boolean landingOpen(int s) { return s == stop && phase != Phase.MOVING && door > 0.9; }

    private int nextCalled() {
        for (int k = 1; k < stops.length; k++) {
            int s = (stop + k) % stops.length;
            if (call[s]) return s;
        }
        return -1;
    }

    private void depart(int to) {
        target = to;
        boarded = false;
        v = 0;
        phase = Phase.MOVING;
    }

    /**
     * One tick. {@code riders}: characters in the car; {@code doorwayBlocked}: anybody in the doorway at the current
     * stop (inside or out).
     */
    public void step(double dt, int riders, boolean doorwayBlocked) {
        switch (phase) {
            case IDLE -> {
                if (call[stop] || doorwayBlocked) {
                    phase = Phase.OPENING;
                } else {
                    int s = nextCalled();
                    if (s >= 0) depart(s);
                }
            }
            case OPENING -> {
                door = Math.min(1.0, door + dt / doorSeconds);
                if (door >= 1.0) {
                    phase = Phase.OPEN;
                    dwell = dwellSeconds;
                    call[stop] = false;
                }
            }
            case OPEN -> {
                call[stop] = false;                 // somebody arriving while it is open is served by this opening
                if (doorwayBlocked) dwell = Math.max(dwell, holdSeconds);
                dwell -= dt;
                if (dwell <= 0 && !doorwayBlocked) phase = Phase.CLOSING;
            }
            case CLOSING -> {
                if (doorwayBlocked || call[stop]) {
                    phase = Phase.OPENING;          // never shut on anybody
                    break;
                }
                door = Math.max(0.0, door - dt / doorSeconds);
                if (door <= 0.0) {
                    if (boarded && riders > 0) {
                        depart((stop + 1) % stops.length);
                    } else {
                        boarded = false;
                        int s = nextCalled();
                        if (s >= 0) depart(s);
                        else phase = Phase.IDLE;
                    }
                }
            }
            case MOVING -> {
                double goal = stops[target];
                double d = goal - y;
                double dir = Math.signum(d);
                double left = Math.abs(d);
                // brake so we stop exactly at the goal: the speed allowed at `left` metres out
                double vMax = Math.min(speed, Math.sqrt(2.0 * accel * left));
                double s = Math.abs(v);
                s = s < vMax ? Math.min(vMax, s + accel * dt) : vMax;
                double stepLen = s * dt;
                if (stepLen >= left || left < 1e-4) {
                    y = goal;
                    v = 0;
                    stop = target;
                    trips++;
                    phase = Phase.OPENING;
                } else {
                    y += dir * stepLen;
                    v = dir * s;
                }
            }
        }
    }
}
