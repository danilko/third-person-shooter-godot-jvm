package com.openworld.game.activity;

import com.openworld.character.AICharacter;
import com.openworld.character.FactionManager;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.WorldLedger;
import com.openworld.game.campaign.ActivityDef;
import com.openworld.game.campaign.CampaignGraph;
import com.openworld.game.campaign.CampaignWrite;
import com.openworld.game.campaign.LiveCampaign;
import com.openworld.game.campaign.Requirement;
import com.openworld.game.campaign.content.CampaignModules;
import com.openworld.game.event.Actors;
import com.openworld.game.event.GameplayEvents;
import com.openworld.game.event.Spot;
import com.openworld.game.mission.MissionDirector;
import com.openworld.game.profile.CareerState;
import com.openworld.game.profile.Economy;
import com.openworld.game.profile.EconomyTable;
import com.openworld.game.profile.PlayerProfile;
import com.openworld.game.profile.Profiles;
import com.openworld.net.NetworkManager;
import com.openworld.world.Breakable;
import com.openworld.world.Door;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.StringName;
import godot.global.GD;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The ENGINE side of the activity framework (PLAN.md 2.1 / AR1), an AutoLoad: it owns the one
 * {@link ActivityDirector}, steps it, feeds it the gameplay events ({@code Phase.ACTIVITY}), and is its
 * {@link ActivityHost} over the live world -- players are {@code PlayerRegistry} bodies and their {@code Profiles},
 * story characters are {@code MissionDirector}'s named registry, the world is the {@code WorldLedger}, an activity's
 * place is the {@link ActivityPlacement} node that registered for it.
 *
 * <p><b>Authority only.</b> Activities run where consequences are decided: single player, or the co-op host. A
 * client runs none; it learns of a start / an end through the mission world events (the same three the old mission
 * slot used -- no new event ints; AR5 replaces them with the replicated state channel) and gets its own result
 * through its profile, which the host changes and sends back.
 *
 * <p><b>What the rest of the game hears.</b> {@code EventBus.missionStarted / missionCompleted / missionFailed} are
 * emitted for an activity as they were for a mission, so the HUD banner and the autosave need no second path. The
 * CAMPAIGN is no longer advanced from them: who is credited is each participant's {@link ActivityResult}.
 */
@Script(className = "ActivityRuntime")
public class ActivityRuntime extends Node implements ActivityHost, ActivityDirector.Listener, com.openworld.control.Interactable {

    /** What a mission world event's objective-type argument says for an activity. */
    public static final String KIND = "ACTIVITY";

    private static ActivityRuntime instance;

    public static ActivityRuntime get() { return instance; }

    private ActivityDirector director;
    private final Map<String, Node3D> placements = new LinkedHashMap<>();
    private final Map<String, List<Door>> doors = new LinkedHashMap<>();
    /** The encounters each run set off (taken away at its release, PLAN.md 2.2). */
    private final Map<String, List<String>> encounters = new LinkedHashMap<>();
    private final Map<String, String> marks = new LinkedHashMap<>();
    private final Set<String> consents = new LinkedHashSet<>();
    private final List<ActivityResult> lastResults = new ArrayList<>();
    private String lastSaid = "";

    // the offer: the activity whose start zone this machine's player stands in, shown as an interact prompt
    private String offered = "";
    /** Past this from the activity's placement the offer is withdrawn (the start zones are smaller than this). */
    private static final double OFFER_RADIUS = 18.0;

    // the objective: what this machine's player is told to do now, by the run they take part in
    private godot.api.CanvasLayer objectiveLayer;
    private godot.api.Label objectiveLabel;
    private String objectiveRun = "", objectiveText = "";
    private double objectiveAge;
    /** Bright for this long after it changes, then dimmed (not hidden: "hard to see the objective", user 2026-10-10). */
    private static final double OBJECTIVE_BRIGHT_SECONDS = 8.0;
    private static final float OBJECTIVE_DIM = 0.6f;

    /** run -> the marker floating over what it marked. */
    private final Map<String, Node3D> markerNodes = new LinkedHashMap<>();
    private double housekeepingIn = 1.0;
    private com.openworld.game.campaign.GameOverWatch gameOver;
    private String lastGameOver = "";

    @Register
    @Override
    public void _ready() {
        instance = this;
        director = new ActivityDirector(CampaignModules.graph(), this);
        director.addListener(this);
        gameOver = new com.openworld.game.campaign.GameOverWatch(CampaignModules.graph().gameOverRules());
        GameplayEvents.subscribe(GameplayEvents.Phase.ACTIVITY, director);
    }

