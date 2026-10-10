package com.openworld.game.campaign;

import com.openworld.game.campaign.content.CampaignModules;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CampaignLintTest {

    /** THE gate: what ships lints clean. */
    @Test
    void theShippedCampaignIsClean() {
        CampaignLint.Report r = CampaignLint.check(CampaignModules.graph());
        assertEquals(List.of(), r.problems());
        assertTrue(r.notes().stream().anyMatch(n -> n.contains("open-ended")), "it says what it did not prove: " + r.notes());
    }

    @Test
    void aBranchingCampaignWithEndingsIsProvenToHaveNoDeadEnd() {
        CampaignLint.Report r = CampaignLint.check(CampaignGraphTest.sample(false));
        assertEquals(List.of(), r.problems());
        assertTrue(r.statesWalked() > 5, r.statesWalked() + " states");
    }

    /** The control: a variant that clears the choice every later node needs strands the player. */
    @Test
    void aDeadEndIsFound() {
        CampaignLint.Report r = CampaignLint.check(CampaignGraphTest.sample(true));
        assertFalse(r.ok());
        assertTrue(r.problems().stream().anyMatch(p -> p.startsWith("DEAD END") && p.contains("trap#STUCK")), r.problems().toString());
    }

    @Test
    void whatIsNamedMustBeDeclared() {
        FlagKey ghost = FlagKey.bool("ghost", FlagKey.Scope.PERSONAL);
        FlagKey side = FlagKey.choice("side", FlagKey.Scope.PERSONAL, "a", "b");
        CampaignBuilder b = new CampaignBuilder();
        b.flag(side);
        b.ending("end");
        b.activity("one").requires(Requirement.flag(ghost)).variant("X", Effect.set(side, "c"), Effect.ending("nope"));
        b.activity("two").requires(Requirement.all(Requirement.achieved("zero"), Requirement.achieved("one", "Y")));
        b.activity("one");
        List<String> p = CampaignLint.check(b.build()).problems();
        String all = String.join("\n", p);
        assertTrue(all.contains("activity 'one' is declared twice"), all);
        assertTrue(all.contains("flag 'ghost', which no module declares"), all);
        assertTrue(all.contains("flag 'side' = 'c', not one of [a, b]"), all);
        assertTrue(all.contains("reaches ending 'nope', which no module declares"), all);
        assertTrue(all.contains("activity 'two' has no variant"), all);
        assertTrue(all.contains("activity 'zero', which no module declares"), all);
        assertTrue(all.contains("'one' variant 'Y', which it does not have"), all);
        assertTrue(all.contains("ending 'end' is never reached"), all);
    }

    @Test
    void anActivityNoStateCanStartAndACampaignWithNoEnding() {
        FlagKey never = FlagKey.bool("never", FlagKey.Scope.PERSONAL);
        CampaignBuilder b = new CampaignBuilder();
        b.flag(never);
        b.activity("open").variant("X");
        b.activity("locked").requires(Requirement.flag(never)).variant("X");
        String all = String.join("\n", CampaignLint.check(b.build()).problems());
        assertTrue(all.contains("activity 'locked' can never be started"), all);
        assertTrue(all.contains("declares no ending"), all);
    }

    @Test
    void aWalkTooLargeToProveSaysSo() {
        CampaignLint.Report r = CampaignLint.check(CampaignGraphTest.sample(false), 3);
        assertTrue(r.problems().stream().anyMatch(p -> p.contains("the walk stopped at 3 states")), r.problems().toString());
    }
}
