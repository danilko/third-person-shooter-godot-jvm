# island-world

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Ground is Terrain3D; road-generator was tried and REMOVED (2026-09-06 → 2026-09-13)
- The block owns its ground: the terrain IS the city's surface (2026-09-21, user-reported with a photograph)
- The island's districts are a gradient, and the plan is a picture (2026-09-21)
- The land redo: the island is rebuilt from a committed BASE, in one order (PLAN.md 3.30, 2026-09-21)
- The safe-house start, the weapon counter, the map grid, and three hitches (user, 2026-09-22)
- Night is lit: a moon, street lamps and headlights (user, 2026-09-20)
- The land-planning batch: divided Wangan, paddy grid + crops, coastal dike, districts and an air base (2026-09-26)
- The station moved off the trunk road; ramps are level through the gore; two konbini and a car park (2026-09-25)
- Four access points on C1, billboards, fenced airside + air base, mission buildings placed, running trains (2026-09-29 night)
- The airport behind the bridge: one divided spur, the rail under it, the station against the terminal, the runway south; every hub station has its street (2026-09-29, user-asked)
- Rail order at Central, one divided spur, runways on their aprons, a Ferris wheel (2026-09-29, later; user-asked)
- The rebuild review batch: port entrance, signal controllers, the waterfront re-plan, services coverage (2026-10-03)
- The fish market: a straight quay, a car park at the dike's height, the crest carried across junction pads (PLAN S11 P12, 2026-10-13)

---

## Ground is Terrain3D; road-generator was tried and REMOVED (2026-09-06 → 2026-09-13)

`TERRAIN3D_TRANSITION.md` is the history of record. Ground moved from the Blender bake to in-engine
**Terrain3D** and stays there. Roads moved to **road-generator** for a week and were then replaced by
the Godot-authored Road Kit (option B, above); the addon, its `road_demos/`, `world.RoadNetworkBridge`
and `tools/godot/bake_road_terrain.gd` are **deleted** (user decision, 2026-09-13). `world/World.tscn`
is the real world; `world/DebugWorld.tscn` is a small-scale version of the *entire* world for fast
iteration. Both are gated by `tools/godot/check_world_envelope.gd`.

