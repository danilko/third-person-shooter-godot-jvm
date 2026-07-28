# World Authoring Guide — how to modify a district and get it into the game

The **day-to-day workflow doc** for `assets/world_source/` — the real commands an artist runs to
change a district `.blend` and see it in-game. The decided naming/structure conventions live in
[`BLENDER_CONVENTIONS.md`](../../BLENDER_CONVENTIONS.md) (repo root); this file is about *doing*.

---

## 1. Pipeline map (what happens between Blender and the game)

```
assets/world_source/districts/District_<theme>_<gx>_<gy>.blend       ← the Blender source you edit
        │  tools/export_world.py (glTF, drops Blender-only collections)
        ▼
src/main/resources/com/openworld/world/districts/<stem>.gltf/.bin    ← throwaway intermediate
        │  WorldBaker (Java, named markers → gameplay nodes)
        ▼
…/districts/<stem>.tscn                                              ← the streamed scene
        │  NavBaker (pedestrian navmesh from the scene's own collision)
        │  DistrictBinaryConverter (.tscn → sibling .scn, faster stream-in parse)
        ▼
streamed in-game by the master's WorldZoneMarkers (predictable path — the master
never needs re-baking when a district changes)
```

**One command runs all of it:** `tools/build_piece.sh` (from `assets/world_source/`). It has two
forms — the difference matters (see §3):

```bash
tools/build_piece.sh shibuya              # config-name form: REGENERATES the .blend, then bakes
tools/build_piece.sh District_city_1_1    # stem form: BAKE-ONLY — exports/bakes the .blend AS-IS
```

Walk-test one district: `<godot-jvm> --path <repo> res://src/main/resources/com/openworld/world/hosts/SoloPiece.tscn`
(the build points it at the piece you just built). Full world: `hosts/WorldMaster.tscn`.

---

## 2. What is generated vs. what you own (edit channels)

A district `.blend` is **mostly generated** by `towns/districts/build_district.py` (from its
`CONFIG` entry + the PLATEAU extraction JSON in `plateau/data/<precinct>.json`). A rebuild
**regenerates these collections from scratch — never hand-edit inside them** expecting the edit
to survive a regen:

| Collection | Contents | Regenerated on rebuild? |
|:--|:--|:--|
| `STREET` | buildings, terrain/ground, roads (visual + collision) | **YES — wiped + rebuilt** |
| `MARKERS` | lane/route/seam/spawn empties for the baker | **YES — wiped + rebuilt** |
| `STREET_LOD_LOW` | low-detail placeholder tier (procedural districts only) | **YES** |
| `ROADS_SRC` | your road curves, re-imported from the sidecar | **YES (from the sidecar)** |
| `MANUAL` | **your hand-authored content** | **NO — preserved** |
| `NEIGHBOR_REF` | linked neighbour-district context (§4) | **NO — preserved (and never exported)** |

The durable channels, in order of preference:

1. **`MANUAL` collection** — put any hand-modeled mesh/marker here (extra props, a plaza, a
   hand-fixed border ramp, `instance_<AssetId>` / `asset_path` markers for kit pieces). It is
   preserved across rebuilds, exported, and baked exactly like generated content — same naming
   conventions apply (`-colonly` collision proxies, `lane_*`, etc., see BLENDER_CONVENTIONS).
2. **Road sidecar `districts/<piece>.lanekit.json`** — internal traffic pieces are built with the
   `road_kit_authoring` addon, then combined: `tools/save_lane_kit.py`, rebuild. Full loop in §7.
3. **The generators themselves** — `build_district.py` CONFIG (counts, landmark, theme knobs) and
   the PLATEAU JSON (re-extract / `--augment` via `plateau/extract_plateau.py`). Anything changed
   here reaches every future rebuild.
4. **Direct edits to generated collections** (last resort) — legitimate for one-off fixes, but you
   must then use the **bake-only** build form (§3) and accept that the next regen of that district
   discards the edit. Prefer moving the result into `MANUAL`.

