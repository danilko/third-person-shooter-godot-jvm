package com.openworld.game.activity;

import com.openworld.game.campaign.ActivityDef;
import com.openworld.game.event.Spot;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * One RUN of an activity (PLAN.md 2.1): who takes part, the stage it is in, its blackboard. This is what a stage's
 * reactions are handed -- they read the world through {@link #host}, and end the stage with {@link #go},
 * {@link #complete} or {@link #fail} (the first request in a step wins; it takes effect when the reaction returns).
 * What a run takes of the world through here (a character's faction, unlocked doors) the framework gives back.
 */
public final class ActivityInstance {

    public enum Outcome { RUNNING, COMPLETED, FAILED, ABORTED }

    public record Participant(String playerId, Activity.Role role, boolean eligible) {}

    final String instanceId;
    final ActivityDef def;
    final Activity script;
    final Plan plan;
    final Activity.Mode mode;
    final ActivityHost host;
    final Map<String, Participant> participants = new LinkedHashMap<>();
    final Blackboard board = new Blackboard();
    final Map<String, String> factionsBefore = new LinkedHashMap<>();
    final Set<Stage.Timer> fired = new HashSet<>();
    final Set<String> careerPushed = new HashSet<>();

    Stage stage;
    double stageSeconds, seconds;
    ActivityCheckpoint checkpoint;
    Outcome outcome = Outcome.RUNNING;
    String variant = "", reason = "";
    int doorsUnlocked;

    private String wantStage, wantVariant, wantFail;

    ActivityInstance(String instanceId, ActivityDef def, Activity script, Plan plan, Activity.Mode mode, ActivityHost host) {
        this.instanceId = instanceId;
        this.def = def;
        this.script = script;
        this.plan = plan;
        this.mode = mode;
        this.host = host;
    }

    // ── what a reaction reads ──

    public String instanceId() { return instanceId; }
    public String activityId() { return def.id; }
    public Activity.Mode mode() { return mode; }
    public ActivityHost host() { return host; }
    public Blackboard board() { return board; }
    public String stageId() { return stage == null ? "" : stage.id; }
    /** Seconds since the current stage was entered. */
    public double stageSeconds() { return stageSeconds; }
    public double seconds() { return seconds; }
    public Outcome outcome() { return outcome; }
    public String variant() { return variant; }
    public String reason() { return reason; }
    public int doorsUnlocked() { return doorsUnlocked; }
    public List<Participant> participants() { return new ArrayList<>(participants.values()); }
    public boolean isParticipant(String playerId) { return participants.containsKey(playerId); }
    public boolean isCast(String characterId) { return plan.cast.contains(characterId); }

    public String owner() {
        for (Participant p : participants.values()) if (p.role() == Activity.Role.OWNER) return p.playerId();
        return "";
    }

    /** How far the nearest participant who is up stands from a story character (infinite when nobody is). */
    public double nearestParticipantDistance(String characterId) {
        Spot c = host.at(characterId);
        double best = Double.POSITIVE_INFINITY;
        for (String id : participants.keySet()) {
            if (!host.playerPresent(id) || host.playerDown(id)) continue;
            best = Math.min(best, host.playerAt(id).distanceTo(c));
        }
        return best;
    }

    // ── what a reaction does ──

    /** Move to another stage. */
    public void go(String stageId) { if (!decided()) wantStage = stageId; }

    /** End it with one of the variants its {@code ActivityDef} declares. */
    public void complete(String variantId) { if (!decided()) wantVariant = variantId; }

    public void fail(String why) { if (!decided()) wantFail = why == null || why.isEmpty() ? "failed" : why; }

    /**
     * Change a story character's faction for the run. A run that FAILS or is aborted gives the old one back (so it
     * can be tried again); a completed run leaves it -- the outcome is the world's new state.
     */
    public void setFaction(String characterId, String faction) {
        factionsBefore.putIfAbsent(characterId, host.faction(characterId));
        host.setFaction(characterId, faction);
    }

    /** Unlock the locked doors within {@code radius} of the activity's placement; locked again at the end. */
    public int unlockDoors(double radius) {
        int n = host.unlockDoors(instanceId, host.anchor(def.id), radius);
        doorsUnlocked += n;
        return n;
    }

    public void say(String speaker, String line) { host.say(instanceId, speaker, line); }

    public void mark(String what) { host.mark(instanceId, what); }

    // ── the director's side ──

    boolean decided() { return wantStage != null || wantVariant != null || wantFail != null; }
    String takeStage() { String s = wantStage; wantStage = null; return s; }
    String takeVariant() { String s = wantVariant; wantVariant = null; return s; }
    String takeFail() { String s = wantFail; wantFail = null; return s; }
}
