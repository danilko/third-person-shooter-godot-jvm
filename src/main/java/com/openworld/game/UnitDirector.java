package com.openworld.game;

import com.openworld.ai.AIController;
import com.openworld.ai.character.ArrestState;
import com.openworld.ai.character.ChaseState;
import com.openworld.ai.character.PatrolState;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.Player;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import static com.openworld.game.EnforcementDispatch.*;
import static com.openworld.game.DispatchWorld.*;

/**
 * The units on foot, every tick: approach slots, the combat hand-over, the breach into a building, the search when
 * the player is lost, out of ammo and the restock, the wave attrition lull, attack tokens, standing down.
 *
 * <p>A part of {@link EnforcementDispatch} (PLAN.md P1e step 2, a move-only split): the state is the dispatch's
 * ({@code ed}), this holds the code.
 */
final class UnitDirector {

    private final EnforcementDispatch ed;

    UnitDirector(EnforcementDispatch ed) { this.ed = ed; }

    /** One searching unit: to its own point round the last known position; a new point when it gets there or tires. */
    void searchTick(Unit u, Player p, AIController brain) {
        Sight s = ed.sightOf.get(u.playerId + "|" + u.side);
        Vector3 b = u.body.getGlobalPosition();
        u.searchFor -= TICK;
        if (u.searchPoint == null || u.searchFor <= 0) {
            double radius = Math.min(SEARCH_MAX, SEARCH_START + SEARCH_GROW * s.lostFor);
            double a = ed.searchRng.nextDouble() * Math.PI * 2, r = radius * (0.35 + 0.65 * ed.searchRng.nextDouble());
            u.searchPoint = new Vector3(s.lastKnown.getX() + Math.sin(a) * r, s.lastKnown.getY(), s.lastKnown.getZ() + Math.cos(a) * r);
            u.searchFor = 5.0 + ed.searchRng.nextDouble() * 4.0;
        }
        brain.setPursuit(p);
        brain.pursuitAway = false;
        brain.pursuitVia.clear();
        brain.pursuitSearch = true;
        brain.pursuitPoint = u.searchPoint;
        brain.pursuitDirect = ed.geometry.clearLine(b, u.searchPoint);
        if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
        u.breachOf = null;
        u.breachDoor = null;
        u.sinceCloser = 0;                 // not stuck: it is not trying to close in
        u.closest = Double.MAX_VALUE;
    }

    void setSlot(Unit u, AIController brain, Character p, boolean melee, boolean interior) {
        if (!ed.approachSlots || interior) { brain.pursuitOffset = new Vector3(); return; }
        Vector3 pp = p.getGlobalPosition(), b = u.body.getGlobalPosition();
        if (Double.isNaN(u.slot)) {
            double base = Math.atan2(b.getX() - pp.getX(), b.getZ() - pp.getZ());
            u.slot = base + ((ed.slotCounter++ % 5) - 2) * SLOT_SPREAD;
        }
        double r = melee ? SLOT_RADIUS_MELEE : SLOT_RADIUS;
        brain.pursuitOffset = new Vector3(Math.sin(u.slot) * r, 0, Math.cos(u.slot) * r);
    }

    /** Where this unit is headed: its slot, or the player. */
    static Vector3 slotGoal(AIController brain, Character p) {
        Vector3 o = brain.pursuitOffset;
        return o != null && o.lengthSquared() > 0.01 ? p.getGlobalPosition().plus(o) : p.getGlobalPosition();
    }

    /** The player's ground speed this tick, measured from position (a probe or a seat moves the body, not velocity). */
    double playerSpeed(String id, Player p) { return ed.playerSpeeds.getOrDefault(id, 0.0); }

    void measurePlayerSpeeds(Map<String, Player> players) {
        for (Map.Entry<String, Player> e : players.entrySet()) {
            Vector3 now = e.getValue().getGlobalPosition();
            Vector3 was = ed.lastPlayerAt.put(e.getKey(), now);
            ed.playerSpeeds.put(e.getKey(), was == null ? 0.0 : flat(now, was) / TICK);
        }
    }

