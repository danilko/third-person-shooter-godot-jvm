package com.openworld.weapon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.openworld.weapon.Accuracy.Posture;
import com.openworld.weapon.Accuracy.Tuning;
import org.junit.jupiter.api.Test;

/** Pins the one accuracy owner (PLAN.md 2.8 item 3). */
class AccuracyTest {

    private static final double EPS = 1e-9;
    /** SNR1-like: tiny base cone, big bloom, hipfire x8. */
    private static final Tuning SNIPER = new Tuning(0.005, 0.6, 0.5, 0.6, 0.34, 8.0);
    private static final Tuning RIFLE = new Tuning(0.01, 0.05, 0.3, 0.25, 0.34, 1.0);

    @Test
    void firstShotHasBaseSpreadOnly() {
        // W31: bloom is added AFTER a shot, so a fresh weapon's cone is its base spread.
        assertEquals(0.005, Accuracy.cone(SNIPER, 0.0, 0.0, 8.0, Posture.UPRIGHT, true), EPS);
        double afterOne = Accuracy.bloomAfterShot(0.0, SNIPER);
        assertEquals(0.6, afterOne, EPS);
        assertEquals(0.605, Accuracy.cone(SNIPER, afterOne, 0.0, 8.0, Posture.UPRIGHT, true), EPS);
    }

    @Test
    void noMovementPenaltyBelowTheStandingThreshold() {
        // 0.34 x 8 = 2.72 m/s: a 0.73 m/s steering jitter and a slow creep cost nothing.
        assertEquals(0.0, Accuracy.movementPenalty(0.73, 8.0, 0.34), EPS);
        assertEquals(0.0, Accuracy.movementPenalty(2.72, 8.0, 0.34), EPS);
        assertTrue(Accuracy.movementPenalty(2.9, 8.0, 0.34) > 0.0);
    }

    @Test
    void penaltyRampsToTheFullLinearTermAtMaxSpeed() {
        assertEquals(0.03 * 8.0, Accuracy.movementPenalty(8.0, 8.0, 0.34), EPS);
        double mid = (2.72 + 8.0) / 2.0;
        assertEquals(0.03 * 8.0 * 0.5, Accuracy.movementPenalty(mid, 8.0, 0.34), 1e-9);
        // beyond max (a slide, a fall) it continues linearly, with no step at max
        assertEquals(0.03 * 10.0, Accuracy.movementPenalty(10.0, 8.0, 0.34), EPS);
        assertEquals(Accuracy.movementPenalty(8.0 - 1e-7, 8.0, 0.34), Accuracy.movementPenalty(8.0, 8.0, 0.34), 1e-6);
    }

    @Test
    void thresholdScalesWithALowerMaxSpeed() {
        // a scoped slowdown to 40% lowers the max to 3.2 m/s, and the threshold to 1.09 m/s with it
        assertEquals(0.0, Accuracy.movementPenalty(1.0, 3.2, 0.34), EPS);
        assertTrue(Accuracy.movementPenalty(1.5, 3.2, 0.34) > 0.0);
    }

    @Test
    void unknownMaxSpeedIsThePlainLinearTerm() {
        assertEquals(0.03 * 2.0, Accuracy.movementPenalty(2.0, 0.0, 0.34), EPS);
    }

    @Test
    void postureMultipliesTheWholeCone() {
        double upright = Accuracy.cone(RIFLE, 0.1, 8.0, 8.0, Posture.UPRIGHT, true);
        assertEquals(upright * 0.7, Accuracy.cone(RIFLE, 0.1, 8.0, 8.0, Posture.CROUCH, true), EPS);
        assertEquals(upright * 0.5, Accuracy.cone(RIFLE, 0.1, 8.0, 8.0, Posture.CRAWL, true), EPS);
        assertEquals(upright * 2.0, Accuracy.cone(RIFLE, 0.1, 8.0, 8.0, Posture.AIRBORNE, true), EPS);
        assertEquals(upright * 1.8, Accuracy.cone(RIFLE, 0.1, 8.0, 8.0, Posture.SWIM, true), EPS);
    }

    @Test
    void hipfireOnlyWidensAndOnlyWhenNotAimed() {
        double aimed = Accuracy.cone(SNIPER, 0.0, 0.0, 8.0, Posture.UPRIGHT, true);
        assertEquals(aimed * 8.0, Accuracy.cone(SNIPER, 0.0, 0.0, 8.0, Posture.UPRIGHT, false), EPS);
        assertEquals(Accuracy.cone(RIFLE, 0.0, 0.0, 8.0, Posture.UPRIGHT, true),
                Accuracy.cone(RIFLE, 0.0, 0.0, 8.0, Posture.UPRIGHT, false), EPS);
    }

    @Test
    void theHostFloorIgnoresAirborneAndHipfireAndIsNeverAboveTheLiveCone() {
        assertEquals(0.005, Accuracy.minimum(SNIPER, Posture.AIRBORNE), EPS);
        assertEquals(0.005 * 0.7, Accuracy.minimum(SNIPER, Posture.CROUCH), EPS);
        for (Posture p : Posture.values()) {
            for (boolean aimed : new boolean[] {true, false}) {
                double live = Accuracy.cone(SNIPER, 0.0, 0.0, 8.0, p, aimed);
                assertTrue(Accuracy.minimum(SNIPER, p) <= live + EPS, p + " aimed=" + aimed);
            }
        }
    }

    @Test
    void crosshairIsAFractionOfTheWeaponsOwnWorstCone() {
        double worst = 0.01 + 0.25 + 6.0 * 0.03;
        assertEquals(0.01 / worst, Accuracy.crosshairFraction(RIFLE, Accuracy.cone(RIFLE, 0, 0, 8, Posture.UPRIGHT, true)), EPS);
        assertEquals(1.0, Accuracy.crosshairFraction(RIFLE, 10.0), EPS);
        assertEquals(0.0, Accuracy.crosshairFraction(new Tuning(0, 0, 1, 0, 0.34, 1), 0.0), EPS);
    }

    @Test
    void bloomDecaysAndCaps() {
        assertEquals(0.3, Accuracy.decayBloom(0.6, SNIPER, 0.6), EPS);
        assertEquals(0.0, Accuracy.decayBloom(0.1, SNIPER, 1.0), EPS);
        assertEquals(0.25, Accuracy.bloomAfterShot(0.24, RIFLE), EPS);
    }
}
