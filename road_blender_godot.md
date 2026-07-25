# Working plan — Mesh-first road kit (Blender addon) → Godot Path3D

> **Progress tracker for a multi-session effort.** Mark items `[x]` as they land so a fresh
> session can resume exactly where this one stopped. Approved 2026-07-22. Companion docs:
> `assets/world_source/AUTHORING_GUIDE.md` (conventions of record), `PLAN_WORLD_AUTHORING.md`
> (its Phase A is superseded by this doc — see the note there).

## Context (why)

Roads today are generated procedurally: hand-drawn `road_*` centerline curves feed
`assets/world_source/lib/road_graph.py`, which abstracts them into a junction-node/edge graph
and *derives* per-lane offset routes + bezier turn connectors (`generate()`,
`road_graph.py:302-393`). This generator is **too limited** — it can't represent arbitrary
hand-modeled intersections, asymmetric curb placement, or non-uniform merges — and is not to be
extended further.

A modular mesh-based road kit was explored in
`assets/world_source/districts/District_manual_1.blend` (7 pieces on a 5 m grid: a plain lane
tile, a lane-tile-with-curb variant, a standalone curb/gutter strip, and 3-way/4-way intersection
pieces with simplified `.001` collision variants). That file is unwired reference material.

**Goal**: a Blender addon that builds roads/intersections **freely as mesh** — placing,
duplicating, rotating kit pieces, adding curbs to either side as needed — where each lane piece
carries a **hand-authored centerline curve** (not auto-derived from mesh topology). The addon
detects lane-to-lane connections across piece boundaries by endpoint proximity where
unambiguous, with a manual review UI for ambiguous cases (multi-lane intersections). This curve
+ connectivity data exports to a new sidecar and eventually drives native Godot `Path3D`/
`Curve3D` nodes for vehicle navigation and (later) GPS/A* — replacing `VehicleRoute`'s
`Marker3D`-list representation, which today hand-reimplements Catmull-Rom smoothing and
arc-length sampling that `Curve3D` already provides natively.

This starts as a new, parallel pipeline alongside `road_graph.py`/`assemble.lay_road_graph`/
`road_network.py` — but the user has said the existing Blender-side road code isn't working well
and it's fine to remove/replace it outright rather than maintain it forever in parallel. So: no
obligation to keep those generators running once the new pipeline covers their ground — only
constraint is that **already-baked Godot output** (`.tscn`/`.glb`/`.scn` for districts not yet
migrated) keeps working, since baked artifacts don't depend on the Blender scripts that produced
them existing. Placeholder district meshes get replaced one district at a time as the new
pipeline matures; old Blender-side generation code can be deleted once nothing still depends on
regenerating through it (track this per-file in this doc as districts migrate off it).

**Also flagged by the user (2026-07-22), broader world-authoring direction**: the PLATEAU
real-world extraction pipeline (`lib/plateau_import.py`, `lib/plateau_common.py`, `plateau/`
data + extraction scripts) is being deprioritized — going forward, districts/city content are
mostly hand-redrawn/rebuilt using existing PLATEAU output as an approximate reference rather than
regenerated through the extraction pipeline. This is consistent with (but a separate task from)
this doc's shift toward hand-authored, mesh-first content — noted here for context, not scoped
into the phases below.

**Long-term scope.** This is intended to eventually replace *all* street authoring — including
the backbone/arterial cell-grid tile system (`lib/road_network.py` + `kit/build_roads.py` →
`roads_kit.blend`, loaded via `kit_common.load_kits()`, used by `towns/build_world.py` /
`towns/districts/build_district.py`) — not just local district streets. That system is
grid-cell-constrained (an auto-tiler), which is a form of the same "too limited" complaint.
Phases 1-5 below scope the pilot to local/internal streets only and leave `road_network.py`
untouched, but the architecture (multiple authoring modes converging on one universal
lane-centerline-curve + connectivity pipeline, see "Authoring modes" below) is meant to
generalize to backbone/arterial roads later without a redesign — replacing `road_network.py`
is a future phase, not in this doc yet.

All paths relative to `assets/world_source/` unless prefixed `src/`.

## Authoring modes

A lane-bearing mesh can come from any of three methods — the pipeline from here on (centerline
curve authoring → connectivity → export) is identical regardless of which produced the mesh:

1. **Kit-piece placement** — instance a pre-built piece (lane tile, curb, intersection) from
   `kit/lane_kit.blend`; the piece's centerline curve(s) are authored once on the kit piece and
   travel with every instance (Phase 1-2).
2. **Hand-modeled mesh** — fully custom geometry for a one-off shape, placed in a district's
   `ROAD_MANUAL` collection; centerline curve(s) extracted the same way kit pieces are — tag a
   `lanedata` vertex group, run `RKA_OT_centerline_from_vertex_group` (Phase 2).