    // ── units on foot ─────────────────────────────────────────────────────────

    void tickUnits(Map<String, Player> players, Map<String, Map<String, Integer>> demand, WantedSystem ws,
                           DispatchRules police) {
        Map<String, Node3DRef> indoors = new HashMap<>();
        for (Map.Entry<String, Player> e : players.entrySet()) {
            Node b = ed.geometry.buildingAround(e.getValue().getGlobalPosition());
            // the building's interior navmesh is attached ON DEMAND, the first time a hunted player is inside it:
            // attached to every enterable building as it streamed, it cost ~1 ms p50 of frame on the walk / drive legs
            // (three ordered pairs, PLAN.md 1d) for regions nobody was using
            if (b instanceof godot.api.Node3D b3 && ed.interiorNav && !ed.units.isEmpty()) com.openworld.world.InteriorNav.attach(b3);
            indoors.put(e.getKey(), new Node3DRef(b));
        }
        Iterator<Unit> it = ed.units.iterator();
        while (it.hasNext()) {
            Unit u = it.next();
            if (!GD.isInstanceValid(u.body)) { ed.settle(u); it.remove(); continue; }
            Player p = players.get(u.playerId);
            Integer stars = p != null ? demand.getOrDefault(u.playerId, Map.of()).get(u.side) : null;
            GangSystem.Captivity held = u.guard && GangSystem.get() != null ? GangSystem.get().captivityOf(u.playerId) : null;
            if (u.guard) stars = p != null && held != null ? Integer.valueOf(1) : null;
            double far = nearestPlayer(u.body.getGlobalPosition());
            boolean seenNow = ed.geometry.inView(u.body.getGlobalPosition());
            // a unit DOWN in the fight is part of the wave's attrition (the lull's trigger, P1e step 1): counted once,
            // the tick it is first seen dead while still on a live call
            if (u.body.isDead() && !u.lossCounted && !u.guard && u.retiredFor == 0 && stars != null) {
                DispatchRules rd = POLICE.equals(u.side) ? police
                        : GangSystem.get() != null ? GangSystem.get().hunterRules() : null;
                if (rd != null) countLoss(u, stars, rd);
            }
            if (u.body.isDead() || stars == null || u.retiredFor > 0) {
                // retired: a corpse, a standing that is gone, or a unit that got stuck -- it leaves the scene, and
                // is freed out of view (never in front of anyone)
                if (!u.body.isDead() && u.retiredFor == 0) release(u, p);
                u.retiredFor += TICK;
                // out of view and away; or, a unit that cannot get clear (a wall behind it), after a while at a
                // distance; a corpse or a stuck unit is never left standing for good
                if ((!seenNow && (far > RETIRE_FAR || u.retiredFor > 30.0))
                        || (u.retiredFor > 45.0 && far > 20.0) || u.retiredFor > 90.0) { ed.settle(u); ed.spawner.free(u.body); it.remove(); }
                continue;
            }
            u.retiredFor = 0;
            DispatchRules r = POLICE.equals(u.side) ? police
                    : GangSystem.get() != null ? GangSystem.get().hunterRules() : null;
            if (!u.guard && r != null && far > r.despawnFar && !seenNow) { ed.settle(u); ed.spawner.free(u.body); it.remove(); continue; }
            if (u.body.currentVehicleNode != null) continue;   // still seated in a car on its way
            AIController brain = u.body.aiController();
            if (brain == null) continue;
            if (u.guard && !held.escaping) {        // covering the captive, weapon on them, not firing
                brain.setPursuit(p);
                brain.pursuitAway = false;
                brain.pursuitStand = true;
                if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
                continue;
            }
            brain.pursuitStand = false;
            brain.pursuitSearch = false;
            if (ed.sightlines.lost(u.playerId, u.side)) {
                // the player is LOST: a sniper holds with nothing on the radio, everybody else searches the area
                if (u.sniper) brain.setPursuit(null);
                else searchTick(u, p, brain);
                continue;
            }
            u.searchPoint = null;
            if (ed.dryRetreat && handleDry(u, p, brain, stars, r)) continue;
            // BREACH (PLAN.md W6): the player is inside a building -- follow them in, at ANY star level (user: always
            // get in, so the behaviour is consistent): through the building's door nearest this unit, straight (no
            // navmesh indoors), forcing a locked one
            Node3DRef in = indoors.get(u.playerId);
            Node ub = ed.geometry.buildingAround(u.body.getGlobalPosition());
            // standing on that building's interior navmesh counts as inside: a compound's yard (a police station, a
            // hospital) is under no roof, and routing again from there sent the unit back out through the gate
            if (in != null && in.node != null && ub != in.node && com.openworld.world.InteriorNav.has(in.node)
                    && com.openworld.world.InteriorNav.onMesh(u.body.getGlobalPosition())) ub = in.node;
            if (!u.sniper && ed.breaching && in != null && in.node != null) {
                if (ub != in.node) {
                    // no progress toward this door (a neighbour against the wall, a fence): give it up, take another
                    Vector3 here = u.body.getGlobalPosition();
                    if (u.breachMark == null || flat(here, u.breachMark) > 1.5) { u.breachMark = here; u.breachStill = 0; }
                    else if ((u.breachStill += TICK) > BREACH_STUCK_SECONDS && u.breachDoor != null) {
                        u.badDoors.add(u.breachDoor);
                        u.breachStill = 0;
                        brain.pursuitVia.clear();
                        ed.doorsGivenUp++;
                    }
                    if (u.breachOf != in.node || brain.pursuitVia.isEmpty()) {
                        if (u.breachOf != in.node) u.badDoors.clear();
                        brain.pursuitVia.clear();
                        brain.pursuitVia.addAll(breachRoute(in.node, u));
                        u.breachOf = in.node;
                        ed.breachRoutes++;
                    }
                    brain.setPursuit(p);
                    brain.pursuitAway = false;
                    brain.pursuitDirect = true;
                    if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
                    u.sinceCloser = 0;          // not stuck: on its way round to the door
                    continue;
                }
                // inside: the door waypoints were only the way IN -- from here the interior navmesh steers (left in,
                // a unit walked straight at a waypoint through the rooms and stood against a wall)
                if (u.breachOf == in.node && com.openworld.world.InteriorNav.has(in.node)) brain.pursuitVia.clear();
                if (u.breachOf == in.node && brain.pursuitVia.isEmpty()) { u.breachOf = null; ed.breachedIn++; }
            } else if (u.breachOf != null) {
                u.breachOf = null;
                u.breachDoor = null;
                brain.pursuitVia.clear();
            }
            // inside a building with an interior navmesh (world.InteriorNav), the unit steers on it: round shelves,
            // counters and rooms, which a straight line runs into (measured: stalled 6.8 m from the player)
            boolean interior = useInteriorNav(u.body, ub);
            if (u.sniper) {
                // a sniper holds its spot and shoots: the squad's radio says where the player is
                brain.setPursuit(null);
                AISquad sq = ed.spawner.squadFor(u.playerId, u.side);
                if (sq != null && p.isAlive()) sq.assignTarget(p, p.getGlobalPosition());
                continue;
            }
            boolean shoot = !POLICE.equals(u.side)
                    || (ws != null && ws.policeShoot(u.playerId));
            double dp = flat(u.body.getGlobalPosition(), p.getGlobalPosition());
            boolean inArrest = brain.getCurrentState() == ArrestState.INSTANCE;
            // a melee unit (the 1-star baton, PLAN.md 1g a) keeps the approach until it is at arm's length: the FSM's
            // chase stood baton officers 22 m off for good (it leans on the navmesh, as above)
            boolean melee = u.body.isMeleeEngagement();
            double engIn = melee ? MELEE_ENGAGE_IN : ENGAGE_IN, engOut = melee ? MELEE_ENGAGE_OUT : ENGAGE_OUT;
            if (shoot && (dp <= engIn || (!inArrest && dp <= engOut))) {
                // close enough: the combat FSM fights (chase / attack / suppress / search)
                brain.setPursuit(null);
                if (inArrest) brain.forceState(ChaseState.INSTANCE);
                AISquad sq = ed.spawner.squadFor(u.playerId, u.side);
                if (sq != null && p.isAlive()) sq.assignTarget(p, p.getGlobalPosition());
            } else if (shoot) {
                // closing in: the FSM's own chase leans on the navmesh and measured standing still 50-70 m out on
                // the island, so the approach is ArrestState's (straight where the line is clear), weapon up
                brain.setPursuit(p);
                brain.pursuitAway = false;
                setSlot(u, brain, p, melee, interior);
                brain.pursuitDirect = !interior && ed.geometry.clearLine(u.body.getGlobalPosition(), slotGoal(brain, p));
                if (!inArrest) brain.forceState(ArrestState.INSTANCE);
            } else {
                brain.setPursuit(p);
                brain.pursuitAway = false;
                setSlot(u, brain, p, melee, interior);
                brain.pursuitDirect = !interior && ed.geometry.clearLine(u.body.getGlobalPosition(), slotGoal(brain, p));
                if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
            }
            double d = flat(u.body.getGlobalPosition(), p.getGlobalPosition());
            // indoors a path winds round rooms, so the straight distance is not progress: a unit on the interior
            // navmesh that is MOVING is not stuck
            boolean walking = interior && flat(u.body.getVelocity(), Vector3.Companion.getZERO()) > 0.6;
            if (d < u.closest - STUCK_GAIN || d < 4.0 || walking) {
                u.closest = Math.min(u.closest, d);
                u.sinceCloser = 0;
            } else if (playerSpeed(u.playerId, p) < OUTRUN_SPEED && (u.sinceCloser += TICK) > STUCK_SECONDS
                    && brain.getCurrentState() == ArrestState.INSTANCE && !u.guard) {
                u.retiredFor = TICK;          // stuck: walk off, a fresh one comes
                release(u, p);
                ed.stuckGivenUp++;
            }
        }
    }

