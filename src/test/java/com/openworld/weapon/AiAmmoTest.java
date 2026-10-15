package com.openworld.weapon;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md P1e step 1: the dropped-AI-firearm reserve roll and the shared, per-AREA explosive cooldown. */
class AiAmmoTest {

    @AfterEach
    void clear() { ExplosiveCooldown.reset(); ExplosiveCooldown.enabled = true; }

    @Test
    void aDroppedAiFirearmKeepsNoneOrWholeSpareMagazines() {
        assertEquals(0, AiAmmoRule.dropReserve(30, 1, 0.0));
        assertEquals(0, AiAmmoRule.dropReserve(30, 1, 0.49));
        assertEquals(30, AiAmmoRule.dropReserve(30, 1, 0.5));
        assertEquals(30, AiAmmoRule.dropReserve(30, 1, 1.0), "a roll of 1 is still the last bucket");
        assertEquals(60, AiAmmoRule.dropReserve(30, 2, 0.99));
        assertEquals(0, AiAmmoRule.dropReserve(30, 0, 0.99), "no spare magazines in the data: the magazine only");
        assertEquals(0, AiAmmoRule.dropReserve(0, 1, 0.99));
    }

    @Test
    void oneExplosiveCoolsItsAreaNotTheWorld() {
        ExplosiveCooldown.configure(6.0, 80.0);
        assertTrue(ExplosiveCooldown.ready(10, 10, 0));
        ExplosiveCooldown.mark(10, 10, 0);
        assertFalse(ExplosiveCooldown.ready(15, 12, 1.0), "the same spot is cooling");
        assertFalse(ExplosiveCooldown.ready(-60, 70, 1.0), "a shooter across the cell line is held too");
        assertTrue(ExplosiveCooldown.ready(400, 400, 1.0), "another incident far away is not");
        assertTrue(ExplosiveCooldown.ready(15, 12, 6.0), "the cooldown ends");
    }

    @Test
    void twoPlayersTogetherDrawOneRocketAtATime() {
        ExplosiveCooldown.configure(6.0, 80.0);
        // two shooters, each answering a different player standing 5 m apart: one area, one rocket
        assertTrue(ExplosiveCooldown.ready(100, 100, 0));
        ExplosiveCooldown.mark(100, 100, 0);
        assertFalse(ExplosiveCooldown.ready(104, 101, 0.5));
    }

    @Test
    void offIsTheControl() {
        ExplosiveCooldown.configure(6.0, 80.0);
        ExplosiveCooldown.enabled = false;
        ExplosiveCooldown.mark(0, 0, 0);
        assertTrue(ExplosiveCooldown.ready(0, 0, 0.1));
    }
}
