package com.openworld.game.activity;

import com.openworld.game.campaign.CampaignBuilder;
import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.Effect;
import com.openworld.game.campaign.FlagKey;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.event.Actor;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.event.Spot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The framework itself (PLAN.md 2.1): careers, rules and rulings, checkpoints, concurrency, bad activities. */
class ActivityDirectorTest {

    static final FlagKey GATE_OPEN = FlagKey.bool("gate_open", FlagKey.Scope.WORLD);
    static final Blackboard.Key<Long> LOADED = Blackboard.count("loaded");

    /** An undercover job: a temporary police career, crates counted on the blackboard, a second checkpoint stage. */
    static final class Undercover extends Activity {
        boolean real;
        @Override protected void define(Plan p) {
            p.temporaryCareer("police", real).replayPay(0.25);
            p.rules()
                    .sanction((a, e) -> e instanceof GameplayEvent.WeaponFired && a.isParticipant(e.actor().id()))
                    .veto((a, e) -> e instanceof GameplayEvent.Theft t && "evidence".equals(t.what()))
                    .penalty("strikes", 1, (a, e) -> e instanceof GameplayEvent.Killed k && "civilian".equals(k.target().faction()))
                    .failOn("the shop was robbed", (a, e) -> e instanceof GameplayEvent.Theft t && "till".equals(t.what()));
            p.stage("LOAD").objective("Chief", "Load three crates.")
                    .on(GameplayEvent.ZoneEntered.class, e -> "crate".equals(e.zoneId()), (a, e) -> {
                        a.board().set(LOADED, a.board().get(LOADED) + 1);
                        if (a.board().get(LOADED) >= 3) a.go("DRIVE");
                    });
            p.stage("DRIVE").checkpoint().after(5, a -> a.complete("DELIVERED"));
        }
    }

    /** A heist that keeps the gangs away and holds the stars at two at least (PLAN.md P1e step 5). */
    static final class Heist extends Activity {
        @Override protected void define(Plan p) {
            p.noDispatch("gang_a").wantedAtLeast(2).reserve("police", 3).incident("bank_alarm");
            p.stage("RUN").after(2, a -> a.complete("DONE"));
        }
    }

    static final class Job extends Activity {
        @Override protected void define(Plan p) {
            p.closed();
            p.stage("WORK").after(2, a -> a.complete("DONE"));
        }
    }

    static final class Broken extends Activity {
        final String how;
        Broken(String how) { this.how = how; }
        @Override protected void define(Plan p) {
            Consumer<ActivityInstance> bad = switch (how) {
                case "variant" -> a -> a.complete("NOPE");
                case "stage" -> a -> a.go("NOWHERE");
                default -> a -> a.go("A");
            };
            p.stage("A").enter(how.equals("loop") ? a -> a.go("B") : a -> { }).after(1, bad);
            p.stage("B").enter(a -> a.go("A"));
        }
    }

    FakeActivityHost w;
    ActivityDirector d;
    List<ActivityResult> results = new ArrayList<>();
    boolean real;

    CampaignGraph graph() {
        CampaignBuilder b = new CampaignBuilder();
        b.flag(GATE_OPEN);
        b.activity("undercover").runs(() -> { Undercover u = new Undercover(); u.real = real; return u; })
                .variant("DELIVERED", Effect.set(GATE_OPEN));
        b.activity("heist").runs(Heist::new).variant("DONE");
        b.activity("job").kind(com.openworld.game.campaign.ActivityDef.Kind.JOB).runs(Job::new).variant("DONE");
        b.activity("bad_variant").runs(() -> new Broken("variant")).variant("OK");
        b.activity("bad_stage").runs(() -> new Broken("stage")).variant("OK");
        b.activity("bad_loop").runs(() -> new Broken("loop")).variant("OK");
        b.activity("legacy").variant("OK");
        b.openEnded();
        return b.build();
    }

