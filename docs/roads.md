# roads

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Road Kit — option B: author in Godot, solve and mesh in python3 (2026-09-13; no Blender since B11, 2026-09-16)
- Edge lines, shoulders and median strips; a 踏切 keeps its own panel (2026-10-05, user-asked)
- Street trees are ROAD FURNITURE, one species per street (PLAN.md 3.16 step 4, 2026-09-20)
- Road types, the interchange templates, one sea bridge (PLAN.md 3.13 step 1, 3.8 steps 3-4, 2026-09-18)
- Traffic is a ring and a budget; hotspots are found by postal code (2026-09-22, PLAN.md 3.32 / 3.26)
- The island's road layout is DERIVED: arterials in, expressway, trunk grid, streets and turnarounds out (PLAN.md 3.13 steps 2-5, 3.3, 3.3b, 2026-09-19)
- Every grade break is rounded, and what is left is named (PLAN.md 0.7, 2026-09-20)
- The north-west coast road: a bench cut into the cliff, with rock sheds (PLAN.md 3.15, 2026-09-19)
- "Has the world finished streaming" has ONE owner; nothing solid stands in a carriageway (PLAN.md 3.35, 2026-09-22)
- 踏切 rules for traffic, a breakable 踏切 unit, the far traffic tier, the Deck perf proxy (2026-10-05)
- Expressway guide signs, and every displayed name is fictional (2026-09-30)
- A vehicle entry is a dropped kerb (切り下げ), authored per station (2026-10-04, user-asked)
- Asphalt from kerb to door; a paved site's edge slopes (2026-10-05, user-asked)
- The expressway as of 2026-10-01: a complete Wangan, a lane-split T at the spur, all four movements at both JCTs
- 横断歩道橋: footbridges over the widest junction arms, measured in Blender, placed from the lane records (2026-10-10, user-asked)
- 電柱 + wires, lamps up the mountain road, white ガードレール (PLAN.md T1 + part of T3, 2026-10-11, user-asked)
- Right-hand traffic is the keep-left lane graph run backwards (2026-10-12, user: "drive on the right")

---

## Road Kit — option B: author in Godot, solve and mesh in python3 (2026-09-13; no Blender since B11, 2026-09-16)

Supersedes road-generator, which is now removed (PLAN.md 3.1; see the section below). The Blender road kit's
solver was kept and its authoring moved into the Godot editor, where zones, Terrain3D and building
scenes live. **Three owners, one contract (`.roads.json`, the kit's `point_model` schema, Z-up):**

| layer | where | what |
|---|---|---|
| authoring | `addons/road_kit/` (GDScript editor plugin) | `RoadKitNetwork` → `RoadKitRoad` → `RoadKitPoint` nodes; a road's CHILD ORDER is its chain; links by uid; the dock's gestures (`road_kit_gestures.gd`, pure functions, headless-testable); overlay of the solver's resolved centrelines; undo = restore the record |
| rules | `blender/tools/roadkit_cli.py` (plain python3) | `validate`, `setback`, `centrelines`, `lanekit`, `ramp` over the record, using the kit's existing pure modules — no Blender |
| meshes | `blender/tools/roadkit_cli.py gltf` (plain python3, B11) | `point_mesh` sweeps, `point_gltf` writes the piece `.gltf`, then `GLTF_READY=1 build_piece.sh` bakes it (WorldBaker, NavBaker); `build_roads_piece.sh <record> <Piece>` runs every step. Until B11 this was headless Blender (`roadkit_build_mesh.py` + `point_build`, deleted) |

Rules that came with it, each measured:
- **The field table is GENERATED** into `road_kit_fields.gd` (`blender/tools/gen_roadkit_godot_fields.py`,
  `--check` fails when stale). A second hand-copied table is the drift the kit's own field-table rule
  exists to prevent.
- **Coordinates convert in ONE GDScript place** (`road_kit_frame.gd`, kit `(x,y,z)` → Godot
  `(x,z,-y)`, mirroring `point_export.godot`). Record positions are in the NETWORK node's frame,
  composed from local transforms, so import/export works outside the scene tree. Gate:
  `test_roadkit_record.gd` + `compare_roads_records.py` — 0 differences on the sample network, and
  the lanekit from the Godot-written record equals Blender's export (worst delta 0.0).
- **Solver facts are never re-derived in GDScript.** A ramp's mouth position, carriageway and taper
  opening are `roadkit_cli.py ramp` (a port of `Make Ramp` + `open_aux_slot` + `Align Ramp To Aux`
  over the record); the GDScript `make_ramp` that guessed them was deleted.
- **Sibling scripts are referenced by PRELOAD, never by `class_name`.** A headless `--script` run
  and a fresh checkout have no global class cache; a `class_name` type hint then fails to parse and
  the script is dead (read as a hang, since the error aborts before `quit()`). Parse-check addon files
  with `godot --headless --check-only --script res://<file>` — verified to catch a strict-typing error.
- **Ground heights come from Terrain3D** (`Gestures.sample_ground`, before every service call), and
  must be the NATURAL ground: stamping road corridors into the height map comes after sampling, or
  the kit's CARVED_FLAG trap returns. Blender keeps a record height when its scene has no terrain.
- Gates: `test_roadkit_record.gd`, `test_roadkit_gestures.gd` (16/16 — a gesture-authored network
  passes the kit's gate with 0 errors and exports 34 lanes), `test_roadkit_ground.gd` (3/3).
  Still to build (PLAN.md 3.1): corridor stamp into Terrain3D (B7), the remaining gestures and
  gizmos (B8), retiring the Blender authoring UI (B9).

**Zones (B6, 2026-09-13): author ONE network, let the build cut it.** The dock's Build writes the
scene's ZoneMarkers to `<stem>.zones.json` (`road_kit_zones.gd`: each centre in the NETWORK's frame,
kit axes, `Zone.size`'s XZ footprint as the box) and `build_roads_piece.sh <record> Roads_<net>
<zones.json>` builds one piece per zone. `point_zones.py` is the ONE owner of the cut, asked by both
the lane export (`roadkit_cli.py pieces`) and the mesh build (`point_build.build_network(part=,
zone=)`), so tarmac and lanes cannot land in different pieces. Rules: a station is in the SMALLEST
box containing it, else the nearest centre within `load_radius`; a **RUN** (not a road — a long
arterial is cut at its own crossings, never mid-carriageway) takes its road's authored `zone_id` if
that names a marker (else reported `zone_id_unknown` and derived), else its stations' majority; a
pad goes with its clique centre; a gore with its ramp's run; anything in no zone goes to the
resident piece `Roads_<net>`, which is exactly the old single-piece build. The **whole** network is
still solved per piece — a kerb beside a ramp is a fact about both roads — and only emission is
filtered: measured on the sample, 81 objects = 52 + 29, every one byte-identical in vertex count and
position sum to the unzoned build, and the unzoned lanekit is unchanged byte for byte. A lane's
`zone_id` is its zone, so a `VehicleSpawnConfig.route_name` of the zone id spawns on exactly that
zone's lanes (`ZoneManager.spawnLanes`' zone-id pass). Successor names cross pieces untouched; the
lane registry is global, so they resolve whenever both pieces are loaded.
- **A cut piece is placed in the NETWORK's frame, not its marker's.** `ZoneManager` parents a zone's
  geometry under the marker, which is right for a district authored about its own centre and put the
  sample's pieces **1403.6 m** off (the probe's control). `Zone.geometryWorldPlaced` +
  `geometryWorldTransform` (written by the dock from the network's global transform) and
  `Zone.placeGeometry` — the one placement rule, used by the streamed tier, the LOD-low tier and
  `WorldPreviewBuilder` — so dragging a marker never drags the road. Moving the NETWORK needs a Build.
- **Wiring** (`plan_wiring`, one undo step): a Zone takes its piece's scene path and the placement; a
  Zone already streaming something that is not one of this network's pieces keeps it and is reported
  (one geometry per zone); a Zone whose road piece this build did not produce is CLEARED, so a stale
  piece file cannot stream roads that are gone; the resident piece is reported, never silently lost.
- Gates: `point_zones.py` self-test (in `check_roads.sh`, now 19), `test_roadkit_zones.gd` (17/17 with
  a build log: the committed `hosts/RoadKitZones.tscn` needs ZERO wiring changes), and
  **`probe_road_zones.gd`** (12/12): both pieces stream and sit at the network's transform, every lane
  starts where its lanekit says (0.0000 m), every successor resolves with both loaded, a car hands
  over from the west pad's connector onto an east lane, walking away unloads west and leaves exactly
  the 6 east→west successors unresolved, and walking back resolves them all. `-- --control` (marker
  frame) fails 4 of them.

**Ground (B6b, 2026-09-14): a support stands on the ground under EACH SAMPLE, and the ground is
Terrain3D's.** The kit decides NONE/FILL/PIER every 4 m from `surface_z − ground_z`
(`point_solve.solve_road`) with `ground_fn` as the sampler — a raycast into the Blender scene. A road
authored in Godot is built in a Blender session with NO terrain, so every sample missed and fell back
to a lerp of its stations' `ground_z`: DebugRoads' `link` (3 stations, 20.9 m over the gap the user
dug between the islands) had **no support at all** — its stations were draped to the old ground, so
the lerp read 0.1 m everywhere. Now the dock's Build (and `tools/godot/write_roadkit_ground.gd`)
samples Terrain3D on a 2 m grid over the network's footprint + 60 m (`road_kit_ground.gd`, network
frame, kit axes, float32 `<stem>.ground.bin` + `<stem>.ground.json`; 424×180 in 58 ms), and
`point_ground.GroundGrid` — bilinear, a NaN cell or the outside is a MISS (None), never 0 — is passed
as `build_network(ground=)` (`rka.point_build(ground_path=)`, then `roadkit_build_mesh.py --ground`; since B11 `point_mesh.build(ground=)` / `roadkit_cli.py gltf --ground`,
`build_roads_piece.sh`'s 4th argument). The road's own heights are NOT re-draped: the support is
derived from the gap, which is the point. Rules:
- **The kit sweeps no embankment.** `road_support` sizes a FILL toe and nothing builds it, so a road
  0.4–4 m over the ground floats until the terrain carries it (B7's stamp). The gate reports FILL
  (120 samples on DebugRoads, mostly `spur`) and does not assert it.
- **A span over a cliff edge is carried by the edge.** Pillars are laid at `PIER_SPACING` along the
  carrier, so the first column can be 30 m in from where the ground falls away; the gate accepts a
  PIER sample within 18 m of a column foot on the terrain OR of ground rising to within `FILL_MAX` of
  the deck.
- `write_roadkit_ground.gd` also re-samples each station's `ground_z` into the record, as every dock
  service call does (a pad reads its mouths' station ground); on DebugRoads that moved exactly one
  station, link's middle one, 10.36 → −10.40.
- `<stem>.ground.bin` is un-ignored (`.gitignore` ignores `*.bin`) and LFS-tracked: once B7 has
  stamped a network it is the ONLY record of the natural ground under its roads.
- The grid is snapped to multiples of its step in the network frame, so on an unrotated network every
  sample IS a Terrain3D vertex (2 m) and B7's restore is exact.
- Gate **`tools/godot/probe_road_ground.gd`** (instances every ZoneMarker's road piece where
  `Zone.placeGeometry` puts it, walks every lane every 4 m against Terrain3D, reads column feet off the
  baked `__surface` meshes): **213/213** pier samples supported, no column stopping short of the
  ground; the same pieces built without the sidecar: **111/213**. `probe_traffic_spawn.gd` 6/6
  (a car still drives `link`), `probe_road_zones.gd` 12/12, `check_roads.sh` PASS=20.

**Seeing it while editing (B6c, 2026-09-14).** A built road is instanced by `ZoneManager` at runtime
and a `ZoneMarker`'s box is runtime-only too, so the editor showed neither. The dock's **Preview
Pieces** (`road_kit_preview.gd`) instances every Zone's `geometry_path` (plus a resident
`Roads_<network>` piece) under ONE `top_level`, UNOWNED node, placed by `Zone.placeGeometry`'s rule
re-stated in GDScript (the Java is not `@Tool`); an unowned node is not written by `PackedScene.pack`,
and the gate proves it with a control that gives the node an owner. It re-reads the scenes
(`CACHE_MODE_REPLACE`) after each Build. **Refresh Preview** now passes `--zones` (written to
`user://`, never over the build's own sidecar) and `roadkit_cli.py centrelines` answers per run
`zone`/`beyond` and the `cross` successor lanes from `point_zones` — the overlay colours, never
decides. Gate `test_roadkit_preview.gd` 12/12; how-to in `addons/road_kit/README.md`.

**The roads are written into Terrain3D (B7, 2026-09-14): carve AND fill, derived from the natural
ground.** `road_kit_stamp.gd` (dock **Stamp Terrain / Restore Terrain**, headless
`tools/godot/stamp_roadkit_terrain.gd`) sets every terrain vertex near a road from the network's
natural-ground sidecar and `roadkit_cli.py corridors` — `point_edges.band_corridors` (moved out of
`point_build` with `solve_all`, which alias them, so the CLI needs no bpy), each point carrying the
natural ground and `road_support.support_kind`. Inside a corridor's paved half-width + `VERGE` (6 m:
a 4 m footway + one 2 m cell) the ground is the road surface − 5 cm; outside, a 1:1 cut batter and a
1:1.5 fill batter. Rules, each a measured defect first:
- **FILL, where the island's `Carve` is carve-only.** Its reason — "`road_support` owns FILL and builds
  the embankment" — is false in the kit: `rka_fill_w` is computed and nothing sweeps it. A Terrain3D
  world's height field is the only thing that can carry a road 0.4–4 m up. The bay-fill hazard is kept
  away by classification: a corridor point may fill only if it is not PIER/TUNNEL (the nearer end of
  a segment decides).
- **A fill batter runs until it meets the ground**, never to a fixed toe (a toe cut-off stood a
  20.8 m wall beside DebugRoads), and **only the NEAREST corridor fills** (the max of every corridor's
  floor spilled the last fill before a bridge 30 m under the deck: 116 of 199 clear-span samples
  buried → 2).
- **Each corridor is its nearest segment.** Every segment in reach measured a graded road's further
  segments from their end caps and capped the ground at the lowest (0.75 m of air under `loop`).
- **On a road the road decides; off every road the batters do.** In a band the ground is the nearest
  corridor's surface, capped by any corridor within one terrain CELL of standing on it or more than
  `UNDERPASS` (3 m) below (a street under a deck) — a hairpin's lower leg must not cut under the
  upper leg, a junction's lower approach not under the pad.
- **`band_corridors` had never included a pad**, though its docstring said so: a pad band is a ring
  plus mouths, so `len(poly) == 2 * len(spine)` skipped every one. `_pad_corridors` fans spokes from
  the centre to a ring resampled at 3 m (spokes to the raw ring let a 18 m cap edge claim 9 m of the
  approach road), heights by `point_solve._idw_z` along each spoke. This also changes the island
  carve's input (`build_island_base`), which has not been rebuilt since.
- **Idempotent by construction and reversible:** heights derive from the natural sidecar, the vertices
  the previous stamp reached (`<stem>.stamp.json`) are re-derived too, and a stamp record makes
  `road_kit_ground` read the sidecar as the ground where it covers (the CARVED_FLAG trap), and refuse
  to sample at all if the record exists and the sidecar does not. Restore puts the natural ground back
  and deletes the record.
- Gate **`tools/godot/probe_road_stamp.gd`** on the saved DebugWorld terrain: no ground proud of any
  lane (0.05 m) or pad mesh vertex (0.15 m) — 0; every lane the kit calls FILL at grade on the stamped
  ground 132/132 (natural ground, the control: 0/132); clear-PIER samples still over the natural ground
  190/192; stamping again changes 0 vertices; restore worst 0.0000 m. 14 103 vertices touched (raise
  histogram ≤4 m 3369, 4–8 m 1384, 8–16 m 322, >16 m 56 — the abutment spill cones). B6b's
  `probe_road_ground.gd` still passes on the stamped terrain (202/202). `check_world_envelope.gd`'s
  "mesh box matches the collision box" FAIL on DebugWorld is pre-existing (same on the unstamped terrain).

**The remaining gestures (B8, 2026-09-14).** Every rule that is not a plain node edit lives once, in
`blender/addons/road_kit_authoring/point_record_ops.py` over `NetworkData` (pure python3, self-tested,
in `check_roads.sh`), reached through `roadkit_cli.py merge|split|renumber|repair|tidy|cross_section|
branch_ramp|facings|flow`; the dock runs each as `Service.record_gesture` — save (promoting rotated
points), run, reload, face — in ONE undo step. B9 retires the Blender operators these restate, so this
module is the owner. The Preview panel's flow report moved to pure `point_flow.py` (`point_preview`
imports it back). Rules that came with it:
- **Rotation is the bend gesture in Godot too.** `RoadKitPoint.auto_facing` is the facing the tool gave
  (stamped by `face()` from `roadkit_cli.py facings` = `point_profile.chain_facings`, and at birth);
  `to_record` promotes an AUTO point turned more than `ROTATED_TOL_DEG` (0.5°, now generated into
  `road_kit_fields.gd` with `MASK_GROUPS`) from it to MANUAL. A drag leaves the basis alone, so it can
  never read as a rotation — the gate's control. A point loaded from the record has no facing until the
  plugin faces it, which every refresh does.
- **A record gesture reloads the network, so node references do not survive it** — carry uids.
- **`point_model.link_order` reversed a road whose HEAD was dragged to the tail**: it started at the end
  that sorts first, which is then the old tail, so Renumber handed the chain back backwards and swapped
  what `lanes_fwd`/`lanes_bwd` mean on every station. The orientation agreeing with more of the current
  order now wins (a 3-point road is genuinely ambiguous). This fixes the Blender operator as well.
- **Branch Ramp Here re-aligns once the ramp has two stations**: aligned with only its mouth, a
  reverse-carriageway exit sat one lane (4.50 m) off the gore line (`ramp_edge_residual`).
- **There is no junction handle node in Godot** — a road's CHILD ORDER is its chain, so a mouth cannot
  be re-parented under one. **Select Junction** selects the clique and the editor's multi-selection
  pivot is the handle. Turning a crossing that way promotes its mouths to MANUAL (the kit's parent-frame
  baseline has no equivalent without a parent).
- `road_kit_gizmo.gd` draws each point's travel arrow and `handle_in`/`handle_out` handles on its own
  axis; a drag is a LENGTH (`handle_length` projects the mouse ray onto the axis, clamped at 0) and makes
  the point MANUAL.
- Gate `test_roadkit_b8.gd` 15/15. `check_roads.sh` now also runs the field-table check and every Godot
  plugin test (section 4, PASS=31 in 1m46s); `timeout -k` because a hung Godot ignores SIGTERM.

**The Blender authoring UI is retired (B9, 2026-09-14).** Deleted: `point_panel`, `point_overlay`,
`point_preview` (its report lives on in pure `point_flow`), `point_live`, `smoketest_point_live`, and 20
interactive operators (Insert/Merge/Split/Tidy/Renumber/Repair/Disconnect/Delete/Select/Jump/Align
Tangent/Sync Facings/Recentre/Validate/Make Ramp/Align Ramp/Branch Ramp/Apply Cross-Section/Add Sample
Network) — their rules are `point_record_ops`'s. `point_ops` keeps what a TOOL drives: New Road, Extend
Road, Connect, Make Intersection (`seed_district_roads.py`), Auto Setback, Load/Save Record, Export
Lanekit, Link Road Kit, plus the helpers `point_build` calls. `make_ramp`/`resolve_aux_pair` moved into
`point_record_ops` (the CLI's `ramp` calls them). The smoketests now drive that pipeline
(`smoketest_point_coverage` 34 checks, the sample network loaded from `RoadKitSample.roads.json`;
`smoketest_point_addon` asserts no `RKA_PT_*` is registered). `build_intersection_prototype.py`, which
called an operator that no longer existed, is in `archive/dead_tools/`. The addon README is now a module
map; the old Blender how-to is in git history.

**Two editor defects, found by running the plugin INSIDE the editor** (`ROADKIT_EDITOR_SELFTEST=<scene>
godot --headless --editor`, the `_selftest` hook in `plugin.gd`, in `check_roads.sh`) — in the editor a
non-@tool JVM script is a placeholder, which no SceneTree test sees:
- **The road did not "show up" because nothing showed it.** Preview Pieces instanced both DebugRoads
  pieces correctly in the real editor — it just had to be ticked, per scene. It is now ON by default
  (EditorSettings `road_kit/preview_pieces`) and rebuilt on every `scene_changed`.
- **A refresh on an UNLOADED network wiped the record.** A saved scene holds `RoadKitNetwork` without its
  points until Load Record; the preview-on-open path called `_refresh` → `_save_for_service` →
  `save_record` and wrote an empty network over `DebugRoads.roads.json` (restored from git, ground
  re-sampled). `RoadKitNetwork.save_record` now refuses to write an empty network over a record that has
  points (`force` to clear on purpose), `_refresh` skips an unloaded network, and the self-test asserts the
  record survives opening the scene.

**The draft surface: the road you are editing, not the last build (B10.1, 2026-09-14).** Until now the
editor showed a thin centreline until a ~30 s Blender build. `roadkit_cli.py bands` returns the paved
footprint Build sweeps, from the solve Build runs (`point_edges.solve_all`): a road run's strip between
`RoadSolve.edges_left/right`, a pad's `JunctionSolve.fan`, a gore's `GoreSolve.tris`, and the kerb /
footway lines of `point_edges.road_edge_runs` / `junction_edge_runs` / `gore_edge_runs`. Those three
are new and are the ONE enumeration of edge runs: `point_build.build_edges` / `build_junction_edges` /
`build_gore_edges` became thin loops over them, so the draft and the build cannot disagree about where a
kerb stops. The overlay uploads it (`road_kit_overlay.gd draft()`, an `ArrayMesh` child of the unowned
overlay, never saved) on every refresh; dock checkbox **Draft Surface**, EditorSettings
`road_kit/draft_surface`, ON by default. Each `bands[i]` names its owner and triangle range, for the
viewport's click-select (B10.3).
- **Materials come off the base meshes, never built in code** (user request): `materials_from(node)`
  collects surface materials by `resource_name` from the Preview Pieces holder, the same `M_Asphalt` /
  `M_ConcreteTile` / `M_LineW` every baked piece carries from `road_kit.blend`. Nothing built yet →
  engine default material. The overlay's line material is a `.tres` too (`road_kit_overlay_lines.tres`).
- **Measured on DebugRoads:** 60 ms wall for the CLI (budget 300; solve 22 ms). RoadKitSample is
  ~400 ms, 260 of it `kerb_runs` — the caching lever if a big network drags.
- **The draft IS the build, within the sweep's own frame:** every one of 2370 draft tarmac/pad vertices
  lies on a built tarmac triangle, worst **0.067 m** — the GN sweep lays each cross-section in the
  curve's frame, which drifts from the per-sample normal on a grade. Control: one station moved 10 m →
  2055/2382.
- **Finding (the build, not the draft): a run's END is cut on its last CHORD by the sweep**, while the
  solver's edges and the pad ring cut it on the mouth's axis (`point_profile.run_end_axes`, §8o). 24
  run-end vertices, worst **0.328 m** at DebugRoads junction 1 (loop mouth); the built road surface ends
  up to 1.5 m short of the draft's cap corner and the pad ring meets it with a step. B10.7 (mesh from the
  Python edges) removes it by construction.
- **Finding: 85 of 1781 lane samples stand on no paving in draft OR build** — turn connectors at
  junction 2 swinging up to 9 m outside the pad, and junction 1's turn paths riding 0.3–0.8 m off its
  planar pad. Draft and build agree on all of them; the lanes are what is wrong.
- Gate trap: a degenerate built triangle makes the closest-point test NaN, and `minf(0.0, NaN)` is NaN —
  it threw away an exact hit and read as a 4.8 m parity failure. Compare with `if d < best`.
