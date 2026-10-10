package com.openworld.game.campaign;

import com.openworld.game.WorldLedger;
import com.openworld.game.campaign.content.Act1;
import com.openworld.game.campaign.content.CampaignModules;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.profile.PlayerProfile;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static com.openworld.game.campaign.Requirement.achieved;
import static com.openworld.game.campaign.Requirement.all;
import static com.openworld.game.campaign.Requirement.flag;
import static com.openworld.game.campaign.Requirement.not;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CampaignGraphTest {

    static final FlagKey TRUST = FlagKey.bool("trust", FlagKey.Scope.PERSONAL);
    static final FlagKey BRIDGE = FlagKey.bool("bridge_open", FlagKey.Scope.WORLD);
    static final FlagKey SIDE = FlagKey.choice("side", FlagKey.Scope.PERSONAL, "police", "gang");

    /** a -> (b | c, exclusive by the side chosen in a) -> finale; a sticky side job; a repeatable job. */
    static CampaignGraph sample(boolean withDeadEnd) {
        CampaignBuilder b = new CampaignBuilder();
        b.flag(TRUST);
        b.flag(BRIDGE);
        b.flag(SIDE);
        b.ending("clean");
        b.ending("dirty");
        b.activity("a").variant("POLICE", Effect.set(SIDE, "police")).variant("GANG", Effect.set(SIDE, "gang"));
        b.activity("b").requires(flag(SIDE, "police")).variant("DONE", Effect.set(TRUST), Effect.set(BRIDGE));
        b.activity("c").requires(flag(SIDE, "gang")).variant("DONE", Effect.storyDead("chief"));
        ActivityDef f = b.activity("finale").requires(Requirement.any(achieved("b"), achieved("c")))
                .variant("CLEAN", Effect.ending("clean"));
        if (!withDeadEnd) f.variant("DIRTY", Effect.ending("dirty"));
        else b.activity("trap").requires(all(achieved("c"), not(achieved("finale"))))
                .variant("DIRTY", Effect.ending("dirty"), Effect.set(TRUST))
                .variant("STUCK", Effect.set(SIDE, ""));
        if (withDeadEnd) f.requires(all(Requirement.any(achieved("b"), achieved("c")), flag(SIDE)));
        b.activity("odd_job").kind(ActivityDef.Kind.JOB).variant("PAID");
        b.activity("old_friend").sticky().requires(all(flag(SIDE, "police"), not(flag(TRUST)))).variant("MET");
        return b.build();
    }

    @BeforeEach
    void clean() {
        GameplayEvents.reset();
        WorldLedger.replace(null);
    }

    @Test
    void unlocksAreDerivedAndABranchCloses() {
        CampaignGraph g = sample(false);
        SimCampaign s = new SimCampaign();
        assertEquals(List.of("a", "odd_job"), ids(g.available(s)));
        assertTrue(g.complete("a", "POLICE", s, true));
        assertEquals(List.of("b", "odd_job", "old_friend"), ids(g.available(s)));
        assertFalse(g.isAvailable("c", s), "the gang branch never opened");
        assertEquals("already completed", g.whyNot("a", s));
        assertEquals("requirement not met", g.whyNot("c", s));
        assertEquals("no such activity", g.whyNot("nope", s));
        assertFalse(g.complete("b", "NO_SUCH_VARIANT", s, true));
        g.complete("b", "DONE", s, true);
        assertEquals("1", s.flag(BRIDGE));
        // old_friend's requirement (not trusted) is false now, but it was available once and is STICKY
        assertTrue(g.isAvailable("old_friend", s));
        g.complete("odd_job", "PAID", s, true);
        assertTrue(g.isAvailable("odd_job", s), "a job is repeatable");
        g.complete("finale", "CLEAN", s, true);
        assertEquals(CampaignGraph.POST_ENDING, s.phase());
        assertTrue(g.isAvailable("odd_job", s), "after an ending the world stays open");
    }

    @Test
    void anUndeclaredOrPlannedActivityIsNeverAvailable() {
        CampaignGraph g = CampaignModules.graph();
        SimCampaign s = new SimCampaign();
        assertFalse(g.isAvailable("m99_nobody_declared", s));
        g.complete(Act1.M01_KONBINI, Act1.BOSS_SPARED, s, true);
        assertFalse(g.isAvailable(Act1.M02_INFORMANT, s));
        assertEquals("not authored yet", g.whyNot(Act1.M02_INFORMANT, s));
    }

    /** The co-op model: personal effects to the profile, world effects to the host's ledger -- or not at all. */
    @Test
    void theLiveStateSplitsStoryAndWorld() {
        CampaignGraph g = sample(false);
        PlayerProfile p = new PlayerProfile("p1");
        LiveCampaign live = new LiveCampaign(p, WorldLedger.get());
        long rev = p.revision();
        g.complete("a", "POLICE", live, true);
        g.complete("b", "DONE", live, true);
        assertEquals("police", p.campaign.flags.get("side"));
        assertEquals("1", p.campaign.flags.get("trust"));
        assertTrue(p.campaign.achieved.contains("b#DONE"));
        assertTrue(WorldLedger.get().isSet("bridge_open"), "a WORLD flag lands in the ledger");
        assertFalse(p.campaign.flags.containsKey("bridge_open"));
        assertTrue(p.revision() > rev, "the profile is dirty");
        assertTrue(p.campaign.sticky.contains("old_friend"));

        // a guest without the host's consent: the story is theirs, the world is not touched
        WorldLedger.replace(null);
        PlayerProfile guest = new PlayerProfile("p2");
        LiveCampaign g2 = new LiveCampaign(guest, WorldLedger.get());
        g.complete("a", "GANG", g2, false);
        g.complete("c", "DONE", g2, false);
        assertTrue(guest.campaign.achieved.contains("c#DONE"));
        assertFalse(WorldLedger.get().isDead("chief"));

        // and the profile's campaign survives its own file shape
        PlayerProfile back = PlayerProfile.fromMap(p.toMap());
        assertEquals(p.campaign.sticky, back.campaign.sticky);
        assertEquals(p.campaign.achieved, back.campaign.achieved);
    }

    @Test
    void aWorldRequirementReadsTheWorldTheActivityWouldRunIn() {
        Requirement r = all(achieved(Act1.M01_KONBINI, Act1.BOSS_SPARED), Requirement.storyAlive(Act1.M01_BOSS));
        PlayerProfile p = new PlayerProfile("p1");
        p.campaign.achieved.add("m01_konbini#BOSS_SPARED");
        assertTrue(r.test(new LiveCampaign(p, WorldLedger.get())));
        WorldLedger.get().markDead(Act1.M01_BOSS);   // this host killed him
        assertFalse(r.test(new LiveCampaign(p, WorldLedger.get())));
    }

    static List<String> ids(List<ActivityDef> l) { return l.stream().map(d -> d.id).toList(); }
}