    /** Does the unit carry a firearm (anything not melee and not infinite)? */
    static boolean carriesFirearm(AICharacter b) {
        if (b.weaponController == null) return false;
        for (int i = 1; i < b.weaponController.getSlotCount(); i++) {
            var w = b.weaponController.getWeaponItem(i);
            if (w != null && !w.isInfiniteAmmo && w.getWeaponType() != com.openworld.weapon.WeaponType.MELEE) return true;
        }
        return false;
    }

    /** A unit that carries a firearm and has no round left in any of them. */
    static boolean isDry(AICharacter b) {
        if (!carriesFirearm(b)) return false;
        for (int i = 1; i < b.weaponController.getSlotCount(); i++) {
            var w = b.weaponController.getWeaponItem(i);
            if (w != null && !w.isInfiniteAmmo && w.getWeaponType() != com.openworld.weapon.WeaponType.MELEE
                    && (w.getMagazine() > 0 || w.getReserve() > 0)) return false;
        }
        return true;
    }

    /**
     * Out of ammo (1g b3). Returns true when this tick's steering is decided here. A dry unit within DRY_MELEE of its
     * player fights on (fists / baton, the FSM); otherwise it radios out and walks back to the nearest vehicle's spare
     * ammunition within supply_reach (a police car's trunk, an armoured vehicle's stowage -- the player's own stolen
     * one too), stands there restock_seconds and comes back full; with none in reach it leaves the fight. Either way
     * it counts toward the squad's regroup lull.
     */
    boolean handleDry(Unit u, Player p, AIController brain, int stars, DispatchRules r) {
        AICharacter b = u.body;
        if (u.restockAt != null) {
            var a = u.restockAt;
            if (!GD.isInstanceValid(a) || !a.isInsideTree() || a.stock <= 0 || supplyTaken(a)) {
                u.restockAt = null;            // the car was destroyed, emptied or taken: leave instead
                retireDry(u, p, stars, r);
                return true;
            }
            b.attackHeld = true;
            brain.setPursuit(p);
            brain.pursuitAway = false;
            if (a.reaches(b.getGlobalPosition())) {
                brain.pursuitVia.clear();
                brain.pursuitStand = true;
                u.restockFor += TICK;
                if (u.restockFor >= com.openworld.item.AmmoSupply.restockSeconds()) {
                    if (a.restock(b)) ed.restocksDone++;
                    u.restockAt = null;
                    u.restockFor = 0;
                    brain.pursuitStand = false;
                    b.attackHeld = false;
                    u.closest = Double.MAX_VALUE;
                    u.sinceCloser = 0;
                    return false;
                }
            } else {
                brain.pursuitStand = false;
                brain.pursuitDirect = true;
                brain.pursuitVia.clear();
                brain.pursuitVia.add(a.getGlobalPosition());
                u.sinceCloser = 0;             // walking to the car is not "stuck"
            }
            if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
            return true;
        }
        if (!isDry(b) || p == null || flat(b.getGlobalPosition(), p.getGlobalPosition()) <= DRY_MELEE) return false;
        countLoss(u, stars, r);
        com.openworld.item.AmmoSupply a = com.openworld.item.AmmoSupply.nearest(ed, b.getGlobalPosition(), r.supplyReach);
        if (a != null && !supplyTaken(a)) {
            u.restockAt = a;
            u.restockFor = 0;
            ed.dryRestocks++;
            ed.radio(p, u.side, "out of ammo, back to the car");
            return true;
        }
        retireDry(u, p, stars, r);
        return true;
    }