---

## 3. The two build loops

**Regenerating loop (config-name form)** — for changes made through the durable channels:

```bash
cd assets/world_source
tools/build_piece.sh shibuya        # or city_2_1, harborE, … (see build_district.py CONFIG keys)
```

Rebuilds the `.blend` **in place** (opens the existing file, wipes only the generated collections,
keeps `MANUAL`/`NEIGHBOR_REF`), then exports → bakes → navmeshes → refreshes the `.scn`.

**Bake-only loop (stem form)** — for hand edits to the `.blend` you just made in Blender:

```bash
tools/build_piece.sh District_city_1_1     # no regen; exports/bakes the file exactly as saved
```

Both forms end with `DistrictBinaryConverter` (mtime-skips untouched districts), so the freshly
baked `.tscn` is never shadowed by a stale sibling `.scn` — nothing else to remember. Streaming
resolves districts by predictable path, so **the master never needs re-baking for a district
change** (`tools/build_world.sh` is only for grid/theme/arterial-level changes).

---

## 4. Editing across district borders (multi-district connections)

Districts are **collaged from different real PLATEAU locations** (different wards, even Osaka), so
adjacent borders do **not** naturally continue into each other — ground height, road ends and
building fabric all change at the seam. That is by design (a "greatest hits" map, not literal
geography); the model for what must line up:

- **Inter-district travel is carried by the always-resident master layer** — the arterial backbone
  + its collision deck (`ARTDECK`, incl. the world safety floor), and (planned) highway/train
  overlays (§5). Districts do **not** have to road-match each other edge-to-edge.
- **A district's job at its border** is visual harmonization: its terrain/ground should meet the
  neighbour's without cliffs/z-fighting where players can see it, and not poke up through the
  arterial deck. Its internal roads may simply end near the border (traffic despawns at route end).
- The only *hard* cross-district contract is the generated seam-route empties (`seam_*`,
  `emit_seam_routes`) — regenerated automatically; you never hand-maintain them.

### See the neighbours while you edit (link_neighbors.py)

You no longer need to merge districts to fix a border. Link the adjacent pieces **into** the
district you're editing, as read-only referenced context at their true relative offsets:

```bash
cd assets/world_source
blender --background districts/District_city_1_1.blend \
    --python tools/link_neighbors.py -- --master
```

Then open `districts/District_city_1_1.blend` normally and edit. What you get:

- A `NEIGHBOR_REF` collection with the 4 edge-adjacent districts' `STREET` content (add
  `--diagonals` for all 8) placed at ±504 m and the correct theme-elevation delta — the **same
  numbers the runtime uses**, so what lines up in the viewport lines up in-game.
- `--master` also links the master's `ARTDECK` (arterial deck + safety floor) so you can see
  exactly where the always-resident road layer crosses your border (`--master=ARTDECK,HARBOR` for
  more collections).
- The links are **true Blender library links**: read-only (you can't accidentally edit a
  neighbour), near-zero file-size cost, and **live** — rebuild or hand-edit a neighbour and the
  reference updates on next file open. They survive this district's own rebuilds, are dropped by
  every export automatically, and `-- --clear` removes them.
- To fix the *other* side of a seam, open the neighbour's `.blend` (run `link_neighbors.py` on it
  too) — each file only ever edits its own content.

### Inspecting without editing

- **`world_master.blend` itself now shows the real world.** The master build
  (`towns/build_world.py`) library-links every **built** district's `STREET`/`MANUAL` into
  `LAYOUT` as a `Piece_<gx>_<gy>` collection-instance at its true world position — the same
  live-link mechanism as `link_world.py` below — replacing the old theme-coloured `Plate_*`
  preview boxes (a plate now appears only as the placeholder for a district not built yet).
  Opening the master shows the assembled world; edits still always happen in each district's
  own `.blend` (links are read-only), and `export_world.py` drops `LAYOUT` so none of it ever
  reaches the baked master — each district streams in on its own at runtime.
