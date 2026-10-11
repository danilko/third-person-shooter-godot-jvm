package com.openworld.game.campaign.content;

import com.openworld.game.activity.Activity;
import com.openworld.game.activity.ActivityInstance;
import com.openworld.game.activity.Plan;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.event.GameplayEvent;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * "The konbini job" (PLAN.md 4.8), the first story mission, as the REFERENCE activity on the framework (2.1): what
 * {@code KonbiniMission} hand-rolled in a scene node -- its phases, its host check, its door unlocks, its fail rule --
 * is two stages here, and the framework owns the rest.
 *
 * <ul>
 *   <li>A crew of named characters loiters on the pavement outside a konbini as {@code neutral}. The shop is an
 *       ordinary open one (redesigned 2026-10-11, user: "the player cannot enter the store ... should be able to
 *       trigger the mission while inside"): a player anywhere in it or on its pavement is offered the job -- walk in,
 *       buy a gun at the counter, start it from behind the shelves -- and starts it with the interact key (another
 *       player walking into the running job joins it): the crew turns {@link #hostileFaction}, which the job's
 *       overlay makes hostile to players. (A LOCKED door within {@link #doorUnlockRadius} is still unlocked for the
 *       run: nothing at this shop any more, the rule is there for a mission whose building is shut.)</li>
 *   <li>FIGHT: with the crew down and the boss under {@link #surrenderHealthFraction}, he SURRENDERS -- neutral
 *       again and running. That is the choice.</li>
 *   <li>SURRENDER: shoot him anyway and the job completes {@code BOSS_KILLED}; let him get {@link #spareDistance}
 *       away, or {@link #spareSeconds} pass, and it completes {@code BOSS_SPARED}. Killing him before he surrenders
 *       is {@code BOSS_KILLED} too.</li>
 *   <li>It fails when every participant is down, or the boss's zone unloads (the players left). A failed job gives
 *       the crew its old faction back and can be retried from the FIGHT.</li>
 * </ul>
 * What each variant CHANGES is {@link Act1}'s row for it, not this class's business.
 */
public final class KonbiniActivity extends Activity {

    public static final String START_ZONE = "m01_start";
    public static final String FIGHT = "FIGHT", SURRENDER = "SURRENDER";

    public String boss = Act1.M01_BOSS;
    public List<String> crew = List.of("m01_crew_1", "m01_crew_2");
    public String hostileFaction = "gang_a";
    public double surrenderHealthFraction = 0.5;
    public double spareDistance = 45;
    public double spareSeconds = 15;
    /** Locked doors this near the job are open for its run (none at the konbini since it is an open shop). */
    public double doorUnlockRadius = 25;
    public String fightObjective = "Take down Kaneda's crew";
    public String surrenderObjective = "Kaneda gives up -- finish him, or let him run";

    @Override protected void define(Plan p) {
        List<String> everyone = new ArrayList<>(crew);
        everyone.add(0, boss);
        p.startsOnZone(START_ZONE).cast(everyone.toArray(new String[0]))
                .relation("player", hostileFaction, "HOSTILE")
                .replayWorld(Requirement.storyAlive(boss));
        p.rules().failWhenAllDown("every player is down")
                .failWhen("left the area", a -> !a.host().present(boss));

        Consumer<ActivityInstance> spared = a -> {
            a.host().uncommand(boss);
            a.complete(Act1.BOSS_SPARED);
        };
        p.stage(FIGHT).checkpoint().marker(boss).objective("", fightObjective)
                .enter(a -> {
                    for (String id : everyone) a.setFaction(id, hostileFaction);
                    a.unlockDoors(doorUnlockRadius);
                })
                .on(GameplayEvent.Killed.class, e -> boss.equals(e.target().id()), (a, e) -> a.complete(Act1.BOSS_KILLED))
                .when("the boss is dead", a -> !a.host().alive(boss), a -> a.complete(Act1.BOSS_KILLED))
                .when("the boss gives up", a -> crewUp(a) == 0 && a.host().healthFraction(boss) < surrenderHealthFraction,
                        a -> a.go(SURRENDER));
        p.stage(SURRENDER).marker(boss).objective("", surrenderObjective)
                .enter(a -> {
                    a.setFaction(boss, "neutral");
                    a.host().command(boss, "FLEE");
                })
                .on(GameplayEvent.Killed.class, e -> boss.equals(e.target().id()), (a, e) -> a.complete(Act1.BOSS_KILLED))
                .when("the boss is dead", a -> !a.host().alive(boss), a -> a.complete(Act1.BOSS_KILLED))
                .after(spareSeconds, spared)
                .when("he got away", a -> a.nearestParticipantDistance(boss) >= spareDistance, spared);
    }

    private int crewUp(ActivityInstance a) {
        int n = 0;
        for (String id : crew) if (a.host().alive(id)) n++;
        return n;
    }
}