    @BeforeEach
    void world() {
        w = new FakeActivityHost();
        w.player("host").ownsWorld = true;
        w.player("guest");
        w.rewards.put("undercover", 1000L);
        make();
    }

    void make() {
        d = new ActivityDirector(graph(), w);
        d.setPublisher(e -> { });
        d.addListener(new ActivityDirector.Listener() {
            @Override public void ended(ActivityInstance a, List<ActivityResult> r) { results.addAll(r); }
        });
    }

    GameplayEvents.Ruling send(GameplayEvent e) {
        GameplayEvents.Ruling r = new GameplayEvents.Ruling();
        d.onEvent(e, r);
        return r;
    }

    void crate(String who) { send(new GameplayEvent.ZoneEntered(Actor.player(who, "player"), Spot.NOWHERE, "crate")); }

    static Actor civilian() { return new Actor("c1", "civilian", Actor.Kind.AI, "", ""); }

    @Test
    void theTemporaryCareerIsPushedAndPoppedAndItsStrikesAreScratch() {
        w.player("host").career.base = "none";
        ActivityInstance a = d.start("undercover", "host", Activity.Mode.STORY).instance();
        assertEquals("police", w.player("host").career.effective());
        assertEquals(List.of("Chief: Load three crates."), w.said);
        send(new GameplayEvent.Killed(Actor.player("host", "player"), civilian(), Spot.NOWHERE, false, "PIS1"));
        assertEquals(1, w.player("host").career.effectiveCount("strikes"));
        d.abort(a.instanceId(), "test");
        assertEquals("none", w.player("host").career.effective());
        assertEquals(0, w.player("host").career.record("police", "strikes"), "a TEMP strike is discarded with the override");
        assertEquals(ActivityInstance.Outcome.ABORTED, results.get(0).outcome());
    }

    @Test
    void aRealRoutingLandsOnTheRealRecord() {
        real = true;
        make();
        ActivityInstance a = d.start("undercover", "host", Activity.Mode.STORY).instance();
        send(new GameplayEvent.Killed(Actor.player("host", "player"), civilian(), Spot.NOWHERE, false, "PIS1"));
        d.abort(a.instanceId(), "test");
        assertEquals(1, w.player("host").career.record("police", "strikes"));
    }

    @Test
    void anOutsidersKillIsNoPenaltyForAParticipant() {
        d.start("undercover", "host", Activity.Mode.STORY);
        send(new GameplayEvent.Killed(Actor.player("guest", "player"), civilian(), Spot.NOWHERE, false, "PIS1"));
        assertEquals(0, w.player("host").career.effectiveCount("strikes"));
        assertEquals(0, w.player("guest").career.effectiveCount("strikes"));
    }

    @Test
    void rulesSanctionVetoAndFailOnAnOutsider() {
        d.start("undercover", "host", Activity.Mode.STORY);
        assertTrue(send(new GameplayEvent.WeaponFired(Actor.player("host", "player"), Spot.NOWHERE, "PIS1")).sanctioned());
        assertFalse(send(new GameplayEvent.WeaponFired(Actor.player("guest", "player"), Spot.NOWHERE, "PIS1")).sanctioned(),
                "an outsider's shot is an ordinary crime");
        assertTrue(send(new GameplayEvent.Theft(Actor.player("host", "player"), Spot.NOWHERE, "evidence", 0, "")).vetoed());
        send(new GameplayEvent.Theft(Actor.player("guest", "player"), Spot.NOWHERE, "till", 500, ""));
        assertEquals("the shop was robbed", results.get(0).reason(), "an outsider broke the job");
        assertEquals(ActivityInstance.Outcome.FAILED, results.get(0).outcome());
    }

