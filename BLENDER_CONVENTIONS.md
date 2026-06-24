# Blender → Godot Conventions

Reference for authoring world/character content in Blender for import into Godot 4.6.
This is a living document — update it as pipeline decisions are made, **before**
content production scales up. Authoring real geometry against undecided conventions means redoing
it once they're set — the same retrofit-cost logic rule is built on.

## Status

Sections below are **proposals to confirm**, not decided defaults — tick each off
as the team agrees on it, and update the section with the actual decision.

- [ ] Coordinate / scale convention
- [ ] Collision-proxy authoring workflow
- [ ] Naming conventions for collision / navigation / gameplay markers
- [ ] Zone-chunking size (must match `WorldZone` grid — see PLAN.md E1)
- [x] Per-chunk navigation + chunk adjacency (abut, don't overlap) — see "Zone chunking" below
- [x] Road / traffic-lane authoring (3.5 m lane modules + `VehicleRoute` lanes) — see "Roads & AI traffic" below
- [ ] LOD / poly budget per region tier
- [ ] Terrain strategy (heightmap vs. hand-modeled mesh)
- [ ] Import / version pipeline
- [ ] Source-control strategy for `.blend` binaries

---

## Coordinate & scale

- 1 Blender unit = 1 Godot unit = 1 meter. Author at real-world scale — every
  distance-based system in the codebase (`LOD_FREEZE_DIST = 200m`, `swimSpeed`,
  `loadRadius`/`unloadRadius`, `relevanceRadius = 200m`, …) assumes meters.
  Off-scale content silently breaks all of them at once.
- Blender is Z-up; Godot is Y-up. Godot's built-in `.blend` importer handles this
  automatically — don't "fix" orientation by rotating the root in Blender, or
  you'll double-correct on import.

## Collision-proxy authoring

- **Decision needed:** hand-authored low-poly proxy meshes (standard for large
  world geometry — better performance, full control) vs. Godot auto-generating
  `CollisionShape3D` from the visual mesh.
- If hand-authored: name proxy meshes with a `-col` suffix so Godot's importer
  auto-converts them to `CollisionShape3D` siblings of the visual mesh.

## Naming conventions for gameplay-relevant objects

The codebase already relies on naming-convention-driven discovery in several
places (e.g. `ParticleManager` requires child containers named exactly after
`SurfaceType` constants; `WeaponController` discovers weapons via `Marker3D`
wrappers — see `CLAUDE.md` "Known Quirks"). The Blender pipeline should follow
the same pattern so content authors can place gameplay objects without hand-editing
scenes afterward. Proposed scheme — confirm before the first real zone is built:

| Authored as (Blender) | Converts to (Godot) | Used by |
|:-----------------------|:--------------------|:--------|
| Empty named `spawn_<faction>_<n>` | `Marker3D` + `SpawnConfig` entry | E1 `WorldZone` |
| Empty named `portal_<zoneA>_<zoneB>` | `PortalTrigger` (`Area3D`) | I2 `InteriorZone` |
| Empty named `water_<id>` (bounding box) | `Area3D` in group `"water"` | I1 `SwimState` |
| Empty named `lane_<route>_<n>` | `Marker3D` child of a `VehicleRoute` | I3 traffic lane (pure pursuit, **not** navmesh) |
| Empty named `zonetrigger_<beatId>` | `ZoneTrigger` (`Area3D`) | F3 |
| Mesh suffixed `-col` | `CollisionShape3D` | all world geometry |

A Godot `EditorScenePostImport` script should walk each imported scene and
convert these by name/prefix into the right node + script attachment. Renaming
hundreds of already-placed objects after the fact is exactly the retrofit cost
this document exists to avoid — lock the prefix scheme down first.

## Zone chunking

- `WorldZoneManager` (PLAN.md E1) streams geometry per `WorldZone` based on
  `loadRadius` / `unloadRadius` (hysteresis). Author and export geometry in chunks
  matching the chosen zone-grid size — **not** as one monolithic scene — or E1 has
  nothing to stream in/out. The chunk is assigned to the `WorldZone.geometry`
  PackedScene field (it instances on **every peer**, host and client — geometry is
  cosmetic/local, only AI bodies are host-authoritative). A mesh placed as a child
  of the `WorldZoneMarker` is static scene furniture and does **not** stream.
- Decide the zone-grid size *before* any real geometry is modeled; it constrains
  border layout, road continuity (I3), and region-transition placement (I4).

### Setting up a zone (recipe) — E1

1. **Pick a zone-grid cell size** (e.g. 60–120 m square) and model/export each
   geometry chunk to those exact extents so chunks **abut** (see below). This is
   the value `WorldZone.size` (X/Z) should match — the spawn box is meant to cover
   the authored chunk footprint; Y is the vertical spawn band (~10 m is plenty for
   ground AI).
2. **Place a `WorldZoneMarker`** (duplicate `resources/.../world/zones/DebugZone.tscn`)
   at the chunk **center** — the marker's world position *is* the zone center — and
   assign a `WorldZone` `.tres` with `size` = the chunk extents.
3. **Set the trigger radii** (both measured from the center, independent of `size`):
   `loadRadius ≈ size/2 + pre-spawn lead (~150 m)` so AI stream in *before* the player
   reaches the box, and `unloadRadius ≈ loadRadius + hysteresis margin (~150 m)`. The
   invariant `unloadRadius > loadRadius > max(size.x,size.z)/2` must hold or the zone
   flickers / unloads while the player is still on it (`WorldZoneManager.warnIfMisSized`
   logs a debug warning otherwise). Neighbour zones' `loadRadius` should reach past the
   `unloadRadius` you're leaving so there's no dead frame with nothing loaded.
4. **Assign the chunk mesh to `WorldZone.geometry`** (the PackedScene field) so it streams
   with the zone. A mesh dropped as a *child of the marker* is static furniture and never
   streams. Populate `spawnConfigs` (ambient AI) and `namedCharacters` (story AI).

### Navigation per chunk — DECIDED (E1)

- Each streamed zone-geometry chunk **carries its own baked `NavigationRegion3D`**
  inside its `geometry` PackedScene (baked offline against that chunk's collision).
  Streaming the chunk in adds its navmesh to the navigation map; streaming out
  removes it. The current single world-baked `NavigationRegion3D` is a placeholder —
  AI path *through* any building you stream in until that building's chunk owns nav.
- Multiple `NavigationRegion3D`s feed one navigation map; Godot stitches them where
  their navmesh **edges fall within the map's `edge_connection_margin` (~0.25 m)**.

### Chunk adjacency: abut, don't overlap — DECIDED (E1)

- **Geometry + navmesh chunks must be edge-adjacent (abutting), never overlapping.**
  Overlapping navmeshes create ambiguous/duplicate regions and seams; only abutting
  edges (within `edge_connection_margin`) stitch cleanly.
- The **load/unload *trigger* radii are the part that overlaps** — `loadRadius` of a
  neighbour reaches past the `unloadRadius` of the one you're leaving, so a player
  crossing a border is inside the next zone's `loadRadius` before leaving the
  current zone's `unloadRadius` (no dead frame with nothing loaded). Distinct from
  the geometry chunks, which abut. There is **no** cross-zone connection/portal graph
  in E1 — zones are independent and AI roam freely between them (the zone box is a
  spawn + load/unload trigger, not a movement fence).

## Roads & AI traffic lanes — DECIDED (I3)

**Core rule: a navmesh does not drive cars.** A navmesh is a 2-D walkable polygon with no concept of
lanes or direction, so it can keep a *pedestrian* on a surface but cannot make a car hold a lane or go
one way. AI traffic (PLAN.md I3) therefore follows an explicit **directional lane path** — a
`VehicleRoute` node whose ordered `Marker3D` children are the lane centerline, in travel order. The car
uses **pure pursuit** (aims a fixed look-ahead ahead *along* the polyline), which keeps it in-lane and
damps steering oscillation. The vehicle navmesh layer was removed; do **not** bake nav for roads.

So a road has **two independent halves**, authored separately:

### 1. Road mesh (Blender) — visuals + collision, on a grid
- **Lane width = 3.5 m** (matches `SingleRoadMesh.tscn`, the placeholder block: 3.5 m wide × 1 m
  forward). A 2-way street = two lanes = **7 m** wide.
- **Block set — modular kit on a 7 m grid, +Z = forward, tiles centered on origin so they abut
  (never overlap, same rule as zone chunks above).** Placeholder kit (replace each with a Blender
  mesh of the same footprint): `resources/.../world/roads/`
  - **`Road2LaneStraight.tscn`** — 7 m × 7 m 2-lane straight (center + edge lane lines). A 7 m
    2-lane tile is the convention (easier than two single-lane rows, matches lane-marking textures);
    `SingleRoadMesh` (a single 3.5 m lane) is kept only as the raw dimension reference.
  - **`Road4Way.tscn`** — 7×7 cross intersection. **Carries an `IntersectionZone`** (right-of-way,
    below) so dropping a 4-way tile brings its own traffic control.
  - **`RoadCorner.tscn`** — 7×7 corner (for ring roads / 90° turns; the lane route defines the curve).
  - *(Model a 3-way `T` tile the same way when needed.)*
  - Each tile carries its **own collision** (StaticBody3D, layer 1) — the imported Blender mesh
    replaces both the visual and that collision. Build a layout by placing tiles on the grid
    (rotate straights 90° for the cross axis); see `RoadKitExample.tscn`.

- **Junction right-of-way (I3b):** the `Road4Way` tile's `IntersectionZone` (an `Area3D`, `collision_mask`
  = vehicle layer) arbitrates crossing — first AI vehicle to arrive holds the junction, others yield
  until it clears (deadlock-free single-occupancy). Place a junction tile and the zone comes with it;
  no per-junction wiring. (Concurrent non-conflicting movements + signals = the fuller lane-graph, still
  future work.)

### 2. Lane paths (`VehicleRoute`) — the directional graph
- **One `VehicleRoute` per lane/direction.** Markers run along the lane centerline, **offset ±1.75 m**
  from the road center, spaced ~5–15 m (denser on curves). Marker order = travel direction.
- **Drive side = a content choice (tunable), not a code flag** — it's purely which side of the road
  centerline each direction's lane markers sit on. To flip it, mirror the lane-offset sign on every
  route; if a route generator lands later (I3b lane-graph), drive-side becomes one parameter there.
- **Project default: drive on the LEFT** (the map targets a Japan-like setting — Japan is left-hand).
  With +Z = north, +X = east, keep-left means: northbound uses the **west** lane (X = −1.75),
  southbound the east lane (X = +1.75), eastbound the **north** lane (Z = +1.75), westbound the south
  lane (Z = −1.75). The near-side (easy, no-oncoming-cross) turn is a **left** turn. `RoadKitExample`
  is authored this way (`RouteTurnNB_WB` is the example left turn). For right-hand traffic, negate all
  those offsets.
- **2-way street** = two routes, opposite directions, one per lane.
- **4-way junction** = one route per movement you actually want (through + each turn). Cars on different
  routes cross at the center and brake for each other via a forward obstacle ray; **true right-of-way /
  signals is the deferred lane-graph (PLAN.md I3b)** — until then, expect bumping at busy junctions.
- `VehicleRoute.loop`: `true` = ring road (cars circulate); `false` = one-way through lane (car drives
  to the last marker and stops — junction-to-junction chaining is I3b).
- **Authoring source of truth = Blender empties** named `lane_<route>_<n>` (see the table above); an
  `EditorScenePostImport` step groups them into `VehicleRoute` nodes. `RoadKitExample.tscn` is the
  hand-built reference layout (4-way + 2-way ring); press **F4** in-game (DebugHarness) to drop one AI
  car on every route to test a layout.

> **Future (I3b):** a connected lane-graph (junction connectivity + right-of-way/signals), an optional
> generator that builds `VehicleRoute`s from Blender curves/empties, and networked spawn replication of
> streamed traffic.

## Blender-authored world & thin Godot loader — DIRECTION (I6)

**Goal: Blender is the source of truth for geometry *and* gameplay markers; Godot just imports +
runs a thin post-import loader.** No hand-placement of roads/lanes/zones in `.tscn`.

- **One conversion mechanism — `EditorScenePostImport`** (already referenced in "Naming conventions"):
  a script on the imported scene walks it once and turns **named** Blender objects into the gameplay
  nodes (the naming table above). Model + name in Blender → Godot auto-builds the node tree.
- **Roads (mesh) via Geometry Nodes:** draw road **centerline curves**; a GN setup sweeps the tile
  profile along them (surface, curbs, lane-line UVs). GN output exports fine — glTF/.blend export the
  *evaluated* mesh. Godot imports baked mesh + bakes collision from `-col` proxies.
- **Lanes via curves, not hundreds of markers (the scale win):** author **one centerline curve per
  road**; a GN/Python step offsets ±1.75 m per lane and reverses the opposite direction — so
  **drive-side is the offset sign, generated** (the tunable knob, see "Roads & AI traffic"). Bridge to
  Godot: glTF doesn't round-trip curves, so bake each lane to **named empties** (`lane_<route>_<n>`,
  exported as nodes) or a **JSON sidecar** of points; post-import builds a `VehicleRoute` per route.
  *(Recommended code follow-up: let `VehicleRoute` optionally hold a baked `Curve3D` so one Blender
  curve = one lane node — pure pursuit samples the curve. Do this with I6.)*
