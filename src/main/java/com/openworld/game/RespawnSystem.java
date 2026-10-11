package com.openworld.game;

import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.world.Places;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.CanvasLayer;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * Death and arrest are not game over (PLAN.md W5, user decisions 2026-10-03). Two outcomes, named in Japanese and
 * English and NOT after another game's cards (user: "more Japan flavour, and avoid being too similar"):
 * <ul>
 *   <li><b>入院 HOSPITALIZED</b> -- a death: the player wakes outside the nearest hospital or clinic.</li>
 *   <li><b>逮捕 ARRESTED</b> -- {@link #arrest}: the player is let go outside the nearest police station.</li>
 *   Both on the building's authored respawn points (MARK_respawn, on its forecourt, carried in the places record),
 *   facing the street; the fade-in waits for the world there to stream (PLAN.md 1c, user 2026-10-06: hospital and
 *   police behave the same, outside -- GTA's steps; the interiors stay mission content).
 * </ul>
 * Either way, after {@link #cardSeconds} of the card the body is replaced by a fresh Player (full health, only the
 * fist: weapons are lost; wanted level cleared), and the running mission FAILS (user: "it ends the mission").
 *
 * <p><b>Networked</b> (2026-10-06): the HOST runs the respawn for every player, its own and each client's: after the
 * card time it despawns the dead body and spawns a fresh one with the same characterId and owner through the ordinary
 * {@code MSG_DESPAWN} / {@code MSG_SPAWN}, so the owning client gets its body back the way it got it on joining (with
 * its own PlayerController and camera). A client only shows the card for its own body and fades in when the new body
 * arrives. Built in code by {@link GameManager}; {@link #enabled} off is the control.
 */
@Script(className = "RespawnSystem")
public class RespawnSystem extends Node {

    static final String PLAYER_SCENE = "res://src/main/resources/com/openworld/character/Player.tscn";

    private static RespawnSystem instance;

    public static RespawnSystem get() {
        return instance != null && GD.isInstanceValid(instance) ? instance : null;
    }

    @Visible public boolean enabled = true;

    public boolean getEnabled() { return enabled; }

    public void setEnabled(boolean v) { enabled = v; }

    /** Unseat a body that died in a vehicle before it is freed (PLAN.md 1i). Off = the old defect: the probe's control. */
    @Visible
    public boolean releaseSeat = true;
    public double cardSeconds = 4.0;
    /** A client waits at most this long (after its card) for the host's new body before fading in anyway. */
    public double clientWaitSeconds = 10.0;

    /** Why the player is being respawned. */
    public enum Reason { HOSPITALIZED, ARRESTED, ABDUCTED }

    /** The place kinds a hospitalised player wakes at (world.Places kinds, nearest wins). */
    static final java.util.Set<String> HOSPITAL_KINDS = java.util.Set.of("Hospital", "HospitalSmall", "Clinic");
    /** The fade-in waits at most this long for the world round the respawn point to finish streaming. */
    public double streamWaitSeconds = 4.0;
    /** A respawn point with a body within this distance is taken: the next one is used (co-op, two downs at once). */
    public double pointClearance = 0.9;

    /** One player waiting to be respawned (on the authority). */
    private static final class Job {
        Player dead;
        String id;
        CharacterInfo info;
        Reason reason;
        double left;
        /** The standing when they went down (the wanted level is cleared at the respawn). */
        int policeStars, gangStars;
        String gang = "";
        /** Cash carried to the new body, after the bill. */
        int charged;
    }

    private final List<Job> jobs = new ArrayList<>();
    /** The local player's card: counting down, then (on a client) waiting for the host's new body. */
    private double cardLeft = -1;
    private double clientWait = -1;
    private String localDeadId = "";
    private Reason reason = Reason.HOSPITALIZED;
    /** The captive's prompt (pay the ransom, or run). */
    private Label captivePrompt;
    private Player fresh;
    private int respawns;
    /** The fade-in is held (seconds left) until the world round the new body has streamed (no transform tear). */
    private double streamWait = -1;

    private CanvasLayer overlay;
    private ColorRect black;
    private Label card, cardEn;
    private godot.api.Font jpFont;
    private double fadeIn = -1;

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus)
            bus.characterDied.connectUnsafe(godot.core.MethodCallable.createUnsafe(this, "onCharacterDied"),
                    godot.core.ConnectFlags.DEFAULT);
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
    }

    private com.openworld.net.NetworkManager net() {
        return getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n && n.isNetworked() ? n : null;
    }

    /** This peer decides respawns (single player, or the host). */
    private boolean authority() {
        com.openworld.net.NetworkManager n = net();
        return n == null || n.isServer();
    }

    /** Will this death be answered by a respawn (so GameManager does not end the game)? */
    public boolean willRespawn(CharacterInfo info) {
        if (!enabled || info == null) return false;
        Player p = playerOf(info.characterId);
        if (p == null) return false;
        // networked: every player respawns (the host runs it); single player: the local player
        return net() != null || p.isLocallyOwnedPlayer();
    }

    @Register
    public void onCharacterDied(CharacterInfo info) {
        if (!willRespawn(info)) return;
        Player p = playerOf(info.characterId);
        if (authority()) {
            if (jobFor(info.characterId) == null) start(p, info, outcomeFor(info.characterId));
        } else if (p.isLocallyOwnedPlayer() && cardLeft < 0 && clientWait < 0) {
            // a client: the card for its own body; the host sends the new one
            reason = Reason.HOSPITALIZED;
            localDeadId = info.characterId;
            cardLeft = cardSeconds;
            showCard(true);
        }
    }

    /**
     * Arrest a player (the police dispatch's arrest moment, PLAN.md W5): the same respawn, in a police cell. Returns
     * false when nothing happened (respawn off, not the authority, already respawning, lethal-wanted).
     */
    public boolean arrest(Player p) {
        if (p == null || p.getCharacterInfo() == null || !willRespawn(p.getCharacterInfo()) || !authority()) return false;
        if (jobFor(p.getCharacterInfo().characterId) != null) return false;
        // a lethal-wanted player is not arrested: police shoot (user, 2026-10-03 -- it usually ends in hospital)
        WantedSystem ws = WantedSystem.get();
        if (ws != null && ws.isLethal(p.getCharacterInfo().characterId)) return false;
        p.inputContexts.push("arrest", com.openworld.control.InputContext.HELD);
        start(p, p.getCharacterInfo(), Reason.ARRESTED);
        return true;
    }

    /**
     * Where a player who went down wakes (user, 2026-10-06; {@link RecoveryRules}): a gang that has any standing
     * against them takes them (拉致); else the police, if they want them (逮捕, a death included); else hospital.
     */
    private Reason outcomeFor(String id) {
        GangSystem gs = GangSystem.get();
        WantedSystem ws = WantedSystem.get();
        String g = gs != null ? gs.worstGang(id) : "";
        int gangStars = g.isEmpty() ? 0 : gs.starsOf(id, g);
        RecoveryRules.Outcome o = RecoveryRules.onDown(gangStars, ws != null ? ws.starsOf(id) : 0);
        return Reason.valueOf(o.name());
    }

    private RecoveryRules recovery() {
        GangSystem gs = GangSystem.get();
        return gs != null && gs.recoveryRules() != null ? gs.recoveryRules() : RecoveryRules.parse(null, null);
    }

    private Job jobFor(String id) {
        for (Job j : jobs) if (j.id.equals(id)) return j;
        return null;
    }

    private void start(Player p, CharacterInfo info, Reason why) {
        Job j = new Job();
        j.dead = p;
        j.id = info.characterId;
        j.info = info;
        j.reason = why;
        j.left = cardSeconds;
        // the standing NOW (it is cleared at the respawn), and the bill (RecoveryRules)
        WantedSystem ws = WantedSystem.get();
        GangSystem gs = GangSystem.get();
        j.policeStars = ws != null ? ws.starsOf(j.id) : 0;
        j.gang = gs != null ? gs.worstGang(j.id) : "";
        j.gangStars = j.gang.isEmpty() ? 0 : gs.starsOf(j.id, j.gang);
        int bill = recovery().fee(RecoveryRules.Outcome.valueOf(why.name()), j.policeStars);
        // the bill is the PLAYER's (their profile, AR2) and may run into debt (CR4): what they cannot cover is owed
        j.charged = (int) com.openworld.game.profile.Economy.bill(com.openworld.game.profile.Profiles.of(p), bill, why == Reason.ARRESTED
                ? com.openworld.game.profile.Economy.Reason.BILL_BAIL : com.openworld.game.profile.Economy.Reason.BILL_HOSPITAL);
        jobs.add(j);
        if (p != null && p.isLocallyOwnedPlayer()) {
            reason = why;
            localDeadId = j.id;
            cardLeft = cardSeconds;
            streamWait = -1;            // a previous respawn's fade still pending must not hide THIS card
            fadeIn = -1;
            showCard(true);
        }
        // a hospitalisation or an arrest ends the running mission (user, 2026-10-03); the host decides
        if (getNodeOrNull("/root/MissionManager") instanceof com.openworld.game.mission.MissionManager mm
                && mm.missionActiveNow()) mm.failMission(why == Reason.ARRESTED ? "player_arrested"
                : why == Reason.ABDUCTED ? "player_abducted" : "player_hospitalized");
        com.openworld.game.activity.ActivityRuntime rt = com.openworld.game.activity.ActivityRuntime.get();
        if (rt != null) rt.playerRecovered(j.id, why == Reason.ARRESTED ? "player_arrested"
                : why == Reason.ABDUCTED ? "player_abducted" : "player_hospitalized");
    }

    private static Player playerOf(String id) {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p != null && GD.isInstanceValid(p) && p.getCharacterInfo() != null
                    && id.equals(p.getCharacterInfo().characterId)) return p;
        }
        return null;
    }

    @Register
    @Override
    public void _process(double delta) {
        for (Job j : new ArrayList<>(jobs)) {
            j.left -= delta;
            if (j.left < 0) {
                jobs.remove(j);
                respawn(j);
            }
        }
        if (cardLeft >= 0) {
            cardLeft -= delta;
            if (black != null) black.setColor(new Color(0f, 0f, 0f, (float) Math.min(1.0, Math.max(0.0, 1.0 - cardLeft))));
            if (cardLeft < 0 && !authority()) clientWait = clientWaitSeconds;
        }
        if (clientWait >= 0) {
            // a client: hold the black until the host's new body for us has arrived
            clientWait -= delta;
            Player back = playerOf(localDeadId);
            if ((back != null && back.isAlive() && back.isLocallyOwnedPlayer()) || clientWait < 0) {
                clientWait = -1;
                fresh = back;
                respawns++;
                fadeIn = 1.0;
            }
        }
        if (streamWait >= 0) {
            streamWait -= delta;
            com.openworld.world.ZoneManager zm = com.openworld.world.ZoneManager.get();
            if (zm == null || zm.streamingPendingNow() == 0 || streamWait < 0) {
                streamWait = -1;
                fadeIn = 1.0;
            }
        }
        if (fadeIn >= 0) {
            fadeIn -= delta;
            if (black != null) black.setColor(new Color(0f, 0f, 0f, (float) Math.max(0.0, fadeIn)));
            if (fadeIn < 0) showCard(false);
        }
        tickCaptive();
    }

    private void respawn(Job j) {
        Player dead = j.dead != null && GD.isInstanceValid(j.dead) ? j.dead : null;
        Vector3 deathAt = dead != null ? dead.getGlobalPosition() : new Vector3();
        // ARRESTED: the nearest police station; HOSPITALIZED: the nearest hospital or clinic -- each woken OUTSIDE, on
        // one of the building's authored respawn points (MARK_respawn, carried in the places record, so nothing has to
        // be streamed; PLAN.md 1c, user 2026-10-06: hospital and police behave the same, GTA's steps). A place with
        // no respawn points falls back to its door. ABDUCTED: the gang's place (its door; captivity is gameplay).
        // Else the scene's PlayerSpawn, else where it happened.
        Vector3 to = null;
        Vector3 from = null;
        double best = Double.MAX_VALUE;
        for (Places.Place p : Places.all()) {
            boolean fits = switch (j.reason) {
                case ARRESTED -> "PoliceStation".equals(p.kind());
                case ABDUCTED -> j.gang.equals(p.gang());
                default -> HOSPITAL_KINDS.contains(p.kind());
            };
            if (!fits) continue;
            double d = p.at().distanceTo(deathAt);
            if (d < best) {
                best = d;
                from = p.at();
                to = j.reason == Reason.ABDUCTED ? p.go() : freePoint(p);
            }
        }
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        if (to == null && scene != null && scene.getNodeOrNull("PlayerSpawn") instanceof Node3D sp)
            to = sp.getGlobalPosition();
        if (to == null) to = deathAt;

        GameManager gm = getParent() instanceof GameManager g ? g : null;
        Node container = gm != null ? gm.resolveCharactersContainer() : null;
        if (container == null && dead != null) container = dead.getParent();
        if (!(GD.load(PLAYER_SCENE) instanceof PackedScene ps) || container == null) {
            GD.print("RespawnSystem: cannot respawn (no Player scene or Characters container)");
            return;
        }
        com.openworld.net.NetworkManager net = net();
        boolean local = dead == null ? j.info.ownerPeerId == 0 || (net != null && net.isAuthorityFor(j.info))
                : dead.isLocallyOwnedPlayer();
        // tell every peer the old body is gone BEFORE the new one with the same id is announced
        if (net != null) net.announceDespawn(j.id);
        if (dead != null) {
            // a body that died SEATED (a seated corpse) leaves its car first, or the car keeps the dead player's
            // controller and camera and the HUD stays in its vehicle situation after the respawn (PLAN.md 1i)
            if (releaseSeat && dead.currentVehicleNode instanceof com.openworld.carrier.vehicle.Vehicle v)
                v.releaseOccupant(dead);
            if (dead.getParent() != null) dead.getParent().removeChild(dead);
            dead.queueFree();
        }
        if (!(ps.instantiate() instanceof Player p)) return;
        // what the last fight left behind goes as soon as the camera is at the new body (the old scene is out of view)
        WorldJanitor wj = WorldJanitor.get();
        if (wj != null) wj.sweepSoon(1.5);
        CharacterInfo info = new CharacterInfo();
        info.characterId = j.id;
        info.displayName = j.info != null ? j.info.displayName : "Player";
        info.faction = Faction.PLAYER;
        info.ownerPeerId = j.info != null ? j.info.ownerPeerId : 0;
        p.characterInfo = info;
        Vector3 pos = to.plus(new Vector3(0, 0.3, 0));
        Vector3 localPos = pos;
        if (container instanceof Node3D c3) localPos = c3.getGlobalTransform().affineInverse().times(pos);
        p.setPosition(localPos);
        // facing AWAY from the building, out to the street; Player._ready copies the body's yaw into the camera rig,
        // so the first frame is already behind the player
        if (from != null) {
            double dx = to.getX() - from.getX(), dz = to.getZ() - from.getZ();
            if (dx * dx + dz * dz > 0.01) p.setRotation(new Vector3(0, Math.atan2(-dx, -dz) + Math.PI, 0));
        }
        container.addChild(p);
        // a body spawned for a remote peer is that peer's puppet here (GameManager.spawnPlayerBody's rule)
        if (net != null && !net.isAuthorityFor(info)) p.attachController(new com.openworld.net.NetworkController());
        if (net != null) net.announceSpawn(p);
        WantedSystem w = WantedSystem.get();
        if (w != null) w.clear(j.id);
        if (j.reason == Reason.ABDUCTED) {
            // held where they wake, by the gang's guards, until they pay or run
            GangSystem gs = GangSystem.get();
            RecoveryRules rr = recovery();
            if (gs != null) gs.hold(j.id, j.gang, to, rr.ransom(j.gangStars));
            EnforcementDispatch ed = EnforcementDispatch.get();
            if (ed != null) ed.guard(p, j.gang, to, rr.guards, rr.guardWeapons);
        }
        if (local) {
            fresh = p;
            respawns++;
            streamWait = streamWaitSeconds;
        }
        GD.print("RespawnSystem: " + j.reason + " -> respawned " + j.id + (local ? "" : " (remote)") + " at " + to);
    }

    /**
     * The local player held by a gang: a prompt with the ransom, and the interact key pays it (single player / host;
     * a client's ransom is not sent yet). Escape needs nothing here: GangSystem watches the distance.
     */
    private void tickCaptive() {
        GangSystem gs = GangSystem.get();
        Player me = null;
        for (Player q : PlayerRegistry.getPlayers()) if (q.isLocallyOwnedPlayer()) me = q;
        GangSystem.Captivity c = gs != null && me != null && me.getCharacterInfo() != null
                ? gs.captivityOf(me.getCharacterInfo().characterId) : null;
        boolean show = c != null && !c.escaping;
        if (show && captivePrompt == null) {
            showCard(false);
            captivePrompt = label(26);
            captivePrompt.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER_BOTTOM, false);
            captivePrompt.setOffset(godot.core.Side.TOP, -120f);
            captivePrompt.setOffset(godot.core.Side.LEFT, -420f);
            captivePrompt.setOffset(godot.core.Side.RIGHT, 420f);
            CanvasLayer layer = new CanvasLayer();
            layer.setLayer(60);
            layer.addChild(captivePrompt);
            addChild(layer);
        }
        if (captivePrompt == null) return;
        captivePrompt.setVisible(show);
        if (!show) return;
        var g = gs.gang(c.gang);
        captivePrompt.setText("拉致 " + (g != null ? g.nameJa() + " " + g.name() : c.gang) + "\n身代金 ransom ¥"
                + String.format("%,d", c.ransom) + "  [E] pay   (cash ¥" + String.format("%,d", com.openworld.game.profile.Profiles.balanceOf(me))
                + ")   or run for it");
        if (authority() && godot.api.Input.INSTANCE.isActionJustPressed("interact") && gs.payRansom(me))
            GD.print("RespawnSystem: ransom paid");
    }

    /** The first of the place's respawn points with no body within {@link #pointClearance}; its door with none. */
    private Vector3 freePoint(Places.Place p) {
        if (p.respawn().isEmpty()) return p.go();
        for (Vector3 v : p.respawn()) {
            boolean taken = false;
            for (Node n : getTree().getNodesInGroup(new StringName("characters")))
                if (n instanceof Node3D c && c.getGlobalPosition().distanceTo(v) < pointClearance) { taken = true; break; }
            if (!taken) return v;
        }
        return p.respawn().get(0);
    }

    private void showCard(boolean on) {
        if (on && overlay == null) {
            overlay = new CanvasLayer();
            overlay.setLayer(90);
            black = new ColorRect();
            black.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
            black.setColor(new Color(0f, 0f, 0f, 0f));
            black.setMouseFilter(Control.MouseFilter.IGNORE);
            if (GD.load(JP_FONT) instanceof godot.api.Font f) jpFont = f;
            card = label(96);
            cardEn = label(34);
            card.setOffset(godot.core.Side.TOP, -70f);
            cardEn.setOffset(godot.core.Side.TOP, 70f);
            overlay.addChild(black);
            overlay.addChild(card);
            overlay.addChild(cardEn);
            addChild(overlay);
        }
        if (on && card != null) {
            Color c = switch (reason) {
                case ARRESTED -> new Color(1f, 0.78f, 0.28f, 1f);
                case ABDUCTED -> new Color(1f, 0.38f, 0.42f, 1f);
                default -> new Color(0.62f, 0.86f, 1f, 1f);
            };
            card.setText(switch (reason) { case ARRESTED -> "逮捕"; case ABDUCTED -> "拉致"; default -> "入院"; });
            // the card never carries money (user, 2026-10-10: a bill line pushed the English up into the kanji);
            // the bill is told by ui.CashReadout's change line
            cardEn.setText(reason.name());
            card.addThemeColorOverride(new StringName("font_color"), c);
            cardEn.addThemeColorOverride(new StringName("font_color"), c);
        }
        if (overlay != null) overlay.setVisible(on);
        if (card != null) card.setVisible(on && (cardLeft >= 0 || clientWait >= 0));
        if (cardEn != null) cardEn.setVisible(on && (cardLeft >= 0 || clientWait >= 0));
    }

    static final String JP_FONT = "res://src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf";

    private Label label(int size) {
        Label l = new Label();
        l.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT, false);
        l.setHorizontalAlignment(godot.core.HorizontalAlignment.CENTER);
        l.setVerticalAlignment(godot.core.VerticalAlignment.CENTER);
        l.setMouseFilter(Control.MouseFilter.IGNORE);
        if (jpFont != null) l.addThemeFontOverride(new StringName("font"), jpFont);
        l.addThemeFontSizeOverride(new StringName("font_size"), size);
        l.addThemeConstantOverride(new StringName("outline_size"), 8);
        l.addThemeColorOverride(new StringName("font_outline_color"), new Color(0f, 0f, 0f, 0.8f));
        return l;
    }

    // ── probe surface ──
    @Register public int respawnsNow() { return respawns; }
    @Register public boolean arrestNow(Node player) { return player instanceof Player p && arrest(p); }
    @Register public String captivePromptNow() { return captivePrompt != null && captivePrompt.isVisible() ? captivePrompt.getText() : ""; }
    @Register public String lastReasonNow() { return reason.name(); }
    @Register public String cardTextNow() { return card != null && card.isVisible() ? card.getText() + " " + cardEn.getText() : ""; }
    @Register public Node respawnedPlayerNow() { return fresh; }
    /** True once the local respawn's fade-in has begun (the world round it had streamed, or the wait ran out). */
    @Register public boolean fadedInNow() { return fresh != null && streamWait < 0; }
}
