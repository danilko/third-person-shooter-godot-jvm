package com.openworld.game;

import com.openworld.ai.AIController;
import com.openworld.ai.character.ArrestState;
import com.openworld.ai.character.ChaseState;
import com.openworld.ai.character.PatrolState;
import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.item.WeaponGrant;
import com.openworld.net.NetworkManager;
import com.openworld.util.CollisionLayers;
import com.openworld.world.RoadGraph;
import com.openworld.world.RoadMap;
import com.openworld.world.Sidewalks;
import com.openworld.world.ZoneManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.UUID;

/**
 * THE ENFORCEMENT DISPATCH (PLAN.md W5; user 2026-10-06: build it first so peak performance can be measured with
 * police and gangs in the ring). The authoritative peer turns each player's standing into UNITS round them:
 *
 * <ul>
 *   <li><b>Police</b>, from the wanted stars ({@code crimes.json} {@code dispatch}): officers on foot appear out of
 *   view between {@code foot_min} and {@code foot_max} of the player, and patrol cars (POC1 / MPC1, a driver and a
 *   partner) on a lane further out drive the ROAD route to the player ({@link VehicleAIController#setPlan}), brake
 *   within {@code arrive_dist} and their crew gets out. Police HUNT the player down (user 2026-10-07): from {@code
 *   shoot_at} stars (1) the police faction is hostile to players ({@link WantedSystem}), units close in with {@link
 *   ArrestState}'s approach and fight with the ordinary
 *   FSM, told where the player is by their squad's radio ({@link AISquad#assignTarget}). Police in sight of the
 *   player stop the heat draining ({@link WantedSystem#seen}).</li>
 *   <li><b>Gangs</b>, from each gang's stars with the player at {@code chase_at} or more ({@code gangs.json}
 *   {@code hunters}): the same, always shooting, in civilian cars.</li>
 * </ul>
 *
 * <p>Units are not ambient: no zone keeps them. They are freed out of view past {@code despawn_far}, and once the
 * standing that called them is gone. The load is reported to {@link ZoneManager#setEnforcementLoad}, which thins
 * the ambient traffic and promoted walkers by as much -- the GTA rule, so a chase does not stack police on a full
 * street. Built in code by {@link GameManager}, a child of the AutoLoad.
 */
@Script(className = "EnforcementDispatch")
public class EnforcementDispatch extends Node {

    /** Extra units that may attack one player at once, on top of the table's tokens_by_stars: the host's
     *  {@link WorldDensity} (QualitySettings.applyDensity). 0 = the table as authored. */
    public static int attackTokenBonus = 0;
    @Register public int attackTokenBonusNow() { return attackTokenBonus; }


    static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    private static final String POLICE = Faction.POLICE;
    private static final double TICK = 0.25;
    /** A unit retired by a standing that is gone, or a corpse, is freed out of view past this (m). */
    private static final double RETIRE_FAR = 40.0;
    /** A car that has not arrived after this long is given up (s). */
    private static final double CAR_GIVE_UP = 75.0;
    /** Re-plan a car's road route this often (s), as the player moves. */
    private static final double REPLAN = 3.0;

    private static EnforcementDispatch instance;

    public static EnforcementDispatch get() {
        return instance != null && GD.isInstanceValid(instance) ? instance : null;
    }

    /** Off = no units (the control: stars still count, nobody comes). */
    @Export public boolean enabled = true;
    /** Units follow a player INTO a building through its door (always; off = the control: they stop outside). */
    @Export public boolean breaching = true;
    /** Interior navmeshes for breaching units (world.InteriorNav); off = the straight-line breach (the control). */
    @godot.annotation.Visible public boolean interiorNav = true;
    /** Attack tokens (PLAN.md 1g b2): only tokens_by_stars units attack one player at once. Off = everyone attacks. */
    @godot.annotation.Visible public boolean attackTokens = true;
    /** Out of ammo (1g b3): walk back to a vehicle's spare ammunition or leave, and the regroup lull. Off = a dry unit
     *  fights on with its fists. */
    @godot.annotation.Visible public boolean dryRetreat = true;
    public boolean getInteriorNav() { return interiorNav; }
    public void setInteriorNav(boolean v) { interiorNav = v; com.openworld.world.InteriorNav.enabled = v; }
    /** Foot units spawned per side per spawn tick, at most. */
    @Export public int spawnPerTick = 2;

    private static final class Unit {
        AICharacter body;
        String side, playerId;
        double retiredFor;
        /** A guard over a captive (an abduction): stands until the captive runs or pays. */
        boolean guard;
        /** Closest it has come to its player, and how long since it last closed in (stuck detection). */
        double closest = Double.MAX_VALUE, sinceCloser;
        /** A sniper (PLAN.md W6): placed at range on a clear line, holds there and shoots; never closes in. */
        boolean sniper;
        /** Attack token: seconds held (negative = none), seconds it must wait after giving one back (1g b2). */
        double tokenHeld = -1, tokenRest;
        /** Walking back to restock at this vehicle's spare ammunition, and how long it has stood there (1g b3). */
        com.openworld.item.AmmoSupply restockAt;
        double restockFor;
        /** The building it is breaching (its player is inside), or null. */
        Node breachOf;
        /** The door marker this unit is breaching through: units are spread over a building's doors. */
        Node breachDoor;
        /** Doors this unit could not reach (no progress for BREACH_STUCK_SECONDS): skipped by the next route. */
        final java.util.Set<Node> badDoors = new java.util.HashSet<>();
        Vector3 breachMark;
        double breachStill;
        /** Its approach slot: a bearing round the player (radians, NaN = not chosen yet), PLAN.md 1i. */
        double slot = Double.NaN;
        /** SEARCHING: the point it is walking to round the last known position, and how long it keeps it. */
        Vector3 searchPoint;
        double searchFor;
    }

    // ── LOSING THE POLICE -- and a gang's hunters (user, 2026-10-10: "even 1 to 3 stars cannot lose the police
    //    engagement"; then "do the same for gang / other engagement members to save overall resources") ──────
    //
    // Two things made it impossible: "seen" was any police body within seen_reach, THROUGH walls, and every unit
    // steered by the player's true position, so one was always within reach and the calm clock never ran. Now:
    //  * SEEN is a police body within seen_reach WITH a clear world line to the player (or within HEAR_REACH: round a
    //    corner at arm's length is not hidden), a patrol car likewise, a helicopter with a clear line from the air;
    //  * a player not seen for LOST_GRACE is LOST: police units stop steering by them and SEARCH -- each walks to its
    //    own point in a disc round the LAST KNOWN position that grows with the time lost, stands, picks another;
    //    new units and cars are sent to that position, not to the player; nothing rams or fights what it cannot see;
    //  * any of them getting a line again ends it at once: the chase is back on and the calm clock restarts.
    // The heat itself is WantedRules' (calm period, then the drain). `searchPhase` off = the old all-knowing dispatch.

    /** Off is the control: units always know where the player is, and reach alone keeps the heat up. */
    @godot.annotation.Visible public boolean searchPhase = true;
    static final double LOST_GRACE = 2.5, HEAR_REACH = 9.0, HELI_SEEN_REACH = 140.0;
    static final double SEARCH_START = 8.0, SEARCH_GROW = 1.0, SEARCH_MAX = 45.0;

    private static final class Sight {
        Vector3 lastKnown;
        double lostFor;
        boolean lostSaid;
    }
    private final Map<String, Sight> sightOf = new HashMap<>();
    /** Its own stream: drawing from `rng` would move every later spawn spot (the probes' units start elsewhere). */
    private final java.util.Random searchRng = new java.util.Random(77);
    private int lostCount, foundCount;

    /** `side` (the police, a gang's hunters) has lost this player (see above). */
    private boolean lost(String playerId, String side) {
        Sight s = sightOf.get(playerId + "|" + side);
        return searchPhase && s != null && s.lastKnown != null && s.lostFor >= LOST_GRACE;
    }

    /** Where `side` believes the player is: the last known position while it has lost them, else the player. */
    private Vector3 believed(Player p, String side) {
        String id = p.getCharacterInfo().characterId;
        return lost(id, side) ? sightOf.get(id + "|" + side).lastKnown : p.getGlobalPosition();
    }

    /** Where NEW units of `side` are sent: the last known position from the first tick nobody has the player in
     *  sight -- not after the grace. (Measured with probe_lose_police: with the grace here too, a player who had just
     *  got away was given a fresh unit 45-75 m off within 1.5 s, which saw them, and they were never lost.) */
    private Vector3 sendTo(Player p, String side) {
        Sight s = sightOf.get(p.getCharacterInfo().characterId + "|" + side);
        return searchPhase && s != null && s.lastKnown != null && s.lostFor > 0 ? s.lastKnown : p.getGlobalPosition();
    }

    /** For the minimap: {x, z, radius m} of the disc the POLICE are searching for this player, or null while they
     *  have them in sight (or are not after them). The radius is the one {@link #searchTick} draws its points from. */
    public double[] searchArea(String playerId) {
        if (!lost(playerId, POLICE)) return null;
        Sight s = sightOf.get(playerId + "|" + POLICE);
        return new double[] {s.lastKnown.getX(), s.lastKnown.getZ(), Math.min(SEARCH_MAX, SEARCH_START + SEARCH_GROW * s.lostFor)};
    }

    /** {@link #searchArea} for a probe: "x,z,r" or "". */
    @godot.annotation.Register
    public String searchAreaNow(String playerId) {
        double[] a = searchArea(playerId);
        return a == null ? "" : String.format("%.1f,%.1f,%.1f", a[0], a[1], a[2]);
    }

    /** Probe readout for the POLICE: "lost=<bool> lost_for=<s> lost_n=<times lost> found_n=<times found again> known=(x, z)". */
    @godot.annotation.Register
    public String sightNow(String playerId) { return sightOfNow(playerId, POLICE); }

    /** {@link #sightNow} for any side (a gang id). */
    @godot.annotation.Register
    public String sightOfNow(String playerId, String side) {
        Sight s = sightOf.get(playerId + "|" + side);
        if (s == null || s.lastKnown == null) return "lost=false lost_for=0.0 lost_n=" + lostCount + " found_n=" + foundCount;
        return String.format("lost=%s lost_for=%.1f lost_n=%d found_n=%d known=(%.1f, %.1f)", lost(playerId, side), s.lostFor,
                lostCount, foundCount, s.lastKnown.getX(), s.lastKnown.getZ());
    }

