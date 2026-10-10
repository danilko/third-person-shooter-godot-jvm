# enforcement

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Wanted level, jail respawn, shop counters and healing supplies (PLAN.md W3 / W5, 2026-10-03)
- Police and gang dispatch, and where a downed player wakes (PLAN.md W5, 2026-10-06, user-asked)
- Gang hangouts, and why gang escalation was unreachable in play (PLAN.md 0.1 / H1, 2026-10-09)
- Enforcement escalation: armour, rammers, snipers, a helicopter, and units that come inside (PLAN.md W6, 2026-10-06)
- Co-op correctness batch: purchases, respawn, missions, clock, passenger view (2026-10-06)
- Death is a clip, corpses and drops are cleared, hub stairs have ramps, sheds stop the helicopter (2026-10-07, user-reported)
- A baton at one star, full loads, and a strike while reloading (PLAN.md 1g a/b, 2026-10-07, user-asked)
- Attack tokens, spare ammo in police vehicles, the regroup lull (PLAN.md 1g b2/b3, 2026-10-07)
- Uniforms per force, a think budget for AI, and dummy traffic cars (PLAN.md 1g c/d/e, 2026-10-07)
- Breaching units walk round the BLOCK, on a baked walk grid (PLAN.md 1g f, 2026-10-07)

---

## Wanted level, jail respawn, shop counters and healing supplies (PLAN.md W3 / W5, 2026-10-03)

Gated since (probe_wanted_respawn, probe_shop_clerk, probe_weapon_counter PASS); co-op half below.
- **Death and arrest are not game over in single player** (`game.RespawnSystem`, a child GameManager builds in code).
  The two outcomes are named in Japanese + English and deliberately NOT after another game's cards (user: Japan flavour,
  and to avoid an infringement claim): a death is **入院 HOSPITALIZED** and `RespawnSystem.arrest(player)` is **逮捕 ARRESTED**:
  BOTH wake OUTSIDE (user, 2026-10-06), on the nearest Hospital / HospitalSmall / Clinic or PoliceStation's authored
  respawn points -- `MARK_respawn` Empties in the building's .blend, copied placed into the places record (`respawn`)
  by `island_buildings.py places`, so nothing has to stream; the first point free of bodies, facing the street, the
  fade held until `ZoneManager.streamingPendingNow()` is 0 (max 4 s). Those buildings stand open (`_Shop`); the cells
  and armoury are mission content. Gate `tools/godot/probe_respawn_points.gd` (ground, capsule clear, a wall between
  the point and the building; `--control` moves each point inside). Since 2026-10-06 a third outcome, 拉致 ABDUCTED, and
  bills: see "Police and gang dispatch, and where a downed player wakes". Either: a 4 s card (the sign font, `make_jp_font.py`
  `UI_WORDS`), the running mission FAILS, a fresh Player (fist only, wanted cleared). `GameManager.onCharacterDied` skips GAME_OVER when
  `RespawnSystem.willRespawn`. In co-op the HOST runs it per player (see "Co-op correctness batch"). `enabled` off is the
  control. Gate: `tools/godot/probe_wanted_respawn.gd [-- --world=island] [-- --control]`.
- **The wanted level is DATA** (`game/crimes.json`: crime id -> heat, min stars, witness; `stars_at` thresholds, a
  calm period then a drain), rules in engine-free `game.WantedRules` (`WantedRulesTest`), state in `game.WantedSystem`
  (authority only). A new crime = one row + one `WantedSystem.report(id, where, playerId)` call. Seams today:
  `Health.applyDamage` (a player hurting / killing a civilian or a police officer) and `FirearmItem` (gunfire). A
  witnessed crime needs a living non-player character within `witness_radius`. `ui.WantedStars` draws FIVE stars (police and gangs alike, `WantedRules.MAX_STARS`, 2026-10-08) left
  of the clock. **Replicated (2026-10-08):** the host sends each player's SHOWN standing -- police stars, lethal, the
  worst gang and its stars -- as `WORLD_EVENT_WANTED` (16) when it changes (checked 4x a second) and to a joining peer
  (`WantedSystem.sendBaseline`); a client keeps the mirror and `WantedSystem.hudOf` answers from it (`WantedStars`
  reads that). Heat, timers and the dispatch stay on the host. Gate: `run_net_debugworld.sh` coop "the host's wanted
  stars reach the client's HUD".