- Gate `test_roadkit_draft.gd` 13/13, in `check_roads.sh`; the editor self-test now also refreshes a
  scratch copy of the record and asserts the draft wears `M_Asphalt` inside the real editor.

**Points are editable the moment a scene opens, and the record is their ONLY saved copy (B10.0,
2026-09-14).** The user could not hand-fix DebugRoads' junctions: a saved scene held only the
`RoadKitNetwork` node, its points appeared only after the dock's Load Record (which nothing prompted),
Preview Pieces showed a baked mesh that looked editable and was not, and a point had no click target in
the viewport. Worse, **the committed `DebugRoads.roads.json` had been overwritten by a 2-point `road_0`**
— `New Road` pressed on that unloaded view, which the empty-network guard did not catch because the
network was no longer empty. Restored from `f8b7859`. What changed, each asserted in the editor self-test:
- **`RoadKitNetwork.needs_load`**: an editor-instanced network with no roads and a record with points
  (set in `_ready`, editor only — a `--script` tool or the game builds its own). `save_record` refuses it
  like an empty network; the plugin's `_adopt` loads it on `scene_changed` and before any dock action.
  Loading is not an undo action, so the scene is not marked modified; the record stays byte-identical.
- **The scene never stores a road.** On `NOTIFICATION_EDITOR_PRE_SAVE` the network writes its record
  (only if the text changed) and clears its roads' and points' owners — `PackedScene.pack` skips an
  unowned node's whole subtree, measured, even an owned child under it — and restores them on
  `POST_SAVE` (and deferred, in case a failed save never sends it). So a scene save IS a record save, and
  there is no second copy to disagree with.
- **`from_record` reconciles instead of rebuilding**: a road keeps its node by name and a point by uid
  (moved between roads, re-ordered, renamed through temporary names). Selection and the editor's own undo
  entries (a Move, an inspector edit) keep pointing at live nodes across gestures and undo.
- **Clickable points.** `road_kit_gizmo.gd` adds collision segments (a 1.5 m cross + post and the travel
  arrow); junction mouths are drawn yellow, ramps cyan, termini red. **Preview piece internals are
  un-owned now**: owned by their piece root, each got a gizmo, and a click on the tarmac under a point
  resolved to its nearest editable ancestor — the SCENE ROOT. Control: no collision → the click selects
  the Terrain3D `Surface` mesh.
- A selected point is labelled in the viewport (road, chain index, role, uid, MANUAL / setback locked).
- **Edits refresh themselves.** Points and roads `set_notify_transform` in the editor and report
  transform and `rk_*` changes to the network (`edited`); the plugin debounces 0.25 s (`SETTLE_SECONDS`)
  and refreshes only when `record_text()` differs from the last refresh (so its own re-facing cannot
  loop). While the mouse is held it only redraws.
- **On release a sideways-moved point is DRAPED**: one that sat at grade (height − ground within
  `DRAPE_BAND` −0.5..1.5 m) keeps that height above the NATURAL ground at its new place; a deck or pier
  station keeps the artist's height. A moved junction mouth gets `setback_locked`. One undo step, and
  none at all when nothing changed. **An undo or redo is not a drag**: `version_changed` with a history
  that did not grow suppresses the drape, or undoing a Move would re-drape, commit, and destroy the redo
  history (measured: history 3 → 1 before the guard).
- `_get_property_list` returns `Array[Dictionary]` (the editor logged the compat ERROR on every open).
- Gate: the editor self-test (`plugin.gd _selftest`, `check_roads.sh` greps `RESULT PASS`) edits and
  saves the REAL DebugWorld scene and record and restores both byte for byte. It picks the at-grade mouth
  and move crossing the most ground (loop_p000, 3.17 m), clicks it through the 3D viewport's input
  surface after framing it with F, and asserts: 21/21 points loaded, all owned, scene unmodified, record
  byte-identical, click selects the point, drape to 0.01 m, setback locked, save writes no point into the
  `.tscn` and exactly `pos`/`setback_locked`/`fillet_radius` of that one point into the record, Ctrl+Z ×3
  commits nothing and returns the point to 0.0000 m with redo intact. Controls (no collision, no drape, no
  owner strip) fail 5 checks. Two self-test traps: undo through `get_history_undo_redo(id).undo()`
  bypasses the manager ("Inconsistent redo history", no `version_changed`) — push Ctrl+Z instead; and a
  point created by `add_child` gets its owner afterwards, so it needs `update_gizmos()` for the 3D editor
  to request its gizmo.

