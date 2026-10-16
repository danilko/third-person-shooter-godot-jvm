package com.openworld.game;

import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * RADIO ITEMS (PLAN.md P1e step 7, user 2026-10-15: "keeps working, LOST on respawn (arrest takes it too), must be
 * obtained again"). A player who has a force's radio hears that force's OTHER incidents -- the ones not about them;
 * the wanted player always hears their own escape cues without one (EnforcementDispatch.say) -- as a line of radio
 * chatter and a marker on the minimap while the incident lasts (the minimal-HUD rule: a line and a marker on change,
 * no new widget).
 * <ul>
 *   <li><b>A police scanner</b> comes with a patrol car: sitting in one (forces.json {@code radio.police_vehicles})
 *   takes it.</li>
 *   <li><b>A gang's radio</b> comes off one of its members' bodies: standing over a dead one takes it.</li>
 *   <li><b>Faction membership</b> gives the channel outright: a player whose faction is a force (an undercover
 *   career, a mission's faction swap) hears it while they are one.</li>
 * </ul>
 * The HOST decides who has what and sends each incident only to the peers whose player has its channel
 * ({@link GameManager#WORLD_EVENT_INCIDENT}). Session-only: never saved; a respawn ({@link #lose}) takes it all.
 */
final class RadioNet {

    private final EnforcementDispatch ed;

    RadioNet(EnforcementDispatch ed) { this.ed = ed; }

    /** Per player: the channels their radios give ("police", a gang id). */
    private final Map<String, Set<String>> owned = new HashMap<>();
    /** Per player: incidents already told (an incident is told once, however many acts merge into it). */
    private final Map<String, Set<Integer>> told = new HashMap<>();
    int linesSent, itemsTaken;
    private double scanIn;

    private static final double PICKUP_REACH = 1.8, MARKER_SECONDS = 45.0;

    private static Set<String> policeVehicles() {
        com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
        return f != null && f.radioVehicles() != null ? f.radioVehicles() : Set.of("POC1", "MPC1", "ARV1");
    }

    /** The channels a player hears now: their radios, and their own faction if it is a force. */
    Set<String> channels(Player p) {
        Set<String> out = new LinkedHashSet<>(owned.getOrDefault(id(p), Set.of()));
        String f = p.getCharacterInfo() != null ? p.getCharacterInfo().faction : "";
        if (Faction.POLICE.equals(f) || (GangSystem.get() != null && GangSystem.get().isGang(f))) out.add(f);
        return out;
    }

    private static String id(Player p) { return p.getCharacterInfo() != null ? p.getCharacterInfo().characterId : ""; }

    /** A respawn (death, arrest, abduction): every radio is gone, it must be obtained again. */
    void lose(String playerId) {
        owned.remove(playerId);
        told.remove(playerId);
    }

    /** Give a channel outright (a probe, a mission reward). */
    void give(String playerId, String channel) {
        if (owned.computeIfAbsent(playerId, k -> new LinkedHashSet<>()).add(channel)) itemsTaken++;
    }

    /** Each dispatch tick, on the host: radios taken, then the new incidents told to whoever hears them. */
    void tick(Map<String, Player> players) {
        scanIn -= EnforcementDispatch.TICK;
        if (scanIn <= 0) {
            scanIn = 0.5;
            for (Player p : players.values()) takeRadios(p);
        }
        List<IncidentBoard.Incident> live = ed.incidents().live(ed.clock);
        if (live.isEmpty()) return;
        for (Player p : players.values()) {
            String pid = id(p);
            Set<String> ch = channels(p);
            if (ch.isEmpty()) continue;
            Set<Integer> done = told.computeIfAbsent(pid, k -> new HashSet<>());
            for (IncidentBoard.Incident i : live) {
                if (done.contains(i.id) || pid.equals(i.source)) continue;   // only OTHER incidents
                String channel = heardOn(i, ch);
                if (channel == null) continue;
                done.add(i.id);
                tell(p, channel, i);
            }
        }
    }

    /** Which of these channels hears this incident (null = none): the police hear attacks on officers and
     *  civilians and anything they answer; a gang hears what is done to or by its members. */
    private static String heardOn(IncidentBoard.Incident i, Set<String> ch) {
        if (ch.contains(Faction.POLICE) && (Faction.POLICE.equals(i.victim) || "civilian_attacked".equals(i.type)
                || "police_attacked".equals(i.type) || "trespass".equals(i.type))) return Faction.POLICE;
        for (String c : ch) if (!Faction.POLICE.equals(c) && (c.equals(i.victim) || c.equals(i.attacker))) return c;
        return null;
    }

    private void tell(Player p, String channel, IncidentBoard.Incident i) {
        String where = placeName(i.x, i.z);
        String what = switch (i.type) {
            case "gang_attack" -> (Faction.PLAYER.equals(i.attacker) ? "someone" : i.attacker) + " hit " + i.victim;
            case "police_attacked" -> "officer under fire";
            case "civilian_attacked" -> "shots fired";
            default -> i.type.replace('_', ' ');
        };
        ed.radio(id(p), channel, what + (where.isEmpty() ? "" : " near " + where));
        RadioMarkers.post(ed, id(p), i.type, i.x, i.z, MARKER_SECONDS);
        linesSent++;
    }

    /** The nearest named place within 400 m, else the district, else "". */
    private static String placeName(double x, double z) {
        com.openworld.world.Places.Place pl = com.openworld.world.Places.nearest(new Vector3(x, 0, z), 400.0);
        if (pl != null) return pl.name();
        String r = com.openworld.world.Places.regionAt(x, z);
        return r == null ? "" : r;
    }

    /** A patrol car sat in, or a dead member stood over: that radio is theirs. */
    private void takeRadios(Player p) {
        if (!p.isAlive()) return;
        String pid = id(p);
        if (p.currentVehicleNode instanceof Vehicle v) {
            String stem = v.getSceneFilePath() == null ? "" : v.getSceneFilePath().toString();
            stem = stem.substring(stem.lastIndexOf('/') + 1).replace(".tscn", "");
            if (policeVehicles().contains(stem) && !owned.getOrDefault(pid, Set.of()).contains(Faction.POLICE)) {
                give(pid, Faction.POLICE);
                ed.say(pid, "Picked up a POLICE SCANNER -- you hear their radio until you go down");
            }
            return;
        }
        GangSystem gs = GangSystem.get();
        com.openworld.world.SpatialEntityGrid grid = com.openworld.world.SpatialEntityGrid.get();
        if (gs == null || grid == null) return;
        List<Node> near = new ArrayList<>();
        grid.queryRadius(p.getGlobalPosition(), (float) PICKUP_REACH, near);
        for (Node n : near) {
            if (!(n instanceof AICharacter ai) || ai.isAlive() || ai.getCharacterInfo() == null) continue;
            String g = ai.getCharacterInfo().faction;
            if (!gs.isGang(g) || owned.getOrDefault(pid, Set.of()).contains(g)) continue;
            give(pid, g);
            ed.say(pid, "Took a " + g.toUpperCase(java.util.Locale.ROOT) + " RADIO off the body -- you hear their radio until you go down");
        }
    }

    /** "channels" for a player, comma separated (probe readout). */
    String channelsOf(String playerId) {
        for (Player p : PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && playerId.equals(id(p))) return String.join(",", channels(p));
        return String.join(",", owned.getOrDefault(playerId, Set.of()));
    }
}