    /** A supply on a vehicle a player is in: not somewhere a unit walks up to. */
    static boolean supplyTaken(com.openworld.item.AmmoSupply a) {
        return a.getParent() instanceof Vehicle v && v.getOccupant() instanceof Player;
    }

    void retireDry(Unit u, Player p, int stars, DispatchRules r) {
        u.retiredFor = TICK;
        release(u, p);
        ed.dryRetreats++;
        ed.radio(p, u.side, "out of ammo, falling back");
    }

    /**
     * WAVE ATTRITION (PLAN.md P1e step 1; it was "half the units dry", which an AI with an unlimited reserve never is):
     * a unit DOWN or DRY counts against its wave; once half the units sent on this player and side since the last lull
     * are lost, the next wave is held back for regroup_seconds (the regroup lull, the player's breather). Not started
     * while armour or a helicopter is still on the player (they are the high-star pressure). Counted once a unit.
     */
    void countLoss(Unit u, int stars, DispatchRules r) {
        if (u.lossCounted) return;
        u.lossCounted = true;
        String key = u.playerId + "|" + u.side;
        int lost = ed.waveLost.merge(key, 1, Integer::sum);
        // the wave = what was lost since the last lull + every unit still in the fight (alive, on the call, not lost):
        // a unit that walked off stuck and was replaced is in neither
        int fighting = 0;
        for (Unit o : ed.units)
            if (key.equals(o.playerId + "|" + o.side) && !o.guard && !o.lossCounted && GD.isInstanceValid(o.body)
                    && !o.body.isDead() && o.retiredFor == 0) fighting++;
        int secs = r.regroupFor(stars);
        if (secs <= 0 || !DispatchRules.lullDue(lost, lost + fighting)) return;
        for (Heli h : ed.helis) if (u.playerId.equals(h.playerId) && GD.isInstanceValid(h.h) && h.retiredFor == 0) return;
        for (Car c : ed.cars) if (u.playerId.equals(c.playerId) && c.gun && GD.isInstanceValid(c.car)) return;
        ed.lullUntil.put(key, ed.clock + secs);
        ed.waveLost.put(key, 0);
        ed.lulls++;
        ed.radioIn.remove(u.playerId);
        ed.radio(u.playerId, u.side, "units regrouping -- " + secs + " s");
    }

