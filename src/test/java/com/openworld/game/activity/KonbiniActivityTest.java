package com.openworld.game.activity;

import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.content.Act1;
import com.openworld.game.campaign.content.CampaignModules;
import com.openworld.game.campaign.content.KonbiniActivity;
import com.openworld.game.event.Actor;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.event.Spot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** TIER 1 of the mission test kit (PLAN.md 2.1 / CR6) for the shipped konbini job: its stage graph run against a
 *  fake world with scripted events and a clock, engine-free. */
class KonbiniActivityTest {

    static final String P1 = "p1", P2 = "p2", BOSS = Act1.M01_BOSS, JOB = Act1.M01_KONBINI;

    FakeActivityHost w;
    ActivityDirector d;
    CampaignGraph graph = CampaignModules.graph();
    List<GameplayEvent> outcomes = new ArrayList<>();
    List<ActivityResult> results = new ArrayList<>();

    @BeforeEach
    void world() {
        w = new FakeActivityHost();
        w.player(P1).ownsWorld = true;
        w.player(P1).at = new Spot(0, 0, 0);
        w.player(P2).at = new Spot(2, 0, 0);
        for (String id : List.of(BOSS, "m01_crew_1", "m01_crew_2")) w.character(id).at = new Spot(5, 0, 0);
        w.lockedDoors = 2;
        w.rewards.put(JOB, 20_000L);
        d = new ActivityDirector(graph, w);
        d.setPublisher(outcomes::add);
        d.addListener(new ActivityDirector.Listener() {
            @Override public void ended(ActivityInstance a, List<ActivityResult> r) { results.addAll(r); }
        });
    }

    void walkIn(String player) {
        d.onEvent(new GameplayEvent.ZoneEntered(Actor.player(player, "player"), Spot.NOWHERE, KonbiniActivity.START_ZONE),
                new GameplayEvents.Ruling());
    }

    /** Walk in and take the offer (a second player walking into the running job joins without one). */
    void enterZone(String player) {
        walkIn(player);
        if (w.offers.remove(JOB + "<" + player)) d.accept(JOB, player);
    }

    @Test
    void walkingInOnlyOffersIt() {
        walkIn(P1);
        assertNull(d.runningOf(JOB), "nothing starts by walking in");
        assertEquals(List.of(JOB + "<" + P1), w.offers);
        assertEquals("neutral", w.character(BOSS).faction);
        assertTrue(d.accept(JOB, P1).ok());
        assertEquals(List.of(": Take down Kaneda's crew"), w.said, "the objective is told on entering the stage");
    }

    void kill(String target, String by) {
        w.character(target).alive = false;
        w.character(target).health = 0;
        d.onEvent(new GameplayEvent.Killed(Actor.player(by, "player"), new Actor(target, "gang_a", Actor.Kind.AI, "", target),
                Spot.NOWHERE, false, "PIS1"), new GameplayEvents.Ruling());
    }

    void toSurrender() {
        enterZone(P1);
        kill("m01_crew_1", P1);
        kill("m01_crew_2", P1);
        w.character(BOSS).health = 0.4;
        w.run(d, 0.1);
    }

    @Test
    void walkingIntoTheZoneStartsTheFight() {
        assertEquals("neutral", w.character(BOSS).faction);
        enterZone(P1);
        ActivityInstance a = d.runningOf(JOB);
        assertEquals(KonbiniActivity.FIGHT, a.stageId());
        assertEquals(P1, a.owner());
        for (String id : List.of(BOSS, "m01_crew_1", "m01_crew_2")) assertEquals("gang_a", w.character(id).faction);
        assertEquals(2, a.doorsUnlocked());
        assertEquals(0, w.lockedDoors);
        assertEquals(List.of(new Plan.Relation("player", "gang_a", "HOSTILE")), w.relations.get(a.instanceId()));
        assertEquals(BOSS, w.marks.get(a.instanceId()));
    }

    @Test
    void theBossSurrendersOnlyWithTheCrewDownAndWoundedPastHalf() {
        enterZone(P1);
        w.character(BOSS).health = 0.4;
        w.run(d, 0.5);
        assertEquals(KonbiniActivity.FIGHT, d.runningOf(JOB).stageId(), "the crew is still up");
        kill("m01_crew_1", P1);
        kill("m01_crew_2", P1);
        w.character(BOSS).health = 0.6;
        w.run(d, 0.5);
        assertEquals(KonbiniActivity.FIGHT, d.runningOf(JOB).stageId(), "he is not wounded enough");
        w.character(BOSS).health = 0.4;
        w.run(d, 0.1);
        assertEquals(KonbiniActivity.SURRENDER, d.runningOf(JOB).stageId());
        assertEquals("neutral", w.character(BOSS).faction);
        assertEquals("FLEE", w.character(BOSS).commanded);
    }