    /** One searching unit: to its own point round the last known position; a new point when it gets there or tires. */
    private void searchTick(Unit u, Player p, AIController brain) {
        Sight s = sightOf.get(u.playerId + "|" + u.side);
        Vector3 b = u.body.getGlobalPosition();
        u.searchFor -= TICK;
        if (u.searchPoint == null || u.searchFor <= 0) {
            double radius = Math.min(SEARCH_MAX, SEARCH_START + SEARCH_GROW * s.lostFor);
            double a = searchRng.nextDouble() * Math.PI * 2, r = radius * (0.35 + 0.65 * searchRng.nextDouble());
            u.searchPoint = new Vector3(s.lastKnown.getX() + Math.sin(a) * r, s.lastKnown.getY(), s.lastKnown.getZ() + Math.cos(a) * r);
            u.searchFor = 5.0 + searchRng.nextDouble() * 4.0;
        }
        brain.setPursuit(p);
        brain.pursuitAway = false;
        brain.pursuitVia.clear();
        brain.pursuitSearch = true;
        brain.pursuitPoint = u.searchPoint;
        brain.pursuitDirect = clearLine(b, u.searchPoint);
        if (brain.getCurrentState() != ArrestState.INSTANCE) brain.forceState(ArrestState.INSTANCE);
        u.breachOf = null;
        u.breachDoor = null;
        u.sinceCloser = 0;                 // not stuck: it is not trying to close in
        u.closest = Double.MAX_VALUE;
    }

    /** Approach slots (PLAN.md 1i, user 2026-10-08: "all police line up and get stuck"): every unit closes on its own
     *  point round the player -- on its own side (the bearing it came from), fanned out by SLOT_SPREAD per unit -- not
     *  on the player point, so a squad arrives from several sides instead of single file. Off = the old approach. */
    @godot.annotation.Visible public boolean approachSlots = true;
    private static final double SLOT_RADIUS = 12.0, SLOT_RADIUS_MELEE = 1.6, SLOT_SPREAD = 0.45;
    /** No two foot units appear closer than this (they used to share the same few footway points). */
    private static final double SPAWN_SPACING = 6.0;
    private int slotCounter;

    private void setSlot(Unit u, AIController brain, Character p, boolean melee, boolean interior) {
        if (!approachSlots || interior) { brain.pursuitOffset = new Vector3(); return; }
        Vector3 pp = p.getGlobalPosition(), b = u.body.getGlobalPosition();
        if (Double.isNaN(u.slot)) {
            double base = Math.atan2(b.getX() - pp.getX(), b.getZ() - pp.getZ());
            u.slot = base + ((slotCounter++ % 5) - 2) * SLOT_SPREAD;
        }
        double r = melee ? SLOT_RADIUS_MELEE : SLOT_RADIUS;
        brain.pursuitOffset = new Vector3(Math.sin(u.slot) * r, 0, Math.cos(u.slot) * r);
    }

    /** Where this unit is headed: its slot, or the player. */
    private static Vector3 slotGoal(AIController brain, Character p) {
        Vector3 o = brain.pursuitOffset;
        return o != null && o.lengthSquared() > 0.01 ? p.getGlobalPosition().plus(o) : p.getGlobalPosition();
    }

    /** An officer running a player down that has not closed in by {@link #STUCK_GAIN} for this long is given up:
     *  it walks off and a fresh one is dispatched (no navmesh under it, a wall in the way). */
    private static final double STUCK_SECONDS = 8.0, STUCK_GAIN = 2.0;
    /** A shooting unit hands over to the combat FSM inside ENGAGE_IN of its player, and back to the approach past
     *  ENGAGE_OUT (hysteresis, so it does not flip at one distance). */
    private static final double ENGAGE_IN = 25.0, ENGAGE_OUT = 35.0;
    private static final double MELEE_ENGAGE_IN = 3.0, MELEE_ENGAGE_OUT = 6.0;
    /** A player moving faster than this (a car) cannot be closed on by a runner: that is not "stuck" (measured: 100-160
     *  officers a leg retired and re-spawned while the perf probe drove the player at 20 m/s). */
    private static final double OUTRUN_SPEED = 5.0;
    private final Map<String, Vector3> lastPlayerAt = new HashMap<>();
    private final Map<String, Double> playerSpeeds = new HashMap<>();

    /** The player's ground speed this tick, measured from position (a probe or a seat moves the body, not velocity). */
    private double playerSpeed(String id, Player p) { return playerSpeeds.getOrDefault(id, 0.0); }

    private void measurePlayerSpeeds(Map<String, Player> players) {
        for (Map.Entry<String, Player> e : players.entrySet()) {
            Vector3 now = e.getValue().getGlobalPosition();
            Vector3 was = lastPlayerAt.put(e.getKey(), now);
            playerSpeeds.put(e.getKey(), was == null ? 0.0 : flat(now, was) / TICK);
        }
    }

    private static final class Car {
        Vehicle car;
        String side, playerId;
        double age, replanIn;
        boolean arrived;
        /** The catalog model ("POC1", "TNK1" ...), whether it fires a main gun, and when it may fire next (s). */
        String model = "";
        boolean gun;
        double gunIn = 2.0;
        /** Seconds it has spent within 30 m of an on-foot player while ramming (the crew bails out after a while). */
        double closeFor;
        /** Stopped by the regroup lull (1g b3); released when it ends. */
        boolean lullHeld;
    }

    private final List<Unit> units = new ArrayList<>();
    private final List<Car> cars = new ArrayList<>();

    /** A helicopter on a call (PLAN.md W6): it orbits its player with a door gunner and a sniper aboard. */
    private static final class Heli {
        com.openworld.carrier.helicopter.Helicopter h;
        String side, playerId;
        double age, gunIn = 2.0, burstLeft, shotIn = 0.1, sniperIn = 4.0, retiredFor;
    }

    private final List<Heli> helis = new ArrayList<>();
    private static final String HELI_SCENE = "res://src/main/resources/com/openworld/vehicle/HLC1.tscn";
    /** Door gun: a 1.2 s burst every 3 s, a shot every 0.12 s, each hitting with this chance (in line, in range). */
    private static final double HELI_RANGE = 140.0, HELI_HIT = 0.22, HELI_DAMAGE = 14.0;
    /** The sniper aboard: one aimed shot every 4 s, this chance, this damage. */
    private static final double HELI_SNIPE_HIT = 0.5, HELI_SNIPE_DAMAGE = 75.0;
    private int heliShots, heliHits;
    private final Map<String, AISquad> squads = new HashMap<>();
    private final Random rng = new Random(0x5EED);
    /** Seconds since start, in dispatch ticks (the lull's clock). */
    private double clock;
    /** Per player|side: no new unit before this clock time (the regroup lull, 1g b3), and units gone dry since the last
     *  lull. */
    private final Map<String, Double> lullUntil = new HashMap<>();
    private final Map<String, Integer> dryCount = new HashMap<>();
    private int dryRetreats, dryRestocks, restocksDone, lulls, tokenHolds;
    private double radioIn;
    private double tickIn, spawnIn;