- **`tools/link_world.py` → `world_overview.blend` — the whole world, persistently.** One
  re-runnable file linking **every built district** (`Piece_<gx>_<gy>` collection-instance
  empties at their true `district_center` + theme elevation), the master's `MARKERS` (+`ARTDECK`
  when a `--full` master built one), and every `overlays/Overlay_*.blend`. Regenerate with
  `blender --background --python tools/link_world.py`; open `world_overview.blend` any time
  after. Because these are **live library links**: edit + save a district source `.blend`, reopen
  the overview (or File ▸ External Data ▸ Reload), and the edit is there — no rebuild. Content
  edits always happen in the district's own file (links are read-only here). **Moving a `Piece_*`
  empty is visualization-only** — runtime positions come solely from
  `lib/world_grid.py:district_center` (the single source of truth), and every re-run snaps the
  empties back.
- `tools/build_debug_preview.py` — same mechanism for an ad-hoc subset (a specific seam pair)
  into a throwaway `.blend`: 
  `blender --background --python tools/build_debug_preview.py -- _debug_edge districts/District_city_1_1.blend:1:1 districts/District_resid_0_1.blend:0:1`
- `tools/render_cluster.py` — same idea as a top-down PNG render.
- `tools/check_seams.py` — engine-free `.seam.json` cross-check of the generated seam routes.
- Headless smoke signal for streaming/traffic health: run `hosts/WorldMasterDebug.tscn` headless and
  watch for `N cars, M moving, K routed` (routed-but-0-moving = something fell through the ground).

### Fixing a border, step by step

