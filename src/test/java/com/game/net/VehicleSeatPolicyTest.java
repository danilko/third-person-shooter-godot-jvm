package com.game.net;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import com.game.net.VehicleSeatPolicy.Verdict;

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
    void exitChecksOnlyVehicleOccupantAndOwnership() {
        assertEquals(Verdict.GRANT,        VehicleSeatPolicy.evaluateExit(true,  true,  true));
        assertEquals(Verdict.NO_VEHICLE,   VehicleSeatPolicy.evaluateExit(false, true,  true));
        assertEquals(Verdict.NOT_OCCUPANT, VehicleSeatPolicy.evaluateExit(true,  false, true));
        assertEquals(Verdict.NOT_OWNER,    VehicleSeatPolicy.evaluateExit(true,  true,  false));
    }
}
