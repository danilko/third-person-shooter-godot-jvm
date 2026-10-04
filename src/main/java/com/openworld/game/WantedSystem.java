package com.openworld.game;

import com.openworld.character.Character;
import com.openworld.character.Faction;
import com.openworld.character.Player;
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
 * The wanted level (PLAN.md W5, user decisions 2026-10-03): stars 0-6 per player, from HEAT that crimes add and that
 * drains once the player has kept out of trouble for a while. The rules and the crime table are
 * {@link WantedRules} over {@code game/crimes.json}; this node only owns the per-player state and the seams.
 *
 * <p>Owned by the AUTHORITATIVE peer (single player or the host), where damage is applied: the seams that report a
 * crime run only there. Built in code by {@link GameManager} (a child of the AutoLoad), reached through {@link #get()}.
 *
 * <p>Seams today: damage to a police officer or a civilian by a player ({@code Health.applyDamage}), a player's
 * gunshot ({@code StimulusManager.post}). Adding a crime = one row in the table + one {@link #report} call.
 *
 * <p>LETHAL crimes (a robbery, a dead policeman) make police shoot the player on sight until the heat is gone
 * (`applyHostility`), and no arrest is offered meanwhile. Gangs are a separate standing: {@link GangSystem}.
 *
 * <p>Not done yet (PLAN.md W5): replication to clients (a client's HUD shows no stars), police dispatch, the arrest trigger.
 */
@Script(className = "WantedSystem")
public class WantedSystem extends Node {

    public static final String TABLE = "res://src/main/resources/com/openworld/game/crimes.json";

    private static WantedSystem instance;

    public static WantedSystem get() {
        return instance != null && GD.isInstanceValid(instance) ? instance : null;
    }

    private WantedRules rules;
    private final Map<String, WantedRules.State> states = new HashMap<>();
    private double now;
    private final List<Node> scratch = new ArrayList<>();
    private final FactionFlips flips = new FactionFlips();
    private double toggleIn;

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (FileAccess.fileExists(TABLE)) rules = WantedRules.parse(FileAccess.getFileAsString(TABLE));
        else GD.print("WantedSystem: no crime table at " + TABLE);
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
        for (WantedRules.State s : states.values()) rules.tick(s, now, delta);
        toggleIn -= delta;
        if (toggleIn <= 0) {
            toggleIn = 0.5;
            applyHostility();
        }
    }

    /** Police are HOSTILE to players while any player is lethal-wanted (FactionFlips restores them after). */
    private void applyHostility() {
        java.util.Set<String> want = new java.util.HashSet<>();
        for (WantedRules.State st : states.values()) if (st.lethal) want.add(Faction.POLICE);
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
        boolean witnessed = !c.witness() || witnessed(where, who);
        WantedRules.State s = states.computeIfAbsent(playerId, k -> new WantedRules.State());
        int before = rules.starsFor(s.heat);
        boolean ok = rules.report(s, crimeId, witnessed, now);
        int after = rules.starsFor(s.heat);
        if (ok && after != before) GD.print("WantedSystem: " + who.getName() + " " + crimeId + " -> " + after + " star(s)");
        return ok;
    }

    /** The crime a hit on {@code victim} by a player is ("" none): police and civilians only. */
    public static String crimeForHit(Character victim, boolean killed) {
        if (victim == null || victim instanceof Player || victim.getCharacterInfo() == null) return "";
        String f = victim.getCharacterInfo().faction;
        if (Faction.POLICE.equals(f)) return killed ? "kill_police" : "assault_police";
        if (Faction.NEUTRAL.equals(f) || Faction.CIVILIAN.equals(f)) return killed ? "murder" : "assault";
        return "";
    }

    /** Health's seam: a hit was applied (authority). */
    public void reportHit(Character victim, String attackerId, boolean killed) {
        String crime = crimeForHit(victim, killed);
        if (crime.isEmpty()) return;
        report(crime, victim.getGlobalPosition(), attackerId);
    }

    /** Anyone but the offender within the witness radius saw it (a living, non-player character). */
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

    /** Clear a player's wanted level (a jail respawn, a mission script). */
    public void clear(String playerId) {
        WantedRules.State s = states.get(playerId);
        if (s != null) s.clear();
        applyHostility();
    }

    // ── probe / console surface ──
    @Register public int starsNow(String playerId) { return starsOf(playerId); }
    @Register public boolean reportNow(String crimeId, String playerId) {
        Character who = findPlayer(playerId);
        return who != null && report(crimeId, who.getGlobalPosition(), playerId);
    }
    @Register public void clearNow(String playerId) { clear(playerId); }
    @Register public boolean lethalNow(String playerId) { return isLethal(playerId); }
}
