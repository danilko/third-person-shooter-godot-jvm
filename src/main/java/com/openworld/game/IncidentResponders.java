package com.openworld.game;

import com.openworld.character.AICharacter;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.game.event.GameplayEvent;
import com.openworld.game.event.GameplayEvents;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import static com.openworld.game.DispatchWorld.*;

/**
 * INCIDENTS FROM WHAT HAPPENS, AND WHO ANSWERS THEM (PLAN.md P1e steps 4 + 6). Every hurt and kill arrives as a
 * {@link GameplayEvent}; this puts it on the dispatch's {@link IncidentBoard}:
 * <ul>
 *   <li>a PLAYER's act -- an incident, for the radio to tell of (the stars and the gang standing that answer it are
 *   the wanted level's and the gangs' own);</li>
 *   <li>an AI attacking an AI -- an incident only NEAR A PLAYER (within the board's near_players: nothing happens
 *   off-screen; no abstract gang wars), never a lawful or on-duty act (the police's, any dispatched unit's, a hit on
 *   one's own faction), merged by area and rate-limited by the board. A NEW one is ANSWERED (forces.json
 *   {@code incidents.responders}): a gang answers any attack on its members (user 2026-10-15: "by a player OR another
 *   gang"), the police an attack on an officer or a civilian. Responders are drawn from that force's stations (the
 *   pools cap it) and the global body cap, set down out of view round the place, and patrol there with the ordinary
 *   FSM -- they fight whoever is hostile to them; they leave once the incident is over and nobody sees them.</li>
 * </ul>
 * A part of {@link EnforcementDispatch}; subscribed in the OBSERVER phase (a sanctioned act is no incident).
 */
final class IncidentResponders {

    private final EnforcementDispatch ed;

    IncidentResponders(EnforcementDispatch ed) { this.ed = ed; }

    /** Off = the control: AI-vs-AI acts raise nothing and nobody answers them. */
    boolean enabled = true;

    private static final class Responder {
        AICharacter body;
        String side;
        IncidentBoard.Incident incident;
        ForcePools.Station origin;
    }

    private final List<Responder> responders = new ArrayList<>();
    int answered, aiIncidents, playerIncidents;

    final GameplayEvents.Subscriber onEvent = this::onEvent;

    private void onEvent(GameplayEvent e, GameplayEvents.Ruling ruling) {
        if (ruling.sanctioned()) return;
        com.openworld.game.event.Actor by, to;
        if (e instanceof GameplayEvent.Damaged d) { by = d.actor(); to = d.target(); }
        else if (e instanceof GameplayEvent.Killed k) { by = k.actor(); to = k.target(); }
        else return;
        if (by.isNone() || to.isNone() || to.isPlayer()) return;
        String type = typeOf(to.faction());
        if (type == null) return;
        Vector3 at = com.openworld.game.event.Actors.vec(e.at());
        if (by.isPlayer()) {
            // a player's act: on the board for the radio (the stars / the gang standing answer it)
            IncidentBoard.Raised r = ed.incidents().raise(type, at.getX(), at.getZ(), to.faction(), Faction.PLAYER, by.id(), ed.clock);
            if (r != null && r.isNew()) playerIncidents++;
            return;
        }
        if (!enabled) return;
        // an AI on an AI: lawful and on-duty acts are not incidents, nor is a hit on one's own side
        String af = by.faction();
        if (af == null || af.isEmpty() || Faction.POLICE.equals(af) || af.equals(to.faction()) || ed.onDuty(by.id())) return;
        IncidentBoard.Rules rules = rules();
        if (nearestPlayer(at) > rules.nearPlayers()) return;          // nothing happens off-screen
        IncidentBoard.Raised r = ed.incidents().raise(type, at.getX(), at.getZ(), to.faction(), af, "", ed.clock);
        if (r == null || !r.isNew()) return;
        aiIncidents++;
        answer(r.incident(), rules);
    }

    /** Which incident an attack on {@code victim} is: on a gang's member, an officer, a civilian; null = none. */
    private static String typeOf(String victim) {
        GangSystem gs = GangSystem.get();
        if (gs != null && gs.isGang(victim)) return "gang_attack";
        if (Faction.POLICE.equals(victim)) return "police_attacked";
        if (Faction.CIVILIAN.equals(victim) || Faction.NEUTRAL.equals(victim)) return "civilian_attacked";
        return null;
    }