- **Junctions / zones / spawns / water = named empties** → post-import creates the Area3D/marker nodes
  (`intersection_<id>` → `Road4Way`'s `IntersectionZone`, `spawn_*`, `water_*`, `zone_*`, …).
- **Stays Godot-side (don't move to Blender):** pedestrian `NavigationRegion3D` bake (scriptable on
  import, but Godot's bake; lanes need none), all networking/gameplay logic (Java), final `.tscn`
  assembly + AutoLoads, `WorldZone` streaming wiring (chunks exported per grid cell per "Zone chunking").
- **Caveats:** glTF triangulates curves (use the empties/JSON bridge); GN can emit geometry for export
  but not real empties (use a Python script for marker/curve data); the whole pipeline hinges on the
  **stable naming scheme** — lock names before volume grows (the retrofit cost this doc exists to avoid).

## LOD / poly budget (Steam Deck target)

- Define a poly-count ceiling per region tier (dense city street vs. distant
  mountain silhouette, etc.), sized to D's frame-budget targets
  (`< 16 ms` across the FROZEN / PASSIVE / ACTIVE AI tiers).
- Decide the LOD-generation workflow now — Blender's Decimate modifier per
  export vs. an external/automated tool — and apply it consistently. Mixed
  per-region budgets make D's profiling numbers meaningless.

## Terrain strategy

- **Decision needed:** heightmap-based terrain (sculpted in Blender, imported
  via a Godot terrain plugin, e.g. Terrain3D) vs. hand-modeled mesh terrain.
  This is a fork, not a style preference — it determines the entire authoring
  workflow *and* how E1's streaming and D's LOD interact with the ground.
  Switching later means re-authoring all terrain from scratch.

## Import / version pipeline

- Confirm everyone runs compatible Blender + godot-kotlin-jvm plugin versions
  (current project: plugin `0.15.0-4.6`, JDK 17 — see `CLAUDE.md`).
- Agree on import presets per asset class (static mesh vs. skeleton+animation —
  `assets/merged_animation.blend` is the existing example of the latter) so
  re-imports stay reproducible across machines.

## Source control for `.blend` files

- `.blend` files are large binaries — the repo already carries
  `assets/merged_animation.blend` and `assets/ui/AssaultRifle_5.blend`. Decide
  *before* volume grows: Git LFS, a separate asset repo, or committing only the
  exported/imported result and keeping `.blend` sources elsewhere.
