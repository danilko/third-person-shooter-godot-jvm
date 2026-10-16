package com.openworld.game;

import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.item.WeaponGrant;
import com.openworld.net.NetworkManager;
import com.openworld.world.Sidewalks;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.UUID;

import static com.openworld.game.EnforcementDispatch.*;
import static com.openworld.game.DispatchWorld.*;

/**
 * Spawning: what a standing calls for each tick ({@link #spawnFor}), foot units, snipers, guards over a captive,
 * hangout members, the body / uniform / weapon each wears, squads, and freeing a body.
 *
 * <p>A part of {@link EnforcementDispatch} (PLAN.md P1e step 2, a move-only split): the state is the dispatch's
 * ({@code ed}), this holds the code.
 */
final class UnitSpawner {

    private final EnforcementDispatch ed;

    UnitSpawner(EnforcementDispatch ed) { this.ed = ed; }

    /**
     * The guards over an abducted player (RespawnSystem): {@code n} armed members of {@code gang} round {@code at},
     * covering the player until they run (then they fight) or pay (then they stand down).
     */
    public void guard(Player p, String gang, Vector3 at, int n, List<String> weapons) {
        if (p == null || p.getCharacterInfo() == null || !ed.authority()) return;
        String pid = p.getCharacterInfo().characterId;
        ed.bodyStars = 3;
        for (int i = 0; i < n; i++) {
            double a = Math.PI * 2 * i / Math.max(1, n) + 0.4;
            double d = 3.0 + (i % 2) * 1.5;
            Vector3 g = ed.geometry.ground(at.getX() + Math.cos(a) * d, at.getZ() + Math.sin(a) * d, at.getY());
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
            ed.units.add(u);
        }
    }

    // ── spawning ──────────────────────────────────────────────────────────────

