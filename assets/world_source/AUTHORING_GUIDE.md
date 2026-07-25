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
2. **Road sidecar `districts/<piece>.roads.json`** — internal traffic spines are hand-drawn
   curves, round-tripped through a git-diffable sidecar: draw `road_<name>` curves, set
   `lanes`/`oneway`/`class` props, run `tools/save_roads.py`, rebuild. Full loop + junction
   rules in §7.
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

## 7. Roads, lanes, intersections & ambient traffic (the blend road system)

> **Superseded, in progress (2026-07-22):** this generator-driven pipeline is being replaced by a
> mesh-first kit-piece + hand-authored-centerline pipeline — see `road_blender_godot.md` at the
> repo root for the plan/phase tracker and `addons/road_kit_authoring/README.md` for the new
> Blender addon. Existing districts on this system keep working unmigrated; don't extend
> `road_graph.py` further.

Everything cars do is **generated from centerline curves you draw** — you never place individual
lane markers, connectors or intersection zones by hand. `lib/road_graph.py` turns centerlines
into per-lane directional routes, junction turn connectors and intersection markers; the baker
turns those into runtime `VehicleRoute`/`IntersectionZone` nodes.

### Drawing a district's roads (the sidecar loop)

1. Open `districts/District_X.blend`. Previous road curves are already there as editable POLY
   curves in the `ROADS_SRC` collection (rebuilt from the sidecar every regen).
2. Draw one **curve per road centerline**, named `road_<name>`, over the PLATEAU road meshes
   (poly or bezier; one spline per object). Set per-curve **Custom Properties**:
   - `lanes` — lanes **per direction** (default 1). `lanes = 2` ⇒ a 4-lane two-way road.
   - `oneway` — bool (default False). A one-way road gets `lanes` forward, none reverse.
   - `class` — `'local'` / `'arterial'` / `'oneway'` (default `'local'`); a road-tier tag.
   - `median` — physical divider width in metres (float, default 0). Each direction's lane pack
     shifts outward by `median/2`, clearing a center strip for a median bump mesh (see "Divided
     roads" below).
3. **Junction rules (how curves connect):** endpoints within **2 m** of each other cluster into
   one junction node. A **T-junction** = the side street's *endpoint* within 2 m of an *interior
   vertex* of the through road (the through curve is split there automatically — don't split it
   yourself). A crossroads = four curve ends (or two crossing curves whose ends touch interior
   vertices) meeting within 2 m. A curve end that touches nothing is a dead end (cars despawn
   there — fine at map edges, a bug in the middle of town).
4. Save the curves to the git-diffable sidecar (the `.blend` is disposable; the sidecar is the
   source of truth):
   ```bash
   blender districts/District_X.blend --background --python tools/save_roads.py
   ```
5. Rebuild the district (`tools/build_piece.sh <config-name>`). The regen re-imports the curves
   into `ROADS_SRC` **and** generates the traffic layer from them.
6. **First sidecar for a district only:** re-run `tools/build_world.sh` once — the master build
   checks for the sidecar and flips that region marker's `traffic_route` meta from `"art_"`
   (arterials-only) to `"<piece>__"` so ambient traffic actually uses your new internal roads.

**Hand-authored blends (no CONFIG entry — kit demos, fully hand-modeled pieces):** the stem-form
bake skips the regen, so nothing would turn your curves into lane markers. Run the standalone
generator instead — it collects the local `road_*` curves, wipes only this piece's old
`lane_`/`intersection_` markers, regenerates the traffic layer under the piece's route prefix and
re-saves the sidecar, all in place:

```bash
# the hand-authored loop
#   draw/edit road_* curves in the blend, then:
blender districts/District_X.blend --background --python tools/gen_roads_only.py
tools/build_piece.sh District_X          # stem form, bake-only
# SoloPiece walk-test; F4 = a car on every route
```

(`-- --no-sidecar` skips the sidecar re-save if you're mid-experiment and don't want the JSON
touched yet.)

### What gets generated (so you can read the result)

- **Per-lane directional routes** `lane_<piece>__<edge>_<F|R><lane>_<n>` — keep-left offsets from
  your centerline, one route per lane per direction, trimmed back at junction stop lines.
- **Turn connectors** `c<node>_<in>_<turn>` — bezier curves through each junction box carrying
  `turn` (L/S/R) + `approach` (N/E/S/W) metas. Turning is a data lookup: each lane end stamps
  `next_routes` (its connectors) + straight-biased `next_weights` (0.6/0.2/0.2).
- **Keep-left lane legality** (the multi-lane rules, applied automatically): a 1-lane approach
  may turn L/S/R; on a ≥2-lane approach the **curb lane (lane 0) turns left or goes straight**,
  the **median lane turns right or goes straight**, middle lanes go straight only.
- **`intersection_<id>` markers** → runtime `IntersectionZone`s: first-come-first-served
  single-occupancy arbitration (cars yield until the junction clears). Timed signals + concurrent
  non-conflicting movements are Roads-v2 Phase 2 (see PLAN.md). AI also self-limits throttle near
  junctions and on L/R connectors, so 90° turns are taken slowly.

### How much traffic spawns where

Per-district car count rides on the master's region markers: `traffic_count` (base number of
cars) scaled by the region's `vehicle_density`, spawn lanes chosen round-robin from all routes
matching the `traffic_route` prefix whose entry is in range (that spread IS the multi-lane spawn
distribution). Cars despawn at route end / out of player range and the zone tops back up — GTA
disposable traffic, not persistent agents.