    @Register
    @Override
    public void _exitTree() {
        if (director != null) GameplayEvents.unsubscribe(director);
        placements.clear();
        doors.clear();
        marks.clear();
        markerNodes.clear();
        if (instance == this) instance = null;
    }

    public ActivityDirector director() { return director; }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n) || !n.isNetworked() || n.isServer();
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        if (director == null) return;
        tickOffer();
        tickObjective(delta);
        tickResult(delta);
        if (!authority()) {
            // this machine joined someone else's world: nothing of its own goes on running
            if (!director.running().isEmpty()) director.abortAll("joined a session");
            return;
        }
        director.tick(delta);
        if ((housekeepingIn -= delta) <= 0) {
            housekeepingIn = 1.0;
            reconcileCareers();
            judgeGameOvers(1.0);
        }
    }

    /**
     * CR4, on the authority, once a second: every player in the session against the campaign's game-over rules. A
     * warning is told by the world (a caller's line on the radio feed); a game over has already rolled that player's
     * PROFILE back to its campaign checkpoint when it is reported here -- the host's copy, which travels back to its
     * owner like any other change. The card and the respawn at the safe house come with the first authored rule
     * (PLAN.md 2.1 LEFT): no module declares one yet, so nothing fires in play.
     */
    private void judgeGameOvers(double dt) {
        if (gameOver.rules().isEmpty()) return;
        Map<String, PlayerProfile> players = new LinkedHashMap<>();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p == null || !GD.isInstanceValid(p) || p.getCharacterInfo() == null) continue;
            PlayerProfile prof = Profiles.of(p);
            if (prof != null) players.put(p.getCharacterInfo().characterId, prof);
        }
        for (com.openworld.game.campaign.GameOverWatch.Notice n : gameOver.step(dt, players, this::story)) {
            switch (n.kind()) {
                case WARNED -> {
                    if (!n.rule().warning().isEmpty() && getNodeOrNull("/root/EventBus") instanceof EventBus bus)
                        bus.radioChatter.emit(n.rule().warning());
                }
                case GAME_OVER -> {
                    lastGameOver = n.playerId() + " " + n.rule().id();
                    director.failFor(n.playerId(), "game_over");
                    GD.print("[Activity] GAME OVER for " + n.playerId() + " (" + n.rule().id() + "): their profile is back at its checkpoint");
                }
                default -> { }
            }
        }
    }

    /** "playerId ruleId" of the last game over, "" when there was none -- probe readout. */
    @Register
    public String lastGameOverNow() { return lastGameOver; }

    /** CR2: a temporary career whose activity is not running (a crash, a disconnect, a save taken mid-mission)
     *  goes. Only the authority decides: a client's journal is the host's copy of it. */
    private void reconcileCareers() {
        reconcile(Profiles.local());
        for (PlayerProfile p : Profiles.remotes().values()) reconcile(p);
    }

    private void reconcile(PlayerProfile p) {
        if (p == null || p.career.overrideJournal.isEmpty()) return;
        if (p.career.reconcile(director::isRunning) > 0) p.touch();
    }

    // ── the offer: a mission is started deliberately, never by walking in ──

    @Override public void offer(String activityId, String playerId) {
        Player p = player(playerId);
        if (p == null) return;
        if (!p.isLocallyOwnedPlayer()) {
            // a co-op guest's prompt and interact key are not on the wire yet (MSG_INTERACT, PLAN.md 3.0): until
            // they are, a guest who MAY start it (the consent rule already said so) starts it by walking in
            director.accept(activityId, playerId);
            return;
        }
        offered = activityId;
        ActivityDef d = director.graph().activity(activityId);
        String title = d == null || d.title().isEmpty() ? activityId : d.title();
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) bus.interactPrompt(this, true, "Start: " + title + " (E)");
    }

    private void withdrawOffer() {
        if (offered.isEmpty()) return;
        offered = "";
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) bus.interactPrompt(this, false, "");
    }

    private void tickOffer() {
        if (offered.isEmpty()) return;
        Player me = player(localId());
        Node3D at = placements.get(offered);
        boolean near = me != null && me.isAlive() && at != null && GD.isInstanceValid(at) && at.isInsideTree()
                && me.getGlobalPosition().distanceTo(at.getGlobalPosition()) <= OFFER_RADIUS;
        if (!near || isRunning(offered) || !director.whyNot(offered, localId(), Activity.Mode.STORY).isEmpty()) withdrawOffer();
    }

    /** The interact key on the offer's prompt (control.Interactions): the player takes the mission. */
    @Override public void interact(com.openworld.character.Character actor) {
        if (offered.isEmpty() || actor == null || actor.getCharacterInfo() == null || !authority()) return;
        String id = offered;
        withdrawOffer();
        ActivityDirector.Start s = director.accept(id, actor.getCharacterInfo().characterId);
        if (!s.ok()) log("'" + id + "' not started: " + s.refusal());
    }

    // ── the objective line and the marker ──

    private void showObjective(String instanceId, String text) {
        objectiveRun = instanceId;
        objectiveText = text;
        objectiveAge = 0;
        if (objectiveLabel == null) {
            objectiveLayer = new godot.api.CanvasLayer();
            objectiveLayer.setLayer(40);
            objectiveLabel = new godot.api.Label();
            objectiveLabel.setAnchorsPreset(godot.api.Control.LayoutPreset.PRESET_CENTER_TOP, false);
            objectiveLabel.setOffset(godot.core.Side.LEFT, -560f);
            objectiveLabel.setOffset(godot.core.Side.RIGHT, 560f);
            objectiveLabel.setOffset(godot.core.Side.TOP, 84f);
            objectiveLabel.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
            objectiveLabel.setMouseFilter(godot.api.Control.MouseFilter.IGNORE);
            objectiveLabel.addThemeFontSizeOverride(new StringName("font_size"), 30);
            objectiveLabel.addThemeColorOverride(new StringName("font_color"), new godot.core.Color(1.0, 0.86, 0.3, 1.0));
            objectiveLabel.addThemeColorOverride(new StringName("font_outline_color"), new godot.core.Color(0, 0, 0, 1));
            objectiveLabel.addThemeConstantOverride(new StringName("outline_size"), 8);
            objectiveLayer.addChild(objectiveLabel);
            addChild(objectiveLayer);
        }
        objectiveLabel.setText(text);
        objectiveLabel.setVisible(!text.isEmpty());
        objectiveLabel.setModulate(new godot.core.Color(1, 1, 1, 1));
    }

    private void tickObjective(double delta) {
        if (objectiveLabel == null || objectiveText.isEmpty()) return;
        objectiveAge += delta;
        double fade = Math.min(1.0, Math.max(0.0, objectiveAge - OBJECTIVE_BRIGHT_SECONDS));   // 1 s to dim
        objectiveLabel.setModulate(new godot.core.Color(1, 1, 1, (float) (1.0 - (1.0 - OBJECTIVE_DIM) * fade)));
    }

    private boolean localTakesPart(String instanceId) {
        String me = localId();
        for (ActivityInstance a : director.running()) if (a.instanceId().equals(instanceId)) return a.isParticipant(me);
        return false;
    }

    private void clearMarker(String instanceId) {
        Node3D m = markerNodes.remove(instanceId);
        if (m != null && GD.isInstanceValid(m)) m.queueFree();
    }

    /** A downward arrow floating over a story character, seen through walls: WHO the objective is about. */
    private void showMarker(String instanceId, AICharacter on) {
        godot.api.Label3D l = new godot.api.Label3D();
        l.setText("▼");
        l.setFontSize(96);
        l.setPixelSize(0.004f);
        l.setBillboardMode(godot.api.BaseMaterial3D.BillboardMode.ENABLED);
        l.setDrawFlag(godot.api.Label3D.DrawFlags.FLAG_DISABLE_DEPTH_TEST, true);
        l.setDrawFlag(godot.api.Label3D.DrawFlags.FLAG_FIXED_SIZE, false);
        l.setModulate(new godot.core.Color(1.0, 0.86, 0.3, 1.0));
        l.setOutlineSize(16);
        l.setCastShadowsSetting(godot.api.GeometryInstance3D.ShadowCastingSetting.OFF);
        l.setPosition(new godot.core.Vector3(0, 2.35, 0));
        on.addChild(l);
        markerNodes.put(instanceId, l);
    }

    // ── placements ──

    /** A placement node registers in {@code _ready} (a Node3D implementing {@link ActivityPlacement}). */
    public void place(Node3D node) {
        if (node instanceof ActivityPlacement p && !p.placedActivityId().isEmpty()) placements.put(p.placedActivityId(), node);
    }

    public void unplace(Node3D node) { placements.values().removeIf(n -> n == node); }

    /** For the MAP (ui.RoadOverlay): mission title -> where its placement stands, for every placed mission the local
     *  player can start now or that is running. A finished one (not replayable now) is off the map. */
    public Map<String, godot.core.Vector3> missionSpots() {
        Map<String, godot.core.Vector3> out = new LinkedHashMap<>();
        if (director == null) return out;
        for (Map.Entry<String, Node3D> e : placements.entrySet()) {
            Node3D n = e.getValue();
            if (n == null || !GD.isInstanceValid(n) || !n.isInsideTree()) continue;
            String id = e.getKey();
            if (!isRunning(id) && whyNotNow(id, "start") != null && !whyNotNow(id, "start").isEmpty()) continue;
            ActivityDef d = director.graph().activity(id);
            out.put(d == null || d.title().isEmpty() ? id : d.title(), n.getGlobalPosition());
        }
        return out;
    }

    private ActivityPlacement placement(String activityId) {
        Node3D n = placements.get(activityId);
        return n != null && GD.isInstanceValid(n) && n instanceof ActivityPlacement p ? p : null;
    }

    // ── what the game asks ──

    /** Is this activity running (for anyone)? What {@code ZoneTrigger.requiredMissionId} asks. */
    public boolean isRunning(String activityId) { return director != null && director.runningOf(activityId) != null; }

    /** A player was recovered (hospital, arrest, abduction): the run they own fails (user, 2026-10-03). */
    public void playerRecovered(String playerId, String why) {
        if (director != null && authority()) director.failFor(playerId, why);
    }

    /** The host said yes, once, to a guest running a world-altering activity here (the co-op model's rule 6). */
    public void grantWorldConsent(String activityId, String guestId) { consents.add(activityId + "<" + guestId); }

    /** This machine's own story with the world it is in. */
    public CampaignWrite localStory() { return new LiveCampaign(Profiles.local(), WorldLedger.get()); }

    /** Host -> one joining peer: every activity already running, as the mission world event a live start sends. */
    public void sendBaseline(int peerId) {
        if (director == null || !authority()) return;
        if (!(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net)) return;
        for (ActivityInstance a : director.running())
            net.sendWorldEventTo(peerId, GameManager.WORLD_EVENT_MISSION_STARTED, a.activityId(), 0f, List.of(KIND, ""));
    }

    // ── ActivityDirector.Listener: tell the rest of the game ──

    @Override public void started(ActivityInstance a) {
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) bus.missionStarted.emit(a.activityId(), KIND);
        broadcast(GameManager.WORLD_EVENT_MISSION_STARTED, a.activityId(), List.of(KIND, ""));
    }

    @Override public void stage(ActivityInstance a) {
        ActivityPlacement p = placement(a.activityId());
        if (p != null) p.stageEntered(a.stageId());
    }

    @Override public void ended(ActivityInstance a, List<ActivityResult> results) {
        lastResults.clear();
        lastResults.addAll(results);
        if (a.instanceId().equals(objectiveRun)) showObjective("", "");
        ActivityPlacement p = placement(a.activityId());
        if (p != null) p.ended(a.outcome(), a.variant(), a.reason());
        EventBus bus = getNodeOrNull("/root/EventBus") instanceof EventBus b ? b : null;
        announceResult(a, results, bus);
        if (a.outcome() == ActivityInstance.Outcome.COMPLETED) {
            if (bus != null) bus.missionCompleted.emit(a.activityId(), "player", a.variant());
            broadcast(GameManager.WORLD_EVENT_MISSION_COMPLETED, a.activityId(), List.of("player", a.variant()));
        } else {
            if (bus != null) bus.missionFailed.emit(a.activityId(), a.reason());
            broadcast(GameManager.WORLD_EVENT_MISSION_FAILED, a.activityId(), List.of(a.reason()));
        }
    }

    // ── "is it over?" (user, 2026-10-11: "hard to know if the mission is complete or not") ──

    private godot.api.Label resultLabel;
    private double resultLeft;
    private String resultText = "";
    static final double RESULT_SECONDS = 7.0;

    /** A banner where the objective was, and a line in the status feed: COMPLETE with what was paid, or FAILED with
     *  why. Shown to this machine's player when they took part; the pause menu's MISSIONS tab keeps the record. */
    private void announceResult(ActivityInstance a, List<ActivityResult> results, EventBus bus) {
        ActivityResult mine = null;
        for (ActivityResult r : results) if (r.playerId().equals(localId())) mine = r;
        if (mine == null) return;
        ActivityDef d = director.graph().activity(a.activityId());
        String title = d == null || d.title().isEmpty() ? a.activityId() : d.title();
        boolean won = a.outcome() == ActivityInstance.Outcome.COMPLETED;
        String text = won ? "MISSION COMPLETE -- " + title + (mine.pay() > 0 ? String.format("   +$%,d", mine.pay()) : "")
                : "MISSION FAILED -- " + title + (a.reason() == null || a.reason().isEmpty() ? "" : " (" + a.reason() + ")");
        resultText = text;
        if (resultLabel == null) {
            godot.api.CanvasLayer layer = new godot.api.CanvasLayer();
            layer.setLayer(41);
            resultLabel = new godot.api.Label();
            resultLabel.setAnchorsPreset(godot.api.Control.LayoutPreset.PRESET_CENTER_TOP, false);
            resultLabel.setOffset(godot.core.Side.LEFT, -700f);
            resultLabel.setOffset(godot.core.Side.RIGHT, 700f);
            resultLabel.setOffset(godot.core.Side.TOP, 130f);
            resultLabel.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
            resultLabel.setMouseFilter(godot.api.Control.MouseFilter.IGNORE);
            resultLabel.addThemeFontSizeOverride(new StringName("font_size"), 40);
            resultLabel.addThemeColorOverride(new StringName("font_outline_color"), new godot.core.Color(0, 0, 0, 1));
            resultLabel.addThemeConstantOverride(new StringName("outline_size"), 10);
            layer.addChild(resultLabel);
            addChild(layer);
        }
        resultLabel.setText(text);
        resultLabel.addThemeColorOverride(new StringName("font_color"),
                won ? new godot.core.Color(0.45, 1.0, 0.55, 1.0) : new godot.core.Color(1.0, 0.4, 0.35, 1.0));
        resultLabel.setModulate(new godot.core.Color(1, 1, 1, 1));
        resultLabel.setVisible(true);
        resultLeft = RESULT_SECONDS;
        if (bus != null) bus.radioChatter.emit(text);
    }

    private void tickResult(double delta) {
        if (resultLabel == null || resultLeft <= 0) return;
        resultLeft -= delta;
        if (resultLeft <= 0) resultLabel.setVisible(false);
        else if (resultLeft < 1.0) resultLabel.setModulate(new godot.core.Color(1, 1, 1, resultLeft));
    }

    /** Probe readout: the banner's text while it is up, else "". */
    @Register public String resultBannerNow() { return resultLabel != null && resultLabel.isVisible() ? resultText : ""; }

    /**
     * THE MISSION LOG for the pause menu's MISSIONS tab: one row {title, status, detail} per mission of the campaign
     * graph, for this machine's player -- IN PROGRESS (its objective), COMPLETED (how it ended), AVAILABLE (where),
     * LOCKED (why not).
     */
    public List<String[]> missionLog() {
        List<String[]> out = new ArrayList<>();
        if (director == null) return out;
        CampaignWrite story = localStory();
        for (ActivityDef d : director.graph().activities()) {
            String id = d.id;
            String title = d.title().isEmpty() ? id : d.title();
            ActivityInstance run = director.runningOf(id);
            if (run != null) {
                out.add(new String[]{title, "IN PROGRESS", objectiveText.isEmpty() ? run.stageId() : objectiveText});
            } else if (story.achieved(id, "")) {
                String how = "";
                for (String v : d.variants()) if (story.achieved(id, v)) how = v;
                out.add(new String[]{title, "COMPLETED", how.replace('_', ' ').toLowerCase(java.util.Locale.ROOT)});
            } else {
                String why = director.whyNot(id, localId(), Activity.Mode.STORY);
                boolean placed = placement(id) != null;
                if (why.isEmpty()) out.add(new String[]{title, "AVAILABLE", placed ? "marked M on the map" : "not placed in this world yet"});
                else out.add(new String[]{title, "LOCKED", why});
            }
        }
        return out;
    }

    /** {@link #missionLog} for a probe: "title|status|detail;...". */
    @Register public String missionLogNow() {
        List<String> rows = new ArrayList<>();
        for (String[] r : missionLog()) rows.add(String.join("|", r));
        return String.join(";", rows);
    }

    private void broadcast(int event, String activityId, List<String> args) {
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) net.broadcastWorldEvent(event, activityId, 0f, args);
    }

    // ── ActivityHost: players ──

    private static Player player(String id) {
        if (id == null || id.isEmpty()) return null;
        for (Player p : PlayerRegistry.getPlayers())
            if (p != null && GD.isInstanceValid(p) && p.getCharacterInfo() != null && id.equals(p.getCharacterInfo().characterId)) return p;
        return null;
    }

    private static PlayerProfile profile(String id) { return Profiles.of(player(id)); }

    @Override public boolean playerPresent(String id) { return player(id) != null; }

    @Override public boolean playerDown(String id) {
        Player p = player(id);
        return p == null || !p.isAlive();
    }

    @Override public Spot playerAt(String id) {
        Player p = player(id);
        return p == null ? Spot.NOWHERE : Actors.at(p.getGlobalPosition());
    }

    @Override public boolean ownsWorld(String id) {
        Player p = player(id);
        return p != null && p.isLocallyOwnedPlayer();
    }

    @Override public boolean worldConsent(String activityId, String guestId) { return consents.contains(activityId + "<" + guestId); }

    @Override public CampaignWrite story(String id) {
        PlayerProfile p = profile(id);
        return p == null ? null : new LiveCampaign(p, WorldLedger.get());
    }

    @Override public CareerState career(String id) {
        PlayerProfile p = profile(id);
        if (p != null) p.touch();   // whoever asks is about to push, pop or count
        return p == null ? null : p.career;
    }

    @Override public void storyCheckpoint(String id) {
        PlayerProfile p = profile(id);
        // never in a state a game-over rule holds in: a game over must not land the player in another one
        if (p != null && gameOver.mayCheckpoint(p, new LiveCampaign(p, WorldLedger.get()))) p.takeCheckpoint();
    }

    @Override public void keepCheckpoint(String id, ActivityCheckpoint cp) {
        PlayerProfile p = profile(id);
        if (p == null || (cp == null && p.activityCheckpoint == null)) return;
        p.activityCheckpoint = cp == null ? null : cp.toMap();
        p.touch();
    }

    @Override public ActivityCheckpoint keptCheckpoint(String id) {
        PlayerProfile p = profile(id);
        return p == null ? null : ActivityCheckpoint.fromMap(p.activityCheckpoint);
    }

    // ── ActivityHost: story characters ──

    private static AICharacter named(String id) {
        MissionDirector d = MissionDirector.get();
        AICharacter ai = d == null ? null : d.getNamedCharacter(id);
        return ai != null && GD.isInstanceValid(ai) ? ai : null;
    }

    @Override public boolean present(String id) { return named(id) != null; }

    @Override public boolean alive(String id) {
        AICharacter ai = named(id);
        return ai != null && !ai.isDead() && ai.isAlive();
    }

    @Override public double healthFraction(String id) {
        AICharacter ai = named(id);
        if (ai == null) return 0;
        return ai.getNodeOrNull("Health") instanceof Health h && h.maxHealth > 0 ? h.getCurrentHealth() / h.maxHealth : 0;
    }

    @Override public Spot at(String id) {
        AICharacter ai = named(id);
        return ai == null ? Spot.NOWHERE : Actors.at(ai.getGlobalPosition());
    }

    @Override public String faction(String id) {
        AICharacter ai = named(id);
        return ai == null || ai.getCharacterInfo() == null ? "" : ai.getCharacterInfo().faction;
    }

    @Override public void setFaction(String id, String faction) {
        AICharacter ai = named(id);
        if (ai != null) ai.setFaction(faction);
    }

    @Override public void command(String id, String state) {
        MissionDirector d = MissionDirector.get();
        if (d != null) d.commandState(id, state);
    }

    @Override public void uncommand(String id) {
        MissionDirector d = MissionDirector.get();
        if (d != null) d.releaseCharacter(id);
    }

    // ── ActivityHost: the place ──

    @Override public Spot anchor(String activityId) {
        Node3D n = placements.get(activityId);
        return n != null && GD.isInstanceValid(n) && n.isInsideTree() ? Actors.at(n.getGlobalPosition()) : Spot.NOWHERE;
    }

    @Override public void configure(String activityId, Activity activity) {
        ActivityPlacement p = placement(activityId);
        if (p != null) p.configure(activity);
    }

    /**
     * Doors are in {@code Breakable.BREAKABLE_GROUP}, so this is a group read, not a tree walk. Only a LOCKED door:
     * a shop (or the player's home base) that is already open stays open -- it is not the activity's to shut when
     * the run ends. A door that has streamed out by then is simply gone from the list.
     */
    @Override public int unlockDoors(String instanceId, Spot at, double radius) {
        if (getTree() == null || at == Spot.NOWHERE) return 0;
        godot.core.Vector3 centre = Actors.vec(at);
        List<Door> held = doors.computeIfAbsent(instanceId, k -> new ArrayList<>());
        int n = 0;
        for (Node node : getTree().getNodesInGroup(new StringName(Breakable.BREAKABLE_GROUP))) {
            if (node instanceof Door door && door.isLocked() && door.getGlobalPosition().distanceTo(centre) <= radius) {
                door.setLocked(false);
                held.add(door);
                n++;
            }
        }
        return n;
    }

    /** The run's enforcement hooks (P1e step 5): registered for the wanted level and the dispatch to read, its
     *  reserved bodies taken from the stations nearest its anchor, its incidents raised there. */
    @Override public void enforcement(String instanceId, String activityId, Plan.Enforcement hooks) {
        com.openworld.game.EnforcementHooks.participant = (inst, pid) -> {
            ActivityInstance a = director == null ? null : director.of(pid);
            return a != null && a.instanceId.equals(inst);
        };
        com.openworld.game.EnforcementHooks.register(instanceId, hooks);
        com.openworld.game.EnforcementDispatch ed = com.openworld.game.EnforcementDispatch.get();
        Spot at = anchor(activityId);
        if (ed != null) {
            ed.reserveFor(instanceId, hooks.reserves, at == Spot.NOWHERE ? null : Actors.vec(at));
            for (String type : hooks.incidents) ed.raiseIncident(type, at == Spot.NOWHERE ? null : Actors.vec(at), instanceId);
        }
    }

    @Override public void relations(String instanceId, List<Plan.Relation> rows) {
        if (!(getNodeOrNull("/root/FactionManager") instanceof FactionManager fm)) return;
        List<String[]> out = new ArrayList<>();
        for (Plan.Relation r : rows) out.add(new String[]{r.a(), r.b(), r.relationship()});
        fm.setActivityOverlay(instanceId, out);
    }

    /** Staging a replay's world (a dead story character standing again for its duration) needs the streamer to
     *  respawn a named character -- not built (PLAN.md 2.1 LEFT): a replay is offered only where its world holds. */
    @Override public boolean canStage(Requirement need) { return false; }

    @Override public void stage(String instanceId, List<Requirement> needs) { }

    @Override public boolean startEncounter(String instanceId, String encounterId) {
        com.openworld.game.encounter.Encounter e = com.openworld.game.encounter.Encounter.find(this, encounterId);
        if (e == null) return false;
        e.startNow();
        encounters.computeIfAbsent(instanceId, k -> new ArrayList<>()).add(encounterId);
        return true;
    }

    @Override public int encounterLeft(String encounterId) {
        com.openworld.game.encounter.Encounter e = com.openworld.game.encounter.Encounter.find(this, encounterId);
        return e == null ? -1 : e.liveNow() + e.wavesLeftNow();
    }

    @Override public void release(String instanceId) {
        List<String> started = encounters.remove(instanceId);
        if (started != null) for (String id : started) {
            com.openworld.game.encounter.Encounter e = com.openworld.game.encounter.Encounter.find(this, id);
            if (e != null) e.stopNow();
        }
        List<Door> held = doors.remove(instanceId);
        if (held != null) for (Door d : held) if (GD.isInstanceValid(d)) d.setLocked(true);
        if (getNodeOrNull("/root/FactionManager") instanceof FactionManager fm) fm.setActivityOverlay(instanceId, List.of());
        com.openworld.game.EnforcementHooks.release(instanceId);
        if (com.openworld.game.EnforcementDispatch.get() != null) com.openworld.game.EnforcementDispatch.get().releaseReserve(instanceId);
        marks.remove(instanceId);
        clearMarker(instanceId);
    }

    // ── ActivityHost: telling the player, money ──

    /**
     * What to do now. It is the OBJECTIVE LINE at the top of the screen of a participant on this machine -- bright
     * when it changes, dimmed after, there for as long as the run is (the minimal HUD's "a subtitle, then gone" failed
     * the play test: "hard to see the mission objective", user 2026-10-10) -- and, when somebody SPEAKS it, a line of
     * radio chatter in the status feed as well.
     */
    @Override public void say(String instanceId, String speaker, String line) {
        lastSaid = speaker.isEmpty() ? line : speaker + ": " + line;
        if (!speaker.isEmpty() && getNodeOrNull("/root/EventBus") instanceof EventBus bus) bus.radioChatter.emit(lastSaid);
        if (localTakesPart(instanceId)) showObjective(instanceId, line);
    }

    @Override public void mark(String instanceId, String what) {
        clearMarker(instanceId);
        if (what == null || what.isEmpty()) {
            marks.remove(instanceId);
            return;
        }
        marks.put(instanceId, what);
        AICharacter on = named(what);
        if (on != null && localTakesPart(instanceId)) showMarker(instanceId, on);
    }

    @Override public long reward(String activityId) { return EconomyTable.get().missionReward(activityId); }

    @Override public void pay(String id, long dollars) {
        PlayerProfile p = profile(id);
        if (p != null) Economy.transfer(null, p, dollars, Economy.Reason.REWARD);
    }

    @Override public void log(String line) { GD.print("[Activity] " + line); }

    // ── the console and the probes ──

    private static String localId() {
        for (Player p : PlayerRegistry.getPlayers())
            if (p != null && GD.isInstanceValid(p) && p.isLocallyOwnedPlayer() && p.getCharacterInfo() != null)
                return p.getCharacterInfo().characterId;
        return "";
    }

    private static Activity.Mode mode(String m) { return "REPLAY".equalsIgnoreCase(m) ? Activity.Mode.REPLAY : Activity.Mode.STORY; }

    /** Start it for this machine's player ("STORY" / "REPLAY"); "" = started, else why not. */
    @Register
    public String startNow(String activityId, String mode) {
        if (!authority()) return "the host starts activities";
        return director.start(activityId, localId(), mode(mode)).refusal();
    }

    /** Try this machine's player's failed run again from its checkpoint; "" = started. */
    @Register
    public String retryNow() { return authority() ? director.retry(localId()).refusal() : "the host starts activities"; }

    @Register
    public String whyNotNow(String activityId, String mode) { return director.whyNot(activityId, localId(), mode(mode)); }

    @Register
    public void abortNow(String activityId) {
        ActivityInstance a = director.runningOf(activityId);
        if (a != null) director.abort(a.instanceId(), "aborted");
    }

    /** Fail the activity's run as if something outside it had ended it for its owner (an arrest) -- probes. */
    @Register
    public void failNow(String activityId, String why) {
        ActivityInstance a = director.runningOf(activityId);
        if (a != null) director.failFor(a.owner(), why);
    }

    @Register
    public String runningIdsNow() {
        List<String> ids = new ArrayList<>();
        for (ActivityInstance a : director.running()) ids.add(a.activityId());
        return String.join(",", ids);
    }

    @Register
    public boolean runningNow(String activityId) { return isRunning(activityId); }

    @Register
    public String stageNow(String activityId) {
        ActivityInstance a = director.runningOf(activityId);
        return a == null ? "" : a.stageId();
    }

    /** "playerId:ROLE:eligible;..." of the activity's run. */
    @Register
    public String participantsNow(String activityId) {
        ActivityInstance a = director.runningOf(activityId);
        if (a == null) return "";
        List<String> out = new ArrayList<>();
        for (ActivityInstance.Participant p : a.participants()) out.add(p.playerId() + ":" + p.role() + ":" + p.eligible());
        return String.join(";", out);
    }

    @Register
    public int doorsHeldNow(String activityId) {
        ActivityInstance a = director.runningOf(activityId);
        List<Door> held = a == null ? null : doors.get(a.instanceId());
        return held == null ? 0 : held.size();
    }

    @Register
    public String markedNow(String activityId) {
        ActivityInstance a = director.runningOf(activityId);
        return a == null ? "" : marks.getOrDefault(a.instanceId(), "");
    }

    @Register
    public String lastSaidNow() { return lastSaid; }

    /** The activity on offer to this machine's player ("" = none) -- probe readout. */
    @Register
    public String offeredNow() { return offered; }

    /** The objective line as shown ("" = hidden) and how opaque it is -- probe readouts. */
    @Register
    public String objectiveNow() { return objectiveLabel != null && objectiveLabel.isVisible() ? objectiveLabel.getText() : ""; }

    @Register
    public float objectiveAlphaNow() { return objectiveLabel == null ? 0f : (float) objectiveLabel.getModulate().getA(); }

    /** Is a marker floating over this story character? */
    @Register
    public boolean markerOnNow(String characterId) {
        AICharacter ai = named(characterId);
        for (Node3D m : markerNodes.values()) if (GD.isInstanceValid(m) && ai != null && m.getParent() == ai) return true;
        return false;
    }

    /** Take the offer as the interact key on ITS prompt does ({@code Interactions} calls {@link #interact} on the
     *  newest prompt -- which another prompt near the player may be, so a probe calls this one directly). */
    @Register
    public boolean acceptOfferNow() {
        if (offered.isEmpty()) return false;
        interact(player(localId()));
        return true;
    }

    /** The last ended run, one line per participant: "activity outcome variant role credit=.. world=.. pay=.. reason". */
    @Register
    public String lastResultsNow() {
        List<String> out = new ArrayList<>();
        for (ActivityResult r : lastResults)
            out.add(r.activityId() + " " + r.outcome() + " " + r.variant() + " " + r.role() + " " + r.mode() + " credit=" + r.storyCredit()
                    + " world=" + r.worldApplied() + " pay=" + r.pay() + " " + r.reason());
        return String.join("\n", out);
    }

    /** Has this machine's player completed it with this variant ("" = any)? */
    @Register
    public boolean achievedNow(String activityId, String variant) { return localStory().achieved(activityId, variant == null ? "" : variant); }

    /** Does this machine's player meet its requirement in this world (whether or not it is authored yet)? */
    @Register
    public boolean requirementMetNow(String activityId) {
        CampaignGraph g = director.graph();
        ActivityDef d = g.activity(activityId);
        return d != null && d.requirement().test(localStory());
    }

    @Register
    public String effectiveCareerNow() { return Profiles.local().career.effective(); }

    @Register
    public boolean hasStoryCheckpointNow() { return Profiles.local().hasCheckpoint(); }

    @Register
    public String activityCheckpointNow() {
        ActivityCheckpoint cp = ActivityCheckpoint.fromMap(Profiles.local().activityCheckpoint);
        return cp == null ? "" : cp.activityId() + "/" + cp.stageId();
    }
}