    /** Hand out attack tokens per player and side: the nearest units in the fight attack, the rest hold (1g b2). */
    void assignTokens(Map<String, Player> players, Map<String, Map<String, Integer>> demand, DispatchRules police) {
        Map<String, List<Unit>> groups = new HashMap<>();
        for (Unit u : ed.units) {
            if (!GD.isInstanceValid(u.body) || u.body.isDead()) continue;
            boolean candidate = ed.attackTokens && !u.sniper && !u.guard && u.retiredFor == 0 && u.restockAt == null
                    && u.body.currentVehicleNode == null && u.body.aiController() != null
                    && u.body.aiController().getCurrentState() != ArrestState.INSTANCE;
            if (!candidate) {
                if (u.restockAt == null) u.body.attackHeld = false;
                u.tokenHeld = -1;
                continue;
            }
            groups.computeIfAbsent(u.playerId + "|" + u.side, k -> new ArrayList<>()).add(u);
        }
        for (Map.Entry<String, List<Unit>> e : groups.entrySet()) {
            List<Unit> g = e.getValue();
            Unit first = g.get(0);
            Player p = players.get(first.playerId);
            Integer stars = demand.getOrDefault(first.playerId, Map.of()).get(first.side);
            DispatchRules r = POLICE.equals(first.side) ? police
                    : GangSystem.get() != null ? GangSystem.get().hunterRules() : null;
            int n = r == null || stars == null ? 0 : r.tokensFor(stars);
            if (n > 0) n += attackTokenBonus;   // world density (host-decided); 0 stays "no limit"
            double[] dist = new double[g.size()], held = new double[g.size()], rest = new double[g.size()];
            for (int i = 0; i < g.size(); i++) {
                Unit u = g.get(i);
                if (u.tokenHeld >= TOKEN_HOLD) { u.tokenHeld = -1; u.tokenRest = TOKEN_REST; }   // give it back
                u.tokenRest = Math.max(0, u.tokenRest - TICK);
                dist[i] = p != null ? flat(u.body.getGlobalPosition(), p.getGlobalPosition()) : 0;
                held[i] = u.tokenHeld;
                rest[i] = u.tokenRest;
            }
            boolean[] give = DispatchRules.tokenHolders(dist, held, rest, n, TOKEN_HOLD);
            for (int i = 0; i < g.size(); i++) {
                Unit u = g.get(i);
                if (give[i]) u.tokenHeld = Math.max(0, u.tokenHeld) + TICK;
                else u.tokenHeld = -1;
                u.body.attackHeld = !give[i];
                if (!give[i]) ed.tokenHolds++;
            }
        }
    }