    @Test
    void theBlackboardCountsAndTheCheckpointCarriesIt() {
        d.start("undercover", "host", Activity.Mode.STORY);
        assertNull(w.player("host").checkpoint, "LOAD is no checkpoint");
        crate("host");
        crate("host");
        assertEquals("LOAD", d.of("host").stageId());
        crate("host");
        assertEquals("DRIVE", d.of("host").stageId());
        ActivityCheckpoint cp = w.player("host").checkpoint;
        assertEquals("DRIVE", cp.stageId());
        assertEquals(3L, ((Number) cp.board().get("loaded")).longValue());
        // through a save file and back
        ActivityCheckpoint back = ActivityCheckpoint.fromMap(cp.toMap());
        assertEquals(cp, back);
        d.failFor("host", "arrested");
        assertEquals("arrested", results.get(0).reason());
        ActivityInstance again = d.retry("host").instance();
        assertEquals("DRIVE", again.stageId());
        assertEquals(3L, again.board().get(LOADED));
        w.run(d, 5.1);
        assertEquals("DELIVERED", results.get(1).variant());
        assertEquals("1", w.world.flag(GATE_OPEN));
        assertNull(w.player("host").checkpoint);
        assertEquals("nothing to retry", d.retry("host").refusal());
    }

    @Test
    void aTimerFiresOncePerStageEntryAndTheClockIsTheStages() {
        d.start("undercover", "host", Activity.Mode.STORY);
        w.run(d, 10);
        assertEquals("LOAD", d.of("host").stageId(), "DRIVE's 5 s has not started");
        crate("host"); crate("host"); crate("host");
        w.run(d, 4.9);
        assertTrue(results.isEmpty());
        w.run(d, 0.2);
        assertEquals(1, results.size());
    }

    @Test
    void severalActivitiesRunAtOnceButAPlayerIsInOne() {
        assertTrue(d.start("undercover", "host", Activity.Mode.STORY).ok());
        w.consents.add("job<guest");
        assertTrue(d.start("job", "guest", Activity.Mode.STORY).ok());
        assertEquals(2, d.running().size());
        assertEquals("already in 'undercover'", d.start("job", "host", Activity.Mode.STORY).refusal());
        assertEquals("it is closed", d.join(d.runningOf("job").instanceId(), "host"));
        w.run(d, 2.1);
        assertEquals(1, d.running().size());
        assertEquals("job", results.get(0).activityId());
        assertTrue(d.start("job", "guest", Activity.Mode.STORY).ok(), "a JOB is repeatable");
    }

    @Test
    void theOwnerLeavingAbortsAHelperLeavingDoesNot() {
        ActivityInstance a = d.start("undercover", "host", Activity.Mode.STORY).instance();
        assertEquals("", d.join(a.instanceId(), "guest"));
        w.player("guest").present = false;
        w.run(d, 0.1);
        assertEquals(1, a.participants().size());
        assertTrue(d.isRunning(a.instanceId()));
        w.player("host").present = false;
        w.run(d, 0.1);
        assertEquals(ActivityInstance.Outcome.ABORTED, results.get(0).outcome());
        assertEquals("the owner left", results.get(0).reason());
        assertTrue(w.player("host").career.overrides().isEmpty(), "the override pops on a disconnect too");
        assertEquals(List.of(a.instanceId()), w.released);
    }

    @Test
    void aReplayPaysItsShareAndNeverTouchesARealRecord() {
        real = true;
        make();
        w.player("host").story.achieve("undercover", "DELIVERED");
        ActivityInstance a = d.start("undercover", "host", Activity.Mode.REPLAY).instance();
        assertFalse(w.player("host").career.overrides().get(0).real(), "a replay's career is TEMP whatever the mission says");
        send(new GameplayEvent.Killed(Actor.player("host", "player"), civilian(), Spot.NOWHERE, false, "PIS1"));
        crate("host"); crate("host"); crate("host");
        w.run(d, 5.1);
        assertEquals(250L, results.get(0).pay());
        assertEquals(0, w.player("host").career.record("police", "strikes"));
        assertEquals("", w.world.flag(GATE_OPEN), "no world effect");
        assertEquals(0, w.player("host").storyCheckpoints);
        assertTrue(a.outcome() == ActivityInstance.Outcome.COMPLETED);
    }

