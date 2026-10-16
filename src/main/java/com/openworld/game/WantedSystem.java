package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.game.data.Tables;
import com.openworld.game.event.Actors;
import com.openworld.game.event.CrimeMap;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import com.openworld.world.SpatialEntityGrid;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.FileAccess;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The wanted level (PLAN.md W5, user decisions 2026-10-03): stars 0-5 per player, from HEAT that crimes add and that
 * drains once the player has kept out of trouble for a while. The rules and the crime table are
 * {@link WantedRules} over {@code game/crimes.json}; this node only owns the per-player state and the seams.
 *
 * <p>Owned by the AUTHORITATIVE peer (single player or the host), where damage is applied: the seams that report a
 * crime run only there. Built in code by {@link GameManager} (a child of the AutoLoad), reached through {@link #get()}.
 *
 * <p>Seams (PLAN.md 2.0 / AR3): this node SUBSCRIBES to {@link GameplayEvents} (phase WANTED) and {@link CrimeMap}
 * says which crime an event is -- a hit on police or a civilian, a gunshot, a threatened clerk, a robbed till. Nothing
 * calls in here to report a crime any more; a new crime = one row in the table + one line in CrimeMap (and, if nothing
 * publishes the act yet, its event). An act an activity sanctioned is skipped.
 *
 * <p>LETHAL crimes (a robbery, a dead policeman) make police shoot the player on sight until the heat is gone
 * (`applyHostility`), and no arrest is offered meanwhile. Gangs are a separate standing: {@link GangSystem}.
 *
 * <p>The police dispatch and the arrest are {@link EnforcementDispatch}'s.
 *
 * <p>REPLICATION (2026-10-08): the host sends each player's shown standing -- police stars, lethal, and the worst gang
 * with its stars -- as {@link GameManager#WORLD_EVENT_WANTED} when it changes (checked 4x a second) and to a joining
 * peer; a client keeps the mirror and {@link #hudOf} answers from it. Only what the HUD shows is sent: heat, timers
 * and the dispatch stay on the host, which is the only peer that acts on them.
 */
@Script(className = "WantedSystem")
public class WantedSystem extends Node {

    public static final String TABLE = "res://src/main/resources/com/openworld/game/crimes.json";

    private static WantedSystem instance;

    public static WantedSystem get() {
        return instance != null && GD.isInstanceValid(instance) ? instance : null;
    }

    private WantedRules rules;
    private DispatchRules dispatch;
    private final Map<String, WantedRules.State> states = new HashMap<>();
    private double now;
    private final List<Node> scratch = new ArrayList<>();
    private final FactionFlips flips = new FactionFlips();
    private double toggleIn;
    private double syncIn;
    /** What a player's HUD shows: police stars, lethal, worst gang ("" none), its stars. */
    public record Shown(int stars, boolean lethal, String gang, int gangStars) {
        static final Shown NONE = new Shown(0, false, "", 0);
    }
    /** Host: what was last sent per player. Client: the host's mirror. */
    private final Map<String, Shown> shown = new HashMap<>();

    private final Runnable onTable = this::readTable;

    /** crimes.json through {@link Tables#CRIMES} (again after a debug reload: the states keep their heat). */
    private void readTable() {
        Tables.Crimes c = Tables.CRIMES.get();
        rules = c == null ? null : c.wanted();
        dispatch = c == null ? null : c.dispatch();
    }

    @Register
    @Override
    public void _ready() {
        instance = this;
        readTable();
        Tables.CRIMES.onReload(onTable);
        GameplayEvents.subscribe(GameplayEvents.Phase.WANTED, onEvent);
        if (rules == null) GD.print("WantedSystem: no crime table at " + TABLE);
    }

    @Register
    @Override
    public void _exitTree() {
        Tables.CRIMES.offReload(onTable);
        GameplayEvents.unsubscribe(onEvent);
        if (instance == this) instance = null;
        states.clear();
        shown.clear();
    }

    @Register
    @Override
    public void _process(double delta) {
        now += delta;
        if (rules == null) return;
        for (WantedRules.State s : states.values()) rules.tick(s, now, delta);
        if (!callIns.isEmpty()) tickCallIns();
        if (EnforcementHooks.any()) applyHolds();
        toggleIn -= delta;
        if (toggleIn <= 0) {
            toggleIn = 0.5;
            applyHostility();
        }
        syncIn -= delta;
        if (syncIn <= 0) {
            syncIn = 0.25;
            syncShown();
        }
    }

    private com.openworld.net.NetworkManager net() {
        return getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n ? n : null;
    }

    private boolean isClient() {
        com.openworld.net.NetworkManager n = net();
        return n != null && n.isNetworked() && !n.isServer();
    }

    /** The live standing of a player (authority). */
    private Shown liveOf(String id) {
        GangSystem gangs = GangSystem.get();
        String g = gangs != null ? gangs.worstGang(id) : "";
        int gs = g.isEmpty() || gangs == null ? 0 : gangs.starsOf(id, g);
        return new Shown(starsOf(id), isLethal(id), g, gs);
    }

    /** Host: send every player whose shown standing changed. */
    private void syncShown() {
        com.openworld.net.NetworkManager n = net();
        if (n == null || !n.isNetworked() || !n.isServer()) return;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || p.getCharacterInfo() == null) continue;
            String id = p.getCharacterInfo().characterId;
            Shown now = liveOf(id);
            if (now.equals(shown.getOrDefault(id, Shown.NONE))) continue;
            shown.put(id, now);
            n.broadcastWorldEvent(GameManager.WORLD_EVENT_WANTED, id, now.stars(), args(now));
        }
    }

    private static List<String> args(Shown s) {
        return List.of(s.lethal() ? "1" : "0", s.gang(), Integer.toString(s.gangStars()));
    }

    /** Host -> a joining peer: every player with any standing (nothing is sent when nobody is wanted). */
    public void sendBaseline(int peerId) {
        com.openworld.net.NetworkManager n = net();
        if (n == null) return;
        for (Map.Entry<String, Shown> e : shown.entrySet())
            if (!e.getValue().equals(Shown.NONE))
                n.sendWorldEventTo(peerId, GameManager.WORLD_EVENT_WANTED, e.getKey(), e.getValue().stars(), args(e.getValue()));
    }

    /** Client: the host's word on a player's standing. */
    public void applyRemote(String id, float stars, List<String> args) {
        String lethal = args.size() > 0 ? args.get(0) : "0";
        String gang = args.size() > 1 ? args.get(1) : "";
        int gs = 0;
        try { gs = args.size() > 2 ? Integer.parseInt(args.get(2)) : 0; } catch (NumberFormatException ignored) { }
        shown.put(id, new Shown(Math.round(stars), "1".equals(lethal), gang, gs));
    }

    /** What a player's HUD shows: live on the authority, the host's mirror on a client. */
    public Shown hudOf(String id) {
        if (id == null) return Shown.NONE;
        return isClient() ? shown.getOrDefault(id, Shown.NONE) : liveOf(id);
    }

    /**
     * Police are HOSTILE to players while any player is lethal-wanted, or wanted at the dispatch's shoot_at stars or
     * more (FactionFlips restores them after). Below that, dispatched officers run the player down to arrest.
     */
    private void applyHostility() {
        java.util.Set<String> want = new java.util.HashSet<>();
        for (WantedRules.State st : states.values())
            if (st.lethal || (dispatch != null && rules.starsFor(st.heat) >= dispatch.shootAt)) want.add(Faction.POLICE);
        flips.apply(getNodeOrNull("/root/FactionManager") instanceof com.openworld.character.FactionManager fm ? fm : null, want);
    }

    /** Lethal-wanted: police shoot on sight and no arrest is offered (user, 2026-10-03). */
    public boolean isLethal(String playerId) {
        WantedRules.State s = states.get(playerId);
        return s != null && s.lethal;
    }

    /** The weapons responding police carry for this player (crimes.json `police_weapons`; the dispatch reads it). */
    public List<String> policeWeaponsFor(String playerId) {
        return rules == null ? List.of() : isLethal(playerId) ? rules.lethalWeapons : rules.normalWeapons;
    }

    /** Report a crime by a player (characterId) at a place. Returns true when it counted. */
    public boolean report(String crimeId, Vector3 where, String playerId) {
        if (rules == null || playerId == null || playerId.isEmpty()) return false;
        // only the authoritative peer keeps the wanted level (a client's own shot also runs the fire path)
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                && net.isNetworked() && !net.isServer()) return false;
        Character who = findPlayer(playerId);
        if (who == null) return false;
        WantedRules.Crime c = rules.crimes.get(crimeId);
        if (c == null) return false;
        // CALLED IN (P1e step 4): a witnessed crime by a player nobody is after yet waits for the witness to phone it
        // in -- and dies with the witness. A police officer in reach sees it at once; a wanted player is already hunted
        if (c.witness() && rules.callInSeconds > 0 && starsOf(playerId) == 0) {
            Character w = witnessOf(where, who);
            if (w == null) return false;
            if (w != who && !(w.getCharacterInfo() != null && com.openworld.character.Faction.POLICE.equals(w.getCharacterInfo().faction))) {
                callIns.add(new CallIn(crimeId, where, playerId, w, now + rules.callInSeconds));
                return true;
            }
        }
        return apply(crimeId, where, playerId, who, !c.witness() || witnessed(where, who));
    }

    /** A running activity's hold on its participants' stars (P1e step 5): set / clear once, lock, at least / most. */
    private void applyHolds() {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || p.getCharacterInfo() == null) continue;
            String id = p.getCharacterInfo().characterId;
            int have = starsOf(id), want = EnforcementHooks.wanted(id, have);
            if (want != have) setStars(id, want, isLethal(id) && want > 0);
        }
    }

    /** A crime waiting for its witness to call it in. */
    private record CallIn(String crimeId, Vector3 where, String playerId, Character witness, double due) {}
    private final List<CallIn> callIns = new ArrayList<>();
    private int calledIn, silenced;

    /** Due call-ins: counted if the witness still lives (the police then know only WHERE it happened). */
    private void tickCallIns() {
        for (java.util.Iterator<CallIn> it = callIns.iterator(); it.hasNext(); ) {
            CallIn ci = it.next();
            if (now < ci.due()) continue;
            it.remove();
            Character who = findPlayer(ci.playerId());
            if (who == null) continue;
            if (!GD.isInstanceValid(ci.witness()) || !ci.witness().isAlive()) { silenced++; continue; }
            if (apply(ci.crimeId(), ci.where(), ci.playerId(), who, true)) {
                calledIn++;
                EnforcementDispatch ed = EnforcementDispatch.get();
                if (ed != null) ed.reportedAt(ci.playerId(), com.openworld.character.Faction.POLICE, ci.where());
            }
        }
    }

    /** Probe control: the call-in delay in seconds (0 = at once, the old rule). */
    @Register public void setCallInNow(double seconds) { if (rules != null) rules.callInSeconds = seconds; }

    /** "called in,silenced,pending" (probe readout). */
    @Register public String callInsNow() { return calledIn + "," + silenced + "," + callIns.size(); }

    private boolean apply(String crimeId, Vector3 where, String playerId, Character who, boolean witnessed) {
        WantedRules.State s = states.computeIfAbsent(playerId, k -> new WantedRules.State());
        int before = rules.starsFor(s.heat);
        boolean ok = rules.report(s, crimeId, witnessed, now);
        int after = rules.starsFor(s.heat);
        if (ok && after != before) GD.print("WantedSystem: " + who.getName() + " " + crimeId + " -> " + after + " star(s)");
        return ok;
    }

    private final GameplayEvents.Subscriber onEvent = this::onGameplayEvent;

    /** The seam (PLAN.md 2.0 / AR3): every crime arrives as an event. One an activity SANCTIONED is not a crime. */
    private void onGameplayEvent(GameplayEvent e, GameplayEvents.Ruling ruling) {
        if (ruling.sanctioned()) return;
        String crime = CrimeMap.police(e);
        if (!crime.isEmpty()) report(crime, Actors.vec(e.at()), e.actor().id());
    }

    /** Anyone but the offender within the witness radius saw it (a living, non-player character). */
    /** The nearest living non-player within witness_radius of a crime, or null. */
    private Character witnessOf(Vector3 where, Character offender) {
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid == null) return offender;          // no grid (a bare test scene): anyone saw it, at once
        scratch.clear();
        grid.queryRadius(where, (float) rules.witnessRadius, scratch);
        Character best = null;
        double bd = Double.MAX_VALUE;
        for (Node n : scratch) {
            if (n == offender || n instanceof Player || !(n instanceof Character c) || !c.isAlive()) continue;
            double d = c.getGlobalPosition().distanceTo(where);
            if (d < bd) { bd = d; best = c; }
        }
        return best;
    }

    private boolean witnessed(Vector3 where, Character offender) {
        SpatialEntityGrid grid = SpatialEntityGrid.get();
        if (grid == null) return true;
        scratch.clear();
        grid.queryRadius(where, (float) rules.witnessRadius, scratch);
        for (Node n : scratch) {
            if (n == offender || n instanceof Player) continue;
            if (n instanceof Character c && c.isAlive()) return true;
        }
        return false;
    }

    private static Character findPlayer(String id) {
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p.getCharacterInfo() != null && id.equals(p.getCharacterInfo().characterId)) return p;
        }
        return null;
    }

    /** Stars of a player (0-6). */
    public int starsOf(String playerId) {
        WantedRules.State s = states.get(playerId);
        return s == null || rules == null ? 0 : rules.starsFor(s.heat);
    }

    /** The police dispatch's rules (crimes.json `dispatch`), or null. */
    public DispatchRules dispatchRules() { return dispatch; }

    /** Do police shoot this player now (lethal, or at the shoot_at stars)? */
    /** Is {@code faction} hostile to players only by this system's flip (Hostility narrows it per player)? */
    public boolean flippedHostile(String faction) { return flips.flipped(faction); }

    public boolean policeShoot(String playerId) {
        WantedRules.State s = states.get(playerId);
        if (s == null || rules == null) return false;
        return s.lethal || (dispatch != null && dispatch.shoots(rules.starsFor(s.heat), false));
    }

    /** Police have the player in sight (the dispatch asks): the heat holds until they lose them. */
    public void seen(String playerId) {
        WantedRules.State s = states.get(playerId);
        if (s != null && rules != null) rules.seen(s, now);
    }

    /** Set a player's stars outright (a probe, a perf run, a mission script). */
    public void setStars(String playerId, int stars, boolean lethal) {
        if (rules == null || playerId == null) return;
        WantedRules.State s = states.computeIfAbsent(playerId, k -> new WantedRules.State());
        rules.setStars(s, stars, lethal, now);
        applyHostility();
    }

    /** Clear a player's wanted level (a jail respawn, a mission script). */
    /** A NEW GAME: nobody is wanted (game.FrontEnd). This node lives under the GameManager AutoLoad, so its states
     *  outlive the world scene they were earned in. */
    public void clearAll() {
        states.clear();
        shown.clear();
    }

    public void clear(String playerId) {
        WantedRules.State s = states.get(playerId);
        if (s != null) s.clear();
        applyHostility();
    }

    // ── probe / console surface ──
    @Register public int starsNow(String playerId) { return starsOf(playerId); }
    @Register public int hudStarsNow(String playerId) { return hudOf(playerId).stars(); }
    @Register public int hudGangStarsNow(String playerId) { return hudOf(playerId).gangStars(); }
    @Register public boolean reportNow(String crimeId, String playerId) {
        Character who = findPlayer(playerId);
        return who != null && report(crimeId, who.getGlobalPosition(), playerId);
    }
    @Register public void clearNow(String playerId) { clear(playerId); }
    @Register public boolean lethalNow(String playerId) { return isLethal(playerId); }
    @Register public void setStarsNow(String playerId, int stars, boolean lethal) { setStars(playerId, stars, lethal); }
}
