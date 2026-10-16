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
    final Enforcement enforcement = new Enforcement();
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

    // ── ENFORCEMENT HOOKS (PLAN.md P1e step 5): what the police and the gangs do while it runs, DECLARED here like
    //    relation() so ActivityLint sees them and ActivityHost.release undoes every one of them at the end ──

    /**
     * The activity's hold on the enforcement, applied to its PARTICIPANTS while it runs (a player who joins later
     * gets it too) and undone at its end, whatever the end. Every field is "not asked" by default.
     */
    public static final class Enforcement {
        /** Sides that send nobody at the participants (empty + {@link #noDispatchAll} false = all send as usual). */
        public final Set<String> noDispatch = new LinkedHashSet<>();
        public boolean noDispatchAll;
        /** Police stars held within [atLeast, atMost] (-1 = no bound); lock = held where they were at the start. */
        public int wantedAtLeast = -1, wantedAtMost = -1;
        public boolean wantedLock;
        /** Set once at the start (or as a participant joins): stars (-1 = not set), or cleared. */
        public int wantedSet = -1;
        public boolean wantedClear;
        /** Forces that hunt the participants AS IF at these stars while it runs, whatever their record says. */
        public final Map<String, Integer> squads = new LinkedHashMap<>();
        /** Bodies taken from a force's stations nearest the activity's anchor for its duration (its own people). */
        public final Map<String, Integer> reserves = new LinkedHashMap<>();
        /** Incidents it raises at its anchor as it starts (the radio and the AI hear of them). */
        public final List<String> incidents = new ArrayList<>();

        public boolean any() {
            return noDispatchAll || !noDispatch.isEmpty() || wantedAtLeast >= 0 || wantedAtMost >= 0 || wantedLock
                    || wantedSet >= 0 || wantedClear || !squads.isEmpty() || !reserves.isEmpty() || !incidents.isEmpty();
        }
    }

    public Enforcement enforcement() { return enforcement; }

    /** Nobody of these sides ("police", a gang id; none = every side) is dispatched at the participants. */
    public Plan noDispatch(String... sides) {
        if (sides.length == 0) enforcement.noDispatchAll = true;
        else enforcement.noDispatch.addAll(List.of(sides));
        return this;
    }

    /** The participants' police stars stay where they were when the run started (or they joined). */
    public Plan wantedLock() { enforcement.wantedLock = true; return this; }

    /** The participants' police stars never fall below {@code stars} while it runs. */
    public Plan wantedAtLeast(int stars) { enforcement.wantedAtLeast = stars; return this; }

    /** ... and never rise above {@code stars}. */
    public Plan wantedAtMost(int stars) { enforcement.wantedAtMost = stars; return this; }

    /** Set the participants' police stars once, as it starts. */
    public Plan wantedSet(int stars) { enforcement.wantedSet = stars; return this; }

    /** Clear the participants' police stars once, as it starts. */
    public Plan wantedClear() { enforcement.wantedClear = true; return this; }

    /** {@code force} hunts the participants as if at {@code stars} for the run (a gang's hit squad, a police raid). */
    public Plan squad(String force, int stars) { enforcement.squads.put(force, stars); return this; }

    /** {@code n} of {@code force}'s bodies are the activity's own for its duration: taken from the stations nearest
     *  its anchor, so the dispatch has that many fewer there. */
    public Plan reserve(String force, int n) { enforcement.reserves.merge(force, n, Integer::sum); return this; }

    /** Raise an incident of this type at the anchor as it starts (see game.IncidentBoard). */
    public Plan incident(String type) { enforcement.incidents.add(type); return this; }

    public List<String> stageIds() { return new ArrayList<>(stages.keySet()); }
    public Set<String> castIds() { return new LinkedHashSet<>(cast); }
    public String startZone() { return startZone; }
    public List<Requirement> replayWorldNeeds() { return List.copyOf(replayWorld); }
    public String temporaryCareer() { return tempCareer; }
}
