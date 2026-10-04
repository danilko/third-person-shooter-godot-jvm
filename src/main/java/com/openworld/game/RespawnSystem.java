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
 * <p>Single player only for now: in a networked session a death keeps the old behaviour (GAME_OVER once every player
 * is down). Built in code by {@link GameManager}; {@link #enabled} off is the control.
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

    /** Why the player is being respawned. */
    public enum Reason { HOSPITALIZED, ARRESTED }

    /** The place kinds a hospitalised player wakes at (world.Places kinds, nearest wins). */
    static final java.util.Set<String> HOSPITAL_KINDS = java.util.Set.of("Hospital", "HospitalSmall", "Clinic");
    /** Seconds the cell is waited for after the respawn (it streams in with the station's building cell). */
    public double cellWaitSeconds = 20.0;
    public double relockDistance = 60.0;
    public double cellSearchRadius = 90.0;

    private Player dead;
    private String deadId = "";
    private CharacterInfo deadInfo;
    private double cardLeft = -1;
    private Reason reason = Reason.HOSPITALIZED;
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

    /** Will this death be answered by a respawn (so GameManager does not end the game)? */
    public boolean willRespawn(CharacterInfo info) {
        if (!enabled || info == null) return false;
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net && net.isNetworked())
            return false;
        Player p = playerOf(info.characterId);
        return p != null && p.isLocallyOwnedPlayer();
    }

    @Register
    public void onCharacterDied(CharacterInfo info) {
        if (!willRespawn(info) || cardLeft >= 0) return;
        start(playerOf(info.characterId), info, Reason.HOSPITALIZED);
    }

    /**
     * Arrest a player (the police dispatch's arrest moment, PLAN.md W5): the same respawn, in a police cell. Returns
     * false when nothing happened (respawn off, networked, not the local player, already respawning).
     */
    public boolean arrest(Player p) {
        if (p == null || p.getCharacterInfo() == null || !willRespawn(p.getCharacterInfo()) || cardLeft >= 0) return false;
        // a lethal-wanted player is not arrested: police shoot (user, 2026-10-03 -- it usually ends in hospital)
        WantedSystem ws = WantedSystem.get();
        if (ws != null && ws.isLethal(p.getCharacterInfo().characterId)) return false;
        p.inputBlocked = true;
        start(p, p.getCharacterInfo(), Reason.ARRESTED);
        return true;
    }

    private void start(Player p, CharacterInfo info, Reason why) {
        dead = p;
        deadId = info.characterId;
        deadInfo = info;
        reason = why;
        cardLeft = cardSeconds;
        showCard(true);
        // a hospitalisation or an arrest ends the running mission (user, 2026-10-03)
        if (getNodeOrNull("/root/MissionManager") instanceof com.openworld.game.mission.MissionManager mm
                && mm.missionActiveNow()) mm.failMission(why == Reason.ARRESTED ? "player_arrested" : "player_hospitalized");
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
        if (cardLeft >= 0) {
            cardLeft -= delta;
            if (black != null) black.setColor(new Color(0f, 0f, 0f, (float) Math.min(1.0, Math.max(0.0, 1.0 - cardLeft))));
            if (cardLeft < 0) respawn();
        }
        if (fadeIn >= 0) {
            fadeIn -= delta;
            if (black != null) black.setColor(new Color(0f, 0f, 0f, (float) Math.max(0.0, fadeIn)));
            if (fadeIn < 0) showCard(false);
        }
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

    private void respawn() {
        Vector3 deathAt = dead != null && GD.isInstanceValid(dead) ? dead.getGlobalPosition() : new Vector3();
        // ARRESTED: the nearest police station (a koban has no cell); HOSPITALIZED: the nearest hospital or clinic.
        // Either, else the scene's PlayerSpawn, else where it happened.
        Vector3 to = null;
        station = null;
        double best = Double.MAX_VALUE;
        for (Places.Place p : Places.all()) {
            boolean fits = reason == Reason.ARRESTED ? "PoliceStation".equals(p.kind()) : HOSPITAL_KINDS.contains(p.kind());
            if (!fits) continue;
            double d = p.at().distanceTo(deathAt);
            if (d < best) {
                best = d;
                to = p.go();
                if (reason == Reason.ARRESTED) station = p.at();
            }
        }
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        if (to == null && scene != null && scene.getNodeOrNull("PlayerSpawn") instanceof Node3D sp)
            to = sp.getGlobalPosition();
        if (to == null) to = deathAt;

        GameManager gm = getParent() instanceof GameManager g ? g : null;
        Node container = gm != null ? gm.resolveCharactersContainer() : null;
        if (container == null && dead != null && GD.isInstanceValid(dead)) container = dead.getParent();
        if (!(GD.load(PLAYER_SCENE) instanceof PackedScene ps) || container == null) {
            GD.print("RespawnSystem: cannot respawn (no Player scene or Characters container)");
            return;
        }
        if (dead != null && GD.isInstanceValid(dead)) {
            if (dead.getParent() != null) dead.getParent().removeChild(dead);
            dead.queueFree();
        }
        dead = null;
        if (!(ps.instantiate() instanceof Player p)) return;
        CharacterInfo info = new CharacterInfo();
        info.characterId = deadId;
        info.displayName = deadInfo != null ? deadInfo.displayName : "Player";
        info.faction = Faction.PLAYER;
        p.characterInfo = info;
        Vector3 local = to.plus(new Vector3(0, 0.3, 0));
        if (container instanceof Node3D c3) local = c3.getGlobalTransform().affineInverse().times(local);
        p.setPosition(local);
        container.addChild(p);
        fresh = p;
        respawns++;
        WantedSystem w = WantedSystem.get();
        if (w != null) w.clear(deadId);
        cellWaitLeft = station != null ? cellWaitSeconds : -1;
        fadeIn = 1.0;
        GD.print("RespawnSystem: " + reason + " -> respawned " + deadId + " at " + to);
    }

    /** Move the fresh body into a cell once the station has streamed in. True when done. */
    private boolean intoCell() {
        Node3D cell = null;
        double best = cellSearchRadius;
        for (Node n : getTree().getNodesInGroup(new StringName("mission_marker"))) {
            if (!(n instanceof Node3D m) || !"prisoner".equals(String.valueOf(m.getMeta(new StringName("team"), "")))) continue;
            double d = m.getGlobalPosition().distanceTo(station);
            if (d < best) { best = d; cell = m; }
        }
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
            boolean arrested = reason == Reason.ARRESTED;
            Color c = arrested ? new Color(1f, 0.78f, 0.28f, 1f) : new Color(0.62f, 0.86f, 1f, 1f);
            card.setText(arrested ? "逮捕" : "入院");
            cardEn.setText(arrested ? "ARRESTED" : "HOSPITALIZED");
            card.addThemeColorOverride(new StringName("font_color"), c);
            cardEn.addThemeColorOverride(new StringName("font_color"), c);
        }
        if (overlay != null) overlay.setVisible(on);
        if (card != null) card.setVisible(on && cardLeft >= 0);
        if (cardEn != null) cardEn.setVisible(on && cardLeft >= 0);
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
    @Register public String lastReasonNow() { return reason.name(); }
    @Register public String cardTextNow() { return card != null && card.isVisible() ? card.getText() + " " + cardEn.getText() : ""; }
    @Register public Node respawnedPlayerNow() { return fresh; }
    @Register public int doorsUnlockedNow() { return unlocked.size(); }
    @Register public boolean inCellNow() { return fresh != null && cellWaitLeft < 0 && station != null; }
}