**A JUNCTION'S KERB FOLLOWS THE VEHICLE, AND A CAR CROSSING A PAD RIDES ITS SURFACE (B10.0b,
2026-09-14).** B10.1's two findings, both fixed in the rules rather than by hand, measured on DebugRoads
(built pieces, `test_roadkit_draft.gd`): lane samples off paving **85 → 0**, run-end vertices off the
draft **0.328 → 0.004 m**; RoadKitSample 20 → 0.
- **Swept-path sizing: `point_solve.contain_turns`.** The pad ring was sized by `fillet_radius` alone and
  `bezier_through` owned the turn shape, so junction 2's `east` — bending ~95° through its own crossing,
  mouths 40 m out — sent every movement between its two mouths across the unpaved corner notch, 7–23 m
  off the tarmac with a green gate. Each ring corner's radius now grows (×1.25 + 1 m per pass) until every
  legal turn path is `TURN_CLEARANCE` (1.0 m, half the car's hull) inside the ring; the kerb corners take
  the same solved radii (`junction_corners(ring=)`), so pad and kerb agree. Growth is monotonic, so it
  stops when nothing escapes or the ring stops changing. An escaping sample grows the corner whose KERB
  EDGE it is nearest to (`_round_ring(owners=)`), never the nearest corner VERTEX — a corner between arms
  40° apart has its vertex on the far side of the pad, 53 m from the notch it rounds, and growing by
  vertex distance grew the wrong (already clamped) corner and stopped. A corner may now take 98% of an
  edge that runs to a CAP point (`CAP_EDGE_REACH`); half an edge is kept only between two rounded corners.
  A path's first and last samples lie ON its cap, so a point within 5 cm of a cap counts as inside —
  without that, boundary parity grew three corners for nothing.
- **A turn is driven as a kerb return is built: `point_solve.turn_shape`** — straight along the longer
  approach, the largest circular arc through the point where the two lane lines meet (tangent length =
  the shorter leg), straight out; a movement turning < `TURN_ARC_MIN_DEG` (20°) or whose lane lines do not
  meet ahead of both mouths (straight-through, lane shift) stays a cubic, now with circular-arc handles
  (`arc_handle`, chord/3 only when straight). This is what makes a corner containable at all: the kerb arc
  sits concentric inside it. A single cubic between the mouths could not be contained whatever its handles
  (one leg 13 m longer than the other), and chord/3 handles bowed a sharp turn toward its chord, into the
  corner. Two sign errors cost a round each and are worth a unit check next time: the fillet radius is
  `t · tan(interior / 2)` (dividing drew a zig-zag), and `u` from `d0·s + d1·u = p1 − p0` is Cramer over
  `cross(d0, d1)` (over −cross the arc branch only ran in the wrong cases).
- **A turn path's HEIGHT is the pad's: `turn_path` reads each sample off the pad's own triangles
  (`pad_z`).** The cubic's Z ran straight between mouths while the pad is IDW-from-mouths, triangulated;
  with 1.1 m between junction 1's mouths they parted by up to 0.81 m. `point_export` now builds each
  connector from the solved pad and fits its `curve` with `curve_points` (control points at the arc's
  breaks, and wherever else 0.05 m needs one) — `JunctionSolve.turns`, the export and the preview share it.
- **The pad meets its stop line at the road's height: `_idw_z` weights by distance to each mouth's CAP
  SEGMENT (`Mouth.cap`)**, not its centre point. A cap corner 9 m out took 0.31 m of the neighbours'
  heights and the pad stepped against the road along `link`'s mouth. A stand-in with only `.pos`
  (`seed_district_roads`) keeps the point rule; the weights are geometry either way, so `_idw_z` stays
  linear in the mouth heights (the pad-lift property `W20` relies on).
- **A run's END is cut on the mouth axis in the BUILD too: `point_build.END_LEAD`.** `Curve to Mesh` (and
  `GN_PointSpine`'s stored lateral) take a poly curve's end frame from its last CHORD, while the solver and
  the pad ring use `run_end_axes`; `carrier_points` inserts a vertex 2 cm inside each open end along that
  end sample's own tangent, with the end's values.
- **What is left is layout, and the gate names it: `turn_off_pad` (WARN, `point_solve.turns_off_pad`)**,
  on the mouth nearest the worst sample other than the movement's own two. DebugRoads has one: `link →
  east` straight crosses the end of `spur`'s carriageway, 2.22 m past the pad, because the `spur` mouth
  (2-point road) faces 79° off its pad centre. Pulling it out 6/10/15 m along its road does not clear it
  (2.00/2.00/1.21 m) — the remedy is turning the mouth, a hand edit.
- Self-tests (`point_solve.py`, 20): turn_shape's arc/line/cubic cases; a 3-arm pad bending 90° through
  30 m mouths contains every movement, with the CONTROL `solve_junction(contain=False)` failing; the pad
  meets every cap at the road height; every turn sample rides `pad_z`. `test_roadkit_draft.gd` asserts
  both former findings.

**The intersection tweak is handles on the point (B10.4, 2026-09-14).** `road_kit_gizmo.gd` draws and
`road_kit_handles.gd` (a `RefCounted` — an `EditorNode3DGizmoPlugin` "can only be instantiated by
editor", so logic kept in the gizmo is untestable headless) owns what each does, through pure
`road_kit_gestures.gd` operations: every point has two LANE-COUNT handles at the outer edge of each
carriageway (`lane_edge_offset` / `lanes_for_offset`; FWD is `+s`, the point's local −X), and a junction
mouth adds a SETBACK handle (`slide_along_axis`: along the mouth's own flattened axis, locks the setback),
a FILLET handle (the radius the pad starts from — `contain_turns` may grow it) and the whole junction's
MOVE and ROTATE handles at the mouths' centroid (`junction_translate` / `junction_rotate`). There is no
junction node to parent the mouths under, so the kit's "turning a crossing promotes nothing" is kept by
rotating each mouth's `auto_facing` baseline with it; a hand turn of one mouth still promotes (the
control). Drags project onto the horizontal plane through the point or pad centre, and each is ONE
record-restoring undo step (`Handles.end` → `{before, after}`); cancel restores the record exactly. Gates:
`test_roadkit_handles.gd` 13/13 (rotate promotes none, move touches only the clique, setback 5e-6 m off
its axis, lane counts ±half a lane, fillet, a rotate drag through `drag_to` passes the kit's gate, cancel
restores); the editor self-test drags the ROTATE handle through the real gizmo plugin with the viewport's
camera, checks all 3 mouths turned and the action is "Road Kit: rotate junction", and Ctrl+Z restores it.
Self-test trap: after the undo checks there is redo history, which a new commit truncates — identify the
action by `get_current_action_name()`, never by history count.

**A viewport tool mode, road-generator style (B10.3, 2026-09-14).** A toolbar in
`CONTAINER_SPATIAL_EDITOR_MENU` (Off / Select / Draw Road / Insert / Delete / Connect) and
`set_input_event_forwarding_always_enabled()`, so a click anywhere reaches `plugin._forward_3d_gui_input`
— not only while a road node is selected. `road_kit_tool.gd` (a `RefCounted`, so testable) owns what a
click does, over the existing gestures: picking is screen-space (a point within 14 px, a centreline within
12 px of the overlay's last `centrelines` runs, which now carry each run's `uids` so a click names its
span); DRAW lands each station on Terrain3D's surface in plan (`get_intersection(..., gpu_mode=false)`,
miss = `z > 3.4e38` or NaN) at the NATURAL ground's height + 0.10 m drape (`road_kit_ground.natural_height`,
so a stamped terrain cannot lift a new road onto the old one), else on the network's y = 0 plane; CONNECT
joins two ends of one road by SEGMENT, makes or grows a junction across roads, and hands off to
`roadkit_cli.py ramp` (the solver places a ramp) when one pick is an interior station with aux lanes. The
plugin wraps every click that changes the network in one record-restoring undo step named after the mode,
and Esc / right-click finishes an open sequence. Gates: `test_roadkit_tool.gd` 12/12 (a real Camera3D over
the sample network: pick, select road, Alt-select junction, insert at the click with the gate still 0
errors, delete, draw 3 stations at the clicks, Esc then a NEW road, connect SEGMENT and junction, and on
DebugWorld a drawn station at natural ground + drape rather than the stamped surface) and the editor
self-test sends a left click through `_forward_3d_gui_input` in Insert mode and undoes it. Two traps: in a
`SceneTree._initialize` a node added to `root` is not `is_inside_tree()` until the first `await
process_frame` (every `global_position` errors); and a GDScript parse error in `plugin.gd` makes the editor
self-test HANG to its timeout — always `--check-only` the plugin first.

**Dragging a road is a move, baked on release (B10.5, 2026-09-14).** A `RoadKitRoad` node dragged with the
stock gizmo already moves its points (a point's record position composes its road's transform), but it
left the road node carrying an offset every later edit had to compose. On release (`_drape_moved`) each
road with a non-identity transform is baked into its points (`Gestures.bake_road_transform`: road back at
identity, every network transform unchanged, the facing baseline turned with it so nothing is promoted to
MANUAL), and — dock option "Dragging a road moves its junctions", on by default — every OTHER road's mouth
at its junctions moves by that junction's mean mouth displacement (`move_junction_partners`), so a pad
travels with the road instead of stretching across the gap. The bake, the partners and the drape are ONE
undo step ("Road Kit: Move Road") back to the last refreshed record; an undo/redo is never baked (the
road's transform may then keep an offset until the next edit, which is harmless — the record composes it).
Gates: `test_roadkit_handles.gd` (bake keeps every network transform, a 10° turn promotes none, partners
follow, bystanders do not) and the editor self-test drags road `east` with a real Move action (4 partner
mouths follow, one step, Ctrl+Z restores the record).

**Build rebuilds only the zones whose output changed (B10.6, 2026-09-14).** Which zones an edit touched is
NOT a record diff — the whole network is solved for every piece (a kerb opens against a neighbour's asphalt,
a pad corner grows for another road's turn, a gore goes with its ramp's zone). `point_digest.piece_digests`
asks the OUTPUT instead: per piece, a SHA-1 of what it emits from the same solve and cut the build runs —
its runs' carrier samples and values, edge runs, marking runs, pads (ring, fan, corners), gores, its own
`split_doc` lanekit and its roads' authored fields — rounded to 0.1 mm, salted with the builder's source
(`point_build`, `point_nodes`, `point_solve`, `point_edges`, `kit_common`, …) and `road_kit.blend`'s size
and mtime, so a builder change dirties everything. `roadkit_cli.py pieces` reports a `digest` per piece
(now with `--ground`, the same ground the mesh build uses); `build_roads_piece.sh` with `DIRTY_ONLY=1`
skips a piece whose digest equals the one in `<stem>.build.json` and whose scene exists, builds only
the dirty ones (`roadkit_cli.py gltf --only`; Blender's `--only` until B11) — and nothing at all when none is — and writes a piece's
digest into the manifest only after it has BAKED, so a failed bake stays dirty. The manifest belongs to the
committed pieces; commit it with them. Dock: **Build Piece (changed zones)** is the default, **Rebuild All
Pieces** forces it, and a build that rebuilt something on a stamped network says to press Stamp Terrain.
Measured on DebugRoads (2 zones): cold 40.7 s, nothing changed **5.2 s** (no Blender), one interior station
of `east` moved **23.4 s** — `debug_b` rebuilt, `debug_a` reported clean. Gate: `point_digest.py`
self-test (in `check_roads.sh`): re-solving reproduces every digest, a station moved in one zone of the
testbed dirties that piece only, moving it back restores the digests.

**Does the road mesh need Blender? Measured, then decided (B10.7, 2026-09-14).** `point_mesh.py` re-sweeps
every layer `point_build` hands Geometry Nodes — carriageway, median, deck, pillars, kerb, footway,
barrier, markings, pads, gores — in pure Python from the same solve and the same layer table, and
`blender/tools/roadkit_mesh_parity.py` compares it with the baked glTF object by object, material by
material (area, triangle count, sampled surface distance both ways) plus the drivable surface under every
lane sample. `roadkit_cli.py mesh` hands the result to Godot (`gltf_tris.py` is the reader).
- **Parity.** DebugRoads: carriageway, pads, markings exact (p95 0.000 m both ways); road surface under
  2 255 lane samples max **2.6 mm** apart. RoadKitSample (ramps, gores, footways, median): footway, gore,
  median, pad, markings exact; 6 046 lane samples max **8.4 mm**; no object in only one build. Kerbs and
  decks exact after the GN fix below, barriers within 0.4% area (Blender evaluates an extrusion's
  thickness per FACE, so a wall's end segment steps where the solver's per-vertex value ramps).
- **Speed.** Python sweep 65–90 ms (DebugRoads) / 526–605 ms (RoadKitSample); **177 ms end to end** into
  Godot `ArrayMesh`es with trimesh collision for DebugRoads, 848 ms for RoadKitSample — against ~40 s for
  the Blender build of DebugRoads before export and bake.
- **What the spike found in the SHIPPED build, and fixed in `GN_PointDeck` (GROUP_VERSION 5):** `Extrude
  Mesh` MOVES the faces it extrudes, and with `Individual` at its default every face got its own four walls.
  So every kerb was hollow (its only horizontal face at road level, 10.46 m, walls to 10.61 m), every bridge
  deck had no underside from below (the soffit still faced up), side walls faced inward (a kerb's signed
  volume −1.8 m³ against +5.46 once fixed), and every segment carried hidden internal walls. Now: one
  region, the moved copy flipped (bottom down, walls out), the swept band joined back on as the top.
  Measured after: kerb 492/492 triangles and deck 556/556 equal to the Python sweep, volumes equal (deck
  2355.2 vs 2355.9 m³). DebugRoads and RoadKitZones pieces rebuilt (the digest salt caught the builder
  change and dirtied every piece by itself).
- **Not ported at the time (all ported in B11, below):** profile ASSETS (artist-modelled sections from `road_kit.blend`
  — neither sample network uses one), style slots (material by name), vertex normals (Blender's glTF
  carries NORMAL; neither carries UVs, the kit's materials are world-position procedural), the `-colonly`
  road/walk/`-noped` collision split, and the piece SCENE (today glTF → `WorldBaker` → `NavBaker`).
- **Decision:** the pure-Python sweep becomes the ONE owner of road geometry (PLAN.md 3.1 **B11**): port the
  five items above, write the piece scene from Godot, gate it with `roadkit_mesh_parity.py` +
  `probe_road_ground`/`probe_road_stamp`/`probe_traffic_spawn`/`probe_road_zones`, then make it the Build
  and retire the Blender road build like B9 (`build_island_base.py` keeps Blender until the island is
  rebuilt on Terrain3D). Until then Blender is the build, and `check_roads.sh` runs
  `roadkit_mesh_parity.py --assert` on DebugRoads so the two cannot drift (control: Python's deck moved
  10 cm → `surface/M_Concrete: surface distance p95 0.100`, exit 1).

**Editing is live, Godot's Delete is a road gesture, and a name says what a point is (B10.8, 2026-09-14,
user-reported: "dragging freezes the editor", "delete like a Godot node", "everything has the same name").**
- **THE FREEZE WAS ONE COMMAND.** With ZoneMarkers in the scene every refresh ran `centrelines --zones`,
  which drew the cross-zone successor edges by running the whole gate and a whole lane export —
  **3.1 s blocking on DebugRoads** (6 s of it `check_path_fidelity`, fitting every lane twice) — on every
  pause of a drag and every release. `roadkit_cli.py live` answers centrelines + draft bands + facings +
  junction centres in ONE process (**0.09 s**, cross edges only with `--cross`, 3.4 s). The plugin runs it on
  worker threads in two LATEST-WINS slots (FAST, and CROSS for the edges), from scratch copies under
  `user://road_kit_live/` — never the real record mid-drag — and sends a drag every `LIVE_TICK` (50 ms)
  while the button is held, so the road follows the mouse. Nothing is saved, draped or faced mid-drag; a
  result is faced only if the record still matches the one sent. Main-thread cost per tick is asserted by
  the editor self-test (`LIVE_TICK_BUDGET_MS`). Validate and Flow Report (2–6 s) run on a thread too
  (`_service_async`); Build already did.
- **Facing the point under the gizmo quietly made it MANUAL.** A settle mid-drag re-faced every AUTO point,
  the gizmo then wrote its pre-drag basis back on the next mouse move, and `was_rotated()` read the
  difference as a hand rotation. Facings now land only after release.
- **SELECT took the PRESS**, so a move-gizmo arrow lying along a road (over its centreline) selected the road
  instead of starting the drag — "dragging does not work". The press and release now pass through; a click
  (release within 4 px of the press) selects the road, deferred after the editor's own click-select.
- **Links in the record are DERIVED from the live tree** (`RoadKitNetwork.record_links`), so the Scene dock's
  Delete needs no hook and its undo (which just re-adds the node) restores the record exactly: a link to a
  point no longer in the tree is not written; SEGMENT/JUNCTION links are written on both ends; two points
  left chain-adjacent by deleted stations are joined (through remembered links, `_known_links`); a
  SEGMENT that skips exactly one live station linking both ends is dropped; an INTERSECTION with no
  JUNCTION left is written as SEGMENT. `Gestures.delete_point` joins the neighbours the same way (it used to
  cut the road). `child_order_changed` on roads and the network is the edit signal; names renumber on settle.
- **Names carry a tag** (`RoadKitNetwork.name_tag`): `_jct` junction mouth, `_ramp` ramp mouth, `_aux` the
  mainline station a ramp leaves, `_end` a road end joining nothing, none for a plain station; each point's
  `editor_description` (the Scene-dock tooltip) lists its role and links, and the overlay floats a
  `JUNCTION (n)` label listing the mouths over every pad. Nothing reads a point by name.
- **The record cannot be lost by a crash or a commit.** `save_record` writes `<record>.tmp` and renames it over
  the record (atomic), skips an unchanged write, and tracks the text it last read or wrote: a record changed
  on disk (a git checkout) is RELOADED as an undo step (`_reload_if_changed_on_disk`), never saved over —
  also on scene save.
- **DebugRoads' west junction is one clean T** (user request). `loop_p010` had been deleted in the editor,
  leaving `link_p000` + `loop_p000` a 2-arm pad; the committed version had that mouth 74° off its pad
  centre because `loop_p009` jogged 25 m north. Rebuilt as a T — loop's tail and `link` the through road,
  loop's head the stem — dropping that station, mouths on their approach lines, AUTO facings, one
  `auto_setback` (before W17 was closed, a second pass grew it): 0 errors, no finding on the pad, 0 of 465 nearby lane samples
  off paving. The tail mouth is `loop_p009_jct` now.
- Gates: `test_roadkit_native_delete.gd` (in `check_roads.sh`), and the editor self-test's new steps — SELECT
  click pass-through, a Scene-dock delete + Ctrl+Z, a record changed on disk reloaded both ways, the junction
  labels, the live-tick cost.

**A BARRIER IS ON OR OFF, NEVER A WEDGE — the "car launched at speed" bug (PLAN.md 0.1, 2026-09-14,
user-reported: "randomly spikes upward at high speed, worse near the bridge and close to a wall").** The
solver decides `rka_wall_h` per 4 m sample (full `barrier_height` where the road is ≥ `BARRIER_MIN_DELTA`
off the ground, 0 elsewhere) and the sweep interpolates every attribute between samples, so the span where
a parapet BEGINS was swept as a 4 m wedge rising from the kerb to 1 m, collision included. On DebugRoads'
`link`, where the bridge leaves the island, that is a jump ramp standing on the road edge: a car at 37 m/s
with its outer wheels on the edge line climbed it and left the ground at up to 23.6 m/s of vertical speed.
(Real highways retired the "ramped end" barrier terminal for the same reason.) `point_edges.step_walls` is
now applied inside all three edge-run enumerations (`road_edge_runs` / `junction_edge_runs` /
`gore_edge_runs`), so the Blender build, the pure-Python sweep, the draft and the digest all see it: where
one vertex has a barrier and its neighbour none, a vertex goes in `WALL_END_STEP` (2 cm) from the bare one at
full height, so the wall covers the whole span and ends in a face. It errs toward more fence. Two non-zero
heights still blend. `point_solve.junction_corners` had the same wedge along a whole corner arc when one arm
is fenced and the other not; it now steps at the corner's middle. Found with two new tools:
- **`tools/godot/probe_road_launch.gd`** — the gate. `debug/LaneDriveProbeController` (the ordinary traffic
  brain, aimed at a lane by name, blind to other cars, optionally riding `lateral_offset` m beside the lane)
  drives Vehicle.tscn through DebugWorld's streamed pieces. A LAUNCH is the body's vertical speed RELATIVE
  TO THE LANE'S OWN RISE RATE going up by more than 3 m/s within 0.25 s while on the road. Measured against
  the road, not the world: a sag at 32 m/s is legitimately a 3.8 m/s change, and the first detector read
  grades as launches. A per-tick threshold was the first detector too, and it missed launches that build
  over several ticks (31 m/s with no flag). Each launch prints every body contact and every wheel ray.
  GATE_CASES: 0 on-road launches over 6 cases; control (the pieces built before `step_walls`): 6 launches
  on the two edge-line cases, worst 23.6 m/s.
- **`tools/godot/probe_road_section.gd`** — a collision cross-section of a streamed lane (`--half`), or a
  lengthwise one at a lateral offset (`--along --lat`): every collider a vertical ray passes through, top
  first. It is what showed the wedge (10.61 → 11.61 m over 4.25 m), which no visual shows.

**A SLOPED PAD IS A GRID OVER A THIN PLATE CLAMPED TO ITS ROADS (B12, 2026-09-16).** Found by the same
probe: DebugRoads' west T has mouths at 10.46 / 12.97 / 11.02 m, and two of its stop lines have cap corners
6 m apart with 1.95 m between them. `point_solve.PadField` is now the ONE owner of a pad's height, and
`pad_triangles` builds a sloped pad as `grid_pad_triangles` (the ring cut by a world-aligned 1.5 m grid,
Sutherland-Hodgman plus ear-clip per edge cell, watertight by area) instead of a one-apex fan. A pad whose
mouths are level and whose roads are level keeps its fan, its triangle count and its digest. The field is the
minimum-curvature surface (squared second differences in x, y and the cross term). Each approach band,
`PAD_APPROACH` 4 m along its road, is fixed to that road's plane: its height at the stop line, rising at
`Mouth.grade` (`mouth_grade`, the run's own end tangent). It is solved in pure Python by conjugate gradients on
a 2 m grid, started from IDW, in 0.07 s on the west T. It is linear in the mouth heights, like IDW.
- **Measure a pad ROAD TO ROAD, never on the pad alone.** The first attempt was a membrane (harmonic,
  fixed at the caps). On the pad it looked better than IDW, 17.9% steepest and 5.9% grade change per 2 m.
  In a car it was worse: it met the `loop` stop line climbing 18% against a +4% road, and `link_R1` at
  20 m/s launched there, where the old fan had not. `point_solve.turn_grades` now follows each movement
  `PAD_GRADE_APPROACH` (10 m) along both roads. Drive profile of the straight `link` → `loop` outer lane
  (crest per 2 m / steepest): old fan 9.3 / 21.2%, IDW 9.9 / 16.3%, membrane 13.2 / 17.3%, thin plate
  8.4 / 12.6%. Worst movement: 41.5 / 17.5 / 18.0 / 12.8%.
- **`pad_grade` (WARN)**: the steepest movement past `PAD_GRADE_MAX` (8%, the kit's hill-road grade),
  naming the two stop lines and the floor no surface can go below (end-to-end rise over plan length). On
  the west T: 18.3% on the left turn from the `loop` head to its tail, whose floor is 15.7% (1.95 m over
  12.4 m). That is layout.
- **The rest was layout, and DebugRoads' west T was re-graded (user decision).** On the new surface
  `probe_road_launch.gd -- --lane=link_R1 --speed=S` still rose 3.65 m/s at 25 m/s and 4.50 at 30. At
  35 m/s the launches were 20-50 m PAST the pad, on `loop` itself, which fell from −2% to −18% within 11 m of
  its head station: B12's original "a car leaves the pad at 5 m/s" was that crest. `loop`'s head mouth
  `p_ffcedf9d` went 11.02 → 12.2 m, and its next two stations 10.63 → 11.5 and 8.06 → 10.8, so the 4 m
  descent runs over 106 m (fill up to 2.8 m, re-stamped). Pad steepest 18.3 → 10.4%, `loop` worst grade
  change per sample 7.2 → 1.6%. `link_R1 +0`: 0 on-road launches at 20/25/30/35 m/s, worst rise 1.62-2.29
  m/s. `pad_grade` still WARNs at 10.4%: `link` (10.46) to `loop`'s tail (12.97) is 6.9% at best. At 30 m/s
  the car also runs wide on a `loop` curve ~250 m on and bounces on terrain, which is unrelated.
- **After a pad change on a stamped network, stamp again.** The terrain was stamped from the old surface,
  and at 20 m/s a rear wheel hit Terrain3D standing 0.18 m proud of the new pad.
- **Terrain3D `get_height` a hair inside a cell edge returns the FAR vertex's height**: (-150.0006, 72.0)
  read 11.09, the (-152, 72) vertex, where (-150, 72) is 10.97. The 1.5 m pad grid shares a vertex with
  the 2 m terrain grid every 6 m, which turned that into 6 false "proud" pad vertices in
  `probe_road_stamp.gd`. The probe queries pad vertices on a 1 cm grid now.
- `blender/tools/measure_pad_grades.py <record>` prints the built pad, its field, IDW and the old fan side
  by side, with the floor.
- Not changed: `seed_district_roads.pad_lifts` still predicts burial with `_idw_z` over stand-in mouths (no
  ring exists yet). Both rules are linear in the mouth heights, so its uniform lift is still exact in kind.

**THE ROAD BUILD HAS NO BLENDER (B11, 2026-09-16).** B10.7's five missing pieces are ported, the Build runs them,
and the Blender road build is deleted. `build_roads_piece.sh`: (1) `roadkit_cli.py pieces` (gate, zone cut, lanekits,
digests), (2) `roadkit_cli.py gltf --gated --only <dirty>` writes `src/.../world/pieces/<piece>.gltf`, (3)
`GLTF_READY=1 build_piece.sh <piece>` bakes it (WorldBaker + lanekit Path3Ds, NavBaker, `.scn`) with no `.blend`.
DebugRoads end to end **28 s**, of which the mesh write is **0.4 s** — the rest is the Godot bake.
- **The kit is DATA** (`point_kit.py`): `blender/tools/export_road_kit_data.py` reads `road_kit.blend` into
  `assets/world_source/kits/road_kit/road_kit.json` — every material as the glTF entry Blender's exporter produced
  (`export_world.py`'s base-colour flattening restated: M_ConcreteTile's checker is its mean, 0.815/0.795/0.755) and
  every `ROAD_KIT` profile's points — plus the `.blend`'s sha1, which `point_kit.self_test` checks, so an edited kit
  with a stale JSON fails the gate. `build_road_kit.py` runs the export at the end of every kit build. Styles resolve
  as `point_style.resolve` did (one slot table, `point_style.SLOTS`): a name the kit lacks falls back to the layer
  default and is reported (`missing_style`, printed by the build).
- **A profile asset is swept in the Z-up curve frame**: section +X is `cross(N, T)` (the curve's left), +Y the Z-up
  normal `N` (perpendicular to the tangent), mirrored for the right flank, open (no caps), origin on
  `point_build.ASSET_Z_ATTR`'s line. Derived from `GN_PointProfile`'s measured correction, then measured: triangle
  counts equal to Blender's on every asset layer (granite kerb 300/300, parapet 816/816, jersey 1400/1400), p95
  0.000 m. **The Blender road build had never swept one from a Godot record**: `roadkit_build_mesh.py` never linked
  the kit, so every named asset resolved to "missing" and the report line was filtered out of the build output.
- **`-colonly` proxies** are `point_mesh._collision` (`point_build.collision_name`'s rule): one road proxy (the
  `__surface`/pad/gore, every material), one walk proxy (the run's edge objects), `-noped` from `ped_access`.
  Godot's importer still makes the `StaticBody3D`s from the name. Navmesh vertex counts and collision shape counts
  of the rebuilt pieces equal the Blender-built ones (RoadKitZones west 32/18, RoadKitSample 32/28).
- **Normals are auto-smooth at 30°, computed** (`point_gltf.indexed`), not matched: Blender's export shaded smooth
  across hard edges and carried inverted normals (88 on one DebugRoads deck). Gate: none inverted, none past the
  angle (worst 28.6°). Quads split on the SHORTER diagonal (`point_mesh._strip`): areas now equal Blender's to
  0.1 m² (they differed by up to 0.7% on the ramps), at p95 0.003 m.
- **The pieces no longer carry the station Empties** (`east_p000` Node3Ds with the record in their extras): nothing
  read them, and the record is the one copy. 38 nodes fewer on RoadKitSample (235 -> 197).
- **Parity before retirement**, Blender references built from the same records with the kit linked, `--assert`
  green on all four: DebugRoads (both zones, with ground) every layer and both proxy kinds p95 0.000 m except the
  known barrier per-face step, lane surface max 0.9 mm over 2 214 samples; RoadKitZones west+east and RoadKitSample
  p95 ≤ 0.003 m, lane surface max 8.4 mm over 6 046 samples; `RoadKitStyled.roads.json` (the sample with material
  slots, three profile assets and one missing name) every layer p95 0.000–0.003 m, the 13 materials identical.
- **The editor shows the full mesh on release**: `roadkit_cli.py live --mesh [--ground]` returns
  `point_mesh.build`'s visible triangles by material; the plugin requests it only when the mouse is up (a drag still
  gets the fast bands), prepares the arrays on the worker thread (`OverlayScript.prepare_mesh`, re-wound for Godot's
  clockwise front face) and uploads them as the draft (`full_mesh`), in the base meshes' materials. DebugRoads
  18 280 triangles in 0.34 s of CLI.
- **Retired:** `blender/tools/roadkit_build_mesh.py`, `build_roadkit_sample_piece.py` and the piece `.blend`s they
  wrote (`Roads_DebugRoads_*`, `Roads_RoadKitZones_*`, `RoadKitSample`). `point_build`/`point_nodes` stayed for
  `build_island_base.py` until 2026-09-18, when both were deleted (PLAN.md 3.10, "The island's roads stream as a
  504 m grid"). The digest salt is now the Python builder's sources and `road_kit.json`'s bytes.
- Gates: `point_kit.py`, `point_gltf.py` self-tests and **`blender/tools/check_roadkit_build.py`** (in
  `check_roads.sh`, now PASS=40): DebugRoads and RoadKitZones rebuilt into a temp dir must equal the committed
  glTFs under `roadkit_mesh_parity --built --assert` (control: one station of `east` moved 3 m in the record →
  `edges/M_Concrete p95 1.584`, FAIL), and RoadKitStyled's styles, assets and normals build. Runtime, on the
  rebuilt pieces: `probe_road_zones` 12/12, `probe_road_ground` 201/201, `probe_road_stamp` PASS,
  `probe_traffic_spawn` 6/6, `probe_road_launch` 0 launches over 6 cases, `probe_road_traffic --scene=roadkit`
  50 cars / 0 stuck; editor self-test PASS including "after a release the draft is the full mesh".
- **Also fixed on the way: a close camera could not click a road** (`road_kit_tool.gd`). `pick_centreline` skipped
  every segment with an end behind the camera, so framed a few metres from a mouth (F) nothing was clickable, which
  is what failed the editor self-test on a clean HEAD. Segments are clipped to the near plane (`visible_part`), and
  the click's screen fraction is mapped back to the segment perspective-correctly (`world_param`): the insert point
  had been up to 0.585 m from the cursor on a close view. Gate `test_roadkit_tool.gd` "close camera" (controls: the
  old skip → no pick; a linear lerp → 0.585 m).

**A PIER IS A MODELLED ASSET: RIGID CAP, STRETCHED SHAFT (PLAN.md 3.5, 2026-09-17, user decision: a modelled
asset slot, not a procedural enum).** A road names `RoadData.pillar_asset` (blank = the plain `rka_pillar_w` box,
byte-identical to before), and `point_mesh.pillars` stands that mesh at every placement the solve already makes
(`pier_placements`: the deck-centre curve resampled every `rka_sp_pillar`, kept where `rka_pillar_param`).
- **The asset** is a `RKA_PIER_<variant>` MESH in `road_kit.blend`'s `ROAD_KIT` collection: Z-up, origin at the TOP
  centre (the soffit), +Y along the road, +X across, at its REAL size (never scaled to the deck, like a profile).
  Its `rka_stretch_z` custom property splits it: every vertex above is rigid (cap, crossbeam), every vertex below
  stretches linearly so the lowest point lands exactly `rka_pillar_h` under the soffit, i.e. on the ground. A pier
  shorter than its cap + `PIER_MIN_SHAFT` (0.3 m) is squashed whole instead. **Each shaft vertex stretches to the
  ground under ITSELF** (the build's ground grid, `place_pier(ground=)`), not under the centreline: stretched to the
  centreline's ground, the portal's side columns (5.5 m off the road's line) stopped 5.09 m over the sloping seabed
  at hama_dori (`probe_road_ground.gd -- World.tscn`, 3 columns); now 0. Any number of materials, each face its
  own. `export_road_kit_data.py` writes each as `piers[name] = {stretch_z, tris: {material: [9 floats]}}` into
  `road_kit.json` (rotation/scale applied, location not, so a pier can stand anywhere in the kit file).
- **Shipped placeholders** (`build_road_kit.py PIERS`; `-- --add-piers` re-makes only these in the existing kit file,
  so hand edits survive): `round` (r 0.9 m column), `hammerhead` (the Shuto T-pier: 12 m tapered cap on a 2.6 x 2.0 m
  column, `stretch_z` -1.8), `portal` (a 16 m crossbeam on two round columns, -1.5). Model a real one in the kit
  file, then run `export_road_kit_data.py`.
- **Wired:** DebugRoads' `link` and `east` (9 m deck half-width) stand `hammerhead`; the island's two sea crossings
  `hama_dori` and `kuko_dori` (29 m decks, columns 3-48 m) stand `portal`.
- A name the kit lacks falls back to the box and is reported (`missing_style` row `(road, "pillar", "asset",
  name)`); a pier reaching past the deck edge is reported as `pier_overhang` (the build prints both).
- Gates: `point_kit.py` (resolve + missing), `point_mesh.py` self-test (cap rigid, foot exactly `height` down,
  turned onto the heading, short pier squashed whole), `check_roadkit_build.py` on `RoadKitStyled` (demo_hwy's
  hammerhead: a whole number of the pier's triangles and the full 12.4 m; the 16 m portal on a 7 m ramp deck is the
  only overhang; control: blank demo_hwy's pier -> 2 FAIL). On the rebuilt DebugRoads pieces
  `probe_road_ground.gd` 201/201 column feet on the terrain, `probe_road_zones.gd` 12/12, `probe_road_launch.gd`
  0 launches; on the island `probe_road_ground.gd -- World.tscn` 2408/2408 and 0 short columns,
  `probe_traffic_spawn --world=island` PASS, `check_roads.sh` PASS=40. Rebuilding the island piece also landed
  3.4b's fix in its lanekit (28 connectors lose a duplicate control point), so the island road map was re-baked. The Blender road build (`point_build`, island base only) does NOT read `pillar_asset`.
- **Still art, not code:** real pier models, and the named hero bridge (Rainbow Bridge), which is authored
  content fitted to a road with `pillar_skip` on its stations.

**A road's texture is a material library, resolved by NAME at bake (PLAN.md 3.6c, 2026-09-17).** glTF carries
the kit's procedural materials only as a flat base colour and the swept mesh has no UVs, so the textured look
lives in Godot: `assets/world_source/kits/road_kit/materials/<M_name>.tres` — `M_Asphalt` (`T_Concrete_Asphalt`),
`M_ConcreteTile` / `M_Concrete` / `M_Barrier` (`T_Concrete`, tinted), with the kit's ORM + normal maps, all
**world-space triplanar** at the Quaternius tile (3 m x `module_scale` 0.91 = **2.73 m**, measured off the kit's
own `Street_*` UVs). `WorldBaker.applyMaterialLibrary` (every bake, after conversion) replaces any mesh surface
whose material is named like a file there; the baked scene REFERENCES the `.tres`, so editing one restyles every
piece with no rebake, while adding or removing a name needs one — `point_digest.builder_salt` hashes the directory
for that reason, so the next `DIRTY_ONLY` build rebakes everything. The names keep `resource_name`, so the editor
draft (`materials_from`) wears them too. Markings (`M_LineW/Y`) and `M_Median` stay flat. Gate:
`tools/godot/shot_road_surface.gd -- <out> [--piece=] [--flat]` (needs a display; `--flat` is the control).
The decals and props are the next paragraph.

**Road decals and street furniture are PLACED by the Road Kit, from facts the build already owns (PLAN.md 3.6c,
2026-09-17).** `blender/addons/road_kit_authoring/point_furniture.py` (pure python, self-tested) runs inside
`roadkit_cli.py gltf`; `assets/world_source/kits/road_kit/furniture.json` is its table (which kit piece, lift, scale, `collide`,
`exclude_roads` globs, and every spacing).
- **At each junction arm, on the APPROACH road** (the Japanese order a driver meets them): a turn arrow on each arriving
  lane 14 m back, chosen from the turns of that lane's connectors (S, L, R, S+L, S+R; L+R and all three get none);
  a stop line 7 m back across the ARRIVING lanes only; a zebra 1-5 m back across the whole carriageway, 45 cm bars and
  gaps with no side bars. The lanes come from the lanekits `pieces` wrote in step 1, ALL of the network's, because a
  mouth's connectors stream with the pad's piece.
- **Along the kerbs:** a drain in the gutter every 20 m, a planter (collides) on a footway at least 3 m wide every
  30 m, and bollards (collide) round every junction corner that has a footway. Manholes every 90 m per through lane,
  at a phase hashed from the lane id, so an unchanged record rebuilds byte-identically. Nothing where a barrier
  stands, or where a ground grid says the lane is more than 2 m up (a bridge). Planters and manholes skip
  `shrine_touge*`.
- **The arrows are the kit's decals; the stop line and zebra are PAINT** (triangles in the road's `mark_w`
  material, object `FURN__marks_w`), because the kit's crosswalk has side bars and it has no stop line.
- **Kit pieces leave as `mmesh_<asset>` glTF nodes** carrying `asset_path` in their extras (`point_gltf.marker_node`,
  piece -Z along `fwd`). `WorldBaker.buildMultiMeshes` already collapses those into one MultiMesh per asset;
  `withKitMaterials` now gives each a DUPLICATED mesh wearing `<kit>/materials/<name>.tres` (the imported material
  turns on vertex-colour-as-albedo from the kit's COLOR_0 wear mask, the buildings' trap). `MI_StreetDecals.tres`
  (alpha scissor) and `MI_Dirt.tres` were added, and their textures set to the 3D import (mipmaps, VRAM) the other
  kit textures already had. Collision is one `FURN_props-prop-colonly` proxy of oriented boxes.
- **The digest** salts `point_furniture.py`, the table and every piece it names, and hashes each lane's successor turns
  into the lane's own piece (an arrow depends on a connector in another piece).
- Measured: DebugRoads (no footways) 159 placements, 7 crossings, 14 stop lines; the island 4659 (1059 planters,
  417 bollards, 2435 drains, 682 manholes, 66 arrows, 36 crossings, 68 stop lines). Picture gate
  `tools/godot/shot_road_furniture.gd` (needs a display; frames `--per` instances of every MultiMesh from behind
  along its own forward). Two traps: a MultiMesh reads identity transforms under `--headless` (the dummy renderer),
  and an unfocused window saves the SAME frame every shot unless `RenderingServer.force_draw()` runs first.
- **Lines stop at the stop line and the zebra (2026-09-18), the Japanese layout.** A lane line on the arriving side
  and the centre line end at the stop line's upstream edge, nothing is painted across the zebra, and a departing
  lane's line starts past it. `point_furniture.clear_zones` derives the keep-clear rectangles from the SAME arm
  frames (`_arms`) and the same placement tests (`_has_zebra`, `_has_stop`) the marks are placed with, so a line
  only stops where a stop line or zebra was actually painted; `point_mesh.build(clear=)` clips every mark polyline
  against them (`clip_outside`, Liang-Barsky per segment, dashes cut at the edge, heights interpolated). Measured,
  mark vertices inside a zone: DebugRoads 423 -> **0** (of ~7.4 k), island 438 -> **0** (of ~74 k); the control is
  `clear=None`. The editor's draft (`roadkit_cli.py live --mesh`) has no lanekits and still draws lines through.
- **Signals and street lighting (2026-09-18, user-asked).** Three pole pieces from Quaternius' CC0 Zombie Apocalypse
  kit, made by `blender/tools/build_street_poles.py` (Blender, from `TrafficLight_2_Japan.blend` — the owner's
  Japanese re-make of `TrafficLight_2` — and the download's `StreetLights.blend`):
  - `TrafficLight_JP`: scaled ×1.099 so the vehicle head's lower edge is **4.7 m** (Japan: ≥ 4.5 m over a
    carriageway; the download's was 4.28), the pedestrian head lifted to a **2.5 m** lower edge. 5.84 m pole,
    5.5 m arm. Still carries the download's "E 12 St" name plate (atlas texture) — replace in the .blend.
  - `StreetLight_JP`: shaft stretched (base, collar, arm, luminaire rigid) to a **10 m** luminaire, the usual
    Japanese arterial mounting height (the download's 6.4 m is residential). `StreetLight_JP_Twin` mirrors the
    arm for a raised median.
  - Placement (`point_furniture._signals` / `_lamps`): a junction is signalised when any mouth is authored
    `traffic_light` or (`signal_all_junctions`) ≥ `signal_min_arms` (3) arms carry arriving traffic. One signal
    per arm on the **FAR side** (the Japanese position): 6 m past the end of the kerb lane's STRAIGHT connector,
    1 m outside that lane's kerb edge, facing the approach, arm over the arriving lanes; with no straight movement
    (a T stem, a Y) the pole is NEAR-side, on the arm's own kerb 0.5 m back from its mouth (junction-side of its zebra). The piece's arm reaches right of forward, so
    a right-hand-traffic arm is refused and counted (`signal_skipped_right_hand`). Lamps: twin-arm down a raised
    median ≥ 1.2 m wide every 36 m (then no kerb lamps), else kerb lamps every 36 m staggered side to side, 0.6 m
    behind the kerb, never over a barrier or `max_above_ground`, none on `shrine_touge*`. Signals are placed
    before every other solid prop, and planters, bollards and lamps keep `pole_clearance` (2 m) from a pole.
    Collision is the SHAFT only (`collide_pole`), never the arm's footprint. An asset may name its own `kit`.
  - The digest now hashes each successor connector's END point (it places the far-side signal).
  - Measured: DebugRoads 7 signals (2 junctions), 56 lamps; `point_furniture.py` self-test covers keep-left
    straight and T-stem placement, the right-hand refusal, the unsignalised 2-arm junction and the pole-only
    collider. The signals are static props: no signal phase logic exists yet.
- Not done: the Japanese-only marks (止まれ, the diamond, speed numbers) belong to our own `jp_street` kit
  (3.6b step 4).

**A car knocks a street pole down and keeps most of its speed; the pole comes back unseen (PLAN.md 3.11,
2026-09-18, user: "like arcade/GTA").** GTA's shape: static until hit, a physics body only while falling, restored
out of view.
- **Data.** `furniture.json` gives `signal` (450 kg), `lamp` and `lamp_twin` (250 kg) a
  `breakable {mass, break_speed 5, respawn 60}`. `point_furniture.put` then leaves the pole OUT of
  `FURN_props-prop-colonly` (planters and bollards stay in it) and puts the pole size and those numbers on the
  placement. `point_gltf.marker_node` writes them as flat `break_*` extras. Flat keys, because the importer
  keeps extras as one Dictionary meta.
- **Bake.** `WorldBaker.buildMultiMeshes` turns such an asset's batch into a `world.BreakableProps` (a
  `MultiMeshInstance3D`, named `Breakable_<asset>`). The node also stores each pole's base and yaw
  (`positions`/`yaws`), because a headless run reads a MultiMesh's transforms back as identity.
  - Its `pieceId` is the baked scene's stem (`WorldBaker.bakingPieceId`), so a key is the same on every peer.
  - Its runtime colliders are stripped before `pack()` (`removeRuntimeParts`, beside `stripEagerLodLow`). The
    baker adds the node to a live tree, so `_ready` would otherwise pack them into the piece.
- **Runtime.**
  - `_ready` builds one `StaticBody3D` "Poles" (WORLD layer) with a box per shaft, so a slow car and a
    walking character stop against it as before.
  - `Vehicle._physicsProcess` → `sweepStreetPoles` → static `BreakableProps.sweepVehicle` runs BEFORE the
    physics step. It checks, in the car's frame, every standing pole the car will reach this step
    (`PropBreakRules.reachesPole`: hull ±1.1 × ±2.0 m, read off its own convex shape, grown by the pole radius
    + 2 steps of travel + 0.35 m, ahead of the motion only). For each one at or above `breakSpeed`:
    - the collider goes off NOW, so the contact never happens. Giving the speed back after a contact would be
      a guess at what the solver took;
    - the MultiMesh instance gets a zero basis;
    - a `RigidBody3D` with the pole's own mesh falls (layer 0, mask WORLD, so it never stops a car; at most 12
      alive worldwide), kicked with the car's lost momentum at bumper height;
    - the car keeps `m_car / (m_car + m_pole)` of its velocity: 0.83 past a lamp, 0.73 past a signal.
  - The engine-free rules are `world.PropBreakRules` (`PropBreakRulesTest`, 8).
  - **The return** (`_process`, 2 Hz, only while a pole is down) needs all of these (`mayRestore`):
    `respawnSeconds` have passed; no remote player is within `hideDistance` (80 m); this peer's camera does not
    have the pole in its frustum within that distance; nothing stands within ~4 m (`SpatialEntityGrid`).
- **Network: NOTHING, on purpose (PLAN.md 3.11b, user decision: cosmetic state costs no bandwidth).** Every peer
  runs `sweepStreetPoles` for every car it sees move — a car it simulates (its velocity) or a puppet (its motion
  per step; a FROZEN body is the puppet mechanism and reports no velocity, so frozen always reads motion, and a
  park flag counts only while simulating) — knocks its own poles down and runs its own return rule. Only the
  simulating peer takes the speed loss, which then reaches every peer in the car's own snapshot.
  - Retired: `WORLD_EVENT_PROP_BROKEN` (number 12 is left unused, commented in `GameManager`),
    `sendBaselineBreakableProps`, `BreakableProps.applyRemote`/`brokenKeys` and the predicted/confirmed bookkeeping.
  - **Accepted divergence:** two peers can disagree about a pole for up to `respawnSeconds` (a puppet's
    interpolated path can graze a pole the real car missed), and a late joiner sees every pole standing. The worst
    visible case is a car stopping against a pole the other peer shows down, re-synced by the next vehicle
    snapshot. If a walk-test ever shows that matters, the fallback is making a pole non-solid to puppet contacts,
    or ONE unreliable rate-limited "pole down" hint from the simulating peer: no return event, no baseline.
  - Same rule for future cosmetic breakables (bollards, bins, trees). `world.Breakable` (glass, walls) changes
    line of sight and stays host-authoritative.
  - A zone that unloads forgets its broken poles: it reloads with them standing, which is out of view by
    definition.
  - `NetStats` now counts `world_event_sent` (every world event goes through `broadcastWorldEvent` /
    `sendWorldEventTo`, the two baselines that called `sendMessage` directly included) and `world_event_received`.
- **A CAR DOES NOT GET WIDER WITH SPEED (PLAN.md 0.8, 2026-09-19, user-reported: "a car driving down the middle of
  the road hits street poles").** `PropBreakRules.reachesPole` grew the car's plan rectangle by the step's travel
  on BOTH axes, so the knock-down sweep's LATERAL reach rose with speed: at 31 m/s it reached 1.05 m past the car's
  own body on each side. Measured on the island's expressway, driving **dead centre** (`-0.00 m right of it`) down
  `shuto_c1_F0` at 31 m/s: **16 poles knocked down over 2.7 km, one every ~36 m, with 0 contacts** — nothing was
  touched, poles simply fell and the car lost 17 % of its speed each time, which is exactly what "it hits poles"
  looks like from the driver's seat. The travel is now swept **along the motion only**: the rectangle is grown by
  the pole radius + `REACH_MARGIN` (the "about to touch" slack, legitimately isotropic) and then translated along
  the velocity by `LOOKAHEAD_STEPS` of travel, tested by slab intersection — exact for a rectangle swept along a
  line, and the "ahead of the motion" dot test is kept so a pole the car is driving AWAY from is still refused.
  Forward behaviour is unchanged. After: **0 poles, 0 contacts** over 2 738 m of the same drive, and the same on a
  city street, the coast road and a trunk road. **The geometry was measured and left alone** — over the island's
  1 962 poles the nearest same-deck lane centre is 2.85 m for a kerb lamp (0.60 m outside a 4.5 m lane's edge),
  2.40 m for a barrier lamp (0.15 m outside, on a barrier that is already there behind a 3 m car wall) and ≥ 2.75 m
  for a signal or median lamp, so a 1.10 m half-width car centred in its lane has at worst 1.30 m of room. No
  `furniture.json` change, no road rebuild. `PropBreakRulesTest` gained
  `theReachGrowsWithSpeedALONGtheMotionOnly` (a pole 2.40 m to the side at 10/20/31/45/80 m/s; it fails on the old
  rule), and `probe_road_launch.gd` now counts **poles knocked down** (`BreakableProps.breaksTotalNow` summed over
  the scene) and **pole contacts** — at speed a pole goes down BEFORE the contact, so the knock-down is what a fast
  drive shows and the contact what a slow one shows.
- **Two defects the wide reach was MASKING, both found by the DebugWorld launch gate the moment it was removed**
  (it went from PASS to 3 launches/falls), and both fixed:
  - **A barrier lamp stood 3 cm INSIDE the car wall.** `point_mesh` puts a barrier's centre — and the 3 m
    vehicle-only CAR WALL on its line — `2·walk + BARRIER_THICKNESS/2` outboard of the paved edge, so the wall's
    INBOARD face is at `2·walk`. `barrier_lamp_inset` was a flat 0.15 m from the edge line, which was right only
    for a road with no footway and no car wall; a 0.18 m shaft there spans −0.03…+0.33, i.e. a post 3 cm inside
    the carriageway that the wall does not protect. Measured on DebugRoads' `link` at 35 m/s with the outer wheels
    on the kerb line: **5 pole contacts and the car flipped off the bridge twice**. The offset is now DERIVED —
    `2·walk + poleHalf + barrier_lamp_clear` (0.05) — so the shaft always starts outboard of that face and, on a
    0.32 m parapet, still stands on the barrier. `_barrier_samples` returns the footway width for it.
  - **The "ahead of the motion" test refused a pole the car's FLANK was sliding into.** Scraping a kerb, the pole
    is nearly abeam and the dot product is nearly zero, so the sweep refused it and the physical collider was hit
    instead. It is now asked ONLY of a pole already inside the grown rectangle (one the car has passed, not one it
    has yet to reach): `|localX| <= hw && |localZ| <= hl && dot <= 0`. After both, the gate is back to **0 launches,
    0 falls**, and `link_F1@-3` knocks its 4 poles down cleanly instead of going off the bridge.
- **Gate `tools/godot/probe_breakable_poles.gd`** (18/18, real DebugWorld lamps):
  - 15 m/s: the lamp goes down, and a ray down the shaft then finds nothing (no static box left in the piece).
    The car keeps **79 %** and drives on.
  - 3 m/s: the lamp stands and the car stops 2.11 m short (its bumper).
  - Aged past its respawn with a camera looking at it: it stays down. Camera turned away: back, solid, the
    falling body gone.
  - A frozen car moved kinematically (a puppet) at 15 m/s knocks a lamp down by itself, and its motion is not
    touched.
  - `-- --control` (`breaking_enabled` off) fails 8: the car stops dead 2.0 m short.
  - Probe trap: holding a car's velocity INTO a contact is an infinite force that slides it round a thin pole,
    and a slow car walks 1.5 m sideways on the crossfall over 22 m. The probe re-aims every tick and lets the car
    coast the last metre.
- **Gate `tools/net/run_net_pole_test.sh`** (7/7; `debug/NetPoleTest.tscn`, `NetPoleTestHost`): the host drives a
  driverless car through one pole, the client takes the seat of another through the ordinary seat request and
  drives it through a second pole; each car is a puppet on the other peer. Both poles go down on BOTH peers, the
  side poles 6 m beside each path stand, and **0** world events are sent or received while the cars drive (2 are
  sent at join: the faction baseline). Bollards, bins and trees are the same mechanism, but none is flagged
  breakable yet.

## Edge lines, shoulders and median strips; a 踏切 keeps its own panel (2026-10-05, user-asked)

Japanese practice (道路構造令): a carriageway ends in a solid white edge line (車道外側線) with a shoulder (路肩) between
it and the kerb or barrier, and a raised median has a side strip (側帯) with a white line each side.
- **The shoulder was already a slot** (`shoulder_left/right_width`, `SH_L`/`SH_R`, paved inside the kerb line:
  `paved_extents` excludes only footways); it carried no line and the presets set it to 0. Now
  `point_profile.build_profile` paints `MARK_SOLID_W` on the lane/shoulder boundary wherever a shoulder exists (on
  `SH_L` itself, on the outermost reverse lane for `SH_R`, on `F0` of a one-way road), and the LANES DO NOT MOVE: the
  kerb, footway and everything beyond move out by the shoulder.
- **`RoadData.median_strip`** (new road field, carried onto each resolved station by `resolve_point`): the 側帯 is
  INSIDE `median_width`. The island is `median_width - 2 * strip` (`rka_med_h` in `point_solve`), and a solid white line
  runs on each median slot edge. 0 = the old island, no line.
- **Presets**: expressway outer shoulders 1.25 m (第2種 urban expressway, 首都高; 第1種 intercity would be 2.5 m), strip 0.2 m (median stays 1.0 m: the island is exactly the wall; a 0.75 m strip moved every lane 0.75 m out and broke 3 ramps and a crossing, measured);
  trunk 0.5 m + strip 0.25 m (median 2.0 -> 2.5 m); arterial / block / farm 0.5 m; lane 0.75 m (路側帯);
  coast 0.75 m (unchanged). Ramps (`point_record_ops.RAMP_SHOULDERS`): 1.0 m outer, 0.5 m inner; the OVERRIDE mouth
  has none, so the shoulders open out of the gore. `point_presets.make_one_way` turns the median's strip into a
  one-way carriageway's right shoulder (both halves of a split keep the strip and their bands do not overlap).
- **Roads whose section predates this** (the island's arterials input): `tools/island_shoulders.py` applies
  `point_presets.add_shoulders` (by road class; `CLASS_SHOULDERS`; a road that has a shoulder keeps it). It runs in
  `island_layout.derive` on the input before the generators and again after the turnarounds. Idempotent.
- **A level crossing keeps the track's surface: a 踏切 panel LYING ON the road** (`point_mesh.crossing_track`,
  user decisions 2026-10-05). ONE precast concrete panel over the whole line (`panel_span`: `PANEL_HALF` 1.25 m past
  each outer track's centre; a double track is paved between its tracks too, as a Japanese 踏切 is),
  section /----\ : a flat top `PANEL_RISE` 3 cm over the ground, the two long edges (what a wheel or a foot crosses)
  sloping down over `PANEL_CHAMFER` 0.15 m to `PANEL_FOOT` 1 cm under it, closed `PANEL_DEPTH` under; the road is
  NOT cut. In the road collision; the rails lie flush with its top.
  - **The 踏切 is ONE LEVEL PLANE** (user, 2026-10-05; option 2 of three, chosen for performance, maintenance and
    Japanese practice). Every vertex stands on `crossing_ground` = the crossed road's own surface (`road_surface_z`,
    projected onto the spine: on a graded road crossed obliquely a panel on the rail's profile stood 0.12 m proud),
    over the FOOTWAYS too, so the panel and its flush rails lie in one plane from sidewalk to sidewalk. The ROAD brings
    its kerb and footway DOWN to it: a road built against the rail (`--avoid`) runs each kerb / footway edge through
    `point_edges.level_spans` (the edge, its footway middle or back edge inside a rail band at the road's height,
    `LEVEL_DZ` 1 m, + `LEVEL_MARGIN` 0.3 m) and `level_crossings` (kerb -> 0 there, eased back over `ENTRY_RAMP` 2 m
    each side, an `EntryKerb` whose `outer` falls too, so the whole footway is lowered and furniture keeps off it).
    DERIVED, never authored (no `entry_style` value). The rail band (~5 m half) is wider than the panel (3.25 m), so the
    ramps lie outside the panel. The pedestrian zone is PAINTED: a white line along each kerb line across the panel's
    top (`crossing_ped_lines`, `<rail>__xmarks`, `PED_LINE_W` 0.15). Rejected: raising the panel over the footways (a
    15 cm step inside the crossing, rails stepped) and raising the track over the road (a hump at every 踏切).
    `Band.footway_rel` now only CLASSIFIES a crossing point as footway (`crossing_class`).
  - **The carrier is densified once** (`densify_crossings`, every `CROSSING_STEP` 0.25 m inside a crossing, each
    road / footway edge bisected), and a span counts as crossing when ANY of the panel's two edges, its centre or a
    track centre is on the road or footway: on an oblique crossing the panel's end is square to the track and reaches PAST
    the slanted footway edge, so the footway is paved over to a straight edge (user: no angled cap). The flat top
    carries a vertex every `PANEL_TOP_STEP` 0.5 m across, so on an oblique crossing each follows its own ground (one
    6.5 m face spanning the kerb at 34 deg stood 0.09 m over a lane; the self-test's 35 deg case, control 0.10 m).
  - `road_surface_z` asks each LEG of the road (heights within 1 m) for its nearest segment: a neighbouring segment
    clamped to its end read that end's height, 4 cm off on a 5 % road.
- **No markings on a 踏切, and an 一時停止 stop line before it** (Road Traffic Act art. 33): a road built against the
  rail (`--avoid`) clips every lane and centre line `CROSSING_MARK_CLEAR` 0.5 m short of a track band crossed at its
  height (`clip_crossings`), and paints a stop line square to the road per approach (keep-left: travel along the
  carrier arrives on the left), across that direction's half, its downstream edge `CROSSING_STOP_GAP` 2 m outside the
  band at both of its ends (`crossing_stop_lines`, `CROSSING_STOP_W` 0.45 m).
  - **A raised median is broken at a 踏切** (`point_mesh.median_runs`): the kerbed island stops
    `MEDIAN_RAIL_CLEAR` (1 m) short of a rail band crossed at the road's own height, each side a capped island,
    the carriageway asphalt (which runs under the island) left across the track. It used to run straight over the
    rails, a 0.15 m kerb a train's wheels met, and the rail gauge sweep (from 0.5 m over the bed) cannot see it.
- Gates: `point_profile.py` (edge lines and their control), `point_mesh.py` (the panel ON a street climbing 5 %
  through the crossing: its top at ground + PANEL_RISE, no steep face over the ground but the kerb step and the end
  caps, across the footway at footway level, in the collision, the flush rails on it; no lane mark inside the track
  band, a stop line each approach, and the control built with no rail whose lines run through; the median broken
  over the track on a trunk road).

## Street trees are ROAD FURNITURE, one species per street (PLAN.md 3.16 step 4, 2026-09-20)

The first half of 3.16 step 4. A 街路樹 is placed by **`point_furniture._street_trees`**, beside the planters,
bollards, drains, signals and lamps — not by a second placer — because "what stands on this footway" is one
question, and it is `Furniture.clear_of` that stops a tree growing through a lamp post.

- **One species per STREET**, chosen by a hash of the ROAD's name (`tree_assets`: `CommonTree_1/3/5` from the
  Stylized Nature kit). A Japanese street is planted with one tree; a per-spot choice reads as scrub.
- **Only on a footway at least `tree_min_footway` (3 m) wide**, which on this island is the trunk/arterial
  network — block streets have 2 m and get none. The trunk stands **AT THE KERB** (`tree_kerb_gap` 0.9 m), the
  Japanese 植樹帯 position and the same side every other prop already keeps to (`planter_kerb_gap` 0.3,
  `lamp_inset` 0.6): so the canopy overhangs the CARRIAGEWAY rather than the lot (the canopies start 2.35–2.58 m
  up, which is the clearance a pruned street tree is kept at), **and the trunk is off the footway's own walk
  line**. That second half is load-bearing and was a measured near-miss: `island_buildings.py` puts the
  sidewalk centreline at half the footway's width from the kerb (2.0 m on the island's 4 m footways), so at the
  1.3 m first tried the trunk's face and a walking body's capsule touched exactly — every promoted pedestrian
  would have rubbed past every tree. At 0.9 there is 0.4 m of clear.
- **The run starts half a tree spacing past where the LAMPS start.** A tree whose station lands on a lamp's is
  simply dropped by the clearance rule, which leaves the avenue with a hole every other tree; offsetting
  interleaves them instead.
- **A footway is a fact about ONE road, so the placer also asks the LANES.** `_LaneIndex` (a 20 m grid over
  every exported lane's plan segments) refuses a spot within that lane's half width plus `tree_lane_clear`
  (0.6 m) — measured on the sample network, a tree on `demo_main`'s footway stood **0.23 m off
  `demo_ramp_b_F0`'s centreline**, because a ramp runs alongside its mainline. A lamp post there is bad; a 9 m
  tree is worse.
- **The collider is the TRUNK** (`collide_pole` 0.35 m x 2.3 m), never the canopy: a box of the piece's
  footprint would stand 4 m across the pavement.
- **A per-asset visibility range was BUILT, MEASURED AND REMOVED, and the measurement is the point.** A tree is
  ~4 k triangles and a piece holds dozens, so a `visibility_range_end` on the batch looks like the obvious lever.
  It is not: **a MultiMesh is ONE instance to the renderer**, so the range is whole-batch, and a range shorter
  than the batch's own extent culls **every instance at any camera distance**. Measured on the island's
  `MM_CommonTree_5` batch (AABB 803.7 m across), camera 12 m from a tree, green pixels in the frame:
  **20285 at no range, 0 at 350 m, 20285 at 700 m, 20285 at 1200 m.** So the only ranges that render are the ones
  that cull nothing. It reads exactly like a bug in the placement — the trees vanish while still casting correct
  leafy shadows, which is how it was found (the picture, not a probe). The lever that WOULD work is cutting a
  piece's trees into several smaller batches; until then the piece's own streaming (700–1450 m) is the bound.
  The plumbing (`furniture.json` `fade`, the glTF `fade_end` extra, the `WorldBaker` branch) is gone rather than
  left unused: a mechanism that does the opposite of what it claims is a trap, not a spare part.
- Measured: **1215 trees on the island**, 44 on `RoadKitSample`, none on DebugRoads (no footway is 3 m there).
- Gate **`blender/tools/check_street_trees.py`** (in `check_roads.sh`, on the island and on the sample), which
  measures the RESULT from the other side of the pipeline — the EXPORTED LANES and the record's authored
  cross-section, never the edge runs the placer read: no tree within half a lane's width of any lane centreline
  plus the trunk's radius, every tree's road authoring a footway at least `tree_min_footway` wide, and no tree
  further from the nearest lane than that lane's half plus the footway plus 2.5 m. `--control` puts the kerb gap
  inside the kerb AND turns the placer's own lane guard off: **109 of 111 trees then stand in a lane**.
  - **Probe trap:** every network's `.lanekit.json` sidecars share `assets/world_source/pieces/`, and another
    world's lanes overlap these coordinates — loading them all reported 13 trees in a lane where one was.
    `--prefix` is the fix.

## Road types, the interchange templates, one sea bridge (PLAN.md 3.13 step 1, 3.8 steps 3-4, 2026-09-18)

- **Road types are presets** (`blender/addons/road_kit_authoring/point_presets.py`, the one owner; self-test 9, in
  `check_roads.sh`): `expressway` (2+2, wall median, no footway, barriers, `hammerhead` piers, 80 km/h,
  `taper_factor` 0.5: the world is compressed, a visible authored choice), `trunk` (3+3, raised median, 4 m
  footways, 60), `block` (1+1, 2 m footways, 30), `lane` (1+1, no footway or kerb, a painted 路側帯 edge, 30),
  `farm` (1+1 at 3.5 m, no kerb, 40). `apply_preset` writes the road's fields, its base section and every INHERIT
  station's lane counts; an OVERRIDE station keeps its own section and is reported. `roadkit_cli.py preset <record>
  <road> <type>`; the Godot dock's **Apply Road Type** picker (road or station selected).
- **Two interchange templates** (`tools/roadkit_interchange.py`, `--check` = gate 0 errors + flow 0 broken/misjoined/
  unreached/orphans + every crossing >= 5.5 m surface to surface, measured on the BUILT mesh's upward-facing asphalt;
  both in `check_roads.sh`):
  - `InterchangeTemplate.roads.json`: a DIAMOND, expressway to street (the sketch's dark-blue exits): expressway at
    10 m over a trunk road; keep-left, so eastbound ramps land on a signalised junction north of the overpass,
    westbound south; the expressway split at the overpass. 56 lanes.
  - `LoopJctTemplate.roads.json` (`--kind loop`): an EXPRESSWAY-TO-EXPRESSWAY junction, the Shibaura-JCT shape that
    takes C1 onto the Rainbow Bridge (user): no ground junction; four ramps incl. the 270-degree loop that climbs over
    its own entry (10.4 m) and over C1; the spur to the bridge as two one-way roads side by side climbing to 32 m.
  - Rules they taught, each hit as a gate error first: an exit and an entrance on the SAME carriageway of one run
    share an aux slot (`aux_slot_shared`) -- split the run (`split_at_joint`) or use the other carriageway; two ramps
    on ONE station confuse which carriageway's slot each takes -- one ramp per station; a 2-lane aux lane needs 432 m
    of taper at 80 km/h (hence the preset's 0.5); keep-left decides every merge (a ramp joins from the road's LEFT);
    a JOINT needs coincident end stations AND a tangential approach, or its lanes land beside each other (`broken`).
- **One sea bridge** (user, 3.8): `tools/island_remove_gulf_crossing.py` deleted `hama_dori__2/3/4` (the gulf span;
  the harbour junction is three-arm, setback re-solved); `hama_dori` ends at the inlet's east shore (the future
  military harbour's access). Pipeline re-run: zones 31 -> 29 pieces (stale `island_4_5`, `island_5_5` removed),
  terrain re-stamp (2636 vertices back to natural ground), 12 traffic zones, road map re-baked; reach 80.8% -> 79.0%.
- **The Rainbow Bridge is on the airport crossing** (`tools/island_rainbow_bridge.py`, `--check`): centre and heading
  DERIVED from the record (the two shore stations of `kuko_dori`), `Landmarks/RainbowBridge` in World.tscn at the road
  network's Y, `pillar_skip` on the 8 deck stations inside the span, and an alignment check over the lanekit lanes
  (32 samples, every lane >= 4.5 m inside the corridor, height error 0.00 m). The model's two road levels are
  parameters (`RB_ROAD_LOWER` 24 = the airport road, `RB_ROAD_UPPER` 32 = reserved for the expressway spur from the
  loop JCT); towers and anchorages stand on the seabed (`RB_BASE_Z` -30); `keep_origin` keeps its scene origin at the
  water line. `pillar_skip` holds from its station to the NEXT (`point_solve._bool_field`), so a station skips its
  piers only when the whole span it starts is inside the structure; `probe_road_ground.gd` counts a PIER sample inside
  a `Landmarks/*` building's footprint as carried by it (reported as its own INFO line, 802 on the island).
- **The coast is zoned, and the beaches have a shelf** (`tools/island_coast.py`, PLAN.md 3.8 steps 1-2):
  `island_coast.json` holds the coast types as rectangles (beach, cliff, industrial harbour, gulf, military harbour,
  airport island, fishing port), written from the tool's table. Every coast used to drop from +0.5 m to the -24 m
  seabed within one cell; `shelf` raises only sea cells whose nearest land is BEACH land (in a beach zone and under
  3 m, so cliffs never qualify) to -0.3 m at the waterline -> -3 m 150 m out -> the seabed by 350 m (cosine). Quays
  and cliffs keep their drop. The water shader colours by depth (turquoise + caustics over 12 m), so the shelf reads
  as a lagoon with no shader change. Applied: 391 765 sea cells (1.57 km2).
  - **The shelf never enters a hard zone** (cliff, harbours, gulf), and its target FADES to the -24 m seabed over
    `HARD_FADE` (150 m) approaching any water it does not take, so it adds no underwater wall (steepest step it adds:
    0.50 m per 2 m cell). The result is `max(h, faded target)` and the target depends on the land mask only, so the
    shelf of a shelved grid is itself: `shelf` is idempotent (a fade toward `h` was not -- a second pass raised again).
  - **`check <new> <orig>` asserts three things:** 95.5% of beach water (outside that fade) is under 2.5 m deep,
    0 quay/cliff/harbour/land cells changed, and the added step is at most 1 m per cell. It is not a quay DEPTH test:
    measured, 13% of harbour/gulf water within 20 m of a quay was SHALLOWER than 10 m before any shelf (the inlet's
    sloping ends), so "unchanged" is the rule.
  - **A stamped network's natural-ground sidecar must take the same edit** (`island_coast.py sidecar <orig> <new>`
    re-runs the shelf on the NATURAL ground -- the terrain with the sidecar's values where it covers -- so a stamp-owned
    fill toe in the sea gets the shelf too; then `stamp_roadkit_terrain.gd`), or a re-stamp or restore puts the old
    seabed back under every stamped corridor (the probe measured 191 388 vertices "re-stamped", 23.3 m off on restore). The same holds for ANY terrain edit
    under a stamped network.

## Traffic is a ring and a budget; hotspots are found by postal code (2026-09-22, PLAN.md 3.32 / 3.26)

- **`ZoneManager.trafficSimRadius` (300 m) and `trafficBudget` (20 cars across every zone)** -- GTA's two rules. A
  traffic zone decides WHERE cars may spawn; these decide how many exist and how far out. The island's traffic zones
  are sized for coverage (unload 1550 m), which alone kept ~80 cars + seated drivers simulated round the player and
  put downtown at 30 fps (physics 13-18 ms a tick, 2-3 catch-up ticks a frame). A ring WITHOUT a budget is worse,
  not better: every zone covers ~1.5 km of lanes, so all of them fill their cars inside the ring. Measured p50 downtown
  walk 33.3 -> 10.9 ms, into Tokyo Station 35.1 -> 13.8, downtown drive 32.8 -> 8.8. Zone-load spawns are
  player-gated too while the ring is on (a zone loads 1+ km out). 0 on either = the old behaviour.
- **Budget 10, ring 250 m, and the leaving car is recycled** (PLAN.md 2c, user 2026-10-07: "10 cars, recycle faster,
  keep a busy street"). `trafficBudget` 10, `trafficSimRadius` 250 + `trafficReclaimMargin` 50. A car beyond
  `trafficRecycleDist` (140 m) of every player, out of this peer's camera view and further than at the last eval tick,
  is reclaimed (reason `leaving`) so its slot respawns near the player -- but only while fewer than `trafficNearTarget`
  (6) cars are within `trafficNearRadius` (200 m), at most one every `trafficRecycleSeconds` (2 s). Measured
  (`probe_walk_perf --deck`, this PC, % frames over 16.7 ms, cars within 100 / 200 m): shipped 20-car budget 98% /
  88%; budget 10 no recycle 9.7% / 5.6%, 0.6 / 4.3 cars; recycling freely 52.6% / 38.9%, 3.7 / 8.1 cars (a recycle a
  second, the near cars all full detail); the shipped gentle rule 4.8% / 5.0%, 1.5 / 6.0 cars. `--recycle=0` is the
  probe's control; `traffic_near_now(r)` / `traffic_recycled_now` its readouts.
- **`tools/godot/probe_walk_perf.gd`** (display) moves the REAL player along walk/drive legs and files every frame
  under its postal code; it prints per-leg frame/physics times, a census (cars, seated drivers, walking AI, light
  peds) and the worst cells, which `postal <code> tp` in the console goes straight to. `--no-traffic` / `--no-peds` /
  `--no-buildings` attribute the cost.
- **`world.PostalGrid`** is the one owner of the x-y postal code (24 x 24 cells of 192 m, keypad sub-cell 1-9); the
  minimap prints it, the full map draws the grid, the console has `postal`, `tp`, `where`, and **Ctrl+F9** prints and
  copies the bug-report line (`world.PostalReport`). Gate `tools/godot/probe_postal.gd`.
- **A joint's two stations are one point, height included**: `island_layout.weld_joints` runs last (a later pass had
  left ring_kita and kaigan_machi 0.107 m apart, and the stamp put the ground 2 cm over the ring's lane).
- **A pier is founded on the lowest ground within 1.5 m of each shaft vertex** (`point_mesh.FOOT_REACH`): over a
  vertical quay (0.6 m land to the -24 m seabed in one cell) a column's sea-side foot stopped 9 m short.
- **Streets the plan removes by hand** are `island_plan.STREET_DROP` (region, axis, coordinate), for blocks too small
  to place buildings simply; the plan picture is `tools/island_plan_picture.py` (postal grid overlaid).

## The island's road layout is DERIVED: arterials in, expressway, trunk grid, streets and turnarounds out (PLAN.md 3.13 steps 2-5, 3.3, 3.3b, 2026-09-19)

**Two layers, one command.** `IslandRoads.arterials.roads.json` is the INPUT (the arterials, the touge and the airport
road as seeded and hand-fixed); `IslandRoads.roads.json` is the OUTPUT, made by **`tools/island_layout.py`**: trunk
grid -> streets -> expressway -> turnarounds -> setback, then it asserts the gate (0 errors), a clean flow (0 broken /
misjoined / unreached / orphaned / open ends) and every grade separation >= `roadkit_interchange.CLEARANCE` on the
built surface. A hand edit to the OUTPUT is lost on the next run: edit the input, or the generator that owns the road.
**`tools/island_rebuild.sh [--no-layout]`** runs the whole island after it: ground, zones (`--split`), build
(`NAV_FIT=1 DIRTY_ONLY=1`), a prune of pieces whose zone is gone (every later step globs the lanekits), stamp, traffic
zones, road map. Shared helpers: `tools/island_roadgen.py` (natural ground, filleted plans, a chain road, a station
inserted into a chain, `cut_road` to land a junction on a ground road, `make_junction`, the pier pass).

- **Expressway** (`tools/island_expressway.py`, roads `shuto_*`):
  - **C1**, a rounded rectangle inside the arterial frame (x 150-1300, y 40-720 record frame), deck 11 m, cut into four
    roads at joints (the JCT, both sides, the diamond's overpass) so no run carries two ramps on one aux slot.
  - **The airport JCT** on C1's south side is the loop template (`roadkit_interchange.build_loop`) with three of its four
    movements (the long flyover does not fit a compact ring). The **spur** is two one-way carriageways 8 m off one
    centreline: south, east at y -396, tangent onto the Rainbow Bridge's UPPER deck at the north anchorage (32 m, the
    bridge's `pillar_skip` span), south past it, and down onto the airport. The carriageways PART at the airport: each
    meets the airport road at its own T, because a pad cannot take two parallel one-way arms 16 m apart (the setback
    solver pushed such mouths 145 m out).
  - **A diamond** on C1's north side down to `naka_hondori` (junctions at y 615 inside the ring and 815 outside), its
    four ramps 260-380 m from the overpass, each a single cubic from its gore to its mouth.
  - **3 m sound walls only where C1 is central to the city** (防音壁, `SOUND_WALL`, user): its south half
    (`SOUND_WALL_ROADS`: the JCT road and the south-west road) faces downtown; the north half faces the farmland and
    the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the bridge. The median wall stays 1.1 m whatever the side barriers are (`MEDIAN_WALL_HEIGHT`).
  - **Every ramp is two lanes** (user: wider for racing): `RAMP_LANES`, and `make_ramp(..., lanes=2)` where a ramp
    merges (the default is ONE lane, and a two-lane ramp into a one-lane slot left its second lane `broken`).
  - Decks are DERIVED: the highest natural ground across the deck + `CLEAR` (11 m), a 4% grade cone. **No pier stands
    on another road**, decided per COLUMN by the build (`point_mesh.pier_on_road`: a column whose footprint is on, or
    within `PIER_ROAD_CLEAR` 3 m of, another road's paved band more than `PIER_ROAD_DZ` 4 m below is dropped; the build
    reports `pier_on_road`). It replaced a station-span pass (`island_roadgen.clear_piers`, retired: it raises) that
    could only switch a whole span off and could not split a taper span, so C1 flew 120 m and `shuto_eb_loop__2`
    250 m over the city with no column -- found by `probe_road_ground.gd`, which had not been run on 3.13. The spur's
    stations inside the Rainbow Bridge take `island_rainbow_bridge`'s own `pillar_skip` rule
    (`island_expressway.bridge_skip`). `taper_factor` 0.25 on every `shuto_*` road (the compressed world; a ring's
    corners leave no 216 m straight), and no station within `MARK_CLEAR` (112 m) of a ramp or joint station.
  - **Not built, and why:** the sketch's OUTER ring closes over the 700 m massif and the touge; the Road Kit has no
    tunnels. The coastal horseshoe that remains is not built either (the lowland is already framed by coastal arterials
    and it needs a second JCT); the E-W link through the city likewise.
- **Trunk grid** (`tools/island_trunk_grid.py`, `trunk` preset 3+3): `nishi_hondori` (x 400), `naka_hondori` (725),
  `higashi_hondori` (1100) from rinkai_dori to nogyo_michi, `ekimae_dori` (y 250) from chuo_dori to hama_dori, and
  `yamate_dori` upgraded. Every crossing a signalised junction; an existing road is CUT for one.
- **Streets** (`tools/island_streets.py`): regions of N-S and E-W lines, each clipped to between its first and last
  crossing, so every street ends on a road. City (block preset, one street down each trunk cell, south of y 560 where
  the diamond ramps come down: they passed 3.1 m over two streets before), the south-west residential lowland (3.3's
  reach gap 2) and the north-east farm grid (farm preset). A line is nudged up to 60 m before it is dropped; a crossing
  of two new lines is kept only where one of them runs THROUGH it (never a two-armed pad); water is judged only once
  the crossings have settled (a partner dropped in the same pass shortens a line).
- **Turnarounds** (`tools/island_turnarounds.py`, 3.3b): every road end that joins nothing becomes a mouth of a 3-arm
  junction with a loop (a teardrop until 2026-09-22, a rounded square since -- see "The map shows the city"), its axis and reach searched for flat land clear of
  every other road; an end with no room is shortened a station at a time. 7 ends, `open_end` 15 -> 0.
- **Measured:** gate 0 errors; flow 1811 lanes, 0 broken / misjoined / unreached / orphans / open ends; 31 grade
  separations, tightest 7.7 m (the airport loop over the westbound exit).

**Five kit defects this surfaced, fixed in the kit:**
- **A T has no straight ahead** (`lane_movements.allowed_turns(available=)`): a middle lane restricted to S led
  nowhere, `broken` at every T with a 3-lane stem (and at the harbour T the gulf removal left, 2 lanes since 3.8). With
  no S on offer the approach splits kerb half -> nearside, median half -> offside.
- **A right turn lands in the median lane** (`target_lane(turn=)`, the road rule; left turns keep the kerb lane).
- **A lane beside a reached lane is reached** (`point_flow.flow_report`): a lane change (`inner_lane`/`outer_lane`)
  reaches it, which is how an aux lane was already entered; a 3-lane trunk off a T is fed into two lanes.
- **Lane-change edges come from EVERY station** (`point_export._adjacency`, widest first): a run with one carriageway's
  aux block at one station and the other's at another has no station holding both, and the lane missing from the widest
  got no edge.
- **A `WALL` median builds its wall** (`point_mesh.median_wall`): `point_solve` had always
  said "RAISED, and a barrier stands on it" and nothing built it -- the expressway's divide was a 0.16 m island. A 0.6 m
  prism, `point_solve.MEDIAN_WALL_HEIGHT` (1.1 m) tall, as its own `<road>_median-road-noped-colonly` COLLIDER; what is
  SEEN is the kit's median panel (user: Quaternius' `TrafficHighwayMidWall`, fitted to 1.1 m by `build_zombie_yard.py`)
  tiled end to end by its own length (`point_furniture._median_walls`, furniture asset `median_wall`; 1028 panels on
  the template's 1.6 km). A fence panel is no collider to scrape at speed, a continuous prism is.
`point_digest` now salts `lib/lane_movements.py` too (it decides every connector).

**Lamps on barriers** (`point_furniture._lamps`, user): where an edge carries a barrier (a deck, a ramp, a bridge
parapet) the kerb lamp is skipped, so an expressway was unlit; now a single `lamp` (the base StreetLight, 10 m
luminaire) stands ON the barrier every `barrier_lamp_spacing` (45 m), staggered. A WALL median takes the median lamp
(`lamp_twin` slot, on the wall's top at `MEDIAN_WALL_HEIGHT`) when that asset exists (`median_wall_lamp_min_half`
0.45); remove the slot (the user is replacing the twin with a simpler Japanese lamp) and the barrier lamps light the
expressway from the sides.

**Sites** (`tools/island_sites.py`, 3.8 steps 5 and 8), each STREAMED as a `SiteZones/<Name>` ZoneMarker whose Zone
places the building scene in world space (`geometry_world_placed`; the dock's road cut skips a zone streaming a
building, `road_kit_zones.is_traffic_only`):
- `ContainerTerminal` (composite, `tools/building_kit/site_container_terminal.py`): 364 x 218 m on `Harbour_Apron`
  slabs, four ship-to-shore cranes (30.48 m gauge, booms raised to 88 deg so nothing overhangs the quay), bollards,
  light masts, ~800 stacked containers; its front laid on the industrial harbour's east quay, a line least-squares
  fitted through 33 edge samples of the natural ground (worst 2.5 m off). 624 k vertices merged, so it streams (900 m).
- `ShuriCastle` (`library_landmarks.shuri_castle`): the Seiden (29 x 17 m, red lacquer, two red-tile roof tiers, a
  karahafu, gold dragon pillars) on a striped Una with the Hokuden, Nanden and Houshinmon, all on a 25 m Ryukyu-limestone
  platform the hill slopes into. Sited by search: a ~140 m patch at 3-27 m, no road within 85 m, the massif behind:
  (-580, -40), facing downtown.
- **The yard pieces are Quaternius'** (Zombie Apocalypse kit, CC0, credited): `blender/tools/build_zombie_yard.py`
  writes containers fitted to ISO 668 (the 40 ft box is the 20 ft model stretched; decimated to 25% of its faces --
  ~800 in one terminal were 1.3 M vertices), pallet, drum, cone, plastic barrier and tyre stack into
  `kits/quaternius_zombie_apocalypse/pieces/yard/` + its `pieces.json`, so a composite names
  `quaternius_zombie_apocalypse:<Piece>`. **A third-party kit stays its own folder** (the licence and credit
  boundary); the `.blend` files the tools build from are copied into its `blends/`, and the download (`source/`) is
  deleted (2026-09-19). New library pieces: `Harbour_Crane/Bollard/Fender/LightMast/Apron`, `ShuriCastle`; palette `MI_CraneRed`,
  `MI_LacquerRed`, `MI_RoofTileRed`, `MI_Limestone`.

- **The crane's collider is BOXES, not its hull** (user: a character or car must pass under a crane). A composite prop
  may say `collide: {"boxes": [[cx, cy, cz, sx, sy, sz], ...]}` in its own frame (`layout_buildings.place_props`), and
  `site_container_terminal.CRANE_BOXES` / `MAST_BOXES` are the bogies, legs, sill and side beams and girders. A
  composite also carries `clear_probes` (points that must stay open), and `probe_buildings.gd` fits the character's
  capsule at each: one under every crane's portal. Control: the crane back on its bounding box fails all four.
- **Generated pieces are safe to hand-edit** (`blender/tools/build_library.py`): each procedural or landmark piece
  stores a fingerprint of its mesh and materials (`lib_generated`), and `--procedural` KEEPS a piece whose fingerprint
  no longer matches ("KEPT Harbour_Bollard"); only `--force` / `--only=<Name>` regenerate. Every piece carries an
  `edit_note` (what else assumes something about it), and the `.blend` a `README_artist` text from
  `kits/library/ARTIST_NOTES.md`; the Zombie kit's owner blends have `kits/quaternius_zombie_apocalypse/blends/README.md`.

**Headless streaming loads synchronously** (`ZoneManager.threadedLoadMode`, `-1` = auto). Under `--headless` the dummy
renderer's mesh storage is not safe against meshes created on the loader thread while the main thread creates others:
it logs "Attempting to initialize the wrong RID" / `mesh_add_surface: Parameter "m" is null`, then segfaults, and the
island's larger pieces made two loads overlap often enough to crash `probe_island_zones.gd` most runs. Auto = threaded
unless `DisplayServer.getName()` is `headless`; a real renderer queues cross-thread calls. `warmDependencies` loads a
piece's non-scene dependencies on the main thread first (not enough alone: 1 of 3 runs still crashed). `ZM_TRACE=1`
prints every streaming step. Cost, headless only: the worst frame of the island drive is 134 ms (a whole piece parsed
in one frame); p99 5.6 ms.

## Every grade break is rounded, and what is left is named (PLAN.md 0.7, 2026-09-20)

**A car at speed was thrown into the air on roads with no hole and no bad collider.** Measured, ruled out
first: not a hole (80 m sectioned, continuous), not the physics rate (same at 60 and 120 Hz), not the wheel
sensor (same with rays, sphere and tyre cylinder). What was left is a **GRADE BREAK** — a profile is built span
by span (`bench_profile`, a grade cone, a deck's `CLEAR` over the ground) and **every one of those holds a LIMIT
per span and says nothing about the CHANGE from one span to the next**, so a road can meet its 5 % limit at
every station and still step from −3.13 % to +3.12 % across one of them. At 45 m/s a 6 % break hands the wheels
~2.8 m/s of vertical velocity in one tick and the suspension throws the car.

**`tools/island_grades.py` is the one owner of that change**, and it is 3.2d's rule (`vertical_curves`, built
for the touge) applied to every road instead of one: `smooth` replaces each profile with its own **moving
average over `LENGTH` (80 m) of arc length**, which IS a vertical curve (K = 8 m/% on a 10 % break) and — because
the derivative of an average is the average of the derivative — **can never make a span steeper than the
steepest it was built from**, so it is safe to run over a whole network with no per-road re-check. `rank` is the
measurement, over the BUILT lanekits rather than the record, because what a car drives is the exported Path3D.
It is step 6 of `island_layout.py`, after the setback solve.

**What is HELD, each for a measured reason:** a junction mouth (a pad is solved FROM its mouths); a ramp mouth
**and the station after it** (that span is the gore, where the ramp and the carriageway still share paving —
dropping the far station tilts it, which is a past defect, not a worry); every station of a `pillar_skip` deck
**and the one either side** (the deck is fitted to a structure — the Rainbow Bridge's road is gated to 0.5 m over
its span — and the span boundary falls BETWEEN two stations); and the first and last station of every CORRIDOR,
where a corridor joins roads across a `split_at_joint` JOINT and smooths them as ONE profile, exactly as the
terrain stamp already joins them.

**A held station is a BOUNDARY, not a pin.** Each stretch between two anchors is averaged separately, extended
past its own ends by its end SLOPE, so a stretch that is straight where it meets an anchor comes back untouched
there. Averaging the whole corridor and pinning the anchors afterwards is what does NOT work: it took a diamond
ramp's 6.15 % break to 6.40 %, because the station 36 m past the anchor moved and the anchor did not.

**Measured on the island**, rebuilt end to end (`tools/island_rebuild.sh`: record → ground → zones → pieces →
stamp → traffic → map), 299 stations moved in 164 corridors, biggest move 0.70 m:

| grade breaks over | 2 % | 3 % | 4 % | 6 % | worst |
|---|---|---|---|---|---|
| before | 508 | 202 | 39 | 3 | **6.25 %** (`kaigan_dori__8`, a −3.13 → +3.12 sag) |
| after | **114** | **34** | **8** | **0** | **4.68 %** (`shuto_d_bwd_on`, a ramp CREST) |

over the same 49 970 through-lane samples. The gate, flow and crossing asserts are unchanged by it (0 errors,
0 broken/misjoined/unreached/orphans/open ends, 31 crossings, tightest 7.7 m).

**A vertical curve needs stations to be followed**, so `smooth` NAMES every break it could not take below 3 %
rather than passing silently — 17 roads before, **7** after, and all 7 are span-limited (their spans are longer
than the curve): the two bridge approaches, the four diamond ramp crests and the spur's deck approach. Those
want stations or a re-graded alignment, not a different constant; densifying the diamond ramps was tried and
bought 0.06 pp.

**Re-driven at 45 m/s with the corner governor off** (`probe_road_launch.gd`, a player's speed, not traffic's),
9.9 km over six cases, **every remaining launch is attributable and none of them is a grade break**:

| case | launches | worst rise | what produced it |
|---|---|---|---|
| `kaigan_dori_R1` | **0** | 0.84 m/s | — (the road that held the 6.25 % worst break) |
| `shuto_d_bwd_on_R1` | **0** | 2.98 m/s | — (the worst break LEFT, 4.68 %: a crest unloads, it does not throw) |
| `shuto_d_fwd_on_R1` | **0** | 2.88 m/s | — |
| `kaigan_dori__8_R1` | 1 | 7.05 m/s | **an ambient car** (`Characters/PIT1`) at 47 → 24 m/s |
| `kuko_dori__2_F1` | 2 | 11.39 m/s | ran 25 m wide onto the footway and the car wall; one at the bridge approach |
| `kuko_dori__3_F1` | 2 | 4.00 m/s | ran 25 m wide |

**Cause 1 is the probe's own brain, and it is now provable rather than inferred.** `LaneDriveProbeController` is
deliberately blind to other cars so a launch run is not spoiled by traffic, which means it rear-ends them at
45 m/s; `probe_road_launch.gd --see-obstacles=1` gives it the shipped sensing back. Same lane, same speed:
**1 launch at 7.05 m/s blind → 0 launches, worst rise 0.57 m/s** over 1793 m.

**What is genuinely left is the Rainbow Bridge approach**, and `island_grades` named it before the drive did.
`kuko_dori` climbs +0.89 → +3.10 → +7.62 → +8.00 % and then steps **+8.00 % → 0.00 % in one station** at the
first `pillar_skip` (deck) station, with the mirror step at the far end (0.00 → −8.00 %) easing to −6.16 % and
then **−6.16 → −0.79 % across an 88.9 m span** — the sag that threw the car at (1711, 10, 1543), 0.93 m from the
lane centre, not running wide. The deck may not tilt and its approach stations are 64–139 m apart, so the 80 m
curve has nowhere to work: that approach needs stations (or a re-grade), which is authored geometry.

## The north-west coast road: a bench cut into the cliff, with rock sheds (PLAN.md 3.15, 2026-09-19)

`kaigan_dori` closes the sketch's outer ring where the expressway cannot go: 4.0 km round the massif's north-west
cliffs, from `kitahama_dori__3`'s end (a JOINT: the coast road continues it westward) to a new T at the
`nishihama_dori__2` / `rinkai_dori` corner (the corner's fillet dropped; nishihama -> coast road is the through road).
**User decisions:** a shelf CUT INTO THE CLIFF FOOT, never a viaduct or fill in the sea (the island stays compact);
2 + 2 lanes; rock sheds (洞門 / ロックシェッド) first, one true tunnel later.

- **The alignment is derived once, then authored** (`tools/island_coast_road.py derive <dump>`, the touge's shape):
  from a Terrain3D height dump (`dump_height_grid.gd -- <out> -2304 -2304 1153 1153 4`) it walks the coast with the sea
  on its left, `D_TARGET` 17 m inland of the water line (paved half 10 + the stamp's 6 m verge = the flat ends at the
  cliff edge, the sea in view past the barrier), smooths, pushes back inland anything under `D_MIN` (a chord across a
  cove cuts toward the water), and resamples at 30 m. Height: no higher than the ground at the band's SEA-side edge
  (+0.3, at least `Z_MIN` 1 m, at most `Z_BENCH` 12 m) nor the ground under the centreline, lowered by a 5% cone, so the
  road only ever CUTS. The first version held a 12 m bench everywhere, and the pictures (`tools/godot/shot_coast_road.gd`,
  needs a display) showed why that is wrong here: this coast has a strip of sand at the cliff foot the whole way round,
  so the road stood on a vertical rock wall 12 m over the beach (the stamp does not fill a cut deeper than `CUT_MAX`, and
  filling it would push an embankment into the sea). It now runs at 1-3 m on the flat strip with the cliff cut beside it. Written to `assets/world_source/pieces/IslandCoastRoad.json` (stations with
  z, shed spans), reviewed like the record. `add` puts it into a record, terrain-free; `island_layout.py` runs it first.
  Measured: 4012 m, nearest the water 12.5 m (the paved edge stays on land), steepest 5.0%, four 300 m sheds.
- **`coast` road type** (`point_presets`, and the dock's picker): 2 + 2 at 4.5 m, a painted median, 0.75 m shoulders, no
  footway, barriers both sides (`ped_access` off), 60 km/h, `cut_batter` 10.
- **`RoadData.cut_batter`** (new road field): the UPHILL side's cut face in metres of rise per metre across; 0 = the
  stamp's ordinary 1:1 batter. A 1:1 face on a 150 m cliff would slice 150 m back into the mountain. Which side is
  uphill is DERIVED per corridor point (`roadkit_cli._steep_side`: the natural ground `STEEP_PROBE` 16 m past each paved
  edge) and handed to the stamp as a 7th corridor-point value, signed in GODOT axes (the kit's sign flipped: Godot z is
  -kit y); `road_kit_stamp.height_at` uses it on that side only.
- **`PointData.shed`** (new station enum, append-only: `NONE`/`OPEN_LEFT`/`OPEN_RIGHT`, which side is open against the
  chain direction), held to the next station like `pillar_skip`, solved into `rka_shed`. `point_mesh.sheds` builds per
  span: a roof slab whose soffit is `point_solve.SHED_CLEAR` (5.5 m) over the road, `SHED_ROOF` (1 m) thick, from past
  the open-side columns to `SHED_BACK` (5 m) past the closed-side wall -- over the stamp's flat verge to the cut face, so
  no daylight shows between roof and rock; the wall against the rock; a 0.8 m column every `SHED_COL_SPACING` (8 m) on
  the open side; two rows of lamp panels under the soffit in `M_TunnelLamp` (sodium orange, emissive,
  `road_kit/materials/M_TunnelLamp.tres`, applied by name at bake). The concrete is also its own
  `<road>_shed-road-noped-colonly` collider.
- **A bench road fills over LAND only** (corridor kind `BENCH`, `road_kit_stamp.LAND_ONLY`): the CLI reports every
  point of a `cut_batter` road as `BENCH` (a centreline cut deeper than `CUT_MAX` would otherwise be `TUNNEL`, which
  never fills, and the road's sea half stood 1-2 m over the sand on its own side face), and the stamp fills such a
  point only where the natural ground is at or above the water line (`LAND_Z`). Measured on a terrain diff against a
  dump taken before the road: the first stamp raised 67 sea cells by up to 28 m where the flat verge overhangs a cove;
  with `BENCH`, 0 on the coast.
- **A turnaround's verge must be on land too** (`island_turnarounds.SHORE`, 13 m round every probe point): the same
  diff found `futo_dori_loop` (3.3b) on the quay with its verge over the harbour, 175 cells filled up to 28 m.
  `futo_dori_loop` and `rinkai_dori_loop` moved.
- Self-tests: `point_mesh.py` (the shed: soffit, columns on the open side, wall + roof to the rock, mirrored),
  `point_presets.py` (coast passes the gate), `tools/godot/test_roadkit_stamp_rules.gd` (the steep face on the named side
  only, and the control with none; in `check_roads.sh`).

**A traffic car can run off the edge of the streamed road, and that has its own reclaim reason** (`stream-edge`). Since
3.10 road pieces stream at 700-1450 m while traffic spawns up to 0.9 x 1550 m from a player, so a car heading away can
reach a lane whose named successors are in a piece that is not loaded; `advanceToNextRoute` finds none and the car is
`isFinished`, which read exactly like a dead end in the network. `VehicleAIController.finishedAtStreamEdge()` marks it
(the lane NAMES successors and none resolve), `ZoneManager.cullFinishedVehicles` logs and records the reason
(`reclaimReasonOf(instanceId)`, registered, the last 256), and `probe_traffic_spawn.gd` exempts only that reason, as it
already exempted leaving range. Measured before: a car set down 640 m from the player vanished after 82 m at 720 m,
just past a road piece's 700 m load radius.

**`LaneGraph` follows the lanes that are streamed** (found driving the coast road, 2026-09-19). Its proximity graph was
built ONCE per scene by a scene-tree walk, so after 3.10's zone streaming it held freed lanes as successors (1086
"Cannot call a method on a previously freed instance" in one 4 km drive) and never saw a piece that streamed in later.
`LaneGraph.invalidate()` is called by `ZoneManager.registerRoute` / `unregisterRoute`, the graph is rebuilt lazily from
the registry (`ZoneManager.registeredLanes()`, never a tree walk; the walk remains only for a scene with no ZoneManager),
and a car whose own lane was freed under it (its piece unloaded) finishes as `stream-edge` instead of querying it
(`VehicleAIController.gatherInput` / `advanceToNextRoute`). Measured after: 0 freed-instance calls over the same drive.

**A barrier has an invisible CAR WALL behind it** (2026-09-19; the user's "ramp walls' collision is not right at speed").
Measured on the diamond's exit ramp (`probe_road_launch.gd -- --lane=shuto_d_fwd_off_F1 --offset=-2`, 25 m/s): a car
pressed into the 1.15 m parapet caught the wall's TOP edge with its hull and was thrown up it -- 4 launches, 7.7 m/s of
rise, contacts on the barrier's top face. The parapet is a proper closed 0.32 m prism; a wall that low simply has an
edge to climb. `point_mesh._edge_run` now adds, wherever a barrier stands (road flanks, junction corners, gore noses),
a collision-only wall on the barrier's line `CAR_WALL_HEIGHT` (3 m) tall, as a `<edge>_carwall-carwall-noped-colonly`
proxy. `WorldBaker.applyCarWalls` puts those bodies on `CollisionLayers.CAR_WALL` (layer 6, 32) with mask 0, and only
`Vehicle.tscn` and `Motorcycle.tscn` bodies have it in their mask (19 -> 51): bullets, characters, wheel rays and the
navmesh never see it. `point_mesh.py` self-test asserts the wall's line and height, and none without a barrier.

**The natural-ground sidecar is kept only where a stamp reached** (`road_kit_ground.stamp_reach` / `natural_height`,
2026-09-19). Once a network is stamped, re-sampling its ground took the old sidecar as the natural ground wherever the
sidecar covered, i.e. over the whole footprint + 60 m -- so a terrain edit made after the first stamp (the harbour
dredged to -24 m) never reached it, and the spur's portal columns stretched to the old seabed stood 3.3 m above the new
one (`probe_road_ground.gd`). Now the old value is kept only where the previous stamp's corridors reach
(`road_kit_stamp.height_at` over the recorded corridors is not NaN); everywhere else the terrain was never stamped and is
sampled. The documented rule still holds for the corridors themselves: re-sculpt under a road only after Restore.

**Probe notes.** `probe_road_stamp.gd`'s support-kind lookup is a 32 m bucket index (it scanned every corridor point
per lane sample: 58 k x 70 k on the island, past 50 minutes; DebugWorld now 7 s). `probe_road_ground.gd` counts a PIER
sample on a span over another road (a lane more than 4 m below within `SPAN_REACH` 60 m) as carried and reports it,
skips the hanging-column check inside a landmark's footprint and where a cell's lowest vertex is a deck SOFFIT (a
lane 0-3 m above it within 8 m): two stacked decks -- the Rainbow Bridge's, a JCT loop over its exit -- read as a column,
and prints its phase timings. **Do not pass `--fixed-fps` to the static probes** (`probe_road_ground`,
`probe_road_stamp`, `probe_gps_route`): under it `probe_road_ground` on World.tscn ran 50 minutes to its timeout, and
about a minute without it.

## "Has the world finished streaming" has ONE owner; nothing solid stands in a carriageway (PLAN.md 3.35, 2026-09-22)

**`ZoneManager.streamingPendingNow()`** counts the whole outstanding queue: in-flight tasks, plus every marker
inside its load radius with nothing loaded, plus every loaded marker past its unload radius. 0 means quiet.
It exists because a caller watching one KIND of zone cannot answer the question: `probe_island_zones` settled on
"the ROAD set has not changed for 1 s", and the island's 221 markers (39 road zones, 82 building cells, 71 crowd
zones, 29 traffic zones) put 100+ of them in range of any stop -- so while the pipeline worked through the
building cells the road set legitimately stood still, the probe called that settled, and then failed its own
coverage check on zones that were merely still queued (the pre-existing failure the forty-eighth session handed over).
**It was the probe, not the streamer**: settled on the real predicate, the worst wait for the streamer to go
quiet is **4.7 s** against a 90 s cap, and the gate is 8/8 + the drive over all 39 stops. Counting only LOADS was not enough
either -- the symmetric half (a zone past its unload radius) then failed at 2078 m, so the readout owes both
directions or it answers a different question from the one its name asks.

### `probe_road_clear.gd` -- the driving space is asked of the COLLISION, not of a placement rule

A road is assembled by several owners that each put solid things near a lane and none of which sees the others:
the Road Kit's piers, median and sound walls, rock-shed columns, the 3 m car wall on every barrier,
`point_furniture`'s signals, lamps, planters, bollards and trees, and -- outside the road pipeline entirely --
lot slabs, sites and landmarks. Every one has its own clearance rule and every rule is about the LANE EDGE.
None of them asks the question a player asks, so the gate does: it sweeps the CAR's own envelope
(`CAR_HALF` 1.10 m either side of the lane centre) along every exported lane of every streamed piece, on a
vehicle's own mask (`WORLD | CAR_WALL`), in two bands -- **OBSTRUCTION** (0.30-1.20 m, in front of the bumper,
FAILS) and **HEADROOM** (1.20-2.00 m, only the roof would touch, reported) -- so a low soffit cannot mask a
bollard and a kerb, a lane line and a deck 5.5 m up are all legitimately outside it. The probe instances the
pieces itself (`Zone.placeGeometry`'s rule) and then FREES every ZoneMarker, because a streamed second copy in
the same physics space would answer a query the probe did not ask. `--control` drops a post in every 40th lane.
It belongs to the Standard gates and must be re-run after any road, furniture, site or landmark change.

**A SIGNAL AND A LAMP HAD SKIPPED THE ONE OWNER OF "IS THIS SPOT IN A CARRIAGEWAY".** `point_furniture._LaneIndex`
exists precisely because a footway is a fact about ONE road (a tree on `demo_main`'s footway measured 0.23 m off
a ramp's centreline), and the trees and the edge props asked it -- while `_signals` and `_lamps` never did, so a
far-side signal stood in the left-turn path it faces and a median lamp stood in a neighbouring road's lane. Both
now nudge the pole OUTBOARD (`_out_of_lane`, `POLE_PUSH_MAX` 2.5 m in 0.25 m steps) or are dropped and counted
(`signal_moved_clear` / `signal_in_lane` / `lamp_in_lane` / `lamp_twin_in_lane`; a median lamp cannot move).
**The margin is the SHAFT's own radius plus `pole_lane_clear` (0.15 m), not a bollard's generous
`prop_lane_clear` (1.2)**: the question is whether a car meets the pole, and a Japanese signal stands AT the
kerb by design -- the bollard margin would have moved every signal in the world. The self-test's own fixture
carried the defect (its near-side signal sat 2.18 m from a 2.25 m half-lane left-turn connector), so it asserts
the new rule plus a control rather than the old hard-coded coordinate. **Measured on the rebuilt island:
21 blocked lanes -> 9, every one of the 12 signal/lamp lanes clear**; on one piece (`island_4_4`) 1 signal
moved clear, 1 dropped, 4 kerb lamps and 10 median lamps dropped -- a dropped median lamp is nearly always one
standing where a turn connector crosses the median, which is where Japan does not put one either.

**What one run found, and it is four different defects -- three of them invisible to every existing check.**
Beside the poles, measured from the lanekits at each reported spot: **a PIER standing in the loop's own lane**
(`shuto_eb_loop_F1` runs 9.71 m BELOW `shuto_eb_loop__2`, so what is in its driving box is a column, and a
column lives in `<road>__surface`, which is why the hit is filed under the surface proxy's name --
`point_mesh.build` passes `own = {road_name}` to `pier_on_road` so a pier is not refused for standing on the
deck it CARRIES, and a loop or a switchback passes under its own alignment, where that exemption is exactly
wrong); **a ramp diverging 0.25 m below its mainline while still under its deck** (`shuto_d_fwd_off_F0` is
2.49 m beside `shuto_c1__6_F1` at dy +0.25, a step rather than a crossing, so `roadkit_interchange --check`'s
5.5 m rule -- which measures DIFFERENT roads -- cannot see it); **a gore nose's footway and car wall laid
across live asphalt** (the two lanes it sits between are 4.50 m apart at the same height); and
`site_tokyo_station`'s collider over `naka_hondori` (3.33's known placeholder, now with a number).
DebugWorld fails it too, and truly: `loop_F1` runs 0.6 m inside the hand-authored CSG blockout.

### Three of those four, fixed -- and each was a fact asked of a LABEL instead of of the geometry (2026-09-22)

- **A ROAD IS NOT EXEMPT FROM ITSELF.** `pier_on_road` took an `own` set of road names so a pier was never
  refused for standing on its own road -- right for the deck it CARRIES, wrong for a road that passes under
  ITSELF (a loop ramp, a switchback, an interchange spur). The name was never the fact that mattered: **the
  deck a pier carries is AT its soffit**, so the existing height test (`PIER_ROAD_DZ`, 4 m below) already
  tells the two apart whoever owns the band. Dropping the exemption is not a widening of the rule -- it is
  the same rule asked of the geometry. `point_mesh.py` self-test carries both cases (the deck at the soffit
  is allowed; a band named like the pier's own road 10 m below is refused). **It needed a second half
  (2026-09-25), found by `probe_road_clear` still failing after the rebuild:** `Band.surface_z` is the
  NEAREST spine sample, and a loop's band covers the pier's point TWICE, so it returned the upper leg's
  height and the pier survived. `pier_on_road` now asks `Band.lowest_surface_z` (the lowest spine height
  within 6 m of the nearest sample).
- **A GORE'S CAP IS A LIE WHEN ITS TWO BOUNDARIES NEVER PAIRED.** 3.35 guessed "the nose is too far back";
  the measurement said otherwise. The mainline boundary is the ramp's points PROJECTED onto it, and that
  projection CLAMPS at the end of the mainline's own edge walk -- so once the ramp outruns it, every later
  ramp point pairs with the SAME foot and the "gap" is a slide ALONG the road, not across a wedge. Measured
  on the island: that gore came back with **two identical mainline points, length 0.00 m and a nose gap of
  27.79 m**, and its cap was struck 27.79 m across `shuto_eb_loop__2`'s own carriageway. The signed gap
  cannot see it (the perpendicular offset stays small), so the refusal is asked of the CAP, the one number a
  wall is actually built from: `GORE_CAP_SLACK` (2.0 m past `GORE_NOSE_WIDTH`) plus a refusal of a
  zero-length strip. That bound is the one the self-test's own "a cap is a wall across the ramp" case had
  asserted since 8j and which the solver never checked. Measured after: **8 gores -> 7**, the degenerate one
  gone and the other 7 unchanged to the centimetre (gaps 4.10-4.49 m, lengths 8.3-20.2 m).
- **A SLIDING MOUTH TAKES ITS ROAD'S OWN HEIGHT AT THE NEW PLACE** (`point_solve._setback_pass`). W17 made
  the setback idempotent and made a mouth slide along its own road; the slide wrote back **`m.pos[2]`, the
  height it had BEFORE moving**, so on any road that is not level the stop line ended up at the height of a
  station metres away -- and a pad is solved FROM its mouths (`_idw_z`), so the pad then had to cover the
  error over the setback. Measured: `shrine_touge__16`'s east mouth slid ~20 m down a 10 % descent and
  landed **2.26 m above** `nishi_dori__6`, which it Ts into 19 m away -- a pad **19.9 %** steep on its left
  movement. **It is general, not the touge's**: every junction on a graded road carried a share of it, and
  two more `pad_grade` WARNs (13.1 %, 10.2 %) are the same shape. The slide now takes the road's grade from
  the span to the station beyond the mouth -- the same `seg` the `MIN_MOUTH_CLEAR` clamp already reads, and
  the only piece of this road the mouth is sliding along. It converges with the plan position, so W17's
  fixed point is unaffected. Self-test: a crossing whose north-south road climbs at 10 % with its mouths
  parked close in, asserting each moved mouth still lies on its own UNTOUCHED stations' line (< 0.05 m),
  with an inline control that the old behaviour is wrong by > 0.25 m.

**A pin is not always the cause.** B6 was written as "ease the touge's last spans onto 0 m", and the touge's
own generator looked guilty: both ends were pinned to the RAW GROUND (`raw(*EAST_FOOT)`) rather than to the
arterial they join. That rule was wrong and is fixed (`island_touges.arterial_point` -- a T must arrive at
the road it meets, and an arterial is draped and then smoothed, so it is not the ground) -- but re-deriving
with it produced a **byte-identical alignment**: its last station was already at z 0.26 against the
arterial's 0.00. The 2.26 m was put there afterwards, by the setback. Measure the OUTPUT record, not the
generator, before believing a generator is at fault.

## 踏切 rules for traffic, a breakable 踏切 unit, the far traffic tier, the Deck perf proxy (2026-10-05)

PLAN.md steps (b), (d), (e) and R-1 / R-9 / R-10, plus a user ask.
- **一時停止 at every 踏切** (Road Traffic Act art. 33, `VehicleAIController.crossingHold`): a car stops at the hold
  line of every level crossing ahead on its lane, open or closed (`TrainSystem.nextCrossing`: crossings of one lane
  within `CROSSING_GROUP` 25 m are one 踏切), stands `LX_STOP_SECONDS` 1 s, and enters only when no vehicle slower
  than 2 m/s stands between it and `LX_ROOM` 7 m past the far side (`farSideQueued`, rays along the lane on the
  VEHICLE layer) -- a car that entered behind a queue was left on the tracks (R-1). A completed stop is remembered
  per lane + crossing, so one 踏切 never stops a car twice. `racing` skips it; a police pursuit flag does not exist
  yet. `crossing_stops` (`@Visible`) is the control. Waiting there counts as waiting for a signal (no stall reclaim).
  **One hold line per 踏切** (PLAN.md 0.16, 2026-10-06): `TrainSystem.stopDistance` holds a car before the FIRST track
  of a crossing group for a closure on ANY of its tracks (`groupStart`). With a line per track, a car crept up to the
  far track's line, 4 m past the real one, which put it more than `COMMITTED` past the near track's line: it then
  ignored the near track and drove onto it in front of the second train once the far one had passed (1 island traffic
  run in 10 lost a car). And a car past the hold line is held while it can still stop short of the train
  (`LX_DANGER` 2.5 m from the first track at `LX_BRAKE` 6 m/s^2), not released at 3 m past the line: logged, cars crept
  3-4 m on a closed crossing and were let go 6 m short of the rails. `group_hold` (`@Visible`) is the control for both;
  `probe_lx_stop.gd` cases 3 (only the far track force-closed, `TrainSystem.force_crossing_closed_now`) and 4 (a car
  standing 4 m past a closed line) fail with it off. Why cars creep on a held line is not known. A vehicle a train hits is logged with the car's
  crossing state (`VehicleAIController.describeBlock`'s `lx[...]`). `probe_lx_lead.gd [-- --world=island]` reports how
  long each crossing has been closed when a train reaches it.
  Gate `tools/godot/probe_lx_stop.gd` (DebugWorld, `TrainSystem.crossings_forced_open` so the rule is measured alone;
  `-- --control`).
- **The 踏切 warning unit is a breakable pole** (user: hit away like a street pole, arcade): `furniture.json`
  `crossing_signal.breakable` (150 kg, 4 m/s, 60 s), so it bakes into `BreakableProps` like a lamp. The AI does not
  read the unit (cars stop from the timetable), so nothing in its logic changes; the flashing lamps of a unit that is
  down go dark (`TrainSystem.unitDown`, through `TrafficSignals.findPole`).
- **The far traffic tier** (`world.FarTraffic`, a child of ZoneManager; `ZoneManager.farTraffic` the control): up to
  `budget` 60 script-free cars on the registered lanes from the simulation ring (`trafficSimRadius` + 20 m) out to
  `farRadius` 700 m round the camera. Each is a lane, a position, a speed and a model; it follows the lane's
  successors (`pickNextRoute`, else `LaneGraph.successorsOf` straight-biased, as the AI), holds at a red
  (`TrafficSignals.stopDistance`) and behind the car ahead on its lane, and is drawn as one MultiMesh per model (the
  model's `.glb` parts merged per material at first use; -Z forward, ground at y 0). Born only out of the camera's
  view nearer than 450 m; a car entering the simulation ring or leaving the outer one is dropped. Local per peer, never
  replicated. No headlights yet. Gate `tools/godot/probe_far_traffic.gd [-- --world=island] [-- --control]`.
- **The Deck proxy perf gate** (`tools/perf_gate.sh`, NEEDS A DISPLAY): `probe_walk_perf.gd --deck` runs at
  1280x800 and scores each frame `deck_ms = max(cpu_ms x cpu_factor, gpu_ms x gpu_factor)`
  (`tools/godot/perf_budget.json`: 2.2 and 12, ESTIMATES until a real Deck calibrates them), judging each leg's p95
  against `frame_deck_ms_p95` (33.3: 30 fps) and draws / characters against `counts_p95`; the wrapper re-runs with
  `--no-peds` / `--no-traffic` / `--no-buildings` and judges each system's cost (shipped p50 - control p50) against
  `systems_deck_ms_p50`. `--quick` = the shipped run only.
- **The 踏切 layout rules are measured** (`island_layout.level_crossings`, LX_*; reported, `LX_ASSERT` after step (c)):
  >= 30 m (arterial) / 20 m (street) from a junction mouth, >= 60 deg (never < 45), two crossings on one road < 12 m
  apart (combined) or >= 30 m. PLAN.md "STEP (c) PREPARED" has the 7 of 18 that break one.

## Expressway guide signs, and every displayed name is fictional (2026-09-30)

- **Names shown to a player are FICTIONAL, for legal reasons (user decision).** The expressway brand is 海都高速
  "Kaito Expwy" (環状線 Loop, 潮風線 Shiokaze, 空港連絡線 Airport Link), never 首都高 / Shuto or a real route name;
  famous real Tokyo road names (山手通り, 明治通り, 昭和通り, 春日通り, 白山通り, 公園通り, 湾岸通り, 臨海通り, 海岸通り, Tokyo's
  中央通り) were renamed in `tools/island_street_names.py`; the map says "Seagate Bridge" and "Hilltop Castle"
  (`island_buildings.SITE_PLACES`). Generic Japanese street words (駅前通り, 本町通り, 桜通り) stay. Internal ids
  (`shuto_*`, `RainbowBridge`, `ShuriCastle`) are never shown and are left alone. New names go through the same table.
- **Green signs, Japanese convention** (PLAN.md item 1g): white letters on green. `point_furniture.expressway_sign_sites`
  finds every ramp from the LANE GRAPH (`road_class` "ramp"): fed by an expressway lane it is an EXIT (出口 EXIT +
  the street it lands on) or a JCT ramp (JCT + the expressway it leads to), and an `expwy_sign` F-type cantilever
  stands `expwy_sign_before` (120 m) before the diverge at the LEFT edge, its panel over the lanes; fed by a street
  junction's connector it is an ENTRANCE, and an `expwy_entrance_sign` (入口 ENTRANCE + the route) stands roadside
  `expwy_entrance_in` up the ramp. A diamond's exit is not mistaken for its U-turn back up the entrance ramp: at a
  junction the connector into a street wins (`_destination`).
- **The panel is measured off the model** (`Table` reads the bounds of the piece's `MI_ExpwyGreen` faces), so an
  artist may move or resize it in `library.blend` (`Sign_ExpwyCantilever`, `Sign_ExpwyEntrance`, placeholders in
  `library_civic.py`) with nothing else to update. The TEXT is drawn at run time: `roadkit_cli gltf` writes
  `<network>.signs.json` (`expressway_sign_plan`, network-wide, beside `.signals.json`) and `world.TrafficSignals`
  builds each sign's labels within `signRadius` (350 m), in the sign font (`make_jp_font.py`, whose `chars` now include
  the sign words). Probe readouts: `expressway_signs_now`, `built_signs_now`, `sign_text_near`. Self-test in
  `point_furniture.py`; pictures with `tools/godot/shot_city.gd` (display).

## A vehicle entry is a dropped kerb (切り下げ), authored per station (2026-10-04, user-asked)

`PointData.entry_left` / `entry_right` (m, 0 = none): a car entry centred on that station, on that side; `entry_style`
(APPEND-ONLY enum): **DROP** (default), **DROP_ASPHALT**, **CUT**. `point_edges.drop_entries` lowers the kerb to
`ENTRY_KERB_H` 5 cm over the width with an `ENTRY_RAMP` 2 m slope (5 %) each end, inserting vertices at the breaks so
the entry is exactly as wide as authored. The footway SLOPES ACROSS (`EntryKerb`, a float carrying the height it was
lowered from): the 5 cm lip at the kerb line, the footway's own height at the property line, so the lot behind meets
it with its ordinary 6 cm step instead of a 16 cm one (セミフラット). DROP_ASPHALT paves that footway in the road's
surface (the kerb lip stays concrete, the drain's edge); CUT removes the kerb and footway (kept for COMPARISON: the
stamped ground under a road is 10 cm below the asphalt, so a cut leaves a pit). Street furniture keeps
`point_furniture.ENTRY_CLEAR` past the ramps; it reads the kerb itself, so every placer obeys it.
- **Placing one**: `roadkit_cli.py entry <record> <x> <y> [--width 5] [--style DROP]` (record frame), i.e.
  `point_record_ops.add_entry`: the nearest road's chain gets a station opposite the point (or reuses one within
  1 m), refused within `MIN_MOUTH_CLEAR` + half the width of a junction mouth or a road end. In the dock the three
  fields are on every point (the generated field table).
- **The comparison street**: `tools/roadkit_entry_test.py` writes `EntryTest.roads.json` (one lane each way, 3 m
  footways, the three styles plus an ordinary kerb); `build_roads_piece.sh ... Roads_EntryTest`;
  `tools/godot/probe_entry_test.gd` (profiles + SPC-1 and CRT-1 driven in; `-- --shot=<dir>` pictures).
- **The island's car parks are wired to it (2026-10-05, user: "the car park looks like a random plate ... do the
  connect").** `island_buildings.drive_entries` turns every car park into an entry -- a deep-pocket one at its
  driveway's kerb point (`drive`, DRIVEWAY_W 5 m), a street-front one on the middle of its front (`ENTRY_FRONT_W` 6 m),
  slid along the front 1 m at a time when the middle is at a junction -- tried on the road record with
  `add_entry` (only what the road takes is kept) and written into `IslandRoads.keepout.json` `entries` (Godot frame
  `[x, z, width]`). `roadkit_cli pieces|gltf --keep-out` applies them to the network IN MEMORY
  (`roadkit_cli._with_entries` -> `point_record_ops.apply_entries`, same calls, same order, so the same answers): the
  record stays the layout's output, and the next road build after a buildings `write` sees them (the keep-out rule).
  A driveway the road refuses meets the kerb as it is (no wedge since 2026-10-06). Measured: 170 car parks, 98 entries, 68 deep driveways keep
  the wedge (they meet the street at a junction or a road end), the rest street-front lots facing a junction pad.
  Three `add_entry` rules came with it: never on `ENTRY_SKIP` classes (expressway, ramp, rail: the first run put
  entries on the Wangan connector); never on a stretch steeper than `ENTRY_MAX_GRADE` 2 % (a station there bends the
  vertical curve: 0.34 m on a dike ramp); and the new station stands on the RESOLVED curve facing along it, its two
  neighbours frozen on the tangent the curve has at them (a station on the chord pulled a bend 5.2 m toward it;
  after, every affected road within 7 cm of where it was). A JOINT end (a zone split) is not a mouth.

## Asphalt from kerb to door; a paved site's edge slopes (2026-10-05, user-asked)

User: "the sidewalk, the block's ground, the parking lots and the building plates all asphalt so they blend; kerbs and
gutters stay concrete", and "use --\ slope on the side of parking spaces so there is no spike when cars drive on".
- **Materials, no rebuild needed for the look** (each is referenced by path), ALL the carriageway's own asphalt
  texture, tile and TONE (user: "the same tone as the road", as a Japanese street reads): the road kit's footway
  `M_ConcreteTile.tres` (name kept; also the raised median's fill), the private ground `M_LotConcrete.tres` (plinths,
  edge aprons), and the block fill's Terrain3D "Urban" layer repacked from it (`make_urban_texture.py --from-lot`, tint
  1 on the texture asset). The road's edge is marked by concrete instead: the kerb (`M_Concrete`) and the L-gutter.
  Car-park bays (`MI_AsphaltLot`) unchanged.
- **The L-gutter (L型側溝 / 街渠)**: `point_mesh.gutter_strips`, a `GUTTER_W` 0.4 m concrete strip (the kerb's material)
  in front of every road kerb, on the carriageway, `GUTTER_Z` 6 mm proud (under the paint's 1 cm, so a zebra or stop
  line over it wins), its own object `<road>__gutter_<side>` in NO collision proxy (no lip a wheel feels). Where the
  kerb is a road kerb (0.01..0.3 m): it continues under a dropped-kerb driveway, stops where a 踏切 levels the kerb,
  none on a rail road. Narrower than a 0.5 m shoulder, so the edge line is never on it. The drain grates
  (`furniture.json` `drain`, inset 0.35 m) sit in it, lifted 8 mm.
- **No slope bumps, and one asphalt everywhere a car drives** (2026-10-06, user: "the slope bump causes more
  trouble than good -- remove it everywhere"). The sloped `Apron_Edge` ring round paved sites (2026-10-05) and the
  gutter WEDGE on the carriageway at a refused driveway are both gone (`island_buildings.DRIVE_WEDGES` False puts the
  wedge back; `apron_edge` in a type row is ignored). Instead a PAVED site (`island_buildings.type_paved`: a composite
  with an apron, marked `paved_site` in its meta, or any kits/interiors building) stands `SITE_LIFT` 1 cm over the block
  ground with NO plinth; other buildings keep FLOOR_LIFT + plinth. The dropped-kerb entries (a sidewalk fix) stay.
  `MI_AsphaltLot` (car-park bays, every compound yard) is now M_LotConcrete's values (asphalt x0.9 over the concrete
  ORM + normal; `palette.json` `orm_path` / `normal_path`), and every kits/interiors yard (`interior_plans.apron`
  default), the container yard, the fish market, the motor pool and the civic placeholders' grounds wear it.

## The expressway as of 2026-10-01: a complete Wangan, a lane-split T at the spur, all four movements at both JCTs

`tools/island_expressway.py` (numbers in `tools/island_plan.py`; PLAN.md item 1 is the running record):
- **`shuto_wangan` is the MAINLINE**: one divided road from the west-coast T along the whole south coast (over Harbour
  station at 18 m: there is 16 m between the container terminal's stacks/cranes and the station), up the waterfront
  to a joint by the airport spur (`WG_MAIN`). Its profile is FIXED (12 m, 18 m at the east end): `deck_profile` reads
  the coastal dike's crest as ground and put the whole coast at 17 m.
- **At the spur the Wangan ENDS IN A LANE SPLIT (分岐 / 合流, `t_split`, 2026-10-01)**: at J0 (`WG_J0`, on the
  straight waterfront diagonal) each carriageway splits lane by lane into four ONE-lane ramps, NW -> SE T3 (EB -> spur
  NB) | T1 (EB -> spur SB, the airport) | T4 (spur SB -> WB) | T2 (spur NB -> WB): no forced merge anywhere, every
  movement exists. Rules it cost, each a measured defect first:
  * **Separate sideways before vertically.** Two ramps beside each other at different heights read as a step (the
    gate's 4 m / 1 m crossing rule): the WB pair (T4 + T2) peels off south-east at J0 at ONE height while the EB pair
    (T1 + T3) stays level `T_HOLD` m and climbs together; only then does T4 turn north-east UNDER T1, nearly square.
  * **A shallow crossing over a road you must then merge into does not fit**: a single round curve over the spur stayed
    ~120 m over it and could not come down before the bridge (measured; the user chose square crossings).
  * `point_export.wire_joints` takes each lane's NEAREST head over all roads on one joint (per link, the last road
    asked won and a lane went nowhere).
  * A ramp's crossing heights are the MEASURED overlap span (`_overlap_spans`) as minimum-height cones (`_heights`),
    never fixed +-15 m windows or a knot list (a knot list stepped 2.2 m in 7 m between two windows).
- **`shuto_wangan_c1`, the connector to C1 west, is a BRANCH**: its south joint parts into Y1 (Wangan EB ->) and Y2
  (-> Wangan WB, a flyover); Y4 (-> Wangan EB) and Y3 (Wangan WB -> it: off the mainline ON LAND at x 220, west of
  the bay, one R ~222 m right turn over the mainline, Y4 and the connector, each crossing at that road's height +
  6.3 m) complete it. Y3 crosses the Wangan at a SHALLOW angle, so it keeps beside it for `Y3_CLIMB` m first (it was
  over the Wangan's deck 80 m after its gore with +-15 m windows hiding it: 4.9 m on the built mesh).
- **The Suburb exit** (`shuto_sb_off`): Wangan EB -> the ground, an S of two R 353 m arcs beside the mainline, level
  over ring_kita (the dike road) then 7 % (the 40 km/h ramp limit) into the teibo_sokudo_2 / kogai_michi junction by
  Suburb station as its 4th arm, ONE lane. The mainline has joints at WG_CUT_X / WG_CUT3_X / WG_CUT2_X so each EB/WB
  run carries one ramp per carriageway.
- **A city entrance merges as ONE lane** (`ENTRY_LANES`: the diamond entrances, Y3, Y4); an exit, and a JCT ramp that IS
  a carriageway at a joint (W1/W2/E1/E2/Y1/Y2), stays two lanes. Ramp arcs are drawn at a 4 m step
  (`rounded_polygon(arc_step=)`): the 30 m default kinked every ramp curve.
- **C1 meets the connector only on its west side (W1, W2) and the spur only on its east side (E1, E2)** -- one access
  per side, by decision; corner turn-backs were built and removed. E1 comes straight onto the spur's line (no curve back
  in); the spur's joint is at y -45.
- The west end runs UP THE WEST COAST (user, 2026-10-02): the T is on the west coast road's north-south stretch, and
  the mainline runs down the land strip outside the dike through `island_plan.WG_WEST_PATH`'s corners (R ~34 at the T,
  posted 40), then along the bay's north shore. That keeps the bay and the military pier's approach clear (210 m off
  the pier, 184 m of deck over water against the old hook's 617 m). The airport end (peel R ~45, U-turn R ~38 into the
  forecourt) is kept.
- Ramps are straights and constant arcs with the LARGEST radius that fits: `two_arc` (exactly two equal arcs and a
  straight, solved; T3, Y3, Suburb exit), `designed_ramp` (a gentle diverge + two arcs, searched; W1, W2, E1, E2 --
  each starts its curve AT the gore via `on_curve`, so branch_ramp's offset station no longer makes a kink),
  `best_corner` (Y1, Y2). Ground exits may be tighter. Both diamonds land on naka_hondori: eki_minami_dori's stretch
  under C1 (y 126 -> -230) was removed from the arterials input.
- The diamonds are TIGHT: junctions 37 m off C1 (`DIAMOND_J`, `S_DIAMOND_*_Y`), their ramps 40 m longer than the first
  build (`DIAMOND_X` 295/305/895/905) and climbing from where their band parts from C1's (`DIAMOND_PART`): 5.8 %. And `island_plan.diamond_strips()` keeps
  generated buildings out of the ground between each ramp and the viaduct.
- The Suburb exit plans its dike crossing by the dike step's own reach rule at 6.3 m (`SB_CLEAR`), and
  `island_dike.PLANNED_OVER` (6.0, a tolerance) lets that stand, with any lift coned at its own 7 % (`PLANNED_GRADE`):
  at the general 4 % a 0.3 m top-up was carried down the whole descent and left the exit 5 m over its junction; the side road by Suburb station sits 25 m further inland
  (`island_dike.SIDE_EXTRA`) so the exit lands at 6.9 %. PLAN.md item 1 "THIRD ROUND" has the open review items.
- Rules this cost: a taper that closes AT a joint cannot hand its lane over (flow `broken`) -- give it a station
  short of the joint; a ramp crossing a road while still climbing measures short after the grade
  smoothing -- reach the height before the crossing; one divided road splitting into two ramps at a joint is welded
  twice, so keep the grade break there small (`WG_EAST_Z`).
- **Lane balance (review P1, 2026-10-02):** a C1 entrance followed by an exit is ONE added lane carried across the
  corner joint between them (`AUX_CARRY`, `lane_balance`); a JCT entrance's added lane runs on across its joint into
  the next ramp and drops there (T3 -> E2, the connector entrance -> W1), never inside that ramp's gore-hold zone
  (`_carry_room`: `island_grades.level_gores` would insert a station into the one-span taper).
- **C1 and the Wangan mainline sweep their DESIGN arcs:** C1's arcs at 10 m (`C1_ARC_STEP`), ramp clearances one-sided
  where a lane is carried through (`island_roadgen.station_at(clear=)`), every station frozen on its design tangent
  (`plan_face`; `thin` may still drop them). With chord facings C1's R180 corners swept ~5.5 m inside (R 118-122). The
  kit keeps a flat-stored interior MANUAL facing on the chain's own climb (`point_profile.stations`).
- **Posted speed = design radius** (`post_speeds`, `SPEED_BY_RADIUS` 170/90/60/30 m -> 80/60/50/40): a tight corner
  gets its own road at a joint so only it slows (`wangan__1`, `spur__3`).
- **Ground ramps** (`ground_ramp`): gore along the mainline's axis, two equal arcs to a new T on an arterial (`cut_road`,
  `_t_arm`), level until the band parts (`part_distance`), one straight grade <= `GROUND_GRADE` 6 %. Built: the
  connector's half IC (SB exit -> wangan_dori, NB entrance <- rinkai_dori; chuo_dori itself has a junction every
  25-60 m), the Suburb WB entrance (<- ring_kita east of the crossing), the port WB exit (-> the port loop's west leg).
  `ground_ramp(path=)` takes an explicit plan polyline where two arcs cannot separate the ramp from the mainline.
- **The port's EB entrance (review R1, 2026-10-02)**: from a T on ring_kita at `PORT_ON_T`, it runs west of the port
  and merges at `PORT_ON_X`. The ramp diverges, runs 22 m off the mainline, then turns in one arc (explicit path, 2.1 %).
  Its lane is carried into Y1, so port -> C1 and port -> airport both exist. The new joint `WG_CUT5_X` makes
  `shuto_wangan__1b` (Y1 + Y2) separate from `shuto_wangan__1` (the entrance), and Y2's added WB lanes are carried
  75 m across it before their taper. The WB port exit stays: it is the only way into the port from the east. An EB
  port exit does not fit (the dike road and Y3/Y4 fill the strip), and R2 was measured impossible (PLAN.md
  "REVIEW OUTCOME"). R3: the connector's SB exit gore is 125 m past the W joint (`CONN_EXIT_Y` -150). R5: the
  Suburb exit lands at 6 % (`island_dike.SIDE_EXTRA` 60).
- **Five rules the 2026-10-02 rebuild's gates taught** (`probe_road_clear` / `probe_road_stamp` / civic `--check`):
  * `island_grades.level_gores` counts a ramp as parted from its mainline when it is `GORE_VERTICAL` (2 m) above or
    below it, not only sideways: T1 runs beside the spur and then flies over it, and holding it at the spur's height
    flattened it into a flat crossing (27.9 -> 21.2 m).
  * `island_grades.pair_held`: two expressway roads side by side at one height (a lane-split pair, T2 + T4) keep
    their stations through the smoothing; a ramp and its own mainline at a gore are excluded (that pinned the
    Wangan's crest at Y3's gore and left Y3 0.3 m under its paving). `island_dike.PLANNED_GRADE["shuto_t2"]` 6 %
    keeps a dike-clearance lift from reaching back into the pair.
  * An expressway guide sign's post stands outside the LEFTMOST lane at its cross-section
    (`point_furniture._leftmost_edge`): a carried aux lane runs left of the lane walked back along.
  * A civic plot's road check covers junction PADS (each pair of a clique's mouths is a segment): a koban stood
    across a crossing.
  * `road_kit_stamp.height_at`: where an ELEVATED road (UNDERPASS over both the lower road and the natural ground)
    passes over a road whose verge reaches the vertex, the lower road decides the ground (the Wangan's deck left the
    dike road's fill 0.84 m short).
- **Lane-designation gantries** before a lane split (`point_furniture.lane_gantry_sites`, sign kind "lanes", one column
  + ↓ per lane, `TrafficSignals`).
- **Kit fix:** a REV lane's taper receiver is `opens_from` in chain order (`point_export.build_run`).
- Iterate with `island_expressway.py <out> --from <base> --fast` (1 s; the base = `island_layout`'s first four
  steps) and the gate subset in-process; the full gate is `island_layout.py` (~20 min, flow 570 s).
- **Every ramp is designed at 40 km/h and every grade break on it is a vertical curve (NEXT PASS step 1,
  2026-10-02).** The rule: <= 7 % to or from the ground (道路構造令 at 40 km/h), <= 6 % between expressways, every
  break K >= 6 m/% -- measured on the EXPORTED lanes (`island_grades.py ramps <record> <lanekit>...`, asserted by
  `island_layout.py`). On the shipped lanekits it found 14 of 26 ramps failing: E2/W2 climbed out of their gores at K
  1.5, T1 reached 7.2 %. Causes and fixes:
  * `island_grades.ramp_curves` (in `smooth`, after `level_gores`): each ramp's resolved centreline is sampled every
    2 m and its profile solved as a SMOOTHING SPLINE -- held spans (gore, mouth, deck, 踏切) fixed, the curvature weight
    raised until K reaches `RAMP_K_SOLVE` 9 (JCT) / `RAMP_K_GROUND` 6.5 (ground; the grade is its tighter budget),
    each END continuing what it joins (a joint the joined road's grade, a junction mouth level). The corridor average
    could never round a break AT an anchor, which is where every gore exit is. Then stations are inserted every
    `RAMP_STATION` 6 m inside curves and every station's TANGENT carries the solved slope: with chord (AUTO) tangents
    the Hermite bent its own way between stations (a solved K 8 read K 5.4 on the lanekit). A held station on a held
    span takes that span's chord slope first, or the Hermite bends up inside the gore (T4). Every ramp station is then
    held for the corridor average.
  * **The dike's clearance is a FLOOR in that solve** (`island_dike.crossing_needs(net, every=True)`, a one-sided
    penalty that only pushes up -- a two-sided spring pulled T2 down into a 22 % step), so the final `island_dike.py
    raise` has nothing left to cone-lift on a ramp (a cone lift is a kink). Ramps clear the ring at `RAMP_OVER` 6.3 m
    (solved against the pass's own 5 m samples), not the 7.5 m margin for decks that never see the embankment: at 7.5
    Y1 and E1 had to climb 1.3 m in the 28 m between their gore and the ring. The Suburb exit plans 5.8 m
    (`SB_CLEAR`, `PLANNED_OVER`): 12.2 m to lose in 213 m with a curve at each end was 7.1 % at 6.3.
  * **...and so is every road the ramp flies over, and a CEILING every road it passes under**: the solve lowers a crest
    and lifts a sag, and without them E2 / W2 came out 4.1 / 4.3 m over C1. A crossing is a sample whose paved band
    OVERLAPS another road's (`CROSS_OVERLAP`) more than `CROSS_DZ` 3 m above or below; the bound is the profile's own
    separation clamped to 5.7..5.9 m. Roads joined at the ramp's ends and the other halves of its split are skipped
    (a one-way band is laid to one side of its stations, so a symmetric half width reads siblings as stacked).
    Tightest crossing on the island after it: 6.15 m (was 5.9).
  * `level_gores` no longer inserts the parting station within `GORE_MIN_SPAN` 6 m of the next station (a 4.5 m span
    no curve fits); T1's base line starts at the end of its level hold (`_heights(hold=)`; it stepped 0.55 m there);
    `T1_LOOP_Y` -570 -> -545 (its descent into the airport merge had ~70 m for 6 m); `T4_TURN_Y` -300 -> -330 (its 5 %
    climb to fly over the spur started at its own diverge).
  * Ramps' `design_speed` is 40 (`RAMP_DESIGN_SPEED`, was the mainline's less 20).
  * Quick loop: the real derive is `island_layout.derive(out)` (~70 s; the step cache replays unchanged steps), then
    `point_export.write` (20 s) and `island_grades.py ramps`; the generator alone on the base cannot judge the diamonds
    (their junctions are cut and set back later).

## 横断歩道橋: footbridges over the widest junction arms, measured in Blender, placed from the lane records (2026-10-10, user-asked)

User: "Japan seems to also equip air bridges on some intersections ... implement on some of the bigger street
intersections (ones with more than 2 lanes) as a way for peds to pass / show more tightness."

**The piece** is `kits/interiors/Footbridge30.blend` (a 3+3 trunk, 30.5 m kerb to kerb) and `Footbridge23.blend` (a
2+2 arterial with a median, 22.5-23 m), laid out by `blender/tools/street_plans.py` from the 立体横断施設技術基準:
4.7 m clear under the girder (the road's 4.5 m 建築限界 + 0.2), a 2.0 m walkway 5.5 m up between two 0.8 m plate
girders, stairs at 50 % (riser 0.15, tread 0.30, 1.6 m wide, a 1.5 m landing at half height), a 1.1 m railing with a
solid lower panel, one pier behind each kerb and one in the median, yellow nosings, one paint (`MI_BridgePaint`).
Built like every interiors piece (one `.blend`, the artist's after the first build; a `custom` row in
`building_types.json`; trimesh collision; `HULL_stair_*` ramps on the stair_ramp layer). 5.4-5.6k vertices, 4
surfaces. **The widths are MEASURED, not the preset table's**: every 3+3 arm is 15.25 m centreline to kerb, but the
2+2 arms are 9.75 (40 arms, no median), 11.25 (73) or 11.5 (26) -- a first piece drawn for "19.5 m" fitted none of
the junctions that wanted it, so the second piece is drawn for 11.35 and the generator refuses an arm more than
0.3 m off its piece.

**The placement** is `tools/island_footbridges.py` -> `assets/world_source/buildings/IslandFootbridges.json` (FROZEN,
hand-editable) -> a generated `IslandFootbridges` block of zones in `World.tscn` (one streamed zone a bridge, load
380 m, the site pattern without a reserve, so the building stages ignore it). `--resite` searches: every signalised
4-arm crossing of two 3+3 roads plus the `EXTRA` ids; on each, the widest arms first, at most `MAX_SPANS` 2, an
opposite pair when there is one; the deck is set back from the pad edge 1 m at a time until the piers and stairs
stand clear (0.7 m) of every furniture point the road pieces placed (the `mmesh_*` nodes of the baked glTF; a lamp,
tree or signal also keeps off the deck's plan), the lanes are straight and level under it, and no other lane passes
3-9.5 m overhead (a rail viaduct at +6..8 m refuses the arm; the C1 deck at +11 m clears). Today: 19 bridges on 10
junctions, all at a 9 m setback but two at 18 m; 6 arms refused (4 under the rail, 1 a lamp, 2 arms 10 m long).
`--list` prints every arm and why; `--check` (in `island_world.sh`'s sites stage) fails on a stale scene block AND on
a frozen bridge that no longer fits today's records.

**Checked:** `probe_stairs.gd -- --scenes=Footbridge30,Footbridge23` 8/8 flights (the first build failed 4: the lower
ramp began exactly at the 0.15 m footway height, a 0.15 m wall wherever the paving is lower -- it now starts one
tread below); pictures from the junction centre, a driver's approach and the stair foot (the crowd passes on the
building half of the footway).

**Not done:** the crowd does not USE a bridge (pedestrians do not cross streets at all yet: `MARK_footbridge_foot`
marks where a walker would step on); no name plate text (`MARK_name_plate`); the stairs are not joined round a
corner into the ring a real big crossing has (each span is its own bridge); no lift / slope; the navmesh under a
streamed bridge is the road piece's own (an AI on foot does not path over the deck); cost at a junction with two in
view is 8 draws -- not measured with `perf_gate.sh`.

## 電柱 + wires, lamps up the mountain road, white ガードレール (PLAN.md T1 + part of T3, 2026-10-11, user-asked)

User: "for the wire and pole asset, use japanese measure, more pole / electric pole placed in blender and exported";
then "for the streets on mountains add gutter and kerb + street lights all the way + destructible ガードレール, white
guardrails along some mountain roads ... also on larger city roads + coastline roads (exclude the intersection where
folks need to walk) (instead of wall when not in tunnel)".

**The pieces are modelled in Blender, in `kits/library/library.blend`** (`blender/tools/library_civic.py`, category
`street`; `build_library.py -- --procedural --only=<names>` then `export_building_kit.py -- --accept-bounds`):

- `Pole_Denchu`, `Pole_DenchuTr` (+ 柱上変圧器), `Pole_DenchuLamp` (+ 防犯灯 at 5 m), `Pole_DenchuTrLamp`: the
  Japanese distribution pole to its real numbers -- a 14 m concrete pole, 根入れ 1/6 (2.33 m, modelled BELOW z 0 so a
  pole on a falling verge still reaches the ground; `lift` -2.33 in the table cancels `put`'s stand-on-lowest-point),
  11.67 m standing, 末口 19 cm, taper 1/75; a one-sided 腕金 for the 6.6 kV lines reaching toward the ROAD (the
  piece's +X), an 架空地線 on a cap bracket, the low-voltage rack ~2 m down, the communication cable at 6.1 m with a
  splice closure, 足場ボルト from 2.7 m, three yellow 反射 bands. Three materials (four with the lamp): a MultiMesh
  draws once per surface. `library_procedural.Builder.cyl` (a tapered, smooth-sided round bar) is new for them.
- `Guardrail_JP`: one 4 m module of the standard W-beam guardrail (beam centre 0.6 m, 350 mm deep, a φ114 post in
  the middle, 0.5 m of post in the ground), white, one material.

**`furniture.json` owns where a wire meets a pole** (`rules.denchu_wires`: kind, x toward the road, z, sag at a 30 m
span, drawn thickness). The pole model reads the table to put its insulators there and `point_furniture.wire_span`
strings the wires from it, so the two cannot disagree; moving a wire is one edit and a library rebuild.

**Placement** (`point_furniture`, the notes in `furniture.json` are the rule text):

- `denchu_kind(road)`: by LANE COUNT, never class -- at most `denchu_max_lanes` (2) each way; not an expressway, a
  ramp or a no-pedestrian road. "lamp" (at most 1 lane each way AND a footway: a block street) = `_Lamp` poles every
  30 m CENTRED in each kerb run, and NO separate `lamp` on that street; "plain" (wider, or no footway: a 2+2 arterial,
  the mountain road) keeps its lamps and trees, and its poles stand on the lamp pitch a quarter of it off, which is
  midway between a lamp and a tree on either kerb (self-tested against both lattices). BOTH kerbs in town
  (`denchu_both_sides`, the user's call the same day: "thought it should be both sides"; the second line is staggered
  half a pitch), ONE kerb -- a hash of the road's name -- on `denchu_one_side_roads` (the mountain road). The coast
  road (`barrier_style` RAIL, no kerb) carries them too, 1 m out behind its guardrail, and is lit like a kerbed road
  (`_lamps` no longer asks for a kerb there). A blocked spot (vehicle entry, lane, car-park keep-out, another solid) slides +-3 / +-6 m first.
  Runs after the lamps and before the trees. Every third pole carries the transformer.
- **Wires** are swept INTO the road piece (`FURN__wires`, material `M_Wire` in `road_kit/materials`, no collision):
  seven three-sided tubes per span (1 ground wire, 3 high voltage, 2 low voltage, 1 communication), a parabola whose
  sag grows with the square of the span, between consecutive poles of one road up to `denchu_max_span` (62 m), over
  a junction or a vehicle entry included. A span to a pole in ANOTHER piece is not strung (each piece builds from
  what it owns), so a zone boundary that falls between two poles leaves one gap.
- `guardrail_kind(road)`: "kerb" -- both kerbs of a road with >= 2 lanes each way and a footway, 0.25 m behind the
  kerb line, never within `guardrail_end_clear` (9 m) of a run's end (the crossing), a vehicle entry, a keep-out, a
  level crossing; "edge" -- a road whose new field **`barrier_style` = RAIL** (the `coast` preset, `kaigan_dori`):
  `point_solve` no longer stands the no-pedestrian wall where the road is on the ground and outside a rock shed
  (a deck, a pier, a shed keep wall AND car wall), and the rail goes wherever no wall is; "drop" -- the roads
  `guardrail_drop_roads` names (`shrine_touge*`): EVERY edge except where the hill stands beside it (the ground 4 m
  outboard is >= 1 m ABOVE the road -- the inner side; first built as "valley side only", widened the same day on the
  user's "all the way, at least the non-inner side"). A module is turned to its edge and PITCHED to its grade (`placement["pitch"]` ->
  `point_gltf.marker_node`), because a level 4 m module on a 10 % grade steps 0.4 m at every joint.
- **A rail is not a "solid" to the spacing rules** (asset key `rail` [half thickness, height, half length]): a tree,
  a lamp and a pole stand behind it. It is breakable like a pole: `BreakableProps.poleHalfLength` + `pitches` (the
  baker reads `break_pole_len` and the marker's pitch), a long box per module, and the car's sweep asks five discs
  along the beam. mass 60 kg, break speed 6 m/s; 電柱 700 kg, 6 m/s.
- **Lamps up the mountain road**: `shrine_touge*` left `lamp`'s `exclude_roads` (and the poles'), so the pass is lit
  kerb to kerb at the ordinary 36 m pitch. Its kerb and L-gutter were already there (the road inherits a 0.15 m
  kerb both sides; 912 gutter drains above 40 m) -- nothing was changed for them.
- **The 防犯灯 is a real lamp to the game**: `world.StreetLights` `LAMP_ASSETS` / `HEAD_OFFSETS` gained the two `_Lamp`
  pieces (bulb (0.91, 4.95, 0)), so they get pools and the nearest get lights, and a knocked-down pole is dark.

**Measured on the island (the mesh build, 41 pieces), first rule set (one kerb, valley-side rails):** 1 124 poles
(478 lit) + 952 wire spans, 8 461 rail modules (33.8 km; 532 more refused for standing in a lane), lamps
1 144 -> 1 587, trees unchanged (889), triangles 2.07 M -> 2.11 M. The numbers after the same-day widening (both
kerbs, the coast road, every non-hill mountain edge) are in PLAN.md's s8 note.

**横断歩道橋 yield nothing; the rail yields to them.** A kerb-long rail stood in a pier or a stair of 18 of the 19
frozen bridges. `island_footbridges.py` now writes `IslandFootbridges.keepout.json` (each pier / stair rectangle
grown by its furniture clearance and half a rail module) and `roadkit_cli --keep-out` takes a comma list, so
nothing that stands up is placed there and only the pieces with a bridge rebuild.

**No zebra on a link shorter than `crosswalk_min_lane` (20 m).** User, with a map picture of wangan_dori at
(15, 420): "duplicate ... two traffic lights". Measured: a T (machi_sw_15) 72 m from the off-ramp's terminal on a
six-lane road left a 10 m link between the two pads carrying TWO zebras back to back and four pedestrian heads
within 4 m. Such a pair is one junction to a walker: the facing arms get no zebra and no pedestrian signal.
The two vehicle heads there are one per direction (each junction's far-side head) and stay.

**The stub `cho_sw_345__2` is gone, by hand, in the record** (user, same picture: "not necessary and breaks the
expressway"): a 34 m block street T-ed into the off-ramp `shuto_c_sb_off` where the ramp is still 1.1-3.4 m up, so
its pad sloped and put a junction on a ramp 70 m before its terminal. The road and its two points are deleted, the
T at (15, -345) keeps three arms, and the ramp's two halves (`__x1`) are one road again. **The generator still makes
it** (`island_streets`: the stub comes from the site-cut path, not `_raised_ramp`; a rule there was tried and did
not remove it) **and a fresh `island_layout.py` no longer reproduces the committed record anyway** (measured the same
day: it also drops `koba_cho_719` and merges three koba roads) -- so the next layout run must be diffed road by
road before its record is accepted, and this stub removed again or the generator fixed first.

**Not done / to judge in play:** a knocked-down pole leaves its wires hanging (cosmetic, 60 s); no service drops to
buildings and no wires ACROSS a street; the rail's collider is built at run time, so the baked navmesh does not
know it -- an AI on foot pathing across a kerb between two crossings will rub against it (people cross at the
ends, which are open); the median hedge and the 横断防止柵 of T3 are not built (the guardrail took the kerb).

## Right-hand traffic is the keep-left lane graph run backwards (2026-10-12, user: "drive on the right")

The setting changed the same day (an island with Japanese influence, Traditional Chinese its language, US influence
on its roads), and the user chose "Drive on the right" when asked what "rightway as the lane" meant.

- **Nothing is redrawn.** Every cross-section, ramp, taper and interchange template of the kit is authored keep-left
  (`point_profile` lays forward lanes on +s). A lane graph run BACKWARDS is a legal lane graph of the same roads for
  traffic on the other side, so `point_export.reverse_traffic` (the last step of `export_network`) keeps each lane's
  geometry and id and reverses it: points and curve (in / out handles swapped), grade and banking negated, `next`
  rebuilt from the predecessors, a connector's turn L <-> R (the tight turn of a keep-left junction is a left turn;
  reversed it is a right turn and still the tight one), a junction arm's `in_lanes` / `out_lanes` swapped, edge kinds
  ramp <-> merge. Every off-ramp becomes an on-ramp and every on-ramp an exit, on the right. `inner_lane` /
  `outer_lane` are about the median and the kerb and stay.
- **The side is a fact about the NETWORK, in a sidecar**: `<stem>.network.json` `{"traffic_side": "right"}`, read by
  `point_model.load_network` into `NetworkData.traffic_side`. Not in `.roads.json`: the Godot dock and every
  round-trip tool rewrite the record from the fields they know and would drop it. `IslandRoads` is right; `DebugRoads`,
  the templates and the rail stay left, so the ~30 DebugWorld probes that name lanes keep their meaning. The piece
  digest is salted with the side only when it is not "left" (a keep-left digest is unchanged).
- **Measured on the island** (same record, both sides): 2 624 lanes, 3 201 edges, the same 5 discontinuities; turns
  L 392 / R 375 become L 375 / R 392; dead ends 15 <-> orphans 53 swap. Those 53 are lanes that only BEGIN at a
  junction mouth (a second lane opening after the pad, reached by a lane change): reversed they END there with no
  connector, a trap. Each gets what a lane drop gets (`_merge_into`): the lane beside it as its successor, kind
  `merge` (38 edges added; dead ends back to 15, the real dead-end streets).
- **Furniture follows the lanes by itself** -- arrows, stop lines, zebras, pedestrian heads, guide-sign SITES are all
  derived from arriving lanes. What was modelled for a left kerb is mirrored: `tools/mirror_piece.py` reflects
  `TrafficLight_JP` (+ its `lamps.json`: lenses and name plates) and `Sign_ExpwyCantilever` in X into `*_R` twins
  (assets `signal_r`, `expwy_sign_r`); `_signals` stands the pole on the kerb the arriving traffic keeps to (the old
  `signal_skipped_right_hand` refusal is now only for a table without the twin); guide signs and lane gantries stand
  `_kerbward`; a rail built `--avoid` a right-hand road network puts its 踏切 units at the road's right kerbs
  (`crossing_signals(..., road_right)`). A mirrored signal reads red-on-the-left, which is the US horizontal order.
- **Game code:** none assumed a side (grep: only comments) -- the traffic brain, RoadGraph, the GPS, dispatch and
  the signal plan all follow `next`.
- **Known consequences, not fixed:** lane and ramp IDS keep their keep-left spelling (`shuto_c_sb_off` is now an
  ENTRANCE; `<road>_F0` runs against the road's point order) -- names only, every consumer follows `next`;
  exit-then-entrance order on a carriageway is reversed (reversal turns each interchange's pair into entrance then
  exit: a weave, where keep-left had none); guide-sign destinations are re-derived but their wording was not
  re-read; the cars are right-hand drive; `RaceDirector` routes and any authored lane names in missions were not
  checked on the island.

**Fixed 2026-10-12 (s9), found by the owed 踏切 picture:** the 一時停止 stop line before a level crossing was still
painted for keep-left traffic -- on a right-hand island it lay on the DEPARTING half of each approach, past the track.
`point_mesh.crossing_stop_lines(..., right)` swaps the halves for a right-hand network (the self-test checks both
sides: the line before the track is on the arriving half); the seven road pieces that hold the island's 12 crossings
were rebuilt (their entries cleared from `IslandRoads.build.json`, `DIRTY_ONLY=1`). The units were already right: the
near-side unit stands on the right kerb. Not checked by a picture yet: the expressway cantilever at an EXIT on the
rebuilt pieces (unchanged code).

## 17 street corners rounded (2026-10-12, s9; user: "if kerbs under building means squash/reduce building, it is possible")

A generated block street turned a right angle through ONE record point with ~15 m legs: the solved centreline bent at
~5 m of radius, its inside lane at 2.9 m. A car cannot follow that; it swung into the oncoming lane (census trace:
opposing cars touching at `koba_waku_w__x2`, one into the building on the corner, a queue standing behind it).

- **`tools/island_fillet_corners.py [--write]`** reads the record through the kit's own curve
  (`point_profile.centreline_runs`), finds each place a street's centreline bends under 9 m, and REMOVES the corner
  point, joining its neighbours (then slides the neighbours back along their legs if that is not enough), measuring
  after each try. Ramps (`shuto*`), the mountain road and roundabouts (`*rotary*`) are skipped. 17 fixed, to
  11-29 m of centreline radius: c1_ura_higashi, c1_ura_nishi, eki_ginza_res_north (only to 5.9 m), ekimae_industry,
  ekimae_suburb, kanransha_michi, kichi_dori__2__x1__x1, kitahama_michi, koba_waku_w__x2, koba_waku_w__x2__x1,
  kogaihama_michi, nishi_ura__x1__x1, nishihama_michi, nodo_waku__x2__x2__x2 (+ neighbours slid x1.5),
  nodo_waku__x2__x2__x2__x2, yamasoi (two). **5 LEFT** -- the bend is at a road's end, beside a junction, where
  there is no plain interior point to remove: eki_ginza_res_north (961, 834), ichiba_michi (561, -702),
  kichi_dori__2__x1 (-499, -1231), nishi_dori__5__x1 (-87, 679), nishi_ura__x1 (-1059, -209) (record x, y).
- **Rebuilt:** `tools/island_roads_stage.sh` (35 min: 27 road + 15 rail pieces, gate 0 errors, lanes 2 624 as before,
  stamp, traffic zones, road map PASS, footbridges unchanged, sidewalks), then the buildings.
- **Buildings** (`tools/island_corner_buildings.py`): four stood inside the new road + footway. Three were slid back
  (a Mansion on yamasoi 5.5 m, an ApartRC3F and a DetachedHouseB 0.5 m), one had no clear place within 8 m and was
  REMOVED (the Apartment_W6 on the inside of the koba_waku_w__x2 corner). `island_buildings.py lots` + `write`
  (2 031 buildings), HLOD rebuilt. `island_downstream.sh --check` PASS; check_roads 44 PASS + the old sample FAIL;
  probe_gps_route --world=island PASS.
- **Measured at the old hot cell** (census, `residential`, 300 s, two runs each): cars standing within 60 m of the
  player 15.8 and 10.8 -> 3.4 and 3.7 (the queue at the corner is gone), contact lines 2 210 and 97 -> 59 and 73,
  scored crashes 6 and 11 -> 5 and 3. What still scores is at the T junction `cj1fe6ac18` 60 m on (connector
  against connector), not the bend.
- **LEFT, known:** (1) the block ground is baked into the terrain by the `ground` stage, which was NOT re-run: on
  the outside of each rounded corner the sliver the road left is at road level, 15 cm under the block beside it,
  until the next `island_world.sh --from terrain`; (2) two civic plots at the koba corners, `danchi` and
  `hospital_west`, now report "lost their frontage": their front stands ~2 m further from the road than the check
  allows (the road pulled in from the corner). Not re-sited; (3) `probe_road_clear` was not re-run (1 h).


## Furniture on both kerbs: measured; a street under a viaduct had lost one; the median hedge (2026-10-12, s10)

User: "check if poles / other should be on both sides of street".

**The rule was already both kerbs; the island was measured against it** (every placement of `point_furniture.place`
over the whole record, sided against its own road's centreline): lamps 860 left / 931 right, street trees 462 / 462,
guardrail modules 7 002 / 7 060, 電柱 1 134 / 838. One-sided roads, and why:

- `shrine_touge*` -- poles on one verge, 311 of them: `denchu_one_side_roads`, by design (a mountain line follows
  one verge). Lamps and rails there are on both.
- `kuko_rotary`, `ekimae_rotary` -- trees on the outer kerb only: a one-way ring, the inside is the island.
- **`chuo_dori` (six records of it) and `ring_kita__4` -- a DEFECT.** They run under the elevated expressway, and
  `_LaneIndex.clear_of` ("is this spot in a lane") was asked in PLAN only, so the viaduct's lanes 8-10 m overhead
  counted as lanes at street level: `chuo_dori__3` carried 6 rail modules on one kerb and 50 on the other, 1 lamp
  against 7, no tree against 6.

**Fix: the lane index is asked in three dimensions when the caller knows how tall its thing is.**
`clear_of(p, margin, height)`: a lane whose deck (`DECK_DEPTH` 1.6 m under its surface) clears the thing's top by
`HEADROOM` 0.3 m, or that runs more than a deck's depth BELOW the spot, is on another level and does not count.
`asset_height` reads the top off the piece's own bounds. Every caller with an asset passes it (`_out_of_lane`:
signals, lamps, poles; trees; planters; bollards; guardrails); the 踏切 unit's search still asks in plan. A 0.8 m
rail and an 8 m lamp fit under a 10 m deck; an 11.67 m 電柱 does not, so a street under a viaduct still carries no
overhead line -- which is right. Island, same record: guardrail modules 14 062 -> 14 547 (refused "in a lane" 486 ->
1), lamps 1 791 -> 1 847 (+15 median lamps), trees 924 -> 980, signals +9, pedestrian heads +17; `chuo_dori__3` is
balanced. Self-test: a lane 10 m up -- the plan-only question refuses the spot under it (the control), 0.8 m and
8.0 m pass, 8.2 m and 11.67 m do not; a spot on the deck is not in a lane below it.

**The median hedge (PLAN.md T3's other half).** `_median_hedge`: a clipped hedge down every RAISED median wide
enough -- boxes `median_hedge_unit` 5 m long with 1 m between, 0.8 m tall, up to 1.2 m wide and 0.4 m in from the
island's kerb, none within 12 m of a run's end (a turning driver sees over the median), none beside a median lamp,
none where a lane or a track crosses. Swept into the piece (`FURN__hedge`, `M_Hedge` in `road_kit/materials`, no collision: the island is
kerbed). 1 193 on the island. `median_hedge_unit` 0 = none (the self-test's control).

**Not done:** T3's 横断防止柵 between the trees stays replaced by the guardrail; a wire span is still not checked
against a deck it may pass under (the poles either side of an overpass, <= 62 m apart).

**Same day, found by the gates after the rebuild:** `check_street_trees` asked the lanes in plan too, so the 45
trees newly planted under the viaduct read as "in a lane"; it is level-aware now (a lane >= 4 m above a tree's foot
is a deck, one >= 1.6 m below is a street under the tree's own deck; `--plan-only` is the old question and fails 45)
and it gained a check of its own: a tree under a deck must end below it. That found 7 trees whose 9 m crowns stood
BESIDE a viaduct's edge and in its deck -- the placer asks the deck within the trunk's reach only. `clear_of(...,
spread)` (a tree's crown, `tree_crown_radius` 3.5 m by default) refuses a spot that close to a deck without room
for the top: 980 -> 970 trees, 65 under a deck, 0 reaching one. The check's `--control` (kerb gap inside the kerb,
lane guard off) still fails, on the new line (41 reaching a deck).

**The rebuild that carried it** (`tools/island_world.sh --from terrain`, twice): road gate 0 errors, 2 624 lanes as
before; the buildings RE-DERIVED on the rounded-corner alignment (2 031; the four hand moves of
`island_corner_buildings.py` are superseded, the block ground re-derived so the road-level sliver outside each
corner is gone); `danchi` and `hospital_west` re-sited by `island_civic_sites.py --resite` -- each slid 13.85 m
along its own road away from the corner, frontage check clean (only `super_sento_city`, the known plot under the
connector deck, still reports). `check_roads.sh` 44 PASS + the old sample street-tree FAIL; `island_downstream.sh
--check` PASS. The sample (`Roads_RoadKitZones`) was rebuilt for the hedge.
