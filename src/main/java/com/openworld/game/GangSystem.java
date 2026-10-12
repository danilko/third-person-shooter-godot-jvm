package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.game.data.Tables;
import com.openworld.game.event.CrimeMap;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.FileAccess;
import godot.api.Node;
import godot.global.GD;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * Each player's standing with each gang (PLAN.md W5, user 2026-10-03) -- INDEPENDENT of the police: its own stars,
 * not cleared by a hospitalisation or an arrest, draining only below the pay threshold, and otherwise cleared only by
 * a "donation" at one of that gang's gray-area counters ({@link #donate}). At {@code attack_at} stars the gang's
 * members (the crowd's included) are hostile to players; at {@code chase_at} they hunt ({@link EnforcementDispatch}).
 * Police neither care about nor fight over it. Rules and data: {@link GangRules}, {@code game/gangs.json}.
 *
 * <p>Authority only, like the police; a child GameManager builds in code. Not saved yet (PLAN.md W5 TODO).
 */
@Script(className = "GangSystem")
public class GangSystem extends Node {

    public static final String TABLE = "res://src/main/resources/com/openworld/game/gangs.json";
    private static GangSystem instance;

    public static GangSystem get() {
        return instance != null && GD.isInstanceValid(instance) ? instance : null;
    }

    private GangRules rules;
    private DispatchRules hunters;
    private RecoveryRules recovery;

    /** A player held by a gang after an abduction (RespawnSystem): where, the ransom, and whether they ran. */
    public static final class Captivity {
        public final String gang;
        public final godot.core.Vector3 at;
        public final int ransom;
        public boolean escaping;
        Captivity(String gang, godot.core.Vector3 at, int ransom) { this.gang = gang; this.at = at; this.ransom = ransom; }
    }

    /** playerId -> their captivity. */
    private final Map<String, Captivity> captive = new HashMap<>();
    /** "playerId|gang" -> standing. */
    private final Map<String, GangRules.State> states = new HashMap<>();
    private final FactionFlips flips = new FactionFlips();
    private double now, flipIn;

    private final Runnable onTable = this::readTable;

    /** gangs.json through {@link Tables#GANGS} (again after a debug reload: the standings keep their heat). */
    private void readTable() {
        Tables.Gangs g = Tables.GANGS.get();
        rules = g == null ? null : g.rules();
        hunters = g == null ? null : g.hunters();
        recovery = g == null ? null : Tables.recovery();
    }

    @Register
    @Override
    public void _ready() {
        instance = this;
        readTable();
        Tables.GANGS.onReload(onTable);
        GameplayEvents.subscribe(GameplayEvents.Phase.GANG, onEvent);
        Tables.CRIMES.onReload(onTable);
    }

    @Register
    @Override
    public void _exitTree() {
        Tables.GANGS.offReload(onTable);
        GameplayEvents.unsubscribe(onEvent);
        Tables.CRIMES.offReload(onTable);
        if (instance == this) instance = null;
        states.clear();
    }

    @Register
    @Override
    public void _process(double delta) {
        now += delta;
        if (rules == null) return;
        for (GangRules.State s : states.values()) rules.tick(s, now, delta);
        flipIn -= delta;
        if (flipIn > 0) return;
        flipIn = 0.5;
        tickCaptivity();
        applyFlips();
    }

    /**
     * Which gangs are hostile to players NOW. By standing (attack_at stars), and then captivity decides (user,
     * 2026-10-10: "should not act unless the character moves past the original point or starts to attack"):
     * a gang HOLDING a player who has done neither is not hostile whatever the standing -- the guards stand over the
     * captive -- and one whose captive ran or attacked IS hostile whatever the standing. The second half was
     * missing: a player abducted on a low standing could walk away, or shoot a guard, and nobody answered.
     */
    private void applyFlips() {
        if (rules == null) return;
        Set<String> want = new HashSet<>();
        for (Map.Entry<String, GangRules.State> e : states.entrySet())
            if (rules.attacks(e.getValue())) want.add(e.getKey().substring(e.getKey().indexOf('|') + 1));
        for (Captivity c : captive.values()) if (!c.escaping) want.remove(c.gang);
        for (Captivity c : captive.values()) if (c.escaping) want.add(c.gang);
        flips.apply(getNodeOrNull("/root/FactionManager") instanceof com.openworld.character.FactionManager fm ? fm : null, want);
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    public boolean isGang(String faction) { return rules != null && faction != null && rules.gangs.containsKey(faction); }

    /** A gang crime by a player. True when it counted. */
    public boolean report(String gang, String crimeId, String playerId) {
        if (rules == null || !authority() || !isGang(gang) || playerId == null || playerId.isEmpty()) return false;
        GangRules.State s = states.computeIfAbsent(playerId + "|" + gang, k -> new GangRules.State());
        int before = rules.starsFor(s.heat);
        boolean ok = rules.report(s, crimeId, now);
        if (ok && rules.starsFor(s.heat) != before)
            GD.print("GangSystem: " + playerId + " " + crimeId + " -> " + gang + " " + rules.starsFor(s.heat) + " star(s)");
        return ok;
    }

    private final GameplayEvents.Subscriber onEvent = this::onGameplayEvent;

    /** The seam (PLAN.md 2.0 / AR3): a member hurt or killed, a protected clerk threatened, a gray till robbed --
     *  by a player, and not sanctioned by an activity. */
    private void onGameplayEvent(GameplayEvent e, GameplayEvents.Ruling ruling) {
        captiveAttacked(e);
        if (ruling.sanctioned()) return;
        CrimeMap.GangCrime c = CrimeMap.gang(e, this::isGang);
        if (c != null) report(c.gang(), c.crimeId(), e.actor().id());
    }

    /** A captive who shoots, or hurts one of the gang holding them, has stopped being a captive who waits: the
     *  guards answer at once (not at the next half-second pass). */
    private void captiveAttacked(GameplayEvent e) {
        Captivity c = captive.get(e.actor().id());
        if (c == null || c.escaping) return;
        boolean attack = e instanceof GameplayEvent.WeaponFired
                || ((e instanceof GameplayEvent.Damaged || e instanceof GameplayEvent.Killed) && c.gang.equals(e.target().faction()));
        if (!attack) return;
        c.escaping = true;
        GD.print("GangSystem: " + e.actor().id() + " attacked while held by " + c.gang);
        applyFlips();
    }

    public int starsOf(String playerId, String gang) {
        GangRules.State s = states.get(playerId + "|" + gang);
        return s == null || rules == null ? 0 : rules.starsFor(s.heat);
    }

    /** The donation that clears a player's heat with a gang (0 = nothing owed). */
    public int feeOf(String playerId, String gang) {
        GangRules.State s = states.get(playerId + "|" + gang);
        return s == null || rules == null ? 0 : rules.fee(gang, s);
    }

    /** Pay the donation from the player's cash: clears the heat. False when nothing is owed or the cash is short. */
    public boolean donate(Character who, String gang) {
        if (who == null || who.getCharacterInfo() == null || !authority()) return false;
        String pid = who.getCharacterInfo().characterId;
        int fee = feeOf(pid, gang);
        if (fee <= 0 || !com.openworld.game.profile.Economy.transfer(com.openworld.game.profile.Profiles.of(who), null, fee, com.openworld.game.profile.Economy.Reason.GANG_FEE)) return false;
        states.remove(pid + "|" + gang);
        Captivity held = captive.get(pid);
        if (held != null && held.gang.equals(gang)) captive.remove(pid);
        GD.print("GangSystem: " + pid + " paid " + fee + " dollars to " + gang);
        return true;
    }

    /** The gang the player stands worst with (the HUD's second row), "" none. */
    public String worstGang(String playerId) {
        String best = "";
        int stars = 0;
        if (rules == null) return best;
        for (String g : rules.gangs.keySet()) {
            int s = starsOf(playerId, g);
            if (s > stars) { stars = s; best = g; }
        }
        return best;
    }

    // ── captivity (拉致 ABDUCTED, RespawnSystem) ──

    public RecoveryRules recoveryRules() { return recovery; }

    /** Hold a player at {@code at} for {@code gang} until they pay {@code ransom} or escape. */
    public void hold(String playerId, String gang, godot.core.Vector3 at, int ransom) {
        captive.put(playerId, new Captivity(gang, at, ransom));
        // NOW, before the guards are spawned: the standing that got the player abducted is usually an attacking one,
        // and guards born hostile opened fire in the up-to-half-second before the next pass ("sometimes they attack
        // at the spawn point whatever I do", user 2026-10-10)
        applyFlips();
        GD.print("GangSystem: " + playerId + " held by " + gang + ", ransom " + ransom + " dollars");
    }

    public Captivity captivityOf(String playerId) { return playerId == null ? null : captive.get(playerId); }

    /** Pay the ransom from the player's cash: released, and the standing with that gang cleared. */
    public boolean payRansom(Character who) {
        if (who == null || who.getCharacterInfo() == null || !authority()) return false;
        String pid = who.getCharacterInfo().characterId;
        Captivity c = captive.get(pid);
        if (c == null || !com.openworld.game.profile.Economy.transfer(com.openworld.game.profile.Profiles.of(who), null, c.ransom, com.openworld.game.profile.Economy.Reason.RANSOM)) return false;
        captive.remove(pid);
        states.remove(pid + "|" + c.gang);
        GD.print("GangSystem: " + pid + " paid a ransom of " + c.ransom + " dollars to " + c.gang);
        return true;
    }

    /** Past escape_start the captive is running (the guards open fire, + the escape heat); past escape_free, free. */
    private void tickCaptivity() {
        if (captive.isEmpty() || recovery == null) return;
        java.util.Iterator<Map.Entry<String, Captivity>> it = captive.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<String, Captivity> e = it.next();
            Player p = null;
            for (Player q : PlayerRegistry.getPlayers())
                if (q.getCharacterInfo() != null && e.getKey().equals(q.getCharacterInfo().characterId)) p = q;
            if (p == null) continue;                              // between bodies (a respawn): keep holding
            Captivity c = e.getValue();
            double d = p.getGlobalPosition().distanceTo(c.at);
            if (!c.escaping && d > recovery.escapeStart) {
                c.escaping = true;
                report(c.gang, "escape", e.getKey());
                applyFlips();
                GD.print("GangSystem: " + e.getKey() + " is escaping from " + c.gang);
            }
            if (d > recovery.escapeFree || !p.isAlive()) {
                it.remove();
                if (p.isAlive()) GD.print("GangSystem: " + e.getKey() + " escaped from " + c.gang);
            }
        }
    }

    /** The gang hunters' rules (gangs.json `hunters`), or null. */
    public DispatchRules hunterRules() { return hunters; }

    /** A NEW GAME: no gang is after anybody and nobody is held (game.FrontEnd; this node outlives the world scene). */
    public void clearAll() {
        states.clear();
        captive.clear();
    }

    /** Every gang this player stands at chase_at or more with, and the stars (the dispatch's hunters). */
    public Map<String, Integer> huntedBy(String playerId) {
        Map<String, Integer> out = new HashMap<>();
        if (rules == null) return out;
        for (String g : rules.gangs.keySet()) {
            GangRules.State s = states.get(playerId + "|" + g);
            if (s != null && rules.chases(s)) out.put(g, rules.starsFor(s.heat));
        }
        return out;
    }

    /** Set a player's stars with a gang outright (a probe, a perf run). */
    public void setStars(String playerId, String gang, int stars) {
        if (rules == null || !isGang(gang)) return;
        GangRules.State s = states.computeIfAbsent(playerId + "|" + gang, k -> new GangRules.State());
        s.heat = stars <= 0 ? 0.0 : rules.starsAt[Math.min(stars, rules.starsAt.length) - 1];
        s.lastCrimeAt = now;
    }

    public GangRules.Gang gang(String id) { return rules == null ? null : rules.gangs.get(id); }

    // ── probe / console surface ──
    /** This player fired a shot, as the firearm's seam publishes it -- probes. */
    @Register public void publishShotNow(String playerId) {
        GameplayEvents.publish(new GameplayEvent.WeaponFired(com.openworld.game.event.Actor.player(playerId, "player"),
                com.openworld.game.event.Spot.NOWHERE, "PIS1"));
    }
    @Register public boolean captiveNow(String playerId) { return captive.containsKey(playerId); }
    @Register public boolean escapingNow(String playerId) { Captivity c = captive.get(playerId); return c != null && c.escaping; }
    @Register public int ransomNow(String playerId) { Captivity c = captive.get(playerId); return c == null ? 0 : c.ransom; }
    @Register public boolean payRansomNow(Node who) { return who instanceof Character c && payRansom(c); }
    @Register public void setGangStarsNow(String playerId, String gang, int stars) { setStars(playerId, gang, stars); }
    @Register public int gangStarsNow(String playerId, String gang) { return starsOf(playerId, gang); }
    @Register public int feeNow(String playerId, String gang) { return feeOf(playerId, gang); }
    @Register public boolean reportNow(String gang, String crimeId, String playerId) { return report(gang, crimeId, playerId); }
}