### Debugging traffic

- **F4** (DebugHarness) drops one AI car on every `VehicleRoute` in the current scene — works in
  `SoloPiece.tscn` for a quick check of a district's authored lanes. Headless/scripted: launch
  with `-- --spawn-all-routes` to auto-fire it ~3 s after scene ready.
- `WorldZoneManager.debugLog` prints per-zone `N cars, M moving, K routed` — routed-but-0-moving
  = cars falling through missing ground; a steady stream of `route-finished` reclaims away from
  map edges = broken junction wiring (usually a curve end that missed the 2 m snap).
- `tools/build_debug_preview.py` to eyeball generated lane empties over the road meshes in 3D.

### Where the `lanes` / `oneway` / `class` / `median` properties live (exact spot — easy to get wrong)

They are **Custom Properties on the curve OBJECT**, not on the curve data:

> select the `road_*` curve → Properties editor → **Object tab** (orange square) →
> **Custom Properties** panel → add `lanes` (integer, e.g. `2`).

`save_roads.py` reads `ob.get("lanes")` — a property added on the **Object Data** (green curve)
tab is silently ignored and the road stays 1-lane. Curves re-imported into `ROADS_SRC` by a
rebuild already carry the properties (stamped by `import_roads_src`), so for an *existing* road
you just change the value; only a *newly drawn* curve needs the property added by hand (missing
= defaults: `lanes 1`, `oneway False`, `class 'local'`).

Alternatively edit the number **directly in the sidecar JSON** (`"lanes": 2` in
`districts/<piece>.roads.json`) and rebuild — equivalent, since the sidecar is the source of
truth. Just don't run `save_roads.py` from a stale `.blend` afterwards (it would overwrite your
JSON edit); rebuild first, then the re-imported curves carry the new value and the round-trip is
consistent.

### Worked example: multi-lane + junction demo (District_industry_5_1, 2026-07)

The reference setup for showing multi-lane traffic + junction turn legality, chosen because
Keihinjima is the only district with a sidecar already wired (master `traffic_route` meta already
flipped to `District_industry_5_1__`), is flat (bay-island DEM), sparse (16 buildings/450 m —
clear sightlines to watch cars), and the traffic debug tooling (Shift+F5 hot-reload, F3 route
overlay, `--auto-walk`) was built around it.

- **The whole change was two sidecar numbers:** `road_spine` (arterial) and `road_north_st`
  bumped `lanes 1 → 2`. Because `road_north_st`'s endpoint already touches an interior vertex of
  `road_spine` at (204, 146), the existing T-junction became a multi-lane junction with the
  keep-left legality rules active (curb lane L+S, median lane R+S) — junctions need **no** setup
  beyond curve topology + lane counts.
- Rebuild (`tools/build_piece.sh industry_5_1`) then reported `lanes=16 connectors=10
  junctions=1` (was 8 all-single-lane lanes), and the bake produced 32 routes + 1
  `IntersectionZone`. Headless verify (`WorldMasterDebug.tscn -- --auto-walk=industry_5_1`):
  zone streams in, spawns round-robin across both forward lanes (`…spine_s0_F0` / `…spine_s0_F1`).
- **Known tweak target:** occasional `fell-out` reclaims — the outer lane sits
  `(1+0.5)×3.5 = 5.25 m` off the centerline and clips the pavement edge in spots. Fix by nudging
  the `ROADS_SRC` centerline (or widening ground) in Blender, not by touching generated lanes.
- **To grow the demo into a crossroads:** draw a 4th `road_*` curve whose endpoint lands within
  2 m of (204, 146), set its `lanes` custom property (Object tab, see above) to 2 if it should be
  multi-lane, then `save_roads.py` → `build_piece.sh industry_5_1` → walk-test in
  `SoloPiece.tscn` (F4 to flood the routes, F3 overlay to see them).