    @Test
    void sparedWhenTheTimeRunsOut() {
        toSurrender();
        w.run(d, 14.0);
        assertTrue(d.runningOf(JOB) != null, "not yet");
        w.run(d, 1.5);
        assertNull(d.runningOf(JOB));
        ActivityResult r = results.get(0);
        assertEquals(ActivityInstance.Outcome.COMPLETED, r.outcome());
        assertEquals(Act1.BOSS_SPARED, r.variant());
        assertTrue(r.storyCredit());
        assertFalse(r.worldApplied(), "sparing him changes nothing in the world");
        assertEquals(20_000L, w.player(P1).paid);
        assertEquals("", w.character(BOSS).commanded, "he is given back to his own AI");
        assertTrue(w.player(P1).story.achieved(JOB, Act1.BOSS_SPARED));
        assertEquals("1", w.player(P1).story.flag(Act1.SPARED_THE_BOSS));
        assertTrue(graph.activity(Act1.M02_INFORMANT).requirement().test(w.story(P1)), "the informant branch is open");
        assertEquals(2, w.lockedDoors, "the shop is locked again");
        assertTrue(w.relations.isEmpty(), "the overlay is gone");
        assertEquals(1, w.player(P1).storyCheckpoints);
        assertNull(w.player(P1).checkpoint, "a completed run keeps no checkpoint");
        GameplayEvent.ActivityOutcome o = (GameplayEvent.ActivityOutcome) outcomes.get(0);
        assertEquals("COMPLETED " + Act1.BOSS_SPARED + " STORY", o.outcome() + " " + o.variant() + " " + o.mode());
    }

    @Test
    void sparedWhenHeGetsAway() {
        toSurrender();
        w.character(BOSS).at = new Spot(60, 0, 0);
        w.run(d, 0.1);
        assertEquals(Act1.BOSS_SPARED, results.get(0).variant());
    }

    @Test
    void shootingHimAnywayKillsTheBranch() {
        toSurrender();
        kill(BOSS, P1);
        ActivityResult r = results.get(0);
        assertEquals(Act1.BOSS_KILLED, r.variant());
        assertTrue(r.worldApplied());
        assertTrue(w.world.storyDead(BOSS), "he is dead in the world");
        assertFalse(graph.activity(Act1.M02_INFORMANT).requirement().test(w.story(P1)));
    }

    @Test
    void killedBeforeHeSurrendersIsKilledToo() {
        enterZone(P1);
        kill(BOSS, P1);
        assertEquals(Act1.BOSS_KILLED, results.get(0).variant());
    }

    @Test
    void aBossWhoDiesWithNoEventStillEndsIt() {
        enterZone(P1);
        w.character(BOSS).alive = false;
        w.run(d, 0.1);
        assertEquals(Act1.BOSS_KILLED, results.get(0).variant());
    }

    @Test
    void everyoneDownFailsItAndTheCrewCalmsDown() {
        enterZone(P1);
        w.player(P1).down = true;
        w.run(d, 0.1);
        ActivityResult r = results.get(0);
        assertEquals(ActivityInstance.Outcome.FAILED, r.outcome());
        assertEquals("every player is down", r.reason());
        assertFalse(r.storyCredit());
        assertEquals(0, w.player(P1).paid);
        assertEquals("neutral", w.character(BOSS).faction, "a failed job gives the old faction back");
        assertEquals(2, w.lockedDoors);
        assertFalse(w.player(P1).story.achieved(JOB, ""));
    }

    @Test
    void leavingTheAreaFailsItAndItCanBeRetriedFromTheFight() {
        enterZone(P1);
        w.character(BOSS).present = false;
        w.run(d, 0.1);
        assertEquals("left the area", results.get(0).reason());
        assertEquals(KonbiniActivity.FIGHT, w.player(P1).checkpoint.stageId());
        w.character(BOSS).present = true;
        ActivityDirector.Start s = d.retry(P1);
        assertTrue(s.ok(), s.refusal());
        assertEquals(KonbiniActivity.FIGHT, s.instance().stageId());
        assertEquals("gang_a", w.character(BOSS).faction);
    }

