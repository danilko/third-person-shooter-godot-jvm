package com.openworld.ai.light;

import com.openworld.ai.light.LightSim.Agent;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md 2.3 / F8: the light combatant tier's brain, engine-free. */
class LightSimTest {

    /** A flat open plane: the path is the straight line, the ground is y 0. Counts what it is asked. */
    static final class Flat implements LightSim.Ground {
        int paths, snaps;
        @Override public double[] path(double fx, double fy, double fz, double tx, double ty, double tz) {
            paths++;
            return new double[] { fx, 0, fz, tx, 0, tz };
        }
        @Override public double[] snap(double x, double y, double z) { snaps++; return new double[] { x, 0, z }; }
    }

    private static void target(Agent a, double x, double z) { a.hasTarget = true; a.tx = x; a.ty = 0; a.tz = z; }

    private static void run(LightSim s, double seconds) { for (int i = 0; i < (int) Math.round(seconds * 60); i++) s.step(1.0 / 60); }

    private static void noPlayers(LightSim s) { s.setPlayers(new double[0], new double[0], 0); }

    @Test void meleeConvergesOnItsTargetAndSwings() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.MELEE, 30, 0, 0, 100);
        target(a, 0, 0);
        run(s, 0.2);
        assertEquals(LightSim.ADVANCE, a.state);
        run(s, 10);
        assertTrue(LightSim.plan(a.x, a.z, 0, 0) <= s.params.reach + 0.1, "reached " + a.x + "," + a.z);
        assertEquals(LightSim.ATTACK, a.state);
    }

    @Test void runsAtRunSpeedAndZombiesShamble() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent h = s.add(LightSim.MELEE, 100, 0, 0, 100);
        Agent z = s.add(LightSim.MELEE, 100, 0, 50, 100);
        z.style = LightSim.ZOMBIE;
        target(h, 0, 0);
        target(z, 0, 50);
        run(s, 2);
        assertEquals(2 * s.params.runSpeed, 100 - h.x, 0.5);
        assertEquals(2 * s.params.zombieSpeed, 100 - z.x, 0.5);
    }

    @Test void rangedStopsAtTheStandoffAndHolds() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.RANGED, 80, 0, 0, 100);
        target(a, 0, 0);
        run(s, 20);
        assertEquals(s.params.standoff, LightSim.plan(a.x, a.z, 0, 0), 1.2);
        assertEquals(LightSim.HOLD, a.state);
    }

    @Test void rangedGoesToItsHoldPointNotTheStandoff() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.RANGED, 80, 0, 0, 100);
        a.hasHold = true; a.holdX = 50; a.holdZ = 10; a.leash = 5;
        target(a, 0, 0);
        run(s, 20);
        assertTrue(LightSim.plan(a.x, a.z, 50, 10) <= 1.1, "at " + a.x + "," + a.z);
        assertEquals(LightSim.HOLD, a.state);
    }

    @Test void meleeChaseIsLeashedToItsHoldPoint() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.MELEE, 40, 0, 0, 100);
        a.hasHold = true; a.holdX = 40; a.holdZ = 0; a.leash = 8;
        target(a, 0, 0);
        run(s, 15);
        assertTrue(LightSim.plan(a.x, a.z, 40, 0) <= 8.6, "left the leash: " + a.x);
    }

    @Test void aHordeKeepsApart() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        for (int i = 0; i < 40; i++) {
            Agent a = s.add(LightSim.MELEE, 40 + (i % 8), 0, (i / 8) * 1.0, 100);
            a.refused = 1e9;                 // nobody may be promoted: they all hold back on the ring
            target(a, 0, 0);
        }
        run(s, 25);
        double closest = Double.MAX_VALUE;
        for (Agent a : s.agents()) for (Agent b : s.agents())
            if (a != b) closest = Math.min(closest, LightSim.plan(a.x, a.z, b.x, b.z));
        assertTrue(closest >= s.params.separation * 0.5, "two bodies " + closest + " m apart");
        for (Agent a : s.agents()) {
            double d = LightSim.plan(a.x, a.z, 0, 0);
            assertTrue(d >= s.params.holdBackRing - 1.0, "a refused body came to " + d + " m (ring " + s.params.holdBackRing + ")");
            assertNotEquals(LightSim.ATTACK, a.state);
        }
    }

    @Test void promotionIsWantedInsideTheRingAndAfterARefusalWaits() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        s.setPlayers(new double[] { 0 }, new double[] { 0 }, 1);
        Agent a = s.add(LightSim.MELEE, 30, 0, 0, 100);
        target(a, 0, 0);
        run(s, 1);
        assertFalse(a.wantsPromotion, "30 m away");
        run(s, 5);
        assertTrue(a.wantsPromotion, "inside 15 m at " + a.x);
        s.refused(a);
        run(s, 0.1);
        assertFalse(a.wantsPromotion);
        run(s, s.params.refusedSeconds + 0.2);
        assertTrue(a.wantsPromotion);
        s.promoted(a);
        run(s, 1);
        assertEquals(LightSim.PROMOTED, a.state);
        assertFalse(a.wantsPromotion);
    }

    @Test void aRangedShooterWithALineWantsAFullBody() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        s.setPlayers(new double[] { 0 }, new double[] { 0 }, 1);
        Agent a = s.add(LightSim.RANGED, 60, 0, 0, 100);
        target(a, 0, 0);
        run(s, 15);
        assertEquals(LightSim.HOLD, a.state);
        assertFalse(a.wantsPromotion, "no line of sight yet");
        a.lineOfSight = true;
        run(s, 0.2);
        assertTrue(a.wantsPromotion);
    }

    @Test void aLethalHitKillsInTheTierAndTheCorpseGoes() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.MELEE, 30, 0, 0, 100);
        assertFalse(s.hit(a, 40));
        assertEquals(60, a.hp, 1e-9);
        assertTrue(s.hit(a, 80));
        assertEquals(LightSim.DEAD, a.state);
        assertFalse(s.hit(a, 10), "a corpse is not hit again");
        run(s, s.params.corpseSeconds + 0.5);
        assertEquals(LightSim.GONE, a.state);
        s.sweep();
        assertTrue(s.agents().isEmpty());
    }

    @Test void demotionCarriesHitPointsAndPlace() {
        LightSim s = new LightSim(new LightSim.Params(), new Flat());
        noPlayers(s);
        Agent a = s.add(LightSim.MELEE, 30, 0, 0, 100);
        s.promoted(a);
        s.demote(a, 5, 0, 7, 35);
        assertEquals(LightSim.IDLE, a.state);
        assertEquals(35, a.hp, 1e-9);
        assertEquals(5, a.x, 1e-9);
        s.lost(a);
        assertEquals(LightSim.GONE, a.state);
    }

    @Test void pathRequestsAreBudgetedPerTick() {
        Flat f = new Flat();
        LightSim.Params p = new LightSim.Params();
        LightSim s = new LightSim(p, f);
        noPlayers(s);
        for (int i = 0; i < 80; i++) target(s.add(LightSim.MELEE, 50 + i, 0, 0, 100), 0, 0);
        for (int t = 0; t < 30; t++) {
            int before = f.paths;
            s.step(1.0 / 60);
            assertTrue(f.paths - before <= p.pathsPerTick, "tick " + t + " asked " + (f.paths - before));
        }
        // and nobody starves: in 30 ticks x 4 = 120 requests every one of the 80 got a path
        for (Agent a : s.agents()) assertNotNull(a.path, "body " + a.id + " never got a path");
    }

    @Test void thinkGroupsSpreadTheDecisionsAcrossTicks() {
        LightSim.Params p = new LightSim.Params();
        p.thinkGroups = 4;
        LightSim s = new LightSim(p, new Flat());
        noPlayers(s);
        for (int i = 0; i < 80; i++) target(s.add(LightSim.MELEE, 50 + i, 0, 0, 100), 0, 0);
        s.step(1.0 / 60);                    // first tick: everyone thinks once
        long first = s.thinks;
        for (int t = 0; t < 40; t++) s.step(1.0 / 60);
        assertEquals(80, first);
        assertEquals(80 * 40 / 4, s.thinks - first, 2, "a quarter of the tier a tick");
        // and the control: one group = everyone every tick
        LightSim.Params q = new LightSim.Params();
        q.thinkGroups = 1;
        LightSim c = new LightSim(q, new Flat());
        noPlayers(c);
        for (int i = 0; i < 80; i++) target(c.add(LightSim.MELEE, 50 + i, 0, 0, 100), 0, 0);
        for (int t = 0; t < 41; t++) c.step(1.0 / 60);
        assertEquals(80 * 41, c.thinks);
    }

    @Test void groundSnapsAreRareAndOnlyForPushedBodies() {
        Flat f = new Flat();
        LightSim s = new LightSim(new LightSim.Params(), f);
        noPlayers(s);
        // spread apart: nobody is pushed, so nobody is snapped (their path corners are on the ground already)
        for (int i = 0; i < 40; i++) target(s.add(LightSim.MELEE, 50 + i * 3, 0, 0, 100), 0, 300);
        for (int t = 0; t < 60; t++) s.step(1.0 / 60);
        assertEquals(0, f.snaps, "spread-out bodies were snapped");
        // a packed crowd is pushed apart: snaps happen, never more than snapsPerTick a tick
        LightSim p = new LightSim(new LightSim.Params(), f);
        noPlayers(p);
        for (int i = 0; i < 40; i++) target(p.add(LightSim.MELEE, 50 + (i % 5) * 0.1, 0, (i / 5) * 0.1, 100), 0, 0);
        for (int t = 0; t < 60; t++) {
            int before = f.snaps;
            p.step(1.0 / 60);
            assertTrue(f.snaps - before <= p.params.snapsPerTick, "tick " + t + " snapped " + (f.snaps - before));
        }
        assertTrue(f.snaps > 0, "a packed crowd was never snapped");
    }
}
