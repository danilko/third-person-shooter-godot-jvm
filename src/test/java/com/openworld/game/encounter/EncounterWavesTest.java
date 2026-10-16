package com.openworld.game.encounter;

import com.openworld.game.encounter.EncounterWaves.State;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md 2.2 / F6: an encounter's waves, trigger, clear and reset; and loadouts.json's picks. */
class EncounterWavesTest {

    /** Records what the encounter asked for; {@code room} bounds what a wave may stand up (the cap). */
    static final class Rec implements EncounterWaves.Out {
        final List<String> log = new ArrayList<>();
        int alive, room = 99;
        @Override public int spawnWave(int index, int count) {
            int n = Math.min(count, room);
            if (n > 0) { alive += n; log.add("wave" + index + ":" + n); }
            return n;
        }
        @Override public void engage() { log.add("engage"); }
        @Override public void releaseAll() { alive = 0; log.add("release"); }
        @Override public void cleared() { log.add("cleared"); }
    }

    private static EncounterWaves.Config cfg(boolean manual, boolean once) {
        return new EncounterWaves.Config(new int[] {4, 3}, 25, 90, 150, 1, 2.0, manual, once);
    }

    private static void step(EncounterWaves w, Rec r, double nearest, boolean provoked) { w.step(0.5, nearest, r.alive, provoked, r); }

    @Test
    void standsUpNearThenTurnsOnThePlayerInsideTheTrigger() {
        EncounterWaves w = new EncounterWaves(cfg(false, true));
        Rec r = new Rec();
        step(w, r, 200, false);
        assertEquals(State.DORMANT, w.state(), "nobody near: nothing stands up");
        step(w, r, 80, false);
        assertEquals(State.STANDING, w.state());
        assertEquals(List.of("wave0:4"), r.log);
        step(w, r, 40, false);
        assertEquals(State.STANDING, w.state(), "near but outside the trigger: still calm");
        step(w, r, 20, false);
        assertEquals(State.ENGAGED, w.state());
        assertEquals(List.of("wave0:4", "engage"), r.log);
    }

    @Test
    void aHurtMemberEngagesFromAnywhere() {
        EncounterWaves w = new EncounterWaves(cfg(false, true));
        Rec r = new Rec();
        step(w, r, 80, false);
        step(w, r, 80, true);
        assertEquals(State.ENGAGED, w.state(), "a sniper's shot from outside the trigger starts it");
    }

    @Test
    void theNextWaveWaitsForTheFirstToThinAndForTheGap() {
        EncounterWaves w = new EncounterWaves(cfg(false, true));
        Rec r = new Rec();
        step(w, r, 80, false);
        step(w, r, 20, false);
        r.alive = 1;
        step(w, r, 20, false);   // 0.5 s since the first wave: the gap holds it
        assertFalse(r.log.contains("wave1:3"));
        r.alive = 2;
        for (int i = 0; i < 6; i++) step(w, r, 20, false);
        assertFalse(r.log.contains("wave1:3"), "two still up (> nextWaveAt 1): no second wave");
        r.alive = 1;
        step(w, r, 20, false);
        assertTrue(r.log.contains("wave1:3"));
        assertEquals(0, w.wavesLeft());
        r.alive = 0;
        step(w, r, 20, false);
        assertEquals(State.CLEARED, w.state());
        assertEquals("cleared", r.log.get(r.log.size() - 1));
        step(w, r, 400, false);
        assertEquals(State.CLEARED, w.state(), "once: a cleared encounter stays cleared");
    }

    @Test
    void everyoneLeavingTakesTheLivingAwayAndItCanHappenAgain() {
        EncounterWaves w = new EncounterWaves(cfg(false, true));
        Rec r = new Rec();
        step(w, r, 80, false);
        step(w, r, 20, false);
        step(w, r, 160, false);
        assertEquals(State.DORMANT, w.state());
        assertEquals("release", r.log.get(r.log.size() - 1));
        step(w, r, 80, false);
        assertEquals(State.STANDING, w.state());
        assertEquals(2, w.wavesLeft() + 1, "the waves start over");
    }

    @Test
    void notOnceComesBackAfterEveryoneLeft() {
        EncounterWaves w = new EncounterWaves(new EncounterWaves.Config(new int[] {2}, 25, 90, 150, 0, 0, false, false));
        Rec r = new Rec();
        step(w, r, 80, false);
        step(w, r, 20, false);
        r.alive = 0;
        step(w, r, 20, false);
        assertEquals(State.CLEARED, w.state());
        step(w, r, 200, false);
        assertEquals(State.DORMANT, w.state());
    }

    @Test
    void aManualEncounterWaitsForStartThenEngagesAtOnce() {
        EncounterWaves w = new EncounterWaves(cfg(true, true));
        Rec r = new Rec();
        step(w, r, 10, false);
        assertEquals(State.DORMANT, w.state(), "manual: a player standing in it does nothing");
        w.start();
        step(w, r, 300, false);
        assertEquals(State.ENGAGED, w.state(), "started far from everyone is still started");
        assertEquals(List.of("wave0:4", "engage"), r.log);
        step(w, r, 300, false);
        assertEquals(State.ENGAGED, w.state(), "a started encounter is not reset by distance");
        w.stop(r);
        assertEquals(State.DORMANT, w.state());
        assertEquals(0, r.alive);
    }

    @Test
    void aFullCapHoldsTheWaveUntilThereIsRoom() {
        EncounterWaves w = new EncounterWaves(cfg(false, true));
        Rec r = new Rec();
        r.room = 0;
        step(w, r, 80, false);
        assertEquals(State.DORMANT, w.state(), "no room: nothing stood up, tried again");
        r.room = 99;
        step(w, r, 80, false);
        assertEquals(State.STANDING, w.state());
    }

    @Test
    void wavesParse() {
        assertArrayEquals(new int[] {4, 3, 0}, EncounterWaves.parseWaves("4, 3,x"));
        assertArrayEquals(new int[0], EncounterWaves.parseWaves(""));
    }

    @Test
    void loadoutsPickByWeightAndTheRollIsStable() throws Exception {
        Loadouts lo = Loadouts.parse(Files.readString(Path.of("src/main/resources/com/openworld/character/loadouts.json")));
        Loadouts.Loadout p = lo.forTeam("police");
        assertEquals("police", p.side());
        assertEquals("PIS1", p.weapon(0.0));
        assertEquals("ASR2", p.weapon(0.99));
        assertEquals(List.of("BAT1"), p.extra());
        assertEquals("gang_b", lo.get("gang_member").sideOr("gang_b"), "an empty side is the caller's faction");
        assertEquals(Loadouts.roll("Markers/MARK_spawn_03"), Loadouts.roll("Markers/MARK_spawn_03"));
        double a = Loadouts.roll("a"), b = Loadouts.roll("b");
        assertTrue(a >= 0 && a < 1 && b >= 0 && b < 1 && a != b);
        // keys that differ only in their last character spread over the range (one crew, several weapons)
        double min = 1, max = 0;
        for (int i = 0; i < 8; i++) {
            double r = Loadouts.roll("/root/World/Encounter#" + i);
            min = Math.min(min, r);
            max = Math.max(max, r);
        }
        assertTrue(max - min > 0.4, "8 sequential keys span " + (max - min));
        // the control: a team naming a loadout that does not exist is a problem, not a silent null
        var d = com.openworld.util.DataReader.of("{\"loadouts\": {}, \"teams\": {\"police\": \"nope\"}}");
        Loadouts.read(d);
        assertEquals(1, d.finish().size(), d.finish().toString());
    }
}