**DebugWorld's road is a Road Kit network now** — `DebugRoads` (`assets/world_source/pieces/
DebugRoads.roads.json`), cut by its two zones into `Roads_DebugRoads_debug_a` / `_debug_b`, and
debug_a's traffic route is its zone id. It was converted once from the road-generator points
(position, and the authored basis at each junction mouth faced along its chain; interior stations
take the kit's own facing, because road-generator's 5 m default handles made near-polyline corners
that folded the inner lanes back on themselves, 177° measured). Three decisions in that conversion,
each measured: road-generator's fork at `RP_008` (two roads claiming one point, no junction — the
source of 3.2's duplicated lanes and self-successor) is DROPPED, not turned into a Y junction (an
invented one hooked two lanes 170° at its mouths), leaving `spur` a dead end; **Auto Setback was not
pressed** — it grew junction 2 to a ~190 m pad over terrain that was only ever flattened along
road-generator's corridor, while the authored mouths keep it at 15–43 m with 0 gate errors; and every
station is draped 0.10 m onto the sampled Terrain3D ground (they sat up to 1.44 m off it; before draping two
ambient cars spawned at junction-1 mouths fell out of the world within 3 s, after it none did in 240 s). The terrain keeps the
road-generator flattening baked into its height map; the Road Kit's own corridor stamp is B7.

**The island's arterials are a Road Kit network in `World.tscn` now** (2026-09-17). Before this,
World.tscn had Terrain3D and NO roads: the 12 arterials existed only in the Blender `Island_base.blend`
bake.
- **Porting.**
  - `IslandRoads.roads.json` (12 roads, 233 stations, 9 junctions) was read out of `Island_base.blend`
    once, with `point_model.read_network` + `save_network` (what `rka.save_record` does). It was not
    re-seeded, so every setback, fillet and pad lift the seeder solved is kept.
  - The `IslandRoads` network node sits at **Y +0.60**, because `island_to_terrain3d.py` moved sea
    level to Y = 0. The median station-vs-terrain difference is 0.00 m.
  - Station `ground_z` was then re-sampled from Terrain3D (`write_roadkit_ground.gd`).
- **Streaming** (superseded 2026-09-18 by the 504 m grid, below). One always-loaded `ZoneMarker` `IslandZone`
  (`zone_id` "island", box 4608 m, load 6000 / unload 9000, `geometry_world_placed` at the network's transform)
  streamed `Roads_IslandRoads_island`. That piece was built with the matching `IslandRoads.zones.json`, so a
  later dock Build produces the same piece name and needs no rewiring. `NAV_HALF=2016` for the navmesh.
  - `ZoneManager`'s approach log now prints only when the distance moves 10 m, because an island-wide
    zone is always "near".
- **Measured.**
  - Validate: 0 errors, 2 `mouth_angle` warnings. Flow: 209 lanes, 0 broken, 0 misjoined, 1 unreached
    (`nishi_dori_1_R0`). The 13 open ends are arterials that really end.
  - `island_v3_reach.py --record` (new flag): **70.8%**, the same as the plan's network.
  - The roads were stamped into World's Terrain3D. `probe_road_stamp.gd -- World.tscn IslandRoads`:
    no ground proud of any lane or pad, stamping again changes 0 vertices, restore is exact, and 590 of
    602 FILL samples are carried.
  - `probe_road_ground.gd -- World.tscn` (now also places a network's resident piece): 2783 of 2833
    PIER samples have a foot on the terrain.
  - World.tscn boots with 0 errors and the zone loads.
- **Two findings from the port, both closed the same day (next section):** the bay bridges stood over a
  −88 m seabed (columns up to 113 m), and the shrine touge rode piers up to 27 m because its switchback was
  fitted to the Python field's slope.

**The seabed is −24 m, the plateau has a 1:3 east face, and the shrine touge climbs in two phases**
(2026-09-17, user decisions). All three are edits to World's Terrain3D data plus the island record, made by
repo tools so they can be re-run and reviewed.
- **Seabed.** `tools/godot/set_world_depths.gd`'s `TERRAIN_FLOOR` is the seabed now: −24 m, where it was a
  −190 m guard. A dredged harbour depth (Tokyo Bay's inner bay averages ~15 m; berths and channels run
  ~15–24 m), and the Python island's own floor. 3.26 M texels raised, from as deep as −138 m. The shelf above
  the floor is untouched. `shape_terrain.gd`'s `HARBOUR_MAX_DEPTH` is 24 to agree.
- **The first mountain's east face** (`tools/island_widen_first_mountain.py`).
  - The shrine plateau (~281 m, centre plan (−1250, 770)) fell east at ~62% on average, and up to 200% on
    the ridges `shape_terrain.gd` laid over it. It now falls at 1:3 from its own measured edge, easing onto
    the 0.6 m city floor. The toe moved ~400 m east, to x ≈ −130.
  - Only the east sector is touched (−35°…0° full, 25° fade), never the sea, and west of a safety line
    before chuo_dori.
  - Ridges are cut only on the plateau's own face. Cutting the massif's foot (north of east) steepened what
    was left: 2989 new >100% cells.
  - It REFUSES a second run. A soft blend is not idempotent, and the check reads the full-strength cells.
    Two defects surfaced through that guard: the face started above the edge threshold it is measured with,
    and the mask used the smoothed edge instead of the raw one. Either way the edit moved its own reference.
  - I/O: `tools/godot/dump_height_grid.gd` / `apply_height_grid.gd` write a float32 grid into a Terrain3D
    data dir; read-back is within 1 mm.
- **Arterials re-routed onto the new toe** (`tools/island_shrine_touge.py`, same uids so links survive).
  - nishi_dori now leaves rinkai_dori at 71°. A first route ran out at 15°, almost along rinkai, and the kit
    correctly solved that shallow crossing to a **102 m** setback. Every centreline sample, and 22 m either
    side, is on ground ≤ 0.48 m.
  - yamate_dori's and nogyo_michi's west ends lost their short first spans.
  - A chuo_dori station 10 m past the chuo × yamate mouth was dropped: that junction now solves 1.5 m wider
    (`station_crowds_mouth`).
  - `roadkit_cli.py setback` re-solved all 9 junctions. It moves every unlocked mouth (W17), so other
    junctions shifted a few metres; rinkai × nishi went 26.5 → 23.8 m.
- **The touge, two phases, both ≤ 10%** (user: watch the driving in two stages).
  - **Phase 1, `shrine_touge`:** from the nishi/nogyo junction, a 40 m level lead-in, then up the widened
    face to a level stop on the plateau. The stop ARCS (45 m radius) round to face the massif, so phase 2 leaves
    straight. Aimed at the plateau centre instead, the hand-off was a 120° bend over a 10 m span, and its inner
    lane had ground 0.17 m proud of it. 2.98 km, 3 hairpins (18 m radius), z 1 → 276 m.
  - **Phase 2, `shrine_touge_2`:** starts ON phase 1's last station (a joint: two coincident points, a
    SEGMENT link). It runs level north along the plateau to the massif's foot, switchbacks up the massif's
    south face, and ends at a stop by the 793 m summit. 5.28 km, 6 hairpins, z 276 → 752 m. The summit end was
    a dead end; since 3.2d it is a turnaround loop (below).
  - Alignments come from `island_v3_terrain.hill_road` on the dumped heights, smoothed (20 m phase 1, 40 m
    phase 2) so the walk does not chase ridge noise. Phase 2 is confined to a south-face band, with "on
    land" asked of the RAW ground 120 m out: the smoothed field blurred the NW sea cliff into 250 m of land.
  - `hill_road`/`switchback` gained `lookahead` (default 0, existing callers unchanged). A walk in a bounded
    band otherwise turns only once its next step leaves the band, and its hairpin is then itself outside and
    ends the road.
  - Profile = `bench_profile`, then fixed stations, then the DOWNWARD cone, then the upward one. Raise-only
    lifted the level lead-in 12 m off its pad (a 21–27% `pad_grade`).
  - The fixed stop stations are counted BACK FROM THE END. Taken as "any station near the arrival point",
    it caught a switchback leg 76 m below the summit and lifted all of phase 2 ~50 m off its mountain.
  - Phase 1's walk grade steps down from 10% until the whole road fits, level lead-in included (it had
    come out 36.7%).
- **The mountain carries its road** (`island_shrine_touge.sculpt`). The kit puts a road more than 4 m over
  its ground on PIERS and the stamp never fills under one, so the ground is shaped to the touge first:
  - within road + verge (14 m) it is the road less 0.10 m;
  - a fill batter (1:1.5) or cut batter (1:1) runs only as wide as the fill or cut at the road's own
    centreline (it daylights), then blends back over 8 m;
  - the sea is never filled; the nearest segment decides.
  - Two wrong versions came first. An unbounded batter "filled" every slope steeper than itself (+633 m
    over a cliff). A batter capped at a height stood 300%+ walls.
  - Result: raised ≤ 63.5 m, lowered ≤ 89 m (rock-cut benches on the ~120% massif face); both roads 0.07–0.15 m
    above the ground on every centreline sample.
- **Measured on the rebuilt island** (pipeline order matters: restore the stamp → sculpt → setback → sample
  the ground → build → stamp; with a stamp record present, sampling reads the OLD sidecar):
  - validate 0 errors (2 `mouth_angle` WARNs, as before); flow 210 lanes, 0 broken, 0 misjoined, 1 unreached
    (`nishi_dori_1_R0`, as before);
  - reach **70.8% → 80.7%** (the massif is served now);
  - `probe_road_stamp -- World.tscn IslandRoads` 6/7: no ground above any lane or pad (highest 0.069 m UNDER a
    lane), idempotent, exact restore. FILL 360/363: the 3 misses are hama_dori's bridge abutments, where the
    lane stands at ~3.9 m, just under `FILL_MAX` (the island had these before);
  - `probe_road_ground -- World.tscn` PASS: 2408/2408 bridge samples have a column foot on the −24 m seabed,
    and both touge phases are all at grade (1494 + 2650 samples, 0 fill, 0 pier);
  - World.tscn boots with 0 errors.
- **Driving it, first build** (`probe_road_launch.gd -- --world=…World.tscn --lane=shrine_touge_F0|shrine_touge_2_F0
  --speed=11`; the probe gained `--world=` and prints each launch's position): phase 1 had 9 launches and a worst
  lateral of 5.8 m, phase 2 had 4 and ran off the summit dead end, and at 15 m/s the car left the road. Fixed in 3.2d:
- **The touge, driven and fixed (PLAN.md 3.2d, 2026-09-17).** Measured first, along the kit's own resampled
  centreline (plan radius over ±6 m, vertical K), which showed that most launches were not where the plan had
  guessed:
  - **Two "grade breaks" were unrounded PLAN corners**: the level lead-in meets the walk at 110° in one station
    (swept at R 18 m), and the walk top meets the plateau ramp at 100° (R **7.7 m**). `fillet` rounds every corner
    nobody drew with a circular arc (40 m, or what the spans leave; sharpest corner served first; collinear
    vertices merged so a straight run counts as one span).
  - **The hairpins were built at 11–14 m, not 18.** `island_v3_terrain.stations` drops the later of two marks
    closer than 10 m, and an even mark landing just before an arc point dropped every other point of the arc
    (chord 9.3 m). `stations(vertices_first=True)` keeps every vertex (default off, so the seeder and
    `bench_depth` are unchanged). The touge's stations are also 20 m apart now, not 70, so the kit can follow a
    vertical curve.
  - **A hairpin arc is not tangent to its own legs.** The walk picks its next heading at the moment it turns,
    so measured 50° into an arc and 32–36° out of it, and Douglas-Peucker had dropped the arc's start point.
    The start is protected, the arc's two boundary points are filleted like any corner, and a vertex that
    cannot be rounded to 18 m is dropped (walk wobble on ridge noise), except beside a hairpin. Result: every
    non-hairpin corner ≥ 23 m, hairpins 12.7–17 m (the worst had been 7.0).
  - **Vertical curves**: `vertical_curves` is the profile's 80 m moving average over arc length. That IS a
    parabolic vertical curve (K = 8 m/% on a 10% break), and it cannot break the grade limit, because the average's
    slope is the average of the slopes. `P2_LEAD` (45 m) keeps the phase joint level through it.
  - **Summit turnaround**: `summit_loop` adds road `shrine_touge_loop`, a level teardrop joined to the stem
    by a 3-arm junction (the kit refuses a 2-arm pad). Its axis and reach are searched (±60°, 70/90/110 m) for
    the flattest summit: straight on, the loop hung 54 m over a slope; chosen −55° / 70 m, ground within 16.6 m.
    A car drives up, round and back down both phases.
  - **The traffic brain had no corner speed.** `CruiseState` cut throttle by a fraction and never braked, so
    uphill at full throttle it held 13 m/s into 18 m hairpins (9.4 m/s² sideways). `VehicleAIController
    .cornerSpeedLimit` is `min over the bends ahead of sqrt(a·R + 2·b·d)`: R is the XZ circumradius of lane
    points 8 m apart, out to the braking distance, re-planned every 0.1 s. `CruiseState` lifts off across
    the first 1 m/s over that limit and brakes past it. `cornerLateralAccel` 4 m/s² (0 = off), `cornerBrakeDecel`
    4 m/s². It is ON for all traffic. `probe_road_launch.gd --corner-accel=` sets it; `GATE_CASES` pass 0, since
    they exist to reach DebugWorld's parapets at 35 m/s.
  - **The generator's input is rebuilt, not stored**: `tools/island_touge_presculpt.sh` (terrain at a389d61,
    seabed clamp, widening) reproduces the pre-sculpt grid byte for byte. Generator + setback on it reproduces the
    record to 0.06 mm. The terrain was swapped as a DELTA over the restored natural ground
    (`nat + sculpt(new) − sculpt(old)`, 115 151 vertices), so nothing else in the window moved. The arterial
    re-route runs only once (`REROUTED_MARK`).
  - **Measured.** At 11 m/s phase 1 goes from 9 launches to **0** (worst rise 2.48 m/s, lateral 1.1 m). Phase 2
    goes from 4 plus the dead end to **0**, driven up, round the loop and down both phases, 14.6 km. At 15 m/s both
    phases have 0.
    Controls on the new road with the governor off: 3 launches at 11 m/s, and 6 plus 5 off-road at 15 m/s.
    Geometry and governor are both needed.
  - Gates: validate 0 errors (3 `mouth_angle` WARNs, one new at a loop mouth); flow 218 lanes, 0 broken/misjoined,
    1 unreached (as before), open ends 13 → 12; reach 80.8%; `probe_road_stamp -- World.tscn IslandRoads` 6/7
    (only the 3 pre-existing hama_dori FILL samples); `probe_road_ground -- World.tscn` PASS; DebugWorld
    `probe_road_stamp` 7/7, launch `GATE_CASES` 0; `probe_traffic_spawn` 6/6, `probe_road_traffic` roadkit and
    debugworld 0 stuck, `probe_dead_driver`, `probe_road_zones` 12/12; World boots with 0 errors; `./gradlew test`.
  - **Probe trap, fixed**: `probe_road_stamp` now also queries LANE samples on the 1 cm grid, the pads' rule. Two
    samples a few mm off an exact terrain vertex read the far vertex, 0.20 m up the 10% grade, which looked like
    "0.09 m proud"; snapped, they are 0.097/0.100 m UNDER the lane.
- **Stamp clearance is 0.10 m** (`road_kit_stamp.gd CLEARANCE`, was 0.05; user: "the road always 0.1 m above
  ground"). `probe_road_stamp.gd` now asserts ground is never above a lane (tolerance 0, was 0.05) and at most
  0.05 m above a pad vertex (was 0.15). DebugWorld re-stamped: 7/7, highest ground 0.078 m UNDER a lane.
- **City ground was already flat** (measured, so no edit): 73% of land under 40 m is exactly 0.60 m, the
  4–16 m bands are flat terraces, and only 0.013 km² of low land deviates more than 0.15 m from its 5×5
  median, nearly all at mountain toes.

The seam into traffic is unchanged in shape: every lane is a `PathLaneRoute` over a native
`Curve3D`. `PathLaneRoute.sourcePath` (an externally owned `Path3D`) outlived the bridge it was
added for; it costs one branch and nothing uses it today. Rules from the road-generator week that
still hold:

- **The lane registry is not guaranteed complete at spawn time.** Baked `VehicleRoute`s registered in
  `_ready`; road-generator built through `call_deferred` and the bridge published a few frames
  later — measured, a zone LOADED one log line before the bridge published and spawned its whole
  fleet unrouted. `ZoneManager.maintainTraffic`'s cull gained an **`unrouted`** reason beside dead /
  route-finished / fell-out / out-of-range, and the existing top-up respawns the car. Re-routing it
  in place was tried and reverted: that is a SECOND placement path, and the two disagreed — it left
  two cars on one lane nose to tail, the front one stuck in `BrakeState`. Since 0.4 the fleet is
  not spawned at all until a lane matches (`spawnTrafficCar` holds it and logs once), so `unrouted`
  now only covers a road rebuild stranding a car.
- **Ambient spawn placement had three defects, and one caused the other two to look like physics**
  (2026-09-13, PLAN.md 0.4, gate `tools/godot/probe_traffic_spawn.gd`). (1) Lanes were taken in
  NAME order (`_1, _10, _11, _2`), not chain order, so a car could land on a lane with no successor.
  (2) The top-up index was `vehicles.size()`, which repeats — two respawns in a row were set down on
  the same point, and on HEAD 19 of 21 spawns went to one lane. (3) A car spawned at its default
  heading (−Z) whatever way its lane ran; one set across a west-running lane crept 6 m north on full
  steer and stopped for good, 54 m from the player — inside the 60 m `stallReclaimMinDist`, so it
  was never reclaimed, and the respawns stacked on it until the fleet read **0 moving**. That is
  the "car at ~0 m/s" shape recorded as unexplained. **Ordering alone did not fix (1)**: once the
  cursor rotates, a short lane merely waits its turn (9 of 22 cars ran out within 160 m), so
  `LaneReach.orderForSpawn` FILTERS to lanes that reach far enough. Measured after, 240 s on
  DebugWorld with the plain `Lane_` prefix (the `Lane_pR` workaround is gone): 15 cars over 7
  lanes, each driving 393–528 m, nearest car at spawn ≥ 13 m, heading within 6° of the lane,
  longest idle 0.1 s; HEAD fails clearance (7.6 m), heading (164°) and rotation (19/21).

- **A car can be alive, routed, in range and still not drive**, and every reclaim reason missed it:
  dead / route-finished / fell-out / out-of-range are all false for a stuck car, so it was immortal
  and held a slot the top-up would have filled with a working one. Distance never covered it — the
  stall happens near the spawn, i.e. near the player, which is where out-of-range is furthest from
  firing. `stalled` (`ZoneManager.vehicleStallTimeout`, 12 s) is that eye, measured on
  **`routeProgress`, not speed** (`VehicleAIController.stalledFor()`): the speed version missed a car
  oscillating across 6 m of plateau at 0.3-1.0 m/s indefinitely — moving the whole time, advancing
  along its lane not at all. Gated by `stallReclaimMinDist` (60 m) so nothing pops in view. Measured:
  `1 moving` -> `3 cars, 3 moving, 3 routed`, steady, after 3 `unrouted` + 2 `stalled` reclaims.
- **A mission vehicle must never be ambient traffic.** There is no mission-vehicle concept yet, and
  when one lands the hazard is the opposite of the obvious: a mission car in a zone's `lz.vehicles`
  is *already* reclaimable by out-of-range and `stalled`, so the mission breaks silently. It belongs
  outside the disposable list, the way `NamedCharacterConfig` sits beside `SpawnConfig`. "Vehicle
  gone -> mission failed" is the mission system's rule (`MissionManager.failMission` +
  `EventBus.missionFailed`, the pattern `Door` already uses), never `ZoneManager`'s — that would put
  reclaim policy and mission policy in two places.

### Ambient traffic on the island — the zones are DERIVED from the lane entries (2026-09-17, PLAN.md 3.4)

`World.tscn` had exactly one `ZoneMarker` (`IslandZone`, which streams the road piece) and no traffic
at all: cars appeared only through `DebugHarness` F4. What was missing is a set of markers carrying a
`VehicleSpawnConfig` — and **where those go is a fact about the lane graph, not a matter of taste.**
`ZoneManager.placementOn` only ever sets a car down in the first few queue slots of a lane, so every
spawn point in the world is a lane **entry**; on a Road Kit network entries cluster at junctions and
road ends, because that is where lanes begin. So the markers ARE those clusters.

**`tools/island_traffic_zones.py`** derives them from the piece's `.lanekit.json`: 94 spawnable lane
entries → **14 clusters** by single-linkage at 250 m (single linkage, not a greedy "cover the most"
pass, which is order-dependent — a lane reordering in the record would then move markers that nothing
about the road changed). Each cluster becomes a geometry-less `Zone` + `ZoneMarker` whose
`VehicleSpawnConfig.route_name` is the lanes' own `zone_id` (`"island"`), which is
`ZoneManager.spawnLanes`' **zone-id pass** — so a marker offers exactly that network's lanes whose
entry is within its `unload_radius`, with no per-zone route naming to keep in step.

**The radii are measured, not chosen.** `spawnTrafficCar`'s player gate is `unload_radius × 0.9` from
a lane ENTRY, so a player driving mid-arterial sees traffic only if that covers the worst distance
from any point ON a lane to the nearest cluster. The tool measures it (**945 m** over 1852 samples,
on `hama_dori_2`) and **refuses** radii that do not, naming the number that would pass — a quiet
stretch of road is a measurement, not a tuning preference. Shipped: `load 1000`, `unload 1400`
(gate 1260 m), 3 cars per zone; ~2.3 zones loaded at a typical point on the network, 8 gaps in 1852
samples at `load 900` and 0 at 1000.

The generated block is identified by NAME (`Zone_traffic_*`, `VehicleSpawn_traffic`, the
`TrafficZones` node), never by a `;` comment — a comment does not survive the editor re-saving the
scene, and the next run would then duplicate the block instead of replacing it. The tool is
idempotent and takes `--check` for CI.

**Gate: `tools/godot/probe_traffic_spawn.gd -- --world=island`** (the probe gained `--world=`;
`debugworld` is still the default and unchanged). 6/6 over 240 s: 29 cars spawned across 15 lanes,
spawn clearance 10.5 m, worst facing 3°, longest idle 0.1 s, one car drove **2.5 km**. Control —
`World.tscn` without the block — fails 2 (0 cars, 0 lanes).

One rule came out of running it on a big world: **a reclaim past `0.95 × unload_radius` is "left
range" and is exempt from the `MIN_DRIVE_M` check.** The gate exists to catch a car that cannot
drive; on a 1.4 km zone the 0.9 gate legitimately sets a car down with only the last tenth of the
radius ahead of it, so an out-of-range reclaim after 130 m is the design working, not a defect. The
probe reads the reclaim radius off the scene (the widest `unload_radius` among markers that actually
spawn traffic) rather than carrying a per-world constant.

**A TURN PATH'S ZERO-LENGTH LEG MADE FIVE LANES UN-QUERYABLE** (found by that gate). A lead or tail
of 1e-5 m — every corner whose approach leg is the shorter one, so the arc starts at the mouth —
still rounded to `k = 1` in `point_solve.turn_shape`, emitting two samples that distance apart AND a
`break` between them; `point_export.curve_points` then put two **coincident control points** on the
exported `Curve3D`, whose zero-length first baked segment makes `Curve3D.get_closest_offset` return
**NaN**. Nothing in the game asks a lane that question (a car walks its own arc length), which is why
it survived — but every probe that attributes a position to a lane does, and `sample_baked(NaN)`
errors and then measures the wrong lane, silently. Measured on the island: **5 of 218 lanes**, all
turn connectors, first chord 0.0000–0.0001 m. `point_solve.TURN_LEG_MIN` (**0.05 m**) is the floor —
a bound on a LENGTH belongs in metres, never in the parameter it is a fraction of — swept in the
`point_solve.py` self-test across an approach offset so the lead passes *through* zero rather than
being aimed at it, with the old 1e-6 floor as the control. The three lane-scanning probes
(`probe_traffic_spawn`, `probe_road_zones`, `probe_road_traffic`) also **skip** a non-finite offset
rather than guess, because every piece baked before this still carries the duplicates until its next
zoned build.

### The island's roads stream as a 504 m grid (PLAN.md 3.10, 2026-09-18)

Before this the whole island network was ONE zone (`IslandZone`, a 4608 m box) streaming ONE piece. So
every prop type was one island-wide MultiMesh that was never culled or unloaded (2435 drains, 1059 planters,
508 lamps in single draws), and the navmesh needed a world-sized bake at ~2 m cells.
**`tools/island_road_zones.py`** derives the zones instead (the `island_traffic_zones.py` idiom: derived,
idempotent, blocks found by node name, `--check`, both checks in `check_roads.sh`):
- **The grid** is the world square cut 8 x 8 (`island_v3_geom`: 504 m about the origin, the old district
  size). Zone ids are `island_<gx>_<gz>` in GODOT axes (`gx` along +X, `gz` along +Z, so `island_0_0` is the
  north-west cell). A cell becomes a zone only if the cut (`point_zones`, B6, unchanged) hands it something,
  found as a fixed point: a cell that owns nothing is dropped and the cut re-run.
- **The cut is still a RUN cut, so long runs had to be split.** A run goes junction to junction, never
  mid-carriageway, and on the unsplit record the zones reached up to **1.76 km** from their cell centre (the
  touge's phase 2 is one 5 km run). `--split` (an AUTHORED change to the record, review the diff) turns a
  station near each cell boundary into a **joint** with the new
  `point_record_ops.split_at_joint`: the station ends its road, an exact copy starts a new road
  (`<road>__<n>`), and the two are SEGMENT-linked. That is the shape the seeder's corner fillets already
  built, so `wire_joints` hands the lanes over. Rules:
  - **The facing is frozen first.** Both halves take the unsplit chain's facing, MANUAL. A road end takes its
    own last chord as its axis, so on a curve the halves would otherwise cut their sections on different
    planes. The self-test's control (facing left free) moves the lane 1 cm.
  - The joint is the station within one of the boundary with the smallest bend (`--max-bend` 15°), never a
    mouth or a ramp. It is placed only if both pieces stay at least `--min-piece` (300 m) long. That same
    rule makes a second run a no-op.
- **Radii are measured.** `load = max(700, reach + 200)` where `reach` is the farthest station or mouth the
  zone owns from its centre, rounded up to 50 m; `unload = load + 300`. A zone left with a stretch past its
  load radius is refused (`zone_beyond_load`).
- **Measured on the island.**
  - 33 joints → 721 stations in 47 roads, cut into **31 zones**. 27 of them load at ≤ 900 m. The widest
    is `island_0_4` (the touge, 1450 m): its hairpins leave no station a joint may take.
  - Lanes 218 → 318. Connectors are unchanged (124), and every sample of the new lanes lies on an old one
    within 0.1 mm (24 308 samples).
  - Validate is unchanged (0 errors, the same 3 `mouth_angle`). Flow is identical: 0 broken, 0 misjoined,
    the same 12 open ends and 1 unreached lane.
- **Traffic follows a zone-id PREFIX.** `ZoneManager.spawnLanes`' zone-id pass matches `routeName` exactly,
  or, when it ends in `_`, as a prefix (`zoneMatches`). So `route_name = "island_"` is one route over the
  whole network, however it streams. `island_traffic_zones.py` takes every piece lanekit and routes by their
  common prefix. It clusters only lane entries at junctions and road ends: a lane whose only predecessors
  are plain lanes starts at a joint, and counting those scattered 35 markers along the arterials. Coverage is
  still measured over every spawnable lane. 11 traffic zones; the worst lane sample is 933 m from a cluster
  (gate 1260 m).
- **A joint is one road to the terrain stamp too.** The stamp represents each corridor by its NEAREST
  segment. Split into separate corridors, a switchback's other leg started capping the hillside between the
  legs as if it were a second road: re-stamping the split touge changed **6088** vertices.
  `roadkit_cli.py corridors` now joins corridors across every joint (`_join_at_joints`), and that took it
  to 15. Those 15, in one region, are the pre-existing joints now judged as one road; World's terrain was
  re-stamped once for them, and the stamp is idempotent again (0).
- **Navmesh: `NavBaker.clipToContent`** (`build_piece.sh`'s `NAV_FIT=1`). A cut piece sits in the
  NETWORK's frame, wherever its cell is, and its runs can pass the cell edge, so neither the origin box nor
  the cell box fits. The clip is the piece's own mesh AABB + 1 m. Pieces share no geometry, so their
  navmeshes meet only where the asphalt does. Every piece bakes at 0.5 m cells.
- **The dock skips traffic-only markers** (`road_kit_zones.is_traffic_only`: vehicle configs, no geometry,
  no AI). Their 60 m boxes would otherwise be the SMALLEST box around a junction and take its pad.
- **Gate `tools/godot/probe_island_zones.gd`** (World.tscn, the real ZoneManager): the player is set down
  at each of the 31 cell centres in a snake. PASS on all of these:
  - every zone inside its load radius is loaded, and none past its unload radius;
  - every piece sits at the network (Y +0.6);
  - every lane starts where its lanekit says (0.0000 m);
  - a successor dangles only into an unloaded zone;
  - every lane within 150 m of the player is streamed.

  Then a 30 m/s drive along the tour (43 648 frames, headless): p50 1.54 ms, p99 3.05 ms, worst 14.98 ms;
  65 pieces entered, the worst frame in which one finished entering 7.07 ms. `-- --control` (load 150 m)
  fails the coverage check. Also: `probe_traffic_spawn --world=island` 6/6 (24 cars on 11 lanes),
  `probe_road_ground -- World.tscn` 2417/2417 PIER samples with a foot, `RoadGraphTest` / `RoadMapBakeTest`
  on all 31 lanekits (`RoadGraphTest.addIsland`), the road map re-baked, `probe_gps_route --world=island`
  17/17 (a 5.2 km route across the pieces). That probe now picks its goal among lanes the start can REACH:
  with the lanes renamed by the split it had picked the inbound carriageway of the `kitahama_dori` dead end,
  which only the dead end feeds (3.3b's missing turnarounds), and reported "no route".
- **Probe finding, not from this change:** `probe_road_stamp -- World.tscn IslandRoads` reads 329/331
  FILL samples carried, identically on the unsplit record. The misses are `kuko_dori`'s bridge abutment
  (0.99 m over the stamped ground), the class the 3 `hama_dori` misses were before.
- **The Blender half of the Road Kit is deleted** (user: "remove unused old blender plugin"). Removed:
  - `point_ops`, `point_build`, `point_nodes`, `paths`, the addon registration, the four
    `smoketest_point_*` and `legacy_graph/`;
  - `build_island_base.py` (the pre-Terrain3D island bake) and `seed_district_roads.py` (the Blender
    district seeder), their only consumers;
  - `run_smoketests.sh`, and `check_roads.sh`'s Blender section.

  `road_kit_authoring/` is now the pure-python rules and build (its README is the module map). The
  `Island_base` piece files and its Blender check tools are data and history, and were left alone.

---

## The block owns its ground: the terrain IS the city's surface (2026-09-21, user-reported with a photograph)

"The block inside the street is not completely filled between the buildings' lands." It was not, and nothing
could have filled it: **a lot is a rotated rectangle grown greedily per building, and a union of rectangles is
not a partition of a block** — two lots in different frames cannot tile, and `grow_lots` stops a whole side at
its first obstructed cell. Whatever the rectangles failed to claim was not "yard" by decision, it was
LEFTOVER: raw heightmap **0.212 m** below the slab beside it (p5 through p75 of 14 368 samples, the kerb 0.15 +
`LOT_RAISE` 0.06), and painted **SAND**, because `paint_terrain.gd` picks a texture by elevation alone
(`SAND_TOP` 5.0 m) and the city plain is 0.6 m. Measured before: **154 km** of paved edge standing against bare
ground, and **21% of a city block bare**, all of it within 90 m of a footway.

**The industry answer is an ownership rule: the paving is a property of the BLOCK; a lot is a property of a
building drawn on it.** CityEngine, the Houdini city HDAs, Skylines and GTA's hand-built blocks all extract the
street-graph face, give it ONE ground surface and only then subdivide. Here that needs **no new geometry**,
because the ground already exists — Terrain3D — so the block's surface is written INTO the height field and
painted. No mesh, no collider, no draw call.

**`tools/island_ground.py` is the one owner.** It rebuilds the placer's own road mask
(`island_buildings.solve_bands`), then the fill is a **geodesic walk out of the LOTS through land that is not
road**, so it cannot cross a street (roads bound it), never paves countryside a building does not reach, and
needs no region box:

    a component of (land minus road) that holds a lot and is <= BLOCK_MAX (4 ha)  -> filled whole (a 街区)
    anything else (the countryside, a huge block's core)                          -> filled to REACH_OPEN (12 m)

Each fill vertex takes its nearest lot's **footway level** (the slab's top less `LOT_RAISE`), so the private
slab keeps standing the authored 6 cm proud of the ground around it — the 民地/公道 rule, and the reason the
terrain is not raised flush, which would z-fight. It writes three grids on `dump_height_grid.gd`'s own 2 m
vertex grid: `.height.f32`, `.paint.u8` and `.natural.f32` (the restore). `tools/godot/apply_paint_grid.gd` is
new beside `apply_height_grid.gd` and **refuses to paint when the terrain's own heights disagree with the grid
by more than 1 cm** — a control map is addressed by REGION texel and the mask by world metre, and getting that
mapping wrong paints somewhere else entirely with nothing in the log to see.

**Measured, on the paving's own edges** — an edge with a ROAD vertex either side is skipped, because the road
piece's paving is a MESH standing on the terrain, so a step there is under the pavement and cannot be seen (it
was 9.1 of 15.0 km, and the SAME before and after):

| | steps over 10 cm | |
|---|---:|---|
| `industry` alone (the trial district, user's choice) | 26.0 km -> **2.1 km** | 92% gone |
| the whole island | 174.6 km -> **11.7 km** | 93% gone |

637 092 terrain vertices moved, median **+0.152 m** (the kerb), at most +1.50 m (`MAX_STEP`). **The stamp never
rises above the road network**: over all 108 699 lane samples of all 31 road pieces the terrain is at most
5.4 cm BELOW a lane and never above one — `probe_road_stamp`'s own assertion, measured directly in numpy
because that probe takes about an hour on World. `probe_buildings.gd` **1043/1043**.

**Four rules, each a defect first:**
- **The walk is 8-connected.** A corner wedge between a junction pad and a lot touches the lot only
  diagonally, so a 4-connected walk left exactly those wedges bare — the tan triangles at every crossing.
- **The paint bleeds 3 vertices past the fill; the height does not.** A junction pad's road MASK is an
  over-estimate of its paving, so a ring of ground shows between the pad's edge and where a lot may stand.
  Raising it is the pad's business; leaving it the colour of a beach is the report.
- **A SITE is not a road and not a block.** Its own scene carries whatever ground it has, so nothing may raise
  terrain under it — but Tokyo Station's forecourt was the largest single patch of sand in the world. Sites
  are out of the fill and IN the paint.
- **A batter gives back a step, not a bank** (`RAMP_DROP` 0.06 m per vertex, `RAMP_MAX` 5). Where the ground
  behind a lot falls further than the whole ramp can return (measured 2.49 m on one 路地 reserved across
  falling ground), a batter is a mound of fill standing in a field. That edge is left for a 塀 / 擁壁.

**The 路地 was a 17 cm TRENCH and had to be fixed with it** — otherwise its slab would have been buried by its
own block's new ground. A lot's top is `road + KERB_H`; a passage's was the CARRIAGEWAY height, so the alley
shipped 0.170 m below the slabs either side of it (measured over 379 passages) against the 2 cm `ALLEY_DROP`
its own comment claimed. `derive` adds `KERB_H` where the road is kerbed: **1150 of 1184 passages moved up
0.150 m, 34 (roads with no footway) did not, and every building in the record is byte-identical.** The alley
MultiMesh also got the box collision it never had — without it a player stood on the terrain under the slab.

**The urban ground is a GENERATED texture, not a tint** (`tools/make_urban_texture.py`, the
`make_sand_texture.py` precedent; a 5th `Terrain3DTextureAsset` "Urban", **id 4 — the id is what the paint
grid writes, so the list is append-only**). Both shipped sets were tried on screen first and both fail for a
reason worth keeping: Ground037's albedo is strongly yellow-green (mean 155/150/92), so any tint of it reads
as earth; Rock023 is neutral (140/139/137) but its features are BOULDER-scale and stretched over a block it
read as cracked slabs. The generated one is fine grey aggregate, mean **101/102/105**, deliberately weak at
the large scale so it does not grow features at the far end.

**`tools/godot/shot_city.gd`** takes the picture — a camera at a named viewpoint in the real World.tscn after
streaming settles. It **needs a display** (`xvfb-run -a`): a `--headless` run draws with the dummy renderer,
which drops MultiMesh transforms, so the lots and the street furniture would be missing from the very picture
being taken to judge them.

**The 路地 slab is GONE (PLAN.md 3.18(c3a), 2026-09-21).** It existed only because the ground between the
lots was bare heightmap; with the block's ground paved it was a second surface doing the first one's job, in all
92 cells. What stays is the RESERVATION (`field.passage`, i.e. 接道義務, and `passages` in the record), and
`island_ground`'s rasterising of passages into the lot mask is now the ONLY thing paving an alley — load-bearing,
and commented as such. Decided by looking (`reference/alley_slab_2026-09-21_*`): the block's grey ground between
the white lots reads as a way through, so there is no second paint id.

**The facade tones are PLATEAU's wall colours, and the sky light is no longer blue (PLAN.md 3.19(e)+(a),
2026-09-21; user: "with the grey setup everything looks greyish ... I wish for PLATEAU's actual building data
theme").** Two causes, both ours. `retone_downtown_kit.neutralise` takes every facade texture to ZERO chroma
(`T_Trim_Neutral` is exactly 134.6/134.6/134.6) and 3.18(p)'s tones then varied only LIGHTNESS; and the Sky3D sky
light painted every wall blue (a white car read navy at noon).
- **The palette is measured on WALLS** (`blender/tools/measure_plateau_wall_colours.py` -> numbers-only
  `assets/world_source/buildings/plateau_wall_palette.json`): each building's texture sampled on its vertical faces
  through their UVs (the older `measure_plateau_facades.py` averages whole atlases, roof included, so it could only
  say how light), median per building, k-means into 8 in L*a*b*. 1 804 walls: **chroma p50 3.3, p90 7.0** --
  central Tokyo IS low-saturation, but warm greige, beige and cool blue-grey panel, not grey. Each cluster's L* is
  LIFTED +9.1 so the median lands on the whole-facade median (aerial walls are in shade; our renderer shades them
  again). Deterministic (seeded).
- **The tones are those colours, in their measured shares.** `retone_downtown_kit.tone_levels` reads the palette;
  tone 0 (the base material) is the largest cluster; names are derived (`_WhiteWarm`, `_DarkCool`, ...) and a tone
  the new palette drops is DELETED so no cell can reference a stale colour. `facade_tones.json` carries each tone's
  `srgb`, `share` and `lum`. `island_buildings.py` draws with the SHARES (`tone_weights`); a region's 7th field is
  now `"dark"` or None (`DARK_BIAS` leans a working district to the darker colours). `island_buildings.py retone`
  re-assigns from each building's own key with NO re-derive (only `tone` fields change). The tones gate checks
  colour DISTANCE between tints and that each tone is worn by at least half its measured share.
- **Lighting: less blue, NOT neutral grey.** The first diagnosis (sky contribution 0 + a grey ambient) removed
  the blue and read flat; the user rejected it. Shipped in World and DebugWorld: `Sky3D.sky_contribution` 0.35
  (the value its day tween restores; the Environment's own `ambient_light_sky_contribution` matches),
  `ambient_energy` 1.4, `ambient_light_color` (1, 0.95, 0.86) -- the sky still lights, a warm bounce term fills.
  Shaded walls keep a photographic cool cast. Sky3D's night boost takes the same flat colour, so night luma rose
  ~10% (0.163 -> 0.181 at midnight, `shot_night.gd`), which the "night is barely visible" report welcomes.
- **Still blue: the glass towers** (`MI_Glass` + `MI_FakeInterior` reflecting the sky) -- a material item in the
  review doc, not lighting.
- **Found on the way: `probe_night_lights.gd` failed on HEAD** ("a lamp lying on the ground is not lit") and it
  was the PROBE: it read `lit_lamps_now` 20 headless frames after coming back from its 400 m case, which is shorter
  than the pool's 0.25 s re-assign, so `before` was 0. It waits in TIME now: 18/18, control still fails exactly 6.

**The artist's Japan checklist is `assets/world_source/buildings/JAPAN_ART_REVIEW.md`** — every type, block rule,
material, library piece and street prop to re-author, each with a target measured from the PLATEAU extract
(`blender/tools/measure_plateau_blocks.py`, massing: gaps, footprint/height percentiles per class, roofs,
setbacks) and pakutaso search keywords (reference only: its terms forbid redistributing the photos, so none is
ever committed). Two findings in it are code (PLAN.md 3.19): **the whole city renders BLUE because of the sky's
AMBIENT light**, not the materials (facade R100 G136 B171 shipped, R102 G138 B174 with metallic off everywhere,
R100 G102 B102 with a neutral ambient and reflections off); and **buildings never touch** — central Tokyo's median
gap to a neighbour is 0.2 m (59% touching), ours 4.4 m (0% within 1 m), because `ALLEY` keeps 1.5 m free on both
sides of every building.

**Still open, and stated so it is not mistaken for done:** the ~12 km of edge the batter refuses wants a
boundary wall (art); parcels that genuinely partition a block (the CityEngine step, which moves every building
and is its own session); `grow_lots`' per-run growth; and — the trap — **`paint_terrain.gd` knows nothing
about any of this, so re-running it repaints the city as beach.** It must learn the mask or always be run
BEFORE `apply_paint_grid.gd`, and nothing enforces that ordering yet.

## The island's districts are a gradient, and the plan is a picture (2026-09-21)

**`tools/island_region_map.py`** draws the district plan whole — pure Python + PIL, no display, no Godot, so it
regenerates in any session. Everything on it is DERIVED from what the game reads: the land from a Terrain3D
height dump, the roads from the BUILT lanekits (so the streets shown are the streets that exist), the region
boxes, their names and their DRAW ORDER from `island_buildings.REGIONS` — including the first-match-wins rule,
so a box hidden behind an earlier one is drawn hidden, which is what it is — every building coloured by the
region the placement GAVE it, and the landmarks by name. Committed as
`assets/world_source/reference/island_districts_2026-09-21.png`.

**The regions are a gradient from the port to the fields** (user), and the order of the table IS that gradient:
harbour → industry → residential → nightlife/downtown/city → farm and beach. Two are new. **`industry`** is the
band a real port city has between its quays and its flats — the container terminal used to meet the residential
grid across one street — and it is measured, not chosen: x −1000..200, z 600..1040 is 100% land at 0.6 m and
sits exactly between the harbour box's north edge and the housing. **`nightlife`** is a 歓楽街 beside the
station, which is Kabukichō's relationship to Shinjuku: 雑居ビル at a 20 m pitch, no flats. Both draw from the
DARK end of the facade tones, which is what makes a working district read greyer — and that costs nothing,
because a building's tone is already an instance override.

**Three landmarks had been built and never placed.** `TokyoTower`, `TokyoStation` and `AirportTerminal` shipped
as finished scenes with 3.12c and nothing in `World.tscn` instanced any of them. `island_sites.py` sites them
the way it already sites the castle — a measured search, never a typed coordinate: the tower on the flattest
clear patch in downtown, the station along **`ekimae_dori`** (駅前通り, "the street in front of the station", so
the trunk grid's own naming says where it goes and which way it faces), the terminal on the airport island's
flattest clear ground. Two defects surfaced doing it, both of which made every candidate fail:
- **A ground floor written in the GODOT frame rejects the whole city.** `Ground.z` returns the RECORD frame,
  where the city plain measures **0.00 m** — the +0.6 m everything sits at in Godot is the network node's own Y.
  A 0.4 m floor found nothing at any road clearance from 70 m down to 20 m, so the clearance looked like the
  constraint and never was.
- **A street is several ROADS.** `island_road_zones.py --split` cuts a long run at every 504 m zone boundary
  (3.10), so `ekimae_dori` is 13 roads and the one keeping the bare name is **43 m** long. A search for "a
  straight run of it" has to re-join them by name prefix and walk them along the street's own principal axis.

**A LANEKIT POINT IS `[x, HEIGHT, z]` IN GODOT AXES, and reading it as a record `(x, y)` pair is silent.** The
first plan drew every road at `z = -height`, i.e. one line through the middle of the picture — and it did not
look empty, because the BUILDINGS are drawn as dots along their frontages and read as streets. It was handed
over as decision material before the mistake was caught, and it changed the answer to two zoning questions once
fixed. The sidecar's `lanes[].points` are already PLACED in world space (the piece's own frame is applied at
export), so there is no record→Godot flip to do; `lanes[].curve[].p` is the same value. A lane also comes in two
kinds (`through` 992, `connector` 1496) and every carriageway repeats per `lane_index`, so "how much STREET is
here" is `kind == "through" and lane_index == 0` — counting them all triples the length.

**A REGION ONLY DOES ANYTHING WHERE THERE IS STREET FRONTAGE ON FLAT LAND**, because a building is placed along a
road, never inside a box — so that, not area, is the number a zoning decision turns on. Measured per region
(buildable = the street's own 24 m band flat to 0.7 m and above the water line):

| region | street | buildable | buildings |
|---|---:|---:|---:|
| city | 48.8 km | 48.1 km | 996 |
| downtown | 20.5 | 20.3 | 568 |
| residential | 20.5 | 19.9 | 862 |
| industry | 8.0 | 8.0 | 445 |
| residential_north | 7.7 | 7.4 | 391 |
| suburb | 5.3 | 2.5 (46%) | 36 |
| residential_west | 4.6 | 1.5 (33%) | 58 |

So a box drawn over the massif or over a shore with no arterials is not a district — it is a label. That is why
the bay market quarter (0.9 km of street, 0.5 buildable) is recorded as blocked on ROADS rather than zoned, and
why `residential_west` is described as a coastal 集落 rather than a suburb.

**What the plan then showed, measured rather than eyeballed: 44% of the island's land (4.40 km²) is in NO
region**, so nothing is placed there — the massif (1.99) and the north-west cliffs (2.08) correctly, but also
the **airport island (0.67 km², which has no region at all)** and 0.42 km² of east coast; and `suburb` is 51%
sea, `farm` 58%, `harbour` 69%. That is PLAN.md 3.18(s), and the coverage table is its gate.

## The land redo: the island is rebuilt from a committed BASE, in one order (PLAN.md 3.30, 2026-09-21)

3.29's final plan (`reference/island_final_plan_2026-09-21.png`) is built by tools, never by editing the world in
place. **`tools/island_world.sh`** is the one order (`--from/--to/--only <stage>`): `land` -> `layout` -> `bridge` ->
`natural` -> `terrain` -> `roads` -> `sites` -> `buildings` -> `ground`. Each stage re-runs the one before it; nothing
downstream is hand-edited.

- **The terrain has a BASE, and the base is committed.** `assets/world_source/terrain/island_base.f32` (LFS, 2305 x 2305
  at 2 m, Godot axes, `dump_height_grid.gd`'s layout) is the island as imported -- 245ed60's Terrain3D data -- plus the
  -24 m seabed clamp and the first mountain's widen. Verified equal to the previous natural ground to 1 mm on every land
  cell away from the touge. `island_touge_presculpt.sh` named a commit (a389d61) that a history rewrite removed; the
  base does not depend on history. `island_reshape.py base <dump>` rebuilds it from a raw dump.
- **`tools/island_reshape.py`** (`build`, `check`) writes the LAND (`terrain/island_land.f32`): the gulf-head landfill,
  the harbour tip / south trim, the far west/east trims, the east seawall, the airport ending at x 1500, the farm moved
  150 m south, and the mountain (x0.55 / x0.5 above 200 m, a level 435 m summit plateau round a 330 m crest, the west
  shore pulled in). Gates: the plateau stays level where the touge meets it, no land step over 8 m, **every mountain
  coast <= 45 deg between any two land cells** (a Lipschitz clamp over the massif -- a `h <= 1 + d` cap bounds a cell by
  its distance and let the SOURCE's cliffs through cell by cell), snow ~0.29 km2, the crest level. Three rules each
  measured as a defect first: the farm shift is SMOOTH (a rigid block cut a 150 m step into the coastline that the coast
  road could not follow), the massif's convex corners are rounded (an 80 m opening), and a trimmed coast gets either a
  QUAY (seabed at the edge) or the base's own shelving SHORE -- a trim that only set land to seabed left the old
  shallow nearshore ring standing 240 m offshore.
- **The ARTERIAL layer is DATA.** `tools/island_plan.py` is the plan: `deform()` (downtown 125 m west, the north 150 m
  south, the band between downtown and the bay compressed -- smooth versions of the plan picture's own maps), the
  plan's new roads (the coastal ring, the bay roads, the castle approach, the military access), the TRUNK GRID as
  lines, the street regions, C1/JCT/diamond numbers, the bridge line. **`tools/island_network.py`** (ONE-SHOT: it
  wrote `IslandRoads.arterials.roads.json`; the pre-redo input is `...arterials.pre_redo.roads.json`) turns named
  lines into a network by rules: clip to land (short wet gaps are bridged), end-to-end joins, a free end within 130 m
  of a line is extended onto it (a T), every crossing is a junction, junctions nearer than two mouths along a line merge,
  a stub past the last junction is trimmed. The trunk grid stopped being a generator because it CUT arterials by NAME
  and names are not stable once lines are joined.
- **`island_roadgen.Ground` reads the land grid**, not the road sidecar: the sidecar is sampled after a build, so it
  described the PREVIOUS world's ground and a generator laid roads on land that had moved.
- **The coast road and the mountain road** are re-derived on the new land: `island_coast_road.py` finds the ring's
  free ends by position (never by name) and its walker's loops are cut out (`remove_loops`); **`tools/island_touges.py`**
  (derive/add/sculpt) is ONE road, `shrine_touge`: phase 1 from a T on nishi_dori up to the plateau junction, the west
  flank, the summit straight, the east flank to a T on the farm arterial (12.5 km, 25 hairpins, <= 10%, cut/fill
  <= 20 m). **3.2d's phase 1 could not be kept** (v13 hoped to): the new summit dome buries its upper legs up to 130 m.
  Two walks sharing one flank crossed each other 36 m apart in height -- phase 1 leaves the arterial further south and
  the east descent keeps north of y 745.
- **The natural ground is the land + the touge sculpt + the beach shelf** (`terrain/island_natural.f32`, committed: it
  is the restore). The `terrain` stage writes it to every vertex and removes the stamp record, the natural-ground
  sidecar and `urban_paint.marker`, then paints by elevation; **`paint_terrain.gd` refuses** while that marker exists
  (`apply_paint_grid.gd` writes it), which closes the "re-running it repaints the city as beach" trap.
- **Sites are FROZEN data** (`assets/world_source/buildings/IslandSites.json`, `island_sites.py --resite[=ids]`): an
  ordinary run places the recorded (x, y, yaw) and re-samples only the height, so an access road can no longer move the
  site it was built for. **A generated record refuses hand edits**: `RoadKitNetwork.generated` (World's `IslandRoads`)
  refuses to save a changed record; `IslandRoadsArterials` (hidden) is the editable input (R5).
- **Two layout clean-ups the network needs**, in `island_layout.tidy`: a pad of TWO arms (a street cut a road and was
  dropped) becomes a joint, and a station inside a solved mouth's clear distance is removed. The expressway now runs
  BEFORE the streets, so they route round its interchanges. A joint's two end stations must share a FACING
  (`freeze`), or the outer lane of a 2-lane ramp ends beside the successor's head (`broken`).
- The Rainbow Bridge stands on the plan's crossing (x 1250, the water gap measured on the land grid,
  `island_rainbow_bridge.crossing_plan`); the lower deck is rail (R7), the spur rides the upper deck, and the spur's
  airport end turns west along the island's south side to descend at <= 4% onto an airport road south of it.
- Road-zone minimum load radius is derived from the building cells (`island_road_zones.min_road_load`, 1350 m, R7);
  `WorldBaker` saves one external mesh per kit asset (`<kit>/baked/<stem>.res`, R15).
- **A WALL IS FOR A ROAD NOBODY FRONTS** (user, 2026-09-21: "the wall is only for the coast road where it runs
  against the mountain; farmland, residential, city and the harbour stay open, with a sidewalk, so the buildings on both
  sides can be entered"). The `coast` preset (no footway, walled end to end) had been put on the whole coastal ring,
  and **339 placed buildings fronted `ring_kita`** with a 1 m parapet between every door and the street. The ring is
  now `arterial` (a new preset: 2 + 2, painted median, 4 m kerbed footways, `ped_access` on, so the barrier rule walls
  it only where it stands 2 m off its ground or on piers). The cliff road splits itself at a joint where it leaves a
  built-up region (`island_coast_road.open_built_up`, "built-up" = `island_buildings.REGIONS`, one owner): the built-up
  stretch is its own street `kaigan_machi` (`arterial`, and not prefixed `kaigan_dori`, which `SKIP_ROADS` never
  builds on), the mountain stretch stays `kaigan_dori` (`coast`). Walled at grade after it: only `kaigan_dori`.
- **A corner bollard keeps clear of every lane, and a car knocks it over** (`point_furniture._edge_props`,
  `prop_lane_clear` 1.2 m past the lane's half width, the tree rule; `furniture.json` `bollard.breakable`, 40 kg,
  1.5 m/s, the 3.11 pole mechanism, now also for a BOX prop, which is not a "pole" to the spacing rules so a row
  keeps its 1.8 m pitch). A turn connector may cut the corner (`turn_off_pad`), and a car turning there pinned its
  hull against a solid bollard with its throttle on: every one of 34 traffic cars reclaimed `stalled` in one
  `probe_traffic_spawn --world=island` run stood beside corner bollards, several at the identical spot. 0.3 m left 2
  (cars running 4.5 m wide on a sharp connector); 1.2 m drops 22% of the island's 9668 bollards. After both: 0.
  `ZoneManager`'s stalled-reclaim log line now names the car's lane, progress, state and what its obstacle ray sees
  (`VehicleAIController.describeBlock`), and the probe prints where each reclaimed car stopped. Also:
  `IntersectionZone` hands the grant on when its holder has stood still 2.5 s (a single-holder arbiter deadlocks when
  the holder's own obstacle ray stops it behind a queued car); it was not this bug's cause, and is kept because it is
  a real deadlock shape.
- **The airport road has no dead end** (`island_expressway`): the island ends at x ~815 west of junction B, so its
  turnaround loop could only turn 90 deg off a 2-station stub, the connector into it was a ~125 deg turn in a small
  pad, and traffic ran onto its kerb. A-B is now one-way westbound and turns at B into the bridge-bound spur (a joint),
  so the airport side is a through route. `island_turnarounds` also tries a near-straight loop (+-45 deg, with the
  road shortened up to 3 stations, evaluated without touching the network) before any wider axis.
- **A generated street keeps away from a road running alongside it** (`island_streets.PARALLEL_CLEAR` 35 m over more
  than 40 m): `machi_612` ran 12.5 m off `naka_hondori` for 460 m and died inside that road's own junction
  (`open_end`, the layout's flow assert).
- **THE CITY PLAIN IS NEVER RAISED, SO THE SUMMIT MOVED (v16, 2026-09-22, user decision).** `island_reshape`'s dome
  falls off over 490 m and `mass_mask` runs to x 350, so its skirt stood 18-70 m of hillside on land the base had at
  0.6 m -- the chuo_dori x nishi_dori junction came out on a **42%** slope with its pad lifted 8 m, and no gate saw it
  (arterials are pure DRAPE with no grade limit; `island_grades` only ranks). Now land under `PLAIN_Z` on the city
  side keeps its own height and the massif rises from it at <= 1:1 (`PLAIN_K`, the coasts' 45 deg). That and a 435 m
  plateau cannot both fit where the crest was (365 m from the plain; the massif is ~1.2 km wide), so the crest was
  MOVED, by a search for the centre and turn that clear both the sea and the plain at 1:1: `CREST_C` (-675, -1125),
  -45 deg, 9 m spare. Its west flank covers the shrine plateau's north half, so the level gate (`PLATEAU_C`) and touge
  phase 1's top (`island_touges.WEST_FOOT`) moved to the south half; `island_touges.py derive` was re-run. **When the
  land changes, the arterials INPUT keeps the old drape** (`island_network.py` is one-shot): re-drape the stations
  that moved.
- **THE BLOCK GROUND IS A LAYER THE STAMP KNOWS ABOUT.** `island_ground.py`'s block surface is written after the road
  stamp, and a stamp re-derives every vertex it reaches from the natural ground -- so a dock Stamp after
  `island_world.sh` took the kerb-level fill back down 0.15 m, silently. `apply_paint_grid.gd` now also writes
  `urban_block.layer` (sparse: "UBL1", nx, nz, x0, z0, step, count, then (index i32, height f32)) beside
  `urban_paint.marker`; `road_kit_stamp.stamp_network` refuses while the marker exists (`--force` in
  `stamp_roadkit_terrain.gd`), and `Stamp.stamp(..., layer)` lays the layer over the stamp -- which is how
  `probe_road_stamp` re-stamps idempotently and judges the restore only on vertices the layer does not own. Beside a
  road with NO footway the block ground is capped at the road less the stamp's clearance (`island_ground.CAP_REACH`),
  or Terrain3D's interpolation lifts it 2 cm over the outer lane. The probe also skips a FILL sample over a road more
  than `UNDERPASS` below (a ramp over a street: the stamp caps to the lower road on purpose).
- **The Wangan** (`island_expressway.wangan_east`, `island_plan.WANGAN_*`): two one-way elevated carriageways from a
  PARTIAL JCT on the spur's east leg (Wangan <-> airport only: C1 would need two loops) along the south waterfront
  offshore of the park, over the gulf and the ring's port-corner bend, then west along the port platform's north
  strip, each down to its own T on the ring at x -730 / -810. Keep-left decides
  the JCT: airport -> Wangan leaves spur_in to its own left; Wangan -> airport must pass UNDER both spur carriageways
  to reach spur_out's left. spur_out is cut at a joint before the Wangan's merge because the loop JCT's
  acceleration lane is on spur_out too (one aux slot per run), and both taper spans are held at 110 m (the gate
  wants 108 at taper 0.25). Iterate on it with `island_expressway.py <out> --from <base> --check` (~17 min; `--fast`
  writes only); the base is `island_coast_road.py add` + `island_touges.py add` over the arterials input.

## The safe-house start, the weapon counter, the map grid, and three hitches (user, 2026-09-22)

- **The game starts at the SAFE HOUSE.** `island_buildings.py`'s `PUBLIC_BUILDINGS` rows carry a ROLE:
  `safehouse` (a `ShopHouse` at (87, -3), central city) and `armoury` (the `Konbini` two doors along the same street).
  `write` (`patch_start`) derives from them, so nothing is a typed coordinate:
  * `PlayerSpawn` (root, read by `GameManager.jitteredSpawnPosition` for every joiner and by `WorldBounds` for a
    fall-out) and the `Player`, 1.5 m out from the safe house's front face, facing the street -- no longer the old
    spawn by the bay at (-20, 1180);
  * the starting car (`VehicleRoot`) parked OFF the carriageway, nose to the street, in the nearest lot space beside
    the house (searched along the frontage: on lots, 0.4 m clear of every building). A car in the kerb lane was the
    first try and is wrong: the traffic brain cannot pass a parked car, so the whole lane queues behind it;
  * the camera starts BEHIND the player (`Player._ready` copies the body's yaw into `controlRotation.yaw`, which
    started at 0 = looking -Z, so a spawn facing anywhere else opened on the player's face);
  * the map places "Safehouse" and "Weapon Counter" (tier 2, always drawn), from `ROLE_PLACES`.
  `island_buildings.py anchors` re-applies the anchors to the existing record (no terrain dump); then `write`.
- **The loose weapons at the spawn are gone; a WEAPON COUNTER replaced them.** `item.WeaponPad` (an `Area3D`, glowing
  disc, the weapon's own `Model` turning above it, "FREE" label): stepping on gives that catalog weapon through the
  ordinary pickup path (`requestEquip`, as the console's `give` does); a weapon already carried is REFILLED instead.
  It re-arms only after the character steps OFF plus `cooldownSeconds`. Only the authoritative peer grants (a
  weapon spawned on a client exists there alone) -- the two-process path is NOT measured. `ARMOURY_PADS` puts 12
  (PIS1 PIS2 REV1 DUP1 SMG1 ASR1 ASR2 SHG1 SNR1 ATL1 FRG1 MEW1) in the konbini's clear aisle, in its own frame, under
  `WeaponCounter`. Gate **`tools/godot/probe_weapon_counter.gd`** 9/9 (spawn at the door, standing; the car settled;
  a pad grants once, not twice while stood on, and refills after stepping off).
- **R9 -- cell HLOD** (PLAN.md 3.32/3.34). `island_buildings.py write` records each cell's buildings as boxes
  (`cells/hlod/boxes.json`: placement, the type's footprint + height, the facade tone's sRGB; `HLOD_GLASS` for
  curtain walls); **`tools/godot/build_building_hlod.gd`** (`--check`) turns each cell's into ONE vertex-coloured
  mesh (`cells/hlod/<cell>.res`, `MI_HLOD.tres`; walls in the tone with a dark band per 3 m storey, grey roof;
  written only when its boxes' hash changes). The cell scene carries it as `HLOD` (`visibility_range_begin`
  `HLOD_BEGIN` 450 m of the cell's AABB centre, dithered, no shadow) and every building's `Mesh` override gets
  `visibility_parent = ../../HLOD`: Godot's own HLOD rule, so a building draws exactly while its cell's HLOD is
  hidden for being near. Re-run order: `island_buildings.py write`, then `build_building_hlod.gd`.
  Measured (`probe_walk_perf.gd`, `--no-hlod` is the control): triangles in the far-view cells cut 55-70 %
  (15-12-5 6.0 -> 2.7 M, 14-12-6 3.2 -> 0.9 M), draws -10-25 %, frame time unchanged at the station -- **the
  station quarter is not bound by the far city**: attributed with `--no-peds` / `--no-traffic`, each alone took its
  p50 from 13.3 to 6.9 ms. The light crowd was ~1 100 of ~4 000 draws there, so `PedCrowd.drawDistance` (180 m, set
  once per ped's meshes at creation: no shadows, dithered fade; a light ped is never nearer than 80 m) took the
  station walk p50/p95 13.3/18.3 -> **11.8/16.2 ms** and downtown p50 8.7 -> 7.6. Still over 16.7 at p95 by
  ~0.2 ms: cells 15-12-2/3 (~3.6k draws; traffic + the station landmark).
- **The map's background is the POSTAL GRID; the region underlay is removed** (its boxes overlapped).
  `RoadOverlay.drawPostalGrid` (one owner, both maps): a faint checkerboard of the 192 m cells under the roads, the
  cell lines, and each cell's "x-y" upright in the middle of its VISIBLE part. On the minimap it is clipped to the
  disc (`clipConvex`, Sutherland-Hodgman against the disc polygon) and turns with a heading-up map; on the full map
  it is clipped to the view, with the column/row numbers still on the edges. `showPostalGrid` on both.
- **The 3.27 s freeze on the way to 12-18 was ONE node:** `BreakableProps._ready` added each pole's
  `CollisionShape3D` to a `StaticBody3D` ALREADY IN THE TREE, so the physics body was rebuilt per shape -- quadratic,
  and a piece's bollard batch has hundreds. The body is filled off-tree and entered once. Found with
  **`tools/godot/probe_start_hitch.gd`** (display; no settle, walks the player from `--from` to `--to`, prints
  every frame over `--slow` ms; with `ZM_TRACE=1` the streaming step of that frame is interleaved -- the trace
  prints BEFORE each `addChild`, so the last "enter" line before a SLOW line is the node that took the time).
  Before: 921 ms at start + 3268 ms at 12-18; after: none over 50 ms past the first 0.7 s of loading.
- **The car camera had W3's frozen-frame bug too** (user: "when I drive, the camera flips 180 and shows the
  character's front"). `VehicleCameraController` is top-level, so its world basis froze at the car's rotation at
  `_ready`, and its Yaw node then added the car's WORLD yaw on top: right only for a car built at 0 deg. The parked
  starting car faces the street (180 deg), so the chase camera sat in front; a 90 deg car was a quarter turn off.
  Traffic never showed it because a traffic car is turned AFTER `_ready`. The rig now restates its AUTHORED local
  rotation (Vehicle.tscn's 180 deg flip, cancelled by `Pivot`) as its world rotation every frame. Gate
  **`tools/godot/probe_vehicle_camera_frame.gd`** 4/4 (cars built at 0/90/180/-90 deg, camera behind and looking
  ahead); with the line removed 3 fail (180 deg reads -1.00). `probe_vehicle_views`, `probe_driveby_aim`,
  `probe_component_car` still pass.
- **Zones start loading NEAREST FIRST** (`ZoneManager`: candidates ranked by distance / load radius, then
  `maxLoadsPerTick` of them). They started in MARKER order, so at the start far cells took every slot and the safe
  house's own block had not appeared after 12 s; now it stands at 4 s.
- **No traffic car is born in front of a player** (it was: a top-up set a car 136-163 m ahead of a player doing
  45 m/s, some in their own lane). `world.TrafficSpawnRules` (engine-free, `TrafficSpawnRulesTest`): never within
  `trafficSpawnMinDist` (80 m); never in the corridor a moving player covers in `trafficSpawnLeadSeconds` (6 s) +
  that (40 m wide, widening 0.5 per metre ahead, so side streets entering it count); and `ZoneManager` adds never
  inside this peer's camera frustum nearer than `trafficSpawnViewDist` (160 m). Checked on the car's actual
  placement; 0 on all three = the old gate. Gate **`tools/godot/probe_traffic_ahead.gd`** (`--speed=45`): 0 born
  ahead, 21 still born; `--control` 6 born ahead.

## Night is lit: a moon, street lamps and headlights (user, 2026-09-20)

User-reported: "night time is barely able to see in game". Measured, and the cause was not a setting to tune —
**there was not one `OmniLight3D` or `SpotLight3D` in the whole project**, `MoonLight.light_energy` was 0, and the
lamps and signals placed by `point_furniture` were props with no light. A clear night was lit by sky ambient
alone. Also `TimeOfDay.minutes_per_day` was the Sky3D default **15**, so a whole day passed every 15 real minutes
(GTA V uses 48; it is 48 here now).

- **"How dark is it" has ONE owner: `world.DayNight`** (AutoLoad). It is **measured off the key light, not read
  off a clock**: Sky3D's clock can be driven by a system time, a scripted beat or an editor scrub, and its own
  `sun_altitude` is stored in a frame this code would have to guess at, while the one thing always true is where
  the sun light points. A `DirectionalLight3D` shines along its own −Z, so the elevation is `asin(-forward.y)`,
  and `nightFactor` ramps 0 → 1 between `dayElevation` (+2°) and `nightElevation` (−8°, the end of civil
  twilight) — so dusk fades the lamps up instead of switching them. The sun is found by the group
  **`sun_light`** (both world scenes put Sky3D's `SunLight` in it), else the brightest directional light. With no
  directional light at all — a bare probe stand — `nightFactor` is 0 and every consumer behaves as before.
- **The sun is never the moon** (2026-10-02, user-reported: "only the back light lights up"). A World rebuild
  (660073ba) dropped `SunLight`'s `sun_light` group (and at runtime Sky3D's node is not in the group even in
  DebugWorld). The fallback was "the brightest DirectionalLight3D", and after dusk Sky3D takes the sun's energy to
  0, so the MOON won. It shines down, so it read as noon all night: no headlight or street lamp ever came on, only
  the day-and-night brake / reverse lamps. `DayNight` now takes the group, then the node NAMED `SunLight`, then the
  brightest non-moon. `probe_night_lights.gd` asserts it with the group removed (`forget_sun_now` drops the cache).
  The old rule fails 8 checks there.
- **Three layers, cheapest first** (`StreetLights`, 2026-10-02): (1) GLOW: the shared window / fascia materials
  (`StreetLights.GLOW`: `MI_FakeInterior*`, `MI_FasciaKonbini/Gas`, `MI_ShopBand`) get emission x the night, one change
  per material for the whole city; (2) FAKE POOLS: a box per lamp head (one MultiMesh per streamed lamp batch, a child
  of it) and per shop door in the places record, drawn with `assets/vfx/night/light_pool.gdshader`, which reads the
  depth buffer and ADDS a warm disc onto whatever surface is behind it, no light math; (3) REAL lights, the
  `maxLights` (24) nearest heads. Emission alone lights nothing here (no SDFGI / VoxelGI / lightmaps), which is why (2)
  exists; baked lightmaps do not fit (Terrain3D has none, streamed + regenerated world, day/night). Measured on the
  island streets at night (`probe_city_perf.gd --hour=0 --night-mode=none|real|pools|all --lights=N`): every
  configuration within noise, GPU p50 under 3 ms; the frame is CPU-bound. `shot_night.gd --mode=` pictures each layer.
- **`probe_city_perf.gd`'s street legs follow REAL roads now** (`_road_path`: one street's lane-0 chain from the built
  lanekits, eye 1.7 m over Terrain3D's height). The fixed y 2.4 m had the camera UNDER the raised city plain on
  91-95 % of both street legs, and the fixed coordinates crossed open blocks and the sea; the corrected noon street
  leg is p95 ~17.4 ms, over the 16.7 budget, where the old one read 15.9.
- **A far car keeps its lamp FACES lit**: past `LIGHT_VIEW_DISTANCE` only the light nodes go (a material swap
  costs nothing per frame), so night traffic down the road still reads as lit cars.
- **`world.StreetLights` (AutoLoad) is a POOL that follows the camera.** The island stands **1 962 poles**; they
  are MultiMesh instances precisely so a district costs one draw call, and a light per instance would undo that
  and light half the island. So the nearest standing lamp HEADS within `radius` (75 m) get one of `maxLights`
  (24) shadowless omni lights, re-assigned every 0.25 s. A lamp beyond the pool still reads, because its glass
  (`MI_LampGlass`) is emissive, which costs nothing; what the pool adds is the pool of light on the road.
  **A knocked-down lamp is dark** — `BreakableProps` already knows which poles are lying down (3.11), so the pool
  skips them and there is no second record of what is broken.
  Where the bulb is comes from the PIECE and is MEASURED (`StreetLights.HEAD_OFFSETS`): `StreetLight_JP`'s
  luminaire mesh spans y 10.00–10.15, z −2.69…−2.08, so its bulb is (0, 10.07, −2.39); the twin's two heads are
  (±2.39, 10.07, 0). They are a table in Java rather than in `furniture.json` for one reason: the piece data
  reaches the game through a BAKE, so putting them there would rebuild all 52 road pieces to move a light 10 cm.
- **Headlights are built in code from the config's measured lamp offsets** (`Vehicle.refreshLights`), so every
  carrier gets them and a new car needs no scene edit: two low-beam `SpotLight3D` and two red tail `OmniLight3D`,
  **no shadows** (one shadow map per lamp per frame, on a street holding a dozen cars, to light the car's own
  shadow in its own beam), built on first need and shown only when `DayNight` says it is dark AND the car is
  within `LIGHT_VIEW_DISTANCE` (140 m) of the camera. The offsets are DERIVED by
  `tools/build_vehicle_scenes.py` from the model's measured bounds — the front/rear face, `LAMP_OUT` (0.62) of
  the way out to the flank, `LAMP_UP` (0.42) of the body's height — never hand-placed.
- **The moon is Sky3D's, and the scene line for it is a trap.** `SkyDome._update_moon_light_energy` writes
  `MoonLight.light_energy` every frame from its own `moon_light_energy` × the moon's altitude, so a value set on
  the light node never wins — the same trap `SkyDome.ground_color` already cost us (the horizon band). The moon
  is turned up at its real owner (`SkyDome.moon_light_energy` 0.6) and `TimeOfDay.celestials_calculations` is
  **SIMPLE**, which puts the moon opposite the sun — a full moon every night, instead of wherever the real
  ephemeris happens to put it. That is what makes open ground away from a road readable at all.
- Gate **`tools/godot/probe_night_lights.gd`** (18/18; `-- --control` turns the pool off and clears the shared
  `SPC1Config`'s lamp offsets, and fails exactly 6): noon reads day and midnight night off the sun light
  (elevation +87.0° / −85.5°); beside a lamp 5 heads are lit, the nearest 11.2 m away, its light exactly
  10.07 m above the pole's base; a camera 400 m from every lamp lights none; a car driven into a lamp puts its
  light out with it; a car 4 m from the camera has its headlights on at night and off by day; and the moon casts
  0.598 at midnight. Pictures: `tools/godot/shot_night.gd` (needs a display) saves a frame per hour with each
  one's **mean luminance**, which is the number the complaint is about.
- **Probe trap:** the Player's TPS rig keeps writing the current camera even with the Player's `process_mode`
  DISABLED, so "move the current camera" silently moved nothing and every lamp reading was of somewhere else
  (the camera stayed 150 m from where the probe asked). A probe that needs a viewpoint owns its own `Camera3D`.

## The land-planning batch: divided Wangan, paddy grid + crops, coastal dike, districts and an air base (2026-09-26)

User asks, one session, built by ONE rebuild from `land` so later district work can be a regional re-derive. Each
item below is data or a generator; nothing is hand-edited in the output record.

**The Wangan is ONE divided 2+2 road** (`island_expressway.wangan_east`, `island_plan.WANGAN_T/JOIN_Z/SPLIT_X`): from
ONE T on the west-coast ring, offshore round the south-west corner, along the waterfront to `WANGAN_SPLIT_X`, where
it parts into the two one-way carriageways the spur JCT needs. **The split is a JOINT, not a junction pad**: the
divided road's end station is SEGMENT-linked to both one-way roads, each starting HALF A MEDIAN to its own side. A
one-way station lays its lanes from itself outward with no median, so each carriageway's lanes are exactly where the
divided road's were, and `point_export.wire_joints` hands every lane over with a 0.000 m gap (measured). Two traps:
`wire_joints`' tolerance is 4.5 m, so the WRONG side passes it 1 m off (the flow is clean either way -- measure the
gap); and **a station's facing IS its forward direction**, so the carriageway running against the divided road must
be frozen facing the opposite way, or its lanes land beside the other carriageway's (both `broken`).
`island_layout.joint_gaps` now REPORTS every cross-road hand-over's gap (not asserted: two older joints hand over
3.4 m and 3.0 m sideways, `kaigan_machi`/`ring_kita` and `nishi_machi_1160`/`nishi_cho_495`).

**The farm is Japanese paddy sections (圃区, 100 x 300 m)** round Farm station: `island_plan.STREET_REGIONS`
`farm_w` (x 510 and the station-front road x 1080, planned FIRST), `farm` (rows y 920/1220/1320/1395, the station
road 1320 ending in a T in front of the station), `farm_s`/`farm_n` (x 810, split round the pond, ため池). Three
street-planner rules came with it and apply everywhere:
- **A new line ends on another new line only inside that line's own extent**, which comes from EXISTING roads -- so
  the road the others end on must be its own earlier region (`farm_w`).
- **Every region is planned TWICE** (`island_streets.PASSES`): the second pass sees the first pass's streets as
  roads. Industry went 0 -> 31 streets; names continue their numbering across passes (a reused name overwrote a road).
- **A region may have HOLES** (a sixth element, record boxes): a line running into one is cut there like a site.
  Residential SW's box overlapped industry's and its 110 m grid had taken industry's ground; the hole gives both
  their own grid (splitting the box instead lost the west part's streets).

**The farm's frame is AUTHORED, and a field is only ever on `farm` land** (2026-09-26). Since the ring became the
12 m dike no farm line could end on it (a 240 m ramp) and the dike's 側道 is built only between two at-grade
crossings, none along the farm's shore -- so the whole farm grid was dropped. `tools/island_core_streets.py` (run by
`island_layout` BEFORE `island_streets`) holds the streets the grid planner cannot make: `nodo_waku`, the farm frame
(west road x 510, the 農道 45 m inside the dike, the station-front road x 1080), whose legs the farm rows end on, and
the core's two 裏通り behind C1 (`c1_ura_nishi` / `_higashi`). An end within 15 m of an existing junction mouth
JOINS that junction; otherwise it is a T cut into the road. `island_streets`' second pass skips a line an earlier pass
built (it used to nudge it into a parallel duplicate). `farm_fields` places a crop cell only where
`region_of` says `farm`, and the seaward flood is seeded only from open sea on its window's border (seeded from every
water cell, the farm pond flooded its whole section).

**Paddy fields and crops.** `island_buildings.farm_fields` derives field cells (2 m) in the farm grid: dry land, and
nothing blocked (road, rail, site, sea) within `FIELD_LEVEE` 1.5 m -- the levee. One section in `WHEAT_ONE_IN` (4)
grows wheat, the rest rice, by a hash of its grid position. Fields are blocked for buildings, recorded as 50 m
chunks with a hex bitmask, and written into the streamed building cells (a cell can now exist for fields alone).
`world.CropField` (Java) builds each chunk's MultiMesh of billboard quads (~1 m tall) at load, one `setBuffer` call
per chunk, with a 180 m view distance per chunk -- NOT stored as instance data (tens of MB of text). The crops are
Binbun3D's **Godot Grass** (CC0, stated on its itch page; the pack ships no licence file), vendored in
`assets/vfx/grass/` with `crop_rice.tres` / `crop_wheat.tres`. The ground under a field is painted **Soil**
(`tools/make_soil_texture.py`, Terrain3D texture id 5, append-only) by a second `apply_paint_grid.gd` pass from
`island_ground`'s `.soil.u8`.

**The coastal dike (海岸堤防)**, `island_reshape.coastal_dike`: the city plain stays at 0.6 m (eastern Tokyo stands at
sea level behind exactly this) and a ridge is built along every NATURAL SHELVING SHORE -- open sea (flood-filled from
the map edge, so the farm pond is not a coast) shallower than -3 m beside the land, out of every harbour-type coast
zone. 1:2 seaward face from the land edge up to a +3.5 m crest 4 m wide, 1:1.5 back to the plain; every end tapers;
never within a road's band + 8 m (roads are DRAPED on the land grid, so a dike under one is a bump in it -- there the
road embankment is the wall). The `beach` coast-zone boxes are STALE after the land redo (one lies over open sea) and
are no longer read by it. Six openings (`DIKE_ACCESS`: suburb, city side, residential NE, farm, west residential,
lighthouse), a 10 m gap with 1:8 ramps, at least `DIKE_ACCESS_SPACING` 150 m apart, recorded in
`assets/world_source/island_dike.json` for the stairs / 陸閘 gates / beach car parks a later pass adds.

**District land planning** (user: "the land-planning portion"; building types come later, by region):
- **Military base** on the port platform's south-west third, gate road `kichi_mon_michi` (a dead end off the port road
  `kichi_dori__2`); two finger piers west into deep water; an **air base**: a reclaimed strip x -1650..-440,
  z 1540..1760 at 4.6 m for a 1 200 x 45 m runway + taxiway (`island_reshape.MILITARY_PIERS`), the paving reserved.
- **Logistics road** `butsuryu_michi` (the port's interior lines meet no road at their quay end, so the planner cannot
  make them). `island_site_access` now cuts its own T (`cut_road`) when the station it leaves is not a junction.
- **Lighthouse** on the north-east headland (`todai_michi`) and a **道の駅** on the north coast road
  (`michinoeki_michi`), each an access road + car park + reserved site.
- **`island_plan.RESERVES`** (Godot boxes) keep generated BUILDINGS off ground whose contents come later: the base, the
  airfield, the waterfront park (Ferris wheel, arena), three resort-hotel plots, the lighthouse, the 道の駅.
- **Zoning rows**: `bay_processing` (水産加工), the `light_industry` 準工業 belt north and west of industry, industry
  as fewer bigger plots (pitch 60, half skipped), the suburb as a low-density resort (pitch 30, 45% skipped).
- Not done: the plan's suburb loop road (the suburb and `north_e` still get almost no block streets).

## The station moved off the trunk road; ramps are level through the gore; two konbini and a car park (2026-09-25)

The tier-B road batch and C0 (PLAN.md "Order check before the tier-B rebuild"). Each rule below replaced a defect
that `probe_road_clear` or the layout gates measured.

- **A site's footprint is a RESERVE, and the station's is sized from PLATEAU.** `island_sites.station_site` used to
  check only that `ekimae_dori` was straight and the land flat, so it put Tokyo Station across `naka_hondori` and
  blocked three lanes. It now places a `STATION_L x STATION_RESERVE_D` (320 x 130 m) reserve beside the street. The
  reserve must be clear of every road's PAVED EDGE (`road_index(widths=True)`, each road's own half width from its
  base section), except block streets, which re-route round a site by themselves.
  - Candidates are walked every 5 m along the JOINED street, across junction gaps: the only place it fits, east of
    `naka_hondori`, is exactly where `ekimae_dori` is broken by a cross street.
  - The building scene stands at the reserve's FRONT (`scene_front` in `IslandSites.json`), with the forecourt in
    front of it and the platform band behind.
  - Each site Zone carries `metadata/site_reserve` (godot x, z, yaw, half x, half z), and
    `island_buildings.site_exclusions` prefers it, because a scene standing off its reserve's centre can no longer
    say where the reserve is.
  - Sizes: `tools/plateau2json/measure_stations.py` (prints numbers only; credited in CREDITS.md). Tokyo Station is
    ~430 x 250 m; the ladder of smaller stations is in PLAN.md B4.
- **A street that no nudge takes clear of a site is CUT by it, not dropped** (`island_streets._line_split`, a last
  resort only when every nudge failed on a site). Cutting first would stop the ordinary nudge moving a street off a
  site's face.
- **A ramp is level with its mainline until the paved bands part** (`island_grades.level_gores`, run first in
  `smooth`). From each RAMP mouth, the ramp takes the mainline's own surface height out to where its centreline is
  `half(main) + half(ramp) + 1 m` from the mainline's (a station is inserted there). Beyond that it rejoins its OWN
  profile at the first station reachable at no more than 7 %; every later station is left alone. The held stations
  are smoothing anchors.
  - Measured before: the diamond exit ran 0.25-1.2 m under C1's deck edge, and the Wangan merge 0.86 m under the
    spur.
  - **Re-grading to the ramp road's far end is wrong, and it was tried**: the Wangan is one long road at layout
    time, designed to climb over `kichi_dori`, and a linear regrade took its clearance from 7.1 m to 1.3 m.
- **A pier's "road below" is the band's LOWEST surface there** (`Band.lowest_surface_z`). `surface_z` is the nearest
  spine sample, and a loop's band covers its own pier's point twice (see "A ROAD IS NOT EXEMPT FROM ITSELF").
- **A kerb corner is metres, never a kilometre.** `point_solve.junction_corners` refuses a corner whose arc runs
  past `CORNER_REACH_FACTOR` (1.5) x the farthest mouth cap + 20 m from the pad centre; validate reports it as
  `corner_runaway`. On the old record it caught 6, including a 5-arm pad's three (1.1-1.8 km) and one of 4.1 km.
  That 5-arm pad was split in the arterials INPUT: `nishi_dori` passes through as a joint, and `rinkai_dori` x
  `kichi_dori` is a T.
- **ONE LOOK, TWO MATERIALS, kerb to door** (user, 2026-09-25; both ASPHALT since 2026-10-05, see "Asphalt from kerb
  to door"): PUBLIC = the footway,
  `road_kit/materials/M_ConcreteTile.tres` (`point_kit.DEFAULT_MATERIAL["footway"]`); PRIVATE (民地) = every building's
  lot slab (`island_buildings.LOT_MATERIAL`) and the block ground between them,
  `buildings/materials/M_LotConcrete.tres`. They ship with the SAME values (plain grey cast concrete, 土間コンクリート,
  at the kit's 2.73 m module) except that the private one is ~8% lighter (albedo 1.0/0.98/0.94 vs 0.92/0.90/0.86,
  user 2026-09-25: fresh private concrete beside the public footway); two files so an artist can move either alone.
  Japan has no fixed "private is darker" rule: a public footway is as often asphalt, interlocking block or coloured
  permeable paving as concrete, and a private forecourt is usually brushed concrete, light when new and darkening
  with weather. `M_TileWhite` is deleted. Only the carriageway differs (`M_Asphalt`).
  - The private file lives OUTSIDE `road_kit/materials/` on purpose: that folder is hashed into every road piece's
    digest (`point_digest.builder_salt`), so a lot edit there would rebuild every road. After editing it:
    `island_buildings.py write` (the cells reference the path) and `make_urban_texture.py --from-lot` (repacks the
    Urban layer and prints the tint/uv to set on `terrain_assets.tres`).
  - The fill is FLUSH with the plates: it stands `LOT_FILL_GAP` (2 cm) under the slab's top, where it was 6 cm
    (`LOT_RAISE`). Two centimetres is invisible and unwalkable as a step, and it keeps the slab winning the depth
    test (exactly coplanar would z-fight).
- **THE BLOCK IS THE PRIVATE GROUND; THE LOT SLAB IS GONE, A BUILDING STANDS ON A PLINTH** (user, 2026-09-25: "small
  gaps between building plates, which seem not normal"). A lot slab was a rectangle grown from its own building in its
  own frame, and rectangles in different frames cannot tile a block, so strips of the fill always showed between
  neighbouring slabs -- a gap no edge bevel could close. The block fill (`island_ground.py`) now stands AT the old
  slab's top (footway + `LOT_RAISE`, `LOT_FILL_GAP` 0) and may LOWER ground on a lot by up to `BURY_TOL` (ground
  left there would poke through a shop floor). Each building keeps a PLINTH (`island_buildings.plinth_boxes`): its
  type footprint + `PLINTH_MARGIN` 0.25 m, top `PLINTH_LIFT` 1.5 cm over the fill and under the floor
  (`FLOOR_LIFT` 3 cm), in `M_LotConcrete`, one MultiMesh + box collision per cell (`Plinths`, `PlinthCollision`).
  The lot RECORD stays: it seeds the fill and decides each building's ground height.
- **A STEP IS EASED ON SCREEN, NOT IN COLLISION** (user, 2026-09-25: "a sudden height increase rather than a smooth
  transition"). `MovementController` still steps the capsule in one tick (`stepUpLedge`, the floor snap), and takes
  that tick's height change into an offset on `meshRoot` (the drawn body, and everything on it: the FPS neck mount,
  the held weapon, the hitboxes) and on the TPS rig's follow point, eased back by a critically damped spring stepped
  EXACTLY (`stepSmoothTime` 0.15 s; 0 is the control). A lip is any on-floor tick whose height change the floor's
  slope does not explain; a tick that changed floor normal is all lip (on a lip the normal is the edge's tilted
  contact, and reading it as a slope pushed the body 8.7 cm the wrong way). The kerb MESH is unchanged and its
  collider stays the true kerb. Gate: `probe_kerb_step.gd -- --at=51,-106` case 3, a 0.15 m kerb: capsule 0.151 m in
  one tick, drawn body at most 0.024 m, camera 0.017 m; `--no-smooth` fails exactly those two.
- **Two konbini and a car park that is an addition.** `KonbiniS` (7 x 10 modules, deep: 12.74 x 18.2 m) and
  `KonbiniL` (12 x 12, 21.84 m square) are laid out from `assets/world_source/store/` (the picture and the text are
  support, not a spec).
  - Each has a real back of house (a staff room with toilet, lockers, desk and safe, a rear staff exit; a walk-in
    cooler behind the drink wall), a customer toilet ROOM with its own door off the sales floor, and the counter
    facing into the store.
  - Interior walls need no layout code: `Wall_Partition` / `Wall_PartitionDoor` are library pieces placed as props.
    The doorway's collider is `collide: {boxes}` (two jambs and a header).
  - `Konbini` and `KonbiniLot` are gone from the table. `ParkingLot4/8/14` are part-less composites (2.5 x 5.0 m
    bays, a 6 m aisle), and `island_buildings.PARKING` places a `ParkingLot8` beside every `KonbiniL`.
  - `layout_buildings.check_doors_clear` samples the capsule's full 0.36 m half-width now. At +-0.30 a locker 1 cm
    into a door passed there and failed `probe_buildings`.
  - `shot_buildings.gd --views=plan` renders an orthographic top-down cut under the ceiling: the only way to check a
    floor plan.
- **Every library piece has a state and a source** (`tools/building_kit/library_status.py` -> `kits/library/
  PIECES.md`). An artist marks a finished model in `kits/library/status.json`. `--check` fails on a piece with no
  recorded source.

## Four access points on C1, billboards, fenced airside + air base, mission buildings placed, running trains (2026-09-29 night)

PLAN.md "NEXT (2026-09-29 night)", one `island_world.sh --from land` rebuild.
- **The expressway is rebuilt round FOUR ACCESS POINTS on C1** (`tools/island_plan.py` numbers,
  `tools/island_expressway.py` builds). **Removed:** `shuto_eb_loop`, the old south JCT at x 655, the Wangan-spur Y,
  the spur's 27.5 m hump, and the x-890 joint.
  - **N diamond** (`DIAMOND_X` 335/345/855/865, a tight diamond down to `DIAMOND_J`). Each end has an exit on one
    carriageway and an entrance on the other, 10 m apart.
  - **W JCT**: the Wangan with all 4 movements. The Wangan's leg runs north beside the rail at `W_LEG_X` 370
    (record). Its two C1 ramps are joints; the `w_fwd_off` flyover and the `w_fwd_on` ramp use `make_ramp`.
  - **E JCT**: the airport. The spur is ONE divided road from its joint at `E_JOINT_Y` and runs straight south down
    x 1250 onto the Rainbow Bridge's upper deck. It has 3 movements; spur -> C1 FWD is not built.
  - **The Wangan's west T is on the straight west coast** (`WANGAN_T` (-1161, 860) Godot).
  - **The S diamond was NOT built.** C1's south side is 790 m and already carries both JCTs' ramps.
  - `island_layout` reports every one-way stretch between a split and its joint (measured: 100 m and 87 m).
- **Phase 2 (a Wangan waterfront continuation to a T on the spur) is HELD, not built.** `island_plan.PHASE2_CORRIDOR`
  (record, half width `PHASE2_HALF` 17.5) and `PHASE2_T_BOX` are street sites (`island_streets`) and building
  reserves (`island_buildings.plan_reserves`). The spur keeps no station inside `SPUR_T_CLEAR`.
  `island_layout.phase2_intrusions` asserts it ("phase-2 Wangan ground held").
- **Two kit fixes the new ramps needed**:
  - `road_points._neighbour_map` takes each aux slot's neighbours from the widest station where THAT slot is live.
    Without it, an entrance's acceleration lane had no receiver when the exit and the entrance on opposite
    carriageways sit at different stations.
  - `island_dike.cmd_raise` re-runs `align_ramp` on every AUX pair after lifting a crossing (ramp_edge_residual
    1.14 m).
- **Rooftop billboards**: every `roof_sign` type (PencilBuilding, ShopHouse, Mansion, OfficeMid, OfficeBlock) gets a
  `<Id>_BB` twin with a `Sign_RoofBillboard_{S,L}_{Red,Cyan,Yellow,Green}` library piece on its top roof, at its
  front edge. The twin is made by `layout_buildings.roof_sign_types`, and the prop uses `"roof_front": d`.
  `island_buildings.sign_pick` swaps a slot to its twin by a hash, per region (`SIGN_REGIONS`: downtown 0.33,
  nightlife 0.45, akiba 0.4, the station fronts ~0.3).
- **The airside is fenced** (`tools/building_kit/site_airport_fence.py`): Mil_Fence bays run round the
  `AirportAirside` footprint. The terminal's span is the only opening. `Airport_ServiceGate` (locked, booth
  landside) stands where `kuko_service` (island_site_access) ends. The civil `AirportControlTower` is a part of the
  composite.
- **The air base is compact** (`tools/building_kit/site_military.py`). Base z 1250..1444.4, runway z 1443..1491,
  the land strip trimmed to 1492, one pier. One fence runs round both, open only at the east gate and the pier gap.
- **Fence rule:** a Mil_Fence bay's outrigger leans 0.6 m to its local +Z. So every line stands 0.7 m inside the
  footprint, and its yaw points the outrigger OUT (a run along local Z takes yaw 90/270).
- **Composite size rule** (`layout_buildings.layout_composite`, read by probe_buildings):
  - a composite PROP past the front counts toward `forecourt_m` (the gate booth);
  - a part set into the ground (`"y"` < 0, the CargoShip in ContainerTerminal) counts its own `base_m` (the hull
    under its waterline origin) in the composite's height.
- **Mission buildings are placed**: 16 `mission_*` civic plots (`island_civic_sites.py`) carry the kits/interiors
  buildings. A shop gets `_Shop` (izakaya, maid cafe, department store, fashion, onsen); every other plot gets
  `_Open`, locked (`island_buildings.CIVIC_SCENE`). CargoShip is berthed in ContainerTerminal, and the
  multistorey car park in CentralForecourt is the walkable `ParkingGarage`.
- **Re-site after every layout:** a layout moves streets, and plots lose their road. After this rebuild 6 plots lost
  their road and `jhs_west` stood 2.8 m onto a band; the civic check misses band overlap, and
  `island_buildings.py roads` found it. Fix with `--resite=<ids> --avoid-streets`, then re-run from `terrain`.
  `--from buildings` refuses once the block ground is laid.
- **Three runtime fixes the gates found**:
  - `RoadGraph` charges a lane change onto an aux lane that opens mid-run for the stretch of the old lane driven
    up to where the neighbour starts (`Lane.leadTo`). It had been a free jump to the neighbour's start, which
    undercounted routes (`RoadGraphTest`).
  - `ZoneManager.zoneStillEntering`: a lane whose own piece is still in GEO_ENTER is not a traffic spawn point.
  - `probe_road_clear` turns `TrainSystem` off.
- **E/W JCT flyovers must cross the Wangan leg HIGH**: `island_grades.level_gores` holds a ramp at its mainline's
  height until the two paved bands part. A ramp running close beside its mainline therefore never climbs, and it
  crossed the leg at grade through the median wall. W3's parallel run is 28 m off the leg, and W4 climbs on the
  west side before turning across. Expressway ramps stand on `RKA_PIER_round`.
- **Running trains** (`world.TrainSystem`, AutoLoad; engine-free `world.TrainTimetable`, `TrainTimetableTest` 4):
  - The tracks are the rail lanekits chained by `next`. One EMU1 4-car set per track shuttles stop to stop:
    trapezoid runs at 0.9 m/s², 25 s dwell, 45 s at a terminus, capped by the lane limit and a curve's sqrt(0.8 R).
  - It runs on the system clock like `SignalTiming`, so there is no message; `game_clock` is for probes.
  - Level crossings close from the timetable (`crossingClosed`). Their units come from `<prefix>.crossings.json`,
    which `roadkit_cli gltf` now writes beside the lanekits. The lamps flash while a crossing is closed, and
    `VehicleAIController.signalSpeedLimit` stops a car at a closed crossing (`TrainSystem.stopDistance`).
  - Cars (AnimatableBody3D) exist only within 650 m of the camera.
  - Gate `tools/godot/probe_trains.gd [--world=island] [--control]`.

- **The Wangan's west end is a terminal loop** (NEXT PASS step 2, 2026-10-02, user's choice of three). The second
  review wanted a west-end turnaround joining the two one-way systems BOTH ways (a port-side PA joins only one). The
  mainline now comes down its straight coast line to `island_plan.WG_LOOP_J` (-850, -1128), a signalised 4-arm junction
  on a reclaimed platform at the plain's height (`island_reshape.WANGAN_TERMINAL_FILL`, painted concrete by
  `island_ground.military_paint`, held from buildings by the `wangan_terminal` reserve): east the mainline, north the
  access road `wangan_iriguchi` (潮風口通り) to a T on the dike road, west and south the two ends of
  `shuto_wangan_loop`, a ONE-WAY 2-lane rounded square laid counter-clockwise (a one-way road lays its lanes on its
  left, so its stations are the loop's OUTER edge). WB -> loop -> EB turns a car round. Gone: the west-coast T, its
  R 34 bend, `port_on` and the WG_CUT5 joint (the access road is the port's way on). The strip between the mainline and
  the dike road is only ~55 m, which is why the junction sits on the coast line and the loop on new land.
  `terminal_loop` in `island_expressway.py`.

## The airport behind the bridge: one divided spur, the rail under it, the station against the terminal, the runway south; every hub station has its street (2026-09-29, user-asked)

User: "station land in middle of street ... let the train below the bridge rather than split the bridge into two one-way
roads ... the station at airport combine with the air terminal, or at least direct connection ... the runway on a
different side from the bridge"; "top of C1 should be similar lane count and exit behaviour both ways"; "the rail must
clear the large train"; "use the latest Blender-authored pieces, not the old placeholders".

- **Why the open-air stations stood in the street**: `World.tscn` still had their PRE-SLIDE positions (City West at
  x −125 where the rail plan puts it at −171.4, Residential North 46 m off, ...); the rail plan and the reserve were
  right, and any rebuild's `sites` stage re-places them. Checked on the plan: every ramp foot lands 1.5–11 m short of
  its street.
- **The Rainbow Bridge decks moved 8 m down** (`library_landmarks.RB_ROAD_LOWER/UPPER` 16 / 24; the towers keep 107.3 m):
  the lower deck is the rail at 16 m = the airport island's ground 8 + `ELEVATED_Z`, so the Main line comes off the
  bridge LEVEL straight into the station. The spur's upper deck (24 m) sits 8 m over the rail head: the EMU1 gauge
  (4.25 m over the bed) clears its 0.8 m deck's soffit by ~3 m (probe_rail_track's gauge sweep is the gate).
  `island_rainbow_bridge.DECK_MIN_Z` 14 (both decks), `island_rail_layout.BRIDGE_DECK_Z` 16, `island_expressway.BRIDGE_Z` 24.
- **The spur is ONE divided road across the bridge** (`island_expressway`: `shuto_spur`). The two one-way carriageways
  (needed by the loop JCT's merge and the Wangan's two ramps) run from C1 past the Wangan's junction S (x 1000),
  converge from `SPUR_OFF` 5.5 to half the median (0.5) over the straight to `SPUR_JOINT_X` 1130, and hand over at a
  JOINT (the Wangan split's rule: each one-way station half a median to its own side, one facing, spur_in faced west).
  They keep a hump (`SPUR_HUMP_Z` 27.5) over wangan_e's underpass, which needs 5.5 m. On the island the divided road
  holds 24 m for `PEEL_HOLD` past the bridge end (off the rail), peels WEST along y −1590, descends to 8 m, U-turns
  at x 870 and ends at `FORE_J`, the middle of the west side of `kuko_rotary`, a one-way two-lane clockwise loop
  (`FORE_BOX`) whose east leg's kerb runs beside the station's west entrances and whose south leg's kerb is under the
  terminal's curb canopy. The old airport roads (`airport_dori*`, `AIR_A/B/P`) are gone.
- **The station against the terminal.** Airport (elevated hub) at (1250, −1670) on the bridge axis. The terminal is the Blender-authored `kits/interiors/AirportTerminal.blend` (150 × 50 m, canopy to
  local +34, bridges to −50.6), DERIVED by `island_sites.terminal_site()` from the reserve: past the terminus end, its
  landside (+Z) facing the station 12 m from the station building's end (`TERMINAL_GAP`), its landside door at local
  x −15 on the station's axis → (1235, −1769.3) yaw 180. The track's buffer stop is 3 m past the platform: at 10 m it ran
  into the terminal's collider at the canopy edge (probe_rail_track's EMU1 gauge sweep). **A custom building is
  RE-CENTRED on its piece's bounds**, so the terminal's canopy (+34 in its piece) stands at +42.3 in its scene:
  `island_sites.terminal_reach()` reads it from `kits/interiors/pieces.json` (a typed 34 put the canopy over the
  loop's lanes, probe_road_clear). The old flat-ground search and its 242 × 170 placeholder size
  are gone.
- **The airside is south** (`island_plan` `airport_airfield` (940, 1812, 1480, 1972.5), `AirportAirside` yaw 180): the
  apron against the terminal's airside face, the taxiway, the 540 m runway along the island's south edge, away from the
  bridge. `island_reshape.AIRPORT_SOUTH` extends the airport island 60 m south (to z 2040) at the platform's height,
  its west-end beach terrace eased over 4 cells (an unchanged terrace next to a changed cell reads as an 8.2 m step).
- **`AirportForecourt`** (`tools/building_kit/site_airport_forecourt.py`, derived from the loop and the
  `airport_forecourt` reserve, levelled like Central's): bus stops on the terminal kerb, the taxi rank on the station
  kerb, the inner island planted.
- **Every hub station has its street** (`island_rail_layout.HUB_ACCESS`, one owner): a door stood 25–320 m from any
  at-grade street. Each row is a street built by `island_site_access` (`station_access()`, a declared dead end
  `ekimae_<station>`, `via` corners supported) whose END comes from the station itself (`station_layout.hub_entrance`),
  and the station's car park placed ON it (the reserve's box with `entrance` + `street_at`, as the open-air stations'):
  Harbour off the ring's low stretch under the Wangan; Industry's annex turned WEST (`side`) with a street off
  kojo_waku; Waterpark along its north face; Suburb along its south face off wangan_dori's diagonal; Bay (no room for
  a T between two junctions 67 m apart) keeps its 28 m apron to nishi_hondori, its car park moved onto that street
  (`mode: "street"`). `island_site_access` now joins an existing junction only when its CENTRE is within 15 m of `at`
  (Bay's first try became a skewed 5th arm).
- **The C1 diamond is symmetric** (`island_plan.DIAMOND_X` 245 / 255 / 945 / 955): each end has its exit on one
  carriageway and its entrance on the other 10 m apart (one ramp per station), so both carriageways widen over the same
  stretch; they stood at 220 / 340 / 860 / 980, which put the extra aux lanes on DIFFERENT stretches of each side.
- **No building stands on a road band at any height**: `island_buildings.py roads` (in the `buildings` stage) checks
  every placed footprint against every solved band in plan (shapely), elevated decks included — the user saw tall
  buildings under C1's deck at the higashi_hondori crossing.

## Rail order at Central, one divided spur, runways on their aprons, a Ferris wheel (2026-09-29, later; user-asked)

- **Main and Harbour swapped sides at Central** (`island_rail_layout`, `_R0`): north to south Blue 229 / Harbour 215 /
  Main 201. As Blue / Main / Harbour the Main line (southbound run at x 205, EAST of Harbour's x 185) curved THROUGH
  the Harbour line west of the core, two double tracks 2-8 m apart, a flat crossing on the viaduct. Nested, Main turns
  innermost and the three never cross (14-24 m apart). Central is anchored on the MIDDLE lane (`("Harbour line", 782,
  215)`): `SHARE_M` (22 m) gathers the lines, and a centre on Main at 201 would leave Blue 28 m out. As the SOUTHERN
  lane Main's curve north turns toward the island platform, so it starts 18 m past the platform end (radius `R_MIN`
  160, tangent x 950; at 180 m it began at x 930 and a car straddling the platform end closed the 0.06 m gap,
  `probe_train_fit`).
- **The spur is ONE divided road from the C1 JCT** (`island_expressway.build`): the two one-way carriageways that ran
  11 m apart to x 1130 are gone. At the JCT end it splits at a joint into `wb_out` / `in_wb` (each half a median to
  its own side, one facing, the first span of each ramp `pillar_skip` -- the Wangan split's pattern). The loop's
  merge and both Wangan ramps are aux lanes on it; the Wangan EXIT leaves 10 m east of its entrance
  (`WANGAN_DIVERGE_DX`, one ramp per station) and the joint at x 890 (`shuto_spur_e`) stays, because the loop's and
  the Wangan's acceleration lanes are both eastbound. **`branch_ramp` cannot place a ramp on a DIVIDED road's far
  carriageway**: it starts the mouth on the centreline, so which carriageway it is on is a tie, and it took the
  eastbound slot (`aux_slot_shared`). Build the ramp as its own road with its mouth off the correct side and attach it
  with `make_ramp`, which reads the carriageway from where the mouth is.
- **`kogai_loop`'s east leg meets the ring from the south-east** (the (1215, -705) corner, `island_core_streets`):
  straight north it left the pad 40 deg from `ring_kita__6`, its mouth 46 m out, and the kerb corner between the two
  lay across `ring_kita__6_F1` (`probe_road_clear`).
- **A pier shaft is founded on the lowest ground within 1.5 m in NINE directions** (`point_mesh.FOOT_OFFSETS`, the
  diagonals added): over a vertical quay a corner stopped 2 m over the seabed a diagonal step away
  (`probe_road_ground`, the Wangan's west viaduct).
- **Runways meet their aprons.** The base's runway moved to x -1015..-475, directly south of the apron, its east end in
  line with the east fence (`island_plan.RESERVES` `military_airfield`; the reclaimed strip trimmed to x -1030). The
  civilian `AirportAirside` is one paved surface: the reserve reaches the terminal's airside face (z 1784), aprons
  from there to a taxiway flush against the runway, two airliners nose-in at gates 1 and 3 (adjacent gates are 35 m
  apart, under a 35.8 m span), one on a remote stand, the hangar opening onto the apron. Before, the gate bridges
  ended 8.6 m short of the apron, no airliner stood at a gate and 21 m of open ground separated taxiway and runway.
- **`FerrisWheelPark`** (library piece `Park_FerrisWheel`, `library_civic.py`): a 100 m wheel on a 60 m hub (110.9 m
  to the top), boarding hall, promenade and plaza on the corrected `waterfront_park` reserve (x 765..875, z 690..890,
  the gulf's east shore beside the resort hotels -- Odaiba's Palette Town / Kasai Rinkai precedent), load 2500 m,
  collision = its own mesh, map label "Ferris Wheel Park" (tier 2). The wheel does not turn yet.
- Probes: `ParkedVehicle`'s vehicles join group `parked_vehicle` and `probe_traffic_spawn` skips them (placed, not
  traffic); `probe_road_ground` counts an ELEVATED station's reserve (its site zone's `site_reserve`, placed > 8 m) as
  carrying the deck; `probe_gps_route` uses the waypoint the player HAS (a click on a place blip takes its door).
- **A concurrent session in the same checkout ran `git stash` / `pop`** (reflog `reset: moving to HEAD`), and a file
  read inside that window looks reverted. Check `git reflog` before concluding edits were lost.

## The rebuild review batch: port entrance, signal controllers, the waterfront re-plan, services coverage (2026-10-03)

A re-review of the remaining plan (PLAN.md "REVIEW OF THE REMAINING REBUILD PLAN") before the one rebuild; each item
measured on the generator's network first.
- **Terminal order is already Japanese**: inside an interchange the exit comes before the entrance (the port, every
  diamond); entrance-before-exit only happens between interchanges as a weave (Y4 -> Suburb exit 540 m, Suburb entrance
  -> Y3 exit 460 m). The planned port collector-distributor road was dropped: step 2 left 3 terminals there, not 6.
- **The port's eastbound entrance** (`island_expressway.port_entrance`): a T on the dike road at `PORT_ON_T` (x -440,
  east of Y1), a one-lane ramp merging EB at `PORT_ON_X` -270 (at -230 its gore stood 16 m from the WB port exit's
  first station and the kit read that exit as bending back across the mainline, `ramp_wrong_side`), level
  `PORT_ON_HOLD` past where its band parts, solved to K 9 (`island_grades.RAMP_K_OVERRIDE`: its descent overlaps its
  plan turn, and the exported Hermite read K 4.6 where the 2 m solve read 6.7). The
  dike road `ring_kita__11` was moved 10-16 m north in the arterials INPUT to make the room
  (`tools/island_dike_port_gap.py`, one-shot, applied). C1 -> port has NO direct ramp (the corridor north of the
  Wangan from x -600 to +300 is full of Y1-Y4 and the connector): it uses the west terminal and its access road.
- **`ground_ramp(hold_extra=)`**: `island_grades.level_gores` holds a ramp at its mainline's height until the bands
  part by its own measure and then rejoins the ramp's profile in one HELD chord, so a ramp already descending by then
  carries a fixed break the solver cannot round (port_on K 3.9). Hold the ramp's own profile level longer.
- **Two generator traps step 2 exposed** (both read as Y3 lying on Y4 for 230 m, Y4 at 19 %):
  - Y3's "mainline" polyline concatenates every `shuto_wangan*` road; `shuto_wangan_loop` joining it added a fake
    segment across the bay. Only the mainline's runs belong in it.
  - Ramp geometry taken from the CHORD to a neighbouring mainline station moves whenever the mainline's length shifts
    the 45 m station grid (Y4 moved 12 m). Y4's merge frame now reads `pm.station_axis` (the frozen design tangent).
    Y3 keeps the chord (the axis put its crossing with Y4 where it could not climb at 6 %). Y4 merges at `Y4_ON_X` 80
    (was 110), lower on the Harbour hump, so Y3 clears it at 5.6 %. Suburb exit planned 5.6 m over the dike road
    (`SB_CLEAR`, `island_dike.PLANNED_OVER`), 6.9 %.
- **Spur speed stage**: `shuto_spur__2b`, 142 m posted 60 (`SPEED_STAGE`) before the 40 km/h hairpin.
- **Coordinated signals** (`point_furniture.coordinate`, self-tested): signalised junctions within `COORD_REACH` 100 m
  sharing a road and a cycle run as ONE controller -- `coord` = {root, rel}: the root's hashed offset + a green wave at
  `COORD_SPEED` 12 m/s, the shared road's group aligned. `TrafficSignals` reads it (offset(root) + rel).
- **The waterfront** (items 4-5): the fish market reserve was 99 m deep where the flat land between the dike's slope and
  the shore is 57 m (shore z 762), and the Wangan and both Suburb ramps crossed its east end: it is now (405, 705, 570,
  775), a 165 x 70 m FishMarket with a quay deck, fenders and a PONTOON parallel to the quay (the Wangan's deck stands
  15-25 m off it) with two FIB1 and a WOB1 moored (`keep_origin` so it is not lifted, `plot_origin`). The Ferris park
  moved south of `shuto_sb_on` (760, 798, 870, 958), Park_FerrisWheel 110 x 160, its wheel's circle facing the open sea.
  The three hotels moved out of the suburb loop to the beach front (z 806..868) as `ResortHotelSite` composites (the
  interiors hotel sea-side, forecourt + 14 bays on the loop's leg). The water resort stands inside the loop on its bottom leg
  (WaterResort now 150 x 70: the dike's embankment slope takes the interior's north part), searched BEFORE the
  fire station and clinic (the civic search runs in table order).
- **Ground hubs** (item 8): measured against each road's FOOTWAY, the defect was the platform-END fences (Bay 2.3 m,
  Fish Market 4.0 m into the crossing street's footway): Bay's platform 92 m at y -136, Fish Market at x 464.
- **Services coverage** (item 6): `island_civic_sites.py --coverage` (after the buildings stage): from each district's
  building centroid, police <= 600 m, fire <= 700, konbini <= 600, and for the residential districts bank and
  clinic/hospital <= 800. New plots: koban_port, fire_branch_port, koban_farm, bank_north, bank_rwest. Not done: the
  yacht.
- **The Japanese 一戸建て** (item 11b, `library_civic._house`, `Builder.convex` for real roof slabs): 平入り, a 玄関 bay by
  the parking, 掃き出し窓, a railed ベランダ, low wall + 門柱, a cantilever carport, the 基礎 2 cm proud; B is the
  hipped mirror.
- `island_rail_layout.picture()` had a dead copy of the reserve's car-park code (`front_park` NameError): removed.

### Post offices, postal vans, and streets into the vacant blocks (2026-10-03, user-asked)

- **郵便局, two enterable sizes** (`blender/tools/interior_plans_jp.py` `post_office_small` / `post_office_large`,
  `kits/interiors/PostOffice*.blend`, rows `PostOfficeSmall` / `PostOffice` in `building_types.json`, which replace the
  library massings; placed `_Shop`, i.e. open):
  - the branch is 12 x 10 m on a 15 x 20 m plot, one storey: ATM corner, 記載台, 窓口 counter, back office (区分棚,
    safe), staff WC; a DELIVERY YARD behind with a POV-1 van;
  - the 集配 main office is 36 x 26 m on a 40 x 40 m plot, three storeys: customer hall, 窓口 + ゆうパック counters, the
    delivery depot with two dock shutters onto a van yard (a POT-1, two POV-1).
  - Placement: `post_office_main` in the city; branches `post_office_west/east/rwest/sw/north/north_e` -- one in every
    residential district (`island_civic_sites.COVERAGE_HOME["post"]` 800 m is in `--coverage`).
- **Postal vans**: `POV1` (郵便 軽バン, Every / N-VAN class, 3.395 x 1.475 x 1.90) and `POT1` (2 t box truck, Elf /
  Dyna class, 4.69 x 1.695 x 2.95), placeholder blocks from `make_placeholder_cars.py`; `VehicleModels` indices 20 / 21
  (append-only); one POV1 in twenty civilian traffic cars.
- **Why the blocks were vacant**: a planner line is kept only if it meets TWO roads, and in several blocks the only
  other road did not exist yet when the streets were planned (the dike's side road is made later), lay outside the
  region's box (koba stopped at y -590, its north road is y -413), or the line hit a junction gap / crowded a junction
  (within 55 m). Fixes:
  - authored frames in `island_core_streets.py`: `c1_naka_yoko` / `_e` (y 465 inside C1 across the three trunk roads,
    one crossroads on naka_hondori -- `_tee` now also reuses a junction by its CENTRE) and `koba_waku_w` (a U off
    kichi_dori along y -655 / -783 across the Blue line, x -800, into the west industrial block);
  - planner regions `koba_w` (x -700 from nishi_cho_413 down to the U) and `city_n` (x 360 and 800 between yamate_dori
    and c1_naka_yoko), lines placed clear of existing junctions.
  - Left vacant, measured: the residential_west hill-foot band (the castle site covers it to 10 m off nishi_dori);
    north_mid (the frozen park/clinic plots fill it); the suburb inside its loop (the legs are dike ramps); industry's
    big plots (by design).
  - Scan tool used: a 4 m vacancy grid (land, flat, not road, not a lot/site/reserve) clustered by region -- the kind
    of measurement to repeat after any street change.

### The suburb moves behind the dike; streets into the deep pockets (2026-10-03, user-asked)

User: "should the suburb street / resort be behind the dike, with only certain entertainment on the beach?" -- then
"homes behind the dike, push the dike further south so there is room, still leave enough beach". The Japanese norm is
homes behind the 防潮堤 and only beach leisure outside it; the suburb (kogai_loop, the resort hotels, the water resort)
had stood OUTSIDE the coastal ring on a loop whose legs were ramps onto the crest.
- **The land reaches south** (`island_reshape.SUBURB_FILL`, Godot x 880..1230, z 760..1170, at the city floor). Its
  bank and dry beach are LAID OUTRIGHT after `coastal_works` (plain 5.6 m, 1:3 bank to 3.0 m, then 1:25 through the
  water line, ~80 m of dry sand): the works fade their beach toward the old 25 m-deep seabed round the fill and left a
  5 m face. `SUBURB_SHELF` lays the sea in front as a shelving shore. The fill's EAST face is a revetment
  (`DIKE_NOT_BOXES`): the Rainbow Bridge's crossing is measured along x 1250 on the land grid, and it did not move
  (centre y -1121, measured before and after).
- **`ring_kita__6` swings south round the suburb** (`tools/island_suburb_dike.py`, a one-shot on the arterials input):
  from the ring_kita__5 / wangan_dori pad down x 1185 (clear of the Main line's viaduct at x 1250), along z 1085, up
  x 945, to a JOINT with `ring_kita__7` at x 895 (45 m east of the Suburb entrance's T). The old stretch (x 954 .. the
  pad) is gone, so **`kogai_michi` no longer meets the dike**: it stays at grade and runs on into `kogai_loop` (legs x
  1013 / 1117, bottom z 984) inside. Nothing inside touches the dike, so nothing is ramped onto its crest (a 14.7 m crest
  needs 180 m of 5 % ramp: that rule is why the old suburb was outside).
- **The dike's 側道 skips that stretch** (`island_dike.SIDE_SKIP`): the town-side offset of a 240 m U by ~180 m folds on
  itself, and a line that is not simple is dropped WHOLE -- it took the side road along ring_kita__7 with it, and the
  Suburb exit (which lands on that side road) failed.
- **Inside**: the water resort in the loop, the two resort hotels in the band between the loop's bottom and the dike's
  land-side toe (the third was dropped: 190 m of band holds two), houses round the loop. **Outside**: the beach, and the
  Ferris-wheel park west of the dike's west leg -- reached on foot over the dike now; no road reaches it (open item).

**Deep vacancy** (user: "reduce large vacancy behind buildings; every building faces a street; add streets"). Measured
as flat land more than 48 m from any street a building could front, with roads, sites, reserves, civic plots, rail,
seawall works and fields blocked. Fixes, each measured against the scan:
- `island_core_streets`: `nishi_ura` (the foothill triangle north of rinkai_dori), `yamasoi` (the strip between
  nishi_dori__3 and the massif's foot), `kojo_minami` (a U into the industry south of kojo_waku), and `kojo_ura`, the
  first `after` street: it carries the x -280 grid street on south through its junction, so it must be added AFTER the
  grid planner (`island_core_streets.py <record> --after`, a new `island_layout` step).
- `island_plan.STREET_REGIONS`: four `fill_*` rows of single lines found by a search that tries every line through a
  pocket with the planner's own rules (`_line_ok`, MIN_SPAN, water) and keeps the one serving the most empty ground;
  the industry grid 200 -> 140 m (its east-west lines listed, clear of Industry station's access at y -650); the suburb
  region starts at x 1000 (the station front and the loop are authored).
- What stays, and why: the long strips between the dike and its side road (the ramp zone: a street there would cross
  every ramped arterial in the air -- a coastal pine belt, 海岸防災林, is the Japanese answer and is proposed, not
  built), the airport island's grounds, the mountain and countryside (no district there), the paddy.
- **A civic plot must cover its building** (`island_civic_sites.py --check` now says so): the campus was a 240 x 180
  plot under a 260 x 220 piece and its wall stood on kichi_dori; the mall, the construction site (40 vs 60 m) and seven
  others were short too. The check doubles each library piece's extent about its origin (a civic building stands with
  its origin on the plot centre) and also flags a record whose size differs from `PLOTS` (re-site it).
- The arena (150 x 120) went to kojo_waku beside Industry station: the dike's side road now runs through its old plot,
  and nothing else on the island fronts it with that much room (the Ariake Arena pattern, bayside ex-industrial land).
- **The deep pockets: cut first, then fill** (user, 2026-10-03: "vacancy around the stations and the highways";
  "split big blocks with streets"; "one large car park instead of small ones spread around, the footway opened for
  its entrance"; "no need to force a park -- leave it empty if that makes more sense"; "residential more parks, light
  industry more car parks"). One street-facing row leaves the ground behind it empty wherever the next street is far
  -- beside an elevated expressway, a rail corridor, a station box, the dike. Three passes, in this order:
  * **Cut the block** (`tools/island_block_split.py derive <layout record>`, frozen into
    `pieces/IslandBlockSplits.json`, added by `island_core_streets.py --after`): every face of the at-grade street
    graph (each mouth joined to its pad's centre, or no block closes) with >= 2500 m2 of deep ground gets a straight
    street across it, square to its long axis, both ends T'd onto at-grade streets >= 34 m from any junction, over
    buildable ground, each half >= 45 m deep; a half still deep is cut again (the T). Each cut is tried through
    `island_core_streets.add` on a copy of the network, so a road piece too short for a mouth is skipped, not
    half-applied. Only a handful pass: most big blocks are crossed by a plot or a site, or would end on the dike.
  * **One large flat building** (`DEEP_BIG`, by district: supermarket, pachinko, スーパー銭湯, multi-storey car park, a
    団地, warehouse yard, cargo shed; each type >= 450 m apart), set back behind its forecourt, reached by a straight
    driveway or a 路地.
  * **One car park per pocket, as large as it holds** (`DEEP_CARPARKS`: `ParkingLot56` / `ParkingLot28` /
    `ParkingLot14`, the two large ones new composites), facing its street with a **driveway** straight to the kerb
    (`DRIVEWAY_W` 5 m, reserved like a 路地, never through a building or a held plot) and the B9 **kerb ramp** where
    it crosses the footway (`drive` / `drive_y`). Spacing by district (`DEEP_CARPARK_SPACING_BY`: 55 m in light
    industry, 160 m in housing). At the airport the car park is a `ParkingGarage` (multi-storey).
  * **Parks only where people live** (`DEEP_PARK_REGIONS`): the 60 m `Park`, else the new 27 m `PocketPark`
    (児童遊園: paved ground, trees, benches, a clock), closer in housing (`DEEP_PARK_SPACING_BY`).
  Anything else is left empty. Measured on the test layout: 52 parks (44 pocket), 64 car parks, 5 multi-storey car
  parks, 26 large buildings. Rows carry `"deep": true`. Preview: `assets/world_source/reference/island_preview_2026-10-03.png`.
- **The apartment ladder** (user, 2026-10-03: "larger and smaller apartments; modern ones with one line of units,
  horizontal or vertical over several floors; the outdated, cheaper two-storey one-line アパート"). Six placeholders in
  `library_jp_city.apartments` (library.blend, custom rows, placed by the housing / city / suburb mixes), at ordinary
  Japanese sizes: `Apato2F4` / `Apato2F6` (木造2階建てアパート: 1K units 3.64 x 7.28 m in one line, 2 x 2.8 m storeys,
  the open corridor and the external steel stair on the street side, a slate gable), `ApartRC3F` (RC 3階建て, 12 x 10 m,
  two units a floor), `MansionLine4` / `MansionLine6` (片廊下型: 6.5 x 11 m 3LDK units in one line, 6 / 8 storeys over a
  lobby floor, glass-panel balconies to the street, the corridor and the lift core at the back) and `MansionPencil`
  (1フロア1住戸, 8 x 14 m, 9 storeys). Deeper and longer than the kit's `Apartment`, so a frontage row leaves less
  empty ground behind it. Test layout: 177 placed.
- **Luxury housing** (user, 2026-10-03): `TowerMansion` (タワマン: a 36 m square tower of 32 x 3.1 m over a 48 x 44 m
  podium with a porte-cochere, ~111 m, wrap-around glass balconies, a sky lounge, a roof H pad; it fits no
  street-front slot, so it is a `DEEP_BIG` type in the city and downtown: 5 on the test layout),
  `LuxuryLowRise` (低層高級レジデンス: 4 x 3.4 m storeys, stone facade, deep planted balconies, a gated forecourt, the
  underground car park ramp; `SPACING` 250 m) and `TerraceHouse4` (メゾネット: four two-storey family units in a row,
  each with its own door, garden and balcony). **Any of these placeholders can become an enterable mission building**
  the way the 18 kits/interiors buildings are (SafeHouseCityLarge, SecureMansion ...): an interiors `.blend` for the
  type with its rooms, `DOOR_` / `EXIT_` / `LIFT_` / `MARK_` Empties (`interior_plans_jp.py` seeds one), its custom
  row pointed at kit `interiors`, which gives `_Open` (locked, a mission unlocks it) and `_Shop` (always open)
  scenes; a mission then places it at a plot (`island_civic_sites.PLOTS`) or an anchor
  (`island_buildings.OPEN_BUILDINGS` / `PUBLIC_BUILDINGS`). Replacing only the LOOK is a hand edit of the piece in
  library.blend (build_library.py keeps a hand-edited piece) and `build_buildings.sh`.

## The fish market: a straight quay, a car park at the dike's height, the crest carried across junction pads (PLAN S11 P12, 2026-10-13)

The Japanese layout the user approved on `docs/previews/market_p12.png` after six review rounds ("as long as it aligns
more to the Japanese setup"): the market stays LOW outside the dike (yard 5.6 m, crest 12.0), ONE truck ramp from the
existing signal, the public parked up at crest height, one straight shore. Roads: `docs/roads.md` "The fish market's
two gates". What was derived: `docs/previews/market_built_plan.png`.

**Land (`island_reshape.py`, three boxes applied last, like the Wangan terminal's platform).**
- `MARKET_QUAY` (262, 720, 730, 780): the plain's height out to **z 780** from the west wedge to the east bank -- one
  straight shore 458 m long where the yard's edge stood at z 762 and stopped at the wedge. x 262..610 is the market's
  quay; x 610..720 a plain vertical sea wall under the Wangan's viaduct (no buildings). Fill over a seabed of -4 (east)
  to -24 m (west): a quay wall into deep water.
- `MARKET_WEDGE` (276, 303, 584, 730): the west wedge was a SLOT of water along x 280..300 (a leftover of
  `GULF_FILL`'s x0 = 300): -24 m and 20 m wide at the shore, narrowing north to a 2 m ditch that ran on under the dike
  road to z 590 behind it. The quay box alone left a pond between z 700 and 730; filled only to the crest's edge it
  left a 17 m hole at the dike's land-side toe (298, 652..660) -- the corner's new arc no longer covered the slot's far
  end, and `island_dike.sculpt` fills no sea cell beside the crest. All of it is filled.
- `MARKET_TERRACE` (352, 398, 696, 753) at 11.9: the car park's terrace against the crest's sea face.
- **The fill does not lower the dike.** `island_dike.exposure` (the open-sea fraction within 1 km that picks a 12.0 or
  14.7 m crest) and `sokudo`'s "which side is the town" test both read the open sea from the land grid; with the wedge
  filled the corner's reading changed and the 側道 moved 20-40 m. `reshape` records every cell that WAS open sea and is
  not after the fills (`terrain/island_market_reclaimed.json`: the filled cells and the slot's cut-off blind end), and
  both readers count them as the bay they were (`RS.market_reclaimed()`). Measured: the pre-expressway record with
  the fills differs from the one without by 0.1 m at most on `teibo_sokudo` (it was 66 m).
- **`island_land.f32` was STALE before this job**: `coastal_works` reads the road record (`_road_near`), and the
  record had gained the north-coast beach lane since the grid was last built. A rebuild with the committed code
  changed 24 189 cells off the north coast (x 500..950, z -2200..-1700; <= 2.8 m, mostly < 0.5) before any market
  change. They are in this rebuild.

**The crest runs on across a junction pad (`island_dike.sculpt`).** A dike road ends at its mouth and the next one
starts at the pad's far mouth, so no segment spanned the pad and the embankment stopped either side of it: under the
x 567 junction the ground stood at the plain, 6.3 m under the road, over z 666..684 (and so under every crest
junction on the ring). One crest segment per pair of dike mouths of a pad, the wider road's width. Measured at the
market junction: 11.9 from z 664 to 696 where it read 5.6.

**The piece (`blender/tools/library_civic.py fish_market`, PLACEHOLDER massing; `FishMarket.tscn`, its mesh is its
collider).** Laid out in WORLD numbers through one helper, because every part answers to something a generator owns.
West to east: the small-boat corner under the terrace with the 浮桟橋 (two FIB1 and a WOB1, off the hall's landing
face); the terrace's retaining walls (2.2 m thick: the land grid's own edge is a 2 m slope) with a stair down the
south face and a 16 m footbridge off the east face to a gallery on the office; the 3-storey office whose roof is the
津波避難 deck (a flight up from the gallery, one down to the yard); the 90 x 29 m sawtooth hall open to the quay with
17 truck berths on its land side; the cold store, ice plant and 給氷塔 with its chute; a fence and gate at x 610; the
strip's coping and pipe railing. The quay face is a wall from -8 m to the yard along the whole 458 m.
- Reserve `fish_market` = (300, 712)-(610, 780) (it was (405, 705)-(570, 775)).
- **Differences from the approved picture** (drawn as notes on `market_built_plan.png`): the office is at the hall's
  WEST end beside the terrace (a footbridge to an office at the east end would be 110 m long over the hall); the car
  park is the ParkingLot56 composite (56 spaces, not ~40) with its T at x 375; no stairs up the dike face (the 1:2.2
  slope is walkable); no ramp wall (the ramp's sides are fill slopes); the ferris wheel park did NOT move -- sliding
  it south puts its south end on the beach, 3-5 m lower -- so the Suburb entrance passes 8 m over its north-west lawn
  (x 760..805, z 798..817).

### The yard came DOWN to a fishing port's height the same day (user, 2026-10-13 late; three fresh reviews)

The user, looking at the first build: "the boat quay should be same level as the pontoon in most images" -- at 5.6 m
over the water (the island's raised plain) no boat lands a catch, and the pontoon far below read wrong. Decision: the
yard at **y 2.0**, "a more reasonable arrangement to a Japanese fish market with quay"; then, at the user's request,
the plan went to three session-less reviewers (Japanese port planner, level designer, developer) BEFORE the rebuild.
Everything above about the terrace, the crest-level car park, the footbridge, the pontoon and "5.6" is the first
build's record; this is what stands.

**Land.** `MARKET_YARD` (262, 608, 700, 780) is SET to `MARKET_YARD_Z` 2.0 after the quay and wedge fills (not a
fill: `np.where`). The dike's own sculpt lays its 1:2 face down to it (toe z 718); the strip under the viaduct east
of x 610 keeps 5.6 behind the piece's 3.6 m retaining wall. `MARKET_TERRACE` is gone.
- `island_dike.sculpt`: a ramp segment was skipped when below `plain + 0.3` -- the ramp's lower half would have hung
  over the yard. It is compared with the ground under the segment now; and a dike segment's REACH is measured from
  the lowest land within 60 m (the developer measured the face's reach with not one cell to spare).
- x1 = 608, not 610: the grid's 2 m slope up to the strip must lie UNDER the wall (607.8..610), or a 3.6 m wedge is
  left behind it and the stair's head ends over a 1.8 m notch (developer, measured on the grid).

**The piece (`library_civic.fish_market`), west to east -- the PLANNER's order:** the public car park (two double
rows, 6 m aisles) and the office over a 直売所 / 食堂 floor (roof = 津波避難 deck, a solid stair) AT THE RAMP'S FOOT,
fenced from the working yard with one gate; the auction hall **90 x 20 m** open to the quay under a 4.5 m eave, its
east gable open, 13 truck berths 13-18 m deep on its land side; the cold store, ice plant and an 18 m 給氷塔 on the
quay (the 準備岸壁); the trucks' turning ground with a net store and container rows; the retaining wall and its stair.
On the quay a 船揚場 slipway (1:11, outside the wall) and three landing stairs; three 避難階段 up the dike's face. Six
boats moored ALONGSIDE (four FIB1, two WOB1), no pontoon.

**What each review changed** (the planner sourced nothing: every figure of theirs is RECALLED or judgement):
- PLANNER: public cars must not drive through the truck berths -> the ends were swapped (my layout, and the user's
  "push the parking east", had the public at the far end past 13 berths); hall 27 -> 20 m deep (a 荷さばき所 is
  15-25 m; backing a 4 t truck wants ~18 m); the dike crest is the refuge, so stairs to it; 乗り越し by ramp, no 陸閘;
  eave over the apron; do NOT move the quay south (29 m of water is a channel, not a basin).
- LEVEL DESIGNER (read in code): my car park had no aisles (2 m between rows); the quay was a one-way door -- the
  swim jump clears ~1 m and the quay is 2 m, the nearest way out 348 m off -> slipway + landing stairs; a chain-link
  box is a see-through bullet stop -> a low wall; cover lines (fish-box rows in the hall, containers).
- DEVELOPER (measured, scripts in the session's scratchpad): safe to rebuild; the x 608 edge; the ramp's fill toe
  reaches z 736..738 after the stamp's 6 m verge -> paving from z 738; the coast road's embankment covers x 262..288
  -> the slipway and car park start at x 290+; record heights below zero pass the whole layout (14 other roads
  already carry them); the site stands at 2.0 (`ground="centre"`); boats clear the fenders by 0.9 m.

**NOT TAKEN, for the user** (each needs a decision or a second job):
- the planner's quay at y 1.5 with a y 1.0 物揚場 for small craft -- the user said "about 2 m"; the slipway and stairs
  are the low landings for now;
- a ramp section of 3.5 m lanes and one footway (10.5 m) and a retaining wall instead of its seaward fill -- the ramp
  keeps the kit's `block` section (13 m) and its fill slope;
- LANES IN THE YARD (designer): AI cars stop at the ramp's foot, and police dispatch discards a car whose route is
  over 2.5x the straight line (a unit on the dike above a player in the yard) -- a teardrop at the foot and a spine
  east along z ~740 are roads, i.e. another layout + road rebuild, and the kit's street section has kerbs and
  footways a paved yard should not;
- a second, unlaned service ramp through the east wall; ladders on the quay wall; boats moored bow-in (縦付け);
  the seabed raised from -24 m to a port's -4 m; the buildings split into separate meshes for occlusion.

**Checked (the lowered yard, 2026-10-13 night).** A dry layout first (0 errors), then land -> layout -> the 16
fillets -> the island from the bridge stage (68 min): layout 0 errors, flow 2 539 lanes clean, 27 ramps (steepest
6.7 %, K >= 6.2), again on the filleted record; road gate 0 errors, 2 607 lanes; 2 027 buildings; footbridges 19
clean; `probe_buildings` 18 163 / 18 163; `probe_road_clear` 0 failures; `probe_road_launch` on the 7 % ramp both
lanes at 12 m/s with the traffic rules (0 launches, worst rise 0.6 m/s) and on both Suburb ramps at 22 m/s (0);
`probe_gps_route --world=island` 33 / 33; `probe_craft` PASS; `island_downstream --check` PASS; `check_roads.sh` 45 +
the old sample FAIL; World.tscn boots. Pictures: `docs/previews/market_built_plan.png` (the derived record) and
`market_built_{overview,quay,water,dike,ramp,yard,gate}.jpg`. NOT DONE: nobody has driven, walked or sailed it;
whether a swimmer really walks out by the landing stairs and the slipway was not tried in play; the nightly sweep
and `perf_gate.sh` were not run.

