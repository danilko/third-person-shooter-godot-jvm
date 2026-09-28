package com.openworld.world;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ElevatorRulesTest {
    static final double DT = 1.0 / 60.0;

    static ElevatorRules lift() { return new ElevatorRules(new double[]{-7.84, 1.26}); }

    static void run(ElevatorRules r, double seconds, int riders, boolean blocked) {
        for (double t = 0; t < seconds; t += DT) r.step(DT, riders, blocked);
    }

    @Test
    void aCallOpensAndARiderIsTakenUpAndLandsExactlyOnTheStop() {
        ElevatorRules r = lift();
        r.call(0);
        run(r, 1.5, 0, false);
        assertEquals(ElevatorRules.Phase.OPEN, r.phase);
        assertTrue(r.landingOpen(0));
        r.board();
        run(r, 30.0, 1, false);
        assertEquals(1, r.stop);
        assertEquals(1.26, r.y, 1e-9);
        assertEquals(1, r.trips);
        // a rider who stays on does NOT ride back
        run(r, 30.0, 1, false);
        assertEquals(1, r.stop);
        assertEquals(1, r.trips);
        assertEquals(ElevatorRules.Phase.IDLE, r.phase);
    }

    @Test
    void theTripTakesAboutTheRiseOverTheSpeed() {
        ElevatorRules r = lift();
        r.phase = ElevatorRules.Phase.MOVING;
        r.target = 1;
        double t = 0;
        while (r.phase == ElevatorRules.Phase.MOVING && t < 60) { r.step(DT, 1, false); t += DT; }
        // 9.1 m at 1.5 m/s with 1.5 s of acceleration each end: 9.1 / 1.5 + 1.5 = 7.57 s
        assertEquals(9.1 / 1.5 + 1.5, t, 0.1);
    }

    @Test
    void theDoorsNeverShutOnSomebodyInTheDoorway() {
        ElevatorRules r = lift();
        r.call(0);
        run(r, 5.0, 0, false);                     // open, dwell running out, closing starts
        assertEquals(ElevatorRules.Phase.CLOSING, r.phase);
        r.step(DT, 0, true);                       // somebody steps in: they reopen
        assertEquals(ElevatorRules.Phase.OPENING, r.phase);
        run(r, 20.0, 0, true);                     // and stay open while the doorway is occupied
        assertEquals(ElevatorRules.Phase.OPEN, r.phase);
        run(r, 10.0, 0, false);
        assertEquals(ElevatorRules.Phase.IDLE, r.phase);
        assertEquals(0.0, r.door, 1e-9);
    }

    @Test
    void aCallAtTheOtherStopFetchesTheCarAndSomebodyWaitingDoesNotCycleTheDoors() {
        ElevatorRules r = lift();
        r.call(1);
        run(r, 15.0, 0, false);
        assertEquals(1, r.stop);
        assertTrue(r.phase == ElevatorRules.Phase.OPEN || r.phase == ElevatorRules.Phase.CLOSING
                || r.phase == ElevatorRules.Phase.IDLE);
        run(r, 30.0, 0, false);                    // nobody boards: it shuts once, and stays shut
        assertEquals(ElevatorRules.Phase.IDLE, r.phase);
        assertTrue(r.resting());
        assertFalse(r.landingOpen(1));
    }

    @Test
    void noLandingIsOpenWhileTheCarMoves() {
        ElevatorRules r = lift();
        r.call(1);
        for (int i = 0; i < 2000; i++) {
            r.step(DT, 0, false);
            if (r.phase == ElevatorRules.Phase.MOVING) {
                assertFalse(r.landingOpen(0));
                assertFalse(r.landingOpen(1));
                assertEquals(0.0, r.door, 1e-9);
            }
        }
    }
}