    @Test
    void aSecondPlayerWalkingInJoinsAndIsCreditedInTheirOwnStory() {
        enterZone(P1);
        enterZone(P2);
        ActivityInstance a = d.runningOf(JOB);
        assertEquals(2, a.participants().size());
        assertEquals(1, d.running().size(), "one run, not two");
        w.player(P1).down = true;
        w.run(d, 0.1);
        assertTrue(d.runningOf(JOB) != null, "one participant is still up");
        kill(BOSS, P2);
        assertEquals(2, results.size());
        for (ActivityResult r : results) {
            assertTrue(r.storyCredit(), r.toString());
            assertEquals(20_000L, r.pay());
            assertEquals(r.role() == Activity.Role.OWNER, r.worldApplied());
        }
        assertTrue(w.player(P2).story.achieved(JOB, Act1.BOSS_KILLED));
    }

    @Test
    void aHelperWhoAlreadyDidItIsPaidAndNothingElse() {
        w.player(P2).story.achieve(JOB, Act1.BOSS_SPARED);
        enterZone(P1);
        enterZone(P2);
        kill(BOSS, P1);
        ActivityResult helper = results.stream().filter(r -> r.playerId().equals(P2)).findFirst().orElseThrow();
        assertFalse(helper.storyCredit());
        assertEquals(20_000L, helper.pay());
        assertFalse(w.player(P2).story.achieved(JOB, Act1.BOSS_KILLED), "their own branch is not overwritten");
    }

    @Test
    void itCannotBeStartedTwiceOrAgainAfterCompletion() {
        enterZone(P1);
        assertEquals("already in '" + JOB + "'", d.whyNot(JOB, P1, Activity.Mode.STORY));
        assertEquals("already running", d.whyNot(JOB, P2, Activity.Mode.STORY));
        kill(BOSS, P1);
        assertEquals("already completed", d.whyNot(JOB, P1, Activity.Mode.STORY));
        walkIn(P1);
        assertNull(d.runningOf(JOB), "walking in again starts nothing");
        assertTrue(w.offers.isEmpty(), "and offers nothing");
    }

    @Test
    void aGuestNeedsTheHostsConsentBecauseItCanKillTheBoss() {
        assertEquals("it changes the world: the host has not agreed", d.whyNot(JOB, P2, Activity.Mode.STORY));
        w.consents.add(JOB + "<" + P2);
        assertEquals("", d.whyNot(JOB, P2, Activity.Mode.STORY));
    }

    @Test
    void aReplayChangesNothingAndIsOnlyOfferedWhereTheBossCanStand() {
        assertEquals("not completed yet", d.whyNot(JOB, P1, Activity.Mode.REPLAY));
        enterZone(P1);
        kill(BOSS, P1);
        results.clear();
        String before = w.player(P1).story.key() + w.world.key();
        long paid = w.player(P1).paid;
        assertTrue(d.whyNot(JOB, P1, Activity.Mode.REPLAY).startsWith("cannot be replayed in this world"), "the boss is dead here");
        w.stageable.add(com.openworld.game.campaign.Requirement.storyAlive(BOSS).toString());
        w.character(BOSS).alive = true;
        w.character(BOSS).health = 1;
        w.character("m01_crew_1").alive = w.character("m01_crew_2").alive = true;
        ActivityDirector.Start s = d.start(JOB, P1, Activity.Mode.REPLAY);
        assertTrue(s.ok(), s.refusal());
        assertEquals(1, w.staged.get(s.instance().instanceId()).size(), "the boss is staged for the replay");
        GameplayEvents.Ruling ruling = new GameplayEvents.Ruling();
        d.onEvent(new GameplayEvent.Damaged(Actor.player(P1, "player"), new Actor(BOSS, "gang_a", Actor.Kind.AI, "", BOSS),
                Spot.NOWHERE, 10, false, "PIS1"), ruling);
        assertTrue(ruling.sandboxed(), "what happens to the cast in a replay is sandboxed");
        kill("m01_crew_1", P1);
        kill("m01_crew_2", P1);
        w.character(BOSS).health = 0.3;
        w.run(d, 20);
        ActivityResult r = results.get(0);
        assertEquals(Act1.BOSS_SPARED, r.variant(), "another choice than the original");
        assertFalse(r.storyCredit());
        assertFalse(r.worldApplied());
        assertEquals(before, w.player(P1).story.key() + w.world.key(), "no flag, variant or ledger entry changed");
        assertEquals(paid, w.player(P1).paid, "the konbini job's replay pays nothing");
        assertTrue(w.staged.isEmpty(), "the overlay is undone");
    }

    @Test
    void theShippedActivityClassesLintClean() {
        ActivityLint.Report r = ActivityLint.check(graph);
        assertEquals(List.of(), r.problems());
    }
}
