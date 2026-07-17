package com.openworld.net;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import com.openworld.net.VehicleSeatPolicy.Verdict;

/** Full verdict matrix for the host-side seat arbitration — mirrors PickupGrantPolicyTest. */
class VehicleSeatPolicyTest {

    private static final double TOL = VehicleSeatPolicy.ENTER_TOLERANCE_METERS;

    private static Verdict enter(boolean vehicleFound, boolean vehicleAlive, boolean seatOccupied,
            boolean characterFound, boolean characterAlive, boolean ownsCharacter, double distance) {
        return VehicleSeatPolicy.evaluateEnter(vehicleFound, vehicleAlive, seatOccupied,
                characterFound, characterAlive, ownsCharacter, distance, TOL);
    }

    @Test
    void enterGrantsWhenAllChecksPass() {
        assertEquals(Verdict.GRANT, enter(true, true, false, true, true, true, 2.0));
        assertEquals(Verdict.GRANT, enter(true, true, false, true, true, true, TOL));   // boundary inclusive
    }

    @Test
    void enterDeniesInPriorityOrder() {
        assertEquals(Verdict.NO_VEHICLE,   enter(false, true,  false, true,  true,  true,  2.0));
        assertEquals(Verdict.DESTROYED,    enter(true,  false, false, true,  true,  true,  2.0));
        assertEquals(Verdict.SEAT_TAKEN,   enter(true,  true,  true,  true,  true,  true,  2.0));
        assertEquals(Verdict.NO_CHARACTER, enter(true,  true,  false, false, true,  true,  2.0));
        assertEquals(Verdict.DEAD,         enter(true,  true,  false, true,  false, true,  2.0));
        assertEquals(Verdict.NOT_OWNER,    enter(true,  true,  false, true,  true,  false, 2.0));
        assertEquals(Verdict.TOO_FAR,      enter(true,  true,  false, true,  true,  true,  TOL + 0.1));
    }

    @Test
    void enterRejectsNonFiniteDistance() {
        assertEquals(Verdict.TOO_FAR, enter(true, true, false, true, true, true, Double.NaN));
        assertEquals(Verdict.TOO_FAR, enter(true, true, false, true, true, true, Double.POSITIVE_INFINITY));
    }

    @Test
    void pickSeatAutoScansDriverFirst() {
        assertEquals(0, VehicleSeatPolicy.pickSeat(new boolean[] {false, false, false, false},
                VehicleSeatPolicy.SEAT_AUTO));                                    // empty car → wheel
        assertEquals(1, VehicleSeatPolicy.pickSeat(new boolean[] {true, false, false, false},
                VehicleSeatPolicy.SEAT_AUTO));                                    // driven car → first passenger seat
        assertEquals(3, VehicleSeatPolicy.pickSeat(new boolean[] {true, true, true, false},
                VehicleSeatPolicy.SEAT_AUTO));
        assertEquals(-1, VehicleSeatPolicy.pickSeat(new boolean[] {true, true, true, true},
                VehicleSeatPolicy.SEAT_AUTO));                                    // full
    }

    @Test
    void pickSeatHonoursConcreteRequests() {
        assertEquals(2, VehicleSeatPolicy.pickSeat(new boolean[] {true, false, false}, 2));
        assertEquals(-1, VehicleSeatPolicy.pickSeat(new boolean[] {true, false}, 0));   // requested taken
        assertEquals(-1, VehicleSeatPolicy.pickSeat(new boolean[] {false, false}, 7));  // out of range
        assertEquals(-1, VehicleSeatPolicy.pickSeat(new boolean[0], VehicleSeatPolicy.SEAT_AUTO));
        assertEquals(-1, VehicleSeatPolicy.pickSeat(null, VehicleSeatPolicy.SEAT_AUTO));
    }

    @Test
    void exitChecksOnlyVehicleOccupantAndOwnership() {
        assertEquals(Verdict.GRANT,        VehicleSeatPolicy.evaluateExit(true,  true,  true));
        assertEquals(Verdict.NO_VEHICLE,   VehicleSeatPolicy.evaluateExit(false, true,  true));
        assertEquals(Verdict.NOT_OCCUPANT, VehicleSeatPolicy.evaluateExit(true,  false, true));
        assertEquals(Verdict.NOT_OWNER,    VehicleSeatPolicy.evaluateExit(true,  true,  false));
    }
}
