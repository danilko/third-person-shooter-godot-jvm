package com.openworld.game.activity;

/**
 * Something a player DOES that has a beginning, stages and an outcome (PLAN.md 2.1 / AR1 = F5): a story mission, a
 * job, a race. A designer writes one class per activity from typed parts -- no JSON mission graph, no beat scripting
 * language:
 *
 * <pre>
 *   public final class KonbiniActivity extends Activity {
 *       &#64;Override protected void define(Plan p) {
 *           p.startsOnZone("m01_start").cast(BOSS, CREW_1, CREW_2).relation("player", "gang_a", "HOSTILE");
 *           p.rules().failWhenAllDown("every player is down");
 *           p.stage("FIGHT").checkpoint()
 *               .enter(a -> a.setFaction(BOSS, "gang_a"))
 *               .on(GameplayEvent.Killed.class, e -> e.target().id().equals(BOSS), (a, e) -> a.complete("BOSS_KILLED"))
 *               .when("the boss gives up", a -> a.host().healthFraction(BOSS) < 0.5, a -> a.go("SURRENDER"));
 *           p.stage("SURRENDER").after(15, a -> a.complete("BOSS_SPARED"));
 *       }
 *   }
 * </pre>
 *
 * <p>The class holds NO engine types: everything it asks of the world goes through {@link ActivityHost}, so its stage
 * graph runs unchanged against a {@link FakeActivityHost} fed scripted events (CR6's tier-1 test kit). The framework
 * ({@link ActivityDirector}) owns the rest: host authority, who takes part, the lifecycle, the temporary career, the
 * checkpoint, what each participant is credited with, cleanup.
 *
 * <p>Tuning is the class's public fields (a placement node may set them before the first stage); a new instance is
 * built for every run, so nothing carries over.
 */
public abstract class Activity {

    /** STORY: the real thing. REPLAY: the same stages in a sandbox (CR7) -- nothing personal or in the world is
     *  written, temporary careers are discarded, heat earned stays. */
    public enum Mode { STORY, REPLAY }

    /** OWNER started it (their story decides whether it may run, their failure rows apply); ASSIST joined.
     *  Anyone else is an outsider: what they do to it is an ordinary crime, and a rule may fail the job on it. */
    public enum Role { OWNER, ASSIST }

    /** Declare the stages, rules and needs. Called once per run, before the first stage. */
    protected abstract void define(Plan p);
}
