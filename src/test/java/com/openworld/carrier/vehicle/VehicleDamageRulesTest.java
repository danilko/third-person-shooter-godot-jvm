package com.openworld.carrier.vehicle;

import org.junit.jupiter.api.Test;

import static com.openworld.carrier.vehicle.VehicleDamageRules.*;
import static org.junit.jupiter.api.Assertions.*;

/** The GTA-style component damage rules (VehicleDamageModel). */
class VehicleDamageRulesTest {

    @Test
    void partsAreKnownByTheirExportedNames() {
        assertEquals(Kind.DOOR, kindOf("door_lf"));
        assertEquals(Kind.BUMPER, kindOf("bump_rear"));
        assertEquals(Kind.WHEEL, kindOf("wheel_rb"));
        assertEquals(Kind.UNKNOWN, kindOf("door.003"));      // an unsplit source object is not a part
        assertEquals(4, slotOf("door_lf"));
        assertEquals(-1, slotOf("chassis"));                  // the chassis never changes state
        assertTrue(SLOTS.length <= 16);
    }

    @Test
    void aPanelWalksOkDentedLooseOff() {
        assertEquals(OK, stateFor(Kind.DOOR, 0));
        assertEquals(DENTED, stateFor(Kind.DOOR, DENT_AT));
        assertEquals(LOOSE, stateFor(Kind.DOOR, LOOSE_AT));
        assertEquals(OFF, stateFor(Kind.DOOR, OFF_AT));
        // a wing only dents; a windscreen cracks then shatters, never hangs loose
        assertEquals(DENTED, stateFor(Kind.WING, 10_000));
        assertEquals(DENTED, stateFor(Kind.WINDSCREEN, (DENT_AT + GLASS_OFF_AT) / 2));
        assertEquals(OFF, stateFor(Kind.WINDSCREEN, GLASS_OFF_AT));
        // a replicated state maps back onto the points that produce it
        for (int s = OK; s <= OFF; s++) assertEquals(s, stateFor(Kind.BONNET, damageFor(Kind.BONNET, s)));
    }

    @Test
    void theDentGrowsAndCaps() {
        assertEquals(0.0, dentWeight(0), 1e-9);
        assertTrue(dentWeight(DENT_AT) > 0.2);
        assertTrue(dentWeight(DENT_AT) < dentWeight(LOOSE_AT * 0.8));
        assertEquals(1.0, dentWeight(LOOSE_AT), 1e-9);
        assertEquals(1.0, dentWeight(OFF_AT * 3), 1e-9);
        assertEquals(0.0, chassisWeight(1.0), 1e-9);
        assertEquals(1.0, chassisWeight(0.0), 1e-9);
    }

    @Test
    void masksMergeByTheMostBrokenReport() {
        int host = withState(0, slotOf("door_lf"), LOOSE);        // shot loose on the host
        int driver = withState(0, slotOf("door_lf"), DENTED);    // only dented where the car is driven…
        driver = withState(driver, slotOf("bump_front"), OFF);    // …which also crashed the bumper off
        int m = merge(host, driver);
        assertEquals(LOOSE, stateAt(m, slotOf("door_lf")));
        assertEquals(OFF, stateAt(m, slotOf("bump_front")));
        assertEquals(OK, stateAt(m, slotOf("boot")));
        assertEquals(m, merge(m, host));                          // idempotent: re-applying changes nothing
        assertEquals(m, merge(driver, host));                     // order-free
    }

    @Test
    void anImpactDamagesWhatItHits() {
        assertEquals(0.0, impactPoints(MIN_IMPACT_DV), 1e-9);    // a scrape
        assertTrue(impactPoints(12) > OFF_AT);                    // a 12 m/s crash takes a part clean off
        double[] min = {-1, 0.2, -2.3}, max = {1, 0.7, -1.6};     // a front bumper
        assertEquals(1.0, share(min, max, new double[]{0, 0.5, -2.0}), 1e-9);
        assertEquals(0.0, share(min, max, new double[]{0, 0.5, 1.0}), 1e-9);  // the other end of the car
        double s = share(min, max, new double[]{0, 0.5, -1.2});   // 0.4 m behind it
        assertTrue(s > 0.4 && s < 0.7);
    }

    @Test
    void positiveHingeAnglesOpenEachPartTheRightWay() {
        // left door: hinge at the front edge, the door runs back (+Z); open = its rear edge swings out to -X
        double[] lever = {0, 0, 0.6};
        double[] axis = openAxis(Kind.DOOR, lever, -0.9);
        double[] swing = cross(axis, lever);
        assertTrue(swing[0] < 0);
        // right door mirrors it
        assertTrue(cross(openAxis(Kind.DOOR, lever, 0.9), lever)[0] > 0);
        // bonnet: hinge at the rear edge, runs forward (-Z); open = front edge lifts
        double[] bl = {0, 0, -0.6};
        assertTrue(cross(openAxis(Kind.BONNET, bl, 0), bl)[1] > 0);
        // boot: hinge at the front edge, runs back; open = rear edge lifts
        double[] kl = {0, 0, 0.25};
        assertTrue(cross(openAxis(Kind.BOOT, kl, 0), kl)[1] > 0);
        // bumper: hangs from one end; open = the free end drops
        double[] ul = {-0.9, 0, 0};
        assertTrue(cross(openAxis(Kind.BUMPER, ul, 0), ul)[1] < 0);
        assertNull(openAxis(Kind.WING, lever, 1));
    }

    @Test
    void gravityHangsABumperAndShutsABonnet() {
        double[] g = {0, -9.8, 0};
        double[] ul = {-0.9, 0, 0};
        assertTrue(hingeAccel(openAxis(Kind.BUMPER, ul, 0), ul, g) > 0);
        double[] bl = {0, 0, -0.6};
        assertTrue(hingeAccel(openAxis(Kind.BONNET, bl, 0), bl, g) < 0);
        // braking hard (the car decelerates: specific force points FORWARD, -Z) swings a door on a front hinge shut,
        // accelerating swings it open
        double[] dl = {0, 0, 0.6};
        double[] axis = openAxis(Kind.DOOR, dl, -0.9);
        assertEquals(0.0, hingeAccel(axis, dl, new double[]{0, 0, -8}), 1e-9);   // along the lever: no torque
        assertTrue(hingeAccel(axis, dl, new double[]{-6, 0, 0}) > 0);             // turning right flings the left door out
    }

    @Test
    void aHingeStaysBetweenItsStopsAndBounces() {
        double[] s = stepHinge(0.0, -3.0, 0.0, 0.0, 1.0, 0.3, 0.1);
        assertEquals(0.0, s[0], 1e-9);
        assertEquals(0.9, s[1], 1e-9);            // slammed shut, bounced at 30 %
        s = stepHinge(0.95, 5.0, 0.0, 0.0, 1.0, 0.2, 0.1);
        assertEquals(1.0, s[0], 1e-9);
        assertTrue(s[1] < 0);
        double a = 0.5, v = 0;                    // damped: settles
        for (int i = 0; i < 600; i++) { double[] r = stepHinge(a, v, 0.0, 4.0, 1.2, 0.3, 1 / 60.0); a = r[0]; v = r[1]; }
        assertEquals(0.0, v, 1e-3);
    }
}
