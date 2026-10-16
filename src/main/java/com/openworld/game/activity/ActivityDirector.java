package com.openworld.game.activity;

import com.openworld.game.campaign.ActivityDef;
import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.CampaignView;
import com.openworld.game.campaign.CampaignWrite;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.event.Actor;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.profile.CareerState;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Runs the activities (PLAN.md 2.1 / AR1): N at once, each an {@link ActivityInstance} of a class a
 * {@code CampaignModule} declared with {@code .runs(..)}. It replaces the ONE mission slot of {@code MissionManager}
 * for everything written on the framework, and owns what a mission class used to hand-roll:
 *
 * <ul>
 *   <li><b>who may start</b> -- the OWNER's own story against this world ({@code CampaignGraph.isAvailable}); a
 *       REPLAY needs it completed and its {@code replayWorld} to hold or be stageable; a guest needs the host's
 *       consent for an activity that alters the world;</li>
 *   <li><b>how it starts</b> -- walking into its start zone only OFFERS it ({@link ActivityHost#offer}: a prompt);
 *       the player {@link #accept}s. Walking into the zone of one already RUNNING joins it;</li>
 *   <li><b>who takes part</b> -- one OWNER, anyone may ASSIST an open one; a player is in at most one run, and an
 *       activity runs once at a time (its story characters are one set in the world);</li>
 *   <li><b>the lifecycle</b> -- stages, their triggers on {@link GameplayEvent}s / timers / conditions, the rules
 *       (fail rows, sanction / veto, career penalties), the checkpoint and RETRY from it;</li>
 *   <li><b>the temporary career</b> -- pushed at the start / on joining, popped at the end whatever the end (CR2);</li>
 *   <li><b>the result</b> -- one {@link ActivityResult} PER PARTICIPANT: story credit only to those who were
 *       themselves eligible, the variant's world effects once through the owner, pay to everyone;</li>
 *   <li><b>cleanup</b> -- doors, the faction overlay, markers, a staged replay world, factions of a failed run.</li>
 * </ul>
 *
 * Engine-free: it is told the time ({@link #tick}) and the events ({@link #onEvent}, subscribed in
 * {@code Phase.ACTIVITY}) and reaches the world through one {@link ActivityHost}. AUTHORITY ONLY, like the event
 * stream it listens to: a co-op client runs none (the host's results reach it through its profile).
 */
public final class ActivityDirector implements GameplayEvents.Subscriber {

    public interface Listener {
        default void started(ActivityInstance a) {}
        default void joined(ActivityInstance a, ActivityInstance.Participant p) {}
        default void stage(ActivityInstance a) {}
        default void ended(ActivityInstance a, List<ActivityResult> results) {}
    }

    /** {@code instance} null = refused, and {@code refusal} says why. */
    public record Start(ActivityInstance instance, String refusal) {
        public boolean ok() { return instance != null; }
    }

    private static final int MAX_HOPS = 16;

    private final CampaignGraph graph;
    private final ActivityHost host;
    private final Map<String, ActivityInstance> running = new LinkedHashMap<>();
    private final Map<String, String> zoneStarts = new LinkedHashMap<>();
    private final List<Listener> listeners = new ArrayList<>();
    private Consumer<GameplayEvent> publisher = GameplayEvents::publish;
    private long started;

    public ActivityDirector(CampaignGraph graph, ActivityHost host) {
        this.graph = graph;
        this.host = host;
        for (ActivityDef d : graph.activities()) {
            Plan p = planOf(d, d.newRun());
            if (p != null && !p.startZone.isEmpty()) zoneStarts.put(p.startZone, d.id);
        }
    }

    private static Plan planOf(ActivityDef d, Activity script) {
        if (script == null) return null;
        Plan p = new Plan();
        script.define(p);
        return p;
    }

    public void addListener(Listener l) { if (l != null && !listeners.contains(l)) listeners.add(l); }

    /** Where {@code ActivityOutcome} goes (default: the event stream; a test collects them). */
    public void setPublisher(Consumer<GameplayEvent> p) { publisher = p == null ? e -> { } : p; }

    public CampaignGraph graph() { return graph; }

    // ── asking ──

    public List<ActivityInstance> running() { return new ArrayList<>(running.values()); }

    public boolean isRunning(String instanceId) { return running.containsKey(instanceId); }

    /** The run of this activity, or null. */
    public ActivityInstance runningOf(String activityId) {
        for (ActivityInstance a : running.values()) if (a.def.id.equals(activityId)) return a;
        return null;
    }

    /** The run this player takes part in, or null. */
    public ActivityInstance of(String playerId) {
        for (ActivityInstance a : running.values()) if (a.participants.containsKey(playerId)) return a;
        return null;
    }

    /** Why this player may not start it now in this mode ("" = they may). */
    public String whyNot(String activityId, String playerId, Activity.Mode mode) {
        ActivityDef d = graph.activity(activityId);
        if (d == null) return "no such activity";
        if (d.isPlanned() || !d.hasScript()) return "not authored yet";
        if (!host.playerPresent(playerId)) return "no such player";
        CampaignWrite story = host.story(playerId);
        if (story == null) return "the player has no profile here";
        ActivityInstance in = of(playerId);
        if (in != null) return "already in '" + in.def.id + "'";
        if (runningOf(activityId) != null) return "already running";
        if (mode == Activity.Mode.REPLAY) {
            if (!story.achieved(activityId, "")) return "not completed yet";
            for (Requirement need : planOf(d, d.newRun()).replayWorld)
                if (!need.test(story) && !host.canStage(need)) return "cannot be replayed in this world: " + need;
            return "";
        }
        String why = graph.whyNot(activityId, story);
        if (!why.isEmpty()) return why;
        if (d.altersWorld() && !host.ownsWorld(playerId) && !host.worldConsent(activityId, playerId))
            return "it changes the world: the host has not agreed";
        return "";
    }

    // ── starting, joining, leaving ──

    public Start start(String activityId, String ownerId, Activity.Mode mode) { return start(activityId, ownerId, mode, null); }

    /** Try a failed run again from its checkpoint (the same mode; the owner alone -- helpers join again). */
    public Start retry(String ownerId) {
        ActivityCheckpoint cp = host.keptCheckpoint(ownerId);
        if (cp == null) return new Start(null, "nothing to retry");
        return start(cp.activityId(), ownerId, cp.mode(), cp);
    }

    private Start start(String activityId, String ownerId, Activity.Mode mode, ActivityCheckpoint from) {
        String why = whyNot(activityId, ownerId, mode);
        if (!why.isEmpty()) return new Start(null, why);
        ActivityDef d = graph.activity(activityId);
        Activity script = d.newRun();
        host.configure(activityId, script);
        Plan plan = planOf(d, script);
        if (plan.stages.isEmpty()) return new Start(null, "it has no stage");
        Stage first = plan.stages.values().iterator().next();
        if (from != null) {
            first = plan.stages.get(from.stageId());
            if (first == null) return new Start(null, "its checkpoint names stage '" + from.stageId() + "', which it no longer has");
        }
        ActivityInstance a = new ActivityInstance(activityId + "@" + (++started), d, script, plan, mode, host);
        if (from != null) a.board.read(from.board());
        else host.keepCheckpoint(ownerId, null);   // a fresh start forgets the checkpoint of whatever was tried before
        running.put(a.instanceId, a);
        add(a, ownerId, Activity.Role.OWNER, true);
        if (mode == Activity.Mode.REPLAY) {
            CampaignView story = host.story(ownerId);
            List<Requirement> stage = new ArrayList<>();
            for (Requirement need : plan.replayWorld) if (!need.test(story)) stage.add(need);
            if (!stage.isEmpty()) host.stage(a.instanceId, stage);
        }
        if (!plan.relations.isEmpty()) host.relations(a.instanceId, List.copyOf(plan.relations));
        if (plan.enforcement.any()) host.enforcement(a.instanceId, activityId, plan.enforcement);
        host.log("activity '" + activityId + "' started by " + ownerId + " (" + mode + (from == null ? "" : ", from checkpoint " + from.stageId()) + ")");
        for (Listener l : listeners) l.started(a);
        enter(a, first);
        settle(a);
        return new Start(a, "");
    }

    /** Join a run as ASSIST ("" = joined; else why not). */
    public String join(String instanceId, String playerId) {
        ActivityInstance a = running.get(instanceId);
        if (a == null) return "no such run";
        if (a.participants.containsKey(playerId)) return "already in it";
        if (!a.plan.open) return "it is closed";
        if (a.participants.size() >= a.plan.maxParticipants) return "it is full";
        if (!host.playerPresent(playerId)) return "no such player";
        ActivityInstance in = of(playerId);
        if (in != null) return "already in '" + in.def.id + "'";
        CampaignView story = host.story(playerId);
        // rule 4: story credit only to a helper who could have started it themselves; anyone may help
        boolean eligible = a.mode == Activity.Mode.STORY && story != null && graph.isAvailable(a.def.id, story);
        ActivityInstance.Participant p = add(a, playerId, Activity.Role.ASSIST, eligible);
        for (Listener l : listeners) l.joined(a, p);
        return "";
    }

    private ActivityInstance.Participant add(ActivityInstance a, String playerId, Activity.Role role, boolean eligible) {
        ActivityInstance.Participant p = new ActivityInstance.Participant(playerId, role, eligible);
        a.participants.put(playerId, p);
        if (!a.plan.tempCareer.isEmpty() && a.plan.tempRoles.contains(role)) {
            CareerState c = host.career(playerId);
            // a REPLAY is a sandbox: its temporary career is always TEMP, whatever the mission says
            if (c != null && c.push(a.instanceId, a.plan.tempCareer, a.plan.tempReal && a.mode == Activity.Mode.STORY))
                a.careerPushed.add(playerId);
        }
        return p;
    }

    /** A player left the session: the run they OWN is aborted; one they assist goes on without them. */
    public void leave(String playerId, String why) {
        ActivityInstance a = of(playerId);
        if (a == null) return;
        if (playerId.equals(a.owner())) {
            end(a, ActivityInstance.Outcome.ABORTED, "", why == null || why.isEmpty() ? "the owner left" : why);
            return;
        }
        popCareer(a, playerId);
        a.participants.remove(playerId);
    }

    public void abort(String instanceId, String why) {
        ActivityInstance a = running.get(instanceId);
        if (a != null) end(a, ActivityInstance.Outcome.ABORTED, "", why);
    }

    /** Something outside the activity ended it for its OWNER (arrested, abducted): the run they own fails. */
    public void failFor(String playerId, String why) {
        ActivityInstance a = of(playerId);
        if (a != null && playerId.equals(a.owner())) end(a, ActivityInstance.Outcome.FAILED, "", why);
    }

    /** Abort every run (the session ends, a save is loaded). */
    public void abortAll(String why) {
        for (ActivityInstance a : running()) end(a, ActivityInstance.Outcome.ABORTED, "", why);
    }

    // ── time and events ──

    public void tick(double dt) {
        for (ActivityInstance a : running()) {
            if (a.outcome != ActivityInstance.Outcome.RUNNING) continue;
            a.seconds += dt;
            a.stageSeconds += dt;
            if (!host.playerPresent(a.owner())) {
                end(a, ActivityInstance.Outcome.ABORTED, "", "the owner left");
                continue;
            }
            for (ActivityInstance.Participant p : a.participants())
                if (!host.playerPresent(p.playerId())) leave(p.playerId(), "");
            RuleSet r = a.plan.rules;
            if (!r.allDownReason.isEmpty() && allDown(a)) a.fail(r.allDownReason);
            for (RuleSet.FailWhen f : r.failWhen) if (!a.decided() && f.holds().test(a)) a.fail(f.reason());
            Stage s = a.stage;
            for (Stage.Timer t : s.timers) {
                if (a.decided()) break;
                if (a.stageSeconds >= t.seconds() && a.fired.add(t)) t.react().accept(a);
            }
            for (Stage.Condition c : s.conditions) {
                if (a.decided()) break;
                if (c.holds().test(a)) c.react().accept(a);
            }
            if (!a.decided() && s.tick != null) s.tick.accept(a, dt);
            settle(a);
        }
    }

    private boolean allDown(ActivityInstance a) {
        for (String id : a.participants.keySet()) if (!host.playerDown(id)) return false;
        return !a.participants.isEmpty();
    }

    /** {@code GameplayEvents.Phase.ACTIVITY}: the running activities hear every event first. */
    @Override public void on(GameplayEvent e, GameplayEvents.Ruling ruling) { onEvent(e, ruling); }

    public void onEvent(GameplayEvent e, GameplayEvents.Ruling ruling) {
        if (e instanceof GameplayEvent.ActivityOutcome) return;
        List<ActivityInstance> now = running();
        for (ActivityInstance a : now) {
            if (a.outcome != ActivityInstance.Outcome.RUNNING) continue;
            boolean byParticipant = a.participants.containsKey(e.actor().id());
            if (a.mode == Activity.Mode.REPLAY && (byParticipant || involves(a, e.target()) || involves(a, e.actor())))
                ruling.sandbox(a.instanceId);
            RuleSet r = a.plan.rules;
            for (RuleSet.Judge j : r.judges) {
                if (!j.match().test(a, e)) continue;
                if (j.verdict() == RuleSet.Verdict.VETO) ruling.veto(a.instanceId);
                else ruling.sanction(a.instanceId);
            }
            if (byParticipant) for (RuleSet.Penalty p : r.penalties) if (p.match().test(a, e)) penalise(a, e.actor().id(), p);
            for (RuleSet.FailOn f : r.failOn) if (!a.decided() && f.match().test(a, e)) a.fail(f.reason());
            for (Stage.EventTrigger<?> t : a.stage.events) {
                if (a.decided()) break;
                t.offer(a, e);
            }
            settle(a);
        }
        if (e instanceof GameplayEvent.ZoneEntered z && e.actor().isPlayer()) zoneEntered(z.zoneId(), e.actor().id());
    }

    private static boolean involves(ActivityInstance a, Actor who) {
        return a.participants.containsKey(who.id()) || a.plan.cast.contains(who.id()) || a.plan.cast.contains(who.storyId());
    }

    private void penalise(ActivityInstance a, String playerId, RuleSet.Penalty p) {
        CareerState c = host.career(playerId);
        if (c == null) return;
        // a REPLAY never touches a real record: only the scratch of the temporary career this run pushed
        if (a.mode == Activity.Mode.REPLAY && !a.careerPushed.contains(playerId)) return;
        c.count(p.counter(), p.n());
    }

    private void zoneEntered(String zoneId, String playerId) {
        String activityId = zoneStarts.get(zoneId);
        if (activityId == null) return;
        ActivityInstance a = runningOf(activityId);
        if (a != null) {
            if (!a.participants.containsKey(playerId) && a.plan.open) {
                String why = join(a.instanceId, playerId);
                if (!why.isEmpty()) host.log("activity '" + activityId + "': " + playerId + " did not join -- " + why);
            }
            return;
        }
        // never started by walking in (user, 2026-10-10: "I accidentally enter the mission"): it is OFFERED, and
        // the player accepts it deliberately
        String why = whyNot(activityId, playerId, Activity.Mode.STORY);
        if (why.isEmpty()) host.offer(activityId, playerId);
        else host.log("activity '" + activityId + "' not offered to " + playerId + ": " + why);
    }

    /** The player took the offer their walking into the start zone made (the interact key on its prompt). */
    public Start accept(String activityId, String playerId) { return start(activityId, playerId, Activity.Mode.STORY); }

    // ── stages and the end ──

    private void enter(ActivityInstance a, Stage s) {
        a.stage = s;
        a.stageSeconds = 0;
        a.fired.clear();
        if (s.checkpoint) {
            a.checkpoint = new ActivityCheckpoint(a.def.id, s.id, a.mode, a.board.toMap());
            host.keepCheckpoint(a.owner(), a.checkpoint);
        }
        host.mark(a.instanceId, s.marker);
        if (!s.line.isEmpty()) host.say(a.instanceId, s.speaker, s.line);
        if (s.enter != null) s.enter.accept(a);
        for (Listener l : listeners) l.stage(a);
    }

    /** Apply what the reactions asked for: a move, a completion, a failure (and whatever the next stage asks). */
    private void settle(ActivityInstance a) {
        for (int hop = 0; a.outcome == ActivityInstance.Outcome.RUNNING && a.decided(); hop++) {
            String fail = a.takeFail(), variant = a.takeVariant(), next = a.takeStage();
            if (fail != null) {
                end(a, ActivityInstance.Outcome.FAILED, "", fail);
            } else if (variant != null) {
                if (a.def.hasVariant(variant)) end(a, ActivityInstance.Outcome.COMPLETED, variant, "");
                else end(a, ActivityInstance.Outcome.FAILED, "", "it ended with '" + variant + "', which '" + a.def.id + "' does not declare");
            } else {
                Stage s = a.plan.stages.get(next);
                if (s == null || hop >= MAX_HOPS) {
                    end(a, ActivityInstance.Outcome.FAILED, "", s == null ? "it went to stage '" + next + "', which it does not have"
                            : "its stages loop without waiting ('" + next + "')");
                    return;
                }
                if (a.stage.exit != null) a.stage.exit.accept(a);
                enter(a, s);
            }
        }
    }

    private void popCareer(ActivityInstance a, String playerId) {
        if (!a.careerPushed.remove(playerId)) return;
        CareerState c = host.career(playerId);
        if (c != null) c.pop(a.instanceId);
    }

    private void end(ActivityInstance a, ActivityInstance.Outcome outcome, String variant, String reason) {
        if (a.outcome != ActivityInstance.Outcome.RUNNING) return;
        a.outcome = outcome;
        a.variant = variant == null ? "" : variant;
        a.reason = reason == null ? "" : reason;
        if (a.stage != null && a.stage.exit != null) a.stage.exit.accept(a);
        running.remove(a.instanceId);
        boolean completed = outcome == ActivityInstance.Outcome.COMPLETED;
        if (!completed) for (Map.Entry<String, String> f : a.factionsBefore.entrySet())
            if (host.present(f.getKey()) && !f.getValue().isEmpty()) host.setFaction(f.getKey(), f.getValue());
        host.release(a.instanceId);
        String owner = a.owner();
        // a FAILED or ABORTED run keeps its checkpoint: that is what RETRY starts from (a save loaded, the session
        // ended, the owner dropped); only completing it -- or starting something else -- forgets it
        if (completed || a.checkpoint == null) host.keepCheckpoint(owner, null);
        List<ActivityResult> results = new ArrayList<>();
        long reward = completed ? host.reward(a.def.id) : 0;
        for (ActivityInstance.Participant p : a.participants()) {
            popCareer(a, p.playerId());
            boolean credit = false, world = false;
            long pay = 0;
            if (completed && a.mode == Activity.Mode.STORY) {
                CampaignWrite story = host.story(p.playerId());
                if (p.eligible() && story != null) {
                    world = p.role() == Activity.Role.OWNER;
                    credit = graph.complete(a.def.id, a.variant, story, world);
                    world &= credit && a.def.effects(a.variant).stream().anyMatch(com.openworld.game.campaign.Effect::world);
                    if (credit) host.storyCheckpoint(p.playerId());
                }
                pay = reward;
            } else if (completed) {
                pay = Math.round(reward * a.plan.replayPay);
            }
            if (pay > 0) host.pay(p.playerId(), pay);
            results.add(new ActivityResult(a.instanceId, a.def.id, p.playerId(), p.role(), a.mode, outcome, a.variant,
                    a.reason, credit, world, pay));
        }
        host.log("activity '" + a.def.id + "' " + outcome + (completed ? " as " + a.variant : " -- " + a.reason));
        for (Listener l : listeners) l.ended(a, results);
        publisher.accept(new GameplayEvent.ActivityOutcome(Actor.player(owner, ""), a.def.id, a.instanceId, outcome.name(),
                a.variant, a.mode.name()));
    }
}
