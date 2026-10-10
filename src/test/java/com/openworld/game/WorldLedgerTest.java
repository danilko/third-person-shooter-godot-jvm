package com.openworld.game;

import com.openworld.game.event.Actor;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.event.Spot;
import com.openworld.util.MiniJson;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WorldLedgerTest {

    private static final Actor BOSS = new Actor("boss_kaito", "gang_a", Actor.Kind.AI, "Kaito", "boss_kaito");
    private static final Actor THUG = new Actor("3f0c", "gang_a", Actor.Kind.AI, "Thug", "");

    @BeforeEach
    @AfterEach
    void clean() {
        GameplayEvents.reset();
        WorldLedger.replace(null);
    }

    @Test
    void flagsChangeOnceAndTellTheStream() {
        List<String> heard = new ArrayList<>();
        GameplayEvents.subscribe(GameplayEvents.Phase.OBSERVER,
                (e, r) -> { if (e instanceof GameplayEvent.FlagChanged f) heard.add(f.flag() + "=" + f.value()); });
        WorldLedger l = WorldLedger.get();
        assertTrue(l.setFlag("bridge_open", true));
        assertFalse(l.setFlag("bridge_open", true));
        assertTrue(l.isSet("bridge_open"));
        assertTrue(l.setFlag("harbour_owner", "gang_b"));
        assertEquals("gang_b", l.flag("harbour_owner", ""));
        assertEquals("none", l.flag("unset", "none"));
        assertTrue(l.clearFlag("bridge_open"));
        assertFalse(l.clearFlag("bridge_open"));
        assertFalse(l.isSet("bridge_open"));
        assertEquals(List.of("bridge_open=1", "harbour_owner=gang_b", "bridge_open="), heard);
        assertEquals(3, l.revision());
    }

    @Test
    void aKilledStoryCharacterStaysDeadAnOrdinaryOneIsNotRecorded() {
        GameplayEvents.subscribe(GameplayEvents.Phase.LEDGER, WorldLedger.SUBSCRIBER);
        Actor p = Actor.player("p1", "player");
        GameplayEvents.publish(new GameplayEvent.Killed(p, THUG, Spot.NOWHERE, false, "PIS1"));
        GameplayEvents.publish(new GameplayEvent.Damaged(p, BOSS, Spot.NOWHERE, 50, false, "PIS1"));
        assertFalse(WorldLedger.get().isDead("boss_kaito"));
        assertTrue(WorldLedger.get().isEmpty());
        GameplayEvents.publish(new GameplayEvent.Killed(p, BOSS, Spot.NOWHERE, true, "PIS1"));
        assertTrue(WorldLedger.get().isDead("boss_kaito"));
        assertEquals(List.of("boss_kaito"), WorldLedger.get().deadStoryCharacters());
        long rev = WorldLedger.get().revision();
        GameplayEvents.publish(new GameplayEvent.Killed(p, BOSS, Spot.NOWHERE, true, "PIS1"));
        assertEquals(rev, WorldLedger.get().revision(), "dead twice is not news");
    }

    /** CR7: a replay is a sandbox -- the boss it spawned dies, the world's ledger does not hear it. */
    @Test
    void aKillInsideASandboxIsNotRecorded() {
        GameplayEvents.subscribe(GameplayEvents.Phase.LEDGER, WorldLedger.SUBSCRIBER);
        GameplayEvents.subscribe(GameplayEvents.Phase.ACTIVITY, (e, r) -> r.sandbox("replay:m05"));
        GameplayEvents.publish(new GameplayEvent.Killed(Actor.player("p1", "player"), BOSS, Spot.NOWHERE, false, "PIS1"));
        assertFalse(WorldLedger.get().isDead("boss_kaito"));
    }

    @Test
    void placeOverrides() {
        WorldLedger l = WorldLedger.get();
        assertNull(l.place("konbini_12"));
        assertEquals("gang_a", l.ownerOf("konbini_12", "gang_a"));
        assertTrue(l.setPlace("konbini_12", "gang_b", ""));
        assertFalse(l.setPlace("konbini_12", "gang_b", ""));
        assertEquals("gang_b", l.ownerOf("konbini_12", "gang_a"));
        assertTrue(l.setPlace("warehouse_3", "", "burnt"));
        assertEquals("gang_a", l.ownerOf("warehouse_3", "gang_a"), "a state-only override keeps the generated owner");
        assertTrue(l.setPlace("konbini_12", "", ""), "both blank = back to as generated");
        assertNull(l.place("konbini_12"));
        assertFalse(l.setPlace("konbini_12", "", ""));
    }

    @Test
    void itSurvivesTheSaveRoundTripThroughJson() {
        WorldLedger l = new WorldLedger();
        l.setFlag("bridge_open", true);
        l.setFlag("harbour_owner", "gang_b");
        l.markDead("boss_kaito");
        l.setPlace("konbini_12", "gang_b", "");
        l.setPlace("warehouse_3", "", "burnt");
        @SuppressWarnings("unchecked")
        Map<String, Object> back = (Map<String, Object>) MiniJson.parse(MiniJson.write(l.toMap()));
        WorldLedger r = WorldLedger.fromMap(back);
        assertEquals(l.toMap(), r.toMap());
        assertTrue(r.isDead("boss_kaito"));
        assertEquals("burnt", r.place("warehouse_3").state());
        assertEquals(0, r.revision(), "a loaded ledger is clean");
    }

    @Test
    void anOldSlotWithNoLedgerOrAGarbledOneReadsAsEmpty() {
        assertTrue(WorldLedger.fromMap(null).isEmpty());
        assertTrue(WorldLedger.fromMap(Map.of("flags", "x", "dead", 3, "places", List.of())).isEmpty());
    }
}
