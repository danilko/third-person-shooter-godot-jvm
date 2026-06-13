package com.game.net;

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

    private VehicleSeatPolicy() { }

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
