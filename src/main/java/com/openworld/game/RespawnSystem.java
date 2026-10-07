package com.openworld.game;

import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.world.Door;
import com.openworld.world.Places;
import godot.annotation.Register;
import godot.annotation.Script;
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
 *   <li><b>入院 HOSPITALIZED</b> -- a death: the player wakes at the door of the nearest hospital or clinic.</li>
 *   <li><b>逮捕 ARRESTED</b> -- {@link #arrest}: the player wakes in a CELL of the nearest police station (a
 *       {@code mission_marker} with {@code team = prisoner}, the 留置場 in {@code interior_plans.py}), once it has
 *       streamed in, and the station's locked doors open until the player is {@link #relockDistance} m away.</li>
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

    @godot.annotation.Visible public boolean enabled = true;

    public boolean getEnabled() { return enabled; }

    public void setEnabled(boolean v) { enabled = v; }
    public double cardSeconds = 4.0;
    /** A client waits at most this long (after its card) for the host's new body before fading in anyway. */
    public double clientWaitSeconds = 10.0;

    /** Why the player is being respawned. */
    public enum Reason { HOSPITALIZED, ARRESTED, ABDUCTED }

    /** The place kinds a hospitalised player wakes at (world.Places kinds, nearest wins). */
    static final java.util.Set<String> HOSPITAL_KINDS = java.util.Set.of("Hospital", "HospitalSmall", "Clinic");
    /** Seconds the cell is waited for after the respawn (it streams in with the station's building cell). */
    public double cellWaitSeconds = 20.0;
    public double relockDistance = 60.0;
    public double cellSearchRadius = 90.0;

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
        int cash, charged;
    }

    private final List<Job> jobs = new ArrayList<>();
    /** The local player's card: counting down, then (on a client) waiting for the host's new body. */
    private double cardLeft = -1;
    private double clientWait = -1;
    private String localDeadId = "";
    private Reason reason = Reason.HOSPITALIZED;
    /** The bill line under the card ("¥15,000", or the ransom). */
    private String cardBill = "";
    /** The captive's prompt (pay the ransom, or run). */
    private Label captivePrompt;
    private Player fresh;
    private Vector3 station;
    private double cellWaitLeft = -1;
    private final List<Door> unlocked = new ArrayList<>();
    private int respawns;

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
                    godot.api.Object.ConnectFlags.DEFAULT);
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        unlocked.clear();
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
        p.inputBlocked = true;
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
        int cash = p != null ? p.cash : 0;
        j.charged = RecoveryRules.charge(cash, bill);
        j.cash = cash - j.charged;
        jobs.add(j);
        if (p != null && p.isLocallyOwnedPlayer()) {
            reason = why;
            localDeadId = j.id;
            cardLeft = cardSeconds;
            cardBill = why == Reason.ABDUCTED ? "身代金 ransom ¥" + String.format("%,d", recovery().ransom(j.gangStars))
                    : j.charged > 0 ? "¥" + String.format("%,d", j.charged) : "";
            showCard(true);
        }
        // a hospitalisation or an arrest ends the running mission (user, 2026-10-03); the host decides
        if (getNodeOrNull("/root/MissionManager") instanceof com.openworld.game.mission.MissionManager mm
                && mm.missionActiveNow()) mm.failMission(why == Reason.ARRESTED ? "player_arrested"
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
        if (fadeIn >= 0) {
            fadeIn -= delta;
            if (black != null) black.setColor(new Color(0f, 0f, 0f, (float) Math.max(0.0, fadeIn)));
            if (fadeIn < 0) showCard(false);
        }
        tickCaptive();
        if (cellWaitLeft >= 0) {
            cellWaitLeft -= delta;
            if (fresh == null || !GD.isInstanceValid(fresh)) cellWaitLeft = -1;
            else if (intoCell() || cellWaitLeft < 0) cellWaitLeft = -1;
        }
        if (!unlocked.isEmpty() && fresh != null && GD.isInstanceValid(fresh) && station != null
                && fresh.getGlobalPosition().distanceTo(station) > relockDistance) {
            for (Door d : unlocked) if (GD.isInstanceValid(d)) d.setLocked(true);
            unlocked.clear();
        }
    }

    private void respawn(Job j) {
        Player dead = j.dead != null && GD.isInstanceValid(j.dead) ? j.dead : null;
        Vector3 deathAt = dead != null ? dead.getGlobalPosition() : new Vector3();
        // ARRESTED: the nearest police station (a koban has no cell); HOSPITALIZED: the nearest hospital or clinic.
        // Either, else the scene's PlayerSpawn, else where it happened.
        Vector3 to = null;
        Vector3 at = null;
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
                to = p.go();
                if (j.reason == Reason.ARRESTED) at = p.at();
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
        // a remote prisoner cannot be moved by the host later (the client owns its position): put it in the cell
        // now if the station has streamed in here
        if (!local && at != null) {
            Node3D cell = cellNear(at);
            if (cell != null) to = cell.getGlobalPosition();
        }
        // tell every peer the old body is gone BEFORE the new one with the same id is announced
        if (net != null) net.announceDespawn(j.id);
        if (dead != null) {
            if (dead.getParent() != null) dead.getParent().removeChild(dead);
            dead.queueFree();
        }
        if (!(ps.instantiate() instanceof Player p)) return;
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
        container.addChild(p);
        // a body spawned for a remote peer is that peer's puppet here (GameManager.spawnPlayerBody's rule)
        if (net != null && !net.isAuthorityFor(info)) p.attachController(new com.openworld.net.NetworkController());
        if (net != null) net.announceSpawn(p);
        WantedSystem w = WantedSystem.get();
        if (w != null) w.clear(j.id);
        p.cash = j.cash;                    // the bill was taken from what they had (RecoveryRules)
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
            station = at;
            cellWaitLeft = station != null ? cellWaitSeconds : -1;
            fadeIn = 1.0;
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
                + String.format("%,d", c.ransom) + "  [E] pay   (cash ¥" + String.format("%,d", me.cash)
                + ")   or run for it");
        if (authority() && godot.api.Input.INSTANCE.isActionJustPressed("interact") && gs.payRansom(me))
            GD.print("RespawnSystem: ransom paid");
    }

    private Node3D cellNear(Vector3 where) {
        Node3D cell = null;
        double best = cellSearchRadius;
        for (Node n : getTree().getNodesInGroup(new StringName("mission_marker"))) {
            if (!(n instanceof Node3D m) || !"prisoner".equals(String.valueOf(m.getMeta(new StringName("team"), "")))) continue;
            double d = m.getGlobalPosition().distanceTo(where);
            if (d < best) { best = d; cell = m; }
        }
        return cell;
    }

    /** Move the fresh body into a cell once the station has streamed in. True when done. */
    private boolean intoCell() {
        Node3D cell = cellNear(station);
        if (cell == null) return false;
        fresh.setGlobalPosition(cell.getGlobalPosition().plus(new Vector3(0, 0.1, 0)));
        fresh.setVelocity(new Vector3());
        // the station's locked doors open for the prisoner (cell doors are interior: never locked). The marker
        // hangs under the building's own Markers node, so the building is two levels up.
        Node building = cell.getParent() != null ? cell.getParent().getParent() : null;
        unlockUnder(building);
        GD.print("RespawnSystem: into the cell at " + cell.getGlobalPosition() + ", " + unlocked.size() + " door(s) unlocked");
        return true;
    }

    private void unlockUnder(Node n) {
        if (n == null) return;
        if (n instanceof Door d) {
            if (d.isLocked() && !unlocked.contains(d)) {
                d.setLocked(false);
                unlocked.add(d);
            }
            return;
        }
        for (Node c : n.getChildren()) unlockUnder(c);
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
            cardEn.setText(reason.name() + (cardBill.isEmpty() ? "" : "\n\n" + cardBill));
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
    @Register public int doorsUnlockedNow() { return unlocked.size(); }
    @Register public boolean inCellNow() { return fresh != null && cellWaitLeft < 0 && station != null; }
}
