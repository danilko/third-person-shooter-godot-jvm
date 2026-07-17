package com.openworld.net;

import com.openworld.game.GameManager;

/**
 * Pure host-side grant decision for a client's MSG_VEHICLE_SEAT_REQUEST — same extraction
 * pattern as {@link PickupGrantPolicy}: the arbitration rules live here, engine-free and
 * unit-tested in {@code VehicleSeatPolicyTest}; the engine-bound handler in GameManager just
 * gathers the booleans and acts on the verdict.
 *
 * <p>Enter requests check the full set. Exit requests deliberately validate only that the
 * vehicle exists and the requesting character is its current occupant — an exit must never be
 * refusable for distance/health reasons (a dead or displaced driver still has to come out, or
 * the seat wedges shut forever).
 *
 * <p>The distance tolerance is generous for the same reason as the pickup grant: the host
 * evaluates the requester's ~50-100 ms-stale interpolated puppet position, so the check only
 * rejects requests from nowhere near the vehicle, never adjudicates a close race. A non-finite
 * distance (NaN from a corrupt position) is rejected.
 */
public final class VehicleSeatPolicy {

    public enum Verdict { GRANT, NO_VEHICLE, DESTROYED, SEAT_TAKEN, NO_CHARACTER, DEAD, NOT_OWNER, TOO_FAR, NOT_OCCUPANT }

    /** Matches the EntranceArea's reach with slack for interpolation staleness. */
    public static final double ENTER_TOLERANCE_METERS = 6.0;

    /** Wire value (u8) for "no specific seat — host picks" in MSG_VEHICLE_SEAT_REQUEST. */
    public static final int SEAT_AUTO = 255;

    private VehicleSeatPolicy() { }

    /**
     * Pure seat selection for an enter request (multi-seat). A concrete requested index is
     * granted only if free; {@link #SEAT_AUTO} scans from seat 0 (driver first — entering an
     * empty car takes the wheel, a car with a driver fills passenger seats in order).
     *
     * @return the seat index to grant, or -1 when nothing is available (requested seat taken
     *         or vehicle full) — the caller maps -1 to a {@link Verdict#SEAT_TAKEN} denial.
     */
    public static int pickSeat(boolean[] occupied, int requestedSeat) {
        if (occupied == null || occupied.length == 0) return -1;
        if (requestedSeat != SEAT_AUTO) {
            return (requestedSeat >= 0 && requestedSeat < occupied.length && !occupied[requestedSeat])
                    ? requestedSeat : -1;
        }
        for (int i = 0; i < occupied.length; i++) {
            if (!occupied[i]) return i;
        }
        return -1;
    }

    public static Verdict evaluateEnter(boolean vehicleFound, boolean vehicleAlive, boolean seatOccupied,
            boolean characterFound, boolean characterAlive, boolean senderOwnsCharacter,
            double distanceMeters, double toleranceMeters) {
        if (!vehicleFound) return Verdict.NO_VEHICLE;
        if (!vehicleAlive) return Verdict.DESTROYED;
        if (seatOccupied) return Verdict.SEAT_TAKEN;
        if (!characterFound) return Verdict.NO_CHARACTER;
        if (!characterAlive) return Verdict.DEAD;
        if (!senderOwnsCharacter) return Verdict.NOT_OWNER;
        if (!(distanceMeters <= toleranceMeters)) return Verdict.TOO_FAR;   // NaN-safe: !(NaN <= x) is true
        return Verdict.GRANT;
    }

    public static Verdict evaluateExit(boolean vehicleFound, boolean requesterIsOccupant,
            boolean senderOwnsCharacter) {
        if (!vehicleFound) return Verdict.NO_VEHICLE;
        if (!requesterIsOccupant) return Verdict.NOT_OCCUPANT;
        if (!senderOwnsCharacter) return Verdict.NOT_OWNER;
        return Verdict.GRANT;
    }
}