3. **Curve-driven GN sweep** — draw a curve first, generate the visual mesh from it via a
   geometry-nodes modifier (reusing `kit_common`'s existing GN sweep building blocks,
   e.g. the pattern in `make_road_profile_group`/`road_from_curve`, as a *tool*, not reviving
   `road_graph.py`'s graph-abstraction/generation step); the driving curve **is** the lane
   centerline directly, no separate authoring step. Useful for long freeform runs where hand-
   placing a centerline separately from the mesh would be redundant. Not scheduled into a
   numbered phase yet — add as a `RKA_OT_add_curve_swept_road`-style operator once Phase 2's
   plain centerline authoring is proven, since it shares the same curve-object convention.

All three converge on `lanecl_*`-prefixed curve objects, which is all `lib/lane_kit.py` and the
connectivity/export tooling (Phase 3) ever look at.

## Architecture

**Two authoring tiers** (mirrors the existing kit-library-vs-per-district-blend split already
used for walls/props in `kit_common.py`):

- **Tier 1 — kit library**: new `kit/lane_kit.blend`. One Blender **Collection per reusable
  piece** (lane tile, curb strip, intersection), each holding its mesh(es) + `-colonly` proxy +
  one or more hand-authored **centerline Curve objects** in local space. Intersection pieces
  carry all their internal per-lane/turn curves once, here. Promoted from
  `District_manual_1.blend`'s 7 pieces.
- **Tier 2 — assembly**: a district `.blend`, built with the new addon. Pieces are placed via
  `kit_common.link_collections` + `kit_common.instance_collection` (true library link — pulls
  mesh *and* paired curve(s) together, no metadata-pairing convention needed). One-off custom
  curved segments go in a `ROAD_MANUAL` collection using the same centerline-authoring operator
  as kit pieces. Both feed the same connectivity/validation/export pipeline, which only cares
  about world-space curve objects tagged as lane centerlines.

**Naming**: new centerline curves use prefix `lanecl_` (not `road_`) so the new collector never
cross-picks the old `road_*` collector's objects if both exist in one `.blend` during migration.
New sidecar: `districts/<piece>.lanekit.json` (parallel to, distinct from, `<piece>.roads.json`).
New scratch collection `ROAD_KIT_SRC` (if the addon needs one for in-progress editing) gets added
to `export_world.py`'s drop-list alongside the existing `ROADS_SRC`.

> **Naming collision avoided (2026-07-22):** there is a pre-existing, unrelated, actively-used
> `assets/world_source/kit/build_roads.py` → `roads_kit.blend` (a cell-grid tile kit driven by
> `lib/road_network.py`, loaded via `kit_common.load_kits()` for backbone/arterial visuals in
> `towns/build_world.py` / `towns/districts/build_district.py`). The new Tier-1 kit library in
> this doc is named `kit/lane_kit.blend` (not `road_kit.blend`) to stay unambiguous —
> matches the `lib/lane_kit.py` module name. `road_network.py`/`roads_kit.blend` is a separate
> backbone-arterial concern and is **out of scope** for this doc; do not touch it.

---

## Phase 1 — Kit library + placement addon skeleton

- [x] P1.1 Promote `District_manual_1.blend`'s pieces into `kit/lane_kit.blend`
      (`kit/build_lane_kit.py`, run via `blender --background --python kit/build_lane_kit.py`) —
      5 named Collections (`Kit_LaneStraight5`, `Kit_LaneCurbRightCityGutter5`,
      `Kit_CurbSideCityGutter`, `Kit_Intersection4Way2Lane`, `Kit_Intersection3Way1Lane`), each
      holding just its visual mesh. **No per-piece `-colonly` collision proxy** — collision is
      deferred to a later Godot-side/bake-time pass that merges whole assembled road segments
      into one collision object instead of one box per tile (see the collision strategy note
      below). Also: the `.001` variants are NOT LOD/collision meshes as their names implied — the
      4-way `.001` covers only one quadrant of the footprint, the 3-way `.001` is a
      differently-shaped/sized piece, not a reduction — kept as plain `_variant` objects in the
      same collection for hand review — **needs your eyes in Blender**: open `kit/lane_kit.blend`,
      decide per intersection whether to keep/merge/discard each `_variant` before Phase 2
      centerline authoring.
      Also fixed a truncated source name: `kit_side_ight_city_gutter_curb_w0.6m_l5m` →
      `kit_side_straight_city_gutter_curb_w0p6m_l5m`.
- [x] P1.2 New addon `addons/road_kit_authoring/` (real installable addon: `bl_info`,
      `register()`/`unregister()`, N-panel — not a batch script, since placement/snapping/review
      need live interactive operators): `__init__.py`, `paths.py` (symlink-safe path setup —
      resolves `__file__` through `os.path.realpath` since the addon is dev-installed as a
      symlink, see P1.4 — and locates `kit/lane_kit.blend` + `lib/` from there), `props.py`
      (`RKA_SceneSettings`: grid=5.0, connect_eps=1.0, active_kit_collection, place_direction;
      `RKA_CurveSettings` on `Curve.rka_curve`: lane_width, oneway, road_class, loop,
      end_behavior — registered now, consumed starting Phase 2), `panel.py` (N-panel "Road Kit"
      tab: Kit Library / Placement / Connectivity boxes).
- [x] P1.3 `ops_placement.py`: `RKA_OT_link_kit_library` (links every Collection out of
      `kit/lane_kit.blend` — not hardcoded by name, so new kit pieces need no addon change),
      `RKA_OT_place_piece` (modal, click-to-drop a linked instance of the active kit Collection,
      ray cast to the world Z=0 ground plane, snapped to the grid, via
      `kit_common.instance_collection`; Esc/right-click stops), `RKA_OT_duplicate_piece`
      (offsets selected instance(s) one grid step along their own local placement direction, so
      it stays correct after a 90° rotation), `RKA_OT_rotate_piece_90` (rotate selected
      instance(s) ±90° around world Z in place).
- [x] P1.4 `README.md`: dev-install instructions (symlink into Blender's user addons dir); added
      the pointer + supersession note in `AUTHORING_GUIDE.md` §7 (top of the section, not a
      rewrite).
- [ ] P1.5 Verify: in a scratch district `.blend`, place a run of straight tiles + a 4-way
      intersection via the addon on the 5 m grid with no gaps/overlaps; confirm editing a piece
      in `lane_kit.blend` and reloading the district reflects the edit (link round-trip).
      **Partially done, headless:** a smoke-test script
      (register → link kit library → instance a piece → duplicate → rotate → unregister) ran
      clean under `blender --background`, confirming `link_kit_library` found and linked every
      Collection in `kit/lane_kit.blend` (now 6, not 5 — an extra `Kit_Intersection3Way2Lane`
      exists in the kit file beyond P1.1's original 5; harmless, the operator doesn't hardcode
      names) and that duplicate/rotate mutate the right selected object. **Still needs your
      hands in Blender**: the modal click-to-place path needs a real 3D viewport (can't run
      headless), and the "no gaps/overlaps" visual check + the link-round-trip-after-editing-a-
      piece check are both eyes-on checks — install the addon per the README, place a short
      straight run + a 4-way intersection, and confirm both.

> **Collision strategy note (decided 2026-07-22):** kit pieces in `kit/lane_kit.blend` carry
> **no per-piece `-colonly` proxy** (confirmed: many tiny `StaticBody3D`/`CollisionShape3D` nodes
> down a long street cost more — per-node overhead — than a few large merged colliders for a
> contiguous run). Collision is deferred to a **one-time merge pass on the Godot/bake side**:
> once a run of placed pieces is finalized, generate one collision object per contiguous major
> road segment (not per tile). `kit_common.colonly_swept` already does this kind of consolidation
> for the old curve-swept ribbon system (one continuous collision mesh instead of
> segment-by-segment) — reuse that pattern. Where exactly this merge runs (a Blender-side export
> step vs. a Godot-side `WorldBaker` pass over the placed geometry) is still open — decide when
> Phase 3's export step or Phase 4's bake step is being built. Until then, placed districts using
> this kit have **no road collision** — fine for authoring/visual walk-throughs, not yet for a
> real drivable pilot (Phase 5).

## Kit geometry v2 — parametric ground-up spec (design, 2026-07-23)

Prompted by wanting the kit rebuilt from a clean, exact parametric spec instead of continuing to
refine ad-hoc hand-modeled geometry. This section is the spec + the design answers to "how do
multi-lane roads and intersections compose from the single-lane unit" and "how is direction
represented for a 2-way street" — **not yet built**, except the direction primitive (item 2),
which is a real bug-fix-shaped improvement made immediately. The rest needs your confirmation
before touching geometry, in particular the intersection strategy (item 4).

1. **Single-lane tile primitive (confirmed against the current hand-modeled geometry — already
   matches, nothing to change here).** `LANE_WIDTH = 5.0 m` on X, **centered** (`X ∈ [-2.5,
   +2.5]`, centerline at X=0) so a 90° rotation never shifts the footprint; `LANE_LENGTH = 5.0 m`
   on Y, **endpoint-pivoted** (`Y ∈ [0, 5]`, forward = +Y per `kit_common`'s existing "forward on
   +Y" convention) so chaining tiles along the travel direction is a plain `+5 m` translate with
   no gap/overlap math — this is exactly what `RKA_OT_duplicate_piece` (P1.3) already does.
   Verified: `kit_single_lane_w5m_l5m` bbox is X[-2.49,2.51] Y[0,5]; the curb-right piece's
   drivable surface is the same X[-2.49,2.51] span plus curb geometry tacked on past X=2.51.

2. **Direction is now explicit via vertex-group weight, not inferred from topology (shipped).**
   `kit_common.centerlines_from_vertex_group` orders each lane tail→head by **ascending vertex
   weight** when the two path endpoints' weights differ (tag 0.0 at the start, 1.0 at the end, in
   Blender's Vertex Weights panel); if both ends carry the vertex-group default (1.0, i.e.
   direction hasn't been authored), it falls back to the old topological-walk order — so this is
   fully backward compatible with what's already tagged in `lane_kit.blend`. Verified with a
   synthetic test (weight said "tail is the Y=5 end" while vertex index order said the opposite —
   weight won) and re-confirmed unchanged output on the real, live `lane_kit.blend` (read-only,
   not saved). **Why this matters for your 2-way-street question below:** a single lane-tile mesh
   can serve *either* direction of a 2-way street just by rotating its placed copy 180° around Z
   — weight travels with the vertex, so "head" stays correct after rotation, whereas a purely
   topological walk (arbitrary tie-break) would not reliably survive that rotation. No second
   mirrored mesh needed.

3. **Multi-lane = combine mesh, and the existing extractor already handles it for free (shipped:
   detection + seam marking; deferred: physical joining).** Per your sketch: place N single-lane
   tiles side by side (`X` offset by `LANE_WIDTH` each), and each seam between two tiles gets a
   marking based on whether the two lanes run the same or opposite direction. **Not** joined into
   one physical mesh yet — kept as separate placed instances during authoring (matches the P1
   Collision-strategy-note precedent of deferring merges to a later bake pass, not authoring
   time); each tile's `lanedata` stays its own connected component regardless, so
   `centerlines_from_vertex_group` already gives one curve per lane with no new code — proven
   against the 4-way intersection's 16 tagged verts splitting into 8 lanes, and re-verified here
   with synthetic same-direction and opposite-direction pairs.
   - `kit_common.lane_marking_strip(name, x_center, y0, y1, z, width, matkey, coll)` — thin flat
     box (reuses `box()`), `matkey` = `'line_w'` (white, same-direction) or `'line_y'` (yellow,
     opposite-direction) — both material keys already existed in `MATS` (reserved, unused until
     now).
   - `RKA_OT_combine_lanes` (`ops_combine.py`) — takes the selected placed lane instances, sorts
     left-to-right by X, and for each adjacent pair reads direction straight off each instance's
     own world rotation (no mesh evaluation needed): same direction → flush white strip at the
     seam midpoint; opposite direction → yellow strip, **plus a warning if the pair is sitting
     flush with no gap** (real median/barrier spacing is a placement decision left to you — the
     operator doesn't auto-relocate geometry, just tells you when a yellow-marked seam has no
     separation). New scene settings `lane_surface_z` (0.15, matches the hand-modeled pieces) and
     `lane_marking_width` (0.1). Verified headless (synthetic instances only, live file never
     opened for writing): same-direction flush → 1 white strip at the exact midpoint;
     opposite-direction flush → 1 yellow strip + the expected warning; opposite-direction with a
     0.5 m gap → 1 yellow strip at the correct offset midpoint, no warning.
   - **Gotcha this testing caught, now fixed:** the tile is endpoint-pivoted at local Y=0, so
     naively rotating a copy 180° *in place* for the reverse lane spins its footprint to the
     wrong road segment entirely (Y∈[0,5] becomes Y∈[-5,0] — zero overlap with its
     same-direction neighbour). `RKA_OT_duplicate_piece` now has a `reverse` option (a second
     panel button, "Duplicate (reverse)") that rotates 180° **and** pushes the placement one
     grid-step further along the source's original forward direction, so the reversed copy's
     footprint correctly lands back on the same segment. Verified end-to-end headless: place →
     duplicate-reverse → combine produces one correctly-positioned yellow seam, no manual
     Y-offset math required from you.
   - A future "merge by distance" cleanup pass to weld touching boundary edges into one
     watertight combined mesh (deferred per above) is safe: only truly-coincident verts merge,
     and lane centerlines sit at each tile's own mid-width, never coincident with a neighbor's.

4. **Intersections composed from lane pieces, not one hand-sculpted mesh — RESOLVED (2026-07-23),
   prototype shipped.** Neither of the two options originally listed here was taken. Prompted by a
   reference traffic-engineering diagram (curb-radius + turn-swept-path diagram, kerb radius
   R=3.5m real-world minimum), the answer is **closed-form 2D corner-fillet math**, computed
   fresh from nothing but a list of approach-arm angles — no hand-tagging, no `road_graph.py`
   dependency (not even as a utility function):
   - **`lib/intersection_kit.py`** (new, pure Python, no bpy — `python3 lib/intersection_kit.py`
     self-tests, same convention as `road_graph.py`/planned `lane_kit.py`). `Arm(name, angle_deg,
     lane_width, lanes)` describes one approach by its outward angle only. `corner_fillet(edge_a,
     edge_b, radius, segments)` is the core primitive: exact tangent-arc rounding of two rays
     meeting at a vertex (closed-form, not Blender's GN Fillet Curve node — kept as plain Python
     so it self-tests with numeric assertions and has zero Blender dependency). `build_curb_corners`
     walks the arms sorted by angle and fillets every angularly-consecutive pair **except a
     "through pair"** (`is_through_pair`, ~180° apart — e.g. a T-junction's main street): there the
     curb is already one continuous straight line, so it's skipped entirely rather than filleted —
     this is what makes a T-junction "3-way with a direct through movement" fall out for free,
     verified in `self_test()` by checking the skipped pair's two curb-edge lines really are
     collinear. `build_lane_movements` generates every ordered arm-pair × lane-index movement: a
     straight 2-point line for a through-pair, a filleted arc (same `corner_fillet` primitive) at
     **`radius = kerb_radius + (lane_index + 0.5) × lane_width`** for a turn — i.e. **larger than
     the curb radius**, so the AI's driving arc is always a wider, easier swing than the physical
     curb corner, not a tight hug of it. `preset_4way` / `preset_3way_t` / `preset_3way_y` cover
     the three requested junction shapes. Self-tested: exact-radius arc/tangent geometry, 4-way
     rotational symmetry (4 congruent corners), T-junction through-pair skip + collinearity,
     Y-junction's 3 corners (no through-street), 12 lane movements on a 4-way (4 through + 8 turns),
     and that raising `kerb_radius` measurably widens the generated turn arcs.
   - **Default radius is deliberately RELAXED, not the tight real-world minimum.** The reference
     diagram's R=3.5m is a real-world *minimum* (delivery-truck-feasible, tight). Game AI driving
     doesn't need to hug that minimum, so `RKA_OT_build_intersection.kerb_radius` defaults to
     **9.0 m** (exposed, freely tunable per intersection via the operator's F9 redo panel) — a
     wide, comfortable arc. Turn centerlines get an even larger effective radius on top of that
     (see above), so the driving path is always relaxed relative to the curb it's set back from.
   - **`kit_common.poly_curve`** (new) — plain POLY-spline curve through exact points, no NURBS
     smoothing/approximation (unlike `road_from_curve`/`barrier_from_curve`'s NURBS spines, which
     would drift off the hand-computed arc); this is the exact same object shape
     `RKA_OT_centerline_from_vertex_group` builds by hand (`lanecl_*`, `rka_curve` prop group) —
     the computed-geometry counterpart of that hand-tagged one. **`kit_common.flat_ribbon`** (new)
     — a flat quad-strip mesh through exact points (same tangent-offset technique as the existing
     `swept_wall`, just horizontal), the visual driving surface under each generated centerline so
     a turn reads as an actual road, not a bare line. The curb corners themselves reuse the
     existing `swept_wall` directly (already exact-point, already vertical) — no new mesh code
     needed there. **Per user instruction: no `-colonly` collision proxy is generated per piece
     here** — collision for the whole road network is built as one pass over the complete road
     segment at export time, not per authored piece (unlike the wall/building kit pieces, which do
     carry their own `-colonly`).
   - **`RKA_OT_build_intersection`** (new, `ops_intersection.py`) — one click builds a full
     intersection (all curb corners + a `lanecl_*` centerline + a visual asphalt ribbon per legal
     lane movement) into a fresh collection at the 3D cursor; `preset` = `4WAY` / `3WAY_T` /
     `3WAY_Y`, plus `lane_width`, `lanes` (per direction), `kerb_radius`, `tail_length` (how far
     generated geometry reaches out from the corner to meet an approach lane tile), `segments`
     (arc smoothness), `curb_height`/`curb_thickness`. Purely additive — never edits `lane_kit.blend`
     or any existing piece; every run gets its own numbered collection, so presets/radii can be
     compared side by side. Wired into the panel's new "Intersection (prototype)" box (settings
     live on the operator's F9 redo panel, not duplicated into scene properties).
   - **Verified headless, end-to-end**, via `tools/build_intersection_prototype.py` (new,
     unrelated to item 5's still-pending straight/curb-tile generator below): built a 4WAY +
     3WAY_T + 3WAY_Y into `kit/intersection_prototype.blend`
     and re-opened it to check real numbers, not just object counts — all 4 corners of the 4-way
     are exactly congruent (rotational symmetry survived the Python→Blender conversion intact),
     and the T-junction's through-movement centerline is a genuinely straight line at constant
     lateral offset (verified: both endpoints at y=-2.5, only x differs by exactly 2×`tail_length`).
   - **What this does NOT yet do** (fair scope cuts for the prototype, not forgotten): asymmetric
     lane counts (in ≠ out per arm — `Arm` assumes symmetric `lanes`); real swept-path turn shapes
     for large vehicles (the diagram's "previous path too tight" vs "updated path" nuance — a
     single-radius circular fillet is a good first approximation, not a true clothoid/comfort
     curve); visual dashing of the centerline (it's a plain solid line — cosmetic only, easy to add
     later via a points-along-curve instancer); traffic-legality filtering of which turns are
     actually legal (every geometrically-possible movement is generated; L/R/S classification for
     `LaneGraph`/`IntersectionZone` consumption is Phase 4 work, not this prototype).

5. **Suggested next concrete step (not yet done):** a small `bmesh`-based procedural generator,
   e.g. `kit/build_parametric_kit.py`, that builds the item-1 straight tile (and the curb-side
   strip) to the exact spec above and writes it to a **new, separate file** for comparison —
   deliberately not touching the live `kit/lane_kit.blend`, since you're actively hand-authoring
   it right now and a from-scratch rebuild of that file would destroy your in-progress tagging
   work (the 8 tagged 4-way-intersection stubs, the new `Kit_Intersection3Way2Lane` piece). Once
   compared, the parametric version can replace the hand-modeled straight/curb tiles in
   `lane_kit.blend` deliberately (a controlled swap you approve), rather than a script silently
   overwriting the file.

6. **Multi-way, per-arm lanes, graph-ready export, and native Godot `Path3D` consumption —
   SHIPPED (2026-07-24).** Carries item 4's geometry into the game, per explicit user direction:
   build the data as infrastructure for a future cross-network GPS/routing layer (not the routing
   layer itself — vehicle-AI destination logic is out of scope, deferred), and consume it via a
   real native `Path3D`/`Curve3D` route type rather than reusing the `VehicleRoute` Marker3D
   pipeline.
   - `lib/intersection_kit.py`: `preset_nway(angles, lane_width, lanes)` (any arm count, any
     angles); every preset now accepts **per-arm** lane counts (a list parallel to the arm
     angles, `_per_arm` helper, length-validated) instead of one scalar for the whole junction —
     e.g. a 2-lane main street crossing a 1-lane side street. `turn_side(entry_dir, exit_dir)`
     classifies every movement `L`/`S`/`R` from the signed 2D cross product (a through-pair
     movement is always `S`). Every lane gets a globally-unique id
     (`<junction_id>_<from>_<to>_L<lane>`) and a stable per-(arm, lane) **port** — the world
     position + tangent of the far end of that lane's stub — via `build_ports`; a turn and a
     through movement sharing an (arm, lane) reach the *identical* port (verified exactly, not
     approximately, in `self_test()`), since physically they're the same lane before/after the
     junction splits it. `export_dict`/`export_json` (stdlib `json`, still no bpy) write this as
     one graph-shaped `.lanekit.json` sidecar per junction: `arms` (nodes), `lanes` (directed
     edges), `ports` (the seams a future cross-piece linker would connect to) — this is the
     concrete hook for `AUTHORING_GUIDE.md` §11's "always-resident manifest for cross-district A*"
     goal, without building the A* itself. 13 self-test sections now pass (up from 7): per-arm
     lanes + length-mismatch guard, `preset_nway` on an arbitrary 5-way, `turn_side`, cross-junction
     id uniqueness, exact port/lane round-trip, and a real JSON file round-trip.
   - `RKA_OT_build_intersection`: new `NWAY` preset (`arm_angles`, comma-separated degrees) and
     `lanes_arm1..4` per-arm overrides (0 = inherit the shared default) alongside the existing
     three presets; new `export_path` (blank = skip) writes the sidecar via `export_json` once
     geometry is built, using the run's own collection name as `junction_id`.
     `tools/build_intersection_prototype.py` now emits one sidecar per example junction
     alongside `kit/intersection_prototype.blend` — verified end-to-end: regenerated headless,
     spot-checked the JSON directly (ids unique, a turn movement's first point lands exactly on
     its port).
   - **`com.openworld.world.Lane`** (new interface) abstracts a directional lane over its concrete
     representation. **`com.openworld.world.PathLaneRoute`** (new, `implements Lane`) wraps a
     native `Path3D`/`Curve3D` — built at bake time from a sidecar's sampled points
     (`curve.addPoint`, no re-smoothing), with a one-time-cached windowed arc-length search
     (mirroring `VehicleRoute`'s own, since this route type is static/baked and never re-edited at
     runtime) implementing `total()`/`pointAtLength()`/`lengthAtNearest()` off `Curve3D`'s native
     baking. `VehicleRoute` now also `implements Lane` (four thin getters added —
     `getTurn/getApproach/getEndBehavior/getReturnRoute` — since an interface can't expose a public
     field directly; zero behavior change). `LaneGraph` and `VehicleAIController` are retyped from
     `VehicleRoute` to `Lane` throughout (`IntersectionZone` needed no change — verified it never
     referenced `VehicleRoute`). The payoff: `LaneGraph`'s existing endpoint-proximity junction
     derivation — unmodified — now treats *any* mix of `VehicleRoute` and `PathLaneRoute` in one
     scene as one connectivity graph, so a car already goes straight or turns correctly depending
     on whichever successor lane it lands on at a junction (the existing straightness-biased
     weighted pick in `VehicleAIController.advanceToNextRoute`), with **no new AI decision code** —
     exactly the scope the user asked for this pass.
   - `PathLaneRoute` does **not** register with `WorldZoneManager`'s route registry (spawn-config
     lookups) and its `pickNextRoute()`/`resolveRoute()` always return null — connectivity is
     entirely geometry-derived for this route type. Wiring it as an ambient-traffic zone spawn
     target is a natural but separate future step, not required for junction traversal.
   - **`WorldBaker`**: new opt-in `@Export lanekitPath` (blank = skip — auto-deriving it from a
     district's own filename, à la `resolveGeometryPath`'s sibling-`.scn` preference, is a natural
     follow-up once proven on more than the one prototype fixture). When set, parses the sidecar
     (`godot.api.JSON.parseString` — note the class is `JSON`, all-caps, not `Json`) and builds one
     `PathLaneRoute` per lane entry; a `kind == "turn"` movement's `turn` field is now the real
     `L`/`R` from `intersection_kit.py`'s `turn_side` (not guessed), and `through` maps to `S`.
   - **Verified**: `python3 lib/intersection_kit.py` (13/13), the Blender prototype regeneration,
     and `./gradlew build` all pass. A headless Godot smoke test (bake the prototype's sidecar,
     spawn a car directly onto a straight `PathLaneRoute` and one onto a turning `PathLaneRoute`,
     confirm `LaneGraph` carries each across the junction correctly) is the remaining verification
     step — see the session's task list.
   - **Asymmetric in/out lanes per arm — plan-only, NOT implemented, per explicit user
     instruction.** `Arm` would need `lanes_in`/`lanes_out` instead of one symmetric `lanes`;
     `half_width()` would split into a CCW-side (`lanes_out`) and CW-side (`lanes_in`) offset —
     `curb_edges()` already computes each side from a separate method call, so that part is
     contained. The real gap is `build_lane_movements`'s `n_lanes = min(a.lanes, b.lanes)`
     assumption that incoming lane index *i* always continues onto outgoing lane index *i*: once
     counts differ, *which* incoming lane feeds *which* outgoing lane is a genuine authoring
     decision (nearest-offset match? leftmost-continues-leftmost? explicit per-movement mapping?),
     not just arithmetic — that ambiguity, not the geometry math, is why this stays deferred.
     Real-world need is narrow (contraflow/channelized lanes); revisit when a specific district
     actually needs it.

7. **Explicit per-lane connection mapping — SHIPPED (2026-07-24), answers item 6's asymmetric-
   lanes "which incoming lane feeds which outgoing lane" question directly.** Rather than solve
   that ambiguity with an algorithm (nearest-offset, leftmost-continues-leftmost, ...),
   `build_lane_movements`/`export_dict`/`export_json` now accept an optional `lane_map`:
   `{(from_arm, to_arm): [(in_lane, out_lane), ...]}`, overriding the default lane-*i*-feeds-lane-
   *i* pairing for exactly the arm pairs it names (every other pair keeps the default). Every
   pair is validated against the arms' own lane counts — an out-of-range index raises, not
   silently drops. This is also generally useful beyond the asymmetric-count case (e.g. a
   deliberate lane shift/merge on equal-count arms). **Exposed in the Blender UI**, not just as a
   Python parameter: `RKA_OT_build_intersection` gained a `lane_map` string field (F9 redo panel
   or the panel button), mini-syntax `'From>To:in-out,in-out; From2>To2:in-out'` (e.g.
   `'N>E:0-1,1-0'` to swap two lanes), parsed by the new `ops_intersection.parse_lane_map` with a
   clear operator-error report on malformed syntax. A movement's exported `id` reflects a real
   swap (`..._L0to1` instead of `..._L0`) so it's visually distinguishable from a default-paired
   lane. Self-tested (14/14 total now): default pairing unchanged for un-named arm pairs,
   out-of-range validation, id-suffix on a swap.

8. **Sample Blender file with a live edit → Godot import loop — SHIPPED (2026-07-24).**
   `kit/intersection_prototype.blend` (already existed) is the editable sample: open it, use the
   "Intersection (prototype)" panel's "Build Intersection" (or its F9 redo panel) to change
   preset / per-arm lanes / `lane_map` / kerb radius / arm angles, same as before. New this round:
   the operator gained **`gltf_export_path`** (mirrors `export_path`) — set both it and
   `export_path` to matching locations on one run and you get a synchronized `{.glb, .lanekit.json}`
   pair for that exact junction, with **no separate manual export step**. `gltf_export_path`
   exports only the visual mesh objects (`curb_*` walls, `roadribbon_*` driving surfaces) — not
   the `lanecl_*` data curves, which carry no separate meaning once exported since the JSON
   sidecar is the data source of truth for Godot.
   - `tools/build_intersection_prototype.py` now also writes the 4-way's pair to
     `src/main/resources/com/openworld/world/districts/District_intersectiondemo.glb` +
     `kit/intersection_prototype.4way.lanekit.json` on every regeneration (kept as the default,
     ready-to-bake fixture).
   - **New `tools/build_intersection_piece.sh`** — deliberately does **not** invoke Blender or
     regenerate the `.blend` (that would wipe manual edits, same reasoning as `build_piece.sh`'s
     stem form): it assumes the `.glb`/`.lanekit.json` pair is already on disk (either from the
     script above or a manual Blender export via the operator's two export fields), triggers a
     Godot import (`--headless --import`), and bakes via a throwaway `WorldBaker` host — same
     `bake_one()` idiom as `build_piece.sh`, minus the `xvfb`/non-headless requirement (no
     MultiMesh content here, so no RenderingServer transform-buffer dependency) — into
     `District_intersectiondemo.tscn`, then repoints **new `SoloIntersection.tscn`** (mirrors
     `SoloPiece.tscn`: Player + WorldSystems + DebugHarness) at it.
   - **The loop**: edit in the Blender GUI (F9 redo, tweak, done) → `tools/build_intersection_piece.sh`
     → open `SoloIntersection.tscn` in the Godot editor (or run it) to walk around and, via
     `DebugHarness`, spawn AI traffic and watch a car actually turn or go straight depending on
     which `PathLaneRoute` it lands on.
   - **Verified**: regenerated the demo, ran the bake script end-to-end (`WorldBaker: lanekit
     sidecar ... → 12 PathLaneRoute(s)`, `pathlanes=12` in the bake summary), and loaded
     `SoloIntersection.tscn` headlessly for 60 frames with no errors — visual walk-testing itself
     is for the user in the editor.
   - **Addon install caveat (bit the user immediately on first try):** `intersection_prototype.blend`
     is built by a *headless* script that registers the addon in-process — that registration is
     never saved into the `.blend` (Blender addon registration is a Python/runtime thing, not
     scene data). Opening the file in an ordinary interactive Blender session has no "Road Kit"
     panel and nothing for F9 to repeat unless the addon is ALSO installed the normal way:
     symlink `assets/world_source/addons/road_kit_authoring` into
     `~/.config/blender/<version>/scripts/addons/`, then enable it in Edit > Preferences > Add-ons
     (per-user, persists across files — a one-time step, not something a script should do).

9. **Straight two-way road segment — SHIPPED (2026-07-24), the piece missing between
   intersections.** Neither `build_curb_corners` (only ever draws the *rounded corners*, not the
   straight curb run along an arm's own sides) nor anything else generated a plain connecting
   stretch of road — every intersection's arms ended in dangling ports with nothing to actually
   connect to. New, in `lib/intersection_kit.py`: `build_straight_segment(p0, p1, lane_width,
   lanes, segment_id)` — a plain 2-point road (curb left/right + N lanes each direction, offset
   outward from centerline exactly like an intersection arm's own lane offsets) — and
   `export_segment_json`, emitting the **exact same lane JSON shape** `build_lane_movements`
   already does (`id`/`points`/`loop`/`turn`/`kind`) — deliberately, so `WorldBaker`'s sidecar
   loader consumes it with **zero Java changes** (verified: baked a segment's own sidecar alone,
   `pathlanes=2` for a 1-lane-each-way segment). This is also the template any future custom piece
   (a bridge/ramp mesh, hand-modeled) should follow to plug into the same lane graph — the
   contract is just "emit a `lanes` array in this shape," not "be built by this generator."
   New **`RKA_OT_build_straight_segment`** (`ops_segment.py`): 3D-cursor start point,
   `direction_deg` + `length`, same `lane_width`/`lanes`/curb/export fields as the intersection
   operator, wired into the panel's new "Straight Segment" box. **Connecting pieces needs no
   explicit stitching step in Blender at all** — position a segment's start/end near an existing
   piece's port (printed by `build_ports`, or just eyeballed) and `LaneGraph`'s existing
   endpoint-proximity clustering links them automatically at Godot bake/runtime, exactly like it
   already does for a hand-authored `VehicleRoute` network. Verified numerically: a segment
   positioned at an intersection's printed port lands ~2.5 m off exactly (half a lane-width — a
   port is the *lane's* position, offset from the road centerline the cursor should target;
   positioning at the centerline instead lands exactly on it) — comfortably inside
   `LaneGraph.JUNCTION_RADIUS` (4.5 m), which exists precisely to tolerate this much authoring
   slop per its own docstring. 16/16 self-tests now (up from 14): curb/lane offset geometry,
   JSON shape + file round-trip.

10. **Custom Blender data fields instead of string mini-syntax — SHIPPED (2026-07-24), per user
    request.** The `lane_map` operator field's `'From>To:in-out,in-out'` mini-syntax was flagged
    as unnecessarily "complex" to hand-write — new `custom_props.py` gives a native-Blender
    alternative that both operators now use:
    - **After every build**, the operator's fully-resolved settings — preset/angles/lane counts,
      and `lane_map` as a **plain nested dict/list** (`{'N>E': [[0,1],[1,0]]}`), not a string — are
      written onto the created Collection as ordinary custom properties (`coll["rka_..."] = ...`,
      Blender's native ID-property system, which already stores nested dict/list structures
      directly via the Python API — no encoding needed). This is a permanent, native-UI-visible
      record of exactly how a piece was built, viewable/editable via Object/Collection Properties >
      Custom Properties even without the addon's redo panel — which is lost the moment the file is
      closed and reopened (F9 only replays within the same undo history).
    - **Before building**, `RKA_OT_build_intersection` checks the *active* collection for an
      `rka_lane_map` custom property first — if present, it wins over the operator's string field
      entirely, so a `lane_map` can be hand-authored/edited as native nested data in Blender's own
      UI (or the Python console: `coll["rka_lane_map"] = {"N>E": [[0, 1]]}`) with no string DSL
      involved. The string field remains for quick one-off/scripted entry
      (`tools/build_intersection_prototype.py` still uses it) — both paths converge on the exact
      same `{(from,to): [(in,out),...]}` shape `build_lane_movements` expects.
    - **Object names shortened to match, once the collection carries the structured record.**
      Every curb/curve/ribbon name used to repeat the full collection name (e.g.
      `curb_Intersection_4WAY_001_N_E`) purely so a human scanning a flat list could tell pieces
      apart — pure redundancy now (and even before this, since Blender's Outliner already nests
      objects under their collection). Confirmed via `WorldBaker`'s prefix table
      (`lane_`/`zone_`/`spawn_`/`water_`/`intersection_`/`instance_`/`mmesh_`) that `curb_`/
      `lanecl_`/`roadribbon_` were never pattern-matched by anything downstream — every Godot-side
      lookup goes through the exported JSON's own `id`, which correctly stays fully qualified
      (must be globally unique across a multi-junction scene) and was NOT shortened. Now:
      `curb_NE`, `lanecl_NE_L0` (or `_L0to1` on a `lane_map` swap, mirroring the JSON id
      suffix), `ribbon_NE_L0` for intersections; `curb_L`/`curb_R`, `lanecl_AB_L0`/`lanecl_BA_L0`
      for segments. Purely a Blender-authoring-convenience rename — verified the full
      export/bake/`PathLaneRouteTestHost` smoke test (`verdict=PASS`) still passes unchanged,
      since none of it depends on these names.

11. **Selectable curb style (BOX / GUTTER) — SHIPPED (2026-07-24), per user request.** Every
    curb generated so far was a plain flat wall (`swept_wall`). The user pointed at a REAL
    hand-modeled piece already in `kit/lane_kit.blend`,
    `kit_side_straight_city_gutter_curb_w0p6m_l5m` (`Kit_CurbSideCityGutter`), and asked for
    something like it. Inspected it read-only (never modified, per the standing constraint) —
    ~0.6 m wide, ~0.2 m tall, a flush road-facing apron stepping up to a flat-topped curb face,
    not a simple box. Literally extracting that mesh's exact topology and bending it along an
    arbitrary-length swept curve isn't a good fit (it's a fixed 5 m straight tile); the user
    explicitly said to simplify to just width/height instead of chasing an exact match.
    - New in `kit_common.py`: **`swept_profile(name, pts, profile_2d, coll, matkey)`** —
      generalizes `swept_wall`'s exact tangent/right-normal-offset technique (no NURBS
      approximation) from a fixed rectangle to an *arbitrary* 2D cross-section (an ordered list of
      `(lateral_offset, height)` pairs) swept along a polyline. **`gutter_curb_profile(width,
      height)`** — a 4-point profile (flush road edge → flush apron edge → curb base → curb top)
      matching the real piece's silhouette at just its width/height, not its literal topology.
    - New `curb_style` enum (`'BOX'` default / `'GUTTER'`) on **both** `RKA_OT_build_intersection`
      and `RKA_OT_build_straight_segment`, dispatched through one shared `build_curb()` helper
      (`ops_intersection.py`, imported by `ops_segment.py`) so the two operators can't drift.
      `curb_thickness` doubles as "gutter width" in GUTTER style (its description says so).
      Persisted via the existing custom-property mechanism (item 10) alongside everything else.
    - **Verified**: built a 4-way + a segment with `curb_style='GUTTER', curb_thickness=0.6,
      curb_height=0.2` headlessly — correct vertex/face counts for the swept profile (a 9-point
      corner arc × 4-point profile → 36 verts/24 faces; a straight 2-point segment side → 8
      verts/3 faces), `rka_curb_style` custom property round-trips. Default is unchanged (`BOX`),
      so the existing demo/bake/smoke-test pipeline needed no other changes and still passes as-is.

12. **Extend/insert/curve network-editing tools — SHIPPED (2026-07-24).** Answers "how do I grow
    a network from here, splice a junction into an existing road, and bend a segment slightly" —
    the angle-tweaking half of the same question was already covered (NWAY's `arm_angles`,
    T/Y's `side_angle`); the missing piece was a global **`rotation_deg`** on
    `RKA_OT_build_intersection` (added to every arm's angle after the preset is built, so
    ANY preset can be aligned to an existing road's direction — not just angle-tweaked in
    isolation) plus the three tools below.
    - **`custom_props.read_arms(coll)`/`read_origin(coll)`** (new) reconstruct an intersection's
      `[(name, angle_deg, lanes), ...]` and raw build-time cursor position from its own
      `rka_arm_names`/`rka_arm_angles`/`rka_arm_lanes`/`rka_origin` custom properties (item 10) —
      `RKA_OT_build_intersection` now also writes `rka_origin`. This is what lets a *later* tool
      reconstruct a piece's exact geometry without re-deriving or guessing it.
    - **`RKA_OT_extend_from_arm`** (new, `ops_segment.py`): activate an intersection's collection,
      pick an arm by name, get a length — builds a new segment starting EXACTLY at that arm's
      stub end, in its exact direction. Because both the intersection's own lane ports and a new
      segment's lane offsets are built the identical "centerline + symmetric `(i+0.5)×lane_width`
      offset" way, this lands at **exact (0 m) alignment**, not just within `LaneGraph`'s 4.5 m
      proximity tolerance — verified numerically (distance = 0.0).
    - **Curved segments**: `build_straight_segment`/`export_segment_json` gained `bend`
      (meters, default 0.0 = byte-identical to the old dead-straight behavior — verified no
      regression) and `segments`. A nonzero `bend` samples a quadratic bezier (control point
      offset from the midpoint) into a polyline, and every lane/curb line is now offset from a
      **local per-point tangent** (not one constant direction) — so a curved segment's lanes and
      curbs genuinely follow the bend, still via the same exact-point sweep technique used
      everywhere else (`swept_wall`/`swept_profile`/`flat_ribbon` already accepted arbitrary-length
      polylines; only the ONE `ops_segment.py` call site that destructured curbs as exactly 2
      points needed fixing). Self-tested: endpoints stay anchored at p0/p1 exactly regardless of
      bend, the midpoint genuinely bulges (not a no-op), arc length exceeds the chord, and a
      bigger `bend` curves more.
    - **`RKA_OT_insert_intersection_on_segment`** (new, `ops_segment.py`, **auto-replace — user
      explicitly confirmed this over a non-destructive report-only alternative**): activate a
      segment's collection, pick a split fraction (+ preset/side angle/optional side-arm length)
      — deletes that segment's objects and collection, builds a new intersection at the split
      point rotated to match the original segment's direction (`rotation_deg`), then calls
      `RKA_OT_extend_from_arm` twice (finding the forward/backward arms by closest angle, not by
      hardcoded name, so this works for any preset) to rebuild the two shorter segments on
      either side — reaching the *exact* original endpoints. Only ever deletes addon-generated
      segment collections, never anything hand-authored. Verified: split a 40 m segment at
      fraction 0.5 → the two rebuilt segments' endpoints are exactly `{0.0, 40.0}` (the original
      p0/p1), spanning the new intersection's footprint in between.
    - Wired into the panel's new "Extend / Insert" box, which shows the right button
      (`Extend From Arm` / `Insert Intersection On Segment`) based on what's active, or a hint to
      activate a piece first.
    - **Verified**: `python3 lib/intersection_kit.py` 17/17; both new operators exercised
      headlessly (exact-alignment extend, correct-span insert); full demo regen + bake +
      `PathLaneRouteTestHost` smoke test (`verdict=PASS`) still pass unchanged, since none of
      this touches the default-behavior path.

13. **Workflow bug fixes — arm markers, cursor auto-advance, F9/curb-toggle, slope, one-mesh
    export — SHIPPED (2026-07-24).** Item 12 built extend/insert/curve, but real use surfaced
    four sharp edges: no visible "arm" to click when extending, new pieces landing at the world
    origin instead of continuing the road, F9 (Adjust Last Operation) silently doing nothing after
    Extend/Insert, and no way to combine or slope a piece.
    - **Root cause of "F9 doesn't work" / "curb toggle doesn't work": nested `bpy.ops.rka.X(...)`
      calls.** `RKA_OT_extend_from_arm` used to build its segment by calling
      `bpy.ops.rka.build_straight_segment(...)` from inside its own `execute()`, and
      `RKA_OT_insert_intersection_on_segment` called `build_intersection`/`extend_from_arm` the
      same way. Each nested `bpy.ops.rka.X()` call pushes its OWN separate undo step, so Blender's
      F9 panel ends up showing the *innermost* operator's properties — not the outer one you
      actually meant to tweak (arm name, split fraction, curb style, bend...). **Fix:** the build
      logic behind every operator was extracted into plain functions with no `bpy.ops` dispatch —
      `build_intersection_geometry()` (`ops_intersection.py`) and `build_segment_geometry()`
      (`ops_segment.py`) — and every operator (`RKA_OT_build_intersection`,
      `RKA_OT_build_straight_segment`, `RKA_OT_extend_from_arm`,
      `RKA_OT_insert_intersection_on_segment`) is now a thin wrapper that calls these directly.
      Insert is now genuinely ONE flat operator/one undo step with its own complete F9 panel
      (fraction/preset/curb style/join-mesh all live and re-apply correctly on redo).
    - **Arm marker Empties ("place arm at end of each intersection")**: `build_intersection_geometry`
      now creates one `arm_<name>` Empty (`SINGLE_ARROW`, oriented along the arm) at each arm's
      tail end, carrying `rka_arm_name`/`rka_arm_angle`/`rka_arm_lanes` custom properties — a
      visible, clickable handle. `RKA_OT_extend_from_arm`'s poll/execute
      (`_resolve_intersection_and_arm`) now accept EITHER the intersection's collection active in
      the Outliner (original workflow, type the arm name) OR one of its `arm_*` Empties as the
      active object (new — click the arm, leave "Arm" blank, it self-fills). Verified headlessly:
      4-way → 4 arm Empties at the correct tail positions; extending from a clicked Empty lands
      exactly on that arm's port.
    - **Cursor auto-advance ("new segment created at origin instead of continuing")**: this was
      real — `RKA_OT_build_straight_segment` never moved the cursor, so repeatedly pressing it
      (the natural "keep going" workflow, as opposed to Extend From Arm) rebuilt at the same spot
      every time, landing at the world origin if the cursor had never been moved. New
      `auto_advance_cursor` prop (default **on**) moves the 3D cursor to the segment's end point
      (XY **and** elevation) after building, so the next press continues the road. Verified: a
      sloped segment (`elevation_delta=3`) starting at z=5 leaves the cursor at z=8; a second
      segment built right after starts exactly there, not back at the original point.
      `RKA_OT_extend_from_arm` never touches the cursor at all (arm data alone fixes its start
      point/direction, so there's no ambiguity to resolve).
    - **Slope ("upload slope, or slightly curve")**: `intersection_kit.build_straight_segment`/
      `export_segment_json` gained `z0`/`z1` (a relative elevation at p0/p1 — constant grade when
      they differ) and `bend_z` (a vertical crest/dip bump at the midpoint, the same
      `4·t·(1-t)` parabola shape used nowhere else in this module — simple and predictable,
      independent of the lateral `bend`). Every returned point is now a 3-tuple `(x,y,z)`; z is
      0.0 throughout when the new params are left at their defaults, so this is a byte-identical
      no-op for every existing caller. One real bug caught by self-test: when `bend == 0` the
      spine was always exactly 2 points, so `bend_z` alone had no midpoint sample to land on —
      fixed by also subdividing the spine (via a bezier whose control point IS the midpoint, which
      degenerates to an exact linear subdivision) whenever `bend_z != 0`, not just when `bend !=
      0`. Exposed on `RKA_OT_build_straight_segment`/`RKA_OT_extend_from_arm` as `elevation_delta`
      / `bend_z`. Self-tested (18/18): flat case unaffected, linear grade hits the right z at the
      midpoint, `bend_z` bumps the midpoint and stays zero at both ends, curbs slope too.
    - **One mesh ("let the intersection mesh be one mesh, or one mesh at export")**: new
      `join_meshes()` helper (`ops_intersection.py`) + `join_visual_mesh` operator prop (default
      off, so existing per-piece-object behavior is unchanged unless asked for) on all four
      operators — selects every curb/ribbon mesh object just built, `bpy.ops.object.join()`s them
      into one, renamed `mesh_<collection name>`. Verified headlessly for both an intersection
      (336 verts, 1 object) and a segment.
    - **What's still NOT built** (scope explicitly deferred, not a bug): true click-and-drag live
      geometry editing ("bevel-style" handles) would need the intersection/segment rebuilt as a
      Geometry Nodes group driven by the arm Empties' transforms — a different architecture from
      today's "Python computes points, `kit_common` sweeps a mesh" pipeline. The arm Empties +
      now-working F9 redo panel are today's practical adjustment path (nudge a number, re-run);
      revisit Geometry Nodes only if that friction turns out to matter in practice.
    - **Verified**: `python3 lib/intersection_kit.py` 18/18; headless demo regen (arm-Empty counts
      match expected: 4-way 32 objects = 4 curb + 12 lanecl + 12 ribbon + 4 arm, T 17, Y 18);
      a dedicated headless script exercising arm-Empty click-to-extend, cursor auto-advance
      (with elevation), and the flattened insert-on-segment op all pass; `join_visual_mesh`
      verified on both an intersection and a segment.

14. **Live click-and-drag editing (handler-driven, NOT a Geometry Nodes rewrite) — SHIPPED
    (2026-07-25).** Item 13 said true drag-to-adjust "bevel-style" handles would need a Geometry
    Nodes rewrite; asked directly, the answer is a **deliberate no** on rewriting the pipeline in
    GN, for a concrete reason: GN can't write the `.lanekit.json` sidecar Godot/WorldBaker actually
    consume, so the tested Python geometry in `lib/intersection_kit.py` would still have to run for
    export regardless — a GN graph would be a SECOND, parallel implementation of the same
    corner-fillet/lane math (through-pair detection, variable arm count, curb-style dispatch),
    with real risk of silently drifting from what actually ships to Godot. Instead: a
    `depsgraph_update_post` handler detects a moved marker Empty and reruns the exact same,
    already-tested functions that back the fresh-build operators — one source of truth, genuinely
    live in the viewport.
    - **`live_edit.py`** (new module, registered as an addon submodule): the handler
      (`_on_depsgraph_update`) scans `depsgraph.updates` for transform changes on an Empty
      carrying `rka_arm_name`/`rka_segend`/`rka_segbend`, and calls
      `ops_intersection.rebuild_intersection_in_place` / `ops_segment.rebuild_segment_in_place` on
      its owning collection. A `_rebuilding` re-entrancy guard plus epsilon-gated marker
      repositioning (only write `.location` back if it actually moved >0.1mm) keeps a rebuild's
      own corrective snap from re-triggering itself indefinitely — verified to settle after at
      most one extra harmless pass, never oscillates.
    - **`rebuild_intersection_in_place(context, coll)`** (`ops_intersection.py`): re-derives each
      arm's ANGLE from its `arm_*` Empty's current bearing off the stored `rka_origin`, deletes the
      old curb/lane objects (`clear_generated_mesh_objects`, keeps every marker Empty), rebuilds via
      a newly-factored `_populate_intersection_mesh` (the same corner/movement/curb/ribbon loop
      `build_intersection_geometry` uses for a fresh build — one function, two callers, so the two
      paths can't drift), then re-snaps each arm back onto the fixed `tail_length` radius (dragging
      an arm ROTATES it around the junction — reshaping the intersection — rather than also
      silently changing tail length, which stays one shared scalar, not per-arm).
    - **`rebuild_segment_in_place(context, coll)`** (`ops_segment.py`): a fresh build now also
      places `segend_A`/`segend_B` (the two endpoints) and `segbend` (the current lateral-`bend` +
      vertical-`bend_z` control point) as marker Empties. Dragging `segend_A`/`segend_B` re-derives
      p0/p1 (and elevation, from their world Z) directly; dragging `segbend` projects its position
      onto the chord's perpendicular+vertical plane to re-derive `bend`/`bend_z` (any along-the-chord
      drag component is ignored, then the marker is re-snapped onto that plane) — so one handle
      each for length/direction, elevation, lateral curve, and vertical crest/dip.
    - **"Build Intersection always uses the cursor, not wherever I just selected" — fixed.**
      `active_marker_position(context)` (`ops_intersection.py`): if the active object is any of
      this addon's marker Empties, both `RKA_OT_build_intersection` and
      `RKA_OT_build_straight_segment` now build starting exactly THERE (and parent the new piece
      as a sibling of the marker's own piece via `parent_collection_of`) instead of at the 3D
      cursor — cursor stays the fallback when no marker is active. Answers "should add arm for
      each segment end?" too: segments now carry the same kind of marker Empties intersections do
      (`segend_A`/`segend_B`), so selecting a segment's end and pressing "Build Intersection"
      lands the new junction there.
    - **`RKA_OT_rebuild_from_handles`** (new, manual fallback): re-runs the same in-place rebuild
      on demand. Exists because a `depsgraph_update_post` handler's dispatch during an actual
      interactive drag could only be partially verified headlessly (see below) — this button is
      the "definitely works regardless" escape hatch, and doubles as the doc-recommended fix if
      "Live Edit From Handles" (new scene toggle, `RKA_SceneSettings.live_edit_enabled`) is off.
    - **What's still NOT built**: per-arm radius (dragging an arm only rotates it, not its
      distance — the data model has one shared `tail_length`, not per-arm; a real ask, revisit if
      it matters in practice), and a `kerb_radius`/`lane_width`/curb-style live handle (still
      F9/custom-property/typed, not drag-adjustable).
    - **Verification & an honest gap**: `python3 lib/intersection_kit.py` 18/18 unchanged; a
      dedicated headless script simulates drags by setting a marker's `.location` and calling
      `rebuild_*_in_place` directly (proves the rebuild math end to end — angle/length/bend/
      elevation all correctly re-derived, arm re-snapped to the fixed radius, repeated rebuilds
      with no further movement are stable/non-oscillating); active-marker-snap verified (`Build
      Intersection` with a `segend_B` marker active lands on it, not a deliberately-different
      cursor position); `join_visual_mesh`/full demo regen still pass unchanged. **Not verified
      headlessly**: whether `depsgraph_update_post` actually fires during a real interactive
      viewport drag — Blender's `--background` scripted mode does not dispatch this handler the
      same way an interactive session does (confirmed: `obj.location = ...` + `view_layer.update()`
      in a background script does NOT fire it, even with `update_tag()`), so this specific claim
      rests on the handler's documented contract (the same mechanism widely used by rigging/
      constraint addons for live updates) rather than a headless proof. `RKA_OT_rebuild_from_handles`
      exists specifically to de-risk this gap.

15. **Live lane-count and arm-count controls — SHIPPED (2026-07-25).** Item 14's drag handler only
    watches marker TRANSFORM changes; a lane/arm COUNT is an integer, not something you drag, and
    hand-editing the `rka_arm_lanes`/`rka_lanes` custom property doesn't trigger the handler at all
    (no transform changed) — so those were still effectively build-time-only. Four new operators,
    all one-click and immediately live (call the item-14 in-place rebuild themselves, no drag or F9
    needed), wired into the panel's "Live Edit" box next to whatever's active:
    - **`RKA_OT_adjust_arm_lanes`** (+/-, active object = an `arm_*` marker): bumps that arm's own
      `rka_arm_lanes` (clamped 1-3) and rebuilds.
    - **`RKA_OT_add_arm`** / **`RKA_OT_remove_arm`**: add places a new `arm_*` Empty at the WIDEST
      angular gap between the intersection's current arms (`_widest_gap_angle`, wrapping-aware) so
      it can't land on top of an existing one, named with the next free letter
      (`_next_arm_name`); remove deletes the active arm marker. Neither needed any change to
      `rebuild_intersection_in_place` itself — it already reads whatever `arm_*` Empties exist in
      the collection with no preset/arm-count hardcoded anywhere, so a 4-way can become a 5-way (or
      a hand-built 7-way back down to a 6-way) with no new geometry code. Remove refuses below 3
      arms (a 2-arm "intersection" is just a through street).
    - **`RKA_OT_adjust_segment_lanes`** (+/-, active = a segment or one of its markers): same
      pattern for a segment's `rka_lanes` (both directions, since segments don't yet have a
      forward/backward split — see the open "direction of lane" question below).
    - **Verified headlessly**: arm lanes bump/clamp and the stored `rka_arm_lanes` custom property
      updates; Add Arm on a 4-way produces a 5th arm at the expected 45° gap-midpoint (all 4 gaps
      were 90°) and one more curb corner; Remove Arm undoes it back to a clean 4-way, then correctly
      refuses a further removal at 3 arms; segment lane bump produces the expected +2 ribbon objects
      (one new lane × two directions).

16. **Open question, deliberately not guessed at: "direction of lane" + "slope looks like a fixed
    piece."** Two asks in the same request whose concrete implementation depends on which of
    several plausible readings is meant — flagged rather than built to avoid wasted work:
    - *Direction of lane* could mean (a) asymmetric lane counts per direction on a segment (e.g. 2
      lanes forward + 1 back) — the exact gap already named as deferred in item 4's "asymmetric
      in/out lanes" design note; (b) a one-way toggle (build only the forward lanes); or (c) which
      physical lane index feeds which on an intersection turn — already solvable today via
      `lane_map` (item on `RKA_OT_build_intersection`), just not obviously discoverable.
    - *Slope "seems like a fixed piece, not an array/follow-curve"* — checked `kit_common.py`'s
      `swept_wall`/`flat_ribbon`/`swept_profile`: all three already sweep along the EXACT input
      3D polyline (each point keeps its own Z; the tangent computed from XY only affects the
      horizontal offset direction, not height) — no flattening bug found there. Most likely reading
      is workflow, not geometry: a straight (unbent) sloped segment is genuinely just 2 points
      tilted as a flat ramp (correct for a straight line — nothing to "follow" yet), which may read
      as "fixed" if a continuously-varying grade (not just a straight tilt) or a curve-object-driven
      path was expected instead of the `bend`/`bend_z` scalar controls item 13 shipped.
    - **Resolved (user chose, 2026-07-25): asymmetric lane counts for "direction of lane" (item
      17), author-a-real-Curve for "slope" (item 18).**

17. **Asymmetric / one-way lanes, for both intersections and segments — SHIPPED (2026-07-25).**
    Directly answers a follow-up requirement ("one road can have only one lane, one way — ensure
    both intersection and segment can accommodate it"), building on the "asymmetric lane counts"
    choice above.
    - **`Arm.oneway`** (`intersection_kit.py`, None default): `'IN'` = this arm only ever
      RECEIVES traffic (0 outgoing lanes — e.g. a one-way street feeding INTO the junction);
      `'OUT'` = only ever SENDS (0 incoming lanes — e.g. a one-way exit). `lanes_in_count()`/
      `lanes_out_count()` gate `build_lane_movements`'s default pairing (now
      `min(a.lanes_in_count(), b.lanes_out_count())`, not `min(a.lanes, b.lanes)`) and
      `build_ports`'s two loops — an OUT-only arm can never be a movement's `from`, an IN-only arm
      can never be a `to`. `half_width()`/curb geometry are UNCHANGED (a one-way arm is still the
      same physical width). Self-tested (test 19): a 4-way with S='IN'/W='OUT' produces zero
      `to=='S'`/`from=='W'` movements, the reverse directions are unaffected, curb corner count
      (4) is untouched, ports only exist for the direction each arm actually carries.
    - **`RKA_OT_set_arm_oneway`** (`ops_intersection.py`, live toggle: Both/In Only/Out Only) on
      the active `arm_*` marker — writes `rka_arm_oneway`, immediately rebuilds. Combine with 1
      lane (`RKA_OT_adjust_arm_lanes`) for a true single-lane one-way arm. `build_intersection_geometry`
      /`RKA_OT_add_arm` write `rka_arm_oneway = ""` (both-ways) on every newly created arm marker
      so the key is always present; `rebuild_intersection_in_place` reads it per arm each pass.
    - **`intersection_kit.build_segment_from_spine`** (new core, see item 18) takes `lanes`
      (forward) and `lanes_backward` (reverse, defaults to `lanes` if `None` — symmetric,
      unchanged); either may be 0 (curb width uses `max(lanes, lanes_backward)`, so the road is
      still full-width on its active side), but BOTH being 0 raises `ValueError` — a road needs a
      lane somewhere. `build_straight_segment` gained the same `lanes_backward` param, delegating
      to the new core (self-test 20: `lanes=1, lanes_backward=0` → exactly 1 lane, curb matches
      the 1-lane width not the old 2-lane width, `lanes=0 & lanes_backward=0` raises, and calling
      the spine path directly reproduces `build_straight_segment`'s result exactly).
    - **`RKA_OT_build_straight_segment`/`RKA_OT_build_segment_from_curve`**: `Lanes Forward`/
      `Lanes Backward` operator props (both default 1, explicit 0 allowed — no magic sentinel).
      **`RKA_OT_extend_from_arm`**: automatically matches the source arm's `oneway` (0 lanes on
      whichever side the arm can't carry) — no manual lanes_backward prop needed there, since the
      arm itself is the source of truth. **`RKA_OT_adjust_segment_lanes`** gained a `backward`
      bool (targets `rka_lanes` vs `rka_lanes_backward` independently) and refuses to drop both to
      0. **Known gap**: `RKA_OT_insert_intersection_on_segment` still treats the split segment's
      lanes as symmetric (reads only `rka_lanes`) — splicing an asymmetric/one-way segment doesn't
      yet propagate that asymmetry to the rebuilt pieces or the new intersection's arms.
    - **Verified headlessly**: a one-way single-lane segment builds exactly 1 ribbon object (not
      2); requesting 0 lanes both directions is refused with a clear error; an intersection arm
      set to `In Only` produces zero movements terminating there (checked directly against
      `build_lane_movements`, not by parsing object names) while the reverse direction is
      unaffected.

18. **Curve-object-driven segment paths — SHIPPED (2026-07-25).** The user's explicit choice for
    "slope looks like a fixed piece": author the road's path as a real Blender Curve object (any
    spline type, Edit Mode, as many control points as wanted) instead of the `bend`/`bend_z`
    scalar model — a genuine multi-point curve/slope, not just one bump.
    - **`intersection_kit.segment_spine_3d`/`build_segment_from_spine`** (new): the p0/p1/bend
      spine-computation and the curb/lane offset logic were split into two functions —
      `build_straight_segment` is now a thin wrapper (`segment_spine_3d` then
      `build_segment_from_spine`), and a caller with its OWN already-resolved 3D spine (a sampled
      curve) calls `build_segment_from_spine` directly. Both paths share one geometry
      implementation — no drift between "straight+bend" segments and "curve-driven" ones.
    - **`_sample_curve_world_points`** (`ops_segment.py`): evaluates a Curve object through the
      depsgraph (`evaluated_get().to_mesh()`, respecting Bezier handles/resolution/modifiers, no
      `bpy.ops`/temp objects) and returns its points as world-space `(x,y,z)` tuples in spline
      order — the standard technique, same vertex order as Blender's own Convert To Mesh for an
      un-beveled curve.
    - **`RKA_OT_build_segment_from_curve`**: select a Curve, run it — builds curb/lane geometry
      following the curve's exact evaluated points, plus a `segcurve_driver` marker Empty
      recording which curve to re-sample on rebuild. **`rebuild_segment_from_curve_in_place`**:
      the live-edit counterpart — re-samples the curve's current points and rebuilds. **`export_
      segment_from_spine_json`** (new): same shape/WorldBaker-compatible sidecar as
      `export_segment_json`, but for an already-ABSOLUTE-Z spine (no separate world-height base
      to add, since curve points already carry real elevation) — self-tested (test 21) for correct
      Godot axis conversion.
    - **`live_edit.py`** extended: the `depsgraph_update_post` handler now also watches Curve
      objects (`is_updated_geometry` for Edit-Mode point drags, `is_updated_transform` for moving
      the whole curve, plus a fallback for Blender versions that report the Curve DATA id instead
      of the Object during Edit-Mode edits) and, via a reverse scan of collections' `rka_curve_object`
      property, rebuilds any segment driven by that curve. `RKA_OT_rebuild_from_handles` and
      `_live_edit_target_collection` (`ops_intersection.py`) also recognize a curve-driven
      segment's `segcurve_driver` marker OR the driving curve object itself as valid "active"
      targets, so the manual fallback works there too.
    - **Verified headlessly**: a 4-point POLY curve produces a segment whose lane centerline
      starts/ends at the curve's actual points (offset by exactly one lane-width, since the curve
      is the ROAD centerline and the lane sits beside it — confirmed this is the expected geometry,
      not a bug); dragging a curve control point + calling `rebuild_segment_from_curve_in_place`
      reshapes the road to match; `RKA_OT_rebuild_from_handles` works with either the curve-segment's
      driver marker OR the curve object itself as the active object.

## On JSON sidecar vs. custom-properties/glTF-extras (design note, not implemented)

Asked whether the Godot-side data interchange (`WorldBaker`'s `lanekitPath` JSON sidecar loader,
already shipped and tested per Kit geometry v2 item 6) should instead read the lane/port data from
Blender custom properties carried through as glTF "extras," eliminating the separate `.lanekit.json`
file. Recommendation: **keep the JSON sidecar as-is; don't build the extras-based path** unless a
concrete need for it shows up. Reasoning:
- The JSON loader is ALREADY WORKING and tested (`PathLaneRouteTestHost`, `verdict=PASS`) — this
  would be a rewrite of a proven Java pipeline for a "fewer files to manage" benefit, not a
  correctness or missing-feature fix.
- glTF "extras" genuinely CAN carry this (custom properties export fine per-node, and a glTF
  extras dict is arbitrary JSON-serializable data — no different in kind from the sidecar), so
  it's not blocked by the earlier-documented "one extras Dictionary" gotcha (that's about a single
  node's several custom properties landing in ONE Godot meta key, not a cross-object collision) —
  but it WOULD require re-deriving `WorldBaker`'s loader to read per-node extras out of the
  imported scene instead of `godot.api.JSON.parseString`-ing a file, a real Java change to
  something that isn't broken.
- The lanecl_* Curve objects the Blender addon already bakes into the .glb are currently INERT —
  WorldBaker's loader ignores the .glb's own geometry entirely and reads the separate JSON instead
  (a genuine duplication, noted here for visibility, not urgency). If this ever gets revisited,
  the more valuable fix is probably making `WorldBaker` consume the lanecl_* curves it already
  imports directly (no sidecar OR extras needed) rather than adding a third representation.
## Phase 2 — Centerline authoring + curb attach

> **Design change (2026-07-23): extracted from tagged mesh topology, not guessed.** The original
> P2.1 (`RKA_OT_add_centerline` = bbox-midline guess, then hand-reshape) is replaced: the artist
> hand-tags each lane's true centerline as a chain of vertices (following existing mesh edges) in
> a `lanedata` vertex group on the mesh — already done in `lane_kit.blend` for both straight
> pieces and (as of this session) 8 of the 4-way intersection's approach stubs. Several *disjoint*
> lane paths can share one `lanedata` group on one mesh (e.g. every movement through an
> intersection) — edge-connectivity alone separates them into distinct lanes, no per-lane group
> needed. `kit_common.centerlines_from_vertex_group(obj, "lanedata")` (new, `lib/kit_common.py`)
> does the extraction: builds the subgraph of mesh edges whose both endpoints are tagged, splits
> it into connected components (one lane each), walks each component from an endpoint (or an
> arbitrary start if it's a closed loop) to produce an ordered point list; a vertex with >2 tagged
> neighbours raises (a lane must be a simple path or loop, never a branch); an isolated tagged
> vertex with no edge partner is skipped with a warning, not an error (lets tagging happen
> incrementally). Verified against the live `lane_kit.blend` (read-only, no save): 2/2 correct on
> both straight pieces, and correctly split the 4-way intersection's 16 tagged verts into 8
> separate 2-point lanes.
> Each extracted curve is inherently **one direction** (it's the mesh's own physically-separate
> drivable strip, not a shared bidirectional line to split later) — see the "One centerline per
> direction, no left/right split" note below for why no separate left/right-lane concept was
> added on top of this.
- [x] P2.1 (superseded — see design-change note above) `ops_centerline.py`:
      `RKA_OT_centerline_from_vertex_group` (active mesh's `lanedata` group → one `lanecl_*` Poly
      curve per edge-connected tagged region, linked into the same collection as the source mesh
      so it travels with every instance). Verified headless: register → run on
      `kit_intersection_4_way_2_lane_straight_2_lane_side` → 8 curves created, 2 points each,
      `loop=False`, matching the source tagging exactly.
- [ ] P2.2 `RKA_OT_add_curb` (snap-attaches a `kit_side_*` curb Collection instance flush to the
      selected lane tile's left/right edge, offset from its bounding box).
- [ ] P2.3 Finish tagging `lanedata` for the remaining pieces/paths in `lane_kit.blend`
      (in progress by hand — 3-way pieces not started yet; 4-way currently has 8 short approach
      stubs, not yet full through-intersection + turn paths) — **your work in Blender, not a
      script step**.
- [ ] P2.4 Verify: curb attaches flush (zero gap) on both edges of a straight run; visual check
      that each kit piece's centerline(s) look correct in the 3D viewport.

> **One centerline per direction, no left/right split (decided 2026-07-23):** the old
> `road_graph.py` model authored ONE curve per multi-lane road cross-section and *derived* the
> per-direction/per-lane offset routes from it (lane count + oneway metadata → generated offset
> curves). This mesh-kit system doesn't need that derivation step: each hand-modeled lane strip
> (a `Kit_LaneStraight5` tile, or one tagged region inside an intersection mesh) is already
> physically one direction of travel, so its extracted `lanecl_*` curve already **is** a
> single-direction lane — a two-way street is built by placing two directional lane tiles
> side-by-side (or tagging two separate regions in one intersection mesh), not by splitting one
> shared centerline. `RKA_CurveSettings.oneway` (already registered, P1.2) is just metadata on an
> already-single-direction curve (true almost always; false only for the rare shared-strip case,
> e.g. a one-lane road used both ways). **Not adding** a separate "right lane / left lane" concept
> at the kit-piece level — it would duplicate information the mesh tagging already encodes.
> Geometry-Nodes-driven lane derivation from a single shared line (the thing being asked about)
> is exactly the pattern being retired with `road_graph.py`; don't reintroduce it here.

## Phase 3 — Connectivity, validation, export sidecar

- [ ] P3.1 New pure-Python (no bpy) module `lib/lane_kit.py`, same convention as
      `road_graph.py`: `LaneCurve(name, pts, lane_width, oneway, cls, loop, end_behavior)`;
      `cluster_endpoints(curves, eps=1.0)` (proximity-groups nearby endpoints — conceptually
      like `road_graph.from_curves`'s `CONNECT_EPS` clustering but standalone, and never
      mutates/splits curve topology); `classify_clusters(clusters)` → unambiguous (auto-link)
      vs ambiguous (needs manual review); `validate(curves, links)` → dangling endpoints,
      direction conflicts, disconnected islands (union-find); `export(curves, links, path)`
      (reuses `save_roads._spline_points`-style world-space sampling — consider relocating
      `_spline_points` into a shared module both import); `if __name__ == "__main__":
      self_test()` (synthetic straight+curb+T-junction scenario).
- [ ] P3.2 Addon operators: `ops_connect.py` (`RKA_OT_auto_connect`, `RKA_OT_review_connections`
      — UIList of ambiguous clusters with click-to-select + Link/Unlink; manual overrides stored
      as `(endpoint_a_key, endpoint_b_key)` pairs in a JSON-encoded custom prop on a
      `RKA_ConnectivityStore` Empty in the district's `MANUAL` collection — auto-detected links
      are never stored, only manual overrides), `ops_validate.py` (`RKA_OT_validate`),
      `overlay_draw.py` (viewport overlay: curve polylines colored by direction, endpoint dots
      green/yellow/red for linked/ambiguous/dangling), `ops_export.py`
      (`RKA_OT_export_lanekit`).
- [ ] P3.3 `tools/save_lane_kit.py` (new, headless: `blender <district>.blend --background
      --python tools/save_lane_kit.py`) — collects `lanecl_*` curves (walking
      `depsgraph.object_instances` to resolve collection-instance duplis), applies manual
      overrides, validates, exports `districts/<piece>.lanekit.json`:
      ```json
      {
        "piece": "District_X",
        "lanes": [{"name": "lanecl_X_12", "points": [[x,y,z], ...], "lane_width": 3.0,
                   "oneway": true, "class": "local", "loop": false, "end_behavior": "CHAIN"}],
        "links": [{"from": "lanecl_X_12", "from_end": "end", "to": "lanecl_X_13",
                   "to_end": "start", "auto": true}],
        "warnings": [{"type": "dangling", "lane": "lanecl_X_9", "end": "start"}]
      }
      ```
- [ ] P3.4 Export flow: `export_world.py` keeps glTF-extras only for small scalar metas
      (unchanged); the lane/connectivity data ships as a **parallel JSON artifact**, copied
      alongside the exported `.glb` into
      `src/main/resources/com/openworld/world/districts/District_X.lanekit.json`.
- [ ] P3.5 Verify: build a small multi-piece test layout (straight → 4-way intersection →
      straight, plus a T off a side arm) via the addon; run `RKA_OT_validate` → zero
      dangling/island warnings; export and confirm `District_lanekittest.lanekit.json` is
      human-readable/git-diffable like `roads.json`.

## Phase 4 — Godot-side Path3D consumption (deferred until Phase 1-3 proven)

- [ ] P4.1 New `com/openworld/world/PathLaneRoute.java` (new class, **not** an in-place
      `VehicleRoute` rewrite — old baked `.tscn` files must keep working forever): `Node3D`
      holding a native `Path3D` child with `Curve3D` populated from sidecar points
      (`addPoint(pos, ZERO, ZERO)`). Preserves the exact surface
      `VehicleAIController`/`LaneGraph`/`IntersectionZone` depend on: `loop`,
      `nextRoutes`/`nextWeights`, `turn`, `approach`, `laneOffset`, `laneWidth`, `endBehavior`,
      `returnRoute`, `startPoint()`/`endPoint()`, tangents, `total()`, `pointAtLength(s)`,
      `lengthAtNearest(...)`, `pickNextRoute()`, `resolveRoute()`.
- [ ] P4.2 Replace `VehicleRoute.java`'s hand-rolled Catmull-Rom + arc-length arrays
      (`ensureBaked`, `catmull`, `cum[]`, lines 154-240) — in `PathLaneRoute`, use
      `Curve3D.getBakedLength()` for `total()`, `Curve3D.sampleBaked()` for `pointAtLength(s)`,
      `Curve3D.getClosestOffset()` (with a local-window fallback scan over `getBakedPoints()`
      to preserve `lengthAtNearest`'s corner-snap-avoidance). Lane offset still needs custom
      code but derives from `getBakedPoints()` instead of hand-subdividing.
- [ ] P4.3 Extract a small `Lane` interface (`startPoint/endPoint/loop/pickNextRoute/...`)
      implemented by both `VehicleRoute` and `PathLaneRoute`, so
      `LaneGraph`/`IntersectionZone`/`VehicleAIController` call sites work against either
      transparently.
- [ ] P4.4 `WorldBaker.java`: new `lanepath_<name>` marker-prefix branch (parallel to `lane_`,
      ~line 172-195) whose `_ready`-time job is loading sampled points from the district's
      `.lanekit.json` (via `godot.api.Json.parseString` → `Dictionary` walk) and building a
      `PathLaneRoute`; new `buildPathRoute()` method parallel to `buildRoute()`; `links[]` →
      `nextRoutes`/`nextWeights` wiring (default straight-biased weight when unspecified —
      decide this in `lib/lane_kit.py`'s export, keeping graph-shape decisions in the authoring
      tool).
- [ ] P4.5 `LaneGraph.java`/`IntersectionZone.java`: no logic change, just interface-typed call
      sites.
- [ ] P4.6 Note (not built now): sidecar data is flat/keyed/world-space, naturally compatible
      with `AUTHORING_GUIDE.md` §11's "always-resident manifest for cross-district A*" goal
      without needing `road_graph.py`'s graph classes — annotate §11 with this once P4 lands.
- [ ] P4.7 Verify: bake `District_lanekittest` via `tools/build_piece.sh`; load in
      `SoloPiece.tscn`; F4 spawns cars that follow `Path3D` lanes, turn correctly at the
      intersection, yield via unmodified `IntersectionZone`; confirm `LaneGraph` picks correct
      outgoing lanes at the junction.

## Phase 5 — Pilot migration of one real placeholder district (deferred)

- [ ] P5.1 Pick one placeholder district; author its full layout with the (by-then mature)
      addon + kit; export, bake (stem form, not added to `build_district.py`'s CONFIG — same
      precedent as `District_kitdemo_9_9`), walk-test.
- [ ] P5.2 Old/new pipelines coexist per-district automatically: `WorldBaker` picks the path
      based on which sidecar exists next to the district's export (`roads.json`-derived markers
      → old `buildRoute`; `.lanekit.json` → new `buildPathRoute`).
- [ ] P5.3 Verify: side-by-side walk-test against the old placeholder (traffic density/behavior
      parity via `WorldZoneManager.debugLog`'s routed/moving counts per §7). Once satisfied,
      write it up as the worked example in a new `AUTHORING_GUIDE.md` §7 subsection, the way
      `District_kitdemo_9_9` is today.

---

## Critical files

- `assets/world_source/lib/kit_common.py` (reuse `link_collections`, `instance_collection`, `colonly*`)
- `assets/world_source/lib/road_graph.py` (reference only — do not extend)
- `assets/world_source/tools/save_roads.py` (`_spline_points` reused, not forked)
- `assets/world_source/tools/gen_roads_only.py` (structural template for `save_lane_kit.py`)
- `assets/world_source/AUTHORING_GUIDE.md` (§2 regen contract, §7/§11 to extend later)
- `PLAN_WORLD_AUTHORING.md` (Phase A flagged superseded)
- `src/main/java/com/openworld/world/WorldBaker.java`, `VehicleRoute.java`, `LaneGraph.java`,
  `IntersectionZone.java` (Phase 4)
- `assets/world_source/districts/District_manual_1.blend` (source material for Phase 1)

## Docs & memory (cross-cutting, after each phase lands)

- [ ] `AUTHORING_GUIDE.md`: new §7 subsection for the lane-kit workflow (mirrors the existing
      `gen_roads_only.py`/kitdemo write-up); §11 annotation once Phase 4 lands.
- [ ] Memory: update/add `project_district_authoring` and a new `project_lane_kit` entry once
      Phase 1 lands (addon location, kit blend location, sidecar format).