    @Register
    @Override
    public void _ready() { instance = this; }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        units.clear();
        cars.clear();
        squads.clear();
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) || !net.isNetworked() || net.isServer();
    }

    private ZoneManager zm() { return ZoneManager.get(); }

    @Register
    @Override
    public void _process(double delta) {
        tickIn -= delta;
        if (tickIn > 0) return;
        tickIn = TICK;
        if (!authority()) return;
        WantedSystem ws = WantedSystem.get();
        GangSystem gs = GangSystem.get();
        DispatchRules police = ws != null ? ws.dispatchRules() : null;
        DispatchRules hunters = gs != null ? gs.hunterRules() : null;

        // what each player's standing calls for: side -> stars, per player
        Map<String, Map<String, Integer>> demand = new HashMap<>();
        Map<String, Player> players = new HashMap<>();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || p.getCharacterInfo() == null) continue;
            String id = p.getCharacterInfo().characterId;
            players.put(id, p);
            Map<String, Integer> d = new HashMap<>();
            if (enabled && p.isAlive()) {
                if (ws != null && police != null && ws.starsOf(id) > 0) d.put(POLICE, ws.starsOf(id));
                if (gs != null && hunters != null) {
                    d.putAll(gs.huntedBy(id));
                    GangSystem.Captivity held = gs.captivityOf(id);
                    if (held != null && !held.escaping) d.remove(held.gang);   // the guards have them
                }
            }
            demand.put(id, d);
        }

        measurePlayerSpeeds(players);
        clock += TICK;
        arrestsAndSight(players, demand, ws, police, hunters);   // first: the units below act on what was SEEN this tick
        tickUnits(players, demand, ws, police);
        assignTokens(players, demand, police);
        tickCars(players, demand, police, hunters);
        tickHelis(players, demand);

        spawnIn -= TICK;
        if (spawnIn <= 0) {
            spawnIn = police != null ? police.spawnInterval : 1.5;
            for (Map.Entry<String, Map<String, Integer>> e : demand.entrySet()) {
                Player p = players.get(e.getKey());
                for (Map.Entry<String, Integer> side : e.getValue().entrySet()) {
                    DispatchRules r = POLICE.equals(side.getKey()) ? police : hunters;
                    if (r != null) spawnFor(p, side.getKey(), side.getValue(), r, ws);
                }
            }
        }
        reportLoad();
    }

    // ── units on foot ─────────────────────────────────────────────────────────

    private void tickUnits(Map<String, Player> players, Map<String, Map<String, Integer>> demand, WantedSystem ws,
                           DispatchRules police) {
        Map<String, Node3DRef> indoors = new HashMap<>();
        for (Map.Entry<String, Player> e : players.entrySet()) {
            Node b = buildingAround(e.getValue().getGlobalPosition());
            // the building's interior navmesh is attached ON DEMAND, the first time a hunted player is inside it:
            // attached to every enterable building as it streamed, it cost ~1 ms p50 of frame on the walk / drive legs
            // (three ordered pairs, PLAN.md 1d) for regions nobody was using
            if (b instanceof godot.api.Node3D b3 && interiorNav && !units.isEmpty()) com.openworld.world.InteriorNav.attach(b3);
            indoors.put(e.getKey(), new Node3DRef(b));
        }
        Iterator<Unit> it = units.iterator();
        while (it.hasNext()) {
            Unit u = it.next();
            if (!GD.isInstanceValid(u.body)) { it.remove(); continue; }
            Player p = players.get(u.playerId);
            Integer stars = p != null ? demand.getOrDefault(u.playerId, Map.of()).get(u.side) : null;
            GangSystem.Captivity held = u.guard && GangSystem.get() != null ? GangSystem.get().captivityOf(u.playerId) : null;
            if (u.guard) stars = p != null && held != null ? Integer.valueOf(1) : null;
            double far = nearestPlayer(u.body.getGlobalPosition());
            boolean seenNow = inView(u.body.getGlobalPosition());
            if (u.body.isDead() || stars == null || u.retiredFor > 0) {
                // retired: a corpse, a standing that is gone, or a unit that got stuck -- it leaves the scene, and
                // is freed out of view (never in front of anyone)
                if (!u.body.isDead() && u.retiredFor == 0) release(u, p);
                u.retiredFor += TICK;
                // out of view and away; or, a unit that cannot get clear (a wall behind it), after a while at a
                // distance; a corpse or a stuck unit is never left standing for good
                if ((!seenNow && (far > RETIRE_FAR || u.retiredFor > 30.0))
                        || (u.retiredFor > 45.0 && far > 20.0) || u.retiredFor > 90.0) { free(u.body); it.remove(); }
                continue;
            }
            u.retiredFor = 0;
            DispatchRules r = POLICE.equals(u.side) ? police
                    : GangSystem.get() != null ? GangSystem.get().hunterRules() : null;
            if (!u.guard && r != null && far > r.despawnFar && !seenNow) { free(u.body); it.remove(); continue; }
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
            if (lost(u.playerId, u.side)) {
                // the player is LOST: a sniper holds with nothing on the radio, everybody else searches the area
                if (u.sniper) brain.setPursuit(null);
                else searchTick(u, p, brain);
                continue;
            }
            u.searchPoint = null;
            if (dryRetreat && handleDry(u, p, brain, stars, r)) continue;
            // BREACH (PLAN.md W6): the player is inside a building -- follow them in, at ANY star level (user: always
            // get in, so the behaviour is consistent): through the building's door nearest this unit, straight (no
            // navmesh indoors), forcing a locked one
            Node3DRef in = indoors.get(u.playerId);
            Node ub = buildingAround(u.body.getGlobalPosition());
            // standing on that building's interior navmesh counts as inside: a compound's yard (a police station, a
            // hospital) is under no roof, and routing again from there sent the unit back out through the gate
            if (in != null && in.node != null && ub != in.node && com.openworld.world.InteriorNav.has(in.node)
                    && com.openworld.world.InteriorNav.onMesh(u.body.getGlobalPosition())) ub = in.node;
            if (!u.sniper && breaching && in != null && in.node != null) {
                if (ub != in.node) {
                    // no progress toward this door (a neighbour against the wall, a fence): give it up, take another
                    Vector3 here = u.body.getGlobalPosition();
                    if (u.breachMark == null || flat(here, u.breachMark) > 1.5) { u.breachMark = here; u.breachStill = 0; }
                    else if ((u.breachStill += TICK) > BREACH_STUCK_SECONDS && u.breachDoor != null) {
                        u.badDoors.add(u.breachDoor);
                        u.breachStill = 0;
                        brain.pursuitVia.clear();
                        doorsGivenUp++;
                    }
                    if (u.breachOf != in.node || brain.pursuitVia.isEmpty()) {
                        if (u.breachOf != in.node) u.badDoors.clear();
                        brain.pursuitVia.clear();
                        brain.pursuitVia.addAll(breachRoute(in.node, u));
                        u.breachOf = in.node;
                        breachRoutes++;
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
                if (u.breachOf == in.node && brain.pursuitVia.isEmpty()) { u.breachOf = null; breachedIn++; }
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
                AISquad sq = squadFor(u.playerId, u.side);
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
                AISquad sq = squadFor(u.playerId, u.side);
                if (sq != null && p.isAlive()) sq.assignTarget(p, p.getGlobalPosition());
            } else if (shoot) {
                // closing in: the FSM's own chase leans on the navmesh and measured standing still 50-70 m out on
                // the island, so the approach is ArrestState's (straight where the line is clear), weapon up
                brain.setPursuit(p);
                brain.pursuitAway = false;
                setSlot(u, brain, p, melee, interior);
                brain.pursuitDirect = !interior && clearLine(u.body.getGlobalPosition(), slotGoal(brain, p));
                if (!inArrest) brain.forceState(ArrestState.INSTANCE);
            } else {
                brain.setPursuit(p);
                brain.pursuitAway = false;
                setSlot(u, brain, p, melee, interior);
                brain.pursuitDirect = !interior && clearLine(u.body.getGlobalPosition(), slotGoal(brain, p));
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
                stuckGivenUp++;
            }
        }
    }

    // ── out of ammo, and attack tokens (PLAN.md 1g b2/b3) ─────────────────────

    /** Within this distance of its player a dry unit fights on with fists / baton rather than leaving. */
    private static final double DRY_MELEE = 4.0;
    /** An attack token is held this long, then given back and not taken again for TOKEN_REST (rotation). */
    private static final double TOKEN_HOLD = 4.0, TOKEN_REST = 1.5;

    /** Does the unit carry a firearm (anything not melee and not infinite)? */
    private static boolean carriesFirearm(AICharacter b) {
        if (b.weaponController == null) return false;
        for (int i = 1; i < b.weaponController.getSlotCount(); i++) {
            var w = b.weaponController.getWeaponItem(i);
            if (w != null && !w.isInfiniteAmmo && w.getWeaponType() != com.openworld.weapon.WeaponType.MELEE) return true;
        }
        return false;
    }

    /** A unit that carries a firearm and has no round left in any of them. */
    private static boolean isDry(AICharacter b) {
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
    private boolean handleDry(Unit u, Player p, AIController brain, int stars, DispatchRules r) {
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
                    if (a.restock(b)) restocksDone++;
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
        countDry(u, stars, r);
        com.openworld.item.AmmoSupply a = com.openworld.item.AmmoSupply.nearest(this, b.getGlobalPosition(), r.supplyReach);
        if (a != null && !supplyTaken(a)) {
            u.restockAt = a;
            u.restockFor = 0;
            dryRestocks++;
            radio(p, u.side, "out of ammo, back to the car");
            return true;
        }
        retireDry(u, p, stars, r);
        return true;
    }

    /** A supply on a vehicle a player is in: not somewhere a unit walks up to. */
    private static boolean supplyTaken(com.openworld.item.AmmoSupply a) {
        return a.getParent() instanceof Vehicle v && v.getOccupant() instanceof Player;
    }

    private void retireDry(Unit u, Player p, int stars, DispatchRules r) {
        u.retiredFor = TICK;
        release(u, p);
        dryRetreats++;
        radio(p, u.side, "out of ammo, falling back");
    }

    /** Count a unit gone dry; past half of the units on this player, hold the next wave (the regroup lull). The lull is
     *  not started while armour or a helicopter is still on the player (they are the high-star pressure). */
    private void countDry(Unit u, int stars, DispatchRules r) {
        String key = u.playerId + "|" + u.side;
        int n = dryCount.merge(key, 1, Integer::sum);
        int live = 0;
        for (Unit o : units)
            if (key.equals(o.playerId + "|" + o.side) && GD.isInstanceValid(o.body) && !o.body.isDead() && o.retiredFor == 0) live++;
        int secs = r.regroupFor(stars);
        if (secs <= 0 || n * 2 < Math.max(2, live)) return;
        for (Heli h : helis) if (u.playerId.equals(h.playerId) && GD.isInstanceValid(h.h) && h.retiredFor == 0) return;
        for (Car c : cars) if (u.playerId.equals(c.playerId) && c.gun && GD.isInstanceValid(c.car)) return;
        lullUntil.put(key, clock + secs);
        dryCount.put(key, 0);
        lulls++;
        radioIn = 0;
        radio(null, u.side, "units regrouping -- " + secs + " s");
    }

    /** One line of radio chatter to the local player, at most every 4 s. */
    private void radio(Player p, String side, String what) {
        if (clock < radioIn) return;
        radioIn = clock + 4.0;
        String who = POLICE.equals(side) ? "POLICE RADIO" : side.toUpperCase(java.util.Locale.ROOT) + " RADIO";
        if (getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus)
            bus.radioChatter.emit(who + ": " + what);
    }

    /** Hand out attack tokens per player and side: the nearest units in the fight attack, the rest hold (1g b2). */
    private void assignTokens(Map<String, Player> players, Map<String, Map<String, Integer>> demand, DispatchRules police) {
        Map<String, List<Unit>> groups = new HashMap<>();
        for (Unit u : units) {
            if (!GD.isInstanceValid(u.body) || u.body.isDead()) continue;
            boolean candidate = attackTokens && !u.sniper && !u.guard && u.retiredFor == 0 && u.restockAt == null
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
                if (!give[i]) tokenHolds++;
            }
        }
    }

    /** Units of {@code side} attacking (holding a token) right now. */
    @Register
    public int attackersNow(String side) {
        int n = 0;
        for (Unit u : units)
            if (side.equals(u.side) && GD.isInstanceValid(u.body) && !u.body.isDead() && u.retiredFor == 0
                    && u.restockAt == null && !u.body.attackHeld && u.body.currentVehicleNode == null
                    && u.body.aiController() != null && u.body.aiController().getCurrentState() != ArrestState.INSTANCE)
                n++;
        return n;
    }

    /** "dryRetreats,dryRestocks,restocksDone,lulls,tokenHolds" (probe readout). */
    @Register
    public String dryNow() {
        return dryRetreats + "," + dryRestocks + "," + restocksDone + "," + lulls + "," + tokenHolds;
    }

    /** Seconds left of the regroup lull on {@code playerId}'s {@code side} (0 = none). */
    @Register
    public double lullLeftNow(String playerId, String side) {
        return Math.max(0, lullUntil.getOrDefault(playerId + "|" + side, -1.0) - clock);
    }

    /** Empty every firearm of every live unit of {@code side} (probe: start the dry case). */
    @Register
    public void drainUnitAmmoNow(String side) {
        for (Unit u : units) {
            if (!side.equals(u.side) || !GD.isInstanceValid(u.body) || u.body.weaponController == null) continue;
            var wc = u.body.weaponController;
            for (int i = 1; i < wc.getSlotCount(); i++) {
                var w = wc.getWeaponItem(i);
                if (w != null && !w.isInfiniteAmmo && w.getWeaponType() != com.openworld.weapon.WeaponType.MELEE) {
                    w.setMagazine(0);
                    w.setReserve(0);
                }
            }
        }
    }

    /** Stand down: walk away from the player (ArrestState's away mode, straight, not by the navmesh), and be freed
     *  once out of view (tickUnits). */
    private void release(Unit u, Player p) {
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

    private int stuckGivenUp, carsDiscarded;
    /** A patrol car is kept only if its road route is at most this many times the straight distance. */
    private static final double ROUTE_DETOUR = 2.5;

    // ── cars ──────────────────────────────────────────────────────────────────

    private void tickCars(Map<String, Player> players, Map<String, Map<String, Integer>> demand,
                          DispatchRules police, DispatchRules hunters) {
        Iterator<Car> it = cars.iterator();
        while (it.hasNext()) {
            Car c = it.next();
            if (!GD.isInstanceValid(c.car)) { it.remove(); continue; }
            c.age += TICK;
            Player p = players.get(c.playerId);
            boolean wanted = p != null && demand.getOrDefault(c.playerId, Map.of()).containsKey(c.side);
            DispatchRules r = POLICE.equals(c.side) ? police : hunters;
            Vector3 at = c.car.getGlobalPosition();
            boolean seenNow = inView(at);
            double far = nearestPlayer(at);
            int starsNow = p != null ? demand.getOrDefault(c.playerId, Map.of()).getOrDefault(c.side, 0) : 0;
            if (c.gun && wanted && r != null && p != null && p.isAlive() && !lost(c.playerId, c.side)) fireMainGun(c, p, r);
            if (!c.arrived) {
                VehicleAIController ctrl = c.car.getController() instanceof VehicleAIController v ? v : null;
                // the regroup lull (1g b3): a car sent before it started stops where it is and waits it out, or its
                // crew would arrive inside the player's escape window. A gun vehicle (armour) keeps coming: the lull
                // is not started while one is on the player, and one sent later is not held.
                boolean lullNow = clock < lullUntil.getOrDefault(c.playerId + "|" + c.side, -1.0);
                if (lullNow && !c.gun && ctrl != null && wanted) {
                    ctrl.ramTarget = null;
                    ctrl.holdStop = true;
                    c.lullHeld = true;
                    c.age -= TICK;                 // waiting is not "lost"
                    continue;
                }
                if (c.lullHeld) {
                    c.lullHeld = false;
                    if (ctrl != null) ctrl.holdStop = false;
                    c.replanIn = 0;
                }
                // RAM (PLAN.md W6): from ram_at stars the car drives AT the player within its ram range instead of
                // stopping 35 m out to unload. Its crew gets out only once the player is on foot and close for a
                // while (a gun vehicle never unloads: it keeps ramming and firing).
                // (a LOST player is not rammed: the car drives to where they were last seen and unloads there)
                boolean ram = wanted && r != null && r.rams(starsNow) && ctrl != null && c.car.getHealthNow() > 0
                        && !lost(c.playerId, c.side);
                if (ctrl != null) ctrl.ramTarget = ram ? p : null;
                if (ram) {
                    double dd = flat(p.getGlobalPosition(), at);
                    boolean onFoot = p.currentVehicleNode == null;
                    c.closeFor = onFoot && dd < 30.0 ? c.closeFor + TICK : 0.0;
                    if (!c.gun && c.closeFor > 8.0) {
                        ctrl.ramTarget = null;
                        ctrl.holdStop = true;
                        if (c.car.getLinearVelocity().length() < 1.5) unload(c);
                        continue;
                    }
                    if (dd < ctrl.ramRange) continue;   // closing in by itself; far: follow the road plan below
                }
                boolean lost = ctrl == null || ctrl.isFinished() || c.age > CAR_GIVE_UP;
                if (!wanted || (lost && far > (r != null ? r.arriveDist * 2 : 70.0))) {
                    if (!seenNow || !wanted) { zm().freeServiceCar(c.car); it.remove(); }
                    continue;
                }
                double d = believed(p, c.side).distanceTo(at);
                boolean stuck = ctrl != null && ctrl.stalledFor() > 4.0 && d < 150.0;
                if (r != null && !c.gun && !ram && (d <= r.arriveDist || stuck || lost)) {
                    if (ctrl != null) ctrl.holdStop = true;
                    if (c.car.getLinearVelocity().length() < 1.5) unload(c);
                    continue;
                }
                c.replanIn -= TICK;
                if (c.replanIn <= 0 && ctrl != null) {
                    c.replanIn = REPLAN;
                    RoadGraph g = RoadMap.graph();
                    if (g != null) {
                        Vector3 pp = believed(p, c.side);
                        // from the lane the car is ON (a position snap may pick the other carriageway, and a car
                        // cannot turn round where it stands: measured, both cars drove away from the player)
                        RoadGraph.Route route = ctrl.getRoute() instanceof Node rn
                                ? g.routeFromLane(rn.getName().toString(), ctrl.routeProgressNow(), pp.getX(), pp.getY(), pp.getZ())
                                : null;
                        if (route == null)
                            route = g.route(at.getX(), at.getY(), at.getZ(), pp.getX(), pp.getY(), pp.getZ());
                        if (route != null) ctrl.setPlan(route.laneIds());
                    }
                }
            } else if (!seenNow && (far > (r != null ? r.despawnFar : 180.0) || !wanted)
                    && !(c.car.getOccupant() instanceof Player)) {
                zm().freeServiceCar(c.car);
                it.remove();
            }
        }
    }

    /** The car has stopped by the player: its crew gets out and joins the units on foot; the brain is removed. */
    private void unload(Car c) {
        c.arrived = true;
        NetworkManager net = getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
        for (int seat = c.car.getSeatCount() - 1; seat >= 0; seat--) {
            Character who = c.car.getSeatOccupant(seat);
            if (!(who instanceof AICharacter ai) || who instanceof Player) continue;
            c.car.tryExit(seat);
            if (net != null && c.car.getCharacterInfo() != null && ai.getCharacterInfo() != null)
                net.broadcastVehicleOccupancy(c.car.getCharacterInfo().characterId, ai.getCharacterInfo().characterId,
                        c.car.getCharacterInfo().ownerPeerId, false, seat);
            ai.lodPinnedActive = true;
            Unit u = new Unit();
            u.body = ai;
            u.side = c.side;
            u.playerId = c.playerId;
            ai.setSquad(squadFor(c.playerId, c.side));
            units.add(u);
        }
        c.car.removeAiDriverBrain();
    }

    // ── being seen ───────────────────────────────────────────────────────────

    /** Who has each hunted player in SIGHT (see "LOSING THE POLICE"), per side: the police and every gang hunting
     *  them. Police in sight also stop the heat draining. There is no arrest by proximity any more (user 2026-10-07:
     *  police hunt the player down); a wanted player who goes DOWN is arrested by RecoveryRules. */
    private void arrestsAndSight(Map<String, Player> players, Map<String, Map<String, Integer>> demand, WantedSystem ws,
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
                for (Unit u : units) {
                    if (seen) break;
                    if (!side.equals(u.side) || !id.equals(u.playerId) || !GD.isInstanceValid(u.body) || u.body.isDead()) continue;
                    if (u.body.currentVehicleNode != null) continue;
                    seen = sees(u.body.getGlobalPosition(), pp, r.seenReach);
                }
                for (Car c : cars) {
                    if (seen) break;
                    if (side.equals(c.side) && id.equals(c.playerId) && GD.isInstanceValid(c.car))
                        seen = sees(c.car.getGlobalPosition(), pp, r.seenReach);
                }
                for (Heli h : helis) {
                    if (seen || !searchPhase) break;
                    if (side.equals(h.side) && id.equals(h.playerId) && GD.isInstanceValid(h.h) && h.retiredFor == 0)
                        seen = h.h.getGlobalPosition().distanceTo(pp) <= HELI_SEEN_REACH
                                && clearRay(h.h.getGlobalPosition(), pp.plus(new Vector3(0, 1.4, 0)));
                }
                Sight s = sightOf.computeIfAbsent(key, k -> new Sight());
                if (s.lastKnown == null) s.lastKnown = pp;       // the crime itself was reported from somewhere
                boolean wasLost = lost(id, side);
                String who = POLICE.equals(side) ? "Police radio" : "Gang radio";
                if (seen) {
                    s.lastKnown = pp;
                    s.lostFor = 0;
                    if (POLICE.equals(side) && ws != null) ws.seen(id);
                    if (wasLost) {
                        foundCount++;
                        s.lostSaid = false;
                        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) bus.radioChatter.emit(who + ": there they are!");
                    }
                } else {
                    s.lostFor += TICK;
                    if (lost(id, side) && !s.lostSaid) {
                        s.lostSaid = true;
                        lostCount++;
                        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus)
                            bus.radioChatter.emit(who + ": lost them -- search the area");
                    }
                }
            }
        }
        sightOf.keySet().retainAll(live);
    }

    /** A body at `from` has the player at `to` in sight: within reach with a clear world line (or at arm's length,
     *  where a corner hides nobody). With {@link #searchPhase} off reach alone counts (the control). */
    private boolean sees(Vector3 from, Vector3 to, double reach) {
        double d = from.distanceTo(to);
        if (d > reach) return false;
        return !searchPhase || d <= HEAR_REACH || clearLine(from, to);
    }

    /** One world ray between two points (a helicopter's eye to a player's chest). */
    private boolean clearRay(Vector3 from, Vector3 to) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return true;
        var q = godot.api.PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD,
                new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = getViewport().getWorld3d().getDirectSpaceState().intersectRay(q);
        return hit == null || hit.isEmpty();
    }

    /**
     * The guards over an abducted player (RespawnSystem): {@code n} armed members of {@code gang} round {@code at},
     * covering the player until they run (then they fight) or pay (then they stand down).
     */
    public void guard(Player p, String gang, Vector3 at, int n, List<String> weapons) {
        if (p == null || p.getCharacterInfo() == null || !authority()) return;
        String pid = p.getCharacterInfo().characterId;
        bodyStars = 3;
        for (int i = 0; i < n; i++) {
            double a = Math.PI * 2 * i / Math.max(1, n) + 0.4;
            double d = 3.0 + (i % 2) * 1.5;
            Vector3 g = ground(at.getX() + Math.cos(a) * d, at.getZ() + Math.sin(a) * d, at.getY());
            Vector3 spot = g != null && Math.abs(g.getY() - at.getY()) < 2.0 ? g : at.plus(new Vector3(Math.cos(a) * d, 0, Math.sin(a) * d));
            String w = weapons == null || weapons.isEmpty() ? "" : weapons.get(i % weapons.size());
            AICharacter ai = spawnBody(gang, spot, w);
            if (ai == null) break;
            ai.setSquad(squadFor(pid, gang));
            Unit u = new Unit();
            u.body = ai;
            u.side = gang;
            u.playerId = pid;
            u.guard = true;
            units.add(u);
        }
    }

    // ── spawning ──────────────────────────────────────────────────────────────

    private void spawnFor(Player p, String side, int stars, DispatchRules r, WantedSystem ws) {
        if (p == null || !p.isAlive()) return;
        bodyStars = stars;
        String pid = p.getCharacterInfo().characterId;
        int foot = 0, carsEnRoute = 0;
        for (Unit u : units) {
            if (pid.equals(u.playerId) && side.equals(u.side) && GD.isInstanceValid(u.body) && !u.body.isDead()
                    && u.body.currentVehicleNode == null && !u.guard) foot++;   // a unit walking off still counts:
            // it is a live body until it is freed, and replacing it at once churned 100+ spawns a leg (perf probe)
        }
        for (Car c : cars) if (pid.equals(c.playerId) && side.equals(c.side) && !c.arrived) carsEnRoute++;
        // the regroup lull (1g b3): half the units ran dry, the next wave is held back -- the player's escape window
        if (clock < lullUntil.getOrDefault(pid + "|" + side, -1.0)) return;
        // LOST and far from where they were last seen: nobody is sent. A unit set down at the last known position
        // would be past despawn_far of every player and freed on the next tick -- a spawn / free churn for nothing
        if (flat(sendTo(p, side), p.getGlobalPosition()) > r.despawnFar - 20.0) return;
        for (int i = DispatchRules.toSpawn(r.carsFor(stars), carsEnRoute, 1); i > 0; i--) spawnCar(p, side, r, ws, stars);
        int snipers = 0;
        for (Unit u : units) if (u.sniper && pid.equals(u.playerId) && side.equals(u.side) && GD.isInstanceValid(u.body)
                && !u.body.isDead()) snipers++;
        for (int i = DispatchRules.toSpawn(r.snipersFor(stars), snipers, 1); i > 0; i--) spawnSniper(p, side);
        int hs = 0;
        for (Heli h : helis) if (pid.equals(h.playerId) && side.equals(h.side) && GD.isInstanceValid(h.h) && h.retiredFor == 0) hs++;
        for (int i = DispatchRules.toSpawn(r.helisFor(stars), hs, 1); i > 0; i--) spawnHeli(p, side);
        for (int i = DispatchRules.toSpawn(r.footFor(stars), foot - snipers, spawnPerTick); i > 0; i--) {
            Vector3 at = footSpot(sendTo(p, side), r.footMin, r.footMax);
            if (at == null) break;
            AICharacter ai = spawnBody(side, at, weaponFor(side, pid, r, ws, stars));
            if (ai == null) break;
            Unit u = new Unit();
            u.body = ai;
            u.side = side;
            u.playerId = pid;
            units.add(u);
        }
    }

    private String weaponFor(String side, String pid, DispatchRules r, WantedSystem ws) {
        return weaponFor(side, pid, r, ws, 0);
    }

    /** What a unit carries: the side's row for these stars (PLAN.md W6), and for police the lethal list on top once
     *  the player is lethal-wanted; a side with no rows uses its flat list. */
    private String weaponFor(String side, String pid, DispatchRules r, WantedSystem ws, int stars) {
        List<String> list = new ArrayList<>(r.weaponsFor(stars));
        if (POLICE.equals(side)) {
            if (list.isEmpty() || (ws != null && ws.isLethal(pid))) list.addAll(ws != null ? ws.policeWeaponsFor(pid) : List.of());
        } else if (list.isEmpty()) list.addAll(r.weapons);
        return list.isEmpty() ? "" : list.get(rng.nextInt(list.size()));
    }

    private void spawnCar(Player p, String side, DispatchRules r, WantedSystem ws, int stars) {
        ZoneManager z = zm();
        if (z == null) return;
        List<String> models = r.vehiclesFor(stars);
        String model = models.isEmpty() ? "" : models.get(rng.nextInt(models.size()));
        String scene = com.openworld.carrier.vehicle.VehicleModels.sceneOfId(model);
        Vehicle v = z.spawnServiceCar(side, scene != null ? scene : "", sendTo(p, side), (float) r.carMin, (float) r.carMax);
        if (v == null) return;
        String pid = p.getCharacterInfo().characterId;
        // a car whose ROAD route is far longer than the straight line (the far side of a river, a one-way loop) is
        // no use: discarded at once, out of view, and the next tick tries another lane
        RoadGraph g = RoadMap.graph();
        if (g != null && v.getController() instanceof VehicleAIController c0 && c0.getRoute() instanceof Node ln) {
            Vector3 pp = sendTo(p, side);
            RoadGraph.Route route = g.routeFromLane(ln.getName().toString(), 0.0, pp.getX(), pp.getY(), pp.getZ());
            double straight = flat(v.getGlobalPosition(), pp);
            if (route == null || route.length > Math.max(400.0, ROUTE_DETOUR * straight)) {
                z.freeServiceCar(v);
                carsDiscarded++;
                return;
            }
            c0.setPlan(route.laneIds());
        }
        if (v.getController() instanceof VehicleAIController ctrl) {
            ctrl.racing = true;          // a car on a call does not wait its turn at a junction
            ctrl.cruiseThrottle = 0.8f;
        }
        AISquad sq = squadFor(pid, side);
        // the driver (seated by ZoneManager) is armed and joins the squad; a partner rides beside
        if (v.getOccupant() instanceof AICharacter drv) {
            String w = weaponFor(side, pid, r, ws, stars);
            if (!w.isEmpty()) WeaponGrant.grant(drv, w, this);
            drv.setSquad(sq);
        }
        for (int seat = 1; seat < Math.min(r.carCrew, v.getSeatCount()); seat++) {
            AICharacter mate = spawnBody(side, v.getGlobalPosition(), weaponFor(side, pid, r, ws, stars));
            if (mate == null) break;
            v.tryEnter(mate, seat);
            if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && v.getCharacterInfo() != null)
                net.broadcastVehicleOccupancy(v.getCharacterInfo().characterId, mate.getCharacterInfo().characterId,
                        v.getCharacterInfo().ownerPeerId, true, seat);
        }
        Car c = new Car();
        c.car = v;
        c.side = side;
        c.playerId = pid;
        c.model = model;
        c.gun = r.hasGun(model);
        cars.add(c);
        v.setEmergency(POLICE.equals(side));      // light bar + siren while on a call
    }

    // ── the main gun (PLAN.md W6: a light tank / tank at the top stars) ──────────────────────────────────────────

    private static final String SHELL_SCENE = "res://src/main/resources/com/openworld/weapon/ATL1Projectile.tscn";

    /** Fire a shell from the turret at the player: in range, on a clear line, every gun_interval seconds. The shell is
     *  the ATL1 rocket's projectile, flown on this (the authoritative) peer; other peers see its detonation. */
    private void fireMainGun(Car c, Player p, DispatchRules r) {
        c.gunIn -= TICK;
        if (c.gunIn > 0) return;
        Vector3 at = c.car.getGlobalPosition();
        double d = flat(at, p.getGlobalPosition());
        if (d > r.gunRange || d < 12.0) return;
        Vector3 up = c.car.getGlobalTransform().getBasis().getColumn(1);
        Vector3 fwd = c.car.getGlobalTransform().getBasis().getColumn(2).times(-1.0);
        Vector3 muzzle = at.plus(up.times(2.6)).plus(fwd.times(3.0));
        Vector3 aimAt = p.getGlobalPosition().plus(new Vector3(0, 1.0, 0));
        if (!clearLine(muzzle.minus(new Vector3(0, 0.6, 0)), aimAt.minus(new Vector3(0, 0.6, 0)))) return;
        if (!(GD.load(SHELL_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof com.openworld.weapon.RocketProjectile rp))
            return;
        rp.speed = 90f;
        rp.explosionRadius = (float) r.gunRadius;
        rp.explosionMaxDamage = (float) r.gunDamage;
        rp.explosionPushForce = 40f;
        rp.attackerId = c.car.getCharacterInfo() != null ? c.car.getCharacterInfo().characterId : "";
        rp.attackerName = c.model;
        rp.attackerFaction = c.side;
        rp.weaponDisplayName = c.model + " gun";
        rp.kind = "ATL1";
        getTree().getCurrentScene().addChild(rp);
        Vector3 dir = aimAt.minus(muzzle).normalized();
        rp.setGlobalPosition(muzzle);
        rp.lookAt(muzzle.plus(dir));
        rp.setLinearVelocity(dir.times(90.0));
        rp.addCollisionExceptionWith(c.car);
        c.gunIn = r.gunInterval;
        shellsFired++;
    }

    private int shellsFired;

    // ── breaching a building (PLAN.md W6) ─────────────────────────────────────

    private record Node3DRef(Node node) {}

    private int interiorSteers;

    /** Put the unit's NavigationAgent3D on the interior map while it stands in a building that has one, else on the
     *  world map. Returns whether it is on the interior map. */
    private boolean useInteriorNav(AICharacter body, Node building) {
        var a = body.getNavAgent();
        if (a == null) return false;
        boolean in = com.openworld.world.InteriorNav.has(building);
        godot.core.RID want = in ? com.openworld.world.InteriorNav.map()
                : (body.getWorld3d() != null ? body.getWorld3d().getNavigationMap() : null);
        if (want != null && !want.equals(a.getNavigationMap())) {
            a.setNavigationMap(want);
            body.aiController().clearNavTarget();
            if (in) interiorSteers++;
        }
        return in;
    }

    /** Probe readout: units switched onto an interior navmesh, and interior regions attached. */
    @Register public String interiorNavNow() {
        return interiorSteers + "," + com.openworld.world.InteriorNav.attachedCount();
    }
    private int breachRoutes, breachedIn;

    /** The building whose roof is over this point (a ray up hits it within 25 m, its owner carries the `building`
     *  meta), or null outdoors. Cheap: one ray per player and per breaching unit, every tick. */
    private Node buildingAround(Vector3 at) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return null;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(at.plus(new Vector3(0, 1.7, 0)), at.plus(new Vector3(0, 25.0, 0)),
                CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("collider") instanceof Node n)) return null;
        StringName key = new StringName("building");
        for (Node x = n; x != null; x = x.getParent()) if (x.hasMeta(key)) return x;
        return null;
    }

    /** A door already taken by this many units costs this much more (m), so a squad spreads over a building's doors
     *  -- front, back and side -- instead of every unit queueing at the one nearest them (user 2026-10-07). */
    private static final double DOOR_SHARE_COST = 25.0;
    /** A breaching unit that has not moved 1.5 m in this long gives up its door (s). */
    private static final double BREACH_STUCK_SECONDS = 6.0;
    private int doorsGivenUp;
    /** How far outside the building's walls a unit walks round a corner (m). */
    private static final double CORNER_MARGIN = 2.5;

    /**
     * The way in for {@code u}: round the building's corners if its walls stand between the unit and the door, then
     * outside the door, then 2.5 m inside it (Door_* markers: -Z points out). The door is the cheapest of the
     * building's doors -- the walk there, plus {@link #DOOR_SHARE_COST} for every unit already going through it.
     * Every door is forced: unlocked and made automatic (a breach does not knock).
     */
    private List<Vector3> breachRoute(Node building, Unit u) {
        List<Vector3> out = new ArrayList<>();
        Vector3 from = u.body.getGlobalPosition();
        java.util.Map<Node, Integer> taken = new java.util.HashMap<>();
        for (Unit w : units) {
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
            List<Vector3> way = pathAround(building, from, outsideOf(m));
            if (place != null && place.walk() != null && !wayClear(from, way)) {
                // the corner route runs into a neighbour: the baked walk grid round the whole block, from where the
                // unit stands (WalkGrid; a unit spawned behind the block cannot even reach the FRONT by the corners)
                Vector3 to = outsideOf(m);
                List<double[]> walk = place.walk().path(from.getX(), from.getZ(), to.getX(), to.getZ());
                if (walk == null) continue;            // no walk from here to this door
                List<Vector3> via = new ArrayList<>();
                for (double[] q : walk) via.add(new Vector3(q[0], from.getY(), q[1]));
                via.set(via.size() - 1, to);
                way = via;
                bakedRoutes++;
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
        out.addAll(bestWay != null ? bestWay : pathAround(building, from, outsideOf(best)));
        out.add(c.minus(o.times(2.5)));
        forceDoorsNear(building, c, Double.MAX_VALUE);   // a breach does not knock: every door of the building
        return out;
    }

    /** Routes that followed a baked door walk (probe readout via escalation_now's breach fields). */
    private int bakedRoutes;

    @Register public int bakedRoutesNow() { return bakedRoutes; }

    /** Every leg of a walk is clear of WORLD geometry (clearLine at knee and chest height). */
    private boolean wayClear(Vector3 from, List<Vector3> way) {
        Vector3 a = from;
        for (Vector3 b : way) {
            if (!clearLine(a, b)) return false;
            a = b;
        }
        return true;
    }

    /** 2.5 m outside a door marker (its -Z points out), on the marker's height. */
    private static Vector3 outsideOf(godot.api.Node3D door) {
        Vector3 o = door.getGlobalTransform().getBasis().getColumn(2).times(-1.0);
        o.setY(0);
        o = o.length() > 1e-3 ? o.normalized() : new Vector3(0, 0, 1);
        return door.getGlobalPosition().plus(o.times(2.5));
    }

    /**
     * From {@code from} to {@code to} (both outside the building): straight when nothing is in the way, else round
     * the building's footprint corners (meta `footprint_m`, its own frame, grown by {@link #CORNER_MARGIN}), the
     * shorter way round. A straight walk to a back door ran into the building's own wall and stayed there.
     * Returns the waypoints, {@code to} last.
     */
    private List<Vector3> pathAround(Node building, Vector3 from, Vector3 to) {
        List<Vector3> path = new ArrayList<>();
        if (clearLine(from, to) || !(building instanceof godot.api.Node3D b)) { path.add(to); return path; }
        double hx = 0, hz = 0;
        if (b.getMeta(new StringName("building"), null) instanceof godot.core.Dictionary<?, ?> meta
                && meta.get("footprint_m") instanceof godot.core.VariantArray<?> fp && fp.size() >= 2) {
            hx = ((Number) fp.get(0)).doubleValue() / 2.0;
            hz = ((Number) fp.get(1)).doubleValue() / 2.0;
        }
        if (hx <= 0 || hz <= 0) { path.add(to); return path; }
        hx += CORNER_MARGIN;
        hz += CORNER_MARGIN;
        Vector3[] corner = {
                b.toGlobal(new Vector3(-hx, 0, -hz)), b.toGlobal(new Vector3(hx, 0, -hz)),
                b.toGlobal(new Vector3(hx, 0, hz)), b.toGlobal(new Vector3(-hx, 0, hz))};
        int ia = nearestCorner(corner, from), ib = nearestCorner(corner, to);
        List<Vector3> best = null;
        double bestLen = Double.MAX_VALUE;
        for (int dir : new int[] {1, -1}) {
            List<Vector3> p = new ArrayList<>();
            for (int i = ia; ; i = (i + dir + 4) % 4) {
                Vector3 q = corner[i];
                p.add(new Vector3(q.getX(), from.getY(), q.getZ()));
                if (i == ib) break;
            }
            p.add(to);
            double len = routeLength(from, p);
            if (len < bestLen) { bestLen = len; best = p; }
        }
        return best;
    }

    private static int nearestCorner(Vector3[] corner, Vector3 at) {
        int k = 0;
        for (int i = 1; i < corner.length; i++) if (flat(corner[i], at) < flat(corner[k], at)) k = i;
        return k;
    }

    private static double routeLength(Vector3 from, List<Vector3> path) {
        double len = 0;
        Vector3 a = from;
        for (Vector3 q : path) { len += flat(a, q); a = q; }
        return len;
    }

    private void forceDoorsNear(Node n, Vector3 at, double reach) {
        for (Node c : n.getChildren()) {
            if (c instanceof com.openworld.world.Door d && d.getGlobalPosition().distanceTo(at) < reach) {
                if (d.isLocked()) { d.setLocked(false); doorsForced++; }
                d.autoOpen = true;
            }
            if (c.getChildCount() > 0 && !(c instanceof com.openworld.character.Character)) forceDoorsNear(c, at, reach);
        }
    }

    private int doorsForced;

    /** "Door_front_7:3,Door_back_2:2": how many live units are breaching through each door (probes). */
    @Register
    public String breachDoorsNow() {
        java.util.Map<String, Integer> n = new java.util.TreeMap<>();
        for (Unit u : units) {
            if (u.breachDoor != null && GD.isInstanceValid(u.breachDoor) && GD.isInstanceValid(u.body) && !u.body.isDead())
                n.merge(u.breachDoor.getName().toString(), 1, Integer::sum);
        }
        StringBuilder sb = new StringBuilder();
        if (doorsGivenUp > 0) n.put("gave_up", doorsGivenUp);
        for (var e : n.entrySet()) sb.append(sb.length() > 0 ? "," : "").append(e.getKey()).append(':').append(e.getValue());
        return sb.toString();
    }

    // ── helicopters (PLAN.md W6) ──────────────────────────────────────────────

    /** In the air, out of view, 220-280 m from the player and 60 m up, a pilot and a gunner aboard, orbiting. */
    private void spawnHeli(Player p, String side) {
        if (!(GD.load(HELI_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof com.openworld.carrier.helicopter.Helicopter h))
            return;
        Vector3 pp = p.getGlobalPosition();
        Vector3 at = null;
        for (int k = 0; k < 12 && at == null; k++) {
            double a = rng.nextDouble() * Math.PI * 2, d = 220.0 + rng.nextDouble() * 60.0;
            Vector3 q = new Vector3(pp.getX() + Math.cos(a) * d, pp.getY() + 60.0, pp.getZ() + Math.sin(a) * d);
            if (!inView(q)) at = q;
        }
        if (at == null) { h.queueFree(); return; }
        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = "Police helicopter";
        info.faction = side;
        h.characterInfo = info;
        Node container = getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = getTree().getCurrentScene();
        container.addChild(h);
        h.setGlobalPosition(at);
        h.aiTarget = p;
        h.setEmergency(POLICE.equals(side));
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) net.announceVehicleSpawn(h);
        for (int seat = 0; seat < Math.min(2, h.getSeatCount()); seat++) {
            AICharacter crew = spawnBody(side, at, seat == 0 ? "" : "SNR1");
            if (crew == null) break;
            h.tryEnter(crew, seat);
        }
        Heli e = new Heli();
        e.h = h;
        e.side = side;
        e.playerId = p.getCharacterInfo().characterId;
        helis.add(e);
    }

    private void tickHelis(Map<String, Player> players, Map<String, Map<String, Integer>> demand) {
        Iterator<Heli> it = helis.iterator();
        while (it.hasNext()) {
            Heli e = it.next();
            if (!GD.isInstanceValid(e.h)) { it.remove(); continue; }
            e.age += TICK;
            Player p = players.get(e.playerId);
            boolean wanted = p != null && p.isAlive() && demand.getOrDefault(e.playerId, Map.of()).containsKey(e.side);
            if (!wanted || e.h.getHealthNow() <= 0) {
                // stand down: fly off (a wide orbit), freed out of view or after a while
                e.retiredFor += TICK;
                e.h.orbitRadius = 600.0;
                e.h.setEmergency(false);
                if ((e.retiredFor > 6.0 && !inView(e.h.getGlobalPosition())) || e.retiredFor > 40.0) {
                    for (int seat = e.h.getSeatCount() - 1; seat >= 0; seat--)
                        if (e.h.getSeatOccupant(seat) instanceof AICharacter ai) free(ai);
                    if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && e.h.getCharacterInfo() != null)
                        net.announceDespawn(e.h.getCharacterInfo().characterId);
                    e.h.queueFree();
                    it.remove();
                }
                continue;
            }
            e.retiredFor = 0;
            e.h.orbitRadius = 55.0;
            e.h.aiTarget = p;
            if (!lost(e.playerId, e.side)) heliFire(e, p);     // nobody shoots what nobody sees
        }
    }

    /** The door gun (bursts) and the sniper aboard: hitscan from the cabin door at the player, each shot hitting with
     *  its chance when the line is clear and the range short enough; tracers either way. */
    private void heliFire(Heli e, Player p) {
        Vector3 gun = e.h.getGlobalPosition().plus(new Vector3(0, -1.2, 0));
        Vector3 chest = p.getGlobalPosition().plus(new Vector3(0, 1.1, 0));
        double d = gun.distanceTo(chest);
        // a gunner in a helicopter hits nobody UNDER COVER (user 2026-10-07: shot on Central's stairs with no shooter in
        // sight): anything solid over the target within HELI_COVER_UP blocks it, even where a gap lines up with the door
        boolean clear = d <= HELI_RANGE && !underCover(chest) && clearShot(gun, chest, e.h);
        e.gunIn -= TICK;
        if (e.burstLeft <= 0 && e.gunIn <= 0) { e.burstLeft = 1.2; e.gunIn = 3.0; }
        if (e.burstLeft > 0) {
            e.burstLeft -= TICK;
            for (int k = 0; k < 2; k++) heliShot(e, p, gun, chest, clear, HELI_HIT, HELI_DAMAGE, "HLC-1 door gun");
        }
        e.sniperIn -= TICK;
        if (e.sniperIn <= 0) {
            e.sniperIn = 4.0;
            heliShot(e, p, gun, chest, clear, HELI_SNIPE_HIT, HELI_SNIPE_DAMAGE, "HLC-1 sniper");
        }
    }

    private void heliShot(Heli e, Player p, Vector3 gun, Vector3 chest, boolean clear, double chance, double dmg, String what) {
        heliShots++;
        boolean hit = clear && rng.nextDouble() < chance;
        Vector3 end = hit ? chest : chest.plus(new Vector3((rng.nextDouble() - 0.5) * 6.0, (rng.nextDouble() - 0.5) * 2.0,
                (rng.nextDouble() - 0.5) * 6.0));
        for (Node n : getTree().getNodesInGroup(new StringName("bullet_tracer_manager"))) {
            if (n instanceof com.openworld.world.manager.BulletTracerManager tm) { tm.spawnTracer(gun, end); break; }
        }
        if (!hit) return;
        for (Node n : getTree().getNodesInGroup(new StringName("impact_manager"))) {
            if (n instanceof com.openworld.world.manager.ImpactManager im) {
                im.processHit(new com.openworld.world.HitInfo(p, chest, gun.minus(chest).normalized()), (float) dmg, what,
                        null, "Police", e.side, gun, e.h.getCharacterInfo() != null ? e.h.getCharacterInfo().characterId : "");
                heliHits++;
                break;
            }
        }
    }

    /** How far above a target a roof, a deck or a platform shed counts as cover from the helicopter (m). */
    private static final double HELI_COVER_UP = 30.0;

    /** Something on the WORLD layer straight above {@code at} within {@link #HELI_COVER_UP}. */
    private boolean underCover(Vector3 at) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return false;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(at.plus(new Vector3(0, 0.9, 0)),
                at.plus(new Vector3(0, HELI_COVER_UP, 0)), CollisionLayers.WORLD,
                new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit != null && !hit.isEmpty();
    }

    /** Nothing on the WORLD layer between the door and the player (the helicopter's own body excepted). */
    private boolean clearShot(Vector3 from, Vector3 to, godot.api.CollisionObject3D self) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return true;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        godot.core.VariantArray<godot.core.RID> ex = new godot.core.VariantArray<>(godot.core.RID.class);
        ex.append(self.getRid());
        var q = godot.api.PhysicsRayQueryParameters3D.create(from, to, CollisionLayers.WORLD, ex);
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit == null || hit.isEmpty();
    }

    // ── snipers ───────────────────────────────────────────────────────────────

    /** A sniper 90-160 m out, out of view, at a spot with a clear line to the player at head height; SNR1, a long
     *  sight and a modest hit chance. Holds there (tickUnits). */
    private void spawnSniper(Player p, String side) {
        Vector3 pp = p.getGlobalPosition();
        for (int k = 0; k < 24; k++) {
            double a = rng.nextDouble() * Math.PI * 2, d = 90.0 + rng.nextDouble() * 70.0;
            Vector3 g = ground(pp.getX() + Math.cos(a) * d, pp.getZ() + Math.sin(a) * d, pp.getY() + 10.0);
            if (g == null || inView(g)) continue;
            if (!clearLine(g.plus(new Vector3(0, 1.0, 0)), pp.plus(new Vector3(0, 0.6, 0)))) continue;
            AICharacter ai = spawnBody(side, g, "SNR1");
            if (ai == null) return;
            com.openworld.ai.AIBehaviorConfig cfg = new com.openworld.ai.AIBehaviorConfig();
            cfg.detectionRange = 260f;
            cfg.attackRange = 260f;
            cfg.hearingRadius = 260f;
            cfg.hitChance = 0.35f;
            cfg.aimScatterRadius = 1.5f;
            cfg.reactionTime = 1.5f;
            cfg.detectionFovDeg = 360f;
            ai.behaviorConfig = cfg;
            ai.setSquad(squadFor(p.getCharacterInfo().characterId, side));
            Unit u = new Unit();
            u.body = ai;
            u.side = side;
            u.playerId = p.getCharacterInfo().characterId;
            u.sniper = true;
            units.add(u);
            return;
        }
    }

    /** The stars the next {@link #spawnBody} is dressed for (set by spawnFor / guard; the body table is by stars). */
    private int bodyStars = 1;
    private final Random bodyRng = new Random(0xB0D1E5);
    private java.util.Map<String, List<DispatchRules.BodyPick>> gangBodies;

    /** Which body and uniform a unit of {@code side} wears at {@link #bodyStars} (PLAN.md 1g c); null = the scene's own. */
    private DispatchRules.BodyPick bodyFor(String side) {
        List<DispatchRules.BodyPick> rows;
        if (POLICE.equals(side)) {
            WantedSystem ws = WantedSystem.get();
            rows = ws != null && ws.dispatchRules() != null ? ws.dispatchRules().bodies : null;
        } else {
            if (gangBodies == null) {
                com.openworld.game.data.Tables.Gangs g = com.openworld.game.data.Tables.GANGS.get();
                gangBodies = g != null ? g.bodies() : new java.util.HashMap<>();
            }
            rows = gangBodies.get(side);
        }
        // its own stream: drawing from `rng` would move every later spawn spot (probe_breach's units then started
        // from a different place and gave up the store's door)
        return DispatchRules.pickBody(rows, bodyStars, bodyRng.nextDouble());
    }

    /** How many units wore each body:outfit (probe readout, "fumiriya:police=3,shino:police=1"). */
    private final java.util.Map<String, Integer> dressed = new java.util.TreeMap<>();

    /** AIController's think budget (PLAN.md 1g d): "decisions,skipped" since start, process-wide. */
    @Register
    public void setThinkBudgetNow(boolean on) { com.openworld.ai.AIController.thinkBudget = on; }

    @Register
    public String thinkCountsNow() {
        return com.openworld.ai.AIController.thinks + "," + com.openworld.ai.AIController.skippedThinks;
    }

    @Register
    public String dressedNow() {
        StringBuilder b = new StringBuilder();
        for (var e : dressed.entrySet()) b.append(b.length() > 0 ? "," : "").append(e.getKey()).append('=').append(e.getValue());
        return b.toString();
    }

    /** A gang member standing at one of its gang's places ({@link GangHangouts}): the dispatch's body, uniform and
     *  weapon rules, but NOT pinned to the active LOD tier (it is scenery until it is provoked). */
    AICharacter spawnHangoutBody(String gang, Vector3 at, String weapon) {
        int keep = bodyStars;
        bodyStars = 1;
        AICharacter ai = spawnBody(gang, at, weapon);
        bodyStars = keep;
        if (ai != null) ai.lodPinnedActive = false;
        return ai;
    }

    private AICharacter spawnBody(String side, Vector3 at, String weapon) {
        if (getTree() == null || getTree().getCurrentScene() == null) return null;
        if (!(GD.load(AI_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof AICharacter ai)) return null;
        DispatchRules.BodyPick look = bodyFor(side);
        if (look != null) {
            String vis = "res://src/main/resources/com/openworld/character/CharacterVisuals_"
                    + java.lang.Character.toUpperCase(look.body().charAt(0)) + look.body().substring(1) + ".tscn";
            if (godot.api.ResourceLoader.INSTANCE.exists(vis, "") && GD.load(vis) instanceof PackedScene vps)
                ai.characterVisuals = vps;   // before _ready, which is what instances it
        }
        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = POLICE.equals(side) ? "Police" : side;
        info.faction = side;
        ai.characterInfo = info;
        Node container = getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = getTree().getCurrentScene();
        container.addChild(ai);
        ai.activateForSpawn(at.plus(new Vector3(0, 0.05, 0)));
        ai.lodPinnedActive = true;
        if (look != null && !look.outfit().isEmpty()) {
            Node mount = ai.getNodeOrNull("VisualsMount");
            if (com.openworld.character.Outfits.apply(mount != null ? mount : ai, look.outfit()) > 0)
                dressed.merge(look.body() + ":" + look.outfit(), 1, Integer::sum);
        }
        if (look != null) for (String x : look.extraWeapons()) WeaponGrant.grant(ai, x, this);
        if (weapon != null && !weapon.isEmpty()) WeaponGrant.grant(ai, weapon, this);
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) net.announceSpawn(ai);
        return ai;
    }

    private AISquad squadFor(String playerId, String side) {
        String key = playerId + "|" + side;
        AISquad sq = squads.get(key);
        if (sq != null && GD.isInstanceValid(sq)) return sq;
        sq = new AISquad();
        sq.setName(new StringName("Squad_" + side + "_" + squads.size()));
        sq.forgetDuration = 30.0f;
        addChild(sq);
        squads.put(key, sq);
        return sq;
    }

    /**
     * Where a unit on foot appears: on the island a footway (Sidewalks) between {@code min} and {@code max} of the
     * player, out of view and on ground a ray confirms; elsewhere (DebugWorld has no footway record) a point in the
     * ring whose ground is within a storey of the player's. Null when nothing qualifies this tick.
     */
    private Vector3 footSpot(Vector3 player, double min, double max) {
        List<Sidewalks.Spot> spots = Sidewalks.near(player, max);
        for (int k = 0; k < 10 && !spots.isEmpty(); k++) {
            Sidewalks.Spot s = spots.get(rng.nextInt(spots.size()));
            Vector3 q = s.point();
            double d = flat(q, player);
            if (d < min || d > max || inView(q)) continue;
            Vector3 g = ground(q.getX(), q.getZ(), q.getY());
            if (g != null && Math.abs(g.getY() - q.getY()) < 1.0 && spaced(g) && clearLine(g, player)) return g;
        }
        for (int k = 0; k < 16; k++) {
            double a = rng.nextDouble() * Math.PI * 2, d = min + rng.nextDouble() * (max - min);
            double x = player.getX() + Math.cos(a) * d, z = player.getZ() + Math.sin(a) * d;
            Vector3 g = ground(x, z, player.getY());
            if (g == null || Math.abs(g.getY() - player.getY()) > 3.0 || inView(g) || !spaced(g) || !clearLine(g, player)) continue;
            return g;
        }
        // a player indoors (a shop, a cell) has no clear line from anywhere outside: an out-of-view spot on the
        // footway then, and the unit finds its way by the navmesh (ArrestState's fallback when the line is blocked)
        for (int k = 0; k < 10 && !spots.isEmpty(); k++) {
            Sidewalks.Spot s = spots.get(rng.nextInt(spots.size()));
            Vector3 q = s.point();
            double d = flat(q, player);
            if (d < min || d > max || inView(q)) continue;
            Vector3 g = ground(q.getX(), q.getZ(), q.getY());
            if (g != null && Math.abs(g.getY() - q.getY()) < 1.0 && spaced(g)) return g;
        }
        return null;
    }

    /** No live unit within SPAWN_SPACING of a spawn spot. */
    private boolean spaced(Vector3 g) {
        for (Unit u : units)
            if (u.body != null && GD.isInstanceValid(u.body) && flat(u.body.getGlobalPosition(), g) < SPAWN_SPACING) return false;
        return true;
    }

    /**
     * Nothing solid between a spot and the player at knee and chest height: an officer walks to the player along that
     * line when there is no navmesh to follow (DebugWorld), and on the island it keeps units off the far side of a
     * building block. Not line of SIGHT for the camera -- the spot is already out of view.
     */
    private boolean clearLine(Vector3 from, Vector3 to) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return true;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        for (double h : new double[] {0.6, 1.4}) {
            var q = godot.api.PhysicsRayQueryParameters3D.create(from.plus(new Vector3(0, h, 0)),
                    to.plus(new Vector3(0, h, 0)), CollisionLayers.WORLD,
                    new godot.core.VariantArray<>(godot.core.RID.class));
            godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
            if (hit != null && !hit.isEmpty()) return false;
        }
        return true;
    }

    /** The first WORLD surface straight down at (x, z) from 40 m over {@code nearY}, or null. */
    private Vector3 ground(double x, double z, double nearY) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return null;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        var q = godot.api.PhysicsRayQueryParameters3D.create(new Vector3(x, nearY + 40.0, z),
                new Vector3(x, nearY - 40.0, z), CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
        godot.core.Dictionary<Object, Object> hit = sp.intersectRay(q);
        return hit != null && !hit.isEmpty() && hit.get("position") instanceof Vector3 v ? v : null;
    }

    private boolean inView(Vector3 p) {
        ZoneManager z = zm();
        return z != null && z.inLocalView(p, 1e9);
    }

    private static double flat(Vector3 a, Vector3 b) {
        double dx = a.getX() - b.getX(), dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dz * dz);
    }

    private static double nearestPlayer(Vector3 at) {
        double best = Double.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(p)) best = Math.min(best, flat(at, p.getGlobalPosition()));
        return best;
    }

    private void free(AICharacter ai) {
        if (!GD.isInstanceValid(ai)) return;
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && ai.getCharacterInfo() != null)
            net.announceDespawn(ai.getCharacterInfo().characterId);
        ai.setSquad(null);
        ai.queueFree();
    }

    private void reportLoad() {
        ZoneManager z = zm();
        if (z == null) return;
        int bodies = 0, n = 0;
        for (Unit u : units) if (GD.isInstanceValid(u.body) && !u.body.isDead()) bodies++;
        for (Car c : cars) {
            if (!GD.isInstanceValid(c.car)) continue;
            n++;
            if (!c.arrived) bodies += Math.max(1, c.car.getSeatCount() > 1 ? 2 : 1);
        }
        z.setEnforcementLoad(bodies, n);
    }

    // ── probe surface ──
    /** "foot,cars en route,cars arrived,0,stuck given up,cars discarded" (live units; the 4th field was arrests,
     *  kept at 0 so readers keep their indexes). */
    @Register
    public String unitsNow() {
        int foot = 0, arrived = 0, enroute = 0;
        for (Unit u : units) if (GD.isInstanceValid(u.body) && !u.body.isDead()) foot++;
        for (Car c : cars) if (GD.isInstanceValid(c.car)) { if (c.arrived) arrived++; else enroute++; }
        return foot + "," + enroute + "," + arrived + ",0," + stuckGivenUp + "," + carsDiscarded;
    }

    /** The escalation's readout (PLAN.md W6): "models en route;rammers;shells fired;snipers;helicopters;heli shots;heli hits". */
    @Register
    public String escalationNow() {
        StringBuilder m = new StringBuilder();
        int rammers = 0, snipers = 0;
        for (Car c : cars) {
            if (!GD.isInstanceValid(c.car)) continue;
            m.append(c.model.isEmpty() ? "car" : c.model).append(' ');
            if (c.car.getController() instanceof VehicleAIController v && v.ramTarget != null) rammers++;
        }
        for (Unit u : units) if (u.sniper && GD.isInstanceValid(u.body) && !u.body.isDead()) snipers++;
        int hl = 0;
        for (Heli h : helis) if (GD.isInstanceValid(h.h) && h.retiredFor == 0) hl++;
        return m.toString().trim() + ";" + rammers + ";" + shellsFired + ";" + snipers + ";" + hl + ";" + heliShots + ";" + heliHits
                + ";" + breachRoutes + ";" + breachedIn + ";" + doorsForced;
    }

    /** Live dispatched bodies on foot of {@code side} (police or a gang id). */
    @Register
    public godot.core.VariantArray<Node> bodiesNow(String side) {
        godot.core.VariantArray<Node> out = new godot.core.VariantArray<>(Node.class);
        for (Unit u : units)
            if (side.equals(u.side) && GD.isInstanceValid(u.body) && !u.body.isDead() && u.body.currentVehicleNode == null)
                out.append(u.body);
        return out;
    }


    /** Live guards over captives (abductions). */
    @Register
    public int guardsNow() {
        int n = 0;
        for (Unit u : units) if (u.guard && GD.isInstanceValid(u.body) && !u.body.isDead() && u.retiredFor == 0) n++;
        return n;
    }

    /** The weapon ids live units of {@code side} carry, comma separated, one per slot holding a weapon other than the
     *  fist (probe readout for the weapons-by-stars rows, PLAN.md 1g a). */
    @Register
    public String unitWeaponsNow(String side) {
        StringBuilder b = new StringBuilder();
        for (Unit u : units) {
            if (!side.equals(u.side) || !GD.isInstanceValid(u.body) || u.body.isDead() || u.body.weaponController == null)
                continue;
            var wc = u.body.weaponController;
            for (int i = 1; i < wc.getSlotCount(); i++) {
                var w = wc.getWeaponItem(i);
                if (w != null) b.append(b.length() > 0 ? "," : "").append(w.weaponId);
            }
        }
        return b.toString();
    }

    /** Melee fallbacks started by every live unit (a target in reach while the gun reloads, PLAN.md 1g b). */
    @Register
    public int meleeFallbacksNow() {
        int n = 0;
        for (Unit u : units) if (GD.isInstanceValid(u.body)) n += u.body.meleeFallbacks;
        return n;
    }

    /** One line per live unit: side, distance to its player, FSM state, LOD tier, speed (probe diagnostics). */
    @Register
    public String debugUnitsNow() {
        StringBuilder b = new StringBuilder();
        for (Unit u : units) {
            if (!GD.isInstanceValid(u.body)) continue;
            double d = nearestPlayer(u.body.getGlobalPosition());
            AIController c = u.body.aiController();
            Vector3 q = u.body.getGlobalPosition();
            b.append(u.side).append(String.format(" (%.0f,%.1f,%.0f) ", q.getX(), q.getY(), q.getZ()))
                    .append(String.format("%.1f", d)).append("m ")
                    .append(c != null && c.getCurrentState() != null ? c.getCurrentState().getClass().getSimpleName() : "-")
                    .append(' ').append(u.body.getLodLevel()).append(' ')
                    .append(String.format("%.1f", u.body.getVelocity().length())).append("m/s")
                    .append(c != null && !c.pursuitVia.isEmpty() ? " via" + c.pursuitVia.size() : "")
                    .append(u.body.getNavAgent() != null && com.openworld.world.InteriorNav.isInteriorMap(u.body.getNavAgent().getNavigationMap()) ? " INNAV" : "")
                    .append(c != null && c.pursuitDirect ? " direct" : "")
                    .append(u.body.isDead() ? " DEAD" : "").append(" | ");
        }
        for (Car c : cars) {
            if (!GD.isInstanceValid(c.car)) continue;
            VehicleAIController ctl = c.car.getController() instanceof VehicleAIController v ? v : null;
            Vector3 q = c.car.getGlobalPosition();
            b.append("CAR ").append(c.side).append(String.format(" (%.0f,%.1f,%.0f) %.1fm %.1fm/s age %.0f ",
                    q.getX(), q.getY(), q.getZ(), nearestPlayer(q), c.car.getLinearVelocity().length(), c.age))
                    .append(c.arrived ? "arrived" : ctl == null ? "no-brain" : ctl.planDebug()
                            + (ctl.isFinished() ? " finished" : "") + String.format(" stall %.0f", ctl.stalledFor())
                            + " " + (ctl.getRoute() instanceof Node rn ? rn.getName() : "-"))
                    .append(" | ");
        }
        return b.toString();
    }
}
