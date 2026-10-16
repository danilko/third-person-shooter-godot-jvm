package com.openworld.game;

import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.item.WeaponGrant;
import com.openworld.net.NetworkManager;
import com.openworld.world.RoadGraph;
import com.openworld.world.RoadMap;
import com.openworld.world.ZoneManager;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static com.openworld.game.EnforcementDispatch.*;
import static com.openworld.game.DispatchWorld.*;

/**
 * Cars and helicopters on a call: the road route to the player, ramming, the regroup hold, unloading the crew, the
 * main gun, the helicopter's orbit and its door gunner.
 *
 * <p>A part of {@link EnforcementDispatch} (PLAN.md P1e step 2, a move-only split): the state is the dispatch's
 * ({@code ed}), this holds the code.
 */
final class VehicleDirector {

    private final EnforcementDispatch ed;

    VehicleDirector(EnforcementDispatch ed) { this.ed = ed; }

    // ── cars ──────────────────────────────────────────────────────────────────

    void tickCars(Map<String, Player> players, Map<String, Map<String, Integer>> demand,
                          DispatchRules police, DispatchRules hunters) {
        Iterator<Car> it = ed.cars.iterator();
        while (it.hasNext()) {
            Car c = it.next();
            if (!GD.isInstanceValid(c.car)) { ed.settleCrew(c.crewOrigins, null); it.remove(); continue; }
            c.age += TICK;
            Player p = players.get(c.playerId);
            boolean wanted = p != null && demand.getOrDefault(c.playerId, Map.of()).containsKey(c.side);
            DispatchRules r = POLICE.equals(c.side) ? police : hunters;
            Vector3 at = c.car.getGlobalPosition();
            boolean seenNow = ed.geometry.inView(at);
            double far = nearestPlayer(at);
            int starsNow = p != null ? demand.getOrDefault(c.playerId, Map.of()).getOrDefault(c.side, 0) : 0;
            if (c.gun && wanted && r != null && p != null && p.isAlive() && !ed.sightlines.lost(c.playerId, c.side)) fireMainGun(c, p, r);
            if (!c.arrived) {
                VehicleAIController ctrl = c.car.getController() instanceof VehicleAIController v ? v : null;
                // the regroup lull (1g b3): a car sent before it started stops where it is and waits it out, or its
                // crew would arrive inside the player's escape window. A gun vehicle (armour) keeps coming: the lull
                // is not started while one is on the player, and one sent later is not held.
                boolean lullNow = ed.clock < ed.lullUntil.getOrDefault(c.playerId + "|" + c.side, -1.0);
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
                        && !ed.sightlines.lost(c.playerId, c.side);
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
                    if (!seenNow || !wanted) { ed.settleCrew(c.crewOrigins, c.car); ed.zm().freeServiceCar(c.car); it.remove(); }
                    continue;
                }
                double d = ed.sightlines.believed(p, c.side).distanceTo(at);
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
                        Vector3 pp = ed.sightlines.believed(p, c.side);
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
                ed.settleCrew(c.crewOrigins, c.car);
                ed.zm().freeServiceCar(c.car);
                it.remove();
            }
        }
    }

    /** The car has stopped by the player: its crew gets out and joins the units on foot; the brain is removed. */
    void unload(Car c) {
        c.arrived = true;
        NetworkManager net = ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
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
            ai.setSquad(ed.spawner.squadFor(c.playerId, c.side));
            if (!c.crewOrigins.isEmpty()) u.origin = c.crewOrigins.remove(0);   // each walks off with its station
            ed.units.add(u);
        }
        for (ForcePools.Station st : c.crewOrigins) ed.settle(st, false);        // seats whose crew died aboard
        c.crewOrigins.clear();
        c.car.removeAiDriverBrain();
    }

    void spawnCar(Player p, String side, DispatchRules r, WantedSystem ws, int stars) {
        ZoneManager z = ed.zm();
        if (z == null) return;
        List<String> models = r.vehiclesFor(stars);
        String model = models.isEmpty() ? "" : models.get(ed.rng.nextInt(models.size()));
        String scene = com.openworld.carrier.vehicle.VehicleModels.sceneOfId(model);
        Vehicle v = z.spawnServiceCar(side, scene != null ? scene : "", ed.sightlines.sendTo(p, side), (float) r.carMin, (float) r.carMax);
        if (v == null) return;
        String pid = p.getCharacterInfo().characterId;
        // a car whose ROAD route is far longer than the straight line (the far side of a river, a one-way loop) is
        // no use: discarded at once, out of view, and the next tick tries another lane
        RoadGraph g = RoadMap.graph();
        if (g != null && v.getController() instanceof VehicleAIController c0 && c0.getRoute() instanceof Node ln) {
            Vector3 pp = ed.sightlines.sendTo(p, side);
            RoadGraph.Route route = g.routeFromLane(ln.getName().toString(), 0.0, pp.getX(), pp.getY(), pp.getZ());
            double straight = flat(v.getGlobalPosition(), pp);
            if (route == null || route.length > Math.max(400.0, ROUTE_DETOUR * straight)) {
                z.freeServiceCar(v);
                ed.carsDiscarded++;
                return;
            }
            c0.setPlan(route.laneIds());
        }
        // its crew is drawn from the stations (P1e step 3): the driver and every partner, by the car's own spot
        List<ForcePools.Draw> crew = new ArrayList<>();
        for (int k = 0; k < Math.max(1, Math.min(r.carCrew, v.getSeatCount())); k++) {
            ForcePools.Draw dr = ed.draw(p, side, stars, v.getGlobalPosition());
            if (dr == null) break;
            crew.add(dr);
        }
        if (crew.size() < Math.max(1, Math.min(r.carCrew, v.getSeatCount()))) {
            for (ForcePools.Draw dr : crew) ed.settle(dr.station(), true);
            z.freeServiceCar(v);
            return;
        }
        if (v.getController() instanceof VehicleAIController ctrl) {
            ctrl.racing = true;          // a car on a call does not wait its turn at a junction
            ctrl.cruiseThrottle = 0.8f;
        }
        AISquad sq = ed.spawner.squadFor(pid, side);
        // the driver (seated by ZoneManager) is armed and joins the squad; a partner rides beside
        if (v.getOccupant() instanceof AICharacter drv) {
            String w = ed.spawner.weaponFor(side, pid, r, ws, stars);
            if (!w.isEmpty()) WeaponGrant.grant(drv, w, ed);
            drv.setSquad(sq);
            // a traffic driver is seated with empty hands (Vehicle.seatQuietly); one on a call rides ready
            drv.setSeatedCombat(true);
        }
        for (int seat = 1; seat < Math.min(r.carCrew, v.getSeatCount()); seat++) {
            ed.outfitOverride = crew.get(Math.min(seat, crew.size() - 1)).tier() != null
                    ? crew.get(Math.min(seat, crew.size() - 1)).tier().outfit() : "";
            AICharacter mate = ed.spawner.spawnBody(side, v.getGlobalPosition(), ed.spawner.weaponFor(side, pid, r, ws, stars));
            ed.outfitOverride = "";
            if (mate == null) break;
            v.seatQuietly(mate, seat, false);   // the car is built with its crew aboard: no door
            if (ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && v.getCharacterInfo() != null)
                net.broadcastVehicleOccupancy(v.getCharacterInfo().characterId, mate.getCharacterInfo().characterId,
                        v.getCharacterInfo().ownerPeerId, true, seat, true);
        }
        Car c = new Car();
        c.car = v;
        c.side = side;
        c.playerId = pid;
        c.model = model;
        c.gun = r.hasGun(model);
        for (ForcePools.Draw dr : crew) c.crewOrigins.add(dr.station());
        ed.cars.add(c);
        v.setEmergency(POLICE.equals(side));      // light bar + siren while on a call
    }

    /** Fire a shell from the turret at the player: in range, on a clear line, every gun_interval seconds. The shell is
     *  the ATL1 rocket's projectile, flown on this (the authoritative) peer; other peers see its detonation. */
    void fireMainGun(Car c, Player p, DispatchRules r) {
        c.gunIn -= TICK;
        if (c.gunIn > 0) return;
        Vector3 at = c.car.getGlobalPosition();
        double d = flat(at, p.getGlobalPosition());
        if (d > r.gunRange || d < 12.0) return;
        Vector3 up = c.car.getGlobalTransform().getBasis().getColumn(1);
        Vector3 fwd = c.car.getGlobalTransform().getBasis().getColumn(2).times(-1.0);
        Vector3 muzzle = at.plus(up.times(2.6)).plus(fwd.times(3.0));
        Vector3 aimAt = p.getGlobalPosition().plus(new Vector3(0, 1.0, 0));
        if (!ed.geometry.clearLine(muzzle.minus(new Vector3(0, 0.6, 0)), aimAt.minus(new Vector3(0, 0.6, 0)))) return;
        // the area's shared explosive cooldown (P1e step 1): a launcher just fired here holds the main gun too
        Vector3 tp = p.getGlobalPosition();     // the incident's area is the target's
        if (!com.openworld.weapon.ExplosiveCooldown.ready(tp.getX(), tp.getZ(), com.openworld.weapon.ExplosiveCooldown.now())) return;
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
        ed.getTree().getCurrentScene().addChild(rp);
        Vector3 dir = aimAt.minus(muzzle).normalized();
        rp.setGlobalPosition(muzzle);
        rp.lookAt(muzzle.plus(dir));
        rp.setLinearVelocity(dir.times(90.0));
        rp.addCollisionExceptionWith(c.car);
        c.gunIn = r.gunInterval;
        ed.shellsFired++;
        com.openworld.weapon.ExplosiveCooldown.mark(tp.getX(), tp.getZ(), com.openworld.weapon.ExplosiveCooldown.now());
    }

    // ── helicopters (PLAN.md W6) ──────────────────────────────────────────────

    /** In the air, out of view, 220-280 m from the player and 60 m up, a pilot and a gunner aboard, orbiting. */
    void spawnHeli(Player p, String side) {
        if (!(GD.load(HELI_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof com.openworld.carrier.helicopter.Helicopter h))
            return;
        Vector3 pp = p.getGlobalPosition();
        Vector3 at = null;
        for (int k = 0; k < 12 && at == null; k++) {
            double a = ed.rng.nextDouble() * Math.PI * 2, d = 220.0 + ed.rng.nextDouble() * 60.0;
            Vector3 q = new Vector3(pp.getX() + Math.cos(a) * d, pp.getY() + 60.0, pp.getZ() + Math.sin(a) * d);
            if (!ed.geometry.inView(q)) at = q;
        }
        if (at == null) { h.queueFree(); return; }
        // a pilot and a gunner, drawn from the stations (P1e step 3)
        ForcePools.Draw pilot = ed.draw(p, side, ed.bodyStars, pp), gunner = pilot == null ? null : ed.draw(p, side, ed.bodyStars, pp);
        if (gunner == null) {
            if (pilot != null) ed.settle(pilot.station(), true);
            h.queueFree();
            return;
        }
        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = "Police helicopter";
        info.faction = side;
        h.characterInfo = info;
        Node container = ed.getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = ed.getTree().getCurrentScene();
        container.addChild(h);
        h.setGlobalPosition(at);
        h.aiTarget = p;
        h.setEmergency(POLICE.equals(side));
        if (ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) net.announceVehicleSpawn(h);
        for (int seat = 0; seat < Math.min(2, h.getSeatCount()); seat++) {
            AICharacter crew = ed.spawner.spawnBody(side, at, seat == 0 ? "" : "SNR1");
            if (crew == null) break;
            h.tryEnter(crew, seat);
        }
        Heli e = new Heli();
        e.h = h;
        e.side = side;
        e.playerId = p.getCharacterInfo().characterId;
        e.crewOrigins.add(pilot.station());
        e.crewOrigins.add(gunner.station());
        ed.helis.add(e);
    }

    void tickHelis(Map<String, Player> players, Map<String, Map<String, Integer>> demand) {
        Iterator<Heli> it = ed.helis.iterator();
        while (it.hasNext()) {
            Heli e = it.next();
            if (!GD.isInstanceValid(e.h)) { ed.settleCrew(e.crewOrigins, null); it.remove(); continue; }
            e.age += TICK;
            Player p = players.get(e.playerId);
            boolean wanted = p != null && p.isAlive() && demand.getOrDefault(e.playerId, Map.of()).containsKey(e.side);
            if (!wanted || e.h.getHealthNow() <= 0) {
                // stand down: fly off (a wide orbit), freed out of view or after a while
                e.retiredFor += TICK;
                e.h.orbitRadius = 600.0;
                e.h.setEmergency(false);
                if ((e.retiredFor > 6.0 && !ed.geometry.inView(e.h.getGlobalPosition())) || e.retiredFor > 40.0) {
                    ed.settleCrew(e.crewOrigins, e.h.getHealthNow() > 0 ? e.h : null);   // a downed helicopter's crew is lost
                    for (int seat = e.h.getSeatCount() - 1; seat >= 0; seat--)
                        if (e.h.getSeatOccupant(seat) instanceof AICharacter ai) ed.spawner.free(ai);
                    if (ed.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && e.h.getCharacterInfo() != null)
                        net.announceDespawn(e.h.getCharacterInfo().characterId);
                    e.h.queueFree();
                    it.remove();
                }
                continue;
            }
            e.retiredFor = 0;
            e.h.orbitRadius = 55.0;
            e.h.aiTarget = p;
            if (!ed.sightlines.lost(e.playerId, e.side)) heliFire(e, p);     // nobody shoots what nobody sees
        }
    }

    /** The door gun (bursts) and the sniper aboard: hitscan from the cabin door at the player, each shot hitting with
     *  its chance when the line is clear and the range short enough; tracers either way. */
    void heliFire(Heli e, Player p) {
        Vector3 gun = e.h.getGlobalPosition().plus(new Vector3(0, -1.2, 0));
        Vector3 chest = p.getGlobalPosition().plus(new Vector3(0, 1.1, 0));
        double d = gun.distanceTo(chest);
        // a gunner in a helicopter hits nobody UNDER COVER (user 2026-10-07: shot on Central's stairs with no shooter in
        // sight): anything solid over the target within HELI_COVER_UP blocks it, even where a gap lines up with the door
        boolean clear = d <= HELI_RANGE && !ed.geometry.underCover(chest) && ed.geometry.clearShot(gun, chest, e.h);
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

    void heliShot(Heli e, Player p, Vector3 gun, Vector3 chest, boolean clear, double chance, double dmg, String what) {
        ed.heliShots++;
        boolean hit = clear && ed.rng.nextDouble() < chance;
        Vector3 end = hit ? chest : chest.plus(new Vector3((ed.rng.nextDouble() - 0.5) * 6.0, (ed.rng.nextDouble() - 0.5) * 2.0,
                (ed.rng.nextDouble() - 0.5) * 6.0));
        for (Node n : ed.getTree().getNodesInGroup(new StringName("bullet_tracer_manager"))) {
            if (n instanceof com.openworld.world.manager.BulletTracerManager tm) { tm.spawnTracer(gun, end); break; }
        }
        if (!hit) return;
        for (Node n : ed.getTree().getNodesInGroup(new StringName("impact_manager"))) {
            if (n instanceof com.openworld.world.manager.ImpactManager im) {
                im.processHit(new com.openworld.world.HitInfo(p, chest, gun.minus(chest).normalized()), (float) dmg, what,
                        null, "Police", e.side, gun, e.h.getCharacterInfo() != null ? e.h.getCharacterInfo().characterId : "");
                ed.heliHits++;
                break;
            }
        }
    }
}
