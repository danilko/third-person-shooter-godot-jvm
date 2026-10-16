package com.openworld.game;

import com.openworld.ai.AIController;
import com.openworld.ai.character.ArrestState;
import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.net.NetworkManager;
import com.openworld.world.ZoneManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Random;

import static com.openworld.game.DispatchWorld.*;

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
 *
 * <p>The state lives here; the code is in five package-private parts (PLAN.md P1e step 2, a move-only split):
 * {@link DispatchWorld} (rays, the ground, a building's walk round), {@link DispatchSight} (seen / lost / last known),
 * {@link UnitSpawner} (what a standing calls for, bodies, squads), {@link UnitDirector} (units on foot, every tick) and
 * {@link VehicleDirector} (cars and helicopters). Everything Godot calls -- the probe readouts -- stays on this Node.
 */
@Script(className = "EnforcementDispatch")
public class EnforcementDispatch extends Node {

    // ── the parts (PLAN.md P1e step 2: a MOVE-ONLY split, behaviour unchanged; the state stays here) ──
    final DispatchWorld geometry = new DispatchWorld(this);
    final DispatchSight sightlines = new DispatchSight(this);
    final UnitSpawner spawner = new UnitSpawner(this);
    final UnitDirector unitDirector = new UnitDirector(this);
    final VehicleDirector vehicleDirector = new VehicleDirector(this);
    final IncidentResponders responders = new IncidentResponders(this);
    final RadioNet radioNet = new RadioNet(this);

    /** Extra units that may attack one player at once, on top of the table's tokens_by_stars: the host's
     *  {@link WorldDensity} (QualitySettings.applyDensity). 0 = the table as authored. */
    public static int attackTokenBonus = 0;
    @Register public int attackTokenBonusNow() { return attackTokenBonus; }


    static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    static final String POLICE = Faction.POLICE;
    static final double TICK = 0.25;
    /** A unit retired by a standing that is gone, or a corpse, is freed out of view past this (m). */
    static final double RETIRE_FAR = 40.0;
    /** A car that has not arrived after this long is given up (s). */
    static final double CAR_GIVE_UP = 75.0;
    /** Re-plan a car's road route this often (s), as the player moves. */
    static final double REPLAN = 3.0;

    static EnforcementDispatch instance;

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

    static final class Unit {
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
        /** Counted toward its wave's attrition (down or dry) -- once (P1e step 1). */
        boolean lossCounted;
        /** The station it was drawn from (P1e step 3; null = an unlimited side, a guard). */
        ForcePools.Station origin;
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

    static final class Sight {
        Vector3 lastKnown;
        double lostFor;
        boolean lostSaid;
    }
    final Map<String, Sight> sightOf = new HashMap<>();
    /** Its own stream: drawing from `rng` would move every later spawn spot (the probes' units start elsewhere). */
    final java.util.Random searchRng = new java.util.Random(77);
    int lostCount, foundCount;

    /** {@link #searchArea} for a probe: "x,z,r" or "". */
    @godot.annotation.Register
    public String searchAreaNow(String playerId) {
        double[] a = sightlines.searchArea(playerId);
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
        return String.format("lost=%s lost_for=%.1f lost_n=%d found_n=%d known=(%.1f, %.1f)", sightlines.lost(playerId, side), s.lostFor,
                lostCount, foundCount, s.lastKnown.getX(), s.lastKnown.getZ());
    }

    /** Approach slots (PLAN.md 1i, user 2026-10-08: "all police line up and get stuck"): every unit closes on its own
     *  point round the player -- on its own side (the bearing it came from), fanned out by SLOT_SPREAD per unit -- not
     *  on the player point, so a squad arrives from several sides instead of single file. Off = the old approach. */
    @godot.annotation.Visible public boolean approachSlots = true;
    static final double SLOT_RADIUS = 12.0, SLOT_RADIUS_MELEE = 1.6, SLOT_SPREAD = 0.45;
    /** No two foot units appear closer than this (they used to share the same few footway points). */
    static final double SPAWN_SPACING = 6.0;
    int slotCounter;

    /** An officer running a player down that has not closed in by {@link #STUCK_GAIN} for this long is given up:
     *  it walks off and a fresh one is dispatched (no navmesh under it, a wall in the way). */
    static final double STUCK_SECONDS = 8.0, STUCK_GAIN = 2.0;
    /** A shooting unit hands over to the combat FSM inside ENGAGE_IN of its player, and back to the approach past
     *  ENGAGE_OUT (hysteresis, so it does not flip at one distance). */
    static final double ENGAGE_IN = 25.0, ENGAGE_OUT = 35.0;
    static final double MELEE_ENGAGE_IN = 3.0, MELEE_ENGAGE_OUT = 6.0;
    /** A player moving faster than this (a car) cannot be closed on by a runner: that is not "stuck" (measured: 100-160
     *  officers a leg retired and re-spawned while the perf probe drove the player at 20 m/s). */
    static final double OUTRUN_SPEED = 5.0;
    final Map<String, Vector3> lastPlayerAt = new HashMap<>();
    final Map<String, Double> playerSpeeds = new HashMap<>();

    static final class Car {
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
        /** The stations its crew was drawn from (P1e step 3), handed to the units on foot when it unloads. */
        final List<ForcePools.Station> crewOrigins = new ArrayList<>();
    }

    final List<Unit> units = new ArrayList<>();
    final List<Car> cars = new ArrayList<>();

    /** A helicopter on a call (PLAN.md W6): it orbits its player with a door gunner and a sniper aboard. */
    static final class Heli {
        com.openworld.carrier.helicopter.Helicopter h;
        String side, playerId;
        double age, gunIn = 2.0, burstLeft, shotIn = 0.1, sniperIn = 4.0, retiredFor;
        /** The stations its crew was drawn from (P1e step 3). */
        final List<ForcePools.Station> crewOrigins = new ArrayList<>();
    }

    final List<Heli> helis = new ArrayList<>();
    static final String HELI_SCENE = "res://src/main/resources/com/openworld/vehicle/HLC1.tscn";
    /** Door gun: a 1.2 s burst every 3 s, a shot every 0.12 s, each hitting with this chance (in line, in range). */
    static final double HELI_RANGE = 140.0, HELI_HIT = 0.22, HELI_DAMAGE = 14.0;
    /** The sniper aboard: one aimed shot every 4 s, this chance, this damage. */
    static final double HELI_SNIPE_HIT = 0.5, HELI_SNIPE_DAMAGE = 75.0;
    int heliShots, heliHits;
    final Map<String, AISquad> squads = new HashMap<>();
    final Random rng = new Random(0x5EED);
    /** Seconds since start, in dispatch ticks (the lull's clock). */
    double clock;
    /** Per player|side: no new unit before this clock time (the regroup lull, 1g b3), and units gone dry since the last
     *  lull. */
    final Map<String, Double> lullUntil = new HashMap<>();
    /** Per player|side since the last lull: units LOST (down or dry) -- the wave attrition that starts the lull
     *  (PLAN.md P1e step 1). */
    final Map<String, Integer> waveLost = new HashMap<>();
    int dryRetreats, dryRestocks, restocksDone, lulls, tokenHolds;
    /** Per player ("" = everyone): no radio line before this clock time (one line every 4 s each). */
    final Map<String, Double> radioIn = new HashMap<>();
    double tickIn, spawnIn;

    @Register
    @Override
    public void _ready() {
        instance = this;
        // the activity lint's "reserves more than the force fields here" (P1e step 5): this world's stations, full
        com.openworld.game.activity.ActivityLint.forceCapacity = force -> {
            if (!pools().limited(force)) return -1;
            int n = 0;
            for (ForcePools.Station st : pools().stations()) if (st.side.equals(force)) n += st.max;
            return n;
        };
        com.openworld.game.event.GameplayEvents.subscribe(com.openworld.game.event.GameplayEvents.Phase.OBSERVER, responders.onEvent);
        com.openworld.game.data.Tables.FORCES.onReload(onForcesReload);
        com.openworld.game.data.Tables.AMMO_SUPPLY.onReload(onAmmoReload);
    }

    /** `tables reload` (debug): forces.json -- the stations are bound again FULL and the incident board starts empty
     *  (a tuning pass, not a save); ammo_supply.json -- the explosive cooldown re-reads its numbers (the AI reserve rule
     *  reads the table every reload of a weapon already). */
    private final Runnable onForcesReload = () -> { this.pools = null; this.board = null; };
    private final Runnable onAmmoReload = com.openworld.weapon.ExplosiveCooldown::reset;

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        com.openworld.game.event.GameplayEvents.unsubscribe(responders.onEvent);
        com.openworld.game.data.Tables.FORCES.offReload(onForcesReload);
        com.openworld.game.data.Tables.AMMO_SUPPLY.offReload(onAmmoReload);
        responders.clear();
        RadioMarkers.clear();
        units.clear();
        cars.clear();
        squads.clear();
    }

    boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) || !net.isNetworked() || net.isServer();
    }

    ZoneManager zm() { return ZoneManager.get(); }

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
                // a running activity's hold (Plan.squad / noDispatch, P1e step 5): forces sent as if at its stars,
                // sides kept from coming at all
                if (EnforcementHooks.any()) {
                    for (Map.Entry<String, Integer> sq : EnforcementHooks.squads(id).entrySet())
                        if (sq.getValue() > 0) d.merge(sq.getKey(), sq.getValue(), Math::max);
                    d.keySet().removeIf(side -> EnforcementHooks.noDispatch(id, side));
                }
            }
            demand.put(id, d);
        }

        unitDirector.measurePlayerSpeeds(players);
        clock += TICK;
        pools().tick(TICK);          // every station regenerates its dead (P1e step 3)
        sweepHangouts();
        restrictedAreas(players, ws);
        responders.tick();
        radioNet.tick(players);
        sightlines.arrestsAndSight(players, demand, ws, police, hunters);   // first: the units below act on what was SEEN this tick
        unitDirector.tickUnits(players, demand, ws, police);
        unitDirector.assignTokens(players, demand, police);
        vehicleDirector.tickCars(players, demand, police, hunters);
        vehicleDirector.tickHelis(players, demand);

        spawnIn -= TICK;
        if (spawnIn <= 0) {
            spawnIn = police != null ? police.spawnInterval : 1.5;
            for (Map.Entry<String, Map<String, Integer>> e : demand.entrySet()) {
                Player p = players.get(e.getKey());
                for (Map.Entry<String, Integer> side : e.getValue().entrySet()) {
                    DispatchRules r = POLICE.equals(side.getKey()) ? police : hunters;
                    if (r != null) spawner.spawnFor(p, side.getKey(), side.getValue(), r, ws);
                }
            }
        }
        reportLoad();
    }

    // ── out of ammo, and attack tokens (PLAN.md 1g b2/b3) ─────────────────────

    /** Within this distance of its player a dry unit fights on with fists / baton rather than leaving. */
    static final double DRY_MELEE = 4.0;
    /** An attack token is held this long, then given back and not taken again for TOKEN_REST (rotation). */
    static final double TOKEN_HOLD = 4.0, TOKEN_REST = 1.5;

    /** One line of radio chatter to the local player, at most every 4 s. */
    void radio(Player p, String side, String what) { radio(p != null && p.getCharacterInfo() != null ? p.getCharacterInfo().characterId : "", side, what); }

    /** One line of radio chatter to {@code playerId}'s own screen ("" = everyone's), at most every 4 s for each. */
    void radio(String playerId, String side, String what) {
        String key = playerId == null ? "" : playerId;
        if (clock < radioIn.getOrDefault(key, -1.0)) return;
        radioIn.put(key, clock + 4.0);
        String who = POLICE.equals(side) ? "POLICE RADIO" : side.toUpperCase(java.util.Locale.ROOT) + " RADIO";
        say(key, who + ": " + what);
    }

    /**
     * Put a radio line on the screen of the player it is about (PLAN.md P1e step 4: these used to be emitted on the
     * HOST's EventBus only, so a client never heard "there they are", "lost them" or "regrouping"). Here when that
     * player is this peer's own (or for everyone), and sent to every other peer as WORLD_EVENT_RADIO, where the peer
     * whose player it is shows it ({@link GameManager}).
     */
    void say(String playerId, String line) {
        boolean mine = playerId == null || playerId.isEmpty();
        if (!mine)
            for (Player p : PlayerRegistry.getPlayers())
                if (GD.isInstanceValid(p) && p.getCharacterInfo() != null && playerId.equals(p.getCharacterInfo().characterId)
                        && p.isLocallyOwnedPlayer()) mine = true;
        if (mine && getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus) bus.radioChatter.emit(line);
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && net.isNetworked() && net.isServer()) {
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_RADIO, playerId == null ? "" : playerId, 0f, List.of(line));
            radioSent++;
        }
    }

    int radioSent;

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

    /** "magazines,reserves,full reserves,reloads" summed over every live unit of {@code side}'s firearms (P1e step 1
     *  probe readout: with the AI rule the reserve stays full as they fight, while the reloads rise). */
    @Register
    public String unitAmmoNow(String side) {
        int mag = 0, res = 0, full = 0, reloads = 0;
        for (Unit u : units) {
            if (!side.equals(u.side) || !GD.isInstanceValid(u.body) || u.body.isDead() || u.body.weaponController == null) continue;
            var wc = u.body.weaponController;
            reloads += wc.reloadsStarted();
            for (int i = 1; i < wc.getSlotCount(); i++) {
                if (!(wc.getWeaponItem(i) instanceof com.openworld.weapon.FirearmItem w) || w.isInfiniteAmmo) continue;
                mag += w.getMagazine();
                res += w.getReserve();
                full += w.getReserveMax();
            }
        }
        return mag + "," + res + "," + full + "," + reloads;
    }

    /** "fired,refused,stamped": AI explosives fired and held by the shared cooldown, AI drops made finite (P1e). */
    @Register
    public String aiAmmoCountsNow() {
        return com.openworld.weapon.ExplosiveCooldown.counts() + "," + com.openworld.weapon.AiAmmoRule.stampedCount();
    }

    /** The P1e step 1 controls: the AI reserve rule and the shared explosive cooldown, on or off. */
    @Register
    public void setAiAmmoRulesNow(boolean unlimitedReserve, boolean explosiveCooldown) {
        com.openworld.weapon.AiAmmoRule.unlimitedOverride = unlimitedReserve;
        com.openworld.weapon.ExplosiveCooldown.enabled = explosiveCooldown;
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

    int stuckGivenUp, carsDiscarded;
    /** A patrol car is kept only if its road route is at most this many times the straight distance. */
    static final double ROUTE_DETOUR = 2.5;

    // ── the main gun (PLAN.md W6: a light tank / tank at the top stars) ──────────────────────────────────────────

    static final String SHELL_SCENE = "res://src/main/resources/com/openworld/weapon/ATL1Projectile.tscn";

    int shellsFired;

    // ── breaching a building (PLAN.md W6) ─────────────────────────────────────

    static final class Node3DRef { final Node node; Node3DRef(Node node) { this.node = node; } }

    int interiorSteers;

    /** Probe readout: units switched onto an interior navmesh, and interior regions attached. */
    @Register public String interiorNavNow() {
        return interiorSteers + "," + com.openworld.world.InteriorNav.attachedCount();
    }
    int breachRoutes, breachedIn;

    /** A door already taken by this many units costs this much more (m), so a squad spreads over a building's doors
     *  -- front, back and side -- instead of every unit queueing at the one nearest them (user 2026-10-07). */
    static final double DOOR_SHARE_COST = 25.0;
    /** A breaching unit that has not moved 1.5 m in this long gives up its door (s). */
    static final double BREACH_STUCK_SECONDS = 6.0;
    int doorsGivenUp;
    /** How far outside the building's walls a unit walks round a corner (m). */
    static final double CORNER_MARGIN = 2.5;

    /** Routes that followed a baked door walk (probe readout via escalation_now's breach fields). */
    int bakedRoutes;

    @Register public int bakedRoutesNow() { return bakedRoutes; }

    int doorsForced;

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

    /** How far above a target a roof, a deck or a platform shed counts as cover from the helicopter (m). */
    static final double HELI_COVER_UP = 30.0;

    /** The stars the next {@link #spawnBody} is dressed for (set by spawnFor / guard; the body table is by stars). */
    int bodyStars = 1;
    final Random bodyRng = new Random(0xB0D1E5);
    java.util.Map<String, List<DispatchRules.BodyPick>> gangBodies;

    /** How many units wore each body:outfit (probe readout, "fumiriya:police=3,shino:police=1"). */
    final java.util.Map<String, Integer> dressed = new java.util.TreeMap<>();

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

    /** The host's World density level's body cap (QualitySettings.applyDensity; -1 = not applied: NORMAL's). */
    public static int densityBodyCap = -1;
    /** A probe's override of the cap (-1 = none). */
    static int capOverride = -1;

    /** The island-wide ceiling on dispatched bodies, all sides (game/density.json body_cap of the host's level; 0 = none). */
    int bodyCap() {
        if (capOverride >= 0) return capOverride;
        return densityBodyCap >= 0 ? densityBodyCap : WorldDensity.NORMAL.row().bodyCap();
    }

    /** Dispatched bodies alive right now, every side: units on foot, the crews of cars on their way, helicopter crews
     *  (guards over a captive and hangout members are not the dispatch's load). */
    int dispatchedBodies() {
        int n = 0;
        for (Unit u : units) if (!u.guard && GD.isInstanceValid(u.body) && !u.body.isDead()) n++;
        for (Car c : cars) {
            if (!GD.isInstanceValid(c.car) || c.arrived) continue;
            for (int seat = 0; seat < c.car.getSeatCount(); seat++)
                if (c.car.getSeatOccupant(seat) instanceof AICharacter ai && !ai.isDead()) n++;
        }
        for (Heli h : helis) if (GD.isInstanceValid(h.h) && h.retiredFor == 0) n += 2;
        return n + responders.live();
    }

    /** Bodies the global cap still allows (a large number when there is no cap). */
    int bodyRoom() {
        int cap = bodyCap();
        return cap <= 0 ? Integer.MAX_VALUE / 2 : Math.max(0, cap - dispatchedBodies());
    }

    /** Probe control (PLAN.md P1e step 2): set the global body cap and both sides' incident merge radius (the police
     *  block's and the gang hunters'), overriding the data until the tables are read again. */
    @Register
    public void setCapAndMergeNow(int cap, double mergeRadius) {
        WantedSystem ws = WantedSystem.get();
        GangSystem gs = GangSystem.get();
        capOverride = cap;
        if (ws != null && ws.dispatchRules() != null) ws.dispatchRules().mergeRadius = mergeRadius;
        if (gs != null && gs.hunterRules() != null) gs.hunterRules().mergeRadius = mergeRadius;
    }

    /** "dispatched bodies,cap" (probe readout, PLAN.md P1e step 2). */
    @Register
    public String bodyCapNow() { return dispatchedBodies() + "," + bodyCap(); }

    // ── FINITE FORCES, HELD PER STATION (PLAN.md P1e step 3; game.ForcePools, game/forces.json) ──

    /** Off = the control: every side is unlimited, as before step 3. */
    @godot.annotation.Visible public boolean forcePools = true;
    private ForcePools pools;
    private int poolsVersion = -1;
    /** Hangout members and the station each was drawn from (they are scenery, not units). */
    final Map<AICharacter, ForcePools.Station> hangoutOrigin = new HashMap<>();
    int emptyLulls;
    /** The tier outfit the next spawnBody wears over the stars' row (set around a draw, like bodyStars). */
    String outfitOverride = "";

    /** The pools, bound to this world's places (re-bound when the places record changes). */
    ForcePools pools() {
        int v = com.openworld.world.Places.version();
        if (pools == null || v != poolsVersion) {
            com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
            pools = new ForcePools(f != null ? f.sides() : Map.of());
            List<ForcePools.PlaceRef> refs = new ArrayList<>();
            for (com.openworld.world.Places.Place p : com.openworld.world.Places.all())
                if (p.at() != null) refs.add(new ForcePools.PlaceRef(p.name(), p.kind(), p.gang(), p.at().getX(), p.at().getZ()));
            pools.bind(refs);
            poolsVersion = v;
        }
        return pools;
    }

    /** One body for {@code side} at {@code stars} near {@code at}: a draw (station null = unlimited), or null when the
     *  side's ladder is empty -- then the side rests (see {@link #rest}). */
    ForcePools.Draw draw(Player p, String side, int stars, Vector3 at) {
        if (!forcePools) return new ForcePools.Draw(null, null);
        ForcePools.Draw d = pools().draw(side, stars, at.getX(), at.getZ());
        if (d == null) rest(p, side);
        return d;
    }

    /** The side's ladder is empty: nobody is sent for its empty_lull_seconds ("no units available"), while the
     *  stations regenerate -- a breather, not a win (stars decay as usual once the player is lost). */
    void rest(Player p, String side) {
        if (p == null || p.getCharacterInfo() == null) return;
        String key = p.getCharacterInfo().characterId + "|" + side;
        if (clock < lullUntil.getOrDefault(key, -1.0)) return;
        double secs = pools().emptyLull(side);
        lullUntil.put(key, clock + secs);
        emptyLulls++;
        radioIn.remove(key.substring(0, key.indexOf('|')));
        radio(p, side, "no units available");
    }

    // ── an activity's reserved bodies and incidents (P1e step 5) ──

    private final Map<String, List<ForcePools.Station>> reserved = new HashMap<>();

    /** Take {@code n} bodies of each force from the stations nearest {@code at} for a run (they are the run's own:
     *  the dispatch has that many fewer there). Given back by {@link #releaseReserve}. */
    public void reserveFor(String instanceId, Map<String, Integer> forces, Vector3 at) {
        if (forces == null || forces.isEmpty() || !forcePools) return;
        List<ForcePools.Station> got = reserved.computeIfAbsent(instanceId, k -> new ArrayList<>());
        double x = at != null ? at.getX() : 0, z = at != null ? at.getZ() : 0;
        for (Map.Entry<String, Integer> f : forces.entrySet())
            for (int i = 0; i < f.getValue(); i++) {
                ForcePools.Draw d = pools().draw(f.getKey(), 1, x, z);
                if (d == null || d.station() == null) break;
                got.add(d.station());
            }
    }

    /** The run is over: its reserved bodies are back at their stations, its incidents end. */
    public void releaseReserve(String instanceId) {
        List<ForcePools.Station> got = reserved.remove(instanceId);
        if (got != null) for (ForcePools.Station st : got) settle(st, true);
        incidents().end(instanceId);
    }

    /** Bodies reserved by running activities (probe readout). */
    @Register
    public int reservedNow() {
        int n = 0;
        for (List<ForcePools.Station> l : reserved.values()) n += l.size();
        return n;
    }

    // ── the incident board (P1e steps 4-7, game.IncidentBoard) ──

    private IncidentBoard board;

    IncidentBoard incidents() {
        if (board == null) {
            com.openworld.game.data.Tables.Forces f = com.openworld.game.data.Tables.FORCES.get();
            board = new IncidentBoard(f != null && f.incidents() != null ? f.incidents() : IncidentBoard.Rules.DEFAULT);
        }
        return board;
    }

    /** Raise an incident (an activity's, a crime's) at {@code at}; null at = nowhere, nothing raised. */
    public IncidentBoard.Raised raiseIncident(String type, Vector3 at, String source) {
        if (at == null) return null;
        return incidents().raise(type, at.getX(), at.getZ(), "", "", source, clock);
    }

    /** "live,started,refused,ai incidents,player incidents,answered,live responders" (probe readout). */
    @Register
    public String incidentsNow() {
        return incidents().live(clock).size() + "," + incidents().startedCount() + "," + incidents().refusedCount() + ","
                + responders.aiIncidents + "," + responders.playerIncidents + "," + responders.answered + "," + responders.live();
    }

    /** A respawn (death, arrest, abduction) takes every radio the player had (P1e step 7). */
    public void loseRadios(String playerId) { radioNet.lose(playerId); }

    /** Probe / harness: a radio line for one player's screen ("" = everyone), delivered as the dispatch's own are. */
    @Register
    public void radioToNow(String playerId, String line) { say(playerId, line); }

    /** Probe: take every radio a player has (what a respawn does). */
    @Register
    public void loseRadiosNow(String playerId) { radioNet.lose(playerId); }

    /** "type|victim|attacker|x|z|acts;..." for every live incident (probe readout). */
    @Register
    public String incidentListNow() {
        StringBuilder b = new StringBuilder();
        for (IncidentBoard.Incident i : incidents().live(clock))
            b.append(b.length() > 0 ? ";" : "").append(i.type).append('|').append(i.victim).append('|').append(i.attacker)
                    .append('|').append(String.format(java.util.Locale.ROOT, "%.0f|%.0f", i.x, i.z)).append('|').append(i.acts);
        return b.toString();
    }

    /** Probe: give a player a channel's radio outright. */
    @Register
    public void giveRadioNow(String playerId, String channel) { radioNet.give(playerId, channel); }

    /** The channels a player hears now, comma separated (probe readout). */
    @Register
    public String radioOfNow(String playerId) { return radioNet.channelsOf(playerId); }

    /** "lines told,radios taken,markers live here,markers received" (probe readout). */
    @Register
    public String radioNowCounts() {
        return radioNet.linesSent + "," + radioNet.itemsTaken + "," + RadioMarkers.live().size() + "," + RadioMarkers.receivedCount();
    }

    /** Probe: raise an incident of {@code type} against {@code victim} by {@code attacker} at a point. */
    @Register
    public void raiseIncidentNow(String type, Vector3 at, String victim, String attacker) {
        incidents().raise(type, at.getX(), at.getZ(), victim, attacker, "probe", clock);
    }

    /** Probe: a body of {@code side} dressed and armed as the dispatch does it, NOT a unit (nobody steers it). */
    @Register
    public Node spawnBodyNow(String side, Vector3 at, String weapon) { return spawner.spawnBody(side, at, weapon); }

    /** Per-target hostility on / off (the control, P1e step 4). */
    @Register
    public void setPerTargetHostilityNow(boolean on) { Hostility.enabled = on; }

    /** Probe: hold EVERY player as an activity would (P1e step 5), until {@link #releaseHoldNow}. Empty / 0 = not asked. */
    @Register
    public void holdNow(String instanceId, int atLeast, int atMost, String noDispatchSide, String squadForce, int squadStars,
                        String reserveForce, int reserveN) {
        com.openworld.game.activity.Plan p = new com.openworld.game.activity.Plan();
        if (atLeast > 0) p.wantedAtLeast(atLeast);
        if (atMost >= 0) p.wantedAtMost(atMost);
        if (!noDispatchSide.isEmpty()) p.noDispatch(noDispatchSide);
        if (!squadForce.isEmpty() && squadStars > 0) p.squad(squadForce, squadStars);
        if (!reserveForce.isEmpty() && reserveN > 0) p.reserve(reserveForce, reserveN);
        java.util.function.BiPredicate<String, String> was = EnforcementHooks.participant;
        EnforcementHooks.participant = (inst, pid) -> inst.equals(instanceId) || was.test(inst, pid);
        EnforcementHooks.register(instanceId, p.enforcement());
        Player any = PlayerRegistry.getPlayers().isEmpty() ? null : PlayerRegistry.getPlayers().get(0);
        reserveFor(instanceId, p.enforcement().reserves, any != null ? any.getGlobalPosition() : null);
    }

    @Register
    public void releaseHoldNow(String instanceId) {
        EnforcementHooks.release(instanceId);
        releaseReserve(instanceId);
    }

    /** The AI-vs-AI incidents and their responders on / off (the control, P1e step 6). */
    @Register
    public void setAiIncidentsNow(boolean on) { responders.enabled = on; }

    /** Is {@code characterId} on duty -- a dispatched unit, a car's crew, a responder (its acts are no incident)? */
    boolean onDuty(String characterId) {
        if (characterId == null || characterId.isEmpty()) return false;
        for (Unit u : units)
            if (GD.isInstanceValid(u.body) && u.body.getCharacterInfo() != null && characterId.equals(u.body.getCharacterInfo().characterId))
                return true;
        for (Car c : cars)
            if (GD.isInstanceValid(c.car))
                for (int seat = 0; seat < c.car.getSeatCount(); seat++)
                    if (c.car.getSeatOccupant(seat) instanceof AICharacter ai && ai.getCharacterInfo() != null
                            && characterId.equals(ai.getCharacterInfo().characterId)) return true;
        return responders.isResponder(characterId);
    }

    /** A dispatched body has left the game: back to its station if it is ALIVE, gone (until regenerated) if not. */
    void settle(ForcePools.Station st, boolean alive) {
        if (st == null || pools == null) return;
        if (alive) pools.giveBack(st); else pools.lose(st);
    }

    /** {@link #settle} for a unit on foot (its body alive and in the world = it walked off). */
    void settle(Unit u) {
        settle(u.origin, GD.isInstanceValid(u.body) && !u.body.isDead());
        u.origin = null;
    }

    /** {@link #settle} for a crew: as many of its stations given back as crew are still alive aboard, the rest lost. */
    void settleCrew(List<ForcePools.Station> origins, godot.api.Node vehicle) {
        int alive = 0;
        if (vehicle instanceof Vehicle v && GD.isInstanceValid(v))
            for (int seat = 0; seat < v.getSeatCount(); seat++)
                if (v.getSeatOccupant(seat) instanceof AICharacter ai && !ai.isDead()) alive++;
        for (ForcePools.Station st : origins) settle(st, alive-- > 0);
        origins.clear();
    }

    /** Hangout members gone from the world: the dead are lost, the living (taken away by GangHangouts) went back. */
    private void sweepHangouts() {
        Iterator<Map.Entry<AICharacter, ForcePools.Station>> it = hangoutOrigin.entrySet().iterator();
        while (it.hasNext()) {
            var e = it.next();
            if (GD.isInstanceValid(e.getKey()) && !e.getKey().isDead()) continue;
            settle(e.getValue(), false);
            it.remove();
        }
    }

    /** GangHangouts is taking a LIVE member away (every player left): it goes back to its place's count. */
    void hangoutLeft(AICharacter m) {
        ForcePools.Station st = hangoutOrigin.remove(m);
        settle(st, true);
    }

    /**
     * A crime was CALLED IN from {@code where} (WantedSystem, P1e step 4): {@code side} knows where it happened, not
     * where the player is now -- so units are sent there and search, until one sees the player.
     */
    public void reportedAt(String playerId, String side, Vector3 where) {
        if (playerId == null || where == null || !searchPhase) return;
        Sight s = sightOf.computeIfAbsent(playerId + "|" + side, k -> new Sight());
        s.lastKnown = where;
        s.lostFor = Math.max(s.lostFor, LOST_GRACE);
        s.lostSaid = true;                 // no "lost them": they never had them
    }

    // ── restricted areas (P1e step 3, GTA V style): a warning first, then the trespass ──

    /** Per player: seconds inside the current restricted area, and whether this visit has already been reported. */
    private final Map<String, Double> insideFor = new HashMap<>();
    private final java.util.Set<String> trespassed = new java.util.HashSet<>();
    int trespasses;

    private void restrictedAreas(Map<String, Player> players, WantedSystem ws) {
        List<RestrictedAreas.Area> areas = RestrictedAreas.all();
        if (areas.isEmpty() || ws == null) return;
        for (Map.Entry<String, Player> e : players.entrySet()) {
            Player p = e.getValue();
            Vector3 at = p.getGlobalPosition();
            RestrictedAreas.Area a = p.isAlive() ? RestrictedAreas.at(areas, at.getX(), at.getZ()) : null;
            if (a == null) { insideFor.remove(e.getKey()); trespassed.remove(e.getKey()); continue; }
            double t = insideFor.merge(e.getKey(), TICK, Double::sum);
            if (!trespassed.contains(e.getKey()) && RestrictedAreas.trespass(a, at.getX(), at.getZ(), t)) {
                trespassed.add(e.getKey());
                trespasses++;
                // a crime is an EVENT (PLAN.md 2.0): an activity may sanction it (a mission into the base)
                com.openworld.game.event.GameplayEvents.publish(new com.openworld.game.event.GameplayEvent.Trespassed(
                        com.openworld.game.event.Actors.of(p), com.openworld.game.event.Actors.at(at), a.name()));
                radio(p, POLICE, "trespass at " + a.name() + " -- all units");
            }
        }
    }

    /** "trespasses,seconds inside now" for a player (probe readout). */
    @Register
    public String trespassNow(String playerId) {
        return trespasses + "," + String.format("%.1f", insideFor.getOrDefault(playerId, 0.0));
    }

    /** The debug console's {@code pools} and a probe's readout: per side and tier, on hand / full, drawn, lost. */
    @Register
    public String poolsNow() {
        return (forcePools ? "" : "(force pools OFF: unlimited)\n") + pools().report() + "\nempty-ladder lulls " + emptyLulls;
    }

    /** "on hand,full" for one side (every tier) -- probe readout. */
    @Register
    public String poolOfNow(String side) {
        int have = 0, full = 0;
        for (ForcePools.Station st : pools().stations()) if (st.side.equals(side)) { have += st.available(); full += st.max; }
        return have + "," + full;
    }

    /** Probe: empty every station of a side (the "all spent" case). */
    @Register
    public void drainPoolNow(String side) {
        pools().empty(side);
    }

    void reportLoad() {
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

    // ── the external API, kept on the Node (the parts are package-private Java, not registered) ──

    /** See {@link UnitSpawner#guard}. */
    public void guard(Player p, String gang, Vector3 at, int n, List<String> weapons) { spawner.guard(p, gang, at, n, weapons); }

    /** See {@link UnitSpawner#spawnHangoutBody}. */
    AICharacter spawnHangoutBody(String gang, Vector3 at, String weapon) { return spawner.spawnHangoutBody(gang, at, weapon); }

    /** See {@link DispatchSight#searchArea}. */
    public double[] searchArea(String playerId) { return sightlines.searchArea(playerId); }
}
