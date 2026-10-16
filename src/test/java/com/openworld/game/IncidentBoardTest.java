package com.openworld.game;

import com.openworld.util.DataReader;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md P1e steps 4-7: acts merge into incidents by area and time; new ones are rate-limited; they expire. */
class IncidentBoardTest {

    @Test
    void aFirefightIsOneIncident() {
        IncidentBoard b = new IncidentBoard(60, 45, 6);
        IncidentBoard.Raised first = b.raise("gang_attack", 0, 0, "gang_a", "gang_b", "", 0);
        assertTrue(first.isNew());
        IncidentBoard.Raised again = b.raise("gang_attack", 20, 10, "gang_a", "gang_b", "", 3);
        assertFalse(again.isNew(), "another shot 22 m away is the same incident");
        assertSame(first.incident(), again.incident());
        assertEquals(2, first.incident().acts);
        assertTrue(b.raise("gang_attack", 500, 0, "gang_a", "gang_b", "", 4).isNew(), "far away: another incident");
        assertTrue(b.raise("gang_attack", 0, 0, "gang_b", "gang_a", "", 5).isNew(), "the other gang hit back: its own");
    }

    @Test
    void itEndsAfterItsLastActAndCanBeEndedBySource() {
        IncidentBoard b = new IncidentBoard(60, 45, 6);
        IncidentBoard.Incident i = b.raise("shots_fired", 0, 0, "", "", "", 0).incident();
        b.raise("shots_fired", 5, 0, "", "", "", 30);
        assertTrue(b.isLive(i, 70), "45 s after its LAST act, not its first");
        assertFalse(b.isLive(i, 80));
        b.raise("bank_alarm", 0, 0, "", "", "heist@1", 100);
        b.end("heist@1");
        assertTrue(b.live(100).isEmpty());
    }

    @Test
    void newIncidentsAreRateLimited() {
        IncidentBoard b = new IncidentBoard(10, 45, 3);
        for (int k = 0; k < 3; k++) assertNotNull(b.raise("gang_attack", k * 100, 0, "gang_a", "gang_b", "", k));
        assertNull(b.raise("gang_attack", 900, 0, "gang_a", "gang_b", "", 5), "a fourth within the minute is refused");
        assertEquals(1, b.refusedCount());
        assertNotNull(b.raise("gang_attack", 1000, 0, "gang_a", "gang_b", "", 70), "a minute later there is room again");
    }

    @Test
    void theDataNamesWhoAnswers() throws Exception {
        IncidentBoard.Rules r = IncidentBoard.Rules.read(DataReader.of(
                Files.readString(Path.of("src/main/resources/com/openworld/game/forces.json"))).child("incidents"));
        assertEquals("victim", r.responders().get("gang_attack").force(), "a gang answers any attack on its members");
        assertEquals("police", r.responders().get("civilian_attacked").force());
        assertTrue(r.nearPlayers() > 0);
    }
}
