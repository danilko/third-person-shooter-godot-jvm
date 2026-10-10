package com.openworld.game.campaign;

import com.openworld.game.profile.PlayerProfile;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** CR4: a few hard game overs, per player, with a grace period, rolling the PROFILE back to its checkpoint. */
class GameOverWatchTest {

    static final GameOverRule DEBT = GameOverRule.debtOver("deep_debt", 100_000, 10, "Lender: you have until tonight.");

    final Map<String, PlayerProfile> players = new LinkedHashMap<>();
    final GameOverWatch watch = new GameOverWatch(List.of(DEBT));

    List<GameOverWatch.Notice> step(double dt) { return watch.step(dt, players, id -> new SimCampaign()); }

    PlayerProfile player(String id, long balance) {
        PlayerProfile p = new PlayerProfile(id);
        p.balance = balance;
        players.put(id, p);
        return p;
    }

    @Test
    void theStartOfTheGameIsTheFirstCheckpoint() {
        PlayerProfile p = player("a", 5_000);
        assertFalse(p.hasCheckpoint());
        assertEquals(List.of(), step(1));
        assertTrue(p.hasCheckpoint());
    }

    @Test
    void aBreachIsWarnedOnceAndClearedWhenPaidInTime() {
        PlayerProfile p = player("a", 5_000);
        step(1);
        p.balance = -150_000;
        assertEquals(List.of(new GameOverWatch.Notice(GameOverWatch.Kind.WARNED, "a", DEBT)), step(1));
        assertEquals(List.of(), step(1), "warned once");
        assertEquals(9.0, watch.graceLeft("a", DEBT), 1e-9);
        p.balance = -50_000;
        assertEquals(GameOverWatch.Kind.CLEARED, step(1).get(0).kind());
        assertEquals(-1, watch.graceLeft("a", DEBT), 1e-9);
        assertEquals(-50_000, p.balance, "nothing was rolled back");
    }

    @Test
    void outlastingTheGraceIsThatPlayersGameOverAndOnlyTheirs() {
        PlayerProfile a = player("a", 5_000), b = player("b", 700);
        a.campaign.achieved.add("m01#X");
        step(1);                                  // both checkpointed here
        a.balance = -150_000;
        a.campaign.achieved.add("m02#Y");
        a.career.base = "courier";
        b.balance = 900;
        step(1);
        List<GameOverWatch.Notice> last = List.of();
        for (int i = 0; i < 10 && last.isEmpty(); i++) last = step(1);
        assertEquals(List.of(new GameOverWatch.Notice(GameOverWatch.Kind.GAME_OVER, "a", DEBT)), last);
        assertEquals(5_000, a.balance, "back at the checkpoint");
        assertEquals(java.util.Set.of("m01#X"), a.campaign.achieved);
        assertEquals("", a.career.base);
        assertEquals("a", a.playerId);
        assertEquals(900, b.balance, "nobody else is touched");
        assertTrue(a.hasCheckpoint(), "the checkpoint stays: the next game over lands here again");
        assertEquals(List.of(), step(1), "and the game over is over: no rule holds at a checkpoint");
    }

    @Test
    void aCheckpointIsNeverTakenInABreachedState() {
        PlayerProfile p = player("a", -150_000);
        step(1);
        assertFalse(p.hasCheckpoint(), "a profile first seen in breach gets no checkpoint there");
        assertFalse(watch.mayCheckpoint(p, new SimCampaign()));
        for (int i = 0; i < 12; i++) step(1);
        assertEquals(-150_000, p.balance, "with no checkpoint there is nothing to roll back to");
    }

    @Test
    void theCheckpointSurvivesTheFileAndAModuleDeclaresRules() {
        PlayerProfile p = player("a", 5_000);
        p.takeCheckpoint();
        p.balance = 1;
        PlayerProfile back = PlayerProfile.fromMap(p.toMap());
        assertTrue(back.hasCheckpoint());
        assertTrue(back.rollbackToCheckpoint());
        assertEquals(5_000, back.balance);
        // over the wire the snapshot stays home: the host's copy says a checkpoint was taken, the owner takes theirs
        PlayerProfile host = PlayerProfile.fromMap(p.toWireMap());
        assertFalse(host.hasCheckpoint(), "the snapshot is not sent");
        host.balance = 9_000;
        host.takeCheckpoint();
        assertFalse(host.toWireMap().containsKey("checkpoint_snapshot"));
        PlayerProfile owner = PlayerProfile.fromMap(p.toMap());
        owner.copyFrom(PlayerProfile.fromMap(host.toWireMap()));
        owner.balance = 2;
        assertTrue(owner.rollbackToCheckpoint());
        assertEquals(9_000, owner.balance, "the owner checkpointed the state the host checkpointed");
        PlayerProfile quiet = PlayerProfile.fromMap(p.toMap());
        PlayerProfile same = PlayerProfile.fromMap(p.toWireMap());
        same.balance = 77;
        quiet.copyFrom(same);
        quiet.rollbackToCheckpoint();
        assertEquals(5_000, quiet.balance, "an ordinary change from the host keeps the owner's checkpoint");
        CampaignBuilder b = new CampaignBuilder();
        b.gameOverRule(DEBT).gameOverRule(DEBT).gameOverRule(GameOverRule.debtOver("no_grace", 1, 0, ""));
        CampaignGraph g = b.build();
        assertEquals(2, g.gameOverRules().size());
        String problems = String.join("\n", CampaignLint.check(g).problems());
        assertTrue(problems.contains("game-over rule 'deep_debt' is declared twice"), problems);
        assertTrue(problems.contains("game-over rule 'no_grace' has no grace period"), problems);
    }
}