    /** Stand down: walk away from the player (ArrestState's away mode, straight, not by the navmesh), and be freed
     *  once out of view (tickUnits). */
    void release(Unit u, Player p) {
        AIController brain = u.body.aiController();
        u.body.clearTarget();
        if (brain == null) return;
        if (p != null && GD.isInstanceValid(p)) {
            brain.setPursuit(p);
            brain.pursuitAway = true;
            brain.forceState(ArrestState.INSTANCE);
        } else {
            brain.setPursuit(null);
            brain.forceState(PatrolState.INSTANCE);
        }
    }

    /** Put the unit's NavigationAgent3D on the interior map while it stands in a building that has one, else on the
     *  world map. Returns whether it is on the interior map. */
    boolean useInteriorNav(AICharacter body, Node building) {
        var a = body.getNavAgent();
        if (a == null) return false;
        boolean in = com.openworld.world.InteriorNav.has(building);
        godot.core.RID want = in ? com.openworld.world.InteriorNav.map()
                : (body.getWorld3d() != null ? body.getWorld3d().getNavigationMap() : null);
        if (want != null && !want.equals(a.getNavigationMap())) {
            a.setNavigationMap(want);
            body.aiController().clearNavTarget();
            if (in) ed.interiorSteers++;
        }
        return in;
    }