### Adding intersections & ramp-style lane splits (what's manually controllable today)

**An intersection is never placed — it is derived from curve topology.** Any node where ≥2 curve
arms meet (ends within 2 m, or an end on a through road's interior vertex) automatically gets:
stop-line trimming on every arm (auto radius = half the widest crossing carriageway + 1 m — only
code-built graphs like the master backbone can override it via `radius_fn`), the legal turn
connectors, and one `intersection_` box → a runtime `IntersectionZone` (FCFS single-occupancy:
first arrival holds the junction, other AI queue behind it; **players never yield**). There is no
per-junction knob in the sidecar; your levers are topology, `lanes`, and `oneway`.

**The "one lane exits to a ramp while the rest continue" case — supported now, via geometry:**

1. Draw the ramp as its own curve (e.g. `road_ramp_x`), custom props `oneway=True`, `lanes=1`,
   with its **start point within 2 m of an interior vertex** of the main road — the main road
   auto-splits into a fork node there.
2. **Make the ramp's first segment depart at ≥45° to the LEFT** (keep-left: exits are curb-side).
   The movement then classifies as `L`, and keep-left legality does the split for you: **only the
   curb lane (lane 0) gets the ramp connector** (`next_routes` = [L→ramp, S→continue], weighted
   0.2/0.6); every other lane gets only the straight connector and continues. After the ≥45°
   departure the ramp can curve back to run parallel.
3. **Pitfall — a shallow gore-style departure (<45°) classifies as `S`**, and the straight
   lane-clamp (`want = min(in_lane, out_lanes-1)`) then maps *every* main-road lane onto the
   1-lane ramp as a second "straight" option — all lanes may exit, not just one. Until Phase 3
   gores exist, always author the exaggerated-angle departure.
4. Merging back: end the ramp within 2 m of the target road (its end, or an interior vertex).
   The merge node gets connectors plus its own `IntersectionZone`, so ramp traffic FCFS-yields
   into the target road — crude but functional.

**Not controllable today (this is exactly R Phase 2/3, PLAN.md):** per-junction traffic share
("10 % take the ramp" — `TURN_WEIGHTS` in `lib/road_graph.py` is a global 0.6/0.2/0.2 constant),
suppressing the stop-box/throttle-clamp at a gore (through lanes are always trimmed and AI always
ease off, so free-flow highway exits aren't possible yet), per-route `speedLimit`, and signal
timing. Cheapest extension if needed before Phase 3: a per-curve custom prop (e.g.
`class='ramp'` or a `weight` prop) read at the `TURN_WEIGHTS` lookup in `road_graph.generate()`
to bias ramp uptake per fork. As always: never hand-edit the generated `MARKERS` lane
empties/connectors or the baked `.tscn` to "fix" a junction — wiped on every rebuild.

### Divided roads (physical median) & road-kit pieces: one centerline or two?

Two facts drive this decision:

- **A two-way curve's centerline is the paint line between directions** — each direction's lane
  pack sits keep-left of it at `(i+0.5)×3.5 m`. There is **no median-width parameter**: with a
  physical median bump, the inner lanes (±1.75 m) would drive through it.
- **A `oneway` curve is NOT the middle of its carriageway** — keep-left offsets put **all** lanes
  strictly LEFT of the curve in travel direction (`_lane_offset_from_center` is always negative).
  A oneway curve is therefore the **median-side edge** of its carriageway. Curve point order =
  travel direction (flip in Edit Mode → Segments → Switch Direction).

**The three models, and when to use each:**

1. **Undivided road (painted centerline only):** one two-way curve. The current model — junctions
   just work. Use for everything without a physical divider.
2. **Divided road via two anti-parallel `oneway` curves** — works today, zero code. Draw both
   curves hugging the median (one per direction, opposite point order); lanes fan out curb-ward
   automatically. Junction endings need a decision:
   - *Pinched* (both carriageway ends within 2 m of the cross street → ONE node): compact
     junction — but forward/reverse are now **different edges**, so the generator's "no U-turn
     back onto the same edge" exclusion no longer blocks the cross-median U-turn: U-turn
     connectors ARE generated, and with near-antiparallel headings their L/R classification is
     geometry-jitter-dependent. Sometimes wanted (GTA-style median U-turns), otherwise noise.
   - *Separated* (ends > 2 m apart → two T-nodes on the cross street): the wide-median model —
     each carriageway crossing is its own `IntersectionZone`, cross traffic clears them one at a
     time, no U-turn connectors. More nodes, more realistic for wide medians.
3. **`median` width prop on a single centerline** — **built (2026-07)**: a per-curve `median`
   custom prop (metres, float, default 0) carried through `save_roads.py` → `from_curves` →
   `generate()`, shifting each direction's lane pack outward by `median/2` (lane offset formula:
   `median/2 + (i+0.5)×3.5`; junction stop-line radius grows by `median` too). One curve stays
   the authoring unit, junction generation and the U-turn exclusion stay sane, turn connectors
   span the median automatically. **Preferred for a modular road-kit piece with a uniform median
   bump** — the kit mesh stays symmetric about the single centerline and the prop matches the
   kit's median width parametrically.

**Recommendation:** for the planned road kit, extend the generator with the `median` prop
(option 3) and keep one centerline down the middle of the kit piece; reserve dual-oneway
carriageways (option 2) for where the directions genuinely diverge — elevation splits, highway
carriageways, ramp gores (Phase 3 territory).

**Kit-piece alignment rules:** the visual road mesh and the traffic curves are **independent
layers** — nothing in the generator reads the mesh; alignment is pure authoring convention. Size
the kit piece as `2 × lanes × 3.5 m + median width` so generated lanes land on pavement; give the
median bump its own `-colonly` proxy (it must block cars); place kit pieces from `MANUAL` via
`instance_<AssetId>` / `asset_path` markers (§8/§10) and draw the `road_*` centerline down the
piece's middle.

### Worked example: divided-road demo (District_kitdemo_9_9)

`districts/District_kitdemo_9_9.blend` demos all three models side by side, each crossed by a
N–S street so junction behaviour is exercised too. It is **fully generated** by
`tools/build_kitdemo.py` (run `blender --background --python tools/build_kitdemo.py` to
regenerate from scratch), coordinates `9_9` = off the 6×6 world grid, so it is never referenced
by a master region marker — walk-test it solo:

```bash
blender --background --python tools/build_kitdemo.py     # (re)generate blend + markers + sidecar
tools/build_piece.sh District_kitdemo_9_9                # stem form, bake-only
# run SoloPiece.tscn, press F4 (or launch with `-- --spawn-all-routes`)
```

Layout (flat ground slab, top z=0):

| model | curves | where | what to look at |
|---|---|---|---|
| 1 plain two-way | `road_plain` lanes=1 | y=+60 | lanes at ±1.75 m of the centerline |
| 2 dual oneway + bump | `road_dual_e`/`road_dual_w`, oneway, y=±5 | bump at ±1.5 m | each curve is the median-side EDGE of its carriageway (lanes land at y=±6.75); opposite point order = opposite travel; 10 m apart ⇒ the cross street forms **two separate T-nodes** (the "separated" model — no U-turn connectors) |
| 3 single centerline + `median=3.5` | `road_median` | y=−60, bump −61.5..−58.5 | lanes at ±3.5 m clear the bump; junction stays single-node |

The cross street is drawn as **per-crossing segments** (`road_xa`..`road_xe`) whose endpoints
land on the through roads' interior vertices — that is the junction contract in practice (a
plain mid-curve crossing creates NO junction; an endpoint within 2 m of an interior vertex
splits the through road). Everything is hand-adjustable: tweak curves/props in Blender, then the
`gen_roads_only.py` → `build_piece.sh` loop above.

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
| Curve `road_<name>` (+ props, via sidecar §7) | `VehicleRoute` lanes + junctions |

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
`VehicleRoute`s register/deregister with `WorldZoneManager` on tree enter/exit; anything baked
into a district `.tscn` vanishes on unload), while the **arterial backbone + ARTDECK collision
deck + safety floor are always resident** in the master. Cross-district features must lean on the
always-resident layer or on pure data — never on live nodes inside a district that might not be
loaded.

### GPS

- **Today (I5, done):** the waypoint is a world-XZ position in `WaypointStore`, drawn by
  radar-style widgets (minimap blip clamp + crosshair arrow). Nothing is per-district, so it
  already works across the whole map — straight-line guidance only.
- **Turn-by-turn upgrade (planned):** do **not** pathfind over live `VehicleRoute` nodes —
  unloaded districts have none. `lib/road_graph.py` already holds the junction-node/edge graph as
  engine-free data at build time; bake that into an always-resident manifest resource and A* over
  it: arterials give the inter-district legs, a district's internal graph refines the first/last
  mile. Draw the result as a minimap polyline. (PLAN.md I6 note: Blender-authored waypoints ride
  the same bake path.)

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
