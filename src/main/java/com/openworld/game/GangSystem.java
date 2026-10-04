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
 * members (the crowd's included) are hostile to players; at {@code chase_at} they hunt (the dispatch, not built).
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
    /** "playerId|gang" -> standing. */
    private final Map<String, GangRules.State> states = new HashMap<>();
    private final FactionFlips flips = new FactionFlips();
    private double now, flipIn;

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (FileAccess.fileExists(TABLE)) rules = GangRules.parse(FileAccess.getFileAsString(TABLE));
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
        Set<String> want = new HashSet<>();
        for (Map.Entry<String, GangRules.State> e : states.entrySet())
            if (rules.attacks(e.getValue())) want.add(e.getKey().substring(e.getKey().indexOf('|') + 1));
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
        if (fee <= 0 || who.cash < fee) return false;
        who.cash -= fee;
        states.remove(pid + "|" + gang);
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

    public GangRules.Gang gang(String id) { return rules == null ? null : rules.gangs.get(id); }

    // ── probe / console surface ──
    @Register public int gangStarsNow(String playerId, String gang) { return starsOf(playerId, gang); }
    @Register public int feeNow(String playerId, String gang) { return feeOf(playerId, gang); }
    @Register public boolean reportNow(String gang, String crimeId, String playerId) { return report(gang, crimeId, playerId); }
}
