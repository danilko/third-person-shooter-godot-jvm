package com.openworld.game.campaign.content;

import com.openworld.game.campaign.CampaignBuilder;
import com.openworld.game.campaign.CampaignModule;
import com.openworld.game.campaign.Effect;
import com.openworld.game.campaign.FlagKey;
import com.openworld.game.campaign.Requirement;

/**
 * Act 1 as it exists today (PLAN.md 2.1): the konbini job and the branch a spared boss opens. This is the graph that
 * {@code KonbiniMission._ready} used to declare from a scene node ({@code declareUnlockOn("m02_informant",
 * "m01_konbini#BOSS_SPARED")}); the ids and variants are the same.
 */
public final class Act1 implements CampaignModule {

    public static final String M01_KONBINI = "m01_konbini";
    public static final String M02_INFORMANT = "m02_informant";
    public static final String BOSS_KILLED = "BOSS_KILLED";
    public static final String BOSS_SPARED = "BOSS_SPARED";
    public static final String M01_BOSS = "m01_boss";

    /** The player let the konbini boss go: he owes them. */
    public static final FlagKey SPARED_THE_BOSS = FlagKey.bool("m01_spared_the_boss", FlagKey.Scope.PERSONAL);

    @Override public String id() { return "act1"; }

    @Override public void define(CampaignBuilder b) {
        b.flag(SPARED_THE_BOSS);
        b.activity(M01_KONBINI).title("The konbini job").runs(KonbiniActivity::new)
                .variant(BOSS_KILLED, Effect.storyDead(M01_BOSS))
                .variant(BOSS_SPARED, Effect.set(SPARED_THE_BOSS));
        // the informant is the spared boss: his mission needs the player to have spared him AND him to be alive in
        // the world it would run in (a guest who spared him at home cannot start it in a world where he was killed)
        b.activity(M02_INFORMANT).title("The informant").planned()
                .requires(Requirement.all(Requirement.achieved(M01_KONBINI, BOSS_SPARED), Requirement.storyAlive(M01_BOSS)));
        // no ending is authored yet (PLAN.md 4.3)
        b.openEnded();
    }
}
