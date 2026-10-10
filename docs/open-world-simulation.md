# open-world-simulation

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Open World Simulation (Part E)

---

## Open World Simulation (Part E)

### Zone streaming — ZoneManager / Zone / SpawnPool (`com.openworld.world`, E1)

As a player walks toward a populated area an AI group streams in; walking away streams it back
out — no scene stutter, no O(n) tree scans, host-authoritative + replicated spawns. Five pieces:

- **`Zone`** (`@Script extends Resource`) — placeholder-AABB zone data: `zoneId`,
  `size` (full XZ extents of the spawn box; *center is the marker's world position*),
  `loadRadius`/`unloadRadius` (hysteresis — unload **>** load avoids boundary flicker), nullable
  `geometry` (PackedScene, cosmetic), and two collections built with class tokens —
  `VariantArray<SpawnConfig> spawnConfigs` (ambient groups) and
  `VariantArray<NamedCharacterConfig> namedCharacters` (story AI with stable ids for Part F).
- **`SpawnConfig`** — `faction`, nullable `behaviorConfig` (else AICharacter `DEFAULTS`), `count`,
  `weaponScenePath` (AR4 default). Ambient AI share the `AICharacter.tscn` archetype.
- **`NamedCharacterConfig`** — stable `characterId`, `displayName`, `faction`, nullable `scene`
  (else AICharacter.tscn), `behaviorConfig`, `weaponScenePath`, `offset` (relative to marker).
- **`ZoneMarker`** (`@Script extends Node3D`) — the inspector-friendly in-scene anchor
  (a `Resource` AutoLoad can't take an inspector-assigned `.tres`, and a marker is positioned by
  dragging). Holds `@Export Zone zone`; **its global position is the zone center**. Registers
  with the manager in `_ready()`, deregisters in `_exitTree()` (the same register-with-AutoLoad
  idiom `Character` uses with `SpatialEntityGrid`).
- **`SpawnPool`** — plain Java helper (not an AutoLoad, not `util/ObjectPool` which throws on
  exhaustion and isn't tree-aware), owned by the manager. `acquire()` polls a `Deque<AICharacter>`
  (recycling a detached body, validated by `isInstanceValid`) or instantiates fresh;
  `wasLastAcquireRecycled()` lets load skip re-equipping an already-armed recycled body;
  `release(ai)` removes from tree + enqueues up to `poolCapacity`, else `queueFree`. **Only healthy
  bodies are pooled** — dead AI follow the normal death/ragdoll→free flow, so a recycled body never
  needs un-ragdolling.
- **`ZoneManager`** (`@Script extends Node`, AutoLoad) — mirrors `SpatialEntityGrid`'s
  shape (JVM-static `instance`/`get()`, `_exitTree()` frees geometry + clears maps + `pool.clear()`
  for leak discipline). Throttled tick (`evalInterval`, 0.5 s) over registered markers computes
  nearest-player XZ distance via `PlayerRegistry.getPlayers()` (O(playerCount)); `< loadRadius` →
  `load`, `> unloadRadius` → `unload`.

**Sizing a zone (radii are center-relative, NOT edge-relative).** Both `loadRadius` and
`unloadRadius` are measured from the **marker (zone center)** and are **fully independent of
`size`** (the spawn box). So the unload trigger can and *should* be much larger than the box — a
player stepping a few metres past the box edge does **not** unload (you'd have to reach
`unloadRadius` from the center). Defaults: `size = (60,10,60)` (30 m half-extent),
`loadRadius = 200`, `unloadRadius = 350` — unload only fires 350 m from center. Recommended
relationship (`halfExtent = max(size.x, size.z)/2`):
`unloadRadius > loadRadius > halfExtent`, e.g. `loadRadius ≈ halfExtent + pre-spawn lead (~150 m)`
and `unloadRadius ≈ loadRadius + hysteresis margin (~150 m)`. `ZoneManager.warnIfMisSized`
(debug-gated) logs once at registration when a `.tres` violates this (the cause of "everything
unloads the moment I step out" — a too-small `unloadRadius`).

**Authority:** AI spawn/despawn is host-only — geometry is instanced on every peer but the spawn
work is skipped on a non-server client (`net.isNetworked() && !net.isServer()`); clients receive
the bodies through the existing `announceSpawn → MSG_SPAWN → GameManager.spawnReplicatedCharacter`
path, and late-joiners via `sendBaselineSpawns`. Unload calls `announceDespawn(characterId)`
before pooling/freeing.

**Incremental streaming pipeline (the district-border anti-freeze rework):** a zone crossing used
to be one synchronous `load()` — `GD.load`-parse a 7–19 MB district `.tscn` on the main thread,
instantiate ~1600 nodes, tree-enter 500+ static bodies + a `NavigationRegion3D`, then spawn every
AI/vehicle, all in a single physics frame. Streaming is now a per-marker **task state machine**
(`StreamTask` in `ZoneManager`), processed every physics frame under a time budget
(`streamBudgetMs`, exported, 4 ms, ≥1 step of progress per frame so tasks can't stall):
`GEO_REQUEST → GEO_WAIT` (PackedScene parsed on **engine worker threads** via
`ResourceLoader.loadThreadedRequest`; main thread only polls) `→ GEO_INSTANTIATE` (one frame:
instantiate off-tree — node construction only — then strip children) `→ GEO_ENTER` (children
re-enter the tree a budget-slice per frame — tree entry is where physics/render registration
happens; a `NavigationRegion3D` gets a frame alone for its nav-map sync spike) `→ SPAWN`
(AI/named/vehicle spawns drained as work items — the formerly-deferred "frame-spread spawning",
now done). Unload is likewise batched: `FREE_BODIES → FREE_GEO` (per-child detach+free instead of
one ~1600-node `queueFree`). Rules that fall out of this: a marker with an in-flight task is in
neither `loaded` nor eligible for a second task; the LOD-low placeholder stays up until full
detail is **completely** entered (no visual hole) and returns only when the last child is freed;
a load whose player retreats past `unloadRadius` mid-stream is **cancelled** (partial content
torn down synchronously; off-tree staged children are explicitly freed — they'd leak otherwise,
same in `detectSceneReload`/`_exitTree`). Synchronous teardown still exists for marker-exit /
scene-reload / AutoLoad-exit (`unloadImmediate`/`teardownZone`). `maxLoadsPerTick` (now 2) only
caps how many *threaded parses* start per eval tick — main-thread work is always serialized to
one zone per frame. The remaining single-frame cost is `instantiate()` of the whole district
(~1600 node constructions, no registration); if that ever reads as a hitch on Steam Deck the next
lever is baking districts as sub-chunk scenes, not shrinking the budget.

**Binary district scenes:** `resolveGeometryPath` prefers a sibling `.scn` over the wired
`geometry_path` `.tscn` when it exists — the baked districts are multi-MB *text* scenes whose
parse dominates stream-in time even on a worker thread. `PieceBinaryConverter`
(`hosts/ConvertPieces.tscn`, one-shot batch job in the `WorldBaker` idiom, mtime-skips
unchanged files) resaves them all; `blender/tools/build_piece.sh` runs it automatically as its final step
(so a fresh bake is never shadowed by a stale `.scn`) — re-run it manually only after baking a
district by hand. `.scn` files are derived artifacts (delete-and-regenerate safe); the `.tscn`
stays the source of truth. No master re-bake or `geometry_path` edit is needed for the preference
to kick in.

**District authoring seam (see `blender/AUTHORING_GUIDE.md`):** a district rebuild
regenerates the `.blend` **in place** — only the procedural collections (`STREET`, `MARKERS`,
`STREET_LOD_LOW`, `ROADS_SRC`) are wiped; `MANUAL` (hand-authored content, exported + baked) and
`NEIGHBOR_REF` (read-only library-linked neighbour/master context from `tools/link_neighbors.py`,
dropped by every export) survive. `build_piece.sh District_<theme>_<gx>_<gy>` (stem form) is the
bake-only loop for hand-edited blends — it skips the regen entirely. Because linked libraries can
carry same-named collections (several linked `STREET`s), every collection lookup in the Blender
pipeline is local-only (`library is None`) — keep new lookups that way.

**What streams vs. what's static (a common confusion):** only two things are added on load and
removed on unload — the **AI bodies** and the zone's **`geometry` PackedScene** (instanced as a
marker child, `queueFree`d on unload). Anything authored directly into the `ZoneMarker` *scene*
(the debug box from `showDebugVolume`, or any mesh you drop under the marker node) is **static scene
content — it never streams**; it is the persistent zone *footprint/outline*. To make a mesh stream
in/out, assign it to the Zone's **`geometry`** field, not as a marker child (a Blender-exported
zone-chunk `.tscn`, same convention every district piece's `geometry_path` already uses). Zones also
do **not** carry their own navigation — AI use the level's `NavigationRegion3D`; nav is a
parent/world concern.

**Body recycling is OFF by default (`recycleBodies`, EXPERIMENTAL).** Reusing a full character body
subtree (detach via `removeChild`, re-attach via `addChild`) is **unsafe** in godot-jvm: the
body carries a `top_level` camera (`TPSCameraController.setAsTopLevel`), a muzzle-flash
`GPUParticles3D`, and a nameplate `SubViewport`, and re-attaching that subtree leaves them
half-initialised — `get_global_transform "not inside tree"` / `particles is null` errors, then a
native use-after-free **segfault on zone enter** (no AI death required). So unload frees and
load instantiates fresh — correct, and no longer a stutter concern: spawns are frame-spread by the
streaming pipeline's SPAWN phase (see above), which was always the proper perf answer, not body
reuse. The `SpawnPool` + `activateForSpawn` reset path is kept
behind the flag for future hardening only. When recycling *is* on, only `isAlive() && !isDead()`
bodies are pooled (a dead body is ragdolled and `activateForSpawn` does not un-ragdoll it).

**The manager is an AutoLoad, so it survives `reloadCurrentScene()`/restart** — and pooled bodies are
parentless (held only by the deque, not in the scene tree), so a scene reload does **not** free them.
`detectSceneReload()` (top of `_physicsProcess`, compares the current-scene instance id) drops
`loaded` + frees the pool on any scene swap, so a restart never resurrects a body from the old scene
into the new one (this was a reproducible restart crash).

**Despawn safety — dangling references:** streaming despawns bodies that other systems may still
reference between target scans. `AICharacter.validateCurrentTarget()` (run every active frame, before
`super._physicsProcess`) drops `currentTarget` + its bone caches the moment the target is freed or
pulled out of the tree — without it, the FSM dereferences an out-of-tree node (`get_global_transform`
/ `look_at` "Node not inside tree") and segfaults once it is freed. `activateForSpawn` also clears the
recycled body's carried-over camera aim target and escort reference for the same reason.

**Pooled-reuse reset constraint (critical):** a pooled body's `_ready()` does **not** re-run on
tree re-entry, so reuse must re-initialize explicitly. `load()` calls
`AICharacter.activateForSpawn(worldPos)` **after `addChild`**, which sets global position,
**re-captures `spawnPosition`** (the patrol anchor, otherwise only set in `_ready()`), clears
`isDead` + all sensor caches, resets LOD + staggered timers, `Health.resetFull()`, re-registers the
`SpatialEntityGrid`, and calls `AIController.resetState()` (FSM back to `initialState()`, all timers
+ last-known targets cleared). Without the re-anchor a recycled AI would patrol around its *previous*
spawn point.

**Debug visualization + walk-test setup:** `ZoneManager.debugLog` (exported, on) prints each
load/unload decision, an approach-distance line while a player is near, and per-load recycled-vs-fresh
+ pool-idle counts. `ZoneMarker.showDebugVolume` (exported, on) builds at runtime a translucent
box (the spawn volume, `zone.size`) plus flat rings at `loadRadius`/`unloadRadius`; the box tints
**green while streamed in, cyan while idle** (driven by `setLoadedVisual` from the manager) — so you
can see a zone and walk into it. Both are pure debug aids, off via their export flags for shipping.
The `DebugHarness` **F12** key drops a code-built `Zone`/`ZoneMarker` in front of the
nearest player (`spawnDebugZone()`, no `.tscn`/`.tres` needed) if you want a quick zone to walk-test
without editing a scene — the standalone example zone scene this used to point at (`zones/DebugZone
.tscn`/`.tres`, `zones/DebugZoneGeometry.tscn`) was retired once the real 36-district open world
(`assets/world_source/`, `hosts/WorldMaster.tscn`) existed to walk-test against instead.

### Ambient traffic & the road graph (roads-v2)

**Generated data, not runtime inference.** `assets/world_source/lib/road_graph.py` (pure Python,
`python3 lib/road_graph.py` self-tests) turns an abstract centerline graph — junction nodes +
polyline edges with `lanes`/`oneway`/`class` — into everything the runtime consumes: per-direction
per-lane offset routes (`<edge>_<F|R><lane>`, keep-left, trimmed at junction stop lines), bezier
**turn connectors** (`c<node>_<in>_<turn>`, short names — Blender's 63-char object-name cap) carrying
`turn` (L/S/R) + `approach` (N/E/S/W) metas, and `intersection_` markers. Turning is a **data
lookup**: each chained lane's `_0` empty stamps `next_routes` (its connectors) + straight-biased
`next_weights` (0.6/0.2/0.2); `LaneGraph` endpoint clustering is only the legacy fallback (now
straightness-biased via `VehicleRoute.start/endTangentXZ`). Weighted choice = `util/WeightedPick`
(engine-free, unit-tested; malformed weights degrade to uniform, never throw). Keep-left legality:
1-lane approach → L/S/R; ≥2 lanes → curb lane (idx 0) L+S, median (n−1) R+S, middle S only; target
lane clamps by index — that clamp is the whole mixed-lane-count answer. `assemble.lay_road_graph()`
emits it all (raises on any name collision/overflow — Blender auto-rename would corrupt the baker's
name grouping).

**Graph sources:** master backbone — `build_world.backbone_graph()` (junction-split, 2 lanes per
direction, 336 lanes + 568 connectors + 49 junctions; `radius_fn` forces stop lines to the 21 m
paved footprint) + `backbone_deck()`, an always-resident **collision-only deck** under every
arterial (without it, cars outside streamed districts fall into the void — PLATEAU districts have
no always-resident ground) in the same exported `ARTDECK` collection. Authored in the master
blend (debuggable there), NOT runtime Java. **There is deliberately no world-spanning safety
floor** (`build_world.safety_floor()`/`--with-floor` and the per-district
`add_ground_safety_plane()` were both removed outright) — a collision-only floor a
meter-plus below visual ground silently trapped `Character`/`Player` bodies with no recovery
path, since neither has any fall-out-of-world safety net (unlike vehicles, which
`ZoneManager.maintainTraffic` reclaims below `Y = -30`). Falling off a road or off the
ArtDeck now falls through, same as any other gap in authored ground — see
`AUTHORING_GUIDE.md` for the districts/void-cell design this replaced it with.

> **A SEABED IS NOT A SAFETY FLOOR** (island v3, 2026-08-30 — `blender/WORLD_REBUILD_PLAN.md`).
> `Island_base` has a `Seabed` sheet under the whole sea and it does not reopen the above. A safety
> floor is *invisible*, *collision-only* and sits a metre under the **visible ground**, so a body
> that falls through a hole lands somewhere it cannot see with no way back — which is why it was
> removed. A seabed is the terrain **continuing past the waterline**: visible, sloped, walkable in
> both directions, and it does not exist under the island at all (`island_v3_terrain.Terrain
> .surface` returns the land wherever there is land). Falling off a cliff onto land still falls.
> Two rules came with it, both cheap to get wrong: a ground sheet must be forced to **face up**
> (`recalc_face_normals` infers "out" from the shape, and an open sheet with no skirt came out
> entirely inverted — invisible from above AND unwalkable to Recast, while its collision proxy
> worked perfectly), and a solid-but-unwalkable surface takes the `-noped` marker (below) so it
> does not bake a 4 km walkable sheet under the sea.
>
> **The beach is the part that is easy to get wrong while fixing the fall-through.** The land stops
> 0.60 m above the water, so a sea floor starting at the waterline rings the island with a 0.80 m
> wall — swimmable *to*, impossible to climb (`MovementController.stepHeight` is 0.35 m), i.e.
> falling out of the world replaced by being locked out of it. `SHORE_Z` starts the floor 0.20 m
> **under the land**: one step down onto ~27 m of dry sand before the water. Measured on 16 shore
> rays: worst natural-coast step **0.206 m**, 0 samples with no surface.
> `blender/tools/check_island_water.py` is that layer's gate (sea-below-land, continuity, the beach
> step, cliff/quay classification, and the markers).
>
> **The water shader fades its detail with distance** (2026-09-16, user-reported "repeated small squares far
> away"). The water shader (now `assets/vfx/water/water_common.gdshaderinc`, Binbun3D CC0) samples 256 px seamless noise in WORLD space (a tile every 5 m in DebugWorld,
> 40 m in World; foam every 2 m) and read the waves at one fixed mip level, so far water aliased into a speckled
> grid of repeated pixel squares — measured on a Vulkan screenshot, not guessed. Now fragment samples use
> automatic mipmaps with anisotropic filtering, a second layer at `far_scale_ratio` (0.125 = 8x bigger features)
> fades in between `detail_fade_start` and `detail_fade_end` (40-320 m from the camera), the foam shape does
> the same, and the normal map flattens toward `far_normal_strength` far out. Near water is unchanged
> (before/after screenshots compared). Vertex displacement still uses the fixed LOD (no derivatives there).
>
> **The dark band under the horizon was the SKY, past the edge of a finite sea** (PLAN.md 3.7, 2026-09-18). Sky3D
> paints every direction below 0° elevation as `ground_color × scatter` (a dark grey), and the sea box ends 8 km
> out, so from any altitude its edge sits a few degrees under the horizontal line and the sky's "ground" filled
> the gap: measured with `tools/godot/shot_horizon.gd` (needs a display; `--mark-sky-ground` paints that colour
> magenta), the band turned magenta, 0.19/0.26/0.32 against a 0.78/0.86/0.92 sea, from 400 m and 1500 m. The fix
> is an ocean that reaches the horizon, not a repainted sky: `WaterVolume.farOceanExtent` (100 km in both worlds,
> the camera's far plane) lays four flat quads round the surface box in the same water material, no collision.
> What is left is under 1° past 100 km (6 px at 1500 m), and **`SkyDome.ground_color`** (the owner: the Sky3D
> script writes it into the material at startup, so editing the material's `shader_parameter/ground_color` alone
> does nothing) is (0.75, 0.85, 0.95), measured to within 0.03 of the far sea. From 400 m nothing is left.
> DebugWorld looks the same before and after: from altitude it renders as haze with no horizon line.
>
> **All water is ONE swim volume** (`water_sea`, baked to a `WaterVolume`), and one box can cover
> the sea, the bay and the lagoon because the land is above every part of it: a box whose TOP is the
> water line cannot touch a character standing on land. `Character` decides wade-vs-swim from the
> true depth under the body, so the beach wades and only real depth swims. **`WorldBaker.buildWater`
> used to build a bare `Area3D` on the default collision mask** — no script, so `setInWater` was
> never called, and mask 1 never sees a character body (they are on `CollisionLayers.CHARACTER`).
> Either half alone was fatal, and together they looked exactly like a swim feature that was never
> written; `SwimState` and the buoyancy spring had been complete since I1.
>
> **The world edge is a LOGIC WALL, not an invisible collider** — `world.WorldBounds`, baked from a
> `bounds_<id>` marker. A warning band inside `warnMargin` (no physics), hard position clamp past the edge with
> only the OUTWARD velocity component cancelled (so swimming home is unresisted), and a `floorY`
> kill-Z that puts a body back at `PlayerSpawn`. A collider would also stop bullets, ragdolls and
> vehicles, would give a body sliding along it no "leaving the area" moment, and — the deciding one —
> could never recover a body that is ALREADY outside. **The wall stands inside the sea floor's own
> edge, not at the world square**: `SEABED_MARGIN` 288 m puts the floor at ±2304 and
> `BOUNDS_INSET` 144 m puts the wall at ±2160 — a 4.6 km sea with 202 m of water at the
> tightest heading and 498 m at the median, over 1 km only on the diagonals. Both extremes were
> walk-tested: the wall AT the world square read as a fence 700 m offshore, and a floor out at
> the ±3800 m budget read as 2.0 km of empty ocean. 3.5 km is not available — the land's own
> bounding box is 3.72 × 3.94 km, because the offshore airport reaches y = −1976 m.
> **ONE physical rule, the hard wall; the band only WARNS** (2026-09-16, PLAN.md P0 0.3 then 0.6).
> User-reported as "an invisible collision block on DebugWorld's loop_p005 corner": `confine` used to
> cancel the outward velocity whenever ANY correction was non-zero, so the soft band's INNER edge was
> a wall with no shape for debug drawing to show (a player stalled at z -363.8, a driven car at
> -356.8). 0.3 made the band a nudge; 0.6 (user decision: "remove the soft push entirely, only warn")
> DELETED it — `softMargin`/`pushSpeed` and the RigidBody3D velocity bias are gone, because a physical
> push nobody can see is indistinguishable from a bug. Past `halfExtent` the position is clamped and
> only the outward velocity cancelled; nothing inside the wall is ever moved. `warnMargin` (80 m;
> DebugWorld 40) raises `EventBus.leavingArea(distanceToWall)` / `returnedToArea` on the EDGE for each
> locally-owned player, and `ui.AreaWarning` (self-gated, not in `BASE_LAYOUT`) shows "LEAVING THE
> AREA" with the distance and a red vignette deepening toward the wall. Local per peer, no message.
> `WorldBounds.showDebugVolume` (on in DebugWorld; DebugHarness **Shift+F2** toggles it) draws the wall
> red and the band's inner edge yellow; `debugLog` prints each hard correction (throttled per body)
> and the warning edges. `WorldBounds.get()` + `distanceToWall(pos)` are the one owner of "how far is
> the edge". `tools/godot/check_world_envelope.gd` asserts every Road Kit station + 18 m of paving
> clears the warning band. Gate **`tools/godot/probe_world_bounds.gd`** 16/16: a Player, an
> engine-driven RigidBody3D and a swept CharacterBody3D keep their FULL speed right up to the wall and
> are turned back at it, `leaving_area` fires once (for the player only) and `returned_to_area` once
> on walking back, and the HUD warning shows and hides; `-- --control` (a velocity cancel in the band)
> fails 5. `HandlingTest.tscn`'s three wall cases unchanged.
> The *accurate*
per-district ground is PLATEAU terrain: originally imported via `extract_plateau.py --dem`
(CityGML `dem:TINRelief`) → `plateau_import.import_terrain`, which built a real sloped ground mesh
(visual + collision) and draped roads onto it — districts extracted without `--dem` have no
continuous ground and fall through in the gaps (no safety-floor catch anymore, see above). **That
extraction/import tooling was removed** once every PLATEAU-derived district/overlay/building asset
had already produced its permanent output `.blend` — see `AUTHORING_GUIDE.md` §2/§6. Terrain is
now hand-owned exactly like everything else; road authoring specifically is the
`road_kit_authoring` addon's point/port graph + `.lanekit.json` v2 sidecar (see "Ambient traffic &
the road graph" below), not the old `road_<name>` centerline/`.roads.json` pipeline that predates
it.

**Spawning:** region markers carry `traffic_count`/`traffic_route` → `WorldBaker.buildZone` builds a
`VehicleSpawnConfig`. `traffic_route` is a route-name **prefix** (`"art_"`, or `"<piece>__"` once a
sidecar exists — the master build flips the meta by checking for the sidecar, so re-run it after
authoring): `ZoneManager.spawnLanes(name, center, maxDist)` matches exact first, else
prefix-collects plain lanes (never turn connectors) whose entry is within `unloadRadius`, then keeps
only those a car can drive at least `unloadRadius` from (`util.LaneReach`, over the same
`LaneGraph.successorsOf` the AI follows — name order put cars on lanes with no successor).
`spawnTrafficCar` is the ONE placement owner (zone load and top-up alike): a per-zone rotating
cursor over those lanes, the car set down ON ITS WHEELS and pitched along the lane (`Vehicle.groundClearanceAtRest`;
with its origin on the road surface the hull started buried and was ejected -- backwards on the touge's 10 % grade,
a 35 m roll to a `stalled` reclaim in 3 of 5 island runs), a slot with nothing within `TRAFFIC_SPAWN_CLEARANCE` (10 m, the obstacle
ray's reach), the car **faced along its lane**, and no spawn at all while a named route matches no
lane yet. See "Ambient spawn placement" under Terrain3D below.
**All lane lookups are registry reads, never scene-tree walks:** `VehicleRoute._ready/_exitTree`
register/deregister with a `TreeMap` on `ZoneManager` (the Character↔SpatialEntityGrid
idiom; sorted names make the prefix query ordered for free), and `entryPoint()` caches the first
marker position per tree entry. The old recursive whole-tree scans (two per spawn, tens of
thousands of JVM-bridge calls with a district streamed in) ran inside the 0.5 s `maintainTraffic`
tick and were the "periodic hitch in all movement" regression; `VehicleRoute.resolveRoute`/
`pickNextRoute` (every lane end) go through the same registry.
`maintainTraffic` reclaims: dead / route-finished / **fell-out** (Y < −30 — an off-road car
free-falls with unchanged XZ, so the range check alone never catches it) / out-of-range, then tops
back up (GTA disposable traffic). `debugLog` prints spawn/reclaim/status lines — "N cars, M moving,
K routed" is the headless-smoke signal (routed-but-0-moving = falling through missing ground;
route-finished churn = broken junction wiring).

**Junction discipline:** `CruiseState`'s curvature probe cannot see past the current route, so
`VehicleAIController` clamps throttle (`junctionThrottleScale`, 0.45) within `junctionSlowdown`
(18 m) of any chained lane end and while riding an L/R connector — without this cars enter 90°
turns at full cruise speed and fly off. Phase 2 (JunctionArbiter FCFS grant sets + timed signals
keyed on the baked `approach`/`turn`) and Phase 3 (highway ring + ramps + `speedLimit`) are next —
see PLAN.md "Roads & Traffic v2".
Since 3.2d cars also hold a CORNER SPEED, `sqrt(cornerLateralAccel·R)` braked for ahead of every bend on the
lane (`VehicleAIController.cornerSpeedLimit`, 4 m/s²; see "The touge, driven and fixed").

**Gone (2026-10-08): the `CharacterInfo` / `VehicleConfig` ClassCastException on instancing a car.** The BASE
`Vehicle.tscn` embedded a JVM-scripted `CharacterInfo` and `VehicleConfig` sub-resource whose script bound late, so
their setters received a plain `Resource` (3 + 3 per process in `run_net_debugworld.sh`). Every car scene replaces the
whole config with its own `.tres` and `Vehicle._ready` builds a `CharacterInfo` when none is set, so both were dead
weight and are removed from the base scene. Do not put a JVM-scripted sub-resource back into a base scene that
inherited scenes override.

### Traffic by region, the idle-car recycle and the 210 m ring (user, 2026-10-10)

**Reported:** "barely more than 3 cars even in the busy city / suburb, residential barely any; the west centre the
most crowded". **Measured** (`tools/godot/probe_traffic_census.gd`: the player stood at each district, ambient cars
counted every 2 s for 30-40 s): the budget was always FULL (10 alive) but the cars were not near the player --

| site | within 100 m / 200 m before | after |
|---|---|---|
| downtown_core | 0.0 / 2.2 | 0.5 / 5.5 |
| nightlife | 0.0 / 0.1 | 2.9 / 9.7 |
| residential_north | 2.7 / 7.7 | 2.5 / 8.3 |
| light industry (the "residential" site) | 2.7 / 5.0 | 3.1 / 6.3 |
| suburb | 1.3 / 6.1 | 0.5 / 6.3 |
| industry | 0.4 / 4.9 | 0.8 / 5.0 (west_centre site) |

Two causes, two fixes, and one honest limit:
1. **A far car that was WAITING held its slot for ever.** Only a car moving AWAY counted as "leaving" (the 2026-10-07
   recycle rule), so a car at a far red light or in a far queue was never recycled and the ring filled with cars
   200-300 m out. `ZoneManager.trafficIdleRecycleSeconds` (12): a car past `trafficRecycleDist` that has not come
   closer to any player for that long is recycled too, under the same rules (out of this peer's view, one per
   `trafficRecycleSeconds`, only while fewer than `trafficNearTarget` cars are within `trafficNearRadius`). 0 = the
   old rule (the control).
2. **The ring was wider than the street the player can see.** `trafficSimRadius` 250 -> 210, `trafficRecycleDist`
   140 -> 110, the near target 6 within 200 m -> 7 within 140 m. A 150 m ring was MEASURED and is too small: the
   spawn rules (never within 80 m, never in view nearer than 160 m) leave no legal entry -- one site had 0 cars and
   7 714 refusals. The far tier's inner edge follows the ring.
3. **The limit:** 10 cars in a 210 m ring is ~2 within 100 m of a player standing still, whatever the rules. More
   cars near the player means a bigger budget, which is a CPU cost (a car is a body AND a seated driver) -- that is
   the host's **World density** setting (docs/front-end.md), not a default.

**The mix is per REGION now** (`game/traffic.json`, `world.TrafficMix`, `Tables.TRAFFIC`): a region of the places
record (`Places.regionAt`, the boxes the buildings were placed by) takes the row whose key is the longest PREFIX of
its name (`residential_north` -> `residential`), else `default`. `mix` = vehicle id -> weight, `scale` = the share
of the budget kept while the busiest player stands there (farm 0.6, harbour 0.8, the housing 0.9). Industry and the
harbour draw box trucks, crate trucks and kei trucks (BOT1 / CRT1 / POT1 / KET1), the farm kei trucks and kei cars,
the nightlife and station fronts taxis. Simulated cars (`VehicleModels.trafficScene(faction, roll, region)`, the
host's pick, replicated as the model index) and the far tier's placeholders both read it; police / military traffic
keep their own cars. An unknown vehicle id or a non-positive weight is a DataTable problem (`TrafficMixTest`, which
also asserts industry > 70 % trucks, the farm > 50 % kei trucks, downtown < 20 % trucks). COT1 (the 12 m container
truck) is deliberately not in any mix: nobody has driven it through a junction as traffic yet.

The three tiers, for the record (the user asked about "placeholder vehicles for the far ones" -- they exist):
REAL cars within `dummyInDist` 70 m; the same cars ON RAILS (`Vehicle.setDummy`: no wheel physics) from
`dummyOutDist` 90 m to the ring; `FarTraffic`'s 60 script-free MultiMesh cars from the ring + 20 m to 700 m, local
per peer. Slowing traffic down does not make a car cheaper per tick; the on-rails tier is what does.

Gates: `probe_traffic_census.gd -- --min-near=4` (every site >= 4 simulated cars within 200 m; in nightly_gates,
slow), `probe_traffic_ahead.gd` (no car born ahead of a fast player; its control fails 2 -- it now counts ambient
traffic only: two PARKED cars in a car park 85 m off the line had failed it), `probe_traffic_spawn`, `probe_far_traffic`,
`probe_road_zones` PASS on the new ring.

### Terrain & seam alignment (ground is NOT a flat plane)

Each district's real ground is a **DEM-derived heightfield** — originally imported via
`extract_plateau.py --dem` → `lib/plateau_import.py: import_terrain` (one continuous sloped mesh
per district, visual + collision in one; that extraction/import code has since been removed, see
`AUTHORING_GUIDE.md` §2/§6 — every district's terrain is now a permanent, hand-owned part of its
`.blend`, this just describes how it originally got its shape) — genuinely non-flat wherever DEM
data was extracted, not a flat square. What makes adjacent districts agree at their shared edge is
a **theme-elevation-step + taper system**, not literal shared/welded geometry:

- `lib/world_grid.py`'s `THEMES` dict assigns each of the 7 region themes a flat **baseline**
  elevation (harbor 0, city 2, resid 4, rural 10, mtn 40, snow 90, industry 0) — a coarse
  staircase across the whole map.
- The original import blended the real (sloped) terrain height toward that baseline within a
  border margin of every district edge (`plateau_import.seam_taper()`, no longer present but
  baked into every existing district's terrain), so the interior keeps real terrain shape but
  every edge lands at a known, neighbor-predictable value.
- A `.seam.json` sidecar per district (36 of the 39 district files have one) records each edge's world
  position, elevation, the neighbor's expected elevation, and route-name chaining;
  `tools/check_seams.py` (pure Python, no Blender needed) verifies two adjacent `.seam.json` files
  agree — this is the existing, already-automated seam-alignment QA step, run whenever
  neighboring districts change.

So cross-district alignment for elevation is a **solved, working system** — districts don't need
literal vertex-welded ground, they need matching boundary *values* (elevation, route endpoints),
which the taper + `.seam.json` + `check_seams.py` trio already enforces.

**Road authoring is now the POINT/PORT GRAPH** (`blender/ROAD_POINT_GRAPH.md`, the design of
record; `blender/addons/road_kit_authoring/point_*.py`). A road is an ordered chain of **road
points** — an Empty that is simultaneously a *station* (its own cross-section: lanes per direction,
median, kerbs, footways, structure) and a *port* (its typed `SEGMENT` / `JUNCTION` / `AUX` links).
A junction is a clique over `JUNCTION` links whose member points **are** the stop lines; a ramp is
an aux slot plus an `AUX` link. Every along-the-length change — lane drop, lane opening, one-way,
an acceleration lane with its taper — is just *"two stations that differ"*. The authored record is
a git-diffable `<stem>.roads.json`; the Empties are a **view** of it. Build emits per road run a
swept `__surface` carrier (a GN layer stack), `__edges` kerb/footway runs placed against the paved
**outline** so gores open by themselves, `__edges` kerb/footway/**barrier** runs per junction
corner too, a pad per junction, a paved **gore strip** per ramp, the terrain cut, and split
`-colonly` road/footway collision proxies. `blender/tools/check_roads.sh` is the one command
that runs the gate (31 checks since B9: the pure self-tests, the headless pipeline smoketests and every Godot plugin test; the Blender panels it used to draw are retired). The worked example of all four link types is `assets/world_source/pieces/RoadKitSample.roads.json`; the editing how-to is `addons/road_kit/README.md`.
**The Empty's transform IS the road frame** — position is the station, **local +Y is travel
direction** (points draw as `ARROWS` so that axis is visible; `SINGLE_ARROW` draws along +Z and
showed the wrong one), roll is banking, and `tangent_mode = MANUAL` makes the rotation drive the
curve, with `handle_in`/`handle_out` in metres (0 = the chord). **Rotating a point IS the bend
gesture — there is no mode to set first.** Points are *born facing their road* (`new_point` takes a
`facing`; `Extend Road`/`Insert Point` pass the chain direction — never via `face_matrix`, which
reads a `matrix_world` still identity on a just-created object and would move the station to the
world origin), and the tool stamps the facing it gave each one in `RKA_Point.auto_tangent` (derived
state, **not** in `.roads.json`). `read_point` then promotes an AUTO point whose facing has left
that baseline to MANUAL — a *read-side* derivation, so it takes effect in the overlay, the gate,
Build and the export at once with no write and no handler. The baseline is what separates a
rotation from a **drag** (a translate changes the chain tangent while leaving the rotation alone,
so recomputing-and-comparing would falsely promote every dragged point). `point_ops.sync_facings()`
is the write half — promotion first, *then* re-face what the tool still owns — run by Build, by the
live rebuild, and by the `Follow Road (Auto)` button; `point_profile.chain_facings()` is the one
owner of "which way does this station face". The overlay draws the **resolved centreline**
(`point_profile.centreline_runs()`, resample-only so it is cheap enough for a per-frame draw
handler), so a rotation reshapes the road live without any rebuild — `rka_live_rebuild` (off by
default) is only about the *mesh*. **Straightness is measured, never authored** (`road_points.segment_bend_deg`) — there is no straight/curved flag to keep in sync. The
`Connections` panel lists the active point's links with derived span / straight-vs-bend / taper
verdict (the taper number comes from the gate's own `taper_min_length`, so the two cannot
disagree), and `Connect Selected` is anchored on the **active** point — `AUX` is directed
(mainline → ramp), so `selected_objects` order was a coin flip. The two previous models are gone: the mesh-graph `graph_*.py` is
archived under `legacy_graph/` (not imported) and the per-piece generators (`ops_placement.py`,
`ops_intersection.py`, `ops_segment.py`, …) were **deleted** — see `legacy_graph/README.md`.
District_industry_5_1's hand-authored `MANUAL` collection predates this and is still valid baked
geometry; it is no longer the authoring reference.

**Style, markings and the Path3D preview (2026-08-27, `blender/ROAD_STYLE_AND_PATH_PREVIEW.md`).**
Three things landed together; the doc is the design of record and its §7 is what actually shipped.

- **The exported Path3D IS the lane, now.** `WorldBaker` builds every `Curve3D` an ambient car
  drives from the `.lanekit.json` `curve` block, and `point_export` used to refit those handles
  from the chord through the neighbouring stations — discarding the authored tangents
  (`station_axis`, the R-key bend) the road is actually swept from. At an open end that chord sat
  **70°** off the true heading: measured **22.57 m** of error on the addon's own sample network,
  with a green gate and perfect geometry. Handles now come from the lane's own sampled tangent,
  length least-squares-fitted, subdividing only where a cubic cannot follow to 0.05 m → **0.09 m**
  worst, with *fewer* control points. Two rules fell out and both are load-bearing: the fit error
  must be measured **curve-to-lane**, not lane-to-curve (a cubic that bulges wide and comes back
  passes near every sample while sitting a lane's width off the road), and the split must
  **bisect** (splitting at the worst sample slivers a span whose real problem is a bad handle).
- **`Preview ▸ Geometry` draws the Path3D by default**, not the lane polyline — the two are
  different objects, and drawing the wrong one is how the above survived. `Both` overlays them with
  orange rungs where they part; `path_deviation` is the matching gate finding, from the same
  function, so picture and finding cannot disagree.
- **One material registry.** `point_build`'s parallel `rka_*` materials are gone; roads now use
  `kit_common.MATS` like every other builder — which had carried `M_LineW`/`M_LineY`, described in
  its own source as lane lines, with **no user at all**. `RoadData` gained a style slot per layer
  (a datablock NAME, so `.roads.json` round-trips; blank = default; a missing name falls back AND
  warns), `median_style` moved from the point to the road as an enum
  (`NONE`/`PAINT_DOUBLE_Y`/`RAISED`/`WALL`), and **lane markings are built at last** from
  `lane_profile.marking_runs`, which had computed every painted boundary since the profile model
  landed and which nothing had ever swept. Dashes are cut in Python (the addon's own rule: Python
  owns the curve, GN only sweeps); paint is lifted `PAINT_Z_BIAS` and is deliberately **not** in
  the collision proxies.
- **A profile asset replaces a layer's parametric band with a swept section the artist modelled**
  (`GN_PointProfile`, `point_style`, `assets/world_source/kits/road_kit/road_kit.blend` via
  `tools/build_road_kit.py`, library-linked). SWEPT, never tiled — rigid pieces round a 9 m corner
  sit ~12.7° apart and open a real ~7.8 cm gap at every joint, which is what retired the previous
  model's asset style; tiling is for lamp posts, and that is `GN_PointAssets`. Three measured
  gotchas: `Curve to Mesh` **drops the profile's materials** (zero slots, even from a two-material
  section — so the addon reads it off the asset), `obj.bound_box` is **stale on a freshly linked
  object** (reported a 0.32 m kerb as 2.32 m — read the curve data), and an asset layer has no
  `WidthAttr` so it **bypassed `layer_has_content`** until `ASSET_REQUIRE` gave it the same gate
  (a named barrier was building along an at-grade pedestrian street).
- **The `JCT_*` Empty is a handle and now sits where the junction is.** It was written once at
  `Make Intersection` and never re-derived, while `JunctionSolve.centre` recomputes the same
  centroid every solve — two owners, one frozen: dragging one mouth 42 m left the grip **10.44 m**
  off, so G and R pivoted on a point with nothing there (and `Auto Setback`, which moves every
  unlocked mouth, caused it immediately). It now follows the centre at Build, at Auto Setback and
  on live settle, moving no mouth. Z rotation is **unlocked** (scale and out-of-plane rotation stay
  locked, which is what the original lock was actually right about) so a whole crossing can be
  turned; `stamp_baseline` moved to the point's **parent frame** so that gesture promotes **0**
  arms to MANUAL instead of all of them, while a hand rotation of one arm still promotes exactly
  that one.

**One owner per derived fact — the four rules the 2026-08-25 fixes added** (`ROAD_POINT_GRAPH.md`
§8f has the full write-up; each of these was a user report):

- **Direction has ONE owner: `point_model.station_axis`.** The carriageway honoured a MANUAL
  tangent while `point_solve.mouth_axis` and `point_validate._axis` each re-derived the direction
  from the *neighbour's position* — so rotating an intersection mouth bent its street and left the
  pad exactly where it was. Both now delegate. Rotating a mouth turns its cap, its two fillets and
  its turn paths.
- **A pad always tessellates.** `point_solve.pad_triangles` fans from the ring's **kernel point**
  (`fan_origin`, found by pushing the apex inside the edges it is outside of) and `ear_clip`s when
  no kernel exists; `build_pad` sweeps exactly that. `pad_not_star_shaped` is a **WARN**, not an
  ERROR — a 2 cm fold from a hand-drag used to refuse the whole build and name as its remedy an
  `Auto Setback` that then reported "moved 0". Never let a hand-drag be a build failure.
- **A ramp is the aux slot's CONTINUATION, not a lane beyond it.** `point_profile.aux_edge_offset`
  returns the aux slot's **through-lane-side** edge (the gore line), so `lanes_fwd = 3,
  aux_fwd = 1` is a four-lane carriageway whose outermost lane leaves. `point_solve.ramp_target`
  is the single owner of where the mouth belongs — and `Align Ramp To Aux` also **faces** it down
  the mainline (`MANUAL`), because two bands cut on different planes touch at one vertex and open
  from the next. Divergence is authored at the ramp's *next* point. `solve_gore` paves the wedge
  between the two roads' own paved edges, from where the signed gap changes sign to a 4 m nose.
  `check_tapers` exempts the station that owns the `AUX` link: a **departing** lane is not a
  **merging** lane and needs no merge taper.
- **Reachability is not geometry, and had no eye.** An `AUX` link exported as *nothing*: the ramp
  lane had no predecessor, so no ambient car could ever reach a ramp anywhere in the world, with a
  green gate and perfect geometry. `point_export.wire_ramps` emits the edge (directed by the ramp
  point's role) and `_aux_handoffs` **ends the exit lane at its gore** so the successor is within
  `CHAIN_TOL`. `point_preview` (the **Preview** panel) draws the *exported* lane graph — directed
  lanes, `next` edges, agents walking it on the exported weights — and reports `broken` /
  `open_end` / `unreached` / `ramp_orphans`. When adding anything to the lane graph, check it
  there: a build being green says nothing about whether traffic can get to it.

**Five more owners, from the 2026-08-26 follow-up** (`ROAD_POINT_GRAPH.md` §8g; same shape as §8f
— a rule right for the case in front of you, applied to one nobody had looked at):

- **An exit is a BLOCK of aux slots, not one slot.** `point_profile.aux_block` returns the whole
  run of same-direction aux slots and the edge facing the through lanes; `aux_edge_offset` is that
  edge. Anchoring on the *outermost* slot was right at `aux_fwd = 1` and put a two-lane ramp half
  on the carriageway at `aux_fwd = 2`.
- **The merge taper is the metric standard × the road's `taper_factor`.** `TAPER_LINEAR_ABOVE` is
  70 km/h (it was 60, which over-demanded by half across the whole 60–70 band). `taper_factor`
  (`ROAD_FIELDS`, default 1.0) exists because **the world is not 1:1** — shortening a taper for a
  compressed map is a visible authored decision on the road, never a constant bent in the checker.
- **A barrier's HEIGHT is authored, its PLACEMENT is derived.** `RoadData.barrier_height` (0 =
  none) × the rule in `solve_road`: fenced along the whole length when `ped_access` is off, and
  only where `delta >= BARRIER_MIN_DELTA` when it is on. It is a layer in `edge_spec()` on the same
  `deck` node group as the kerb, so it rides the **outline** — which is why it opens across a gore
  and closes past the nose with no ramp-specific code at all.
- **A junction corner IS an edge run.** `point_solve.junction_corners` emits one `Corner` per real
  corner from `intersection_kit.build_junction_curb_segments` (the same curve the pad boundary is
  rounded with) and `point_build.build_junction_edges` sweeps it with the ordinary `edge_spec()`.
  Before this, every crossing in the world had four missing pavement corners.
- **`point_edges.Band.carries_edge` — a pad hands the furniture on, a gore does not.** A run must
  not suppress its kerb against a footprint that continues it (that gap was the missing corner
  pavement), but it MUST open across one that does not. A run is a member of both, so membership
  alone cannot tell them apart; keying on it left a barrier stub standing across the gore paint.
- **`intersection_kit.curb_edges(..., tail_length=)` anchors each arm's kerb ray on that arm's own
  `tail_center`, not the origin** (§8h). The origin-anchored ray passes through the cap only
  because a plain arm's tail centre is a multiple of its direction — an off-ray `tail_pos` (which
  is what `_PadArm` sets from the AUTHORED mouth) does not satisfy that, so a **rotated** mouth's
  corner left the cap ~50° out and its footway met the street in a notch. Opt-in by parameter, and
  byte-identical for any arm without `tail_pos`; `Arm.tail_center`'s docstring records the opposite
  scope limit, which was right for the model that wrote it and wrong for this one.
- **`point_edges.covered(..., outward=)` is DIRECTIONAL: "does the pavement continue past this
  line", not "is there asphalt within 0.6 m".** Where a ramp leaves along the mainline's outer
  edge, both edges are the outer boundary of the same pavement, and the undirected `NEAR_PAD` slop
  had each band suppress the OTHER's parapet — 11 m of unwalled edge at the top of a 14 m drop.
  The probe is taken `NEAR_PAD` **outboard** and must land strictly inside another band.
  `measure_on_asphalt` uses the same tolerance for the same reason: it measures standing ON asphalt.
- **A directional `covered` asks TWO questions, and a run's END is CLIPPED, not rounded (§8h.4).**
  Two user reports, opposite ends of one ramp, one root cause — start/end decided per 4 m sample
  about features metres across. (a) The outboard probe can step clean OVER a band narrower than
  `NEAR_PAD`: at a mouth the mainline's outer edge lies 0.5 m inside the ramp's band, the probe
  landed 3 cm past it, and both parallel edges kept a wall — "one extra wall at the ramp
  connection". So `covered` now also suppresses when the point ITSELF is `BURIED_TOL` (5 cm) inside
  another band. That is a tolerance for *exactly on*, not a margin — an edge on another band's
  boundary is the shared outer boundary and keeps its wall, which is §8h.2's case. (b)
  `point_edges.open_runs` returns `Run(i0, i1, head, tail)` — still `(i0, i1)` when indexed — whose
  `head`/`tail` are **bisected onto the covering band's boundary** (`_clip_end`), so a run ends at
  the mouth it hands over at and starts at the gore nose it must meet, instead of a sample either
  side. `sub_polyline` + `pe.run_values` emit points and attributes from one place so they cannot
  come out different lengths. Together these let the gore cap sit FLUSH on the strip's last pair
  (`GoreSolve.nose`) with both flank walls meeting it — three walls, one closed corner.
- **A GORE OWNS ITS OWN NOSE — neither flanking road can (§8h.3).** A gore is bare paint
  (`Band.carries_edge` False), so both flanking walls open across it: right along the join, where a
  wall would stand in the exit lane, and wrong at the wide end, where the two roads have parted and
  their walls restart `GORE_NOSE_WIDTH` apart with an open V between them at the tip of a viaduct.
  Neither road can fill it — the stretch is the other one's asphalt — so `point_solve._gore_nose`
  emits an ordinary `Corner` and `point_build.build_gore_edges` sweeps it with the ordinary
  `edge_spec()` (`GORE_*__edges_nose`). **What** it carries is still the roads': each end reads that
  road's own solved `rka_wall_h`/`rka_curb_h*`/`rka_walk_h*` and the run blends between them, so a
  fenced highway meeting a fenced ramp is a wall, an approach declaring a footway gets a kerbed
  island, and a pair declaring neither builds nothing. `GoreSolve.ped_access` is both flanks'
  answer, so the proxy is `-noped` between an expressway and its ramp and walkable between two
  streets. **Where** it sits is derived: one `GORE_STEP` past the nose on each road's own edge — the
  first sample outside the gore's polygon, i.e. exactly where `open_runs` lets that flank's wall
  resume. `point_build.edge_run_values`/`build_edge_run` are now the one owner of the per-vertex
  furniture arithmetic, shared by a road flank, a junction corner and this.

**And the gesture round, 2026-08-26** (`ROAD_POINT_GRAPH.md` §8i; six user reports). §8f–§8h were
all *one fact with two owners*; §8i is the other face — **a fact the artist was made to declare
that the model already knew**, or **an ordering the tool imposed because nobody had asked the
question from the other side**:

- **`Extend Road` works from EITHER end.** `_next_point_name` only ever hands out the next free
  index, so a new point was always born at the *tail* of the names however the artist got there:
  extending `..._p000` misfiled it at the far end of a road it starts, and (the head has no `prev`
  to take a chord from, so it fell back to its own `+Y` = the way the road already runs) placed it
  *forward*, back down the road. `chain_unlinked` on an untouched pair, on the next Build. Now the
  head grows away from the chain and `_renumber(..., at=0)` prepends; an interior point is refused
  by name.
- **Which point is the MAINLINE is a fact, not click order** (`point_ops.resolve_aux_pair`). `AUX`
  stays directed (mainline → ramp) but the gesture works from either end — an entrance ramp reads
  "ramp joins road", and insisting the mainline be active made every merge unauthorable with the
  button the panel offers. `Make Ramp` shares the resolution.
- **ONE ramp role.** `RAMP_ENTRY`/`RAMP_EXIT` fed exactly one decision (which way
  `point_export.wire_ramps` points the lane edge) while `point_solve` derived the same thing from
  the chain — and when the two disagreed the geometry was perfect, the gate green, and the traffic
  wired backwards. `point_model.ramp_is_entrance` is the one owner: the mouth's position in its own
  **run** plus which way the ramp's lanes run (`lanes_bwd = 1, lanes_fwd = 0` is ordinary, and its
  head is where cars come *out*). `road_runs` moved to `point_model` for this (a run is a fact about
  the chain and its links); `point_solve.road_runs` is an alias. The ramp edge is now **added to**
  the junction connectors rather than dropped when a lane has both — §8f.4's orphan again.
- **The taper is PER CARRIAGEWAY and only WITHIN a run.** Summing both sides doubled the demand
  (336 m where the standard asks 168) on the theory that two opposite lane drops compound; they do
  not — a merge is one driver on one side of the divide, so the demand is the *wider* of the two
  changes. And walking the chain pairwise measured a taper straight across a junction gap, where the
  pad joins the mouths and no carriageway exists. `taper_factor` is unchanged (1.0 is the book) but
  the finding now names the factor that would pass.
- **A gore's nose carries the RAMP's section, uniformly** — not a blend of the two flanks (§8h.3's
  blend was right only while both roads declared the same *kind* of furniture; a fenced ramp leaving
  a kerbed street gave a wall of falling height standing in a widening footway). The mainline's kerb
  and footway run on past it unbroken. The mainline's values are the fallback only when the ramp
  declares nothing at all.
- **A Blender `EnumProperty` is stored by ORDINAL, not identifier** — introduced and caught in this
  same round. Inserting `RAMP` into the middle of `ROLES` re-read every saved role in every `.blend`
  (`RAMP_EXIT` → `RAMP_ENTRY`) with nothing to see in any diff. **The enum tuples in `point_model`
  are append-only**; `_enum_items` emits the 5-tuple form so the numbers are written down.
- **`Author ▸ Corridor ▸ Split To New Road`** is the repair when a stretch lands in the wrong road
  (a ramp grown with `Extend Road` off its mainline). Links are object pointers, so the `AUX` link
  survives the move. `chain_unlinked` is a **WARN** now, not an ERROR: `road_runs` already builds a
  split chain correctly. The real defect — a point joined to nothing — arrives under its own name,
  `point_stranded`.
- **`Author ▸ Repair ▸ Tidy Roads`** does the same filing with **no selection**, from the links
  alone: a point whose `SEGMENT` links all land in one *other* collection moves there (placed next
  to the neighbour it joins — appending would repeat §8i.1's defect), and a collection holding more
  than one **corridor** splits. A *corridor* is not a *run*: `point_model.road_corridors` breaks
  only where two chain-adjacent points carry neither a `SEGMENT` nor a `JUNCTION` link, because a
  crossing does not split a street — `road_runs` breaks at the junction gap too, since a lane must
  not be swept across a pad. One owner, shared with `check_chains`. A split-out corridor something
  `AUX`-links into is named `<road>_ramp`.
- **`Author ▸ Repair ▸ Repair Links` now exists.** The gate had named it as the remedy since step 1
  (`uid_duplicate`: "run Repair Links") and it had never been built. It **drops** what cannot be
  honoured (a `None`/self/non-point/no-road target, a duplicate row — a pair carries at most ONE
  link) and the ramp's half of an `AUX` pair; **restores** the missing half of a `SEGMENT`/
  `JUNCTION` link and completes a junction component into its clique; and **writes back** the uid
  `read_network`'s `dedupe_uids` re-allocates, which nothing had ever persisted (so the warning
  could not be cleared). Type conflict between the two rows of a pair: `AUX` > `JUNCTION` >
  `SEGMENT`.
- **A finding must name an object in the MESSAGE, not just the subject.** Rule 5 was half-kept:
  `Validate` translated `Finding.obj` but not the body, where most uids are ("is chain-adjacent to
  `p_862c8815`", "move `p_5dd247b1` further away"), and `Build`/`Export` translated neither.
  `point_validate.describe(finding, labels)` is the one owner (regex over `p_` + 8 hex);
  `point_model.point_labels()` supplies `{uid: "<road>/<object>"}`.
- **`Add Sample Network` is authored BY THE GESTURES now**, not by the internal helpers. As a
  data-model fixture it could be perfect while `Extend Road` grew roads backwards and `Make Ramp`
  refused half the ramps in the world — the smoketest pressed the button and covered neither. It
  now contains the arrangements that were broken (a head extension, aux lanes on *both*
  carriageways over one span, one ramp that is an exit at one end and an entrance at the other,
  and a fenced-ramp-to-kerbed-street gore), so it is evidence rather than illustration; under the
  old taper rule it would be red. `is_loop` is the one shape it does not carry yet.
- **A junction arm offers only the lanes that exist AT THE STOP LINE** (`point_export._arm_lanes`)
  — a pre-existing bug the new sample surfaced. `lane_movements.target_lane` preserves distance
  from the **kerb**, and an arm was offering every lane of its run including one that opens 200 m
  past the stop line and is zero width there: both approach lanes shifted one outboard, the
  straight-ahead movement fed a lane that is not there yet, and the exit's **median** lane came
  out with no predecessor — at every junction whose exit arm has an aux lane in the same run.
  Which end is zero decides it, so it is asked per end; `spawnable` is the same fact from one side
  and is NOT the test. Found by `Preview ▸ Flow Report`, which the smoketest now asserts is clean
  on the sample.
- **Object names are GLOBAL — renumber the DESTINATION first when points move between
  collections.** `_renumber`'s two passes only protect against collisions *within* one collection;
  a point that has left but not yet been renamed still holds `<src>_pNNN`, so renumbering the
  source first gets `main_p000.001` back from Blender — a point whose name sorts outside its own
  chain, which is the one thing the name order has to guarantee. Asserted in the coverage
  smoketest (no `.` in any point name).

**And the duplicate-and-branch round, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8j; four user reports
about authoring a *second* ramp). Every one was a derived fact resolved through a proxy that is
usually right — a **uid** where the ground truth is an **object**, or the **walk direction** where
the ground truth is the **road** — and every one failed by returning a plausible number rather than
an error:

- **Membership is read off the OBJECT; links resolve by OBJECT IDENTITY.** Duplicating a road
  collection gave every copy the original's uid, so `dedupe_uids` dropped the copy's own internal
  wiring (right for Shift+D on one Empty, wrong for a whole road) and `read_network`'s
  `{old_uid: new_uid}` remap — only a function while uids are unique, which is exactly what they
  are not at that moment — rewrote **both** roads' point lists, leaving the ORIGINAL orphaned.
  `point_model.relink_from_objects` keeps a link row that stays inside the re-allocated set (the
  copy's own wiring) and drops one that leaves it (a clone's inherited connectivity); a link to an
  object in no road collection is dropped, not resolved by uid onto whoever shares it. `net.labels`
  comes from the same read so §8i.10's rule survives the dedupe.
- **`Author ▸ Ramp ▸ Branch Ramp Here`** is the gesture for a ramp that starts mid-corridor.
  `Extend Road` refuses an interior station and is right to, but the thing the artist was doing had
  no gesture at all. It opens the aux slot back to the first span long enough to hold the taper
  `check_tapers` asks for (an aux count is an integer, so the slot goes zero-to-full across exactly
  ONE span — opening it on more stations moves which span the change lands on, never lengthens it),
  places and faces the mouth via `Align Ramp To Aux`, bends the second station **outboard**, and
  leaves the far end active.
- **Outboard is a fact about the road, not about the walk.** `point_solve._signed_gap` took its
  normal off the chord it was walking, so the upstream reading was the downstream one sign-flipped:
  "which way do the bands part" picked upstream unconditionally, the two edges were paired running
  opposite ways in world space, and the gore's nose cap came out **22 m long, laid across the
  merge** — with a green gate, zero residual and zero angle. It now takes a `sense`. The same fix
  ended the arterial footway that was built across the ramp mouth: `open_runs` opens a kerb across
  whatever the gore actually covers.
- **A ramp that bends back ACROSS the road it leaves had no eye on it.** Both ramp checks measure
  the mouth, and `Align Ramp To Aux` sets both, so a ramp that leaves correctly and then drives
  through the carriageway passed the whole gate with no gore built and nothing said.
  `ramp_divergence` measures the station *after* the mouth; `ramp_wrong_side` (ERROR) /
  `ramp_parallel` (WARN). The sample network's own exit ramp was authored that way.
- **`ramp_frame_sign` is the product of TWO signs**: which carriageway the aux slot is on
  (`aux_fwd` vs `aux_bwd` — traffic through a reverse slot runs against the station axis) and which
  way the ramp's own lanes run. Three places derived it and all three assumed +1, so a
  reverse-carriageway ramp was faced, placed and edged as a forward one — a two-lane entrance came
  out as a 600 m hairpin with a 38 m wall down the middle. `Make Ramp` also stopped writing
  `aux_fwd` unconditionally: `ramp_carriageway` reads it off which side the mouth is on.
- **One aux slot, one ramp, per run.** `point_profile.aux_slot_ids` is the one owner of which lanes
  leave (`_aux_handoffs` was still handing over the outermost slot only, so a 2-lane ramp's inner
  lane had no predecessor — §8g.1 one level up). The structural half is reported, not fixed: a run
  exports ONE lane per slot, so two ramps on one run — or one station wired to two ramps, where a
  duplicated ramp collection lands — both claim `AF0` and one is reachable by no car.
  `check_aux_slots` (ERROR) names both and the two ways out: the other carriageway, or a run break.

**The diverge/merge round, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8k). Two ramps hanging off ONE
mainline station — a two-lane exit that splits, two ramps merging back into one two-lane slot — is
the ordinary shape of an interchange, and §8j.6 had just declared it an error. That was right about
the *run* and wrong about the *station*: a station's aux block is several slots, and what was
missing was which of them is THIS ramp's.

- **`point_solve.aux_allocation` divides a station's aux block among its ramps**, each taking as
  many slots as it declares lanes. Order is derived from where the artist put the mouths (nearest
  the through lanes takes the innermost slot) — not click order (§8i.2) and not uid order, which is
  invisible and would reshuffle a network on a rename. `aux_gore_offset` replaces "the block's gore
  line" everywhere, and `wire_ramps` hands each ramp only its own aux lanes. `aux_slot_shared` is
  narrowed to the same slot claimed twice IN ONE RUN; over-subscription is its own finding.
- **A gore is against the neighbour on the INBOARD side, which is not always the mainline.** The
  outer ramp's is the INNER RAMP; measured against the mainline its wedge is struck across the
  inner ramp's asphalt. `inboard_neighbour` chooses it and reads that road's outboard edge with its
  own `ramp_frame_sign`.
- **Two boundaries pair by PROJECTION, never by index** (`_project_signed`). Equal-arclength walks
  assume both advance together; two sibling ramps do not, so by 90 m the samples lag six metres and
  the perpendicular offset was measured against a point that is not opposite. Two ramps with a real
  5 m hole between them read as a gap of zero and no gore was paved.
- **Which carriageway a ramp is on is a fact about where its mouth is** (`ramp_carriageway`).
  `Make Ramp` wrote `aux_fwd` unconditionally, putting a westbound ramp's slot on the eastbound
  carriageway.
- **"Does this lane exist at the stop line" is asked of the WIDTHS, not of the receiver.**
  `merge_into`/`opens_from` are both None when `lane_taper_route` cannot resolve a receiver —
  indistinguishable from a full-length lane. Declaring `aux_bwd` on the arterial was enough to make
  the junction arm offer the forward aux lane, shift every straight movement one lane outboard, and
  leave an ordinary through lane reachable by nothing (§8i.13 again, from the other side).
  `LaneRoute.i0`/`i1` are the question actually being asked.

**One ramp out and one ramp in at one station, 2026-08-27** (`ROAD_POINT_GRAPH.md` §8l) — the
ordinary half-interchange, and what `Add Sample Network` now carries (the westbound ramp two lanes
wide, plus a spur branched mid-corridor). Four things were in the way:

- **`aux_block` answered "forward" for a reverse ramp.** A station handing a ramp to each
  carriageway declares `aux_fwd` AND `aux_bwd`, and the case-free "most slots, ties to FWD" reading
  then put the reverse ramp's mouth on the forward gore line. `aux_block(profile, direction)` takes
  the side when the caller knows it, and `point_solve.ramp_side_of` knows it — §8j.4's rule asked
  per RAMP instead of per station. `aux_allocation` allocates each carriageway separately,
  `inboard_neighbour` only pairs same-side siblings, and `check_aux_slots` no longer reads one ramp
  on each side as a collision (`AF*`/`AR*` ids keep them apart by construction).
- **An entrance's lane was cut off the wrong end.** `_aux_handoffs` ends an aux lane at its gore
  because *an exit lane has left with the ramp*; applied to an entrance it handed the merging ramp
  the stretch of slot UPSTREAM of the merge — a successor whose head was 600 m back down the road.
  An entrance's lane is the acceleration lane and BEGINS at the gore.
- **Nothing could see that, because every check asked whether an edge EXISTS.** `broken` is no
  successor, `unreached` no predecessor, `ramp_orphans` nothing leads to a ramp — a successor
  pointing the wrong way is healthy by all three. `flow_report` now also reports **`misjoined`**: a
  successor whose head is not where this lane's tail is (`merge` edges exempt — a taper hand-over is
  lateral and its target spans the run).
- **`unreached` stopped reporting non-`spawnable` lanes.** A deceleration lane that opens after a
  junction is supposed to have no predecessor: it is entered by a lane change, and a lane-change
  edge is `inner_lane`/`outer_lane`, not `next`. It keeps its bite where it matters — a full-width
  through lane is spawnable, which is §8k.5's case.

**NAME ORDER IS CHAIN ORDER, AND A HAND EDIT CAN BREAK IT** (2026-08-31, `ROAD_POINT_GRAPH.md`
§8m). `point_model.read_network` sorts a road's point objects **by name** and that order IS the
chain; the links are the separate, authored fact. A rename, a `Shift+D` or a point dragged between
collections therefore reorders the road silently — the build follows the links and is correct,
while the file no longer reads the way it behaves. `point_model.link_order` is the one owner of
"what order do the links put these in" (idempotent on a correct road, and it leaves a **branching**
stretch alone rather than inventing an order for it); `Author ▸ Repair ▸ Renumber Roads` renames to
match — links are authored, a name is derived, so the name is what is wrong — and
`chain_out_of_order` / `chain_branched` are the WARNs that say so. Two gestures came with it:
**`Merge Points`** (a contiguous run of ONE road collapses to one station; the first survives with
its uid and section, outward links carried over — points in *different* roads are a junction, not a
merge) and **`Insert Point` from a single selection** (splits the span after it; `_next_in_chain`
derives the neighbour from the link AND the order, since either alone is ambiguous).

**A RUN'S END IS NOT A ROAD'S END, AND A PAD IS SIZED BY THE WHOLE SECTION** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8o, `WORLD_REBUILD_PLAN.md` `W16`). Two junction defects, both of them the
footway reaching a solve that had never been asked for it. (1) `road_points.chain_tangents` is
handed a RUN, and a run stops at a junction mouth, so its end tangent falls back to the one
available chord — right for a road that ends, wrong for a mouth, where the road carries on across
the pad and the cap is cut on `point_model.station_axis`. They agree only while a road runs
straight through a crossing: at a 12.2 deg bend the street's kerb line finished **2.23 m** off the
pad corner it must meet. `point_profile.run_end_axes` gives the two end stations the chain's
direction (keeping their own Z slope, so a graded approach does not kink) and the sweep, the export
and the overlay all take it. (2) `point_solve.corner_setback` passed the CARRIAGEWAY half-width to
`corner_clearance`, whose own docstring quotes the DECK half — indistinguishable while every
footway was 0 m wide, and the day one was not, every pad was sized for a 21 m road that is 29 m
wide, leaving corners whose cap points are 3.31 m apart for a kerb that has to turn 95 deg through
them. **A number derived from a section must be derived from the whole section:** while a layer is
optional and zero everywhere, every consumer standing for "the road's width" holds a value that
merely happens to be right.

**A CONSISTENCY CHECK CANNOT SEE A FACT THAT WAS NEVER WRITTEN DOWN** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8n, `WORLD_REBUILD_PLAN.md` `W14`). Every gate check reads the authored
graph and asks whether it is consistent, which is blind to a junction that was never authored at
all: two roads whose end stations sit at the identical position with no link between them have no
link to be asymmetric, no chain with a hole and no clique to be incomplete, so an 839 m road can
be an unreachable component of the island with the gate reading 0/0. The cause was
`seed_district_roads.seg_intersect` testing `0.0 <= t <= 1.0` on a crossing that lands on a shared
VERTEX — the plan's own rule is that an arterial terminates on another arterial, and `resample`'s
float drift put `t` at `1.0000000006`, so **four of the island's sixteen crossings were dropped at
the ninth decimal place**. Bounds belong in **metres** (`TOUCH`, 5 cm), never in parameter space:
`t` and `u` are fractions of two segments of different lengths and one number cannot mean the same
thing to both. `point_validate.check_meetings` / `road_end_unjoined` is the eye — open ends only
(a ramp mouth stands beside its mainline by construction) and in **3D** (a street under a deck is
not a meeting).

**A STATION'S CROSS-SECTION COMES FROM THE ROAD, NOT THE STATION** (2026-09-04,
`WORLD_REBUILD_PLAN.md` `W3`). `point_model.resolve_point` gives an `INHERIT` station its road's
`base` and takes only the four `DELTA_FIELDS` (`lanes_fwd/bwd`, `aux_fwd/bwd`) from the point —
lane width, median, footway widths, kerb heights and design speed all come from `RoadData.base`.
So writing a footway width onto every point of a seeded road is writing it where nothing reads it:
`seed_district_roads` did exactly that, and **the island had no pavement at all** — `rka_walk_hl`
was 0.0 on every sample of every road, for as long as the point-graph seeder had existed, with a
green gate. A field being *per-point in the schema* does not make the point its owner; only
`profile_mode = OVERRIDE` does. The barrier needed nothing: `point_solve.solve_road` derives it
(fenced end to end where `ped_access` is off, and where `delta >= BARRIER_MIN_DELTA` or on piers
where it is on) and the missing footway had only left it standing on the kerb line instead of at
the pavement's outboard edge.

**A MOUTH SLIDES ALONG ITS OWN ROAD, AND THE SEEDER MUST NOT GUESS HOW FAR** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8p, `WORLD_REBUILD_PLAN.md` `W18`). Two owners of "where is the stop line":
`seed_district_roads` placed every junction mouth at a provisional **14 m** and pruned the stations
inside `14 + MIN_SPAN` of the crossing; `bpy.ops.rka.auto_setback()` then solved the real distance
(**17.9–35.5 m** over the island's ten pads) and walked the mouth out over the top of a station
that had survived a window computed from the wrong number. `point_solve.solved_setback` is the one
owner now — a function of the ARMS alone, so `seed_district_roads.place_setbacks` can ask it with
planned arms before an Empty exists. Nothing could see the result: two stations with the same
profile make `check_tapers` return on `dw == 0` and `station_coincident` only fires at 1e-6, so the
island shipped an ordinary station **0.19 m** past a mouth with a green gate —
`point_validate.check_mouth_clearance` / `station_crowds_mouth` is that eye. And `auto_setback`
placed each mouth on a ray from the pad CENTROID, which is on none of the roads: identical to the
crossing on a symmetric X (which is why it was invisible), **12 m** off it on a 5-arm pad, enough
to leave one approach 40° from its own alignment and 3.54° from the next arm — two carriageways
leaving on top of each other. The centre is projected onto each mouth's own axis first, so a mouth
can only slide along its road.

**`Auto Setback` IS IDEMPOTENT NOW, AND THE DISTANCE COMES FROM THE ARMS ALONE** (2026-09-17,
`W17` closed). It moved 17 of 35 island mouths on a second press, and on DebugRoads 52, 34, 43, 84
and 69 m on five presses, the fifth turning an AUTO arm round. Three inputs moved with the mouths:
- **The search start.** `recommended_tail_length` grows ×1.3 from `start`, and its overshoot is not
  monotone, so the start is part of the answer (DebugRoads' east pad: 42.4 m from 5, 57.9 from 12,
  50.7 from 30). `auto_setback` passed the widest mouth, so each press fed the next. And
  `solved_setback`'s default was `start=0.0`, and `0 × 1.3` never grows, so the seeder only ever got the
  corner term and never ran the turn search. The default is `None` now, the search's own 12 m, for
  every caller. **Consequence: an unlocked mouth further out than the solve comes IN**
  (RoadKitSample's provisional 14 m mouths go to 12). The override is `setback_locked`, which the
  setback handle and a mouth drag already set.
- **The centre.** The mouths' centroid moves when a mouth slides. `point_solve.axis_crossing` is the
  least-squares point nearest every mouth's axis LINE, which a slide along that line does not move.
- **An AUTO axis is a chord through the opposite mouth across the pad**, so the passes repeat to a
  fixed point (`SETBACK_SETTLE_TOL` 1e-5 m; DebugRoads settles in 3 passes).

A mouth is never slid over the station beyond it: it stops `point_validate.MIN_MOUTH_CLEAR` (10 m)
short along its axis. `auto_setback(clamped=)`, the CLI's `clamped` list and the dock message name it,
with the gate's remedy (delete the station or lock the mouth). Measured: DebugRoads settles on press 1
(58.6 m) and moves 0 on presses 2–4, and RoadKitSample the same (2.0 m, then 0). `point_solve`
self-test (21) builds a crossing whose two roads bend through it, with four AUTO mouths whose axes
pass metres from their centroid. On it, presses 2–4 move nothing, the seeder's number equals the
solved one, and a station 22 m out holds its mouth 10 m short. Controls: HEAD's `auto_setback` fails
"press 2 moved mouths", and the old single pass drifts 1.79, 0.99, 0.68 m on successive presses.
DebugRoads' committed record was not re-pressed: its authored east pad is still the shallow 4-arm one
that a press grows to 58 m.

**A GESTURE THAT HANDS OUT A `JUNCTION` LINK OWES THE WHOLE PAD** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8q, `WORLD_REBUILD_PLAN.md` `W19`). A pad is three facts written together —
the members form a **clique**, each is typed `INTERSECTION`, each hangs off the `JCT_*` handle — and
`point_ops.make_pad` was the only thing that had ever written them. `Merge Points` correctly carried
"every link that left the collapsed run" onto the survivor and stopped there, so merging a plain
station into a crossing (the plain station is `doomed[0]`, so it survives) left the pad a
**component, not a clique**, with mouths still typed `SEGMENT` and unparented — 8 gate errors from
one gesture, and `Auto Setback` then solving a clique that is not one.
`point_ops.complete_junction_cliques` is the shared owner; `Repair Links` recovers a file already
broken by it. A merge smoketest that only merges **interior** stations cannot see this.

**`resample` NEEDS AN OPPOSITE NUMBER** (same round). It lays a station every `spacing` metres so a
road has stations where it needs them; on the straight legs between two authored plan vertices those
are exactly collinear and cost geometry, build time and a lane control point each for nothing.
`seed_district_roads.simplify` is **Douglas-Peucker** over the 3D polyline — never a pairwise
"is this station between its neighbours" walk, which measures each candidate against a line that
already reflects previous removals and lets a shallow curve walk off by many times the tolerance one
legal step at a time. Run twice and unioned: against the ROAD at `STATION_MERGE_TOL` (0.25 m) and
against the GROUND at `GROUND_MERGE_TOL` (1.0 m, looser because a station's `ground_z` is what
`road_support` sizes its piers from — a straight deck over a bay must not collapse to its two shore
stations). Junction mouths are protected outright: a stop line is not a shape. Measured on the
island: **433 → 184 stations** for **+0.02 m** of drape error (worst at-grade road-to-ground gap
0.32 → 0.34 m, against a 0.35 m `MovementController.stepUpLedge`).

**A CORNER IS A BEND STATION, AND ONLY THE JOINT HAS TO MOVE** (2026-09-04,
`ROAD_POINT_GRAPH.md` §8r, `WORLD_REBUILD_PLAN.md` `W15`). **A run never spans two road
collections** (`point_solve.road_runs` walks one road's own points), so two plan arterials meeting
end-to-end each sweep their own carriageway to the joint at their OWN heading — sections cut on
planes 98–124° apart agree nowhere, and the island's three corners ended **24–28 m apart** with a
SEGMENT link across the hole. Rounding the corner and using a bend station are the same answer:
`seed_district_roads.fillet_corner` trims both chains by the tangent length, lays an arc of
`CORNER_RADIUS_FACTOR` (3.0) × the **deck** half-width (43.5 m on a T2 — derived from the section
per `W16`, clamped by `CORNER_MAX_CHAIN_FRACTION` when the road is too short), and **splits it at
its midpoint** so each road carries half the turn and they meet **tangentially** — the
straight-through joint the seeder already built correctly, with each street keeping its name and
every lane id. A 2-arm pad is refused by the model; merging the two roads costs a street its
identity. Measured: gap **25.6 → 0.00 m**, deflection **106/124/98° → ~7°** (one arc step).
**The geometry meeting is not the graph chaining:** the fix moved the flow verdict from `open_end`
to **`broken`** (a tail on a head with no edge), and `point_export.wire_joints` emits the
hand-over — matched by geometry, not lane index — taking `broken` to 0. The runtime's
`LaneGraph` proximity fallback would have hidden it, which is exactly why it is exported.

**A PAD IS A PLANE AND THE GROUND UNDER IT IS NOT** (2026-09-05, `ROAD_POINT_GRAPH.md` §8s,
`WORLD_REBUILD_PLAN.md` `W20`/`W21`). `point_solve._idw_z` interpolates a junction's surface from
its mouths so a pad meets every approach at that approach's own elevation — right, and it stops a
junction on a grade from stepping — but between the mouths the ground goes on doing whatever it
does, and where it rises inside the footprint the pad is **under** it. **The collider is why that
matters:** `point_build.cut_ground` punches a vertical prism through the terrain over every band
including the pad, so the burial is invisible, but `Ground-colonly` is deliberately in a collection
the cut does **not** recognise (continuous collision under the island is the base layer's whole
job), so the player walks on ground the eye says is not there. Measured at the port crossing, four
arterials on ground falling 2.09 m across the pad: **0.924 m** of ground proud of the pad, against
a 0.35 m `stepUpLedge`. `seed_district_roads.pad_lifts` probes the footprint on a 2 m grid and
raises **every mouth by one uniform offset** (`_idw_z` is linear in the mouth heights, so one pass
is exact and the pad keeps its tilt), applied as a **floor before the grade cone**
(`height_profile(..., floors=)`) so the approaches ramp instead of stepping and `road_support`
grows the embankment for free. `PAD_BURY_TOL` (5 cm — `point_edges.BURIED_TOL`'s "exactly on"
idea, not a margin) keeps it off flat pads, whose raw burial measures 0.000000–0.000122 m against
the slope's 0.924. **Still open (`W21`): the terrain collider is never cut**, so ANY road surface
below the ground is unreachable — `W20` fixed the one place it happened, not the class.

**THE ROAD DEFORMS THE GROUND; IT DOES NOT CUT IT** (2026-09-06, `ROAD_POINT_GRAPH.md` §8v,
`WORLD_REBUILD_PLAN.md` `W13`/`W21` — both closed). The boolean cut is **deleted**
(`point_build.cut_ground`, `clear_cuts`, `_cut_tube`, `_cut_section`, `_outward_offsets`,
`_self_intersects`, the `Cut Ground` build option and the exporter's cutter-hiding workaround).
Four rounds of fixing it each found a real defect — a zero-thickness cutter that had never cut
anything (`W22`); a sampler reading the terrain the PREVIOUS build had cut, so 29 of the touge's 66
stations found no ground and were never cut again; a switchback's cutter passing through itself,
which an exact solver answers by leaving the ground standing, silently — and the measurement that
settled it is that **from identical inputs (same network, same terrain, same sampled `ground_z`
byte for byte) a second Build took the touge from 2 buried stations to 9.** That is the tool, not
the road. It was also never the industry approach: terrain is a **heightfield**, a heightfield has
no topology to cut, and from Unreal's `Deform Landscape to Splines` to a Houdini road HDA the
operation is to write the road's elevation INTO the field — where the collision IS that field, so
visual and collider cannot disagree. (Manual cut-and-stitch is real but narrow: terrain holes plus
a hand-modelled piece, for what a 2.5D field cannot express — tunnels, overhangs, an abutment into
a cliff.)

`island_v3_terrain.Carve` is the rule — `z = min(z, road_corridor_z)`, and **carve-only is
load-bearing**: `road_support` already owns FILL (NONE/FILL/PIER/CUT from `surface_z − ground_z`),
so rising ground would build the same embankment twice, and a rule that raises ground would **fill
the bay** under `W1`'s 18.20 m bridge. `min` needs no bridge case because it cannot raise ground.
Terrain owns the cut and its batter; `road_support` owns the fill and the piers — opposite signs of
one number. **One direction of derivation:** a road's profile is derived FROM the ground
(`bench_profile`/`grade_cone`/`height_profile`), so a `Carve` is a separate VIEW (`carved_field`)
handed only to the ground-MESH builder — `build_island_base` emits the ground **twice** (natural →
seed + solve → carved), alignment against the original terrain and terrain deformed to the finished
alignment, never back. **The verge is what makes a 12 m grid exact:** the flat shelf runs one full
`GROUND_CELL` past the pavement, so no triangle spanning the road can have a raised corner —
measured 1 185 377 samples, **0 proud / 0.000 m**, against 450 at 3.508 m with no verge; subdivision
was measured and rejected as the lever (12 m → 3 m moved the worst intrusion only 3.508 → 0.647 m,
still past the 0.35 m `stepUpLedge`, for 16× the vertices). **A hairpin needs no case** — the lower
leg wins where two legs overlap and each leg clears itself, which is the geometry that defeated the
boolean four times. Measured on the built island, 28 295 samples: ground proud of the road **2 of
225 at 3.20 m → 0 at 0.00 m** on the visual and **0 at 0.00 m on the collider**, `Ground` 30 577 →
**21 547** verts, **collider identical to the visual** (that is `W21` closed by construction), and
repeated Build stable. One trap it introduced, with an eye on it: a carved ground is not the
natural ground, and a second Build stamped "the ground meets the road here" onto **195 of 225**
stations (biggest 9.46 m) — `point_build.CARVED_FLAG` refuses that with a message, re-measured 0 of
225. `point_build.road_corridors` / `band_corridors` is the addon's whole remaining contribution:
the centreline and half-width of what it just built, the width read off the swept band.

**THE GROUND CUT HAD NEVER CUT ANYTHING** (2026-09-05, `ROAD_POINT_GRAPH.md` §8t,
`WORLD_REBUILD_PLAN.md` `W22`). `point_build.cut_ground` built its cutters with
`bmesh.ops.solidify(bm, geom=[face], thickness=…)` and got **no thickness at all** — measured across
all 32, `z_min == z_max == -40.00`, so every boolean was a no-op and the evaluated terrain came back
with exactly its base vertex count. It stayed invisible for as long as every road was draped ON the
ground (a road 0.16 m proud needs no cut to look right) and surfaced only where a road went *below*
it: the buried junction pad (`W20`) and the touge's slot (`W13`) are the same defect seen twice.
The solid is built explicitly now. Three rules came with it: **a road is cut as a TUBE, not one
lofted outline** (`band_of` walks left-edge-out/right-edge-back, so a switchback's outline
self-intersects and its single n-gon cap is geometry the exact boolean will not arrange — a tube has
only two small end caps); **coincident rings are welded, not emitted** (at grade the cut depth is 0
and the middle rings coincide, and a solid of degenerate quads is non-manifold, which the boolean
also answers by doing nothing, silently); and **the reach is asymmetric** — full depth downward, but
upward only to each section's own daylight point, because ground above that is hillside the batter
has run out to meet (a local downward reach was measured too: holes 57% → 21% for no gain).
`road_support.cut_footprint`/`CUT_SLOPE` give a CUT the batter only a FILL had — steeper than the
fill (1:1 vs 1:1.5) because a cut face is undisturbed ground while a fill is placed earth on its
angle of repose. And **`CUT_MAX` had two owners that disagreed 8×**: it said a trench deeper than
3 m is a TUNNEL while `island_v3_terrain.MAX_BENCH` said 25, so the touge's 8.1 m bench was
classified as a tunnel nothing builds; `MAX_BENCH` reads `CUT_MAX` now. Measured: samples cut
**6% → 57%**, ground standing proud on eleven of twelve roads **up to +0.42 m → +0.00 m**.
**Still open (`W13`): the shrine touge is the twelfth** — still 0% cut and 8.71 m under its
hillside — and it is a SAMPLER problem, not a geometry one. The hairpin theory was tested twice and
reverted (chunking the cutter every 150° of turn, and a local skirt instead of the full depth:
neither moved the touge, and the second cost 57% → 21% of through-holes elsewhere). At the deepest
station `ground_sampler` returns ground 3 m **below** the road while the station's stored `ground_z`
says the road is 8 m **below** the ground — an 11 m disagreement — so `_cut_section` gets a daylight
height of 0 and correctly removes nothing. `scene.ray_cast` respects modifiers and punches through
whatever `is_terrain` rejects; that is where the 11 m comes from.

**A MATERIAL IS AN ASSET, NOT A CONSTANT IN A BUILDER** (2026-09-05, user-asked: default the
plugin's materials to the ones in `assets/`). `kit_common.mat()` used to get-or-**create** every
material from its own Python table, in whichever `.blend` was building — so the look of the world
lived in code, and it was not even one datablock: `road_kit.blend`'s profile sections carry their
own `M_Concrete` (built by that same function, in that file), so a district linking a kerb section
got the kit's concrete on the kerb and a locally-created one on the deck beside it. Identical, and
two materials in the exported scene. **The kit file is the material library now** —
`blender/tools/build_road_kit.py` writes every `MATS`/`TILED_MATS` entry into
`assets/world_source/kits/road_kit/road_kit.blend` with a **fake user** (a `.blend` drops any zero-user
datablock on save, so without the flag the kit shipped only the 3 of 25 its sections happened to
use). `mat()` is still the ONE resolver and grew one lookup, not a second registry: a datablock of
that name already in the file wins (`bpy.data.materials.get` prefers a LOCAL one over a linked one
— measured — so a hand-edit survives a rebuild), else it is **linked** from the kit, else built
from the table as the BOOTSTRAP (`build_road_kit.py` sets `kc.USE_MATERIAL_LIBRARY = False`: the
tool that writes the library must not read it). Linked, not appended — an appended copy drifts —
and a linked material *is* writable from Python in a background process, so the base-colour
flattening below is unaffected. `point_build.material()`/`MATERIAL_KEYS` and `point_style.resolve`
are **untouched**: the addon had one default-material lookup and still has one; adding a second
there would have been the very defect this closes. Measured on `Island_base`: the same 11
materials with the same user counts, every one now `lib=//../kits/road_kit/road_kit.blend`, all 11 baked
with an `albedo_color`, `check_roads.sh` PASS=18.

**A PROCEDURAL BASE COLOUR CANNOT CROSS glTF, AND IT LEAVES NO TRACE WHEN IT FAILS**
(2026-09-05, user-reported "materials seem lost"). glTF carries a base colour as either a CONSTANT
factor or an IMAGE texture. Blender's exporter reads the Principled BSDF's Base Color: unlinked it
writes the constant, linked to an image it writes the texture, and **linked to anything else — a
Checker, a Noise, a Mix — it writes nothing**, so Godot renders the surface pure white with no
warning on either side. `kit_common.get_tiled_mat` builds exactly that shape, for a good reason (a
world-position checker survives a curved corner without the UV pinch a tangent-frame pattern gets,
which is what a footway wrapping a junction fillet needs) — so **`M_ConcreteTile`, the PAVEMENT,
had been white in-game ever since**, while looking right in every Blender render. The authoring
intent belongs in Blender and the constraint belongs to the seam, so the fix is at the seam:
`export_world.py` temporarily replaces any Base Color driven by a non-image node with a
representative constant (a Checker's is the mean of its two colours; anything else falls back to
the material's viewport `diffuse_color`) and restores it after export. **Verified by reading the
baked `.tscn`:** every named material now carries an `albedo_color` (the one remaining blank is an
unused glTF default with 0 users). When a surface looks white in Godot and right in Blender, check
this before suspecting the mesh.

**A GROUND CUTTER IS A MODIFIER INPUT, NOT CONTENT — AND IT MUST BE UNLINKED, NEVER REMOVED**
(2026-09-05, user-reported "one white ground cover the main pave segment, like an open box over the
road"). `point_build.cut_ground` builds one solid per road/pad and hands it to the terrain as a
BOOLEAN target; they are scene objects in `ROAD_MANAGER_GEN/CUTTERS`, and the glTF exporter takes
the whole scene — so all 32 baked into the game as raw white boxes straddling every road. It went
unseen for as long as `bmesh.ops.solidify` was silently producing zero-thickness sheets at z = −40
(the `W22` defect): invisible cutters that cut nothing. Giving them real volume made them real
geometry in Godot. **Removing the objects is not the fix** — the boolean would lose its target and
the terrain would export UNCUT, undoing `W22` where it matters. `export_world.py` UNLINKS them from
every collection instead: verified, the evaluated terrain reads 30577 vertices linked, unlinked and
relinked alike, because the modifier's own reference keeps the datablock alive while the exporter,
which walks the scene rather than `bpy.data`, no longer sees it. Baked scene: 32 cutter nodes → 0,
Ground still 38153 vertices against 19477 uncut.

**The Blender→Godot axis mapping is (x, y, z) → (x, z, −y), and it is correct** — verified to three
decimals on a baked road (`export_yup=True`). A piece that "looks flipped" in Godot is far more
likely a lost material than a transform; measure a known object's bounds on both sides before
chasing the export.

**A HILL ROAD IS DERIVED, NOT DRAWN** (island v3, 2026-08-31 — `blender/WORLD_REBUILD_PLAN.md`
`W2`). `island_v3_terrain.hill_road` walks the height field to produce a switchback alignment:
write a heading as `cos φ · uphill + sin φ · contour` and the height gained per metre is
`|∇z| cos φ`, so asking for the road's grade fixes `φ = acos(grade / |∇z|)` — on a 92% flank an 8%
road runs 85° off the fall line, and flipping the contour term's sign IS the hairpin. It is not a
grid search on purpose: the legal headings lie within ~5° of the contour, a grid offers 8 or 16 of
them, so A* returns nothing and that reads as "there is no route up this hill" (which the plan had
recorded as a measured fact). Three rules came with it and each was a defect first — **the hairpins
are part of the climb** (a half-turn moves the road `2R` across the slope, so it gains `2R·m` in
`πR`; legs walked at the limit average 10.1% on an 8.1% road, and the grade cone "corrects" that by
lifting the foot of the mountain, giving a 57 m sky-road that every per-sample check passes);
**a benched road is judged over its whole alignment**, not sample by sample
(`island_v3_terrain.BENCHED_CLASSES`, `alignment_grade`, `bench_depth`, `MAX_BENCH`) — its hairpins
are cut-and-fill platforms and the ground across a turn swings far more steeply than the road does;
and **the station rule has one owner** (`island_v3_terrain.stations`), because a resample that only
lays even arc-length stations steps clean over a 38 m hairpin at 70 m spacing and the cone then
fills the cut corner (25.6 m of pier where the model said 14.7). `grade_cone` is likewise one
function shared by the seeder that builds the road and the gate that predicts it.

**A MOUNTAIN ROAD IS A BENCH, NOT A VIADUCT** (2026-08-31). `seed_district_roads.height_profile`
raises a draped profile with a grade cone, which is right for a bay crossing (you do not cut a
bridge into water) and wrong for a hill — it answered every hairpin with a pier and left 71 of the
shrine touge's 90 stations elevated, up to 16.3 m, over a hillside the ground cut had already
punched a road-shaped slot through. `island_v3_terrain.bench_profile` takes the MIDPOINT of the two
envelopes (least legal profile above the ground, greatest below); it is grade-legal for free because
`|dz| <= limit*span` is convex, and it turns +16.3/−0.0 into a symmetric ±8.1 at an unchanged 8.10%.
Applied only to `BENCHED_CLASSES`. **The ground cut itself was never the problem** — measured at the
centreline stations it leaves ground standing proud at 1 of 419, by 0.18 m (`cut_ground` is a
vertical prism from −40 to +40 m over each band's footprint). What is still missing is a CUT BATTER:
`road_support` builds an embankment toe for FILL and columns for PIER and nothing at all for CUT, so
a benched stretch comes out in a vertical-walled slot.

**A SHALLOW CROSSING NEEDS A BIG PAD** (2026-08-31). `point_solve.auto_setback` searched only for a
tail that fits every turn MOVEMENT and never asked whether the arms' own CAPS stay in ring order —
so `pad_not_star_shaped` named `Auto Setback` as its remedy and `Auto Setback` answered "moved 0".
The ring stays in order while `atan(half_a/d) + atan(half_b/d) <= theta`, i.e. `h/tan(theta/2)` at
equal widths: 14.5 m at a square crossing, **27.2 m at 56°**. `corner_clearance`/`corner_setback`
add that term. It is the CAP-ORDER test, not "where the outer edges cross" (30.8 m at 56°), which
over-demands by half — a fillet may bulge past that point, and asking for it grows every square
junction for a fold that is not there.

**LANES ARE 4.5 m, WHICH IS AN ARCADE NUMBER** (`seed_district_roads.LANE_WIDTH`, and
`point_model`'s own default, 2026-08-31). The car's hull is 2.00 m with wheels at ±1.1 m, so its
footprint is ~2.4 m: in a book-correct 3.25 m lane that is 74% of the lane and it drives like a
lorry in a tunnel. 4.5 m leaves 1.05 m either side. `island_v3_plan.ROAD_HALF` carries the same
arithmetic (T2 = 4 lanes + 3 m median + two 4 m footways = 29.0 m).

**THE VEHICLE SPEED-FEEL OVERLAY IS DELETED** (2026-08-31, walk-test: "too much… hard to see
road"). `SpeedFX`/`SpeedLines` and `SpeedLines.gdshader` are gone from `Vehicle.tscn`, not hidden.
`VehicleCameraController`'s FOV/accel/NOS/spring-arm terms are kept as exported knobs and ship at
**0**, with their previous values recorded on each field — a camera that cannot react to speed at
all is a decision to take deliberately, not by deletion. The planned replacement is world-space (a
trail or wheel effect on the car), never a screen overlay.

**`-noped` HAS A READER ON THE GODOT SIDE NOW** (2026-08-30). `point_build.collision_name` had
stamped the marker into every carriageway `-colonly` proxy since the point graph landed,
*specifically* so the navmesh would skip them, and nothing in Java had ever looked at it —
`NavBaker` parsed the whole root, so every carriageway baked into the navmesh the marker exists to
keep it out of. `NavBaker.NO_PED_TOKEN` is that reader: it clears each matching body's
`collision_layer` for the duration of `parseSourceGeometryData` (Godot's `STATIC_COLLIDERS` parser
tests the layer against the navmesh's geometry mask) and restores it before `pack()` — reversible,
and it cannot drop geometry from the SAVED scene the way detaching nodes could. What the marker
means on this side is "solid, but not walkable ground", so it is **not road-only**: the island's
`Seabed-noped-colonly` is its second user. Note the honest limit measured on `Island_base`:
excluding the carriageway removed only 11 of 1232 navmesh vertices, because the road stands 0.16 m
proud of ground that is continuous underneath it — a street stays crossable (correctly), and the
case the marker really decides is an on-ramp on piers, where there is no ground under the deck.

**Road/geometry alignment across a shared seam is a separate, still-manual concern.** Because Blender's Library Override
system can move/rotate a linked object as a whole but can never edit linked mesh/curve vertex
data, aligning road geometry that genuinely spans two districts' seam needs either (a) read-only
whole-world context while editing one district locally (`tools/link_neighbors.py`, extendable to
every built district, not just immediate neighbors), or (b) a temporary scoped multi-district
edit session — append (not link) just the districts that need reconciling into one scratch file,
edit their `MANUAL` content together with full Edit Mode access, then write each district's
result back into its own file. See `AUTHORING_GUIDE.md` for the current tooling around this.

### AI spatial perception — StimulusManager (`com.openworld.world`, AutoLoad, E2)

Poll-based, spatial channel for AI-perceptible world events — the AI counterpart to `SpatialEntityGrid`
(events instead of bodies). **Not EventBus:** EventBus fans every signal to every listener (right for
UI, wrong for AI at open-world scale); a stimulus is instead *dropped at a world position with an
audible `radius`*, and AI **poll** their own neighbourhood. EventBus is unchanged and keeps all UI
signals — only AI-perception events live here.

- **`StimulusManager`** mirrors the AutoLoad shape (JVM-static `get()`, `_exitTree()` clears). Holds a
  `List<Stimulus>` aged out after `stimulusLifetime` (5 s) in `_process`. `post(type, origin, radius,
  source, sourceFaction)` drops one; `getStimuli()` exposes the live list read-only (same backing-list
  convention as `PlayerRegistry`). `Stimulus` is an immutable plain object; `Type` =
  `GUNSHOT, EXPLOSION, VEHICLE_CRASH, DEAD_BODY, PLAYER_SPOTTED` (last two reserved for later).
- **Emit (authority side-effect paths only**, so the host that simulates the AI sees them):
  `FirearmItem.useWeapon` → `GUNSHOT` at the muzzle (`gunshotHearingRadius`, exported, 150 m — *not* the
  puppet `playRemoteFireCue`); `ExplosionManager.triggerExplosion` → `EXPLOSION` at the blast center
  (heard past the blast); `Vehicle._integrateForces` → `VEHICLE_CRASH` on a fast impact (throttled
  ~1×/s).
- **Poll:** `AICharacter.hearAlarm()` returns the nearest investigate-worthy origin within
  `behaviorConfig.hearingRadius` (capped by each stimulus's own radius), ignoring its own events and
  *allied* gunfire (`Faction.areHostile` for `GUNSHOT`; explosions/crashes alert everyone).
  `PatrolState` calls it after the visual-target check and, on a hit, sets the controller's
  last-known-position and transitions to `SearchState` (which already navigates there). `DebugHarness`
  **F8** drops a synthetic enemy `GUNSHOT` at the player for a vision-free walk-test.

**Networked propagation:** stimuli are a local per-peer list (puppet AI don't think). A remote
*client's* gunshot is delivered to host AI **for free via the existing fire replication** — when the
client's `fireSeq` bumps, the host runs `FirearmItem.playRemoteFireCue` on that puppet and (gated to
`isServerPeer()`) posts the same GUNSHOT stimulus there, where the AI poll. No new network message;
other clients run the cue but don't post (their AI are puppets). Non-gunshot stimuli
(explosion/crash) still post only where their authoritative side-effect runs.

### Squad awareness — AISquad (`com.openworld.character`, E3)

Shared group targeting so shooting one AI turns the whole nearby band toward the shooter within a
frame, instead of each AI waking on its own ~0.4 s scan.

- **`AISquad`** is a `Node` (editor-placed, or one created per `SpawnConfig` by `ZoneManager`).
  Members `register`/`unregister`; it holds a `sharedTarget` + `sharedLastKnownPosition`.
  `getSharedTarget()` self-clears a dead/freed/out-of-tree target (the "lose track" path);
  `clearThreat()` drops a still-alive one.
- **Spot → broadcast:** `broadcastSpotted(spotter, target, pos)` records the target and pushes it to
  every member within `alertBroadcastRadius` (60 m of the spotter) via `AICharacter.adoptSquadTarget`
  — which sets `currentTarget` + last-known immediately (skipping the scan interval). Triggers:
  `AttackState` on confirmed LoS, and `AICharacter.onEnemyDamaged` (being shot is a sighting too — uses
  `currentTarget`, the believed attacker). Squad-mates are one faction and the spotter already verified
  hostility, so adopters skip a redundant faction check.
- **Converge:** `AICharacter.discoverTarget()` consults `getSharedTarget()` **before** its own scan, so
  a mate keeps the shared target across rescans; `PatrolState` chases a squad-adopted target even
  without personal LoS yet. `AICharacter` holds the squad via `activeSquad()` (nulls a stale ref to a
  freed squad node — pooling/reuse safe); `setSquad` moves registration; `ZoneManager` frees each
  per-group squad on unload.

`AISquad._process` also implements **lose-track**: if no member has spotted the shared target for
`forgetDuration` (8 s) it `clearThreat()`s and members fall back to their own scans (death is handled
sooner by `getSharedTarget`'s self-clear).

> **Part E (E1–E3) complete.** Only deferred item left: body-recycling (E1, off by default — subtree
> reuse unsafe; frame-spread spawning is the real perf fix, TODO).

---

