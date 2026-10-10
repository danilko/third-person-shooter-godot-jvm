package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Player;
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

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (FileAccess.fileExists(TABLE)) {
            String text = FileAccess.getFileAsString(TABLE);
            rules = GangRules.parse(text);
            hunters = DispatchRules.parse(text, "hunters");
            String crimes = FileAccess.fileExists(WantedSystem.TABLE) ? FileAccess.getFileAsString(WantedSystem.TABLE) : null;
            recovery = RecoveryRules.parse(crimes, text);
        }
    }

    @Register
    @Override
    public void _exitTree() {
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
        Set<String> want = new HashSet<>();
        for (Map.Entry<String, GangRules.State> e : states.entrySet())
            if (rules.attacks(e.getValue())) want.add(e.getKey().substring(e.getKey().indexOf('|') + 1));
        // a gang holding a player who has not run does not shoot them (the guards stand over the captive)
        for (Captivity c : captive.values()) if (!c.escaping) want.remove(c.gang);
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

    /** Health's seam: a gang member was hurt / killed by someone (only a player's hit counts). */
    public void reportHit(Character victim, String attackerId, boolean killed) {
        if (victim == null || victim instanceof Player || victim.getCharacterInfo() == null) return;
        String f = victim.getCharacterInfo().faction;
        if (!isGang(f)) return;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (p.getCharacterInfo() != null && attackerId.equals(p.getCharacterInfo().characterId)) {
                report(f, killed ? "kill_member" : "hit_member", attackerId);
                return;
            }
        }
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
        GD.print("GangSystem: " + pid + " paid " + fee + " yen to " + gang);
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
        GD.print("GangSystem: " + playerId + " held by " + gang + ", ransom " + ransom + " yen");
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
        GD.print("GangSystem: " + pid + " paid a ransom of " + c.ransom + " yen to " + c.gang);
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
    @Register public boolean captiveNow(String playerId) { return captive.containsKey(playerId); }
    @Register public boolean escapingNow(String playerId) { Captivity c = captive.get(playerId); return c != null && c.escaping; }
    @Register public int ransomNow(String playerId) { Captivity c = captive.get(playerId); return c == null ? 0 : c.ransom; }
    @Register public boolean payRansomNow(Node who) { return who instanceof Character c && payRansom(c); }
    @Register public void setGangStarsNow(String playerId, String gang, int stars) { setStars(playerId, gang, stars); }
    @Register public int gangStarsNow(String playerId, String gang) { return starsOf(playerId, gang); }
    @Register public int feeNow(String playerId, String gang) { return feeOf(playerId, gang); }
    @Register public boolean reportNow(String gang, String crimeId, String playerId) { return report(gang, crimeId, playerId); }
}