    private static IncidentBoard.Rules rules() {
        com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
        return f != null && f.incidents() != null ? f.incidents() : IncidentBoard.Rules.DEFAULT;
    }

    /** Send the incident's responders: drawn from the force's stations, out of view round the place. */
    private void answer(IncidentBoard.Incident inc, IncidentBoard.Rules rules) {
        IncidentBoard.Responder spec = rules.responders().get(inc.type);
        if (spec == null || spec.units() <= 0) return;
        String side = "victim".equals(spec.force()) ? inc.victim : spec.force();
        if (side == null || side.isEmpty()) return;
        inc.answered = true;
        answered++;
        Vector3 at = new Vector3(inc.x, 0, inc.z);
        Vector3 g = ed.geometry.ground(inc.x, inc.z, nearestPlayerY(at));
        if (g != null) at = g;
        int keep = ed.bodyStars;
        ed.bodyStars = 2;
        for (int i = 0; i < spec.units() && ed.bodyRoom() > 0; i++) {
            Vector3 spot = ed.spawner.footSpot(at, 25.0, 55.0);
            if (spot == null) break;
            ForcePools.Draw dr = ed.forcePools ? ed.pools().draw(side, 2, inc.x, inc.z) : new ForcePools.Draw(null, null);
            if (dr == null) break;                              // the force is spent here: nobody answers
            ed.outfitOverride = dr.tier() != null ? dr.tier().outfit() : "";
            DispatchRules r = Faction.POLICE.equals(side) ? policeRules() : hunterRules();
            String w = r == null ? "PIS1" : ed.spawner.weaponFor(side, "", r, WantedSystem.get(), 2);
            AICharacter ai = ed.spawner.spawnBody(side, spot, w.isEmpty() ? "PIS1" : w);
            ed.outfitOverride = "";
            if (ai == null) { ed.settle(dr.station(), true); break; }
            com.openworld.ai.AIBehaviorConfig cfg = new com.openworld.ai.AIBehaviorConfig();
            cfg.patrolRadius = 18f;
            ai.behaviorConfig = cfg;
            Responder x = new Responder();
            x.body = ai;
            x.side = side;
            x.incident = inc;
            x.origin = dr.station();
            responders.add(x);
        }
        ed.bodyStars = keep;
        String who = Faction.POLICE.equals(side) ? "police" : side;
        ed.radio("", side, inc.type.replace('_', ' ') + " -- " + who + " units responding");
    }

    private static DispatchRules policeRules() {
        WantedSystem ws = WantedSystem.get();
        return ws != null ? ws.dispatchRules() : null;
    }

    private static DispatchRules hunterRules() {
        GangSystem gs = GangSystem.get();
        return gs != null ? gs.hunterRules() : null;
    }

    private static double nearestPlayerY(Vector3 at) {
        double best = Double.MAX_VALUE, y = at.getY();
        for (Player p : PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && flat(at, p.getGlobalPosition()) < best) { best = flat(at, p.getGlobalPosition()); y = p.getGlobalPosition().getY(); }
        return y;
    }

    /** Each tick: responders whose incident is over walk off and are freed out of view (the living go back to their
     *  stations); a corpse is lost to its station and freed out of view. */
    void tick() {
        for (Iterator<Responder> it = responders.iterator(); it.hasNext(); ) {
            Responder x = it.next();
            if (!GD.isInstanceValid(x.body)) { ed.settle(x.origin, false); it.remove(); continue; }
            boolean over = x.body.isDead() || !ed.incidents().isLive(x.incident, ed.clock);
            if (!over) continue;
            Vector3 b = x.body.getGlobalPosition();
            if (!ed.geometry.inView(b) && nearestPlayer(b) > 40.0) {
                ed.settle(x.origin, !x.body.isDead());
                ed.spawner.free(x.body);
                it.remove();
            }
        }
    }

    /** Live responders (the load, a probe). */
    int live() {
        int n = 0;
        for (Responder x : responders) if (GD.isInstanceValid(x.body) && !x.body.isDead()) n++;
        return n;
    }

    /** Is {@code characterId} one of these responders (on duty: its own shots are not new incidents)? */
    boolean isResponder(String characterId) {
        for (Responder x : responders)
            if (GD.isInstanceValid(x.body) && x.body.getCharacterInfo() != null && characterId.equals(x.body.getCharacterInfo().characterId))
                return true;
        return false;
    }

    void clear() { responders.clear(); }
}