    /**
     * The way in for {@code u}: round the building's corners if its walls stand between the unit and the door, then
     * outside the door, then 2.5 m inside it (Door_* markers: -Z points out). The door is the cheapest of the
     * building's doors -- the walk there, plus {@link #DOOR_SHARE_COST} for every unit already going through it.
     * Every door is forced: unlocked and made automatic (a breach does not knock).
     */
    List<Vector3> breachRoute(Node building, Unit u) {
        List<Vector3> out = new ArrayList<>();
        Vector3 from = u.body.getGlobalPosition();
        java.util.Map<Node, Integer> taken = new java.util.HashMap<>();
        for (Unit w : ed.units) {
            if (w != u && w.breachOf == building && w.breachDoor != null && GD.isInstanceValid(w.body) && !w.body.isDead())
                taken.merge(w.breachDoor, 1, Integer::sum);
        }
        godot.api.Node3D best = null;
        List<Vector3> bestWay = null;
        double bd = Double.MAX_VALUE;
        // the baked walks round the neighbours to each side / back door (PLAN.md 1g f; the places record's door_paths)
        com.openworld.world.Places.Place place = building instanceof godot.api.Node3D bn
                ? com.openworld.world.Places.nearest(bn.getGlobalPosition(), 2.0) : null;
        for (Node c : building.getChildren()) {
            if (!(c instanceof godot.api.Node3D m) || !c.getName().toString().startsWith("Door_")) continue;
            if (u.badDoors.contains(m)) continue;
            List<Vector3> baked = place == null ? List.of() : place.doorPath(c.getName().toString());
            if (baked == null) continue;               // no walk reaches this door: never send anyone there
            List<Vector3> way = ed.geometry.pathAround(building, from, outsideOf(m));
            if (place != null && place.walk() != null && !ed.geometry.wayClear(from, way)) {
                // the corner route runs into a neighbour: the baked walk grid round the whole block, from where the
                // unit stands (WalkGrid; a unit spawned behind the block cannot even reach the FRONT by the corners)
                Vector3 to = outsideOf(m);
                List<double[]> walk = place.walk().path(from.getX(), from.getZ(), to.getX(), to.getZ());
                if (walk == null) continue;            // no walk from here to this door
                List<Vector3> via = new ArrayList<>();
                for (double[] q : walk) via.add(new Vector3(q[0], from.getY(), q[1]));
                via.set(via.size() - 1, to);
                way = via;
                ed.bakedRoutes++;
            }
            double d = routeLength(from, way) + DOOR_SHARE_COST * taken.getOrDefault(m, 0);
            if (d < bd) { bd = d; best = m; bestWay = way; }
        }
        if (best == null) {
            if (!u.badDoors.isEmpty()) { u.badDoors.clear(); return breachRoute(building, u); }   // every door tried: again
            return out;
        }
        u.breachDoor = best;
        Vector3 c = best.getGlobalPosition();
        Vector3 o = outsideOf(best).minus(c).normalized();
        out.addAll(bestWay != null ? bestWay : ed.geometry.pathAround(building, from, outsideOf(best)));
        out.add(c.minus(o.times(2.5)));
        ed.geometry.forceDoorsNear(building, c, Double.MAX_VALUE);   // a breach does not knock: every door of the building
        return out;
    }
}