1. `link_neighbors.py -- --master` on the district, open it in Blender.
2. Judge the mismatch at the shared edge (ground step? building clipping the deck? road stub
   pointing into a neighbour's building?).
3. Fix on **this** side only: sculpt/patch this district's terrain border band, add a hand ramp or
   retaining-wall mesh in `MANUAL` (with a `-colonly` proxy if it needs collision), or move/trim
   the offending generated content (then bake-only).
4. `tools/build_piece.sh District_<…>` (stem form if you hand-edited generated collections;
   config-name form if you worked through `MANUAL`/sidecars — `MANUAL` survives either way).
5. Walk-test via `SoloPiece.tscn`, or the seam itself in `WorldMaster.tscn`.

---

## 5. Highways / railways / bullet train (overlay convention — SEPARATE files, never embedded)

Long-span connective structures (an expressway ring, elevated rail, a shinkansen line) are
**their own `.blend` files outside any district** — `assets/world_source/overlays/<Name>.blend` —
**never embedded in the district blends**. The reasons are structural, not stylistic:

- **They cross many district cells.** Embedded, a single track would be sliced into up to 6
  independently-regenerated files that must agree at every seam — exactly the cross-district
  coupling this pipeline removed. As one overlay file, the entire line is authored (and curved,
  banked, elevation-profiled) continuously in one place.
- **Different lifecycle.** A district regen (`build_district.py`) must never touch the highway;
  an overlay edit must never force 6 district rebuilds. Separate files = separate build loops.
- **Different residency.** A rail/highway is visible from far away and carries its own traffic;
  it wants to be always-resident (like `ARTDECK`) or streamed in long spans by its own zone
  markers — not chopped to the 504 m district streaming grain.
- **A train is not per-district content.** A vehicle that traverses the whole map needs one
  continuous route; per-district route fragments would need seam chaining for something that
  never behaves per-district.

The conventions (established by the first overlay, the Rainbow Bridge):

- Authored in **world coordinates** (like the master's own content), exported with the same
  `tools/export_world.py` + WorldBaker path to its own `.tscn` under
  `src/main/resources/com/openworld/world/overlays/`.
- Districts don't know about overlays; an overlay touches down via its own ramp/pillar geometry
  over a district's ground (pillars carry their own `-colonly`). Author the touchdown against the
  real district content via `link_neighbors.py --master=<OverlayColl>` linking or
  `build_debug_preview.py`.
- Traffic on a highway overlay = its own `lane_*`/route layer inside the overlay blend, joining
  the arterial graph at ramp junctions (Roads & Traffic v2 Phase 3 — see PLAN.md). A train is a
  single long (probably looped) route of its own with one scripted vehicle, not ambient traffic.

### The overlay loop (mirrors the district loop, §3)

Each overlay is `overlays/Overlay_<Name>.blend` with two collections — `OVERLAY` (generated by
`overlays/build_<name>_overlay.py`, wiped + rebuilt every regen) and `MANUAL` (your hand-tuning
channel — seat/scale fixes, ramps, extra piers with `-colonly` proxies — **preserved** across
regens). Shared seat coordinates (e.g. the bridge's `BR_*`/`ISL_*` constants) live in
`lib/world_grid.py` so the master blockout, `slot_` anchors, and the overlay agree.

```bash
tools/build_overlay.sh rainbow_bridge          # generator form: regen (MANUAL survives) + export + bake
tools/build_overlay.sh Overlay_RainbowBridge   # stem form: BAKE-ONLY after hand-editing the .blend
```

**Residency:** the baked overlay `.tscn` is instanced as a **permanent node in
`hosts/WorldMaster.tscn`** (beside `Master` — the same always-resident model as ARTDECK), so it
never streams with the 504 m district grain. Wiring it there is a one-time step per overlay; a
rebake needs nothing else (same predictable path). Very large overlays can later switch to their
own long-span `WorldZoneMarker`s without changing the authoring side.

The first overlay: `Overlay_RainbowBridge` — the real PLATEAU span (joined to one mesh) + the
`-colonly` road/rail decks and piers that used to be the master's preview-only HARBOR blockout
(which never shipped; the blockout boxes were removed from `build_world.build_harbor`, the
`slot_rainbowbridge` anchor stays as the coordinate record).

---

## 6. PLATEAU data (extraction + real-terrain ground)

- Fresh extraction: `plateau/extract_plateau.py --precinct <name> --lon … --lat … [--dem <dirs>]`
  → `plateau/data/<precinct>.json` (buildings/roads/terrain in district-local metres). Raw CityGML
  lives outside the repo (`/data/danilko/plateau_model/`); see `plateau/ATTRIBUTION.md`.
- Add real DEM terrain to an **existing** extraction without disturbing it:
  `extract_plateau.py --augment data/<precinct>.json --dem <dirs>` (auto-picks the JIS mesh-code
  tiles; `--dem-radius` defaults to 380 m = full district-square coverage).
- **Terrain-as-ground rule:** if the stored terrain fully covers the district square
  (`terrain_covers_square`), the build uses the real DEM mesh as the ground and **skips the flat
  `GroundSafety` plane**; partial-coverage terrain keeps the plane underneath. Districts with no
  DEM source keep the plane as their only ground. Roads are draped onto the terrain sampler either
  way.

## 7. Roads, lanes, intersections & ambient traffic (road_kit_authoring)

> **Replaced (2026-07-27, road_blender_godot.md Phase 6):** the old generator-driven pipeline
> (`lib/road_graph.py`, `tools/save_roads.py`/`gen_roads_only.py`, hand-drawn `road_*` centerline
> curves + a `.roads.json` sidecar) has been removed entirely — no dual-path, no backward
> compatibility, every district regenerates through the addon below. See `road_blender_godot.md`
> Phase 6 (P6.1-P6.8) for the full migration history/design record.

Roads are built as **mesh-first pieces** with the `road_kit_authoring` Blender addon (dev-install:
`addons/road_kit_authoring/README.md`), not drawn as bare centerlines. Three piece types —
intersections, straight/curved segments, lane-count transitions — each carry the geometry AND a
permanent "how was this built" record as native Collection custom properties (`rka_*`, editable in
Blender's own Custom Properties panel, survives file close/reopen). `lib/intersection_kit.py`
(pure Python, no bpy, self-tested — `python3 lib/intersection_kit.py`) is the closed-form geometry
underneath every piece: corner-fillet junctions from a list of approach-arm angles, per-lane
offset segments from an arbitrary spine, lane-count tapers.

**The authoring loop:**

1. Open a district `.blend`. Use the addon's Sidebar (`N`) panel to build intersections
   (`Build Intersection`, presets 4-way/3-way-T/3-way-Y/N-way) and segments (`Build Straight
   Segment`, or `Extend From Arm`/`Extend From Port` off an existing piece's own marker/port —
   snaps zero-gap by construction). Drag a piece's own marker Empties to reshape it live
   (`live_edit.py`'s `depsgraph_update_post` handler rebuilds in place).
2. Collect every piece in the open `.blend` into one combined sidecar:
   ```bash
   blender districts/District_X.blend --background --python tools/save_lane_kit.py
   ```
   Writes `districts/District_X.lanekit.json` next to the `.blend` (same tool works unchanged for
   an `overlays/*.blend`, writing beside that instead). Prints an authoring-time connectivity
   lint (`lib/lane_kit.py`): `paired` (clean 1:1 connections), `isolated` (a dangling end —
   informational, a network boundary is legitimate), `ambiguous` (3+ candidates within
   `JUNCTION_RADIUS`, needs a look). Two pieces in DIFFERENT files (e.g. two neighboring
   districts) can be cross-checked the same way with `tools/check_lanekit_connectivity.py
   <a>.lanekit.json <b>.lanekit.json`.
3. Rebuild (`tools/build_piece.sh <config-name-or-stem>` / `tools/build_overlay.sh <name>`) —
   `bake_one()` auto-detects the `.lanekit.json` sidecar and wires it into `WorldBaker` as
   `lanekit_path`, no separate flag needed. Each lane becomes a native `Path3D`/`Curve3D`-backed
   `PathLaneRoute` (same `Lane` interface `VehicleRoute` implements — `LaneGraph`/
   `VehicleAIController` are fully polymorphic, so connectivity across pieces/files is
   **geometry-derived at runtime**: any two lanes whose baked endpoints land within
   `LaneGraph.JUNCTION_RADIUS` of each other connect, regardless of which piece/file built them).

   **One-click shortcut for steps 2-3** on a `District_<theme>_<gx>_<gy>.blend`: the panel's
   "Godot Export" box (top of the Sidebar) runs both commands for you in the background (a modal
   timer, so Blender's UI stays responsive for the ~20-40s bake) — watch the System Console for
   progress. Only enabled for a district saved in that exact stem form; an overlay or anything
   else still uses the two commands above by hand.

**Collision:** every piece already exports its own `-colonly` collision alongside the visual mesh —
`junction_pad` footprints (`kit_common.colonly_polygon`) and every `curb_loop()` (straight/curved
segments, lane transitions, per-corner intersection curbs, via `kit_common.colonly_swept`). This is
generated automatically by the normal build/rebuild operators; nothing extra to author. It is
**deliberately a separate mesh from the district's ground/terrain collision, never merged into it**
— roads (authored/regenerated via this addon) and ground (PLATEAU terrain, re-extracted from DEM
per district) change on independent schedules, and Godot's physics doesn't need one watertight mesh
for two overlapping static colliders to work correctly. Editing a road never requires touching the
ground mesh, and re-extracting terrain never requires re-authoring roads.

**Curb style, after the fact:** the panel's "Curb Style" button row (Left/Right ×
None/Box/Gutter/Asset, shown when a segment or lane-transition piece is active/selected) changes
curb style on an already-built piece and rebuilds in place — a persistent alternative to the build
operator's own F9 redo panel, which stops applying the moment any other action runs. For an
asymmetric ASSET curb mesh (authored to attach on one side only), use the SAME asset collection on
both Left and Right — the addon automatically spins the right-side row 180° (`curb_asset_rot_offset_r`)
so it still faces the correct way; no separate right-side asset or two-level gutter+curb split needed.

**Ambient traffic + zones:** every combined lane is tagged `zone_id` (the `.blend`'s own stem by
default, overridable per-piece via a manually-added `rka_zone_id` custom property) — a district's
master region marker sets `traffic_route` to that exact stem, matched by
`WorldZoneManager.findRoute`'s zone-id-equality pass (checked before its legacy name-prefix scan,
which still exists only for hand-authored `VehicleRoute` content that never went through this
pipeline). Re-run the master build (`towns/build_world.py`) after a district's first
`.lanekit.json` lands so the region marker's meta picks it up.

**Debugging:** F4 (`DebugHarness`) drops one AI car on every route in the scene (works in
`SoloPiece.tscn`); `WorldZoneManager.debugLog` prints per-zone `N cars, M moving, K routed`
(routed-but-0-moving = falling through missing ground); F3 (`RouteDebugOverlay`) renders every
`VehicleRoute`/`PathLaneRoute` in the scene, colour-coded.

## 8. Placing water & other gameplay objects (in Blender — never edit the baked .tscn)

Everything gameplay-flavoured is placed in the `.blend` as a **named object**; the WorldBaker
converts it by name. Hand-editing a baked `.tscn`/`.scn` is always wrong — the next bake
overwrites it. Put hand additions in `MANUAL` (survives regen, §2); the full name → node table
is in `BLENDER_CONVENTIONS.md` (I6a), the common ones:

| You place (Blender) | Becomes (Godot, at bake) |
|:--|:--|
| Empty `water_<id>` scaled/parented over a box (or with `size` custom prop) | `Area3D` in group `"water"` (swim volume) |
| Empty `spawn_<faction>_<n>` (+ `count` prop) | ambient-AI `SpawnConfig` on the zone |
| Empty `instance_<AssetId>` or any object with `asset_path = res://…` prop | scene **instance** of that asset (own collision/scripts) |
| `mmesh_<piece>` markers (generated, but same idea) | one `MultiMeshInstance3D` per asset |
| Mesh named `<Name>-colonly` / `-col` / `-convcolonly` | collision (invisible / visible / convex) |
| `road_kit_authoring` piece (+ combined `.lanekit.json` sidecar, §7) | `PathLaneRoute` lanes + junctions |

So: **water = drop a `water_<id>` marker in the blend and re-bake** — no `.tscn` editing. Same
for any future volume/marker type: add a prefix to the WorldBaker table once, then it's pure
Blender authoring forever.

## 9. Navigation (pedestrian navmesh) — what it's for, known warnings

- **Cars never use the navmesh** — they follow the explicit lane graph (§7). A navmesh has no
  lanes/direction, so it can't drive traffic; don't try.
- **Pedestrian AI uses one baked `NavigationRegion3D` per district**, baked by `NavBaker` from
  the district's own collision as part of `build_piece.sh`. This is the right tool here: AI must
  path around arbitrary real PLATEAU building layouts, which grid/waypoint graphs handle worse
  for more authoring effort. Alternatives only pay off elsewhere (flow fields for 100+-agent
  crowds; nav links for jumps/ladders — Godot supports those *on top of* the navmesh anyway).
- **"Navigation region synchronization had N edge error(s) / more than 2 edges tried to occupy
  the same map rasterization space"** — Godot merging the loaded navmeshes found coincident
  edges: typically two loaded districts' meshes meeting exactly at a seam, or coplanar surfaces
  (road slab on terrain) baked into one mesh. It is a **warning, not a failure** — the duplicate
  edge connection is dropped, agents still navigate. Act on it only if AI visibly stall at a
  border; remedies, in order: raise the bake `cell_size` in `NavBaker`, lower
  `navigation/3d/merge_rasterizer_cell_scale` (project settings), or silence it via
  `navigation/3d/warnings/navmesh_edge_merge_errors`. Districts abut by design, so occasional
  seam-edge merges are expected background noise.

## 10. Recycled building kit

`buildings/RecycledBuildingKit.blend` holds real PLATEAU buildings recycled as reusable assets —
**one top-level collection per placeable asset**. Place one by name from `MANUAL` (or via
`instance_`/`asset_path` markers); `buildings/PLATEAU_TokyoTower.blend` etc. are the hand-modeled
landmark equivalents (`build_district.place_landmark`). Streetwall/building solidity in procedural
districts comes from generated convex collision proxies (`lib/buildings.py`,
`_building_collision`), not per-visual-mesh collision — keep hand-added buildings on that diet
too: simple `-colonly` boxes.

## 11. Cross-district GPS & race courses (conventions — design notes, R2 not yet implemented)

The structural fact everything here follows from: **district content streams** (its
`VehicleRoute`/`PathLaneRoute` lanes register/deregister with `WorldZoneManager` on tree
enter/exit; anything baked into a district `.tscn` vanishes on unload), while the **ARTDECK
collision deck + safety floor are always resident** in the master (P6.8: the old arterial LANE
backbone over that deck was removed — see §7 — so today the deck is collision-only; an overlay,
§5, is the always-resident place for a real map-spanning lane network, e.g. a highway). Cross-
district features must lean on the always-resident layer or on pure data — never on live nodes
inside a district that might not be loaded.

### GPS

- **Today (I5, done):** the waypoint is a world-XZ position in `WaypointStore`, drawn by
  radar-style widgets (minimap blip clamp + crosshair arrow). Nothing is per-district, so it
  already works across the whole map — straight-line guidance only.
- **Turn-by-turn upgrade (planned):** do **not** pathfind over live `VehicleRoute`/`PathLaneRoute`
  nodes — unloaded districts have none. Every district's `.lanekit.json` sidecar (§7,
  `tools/save_lane_kit.py`) already holds its junction/lane graph as engine-free JSON at build
  time; bake all of them into one always-resident manifest resource and A* over it: an overlay's
  lanes (§5, e.g. a highway) give the inter-district legs, a district's own combined sidecar
  refines the first/last mile — the same "prefer a highway/overlay path when one exists, else
  district-to-district local roads" preference recorded in road_blender_godot.md P6.5. Draw the
  result as a minimap polyline. (PLAN.md I6 note: Blender-authored waypoints ride the same bake
  path.)

### Race courses (R2 design, PLAN.md)

- **Checkpoints must not stream.** A `race_<id>_<idx>` empty baked inside a district `.tscn`
  disappears mid-race when that district unloads. A cross-district course therefore lives in an
  **overlay** (§5 — exactly the "long-span content that must never chop at the 504 m grain" case,
  same precedent as highway/train), or `RaceDirector` holds checkpoint *positions as data* and
  spawns the `Area3D`s itself for the race's lifetime.
- **AI racers survive unloaded districts** because ARTDECK + the safety floor guarantee ground
  everywhere — an arterial-backbone race works with zero streaming concern. A race line through
  district *interiors* needs those districts loaded: racers cluster near players so proximity
  streaming mostly covers it; the safety net is a small `RaceDirector` → `WorldZoneManager`
  "pin these zones while the race runs" extension.
- **The AI racing line is the same authored-curve pipeline** — a `VehicleRoute` drawn along the
  course (in the race overlay for cross-district courses), driven by `VehicleAIController`
  verbatim. Replication is host-authoritative checkpoint grants over the existing world-event
  seam.
