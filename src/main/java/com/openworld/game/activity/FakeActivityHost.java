package com.openworld.game.activity;

import com.openworld.game.campaign.CampaignWrite;
import com.openworld.game.campaign.FlagKey;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.campaign.SimCampaign;
import com.openworld.game.event.Spot;
import com.openworld.game.profile.CareerState;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * A world in memory for running activities without the engine (PLAN.md 2.1 / CR6, tier 1 of the mission test kit):
 * players and story characters are rows a test sets, the clock moves when the test says, and everything an activity
 * asked of the world is written down ({@link #said}, {@link #commands}, {@link #paid}, {@link #log}).
 *
 * <pre>
 *   FakeActivityHost w = new FakeActivityHost();
 *   w.player("p1").owner = true;
 *   w.character("m01_boss");
 *   ActivityDirector d = new ActivityDirector(graph, w);
 *   d.start("m01_konbini", "p1", Activity.Mode.STORY);
 *   w.character("m01_boss").health = 0.3;
 *   w.run(d, 1.0);                       // one second of steps
 * </pre>
 *
 * Every player has their own story; they all stand in ONE world ({@link #world}), as in a co-op session.
 */
public final class FakeActivityHost implements ActivityHost {

    public static final class FakePlayer {
        public boolean present = true, down, ownsWorld;
        public Spot at = Spot.NOWHERE;
        /** Their personal story (its world half is unused: {@link FakeActivityHost#world} is the world). */
        public final SimCampaign story = new SimCampaign();
        public final CareerState career = new CareerState();
        public ActivityCheckpoint checkpoint;
        public int storyCheckpoints;
        public long paid;
    }

    public static final class FakeCharacter {
        public boolean present = true, alive = true;
        public double health = 1.0;
        public Spot at = Spot.NOWHERE;
        public String faction = "neutral";
        /** The scripted state it was last put in, "" when its own AI has it. */
        public String commanded = "";
    }

    public final Map<String, FakePlayer> players = new LinkedHashMap<>();
    public final Map<String, FakeCharacter> characters = new LinkedHashMap<>();
    /** The one world everyone is in: world flags, dead story characters, place overrides. */
    public final SimCampaign world = new SimCampaign();
    public final Map<String, Spot> anchors = new LinkedHashMap<>();
    public final Map<String, Long> rewards = new LinkedHashMap<>();
    public final Set<String> consents = new LinkedHashSet<>();
    /** World requirements this world can stage for a replay (by their toString). */
    public final Set<String> stageable = new LinkedHashSet<>();
    /** Locked doors standing near each anchor. */
    public int lockedDoors;

    public final Map<String, Integer> doorsHeld = new LinkedHashMap<>();
    public final Map<String, List<Plan.Relation>> relations = new LinkedHashMap<>();
    public final Map<String, List<Requirement>> staged = new LinkedHashMap<>();
    public final Map<String, String> marks = new LinkedHashMap<>();
    /** "activity<player" for every offer made and not yet taken by the test. */
    public final List<String> offers = new ArrayList<>();
    public final List<String> said = new ArrayList<>(), commands = new ArrayList<>(), log = new ArrayList<>(),
            released = new ArrayList<>();
    public double now;

    public FakePlayer player(String id) { return players.computeIfAbsent(id, k -> new FakePlayer()); }

    public FakeCharacter character(String id) { return characters.computeIfAbsent(id, k -> new FakeCharacter()); }

    /** Step {@code director} through {@code seconds} of time, 60 steps a second. */
    public void run(ActivityDirector director, double seconds) {
        int steps = (int) Math.round(seconds * 60);
        for (int i = 0; i < steps; i++) {
            now += 1.0 / 60;
            director.tick(1.0 / 60);
        }
    }

    /** One player's story over the shared world. */
    private final class Seat implements CampaignWrite {
        private final SimCampaign mine;
        Seat(SimCampaign mine) { this.mine = mine; }
        private SimCampaign of(FlagKey key) { return key.scope() == FlagKey.Scope.WORLD ? world : mine; }
        @Override public String flag(FlagKey key) { return of(key).flag(key); }
        @Override public boolean achieved(String activity, String variant) { return mine.achieved(activity, variant); }
        @Override public String phase() { return mine.phase(); }
        @Override public boolean endingSeen(String ending) { return mine.endingSeen(ending); }
        @Override public boolean hasCareer(String career) { return mine.hasCareer(career); }
        @Override public long balance() { return mine.balance(); }
        @Override public boolean storyDead(String storyId) { return world.storyDead(storyId); }
        @Override public boolean stickyUnlocked(String activity) { return mine.stickyUnlocked(activity); }
        @Override public void setFlag(FlagKey key, String value) { of(key).setFlag(key, value); }
        @Override public void achieve(String activity, String variant) { mine.achieve(activity, variant); }
        @Override public void ending(String ending) { mine.ending(ending); }
        @Override public void chapter(String chapter) { mine.chapter(chapter); }
        @Override public void markStoryDead(String storyId) { world.markStoryDead(storyId); }
        @Override public void setPlace(String placeId, String owner, String state) { world.setPlace(placeId, owner, state); }
        @Override public void unlockSticky(String activity) { mine.unlockSticky(activity); }
    }

    private FakePlayer p(String id) { return players.get(id); }
    private FakeCharacter c(String id) { return characters.get(id); }

    @Override public boolean playerPresent(String id) { return p(id) != null && p(id).present; }
    @Override public boolean playerDown(String id) { return p(id) == null || p(id).down; }
    @Override public Spot playerAt(String id) { return p(id) == null ? Spot.NOWHERE : p(id).at; }
    @Override public boolean ownsWorld(String id) { return p(id) != null && p(id).ownsWorld; }
    @Override public boolean worldConsent(String activityId, String guestId) { return consents.contains(activityId + "<" + guestId); }
    @Override public CampaignWrite story(String id) { return p(id) == null ? null : new Seat(p(id).story); }
    @Override public CareerState career(String id) { return p(id) == null ? null : p(id).career; }
    @Override public void storyCheckpoint(String id) { if (p(id) != null) p(id).storyCheckpoints++; }
    @Override public void keepCheckpoint(String id, ActivityCheckpoint cp) { if (p(id) != null) p(id).checkpoint = cp; }
    @Override public ActivityCheckpoint keptCheckpoint(String id) { return p(id) == null ? null : p(id).checkpoint; }

    @Override public boolean present(String id) { return c(id) != null && c(id).present; }
    @Override public boolean alive(String id) { return present(id) && c(id).alive; }
    @Override public double healthFraction(String id) { return present(id) ? c(id).health : 0; }
    @Override public Spot at(String id) { return c(id) == null ? Spot.NOWHERE : c(id).at; }
    @Override public String faction(String id) { return present(id) ? c(id).faction : ""; }
    @Override public void setFaction(String id, String faction) { if (present(id)) c(id).faction = faction; }

    @Override public void command(String id, String state) {
        if (present(id)) c(id).commanded = state;
        commands.add(id + " " + state);
    }

    @Override public void uncommand(String id) {
        if (present(id)) c(id).commanded = "";
        commands.add(id + " released");
    }

    @Override public Spot anchor(String activityId) { return anchors.getOrDefault(activityId, Spot.NOWHERE); }
    @Override public void configure(String activityId, Activity activity) { }

    @Override public int unlockDoors(String instanceId, Spot at, double radius) {
        int n = lockedDoors;
        lockedDoors = 0;
        doorsHeld.merge(instanceId, n, Integer::sum);
        return n;
    }

    @Override public void relations(String instanceId, List<Plan.Relation> rows) { relations.put(instanceId, rows); }
    @Override public boolean canStage(Requirement need) { return stageable.contains(need.toString()); }
    @Override public void stage(String instanceId, List<Requirement> needs) { staged.put(instanceId, needs); }

    @Override public void release(String instanceId) {
        lockedDoors += doorsHeld.getOrDefault(instanceId, 0);
        doorsHeld.remove(instanceId);
        relations.remove(instanceId);
        staged.remove(instanceId);
        marks.remove(instanceId);
        released.add(instanceId);
    }

    @Override public void offer(String activityId, String playerId) { offers.add(activityId + "<" + playerId); }

    @Override public void say(String instanceId, String speaker, String line) { said.add(speaker + ": " + line); }

    @Override public void mark(String instanceId, String what) {
        if (what == null || what.isEmpty()) marks.remove(instanceId);
        else marks.put(instanceId, what);
    }

    @Override public long reward(String activityId) { return rewards.getOrDefault(activityId, 0L); }
    @Override public void pay(String id, long dollars) { if (p(id) != null) p(id).paid += dollars; }
    @Override public void log(String line) { log.add(line); }
}
