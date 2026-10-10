package com.openworld.game.activity;

import com.openworld.game.campaign.Requirement;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * What an {@link Activity} declares about itself in {@code define}: its stages (the first one declared is where it
 * starts), its rules, who may take part, and what it needs of the world while it runs.
 */
public final class Plan {

    /** One row of the activity's faction overlay: while it runs, {@code a} and {@code b} are {@code relationship}
     *  ("HOSTILE", "NEUTRAL", ... -- {@code FactionRules}' words), both ways. */
    public record Relation(String a, String b, String relationship) {}

    final Map<String, Stage> stages = new LinkedHashMap<>();
    final RuleSet rules = new RuleSet();
    final List<Relation> relations = new ArrayList<>();
    final Set<String> cast = new LinkedHashSet<>();
    final List<Requirement> replayWorld = new ArrayList<>();
    String startZone = "";
    int maxParticipants = 4;
    boolean open = true;
    String tempCareer = "";
    boolean tempReal;
    EnumSet<Activity.Role> tempRoles = EnumSet.of(Activity.Role.OWNER);
    double replayPay;

    /** A stage, created on first mention. The first one declared is the start. */
    public Stage stage(String id) { return stages.computeIfAbsent(id, Stage::new); }

    public RuleSet rules() { return rules; }

    /** Where it starts: a player walking into this trigger zone ({@code GameplayEvent.ZoneEntered}) is OFFERED the
     *  activity and starts it by accepting (never by walking in) -- or, when it is already running and
     *  {@link #closed} was not said, joins it as ASSIST. */
    public Plan startsOnZone(String zoneId) { startZone = zoneId == null ? "" : zoneId; return this; }

    /** The story characters it is about: what happens to them in a REPLAY is sandboxed with it. */
    public Plan cast(String... storyIds) { cast.addAll(List.of(storyIds)); return this; }

    /** A faction relationship for the activity's duration (removed at its end, whatever the end). */
    public Plan relation(String a, String b, String relationship) {
        relations.add(new Relation(a, b, relationship));
        return this;
    }

    public Plan maxParticipants(int n) { maxParticipants = Math.max(1, n); return this; }

    /** Nobody may join after the start (default: anyone in the session may ASSIST). */
    public Plan closed() { open = false; return this; }

    /**
     * It puts these roles (default: the OWNER) in a TEMPORARY career while it runs -- "undercover as a police
     * officer" (CR2). {@code real} false: strikes earned under it go to a scratch record that is discarded at the
     * end; true: they land on the career's real record.
     */
    public Plan temporaryCareer(String career, boolean real, Activity.Role... roles) {
        tempCareer = career == null ? "" : career;
        tempReal = real;
        if (roles.length > 0) tempRoles = EnumSet.copyOf(List.of(roles));
        return this;
    }

    /** A REPLAY pays this share of the reward (default 0: nothing). */
    public Plan replayPay(double share) { replayPay = Math.max(0, share); return this; }

    /**
     * The world a REPLAY needs -- the world as it was for this mission ("the boss alive"). Only WORLD requirements
     * ({@code Requirement.storyAlive}, a WORLD flag). A replay is offered only where each one holds, or where the
     * host can stage it as a temporary overlay ({@link ActivityHost#canStage}); the ledger is never rolled back.
     */
    public Plan replayWorld(Requirement... needs) { replayWorld.addAll(List.of(needs)); return this; }

    public List<String> stageIds() { return new ArrayList<>(stages.keySet()); }
    public Set<String> castIds() { return new LinkedHashSet<>(cast); }
    public String startZone() { return startZone; }
    public List<Requirement> replayWorldNeeds() { return List.copyOf(replayWorld); }
    public String temporaryCareer() { return tempCareer; }
}
