package com.openworld.game;

import com.openworld.character.Player;
import godot.core.Vector3;
import godot.global.GD;

import java.util.Map;

import static com.openworld.game.EnforcementDispatch.*;

/**
 * Who has each hunted player in SIGHT, per side, and the LOST / last-known / search state built on it (see "LOSING
 * THE POLICE" on {@link EnforcementDispatch}).
 *
 * <p>A part of {@link EnforcementDispatch} (PLAN.md P1e step 2, a move-only split): the state is the dispatch's
 * ({@code ed}), this holds the code.
 */
final class DispatchSight {

    private final EnforcementDispatch ed;

    DispatchSight(EnforcementDispatch ed) { this.ed = ed; }

    /** `side` (the police, a gang's hunters) has lost this player (see above). */
    boolean lost(String playerId, String side) {
        Sight s = ed.sightOf.get(playerId + "|" + side);
        return ed.searchPhase && s != null && s.lastKnown != null && s.lostFor >= LOST_GRACE;
    }

    /** Where `side` believes the player is: the last known position while it has lost them, else the player. */
    Vector3 believed(Player p, String side) {
        String id = p.getCharacterInfo().characterId;
        return lost(id, side) ? ed.sightOf.get(id + "|" + side).lastKnown : p.getGlobalPosition();
    }

    /** Where NEW units of `side` are sent: the last known position from the first tick nobody has the player in
     *  sight -- not after the grace. (Measured with probe_lose_police: with the grace here too, a player who had just
     *  got away was given a fresh unit 45-75 m off within 1.5 s, which saw them, and they were never lost.) */
    Vector3 sendTo(Player p, String side) {
        Sight s = ed.sightOf.get(p.getCharacterInfo().characterId + "|" + side);
        return ed.searchPhase && s != null && s.lastKnown != null && s.lostFor > 0 ? s.lastKnown : p.getGlobalPosition();
    }

    /** For the minimap: {x, z, radius m} of the disc the POLICE are searching for this player, or null while they
     *  have them in sight (or are not after them). The radius is the one {@link #searchTick} draws its points from. */
    public double[] searchArea(String playerId) {
        if (!lost(playerId, POLICE)) return null;
        Sight s = ed.sightOf.get(playerId + "|" + POLICE);
        return new double[] {s.lastKnown.getX(), s.lastKnown.getZ(), Math.min(SEARCH_MAX, SEARCH_START + SEARCH_GROW * s.lostFor)};
    }

    // ── being seen ───────────────────────────────────────────────────────────

    /** Who has each hunted player in SIGHT (see "LOSING THE POLICE"), per side: the police and every gang hunting
     *  them. Police in sight also stop the heat draining. There is no arrest by proximity any more (user 2026-10-07:
     *  police hunt the player down); a wanted player who goes DOWN is arrested by RecoveryRules. */
    void arrestsAndSight(Map<String, Player> players, Map<String, Map<String, Integer>> demand, WantedSystem ws,
                                 DispatchRules police, DispatchRules hunters) {
        java.util.Set<String> live = new java.util.HashSet<>();
        for (Player p : players.values()) {
            String id = p.getCharacterInfo().characterId;
            Vector3 pp = p.getGlobalPosition();
            for (String side : demand.getOrDefault(id, Map.of()).keySet()) {
                DispatchRules r = POLICE.equals(side) ? police : hunters;
                if (r == null) continue;
                String key = id + "|" + side;
                live.add(key);
                boolean seen = false;
                for (Unit u : ed.units) {
                    if (seen) break;
                    if (!side.equals(u.side) || !id.equals(u.playerId) || !GD.isInstanceValid(u.body) || u.body.isDead()) continue;
                    if (u.body.currentVehicleNode != null) continue;
                    seen = sees(u.body.getGlobalPosition(), pp, r.seenReach);
                }
                for (Car c : ed.cars) {
                    if (seen) break;
                    if (side.equals(c.side) && id.equals(c.playerId) && GD.isInstanceValid(c.car))
                        seen = sees(c.car.getGlobalPosition(), pp, r.seenReach);
                }
                for (Heli h : ed.helis) {
                    if (seen || !ed.searchPhase) break;
                    if (side.equals(h.side) && id.equals(h.playerId) && GD.isInstanceValid(h.h) && h.retiredFor == 0)
                        seen = h.h.getGlobalPosition().distanceTo(pp) <= HELI_SEEN_REACH
                                && ed.geometry.clearRay(h.h.getGlobalPosition(), pp.plus(new Vector3(0, 1.4, 0)));
                }
                Sight s = ed.sightOf.computeIfAbsent(key, k -> new Sight());
                if (s.lastKnown == null) s.lastKnown = pp;       // the crime itself was reported from somewhere
                boolean wasLost = lost(id, side);
                String who = POLICE.equals(side) ? "Police radio" : "Gang radio";
                if (seen) {
                    s.lastKnown = pp;
                    s.lostFor = 0;
                    if (POLICE.equals(side) && ws != null) ws.seen(id);
                    if (wasLost) {
                        ed.foundCount++;
                        s.lostSaid = false;
                        ed.say(id, who + ": there they are!");      // the wanted player's own screen (P1e step 4)
                    }
                } else {
                    s.lostFor += TICK;
                    if (lost(id, side) && !s.lostSaid) {
                        s.lostSaid = true;
                        ed.lostCount++;
                        ed.say(id, who + ": lost them -- search the area");
                    }
                }
            }
        }
        ed.sightOf.keySet().retainAll(live);
    }

    /** A body at `from` has the player at `to` in sight: within reach with a clear world line (or at arm's length,
     *  where a corner hides nobody). With {@link #searchPhase} off reach alone counts (the control). */
    boolean sees(Vector3 from, Vector3 to, double reach) {
        double d = from.distanceTo(to);
        if (d > reach) return false;
        return !ed.searchPhase || d <= HEAR_REACH || ed.geometry.clearLine(from, to);
    }
}