    @Test
    void aBrokenActivityFailsWithItsNameInsteadOfHanging() {
        for (String id : List.of("bad_variant", "bad_stage", "bad_loop")) {
            results.clear();
            ActivityDirector.Start s = d.start(id, "host", Activity.Mode.STORY);
            if (s.ok()) w.run(d, 1.1);
            assertEquals(ActivityInstance.Outcome.FAILED, results.get(0).outcome(), id);
            assertTrue(d.running().isEmpty(), id);
        }
        assertEquals("not authored yet", d.whyNot("legacy", "host", Activity.Mode.STORY));
        assertEquals("no such activity", d.whyNot("ghost", "host", Activity.Mode.STORY));
    }

    @Test
    void theLintNamesAnEmptyStageAndAPersonalReplayWorld() {
        FlagKey mine = FlagKey.bool("mine", FlagKey.Scope.PERSONAL);
        CampaignBuilder b = new CampaignBuilder();
        b.flag(mine);
        b.activity("x").runs(() -> new Activity() {
            @Override protected void define(Plan p) {
                p.startsOnZone("z").replayWorld(Requirement.flag(mine));
                p.stage("EMPTY");
            }
        }).variant("OK");
        b.activity("y").runs(() -> new Activity() {
            @Override protected void define(Plan p) { p.startsOnZone("z"); }
        }).variant("OK");
        b.activity("z").variant("OK");
        ActivityLint.Report r = ActivityLint.check(b.build());
        String all = String.join("\n", r.problems());
        assertTrue(all.contains("stage 'EMPTY' has nothing in it"), all);
        assertTrue(all.contains("which is not WORLD state"), all);
        assertTrue(all.contains("'y' declares no stage"), all);
        assertTrue(all.contains("starts on zone 'z', which already starts 'x'"), all);
        assertTrue(r.notes().stream().anyMatch(n -> n.contains("'z' has no class")), r.notes().toString());
    }

    @Test
    void enforcementHooksGoToTheHostAndAreReleasedAtTheEnd() {
        ActivityInstance a = d.start("heist", "host", Activity.Mode.STORY).instance();
        Plan.Enforcement e = w.enforcement.get(a.instanceId());
        assertTrue(e != null && e.noDispatch.contains("gang_a") && e.wantedAtLeast == 2, "handed to the host as it starts");
        assertEquals(3, e.reserves.get("police"));
        d.abort(a.instanceId(), "test");
        assertNull(w.enforcement.get(a.instanceId()), "released at its end, whatever the end");
    }

    @Test
    void theLintReadsTheHooks() {
        com.openworld.util.DataTable.setSource(com.openworld.util.DataTable.DISK);
        List<String> problems = new ArrayList<>();
        Plan p = new Plan();
        p.wantedAtLeast(4).wantedAtMost(2).squad("gang_a", 3).noDispatch("gang_a").reserve("yakuza", 2).wantedSet(9);
        ActivityLint.enforcement("activity 'x'", p.enforcement(), problems);
        assertTrue(problems.stream().anyMatch(s -> s.contains("both cannot hold")), problems.toString());
        assertTrue(problems.stream().anyMatch(s -> s.contains("both sends 'gang_a' and keeps it")), problems.toString());
        assertTrue(problems.stream().anyMatch(s -> s.contains("'yakuza', which is not a force")), problems.toString());
        assertTrue(problems.stream().anyMatch(s -> s.contains("9 stars")), problems.toString());
        List<String> clean = new ArrayList<>();
        Plan hp = new Plan();
        new Heist().define(hp);
        ActivityLint.enforcement("activity 'y'", hp.enforcement(), clean);
        assertTrue(clean.isEmpty(), clean.toString());
    }
}
