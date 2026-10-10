package com.openworld.game;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class RecoveryRulesTest {

    private static RecoveryRules rules() throws Exception {
        String dir = "src/main/resources/com/openworld/game/";
        return RecoveryRules.parse(Files.readString(Path.of(dir + "crimes.json")), Files.readString(Path.of(dir + "gangs.json")));
    }

    @Test
    void aGangOutranksThePoliceAndThePoliceOutrankTheHospital() {
        assertEquals(RecoveryRules.Outcome.ABDUCTED, RecoveryRules.onDown(1, 4));
        assertEquals(RecoveryRules.Outcome.ARRESTED, RecoveryRules.onDown(0, 1), "a death while wanted is jail");
        assertEquals(RecoveryRules.Outcome.HOSPITALIZED, RecoveryRules.onDown(0, 0));
    }

    @Test
    void theBillsClimbHospitalThenArrestThenRansom() throws Exception {
        RecoveryRules r = rules();
        int h = r.fee(RecoveryRules.Outcome.HOSPITALIZED, 0);
        int a1 = r.fee(RecoveryRules.Outcome.ARRESTED, 1), a5 = r.fee(RecoveryRules.Outcome.ARRESTED, 5);
        assertTrue(h > 0);
        assertEquals((r.hospital + r.policePerStar) * 5, a5, "the arrest bill is per star");
        assertTrue(a1 > h);
        assertTrue(r.ransom(1) > a5, "the cheapest ransom is dearer than the worst arrest");
        assertTrue(r.ransom(5) > r.ransom(1));
        assertEquals(0, r.fee(RecoveryRules.Outcome.ABDUCTED, 3), "a ransom is the price of leaving, not of waking");
    }
}
