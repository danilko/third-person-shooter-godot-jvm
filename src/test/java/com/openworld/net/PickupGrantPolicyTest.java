package com.openworld.net;

import com.openworld.net.PickupGrantPolicy.Verdict;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PickupGrantPolicyTest {

    private static final double TOLERANCE = 4.0;

    private static Verdict eval(boolean pickupFound, boolean alreadyTaken, boolean characterFound,
            boolean senderOwns, double distance) {
        return PickupGrantPolicy.evaluate(pickupFound, alreadyTaken, characterFound, senderOwns,
                distance, TOLERANCE);
    }

    @Test
    void happyPathGrants() {
        assertEquals(Verdict.GRANT, eval(true, false, true, true, 1.0));
    }

    @Test
    void missingPickupRejected() {
        assertEquals(Verdict.NO_PICKUP, eval(false, false, true, true, 1.0));
    }

    @Test
    void alreadyTakenRejected() {
        // The contention case: two players grab the same item — the second request must lose.
        assertEquals(Verdict.ALREADY_TAKEN, eval(true, true, true, true, 1.0));
    }

    @Test
    void missingCharacterRejected() {
        assertEquals(Verdict.NO_CHARACTER, eval(true, false, false, true, 1.0));
    }

    @Test
    void nonOwnerRejected() {
        // A peer may only collect with characters it owns — forged characterIds are dropped.
        assertEquals(Verdict.NOT_OWNER, eval(true, false, true, false, 1.0));
    }

    @Test
    void farRequestRejected() {
        assertEquals(Verdict.TOO_FAR, eval(true, false, true, true, TOLERANCE + 0.01));
    }

    @Test
    void distanceExactlyAtToleranceGrants() {
        assertEquals(Verdict.GRANT, eval(true, false, true, true, TOLERANCE));
    }

    @Test
    void nonFiniteDistanceRejected() {
        assertEquals(Verdict.TOO_FAR, eval(true, false, true, true, Double.NaN));
        assertEquals(Verdict.TOO_FAR, eval(true, false, true, true, Double.POSITIVE_INFINITY));
    }
}