- **A shop clerk** (`world.ShopClerkSpot`, from a `MARK_clerk` in the shop's model once the builder supports it; props
  `surrender`, `weapons`, `responders`, `till`): aimed at or hurt, it rolls once by its id -- surrender (crouches) or
  fight (a heavy weapon, faction `vigilante`, the AIController brain). Threatening it is `threaten_clerk`; robbing the
  till afterwards (the nearest `ShopCounter`'s "Empty the till" row) is `rob_store` at EVERY store. LETHAL crimes
  make police hostile to players (`game.FactionFlips`, both directions, the old relation restored afterwards) and
  refuse an arrest. A GRAY-AREA shop (`responders`) adds its gang: armed people come out, and the gang's standing
  rises. Gate `tools/godot/probe_shop_clerk.gd`.
- **Gang standing is separate from the police** (`game.GangSystem`, `game.GangRules`, DATA `game/gangs.json`): stars per
  (player, gang) from hitting/killing members and threatening/robbing its shops; hostile at `attack_at`; survives a
  hospitalisation or an arrest; drains only below `pay_at`, otherwise cleared only by the "Donation" row at that
  gang's gray-area counter. `DefaultFactions.tres` ships police<->player and police<->gangs NEUTRAL. HUD: a second
  star row in the gang's colour.
- **A shop sells through a COUNTER, not floor pads** (user: pads blocked pedestrians and AI). `item.ShopCounter` is a
  sensor box in front of the register (no collider, group `shop_counter`), its `stock` a comma list of catalog weapon
  ids and supply ids; `interact` opens `ui.ShopMenu` (GTA SA's Ammu-Nation list). Every grant goes through
  `item.WeaponGrant` (a carried weapon is refilled), which `WeaponPad` uses too until the pads are removed. A client
  sends `MSG_SHOP_REQUEST` (31); the host checks the owner and that the buyer stands at a counter that sells it.
- **Healing supplies are a WEAPON stack** (user, 2026-10-06; food from a konbini / restaurant / market, medical from a
  hospital, "strange" from an adult shop): `item/supplies.json` rows, one shared scene `weapon/Supply.tscn`
  (`weapon.SupplyItem`, configured by its row; `WeaponCatalog.instantiate` and the inventory manifest route a supply id
  there, so there is no per-kind scene). It sits in the CONSUMABLE slot (key 6), one kind at a time like a grenade
  stack: magazine = count, same kind tops up, another kind displaces it, the last use clears the slot. FIRE uses one on
  yourself (not at full health); holding AIM on another living character within `giveReach` 2.5 m and `giveConeDeg`
  25 deg uses it on THEM, and that character wears an L4D-style rim while targeted (`assets/vfx/outline/
  target_outline.tres`, an inverted-hull `material_overlay`, local only); the drop key gives the stack away. Health is
  applied on the authority; a client sends `MSG_SUPPLY_USE` (32: user, target, supply), the host re-checks the stack,
  the reach and that the target lives. Icons `assets/ui/weapons/supply_<kind>.png` (placeholders). The old H key,
  `Character.supplies` and the HUD supplies line are gone. Gate **`tools/godot/probe_holster_supply.gd`** 10/10
  (`--control`, give reach 0, fails the 2 give checks); `probe_weapon_counter.gd` buys a stack and eats one. Not gated:
  a client giving to someone across two processes.
- **Under the map** (`WorldBounds.underground`, PLAN.md W1): a body more than 1 m under the Terrain3D surface for
  0.5 s is put on the topmost collider within 8 m over the terrain there; swimming over the seabed is never touched.
  Gate `tools/godot/probe_underground.gd` (3 cases, `--control`).
- **`./gradlew test` replaces `jvm/main.jar`** (shadowJar + copyDesktopJars). While Godot bakes are running, test with
  `./gradlew test -x shadowJar -x copyDesktopJars -x packageBootstrapJar`.

## Police and gang dispatch, and where a downed player wakes (PLAN.md W5, 2026-10-06, user-asked)

Built first so peak performance can be measured with enforcement in the ring (user). Gates:
`tools/godot/probe_enforcement.gd [-- --world=island] [-- --control]` (PASS both worlds, control PASS) and
`tools/godot/probe_recovery.gd [-- --world=island]` 23/23; unit tests `DispatchRulesTest`, `RecoveryRulesTest`.
- **`game.EnforcementDispatch`** (a GameManager child, authority only) turns standing into units. Police from the stars
  (`crimes.json` `dispatch`: foot units and patrol cars per star, spawn rings, `shoot_at` 1), gangs at `chase_at` or
  more (`gangs.json` `hunters`). Rules engine-free in `game.DispatchRules`.
  * **Foot officers** appear out of view 45-75 m away, on a footway (island) with a clear line to the player, else
    any out-of-view spot (indoors: the navmesh then). They are `AICharacter.lodPinnedActive` (the PASSIVE tier held
    them on a heading and walked them away, 79 -> 165 m).
  * **Police HUNT the player down; there is no arrest by proximity** (user, 2026-10-07: the walk-up arrest was
    unreadable). `shoot_at` is 1, so from one star police are hostile; a wanted player who goes DOWN wakes 逮捕
    ARRESTED (`RecoveryRules`), which is how an arrest happens now. `ArrestState` survives as the APPROACH state
    (straight when `pursuitDirect`, else the navmesh, plus the breach `pursuitVia` and the guards' stand mode).
  * **Hostile** (from `shoot_at`, or lethal): the police faction is hostile (`WantedSystem.applyHostility`); units APPROACH with
    ArrestState and hand over to the combat FSM inside 25 m (back out past 35). The FSM's own ChaseState stood still
    50-70 m out on the island. Each player's units share an `AISquad`; `assignTarget` is the radio.
  * **Patrol cars** (POC1/MPC1 + partner): `ZoneManager.spawnServiceCar` (never on expressway/ramp/rail lanes),
    `VehicleAIController.setPlan` = `RoadGraph.routeFromLane` from the car's OWN lane (a position snap picked the
    other carriageway: cars drove away). A car whose road route is > 2.5x the straight line is discarded at spawn.
    `racing` set. Within 35 m (or stuck/finished) it `holdStop`s, the crew gets out and joins the foot units.
    Measured: arrives ~16 s after spawn.
  * Stuck (no 2 m gain in 8 s) -> walks off, replaced. Stood down units walk AWAY (ArrestState `pursuitAway`) and are
    freed out of view; an arrived car stays parked until out of view. Police in reach stop the heat draining
    (`WantedSystem.seen`).
- **Enforcement balancing** (user: "reduce crowd when enforcement occurs"): the dispatch reports its load and
  `ZoneManager.effectiveTrafficBudget` = budget - 2/car - 1 per 2 bodies (floor `trafficFloor` 6); walker and fighter
  budgets likewise. Ambient cars over it are SHED one a tick, farthest, out of view, past 60 m.
  `enforcementBalancing` off is the control (`probe_walk_perf --no-balance`).
- **Playtest batch, 2026-10-08** (PLAN.md 1i): police and gangs both top out at FIVE stars (`WantedRules.MAX_STARS`;
  special forces + armour at 5; every `*_by_stars` table has 6 rows). A body row may carry `extra_weapons`
  (special forces: MEW1, used by the close-quarters fallback; `AICharacter.selectBestWeapon` now takes a ranged weapon
  with ammo first). Black is special forces only; gang_a wears its magenta. **Approach slots**
  (`EnforcementDispatch.approachSlots`): each unit closes on its own point 12 m round the player (1.6 m for melee) on
  the side it came from, fanned 0.45 rad per unit, and foot units spawn >= 6 m apart (`probe_police_spread.gd`).
  **A body that dies seated is unseated before it is freed** (`Vehicle.releaseOccupant`, from `RespawnSystem.respawn`
  and `GameManager.despawnReplicatedCharacter`): the car had kept the dead player's PlayerController and camera and the
  HUD its vehicle situation. Gate `tools/godot/probe_die_seated.gd [-- --seat=passenger] [--control]`.
- **Where a downed player wakes** (`game.RecoveryRules`, user 2026-10-06): any gang standing -> **拉致 ABDUCTED**;
  else police stars -> **逮捕 ARRESTED** (jail, a death included); else **入院 HOSPITALIZED**. Bills from cash, never
  below 0, carried to the new body: hospital `fees.hospital` (¥5,000); arrested (hospital + `police_per_star`) x
  stars (¥15,000/star); abduction: a ransom `ransom_per_star` x that gang's stars (¥100,000/star, the highest).
  Abducted: woken at the nearest place of that gang (the places record's new `gang` field, from the civic plots),
  `gangs.json` `abduction.guards` guards cover them (ArrestState `pursuitStand`; the gang is held NON-hostile while
  the captive stays), prompt "拉致 ... [E] pay or run". Pay (`GangSystem.payRansom`, or a donation at that gang's
  counter) clears the standing and the guards stand down; past `escape_start` (15 m) they are escaping (gang hostile,
  + the `escape` heat), past `escape_free` (90 m) free. The card shows the bill. `make_jp_font.py` adds 拉致身代金¥ and
  the gang names. Not done: a client paying a ransom (the key is read on the authority only); no interior "captive"
  marker yet (they wake at the place's door, guards round them).
- Peak load for perf: `probe_walk_perf.gd --wanted=N --gang=N [--no-balance]`.

## Gang hangouts, and why gang escalation was unreachable in play (PLAN.md 0.1 / H1, 2026-10-09)

User: "the gang / all weapons / helicopter altitude seem not working". `tools/godot/probe_escalation_play.gd`
(World.tscn WITH the crowd and traffic, stars set ONCE, logs units / escalation / weapons / heli height every 5 s)
showed the ladder works on the island once stars exist: tanks, rammers, snipers, both helicopters, gang hunters, every
weapon tier. Two real gaps:
- **Nothing to provoke.** No code spawned an ambient gang member, so gang standing could only rise at a gray-area
  counter or in a mission. `game.GangHangouts` (built in code by GameManager, authority only; data `gangs.json`
  `hangout`) stands `count` (4) members in the gang's uniform in front of every place the places record marks with a
  `gang` (9 places), spawned within `near` 70 m of a player, taken away past `far` 110 m; a hangout whose members all
  went down stays empty until every player has left. Bodies come from `EnforcementDispatch.spawnHangoutBody` (the
  dispatch's body/outfit/weapon rules, not LOD-pinned), patrol 6 m round their spot.
- **Player <-> gang was inherently HOSTILE** (no table row; two different factions), so an ambient member would have
  opened fire on sight. `DefaultFactions.tres` now ships player<->gang_a/gang_b NEUTRAL: the first hit on a member is
  `hit_member` = one star = `attack_at`, and GangSystem's flips turn the gang hostile. The konbini mission relied on
  the inherent hostility, so it carries its own table (`M01_Konbini_Factions.tres`, player<->gang_a HOSTILE).
- **The helicopter checked clearance only at its orbit point**, and flew there in a straight line 6 m over roofs. It
  now takes the highest WORLD surface under the orbit point, under itself and 2 s ahead (`AHEAD_SECONDS`), and climbs
  first (half horizontal speed) while lower than that + `orbitClearance`. Lowest AI clearance in the play probe 11.6 m.
Gate **`tools/godot/probe_gang_hangout.gd`** 6/6 (`--control` fails 3); probe_konbini_mission kill/spare,
probe_faction_presets, probe_shop_clerk, probe_enforcement, probe_recovery, probe_escalation, probe_helicopter PASS.
Not done: a gang-territory overlay on the map (PLAN.md 3.5 H5).

## Enforcement escalation: armour, rammers, snipers, a helicopter, and units that come inside (PLAN.md W6, 2026-10-06)

User: the chase stopped at buildings and every unit carried small arms. All of it is DATA in `crimes.json` `dispatch`
/ `gangs.json` `hunters` (`DispatchRules`, `DispatchRulesTest`): `weapons_by_stars`, `vehicles_by_stars`,
`snipers_by_stars`, `helis_by_stars`, `ram_at`, `gun` (which models carry a main gun, interval, range, damage, radius).
- **Armour**: ARV1 (riot van), LTK1 (light tank), TNK1 (tank), placeholder `armour` shape in
  `make_placeholder_cars.py`, VehicleModels 23-25. LTK1/TNK1 fire an ATL1 rocket from the turret every `gun` interval
  in range (`EnforcementDispatch.fireMainGun`) and never unload their crew.
- **Ramming** from `ram_at` stars: `VehicleAIController.ramTarget` steers at the player's predicted position at full
  throttle (boost past 25 m, reverse and re-try when it overshoots or stalls); the crew bails out on foot only after 8 s
  close.
- **Light bars + siren**: `Vehicle.setEmergency` flashes a `lamp_red` bar material (0.5 s) with a red light and plays
  `Sound.SIREN` (file missing: silent), within 350 m of the camera. Set by the dispatcher on its cars only; not
  replicated yet, and an ambulance / fire engine on a call does not use it yet.
- **Snipers**: placed at range on a clear line with SNR1, they hold and shoot.
- **The helicopter** (`carrier/helicopter/Helicopter`, HLC1, VehicleModels 26; the Airplane scene with this script via
  `build_craft_scenes` `script`): an arcade hover -- lift holds the weight (let go = hold height), Space climbs, Ctrl (crouch, `UserCommand.descend`)
  descends -- capped near the ground at max(1.2 m/s, 0.5 x the skids' clearance), so holding it lands at ~1.3 m/s --
  Shift boosts (it used to descend on Shift too, user 2026-10-07), forward flies,
  steer yaws, kept level, `setCanSleep(false)` while the rotor runs (Jolt sleeps a body whose forces balance). With
  `aiTarget` set and nobody aboard it orbits 38 m up / 55 m out, nose on the target. The dispatcher spawns it in the air
  out of view with a pilot and a sniper; door-gun bursts and aimed shots are hitscan from the door (tracers,
  ImpactManager damage). Parked (MARK_vehicle HLC1) on the hospital and police-station roof pads; `ParkedVehicle` lifts
  an aircraft by how far its collision box reaches below its origin. Gate `tools/godot/probe_helicopter.gd`.
- **Units always follow the player INTO a building** (user: "officers always get in, so behaviour is consistent"), at
  every star level: a player is indoors when a ray up hits a building roof (`building` meta); each unit walks
  STRAIGHT to 2.5 m outside that building's nearest `Door_*` marker and 2.5 m inside it (`AIController.pursuitVia`,
  followed by `ArrestState`), and EVERY door of that building is forced (unlocked, automatic: a breach does not knock).
  `EnforcementDispatch.breaching` is the control.
- **Inside, units steer on a per-type INTERIOR NAVMESH** (`world.InteriorNav`, PLAN.md 1d, user 2026-10-07: "a navmesh
  if performance allows"). Without it (measured, `probe_breach.gd --no-stop`): a player 8 m into a konbini was reached
  by 0 units in 90 s (one stalled 6.8 m away), nobody got into a police station. With it: konbini 4 units (first at
  8 s), clinic 5, hospital 36 m inside 2, police station 30 m inside 3; `--no-interior-nav` (the control) 0.
  * Baked OFFLINE once per enterable TYPE by `tools/godot/bake_building_nav.gd -- --all --write` into
    `world/buildings/nav/<Type>_nav.res` (the `_Shop` variant, door leaves and ticket gates left out; cell 0.175 m,
    agent radius 0.35, a 1 m apron round the footprint): 112 types, 912 KB, 3-60 ms each (the 300 m Central station
    254 ms, 62 KB), a path query 5-60 us. **Re-run it after `build_building_scenes.gd` changes a building.**
  * Attached ON DEMAND: the dispatch calls `InteriorNav.attach(building)` the first time a player it is hunting stands
    inside it (a `NavigationRegion3D` named `InteriorNav`; only an enterable `_Shop` / `_Open` type has a bake).
    Attached to every enterable building as cells streamed, it cost ~1 ms p50 of frame on walk_station /
    drive_downtown in three ordered on/off pairs (`probe_walk_perf --no-interior-nav`), though the navigation server's
    own time rose only ~0.2 ms at p95 (the probe now prints it).
  * Every region joins ONE separate navigation map at the 0.1 m cell (a 1.1 m konbini aisle closes at the street
    map's 0.5 m), so the street map and its road-piece seams are untouched.
  * A unit's NavigationAgent3D is put on that map while it stands under that building's roof OR on its interior mesh
    (a compound's yard has no roof, and routing again from the yard sent units back out through the gate), and back
    on the world map outside; inside, its door waypoints are dropped (walked straight, they stood a unit against a
    wall), and a unit that is moving on the interior mesh is not "stuck" (a corridor does not shorten the straight
    distance). Readout `interior_nav_now` ("units switched,regions attached"); `EnforcementDispatch.interior_nav` off
    is the control.
  * Seen: units die in their own crossfire in a police station corridor. Not addressed.
  * **Stations were navmesh ISLANDS until 2026-10-08** (units never reached a player in one). Two bake defects: the
    footprint apron stood at the building ORIGIN, which for a station is the track bed (7.8 m over an elevated hub's
    street), so it cut every stairwell with a floor in mid-air; and the 0.175 m cell with a 0.35 m radius eroded the
    ticket-gate lanes shut. A station's apron now sits at its street (the lowest walkable floor at the footprint
    edge, from a first bake) and interior nav is cell 0.1 / radius 0.3 (`InteriorNav.CELL` must equal the bake's).
    Central 122 components -> one of 8967 polygons. Gate `tools/godot/check_building_nav.gd` (every station's largest
    component >= 85%; `--all` reports the other types, whose walkable roofs are islands by design).
- `escalation_now` readout: `models;rammers;shells;snipers;helis;heliShots;heliHits;breachRoutes;breachedIn;doorsForced`.
  Gate `tools/godot/probe_escalation.gd` (5 stars every piece; `--control` 2 stars none).
- **Not built yet**: breakable building glass (shopfront panes are merged into the building mesh with a solid wall
  collider; making them breakable needs per-pane nodes from `build_building_scenes.gd`).

## Co-op correctness batch: purchases, respawn, missions, clock, passenger view (2026-10-06)

User-reported gameplay bugs, all two-process. Gate: `tools/net/run_net_debugworld.sh` phase **coop** (a client buys at
a real counter, dies, is respawned; both print the clock) -- 25/25 with walk + tour.
- **A client's purchase reaches its own body**: an owned body never takes items from the inventory manifest, so the
  host sends `MSG_SHOP_GRANT` (33) to the buyer after an accepted `MSG_SHOP_REQUEST`, and the owner runs `WeaponGrant`.
- **Buying no longer robs the store**: `ShopClerkSpot.robbable()` is true only after a clerk STOOD there and
  surrendered or died (a client asks its replicated clerk), and the till row is listed LAST. An aim threat needs a
  drawn weapon (not fists / a supply / holstered), the player not in a menu, held 0.6 s.
- **Co-op respawn**: `RespawnSystem` keeps a job per player on the HOST (despawn, respawn with the same id and owner; an
  arrested remote player goes straight into a streamed cell). A client shows the card and fades in when its body
  arrives. `GameManager.despawnReplicatedCharacter` removes the body from the tree at once, or the same-id respawn is
  skipped as a duplicate.
- **Missions are the host's**: a client's `MissionManager` mirrors (`mirrorStarted/mirrorEnded`) and refuses to start,
  complete or fail one; a `ZoneTrigger` tripped by a client's player is forwarded (`MSG_BEAT_REQUEST` 34) and fired on
  the host by the trigger's own rules. Open: a late joiner is not told about a running mission.
- **The clock**: the host sends its time of day at join and every 15 s (`WORLD_EVENT_TIME_OF_DAY` 14, counted as
  `time_sync_*`, so the pole test's world-event count is unchanged); measured 0.03 game min apart.
- **Cars stop-and-go on a client: ENet's packet throttle** (measured with `-- --car-trace`, DebugHarness: per puppet car
  `[cartrace]` every 5 s -- snapshot arrival gaps, frames past the 0.15 s projection cap, stall/surge frames -- plus
  `[nettrace]` host broadcast gaps, frame hitches, per-batch arrival-vs-send gaps and the host's peer throttle). On the
  island with two peers the host's ENet throttle fell to 0/32 for 27 broadcasts: ENet drops UNRELIABLE packets when a
  peer's RTT jumps (a frame hitch is enough), so whole snapshot batches never left and every car in them froze, then
  snapped. `handlePeerConnected` sets `throttleConfigure(5000, 2, 0)` (never back off). Four runs before vs after: per-car
  gaps >100 ms 243-1129 -> 165, frames past the cap 1211-3451 -> 247, stalled frames 213-904 -> 77; what is left matches
  the headless host's own 150-260 ms hitches (headless loads synchronously). On DebugWorld it was already 0.
- **Passenger view**: a local passenger looks through the carrier's chase camera (third person, free aim while holding
  aim/fire) and aims where it looks (`Vehicle.carrierAimFor`).

## Death is a clip, corpses and drops are cleared, hub stairs have ramps, sheds stop the helicopter (2026-10-07, user-reported)

- **A body that dies standing plays `death_fall_back`** (Quaternius UAL1 `Death01`, retargeted onto shino.blend with
  `retarget_ual.py --only death_fall_back`; the script now finds the deform armature when it is not Godot-chan's).
  `CharacterRagdoll.startDeathClip`: the AnimationTree goes inactive, a one-off `DeathPlayer` AnimationPlayer beside it
  plays the clip from the tree's own library, aim/IK modifiers off, bones off the hitbox layer. The first bullet within
  0.15 s turns MeshRoot to face the shooter, so the backward fall goes AWAY from them. **The ragdoll is kept** for a
  body killed in the air, and for a hit with no struck bone (a blast, a car, a train), where the clip hands over
  (`clipToRagdoll`). `Character.deathAnimation` off = always ragdoll. The ragdoll's per-bone impulse is capped at 6 N·s
  (a PhysicalBone3D is 1 kg: a 150-dmg round was 45 m/s on a hand). **Still open: every ragdoll joint is a PIN joint
  with no limits** (`build_character_visuals.gd`), which is why a ragdoll bends where a body cannot. Gate
  `tools/godot/probe_death_anim.gd` 11/11 (`--control` fails the 3 clip checks).
- **`game.WorldJanitor`** (built in code by GameManager, authority only): a dead non-player body goes after 30 s out of
  view (camera frustum within 90 m), at most 12 (oldest out of view first), all after 180 s; story characters, mission
  entities and seated corpses are left alone; corpses go to peers by `announceDespawn`. A DROPPED weapon
  (`WeaponController` stamps meta `dropped_at_ms`; never a scene pickup): 60 s / 24 / 300 s, sent as
  `WORLD_EVENT_PICKUP_CLEARED` (15). A respawn sweeps everything out of view 1.5 s later. Wrecks already had a 15 s timer.
- **Elevated-hub stairs carry ramp hulls** (`build_station_blends.eh_stair_hulls`, one per flight between landings):
  Central, Suburb and Airport had none. `probe_stairs.gd` now puts its floor under the lowest flight (its floor at y 0
  had sliced through an elevated hub's stair and read as "stuck"), and names what is overhead.
- **Platform shed roofs collide** (all three station forms). With no collider a helicopter's door gunner shot through
  them onto the stairs; also `EnforcementDispatch.underCover`: a heli shot never hits a target with WORLD geometry
  within 30 m straight above. `probe_train_fit --stations` PASS with the new roofs.

## A baton at one star, full loads, and a strike while reloading (PLAN.md 1g a/b, 2026-10-07, user-asked)

- **BAT1, the police baton** (警棒; a PR-24 side-handle baton, 0.61 m): the CC0 melee pack's `PoliceBaton`, conformed
  by `import_melee_pack.py -- --only=BAT1` (`MELEE_PACK=<dir>` names the unpacked pack), held as a club by the short
  end, side handle hanging down. A plain `MeleeItem` (BLUNT), chain `attack_swing_mw2` 25 -> `attack_chop_mw2` 40.
  `crimes.json` `weapons_by_stars[1]` = BAT1: at one star police are hostile but melee only; firearms from two.
- **A melee unit keeps the dispatch's straight approach until 3 m** (`MELEE_ENGAGE_IN/OUT` 3/6 against a gun's 25/35):
  handed to the FSM at 25 m, baton officers stood 22 m off for the whole 90 s case.
- **No unlimited ammo** (user decision): units carry each weapon's normal full load, and the base reserves were raised
  to CS's buy-menu loads (PIS1 15+90, PIS2 7+35, REV1 6+36, DUP1 30+120, SMG1 30+120, SHG1 6+32, ASR1/2 30+90,
  SNR1 5+30), which the player gets too. Out of ammo an AI fights with its fists (selectBestWeapon's slot-0 fallback).
- **A reloading AI with its target within 1.8 m strikes instead** (`AICharacter.startMeleeFallback`, 2 s, its melee
  slot else the fists), then goes back to the gun. **A weapon switch now CANCELS a running reload** (CS): before, the
  reload finished on whatever weapon was raised next and refilled ITS magazine for free.
- Gates: `probe_enforcement.gd` (one star: only BAT1, the player downed and ARRESTED in 6 s; four stars: firearms),
  `DispatchRulesTest`, `probe_weapon_scale` / `_sockets` / `probe_melee`. Readouts `unit_weapons_now(side)`,
  `melee_fallbacks_now`.

## Attack tokens, spare ammo in police vehicles, the regroup lull (PLAN.md 1g b2/b3, 2026-10-07)

- **Tokens**: per player and side only `tokens_by_stars` units (crimes.json / gangs.json) attack at once
  (`AICharacter.attackHeld` stops AttackState firing); the nearest get them, held 4 s then 1.5 s rest (rotation;
  `DispatchRules.tokenHolders`). Snipers, guards, seated and approaching units are outside the pool.
- **Dry units**: out of every firearm round and > 4 m from the player, a unit radios out (`EventBus.radioChatter`, a
  HUD status line) and walks to the nearest `item.AmmoSupply` within `supply_reach` 60 m -- a box behind any vehicle
  listed in `item/ammo_supply.json` (POC1, MPC1, ARV1, LTK1, TNK1, HLC1; `stock` restocks each) -- stands
  `restock_seconds` and returns full; with none in reach (or the car taken by a player) it leaves. A PLAYER restocks
  there with interact (client: `MSG_SHOP_REQUEST` item `ammo_supply`).
- **Regroup lull**: once half a player's units on a side ran dry, no new unit is spawned for `regroup_seconds_by_stars`
  and cars already en route stop where they are until it ends; not started while armour or a helicopter is on the
  player. `attack_tokens` / `dry_retreat` (`@Visible`) are the controls. Gate `tools/godot/probe_ammo_supply.gd
  [-- --world=island] [-- --control]` 11/11.

## Uniforms per force, a think budget for AI, and dummy traffic cars (PLAN.md 1g c/d/e, 2026-10-07)

- **Who a unit IS is data** (1g c): `crimes.json dispatch.bodies` (police: Fumiriya x3, Shino, Shibu below 5 stars;
  outfit `special_force` from 5) and `gangs.json gangs.<id>.bodies` (outfit = the gang id), each row
  `{body, outfit, weight, min_stars, max_stars}`, picked by `DispatchRules.pickBody` from its OWN rng stream
  (`EnforcementDispatch.bodyRng`: drawing from the spawn rng moved every later spawn spot -- probe_breach's units
  then started elsewhere and all gave up the konbini's door). `character/outfits.json` says what each outfit puts on
  every CLOTH surface: a VRoid cloth material is `<...>_<Part>_<nn>_CLOTH`, so the part (Tops, Bottoms, Onepice,
  Accessory, Shoes; `cloth` = any other) is read off the name, never authored per body. A value is a flat placeholder
  colour or a res:// material an artist made. `character.Outfits` applies it (one material per source x outfit,
  cached; cleared in GameManager._exitTree); the pure half is `OutfitTable` (DispatchRulesTest).
  **Final art = dedicated uniform bodies** on the skeleton contract with merged materials (a perf win at ~12 units)
  and a real silhouette; one `body` value per row, no code. Readout `EnforcementDispatch.dressed_now`.
- **AI think budget** (1g d): `AIController.gatherInput` runs the FSM every `THINK_NEAR` (2nd) tick within
  `THINK_NEAR_DIST` (30 m, from `AICharacter.lastPlayerDistance`, refreshed with the LOD every 2 s) and every
  `THINK_FAR` (4th) beyond, staggered by instance id. A skipped tick repeats the last decision's movement, stance,
  combat and aim with every press (fire, reload, jump, weapon switch, drop) released; the next decision gets the
  whole elapsed time, so FSM timers run at the same speed. `AIController.thinkBudget` (static; env `OW_NO_THINK=1` or
  `EnforcementDispatch.set_think_budget_now(false)`) is the control. Bench `tools/godot/bench_ai_think.gd`
  (DebugWorld, 6 stars, alternated): physics 7.23 vs 9.15 ms/tick (-1.9 ms, -21%), decisions -60%.
- **ChaseState, two fixes the budget work surfaced:** an agent whose next point is under 0.5 m away (off a navmesh it
  hands back the body's own position) is not followed -- the unit steers at the goal (two baton officers stood 3.9 m
  off a still player for 90 s); and with the target in sight inside `CLOSE_DIRECT` 8 m AND a clear WORLD line at knee
  and chest height (`walkableLine`), it walks straight at it -- the nav path ends at the nearest navmesh point, which
  for a target on a slab is metres off (baton officers circled at 3.5 m with a 1.9 m reach). Sight alone is not a
  way: through a konbini's glazing it walked officers into the wall. A FINISHED agent still leads (treating it as
  "no guidance" broke the interior-navmesh breach).
- **Dummy traffic cars** (1g e / 2d, GTA's dummy): `ZoneManager.updateDummyTier` (each traffic tick) puts a traffic
  car beyond `dummyOutDist` (90 m) of every player ON RAILS (`Vehicle.setDummy`: frozen KINEMATIC, no locomotion or
  `_integrateForces`, the seated driver's AnimationTree paused) and makes it real inside `dummyInDist` (70 m). On
  rails `VehicleAIController.dummyInput` advances its lane progress at a speed under the same rules as a real car
  (lane limit, corner governor, `signalSpeedLimit`'s red / closed / 一時停止 踏切) and `DUMMY_GAP` 9 m behind the car
  ahead on its lane, and poses the body on its wheels along the lane. Promotion hands the speed back as a velocity; a
  dummy that loses health is promoted at once. Cars on a call (a plan, a ram target), racers and anything with a
  player aboard stay real. `dummyOutDist` 0 is the control. Gate `tools/godot/probe_dummy_cars.gd [-- --world=island]
  [-- --control]` (PASS both worlds); bench `tools/godot/bench_dummy_cars.gd` (downtown, 10 of 18 cars on rails:
  5.55 vs 7.03 ms/tick).

## Breaching units walk round the BLOCK, on a baked walk grid (PLAN.md 1g f, 2026-10-07)

The live breach route went round the building's OWN corners, so a neighbour touching the building stopped it: one
extra draw from the spawn rng moved the officers' spawn spots and probe_breach went from 1 unit inside a konbini to
26 "gave_up" of 28. `island_buildings.py places` (or `write`) now bakes, per enterable (`_Shop`/`_Open`) place in the
places record, `walk` -- the 70 m window round the building as a 0.5 m occupancy grid (every plinth grown by a 0.4 m
body; a compound's own yard and car parks / parks walkable; base64 bits, `tools/building_door_paths.py walk_grid`) --
and `door_paths` (front door -> each other door, or null when no walk reaches it). `world.WalkGrid` (engine-free,
`WalkGridTest`) searches it from wherever the unit stands; `EnforcementDispatch.breachRoute` uses it when the corner
route's legs are not clear (`wayClear`), and never sends anyone to a null door. Record ~600 KB (4 unreachable side/back
doors island-wide). Gate: probe_breach (default and `--stars=3`), and the fragile spawn case passes too.
Re-run `island_buildings.py places` after any building change.

### Captors act on what the captive DOES (user, 2026-10-10)

"Sometimes the gang attacks, or does not, at the spawn point whatever I do, even just standing there": three defects
in `GangSystem`, all in which gangs are hostile to players (`applyFlips`, one owner now):
- **They fired on a captive who stood still.** `hold()` only took effect at the next half-second pass, and the standing
  that got the player abducted is usually an attacking one -- so the guards were born hostile and could open fire
  first. `hold()` applies the flips at once, before `EnforcementDispatch.guard` spawns anybody.
- **They did not answer an escape.** Past `escape_start` the guards' ArrestState is released, but they only shot if
  the STANDING was at `attack_at`; a player abducted on one star walked away. A gang whose captive is `escaping` is
  hostile whatever the standing.
- **They did not answer being shot.** A captive who fires (`WeaponFired`), or hurts / kills a member of the gang
  holding them, is `escaping` from that event on -- not at the next pass.
So: held and standing there = nothing happens, for as long as it lasts; leave the spot or attack = they act.
`probe_recovery.gd` case 5 (a low standing: 4 s standing still changes nothing; one shot makes the gang hostile in the
same frame).