    /** Is a unit / car / helicopter on {@code ownerId} part of the same INCIDENT as player {@code p} -- the same
     *  player, or another one within merge_radius of them (co-op players together are one incident, PLAN.md P1e step
     *  2: two players side by side used to draw a full complement EACH)? */
    private boolean sameIncident(String ownerId, String pid, Vector3 pp, double mergeRadius) {
        if (pid.equals(ownerId)) return true;
        if (mergeRadius <= 0) return false;
        for (Player o : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(o) || o.getCharacterInfo() == null || !ownerId.equals(o.getCharacterInfo().characterId)) continue;
            return flat(o.getGlobalPosition(), pp) <= mergeRadius;
        }
        return false;
    }

    void spawnFor(Player p, String side, int stars, DispatchRules r, WantedSystem ws) {
        if (p == null || !p.isAlive()) return;
        ed.bodyStars = stars;
        String pid = p.getCharacterInfo().characterId;
        Vector3 pp = p.getGlobalPosition();
        double merge = r.mergeRadius;
        // what is already on this INCIDENT: this player's units and those of every player standing with them
        int foot = 0, carsEnRoute = 0;
        for (Unit u : ed.units) {
            if (side.equals(u.side) && GD.isInstanceValid(u.body) && !u.body.isDead() && u.body.currentVehicleNode == null
                    && !u.guard && sameIncident(u.playerId, pid, pp, merge)) foot++;   // a unit walking off still counts:
            // it is a live body until it is freed, and replacing it at once churned 100+ spawns a leg (perf probe)
        }
        for (Car c : ed.cars) if (side.equals(c.side) && !c.arrived && sameIncident(c.playerId, pid, pp, merge)) carsEnRoute++;
        // the regroup lull (1g b3): half the units ran dry, the next wave is held back -- the player's escape window
        if (ed.clock < ed.lullUntil.getOrDefault(pid + "|" + side, -1.0)) return;
        // LOST and far from where they were last seen: nobody is sent. A unit set down at the last known position
        // would be past despawn_far of every player and freed on the next tick -- a spawn / free churn for nothing
        if (flat(ed.sightlines.sendTo(p, side), pp) > r.despawnFar - 20.0) return;
        // the GLOBAL BODY CAP (PLAN.md P1e step 2): every dispatched body on the island, all sides, counts against one
        // ceiling -- per-player tables alone put ~150 bodies round 4 co-op players at 5 stars with two gangs
        int room = ed.bodyRoom();
        for (int i = DispatchRules.toSpawn(r.carsFor(stars), carsEnRoute, 1); i > 0 && room >= r.carCrew; i--) {
            ed.vehicleDirector.spawnCar(p, side, r, ws, stars);
            room = ed.bodyRoom();
        }
        int snipers = 0;
        for (Unit u : ed.units) if (u.sniper && side.equals(u.side) && GD.isInstanceValid(u.body) && !u.body.isDead()
                && sameIncident(u.playerId, pid, pp, merge)) snipers++;
        for (int i = DispatchRules.toSpawn(r.snipersFor(stars), snipers, 1); i > 0 && room >= 1; i--) {
            spawnSniper(p, side);
            room = ed.bodyRoom();
        }
        int hs = 0;
        for (Heli h : ed.helis) if (side.equals(h.side) && GD.isInstanceValid(h.h) && h.retiredFor == 0
                && sameIncident(h.playerId, pid, pp, merge)) hs++;
        for (int i = DispatchRules.toSpawn(r.helisFor(stars), hs, 1); i > 0 && room >= 2; i--) {
            ed.vehicleDirector.spawnHeli(p, side);
            room = ed.bodyRoom();
        }
        for (int i = Math.min(room, DispatchRules.toSpawn(r.footFor(stars), foot - snipers, ed.spawnPerTick)); i > 0; i--) {
            Vector3 at = footSpot(ed.sightlines.sendTo(p, side), r.footMin, r.footMax);
            if (at == null) break;
            // drawn from the nearest station of its tier with a body on hand (P1e step 3); none = the side rests
            ForcePools.Draw dr = ed.draw(p, side, stars, pp);
            if (dr == null) break;
            ed.outfitOverride = dr.tier() != null ? dr.tier().outfit() : "";
            AICharacter ai = spawnBody(side, at, weaponFor(side, pid, r, ws, stars));
            ed.outfitOverride = "";
            if (ai == null) { ed.settle(dr.station(), true); break; }
            Unit u = new Unit();
            u.body = ai;
            u.side = side;
            u.playerId = pid;
            u.origin = dr.station();
            // held until the token pass hands it one: units are spawned AFTER assignTokens in the tick, so a new
            // unit otherwise attacked unbidden for a tick (probe_ammo_supply saw 4 attackers on 3 tokens)
            ai.attackHeld = ed.attackTokens;
            ed.units.add(u);
        }
    }

    String weaponFor(String side, String pid, DispatchRules r, WantedSystem ws) {
        return weaponFor(side, pid, r, ws, 0);
    }

    /** What a unit carries: the side's row for these stars (PLAN.md W6), and for police the lethal list on top once
     *  the player is lethal-wanted; a side with no rows uses its flat list. */
    String weaponFor(String side, String pid, DispatchRules r, WantedSystem ws, int stars) {
        List<String> list = new ArrayList<>(r.weaponsFor(stars));
        if (POLICE.equals(side)) {
            if (list.isEmpty() || (ws != null && ws.isLethal(pid))) list.addAll(ws != null ? ws.policeWeaponsFor(pid) : List.of());
        } else if (list.isEmpty()) list.addAll(r.weapons);
        return list.isEmpty() ? "" : list.get(ed.rng.nextInt(list.size()));
    }

    // ── snipers ───────────────────────────────────────────────────────────────

    /** A sniper 90-160 m out, out of view, at a spot with a clear line to the player at head height; SNR1, a long
     *  sight and a modest hit chance. Holds there (tickUnits). */
    void spawnSniper(Player p, String side) {
        Vector3 pp = p.getGlobalPosition();
        for (int k = 0; k < 24; k++) {
            double a = ed.rng.nextDouble() * Math.PI * 2, d = 90.0 + ed.rng.nextDouble() * 70.0;
            Vector3 g = ed.geometry.ground(pp.getX() + Math.cos(a) * d, pp.getZ() + Math.sin(a) * d, pp.getY() + 10.0);
            if (g == null || ed.geometry.inView(g)) continue;
            if (!ed.geometry.clearLine(g.plus(new Vector3(0, 1.0, 0)), pp.plus(new Vector3(0, 0.6, 0)))) continue;
            ForcePools.Draw dr = ed.draw(p, side, ed.bodyStars, pp);
            if (dr == null) return;
            ed.outfitOverride = dr.tier() != null ? dr.tier().outfit() : "";
            AICharacter ai = spawnBody(side, g, "SNR1");
            ed.outfitOverride = "";
            if (ai == null) { ed.settle(dr.station(), true); return; }
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
            u.origin = dr.station();
            ed.units.add(u);
            return;
        }
    }

    /** Which body and uniform a unit of {@code side} wears at {@link #bodyStars} (PLAN.md 1g c); null = the scene's own. */
    DispatchRules.BodyPick bodyFor(String side) {
        List<DispatchRules.BodyPick> rows;
        if (POLICE.equals(side)) {
            WantedSystem ws = WantedSystem.get();
            rows = ws != null && ws.dispatchRules() != null ? ws.dispatchRules().bodies : null;
        } else {
            if (ed.gangBodies == null) {
                com.openworld.game.data.Tables.Gangs g = com.openworld.game.data.Tables.GANGS.get();
                ed.gangBodies = g != null ? g.bodies() : new java.util.HashMap<>();
            }
            rows = ed.gangBodies.get(side);
        }
        // its own stream: drawing from `rng` would move every later spawn spot (probe_breach's units then started
        // from a different place and gave up the store's door)
        return DispatchRules.pickBody(rows, ed.bodyStars, ed.bodyRng.nextDouble());
    }

    /** A gang member standing at one of its gang's places ({@link GangHangouts}): the dispatch's body, uniform and
     *  weapon rules, but NOT pinned to the active LOD tier (it is scenery until it is provoked). */
    AICharacter spawnHangoutBody(String gang, Vector3 at, String weapon) {
        // a hangout member DEBITS its gang's places (P1e step 3): a spent gang shows as thinner hangouts. It never
        // starts the gang's "no units" rest -- nobody is hunting anyone here
        ForcePools.Draw dr = ed.forcePools ? ed.pools().draw(gang, 1, at.getX(), at.getZ()) : new ForcePools.Draw(null, null);
        if (dr == null) return null;
        int keep = ed.bodyStars;
        ed.bodyStars = 1;
        AICharacter ai = spawnBody(gang, at, weapon);
        ed.bodyStars = keep;
        if (ai == null) { ed.settle(dr.station(), true); return null; }
        ai.lodPinnedActive = false;
        if (dr.station() != null) ed.hangoutOrigin.put(ai, dr.station());
        return ai;
    }

    /**
     * A PLACED body (PLAN.md 2.2: an Encounter's member, a building's guard): the side's body rows at 1 star, the
     * loadout's uniform and ONE weapon picked by {@code roll} + its extras. Not drawn from a station's pool and not
     * pinned to the active LOD tier -- the caller pins it once it fights. {@code faction} "" = the side.
     */
    AICharacter spawnPlaced(String side, String faction, com.openworld.game.encounter.Loadouts.Loadout l, Vector3 at, double roll) {
        int keep = ed.bodyStars;
        ed.bodyStars = 1;
        ed.outfitOverride = l != null ? l.outfit() : "";
        ed.factionOverride = faction != null ? faction : "";
        AICharacter ai = spawnBody(side, at, l != null ? l.weapon(roll) : "");
        ed.outfitOverride = "";
        ed.factionOverride = "";
        ed.bodyStars = keep;
        if (ai == null) return null;
        ai.lodPinnedActive = false;
        if (l != null) for (String x : l.extra()) WeaponGrant.grant(ai, x, ed);
        return ai;
    }

    AICharacter spawnBody(String side, Vector3 at, String weapon) {
        if (ed.getTree() == null || ed.getTree().getCurrentScene() == null) return null;
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
        // a placed body may be another faction than the body rows it wears (an Encounter's "enemy" crew in gang_a
        // clothes); set before the spawn is announced, so every peer gets the right one
        info.faction = ed.factionOverride != null && !ed.factionOverride.isEmpty() ? ed.factionOverride : side;
        ai.characterInfo = info;
        Node container = ed.getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = ed.getTree().getCurrentScene();
        container.addChild(ai);
        ai.activateForSpawn(at.plus(new Vector3(0, 0.05, 0)));
        ai.lodPinnedActive = true;
        // a body drawn from a tier with its own uniform (special forces, the military: forces.json) wears it whatever
        // the stars' row says (P1e step 3)
        String outfit = ed.outfitOverride != null && !ed.outfitOverride.isEmpty() ? ed.outfitOverride
                : look != null ? look.outfit() : "";
        if (!outfit.isEmpty()) {
            Node mount = ai.getNodeOrNull("VisualsMount");
            if (com.openworld.character.Outfits.apply(mount != null ? mount : ai, outfit) > 0)
                ed.dressed.merge((look != null ? look.body() : "scene") + ":" + outfit, 1, Integer::sum);
        }
        if (look != null) for (String x : look.extraWeapons()) WeaponGrant.grant(ai, x, ed);
        if (weapon != null && !weapon.isEmpty()) WeaponGrant.grant(ai, weapon, ed);
        if (ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) net.announceSpawn(ai);
        return ai;
    }

    AISquad squadFor(String playerId, String side) {
        String key = playerId + "|" + side;
        AISquad sq = ed.squads.get(key);
        if (sq != null && GD.isInstanceValid(sq)) return sq;
        sq = new AISquad();
        sq.setName(new StringName("Squad_" + side + "_" + ed.squads.size()));
        sq.forgetDuration = 30.0f;
        ed.addChild(sq);
        ed.squads.put(key, sq);
        return sq;
    }

    /**
     * Where a unit on foot appears: on the island a footway (Sidewalks) between {@code min} and {@code max} of the
     * player, out of view and on ground a ray confirms; elsewhere (DebugWorld has no footway record) a point in the
     * ring whose ground is within a storey of the player's. Null when nothing qualifies this tick.
     */
    Vector3 footSpot(Vector3 player, double min, double max) {
        List<Sidewalks.Spot> spots = Sidewalks.near(player, max);
        for (int k = 0; k < 10 && !spots.isEmpty(); k++) {
            Sidewalks.Spot s = spots.get(ed.rng.nextInt(spots.size()));
            Vector3 q = s.point();
            double d = flat(q, player);
            if (d < min || d > max || ed.geometry.inView(q)) continue;
            Vector3 g = ed.geometry.ground(q.getX(), q.getZ(), q.getY());
            if (g != null && Math.abs(g.getY() - q.getY()) < 1.0 && spaced(g) && ed.geometry.clearLine(g, player)) return g;
        }
        for (int k = 0; k < 16; k++) {
            double a = ed.rng.nextDouble() * Math.PI * 2, d = min + ed.rng.nextDouble() * (max - min);
            double x = player.getX() + Math.cos(a) * d, z = player.getZ() + Math.sin(a) * d;
            Vector3 g = ed.geometry.ground(x, z, player.getY());
            if (g == null || Math.abs(g.getY() - player.getY()) > 3.0 || ed.geometry.inView(g) || !spaced(g) || !ed.geometry.clearLine(g, player)) continue;
            return g;
        }
        // a player indoors (a shop, a cell) has no clear line from anywhere outside: an out-of-view spot on the
        // footway then, and the unit finds its way by the navmesh (ArrestState's fallback when the line is blocked)
        for (int k = 0; k < 10 && !spots.isEmpty(); k++) {
            Sidewalks.Spot s = spots.get(ed.rng.nextInt(spots.size()));
            Vector3 q = s.point();
            double d = flat(q, player);
            if (d < min || d > max || ed.geometry.inView(q)) continue;
            Vector3 g = ed.geometry.ground(q.getX(), q.getZ(), q.getY());
            if (g != null && Math.abs(g.getY() - q.getY()) < 1.0 && spaced(g)) return g;
        }
        return null;
    }

    /** No live unit within SPAWN_SPACING of a spawn spot. */
    boolean spaced(Vector3 g) {
        for (Unit u : ed.units)
            if (u.body != null && GD.isInstanceValid(u.body) && flat(u.body.getGlobalPosition(), g) < SPAWN_SPACING) return false;
        return true;
    }

    void free(AICharacter ai) {
        if (!GD.isInstanceValid(ai)) return;
        if (ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && ai.getCharacterInfo() != null)
            net.announceDespawn(ai.getCharacterInfo().characterId);
        ai.setSquad(null);
        ai.queueFree();
    }
}
