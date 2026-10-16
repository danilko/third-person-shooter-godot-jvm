package com.openworld.game.event;

import com.openworld.game.GangRules;
import com.openworld.game.WantedRules;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Predicate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CrimeMapTest {

    private static final Actor P = Actor.player("p1", "player");
    private static final Spot AT = new Spot(0, 0, 0);
    private static final Predicate<String> IS_GANG = f -> f.startsWith("gang_");

    @Test
    void aPlayersHitIsACrimeByWhoWasHit() {
        assertEquals("assault", CrimeMap.police(new GameplayEvent.Damaged(P, Actor.ai("c", "civilian"), AT, 10, false, "PIS1")));
        assertEquals("murder", CrimeMap.police(new GameplayEvent.Killed(P, Actor.ai("c", "neutral"), AT, false, "PIS1")));
        assertEquals("assault_police", CrimeMap.police(new GameplayEvent.Damaged(P, Actor.ai("o", "police"), AT, 10, false, "PIS1")));
        assertEquals("kill_police", CrimeMap.police(new GameplayEvent.Killed(P, Actor.ai("o", "police"), AT, true, "PIS1")));
        // an enemy, a gang member, another player: no police crime
        assertEquals("", CrimeMap.police(new GameplayEvent.Killed(P, Actor.ai("e", "enemy"), AT, false, "PIS1")));
        assertEquals("", CrimeMap.police(new GameplayEvent.Killed(P, Actor.ai("g", "gang_a"), AT, false, "PIS1")));
        assertEquals("", CrimeMap.police(new GameplayEvent.Killed(P, Actor.player("p2", "civilian"), AT, false, "PIS1")));
    }

    @Test
    void onlyAPlayersActIsACrime() {
        Actor cop = Actor.ai("o", "police");
        assertEquals("", CrimeMap.police(new GameplayEvent.Killed(cop, Actor.ai("c", "civilian"), AT, false, "PIS1")));
        assertEquals("", CrimeMap.police(new GameplayEvent.WeaponFired(cop, AT, "PIS1")));
        assertEquals("", CrimeMap.police(new GameplayEvent.Killed(Actor.NONE, Actor.ai("c", "civilian"), AT, false, "fall")));
        assertNull(CrimeMap.gang(new GameplayEvent.Killed(cop, Actor.ai("g", "gang_a"), AT, false, "PIS1"), IS_GANG));
    }

    @Test
    void theOtherSeams() {
        assertEquals("gunfire", CrimeMap.police(new GameplayEvent.WeaponFired(P, AT, "PIS1")));
        assertEquals("threaten_clerk", CrimeMap.police(new GameplayEvent.Threatened(P, Actor.ai("k", "civilian"), AT, "")));
        assertEquals("rob_store", CrimeMap.police(new GameplayEvent.Theft(P, AT, "till", 30000, "")));
        assertEquals("", CrimeMap.police(new GameplayEvent.ZoneEntered(P, AT, "beat")));
        assertEquals("trespass", CrimeMap.police(new GameplayEvent.Trespassed(P, AT, "Air Base")));
        assertEquals("", CrimeMap.police(new GameplayEvent.BalanceChanged("", "p", 10, "REWARD")));
    }

    @Test
    void gangCrimes() {
        assertEquals(new CrimeMap.GangCrime("gang_a", "hit_member"),
                CrimeMap.gang(new GameplayEvent.Damaged(P, Actor.ai("g", "gang_a"), AT, 10, false, "PIS1"), IS_GANG));
        assertEquals(new CrimeMap.GangCrime("gang_b", "kill_member"),
                CrimeMap.gang(new GameplayEvent.Killed(P, Actor.ai("g", "gang_b"), AT, false, "PIS1"), IS_GANG));
        assertEquals(new CrimeMap.GangCrime("gang_a", "threaten_clerk"),
                CrimeMap.gang(new GameplayEvent.Threatened(P, Actor.ai("k", "civilian"), AT, "gang_a"), IS_GANG));
        assertEquals(new CrimeMap.GangCrime("gang_a", "rob_gray"),
                CrimeMap.gang(new GameplayEvent.Theft(P, AT, "till", 1, "gang_a"), IS_GANG));
        // an ordinary shop is nobody's: no gang crime
        assertNull(CrimeMap.gang(new GameplayEvent.Theft(P, AT, "till", 1, ""), IS_GANG));
        assertNull(CrimeMap.gang(new GameplayEvent.Damaged(P, Actor.ai("c", "civilian"), AT, 10, false, "PIS1"), IS_GANG));
        assertNull(CrimeMap.gang(new GameplayEvent.WeaponFired(P, AT, "PIS1"), IS_GANG));
    }

    /** Every id the map can return is a ROW of the table it is reported against (a renamed row would go silent). */
    @Test
    void everyMappedCrimeIsARowOfItsTable() throws Exception {
        String dir = "src/main/resources/com/openworld/game/";
        WantedRules w = WantedRules.parse(Files.readString(Path.of(dir + "crimes.json")));
        for (String id : List.of("assault", "murder", "assault_police", "kill_police", "gunfire", "threaten_clerk", "rob_store"))
            assertTrue(w.crimes.containsKey(id), id);
        GangRules g = GangRules.parse(Files.readString(Path.of(dir + "gangs.json")));
        for (String id : List.of("hit_member", "kill_member", "threaten_clerk", "rob_gray"))
            assertTrue(g.crimes.containsKey(id), id);
    }
}
