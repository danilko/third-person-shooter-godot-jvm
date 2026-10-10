package com.openworld.game.event;

import com.openworld.game.event.GameplayEvents.Phase;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GameplayEventsTest {

    private static final GameplayEvent SHOT =
            new GameplayEvent.WeaponFired(Actor.player("p1", "player"), new Spot(1, 2, 3), "PIS1");

    @BeforeEach
    @AfterEach
    void clean() {
        GameplayEvents.reset();
        GameplayEvents.setErrorLog((s, e) -> { });
    }

    @Test
    void subscribersAreHeardByPhaseNotBySubscriptionOrder() {
        List<String> heard = new ArrayList<>();
        GameplayEvents.subscribe(Phase.OBSERVER, (e, r) -> heard.add("observer"));
        GameplayEvents.subscribe(Phase.GANG, (e, r) -> heard.add("gang"));
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> heard.add("wanted"));
        GameplayEvents.subscribe(Phase.ACTIVITY, (e, r) -> heard.add("activity"));
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> heard.add("wanted2"));
        assertNotNull(GameplayEvents.publish(SHOT));
        assertEquals(List.of("activity", "wanted", "wanted2", "gang", "observer"), heard);
        assertEquals(1, GameplayEvents.publishedCount());
    }

    @Test
    void aSanctionIsSeenByEveryLaterPhase() {
        boolean[] wantedSaw = {false};
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> wantedSaw[0] = r.sanctioned());
        GameplayEvents.subscribe(Phase.ACTIVITY, (e, r) -> r.sanction("arrest_m07"));
        GameplayEvents.Ruling r = GameplayEvents.publish(SHOT);
        assertTrue(wantedSaw[0]);
        assertEquals("arrest_m07", r.sanctionedBy());
        assertFalse(r.vetoed());
    }

    @Test
    void aVetoEndsTheEventAfterItsPhase() {
        List<String> heard = new ArrayList<>();
        GameplayEvents.subscribe(Phase.ACTIVITY, (e, r) -> { heard.add("a1"); r.veto("rule"); });
        GameplayEvents.subscribe(Phase.ACTIVITY, (e, r) -> heard.add("a2"));
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> heard.add("wanted"));
        assertTrue(GameplayEvents.publish(SHOT).vetoed());
        assertEquals(List.of("a1", "a2"), heard);
        assertEquals(1, GameplayEvents.vetoedCount());
    }

    @Test
    void aClientDropsTheEvent() {
        int[] heard = {0};
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> heard[0]++);
        GameplayEvents.setAuthority(() -> false);
        assertNull(GameplayEvents.publish(SHOT));
        assertEquals(0, heard[0]);
        assertEquals(1, GameplayEvents.droppedCount());
        assertEquals(0, GameplayEvents.publishedCount());
    }

    @Test
    void anEventPublishedByASubscriberIsDeliveredAfterTheCurrentOne() {
        List<String> heard = new ArrayList<>();
        GameplayEvent flag = new GameplayEvent.FlagChanged("f", "1");
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> {
            heard.add("wanted:" + e.getClass().getSimpleName());
            if (e == SHOT) assertNull(GameplayEvents.publish(flag));
        });
        GameplayEvents.subscribe(Phase.OBSERVER, (e, r) -> heard.add("observer:" + e.getClass().getSimpleName()));
        GameplayEvents.publish(SHOT);
        assertEquals(List.of("wanted:WeaponFired", "observer:WeaponFired", "wanted:FlagChanged", "observer:FlagChanged"), heard);
    }

    @Test
    void aThrowingSubscriberDoesNotSilenceTheOthers() {
        int[] heard = {0}, errors = {0};
        GameplayEvents.setErrorLog((s, e) -> errors[0]++);
        GameplayEvents.subscribe(Phase.WANTED, (e, r) -> { throw new IllegalStateException("boom"); });
        GameplayEvents.subscribe(Phase.GANG, (e, r) -> heard[0]++);
        GameplayEvents.publish(SHOT);
        GameplayEvents.publish(SHOT);
        assertEquals(2, heard[0]);
        assertEquals(2, errors[0]);
    }

    @Test
    void unsubscribeAndDoubleSubscribe() {
        int[] heard = {0};
        GameplayEvents.Subscriber s = (e, r) -> heard[0]++;
        GameplayEvents.subscribe(Phase.GANG, s);
        GameplayEvents.subscribe(Phase.GANG, s);
        assertEquals(1, GameplayEvents.subscriberCount());
        GameplayEvents.publish(SHOT);
        GameplayEvents.unsubscribe(s);
        GameplayEvents.publish(SHOT);
        assertEquals(1, heard[0]);
    }
}
