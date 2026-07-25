# Working plan — Minimal Master + Divided-Road Demo + Curve-Driven Road Kit + World Overview

> **Progress tracker for a multi-session effort** (branch `issue-34`). Mark items `[x]` as they
> land so a fresh session can resume exactly where this one stopped. Approved plan 2026-07-18;
> execution order **D → B → C → A**. Companion docs: `assets/world_source/AUTHORING_GUIDE.md`
> (conventions of record), PLAN.md §R (roads v2 roadmap).

## Context (why)

- An unexplained **"extra collision layer"** is felt in-game. Verified: the baked master
  (`src/main/resources/com/openworld/world/master/World_master.tscn`) contains exactly **15
  invisible solid bodies** — 14 `ArtDeck` strips + 1 world-spanning `SafetyFloor` slab (top
  Z=−2.5) — all on default collision layer 1, overlapping streamed district ground at seams.
  They are the only StaticBody3D in the master and the prime suspects.
- Decisions (user-approved): master goes **minimal by default** (region markers + landmark
  slots + water only; `--full` restores lanes/deck/floor); ambient traffic need not survive
  minimal mode (graceful degradation only); ground continuity moves to the districts (slight
  DEM clip overlap + **manual** seam smoothing — elevations differ, auto-align impossible);
  overlays (Rainbow Bridge) **stay separate files**, never cut into districts; road kit is
  **curve-driven geometry nodes** (the `road_*` centerline generates the visual — no snapping
  needed); curve connection contract stays proximity-based (2 m endpoint clustering, no
  physical curve joins); future vehicle no-go "air walls" = `-colonly` boxes in `MANUAL`
  (docs only).
- District vs zone: currently 1:1 by convenience (one `region_` marker per district carries
  both streaming geometry and gameplay flavor). A `WorldZoneMarker` with no geometry is
  already a pure gameplay zone — document, no code.

All paths relative to `assets/world_source/` unless prefixed `src/`.

---

## D. Minimal master build (default) + collision diagnostics

- [x] D1 `towns/build_world.py`: `parse_args()` after `--`: `--full` (lanes+deck+floor = old
      behavior) + granular `--with-lanes` / `--with-deck` / `--with-floor` for A/B bisection.
      **Default = minimal** (all off). Gate `asm.lay_road_graph(backbone_graph(),…)` (~L263),
      `backbone_deck` (~L266), `safety_floor` (~L267); zero skipped counts; add
      `mode=minimal|full` to the `WORLD:` summary print.
- [x] D2 `traffic_route` meta (~L252–254): sidecar districts keep `"<stem>__"`; `"art_"`
      fallback only when lanes built; else `traffic_route=""` AND `traffic_count=0`.
      (Verified graceful: `WorldBaker.buildZone` skips VehicleSpawnConfig on empty route/0
      count; `WorldZoneManager.findRoute` null-safe.)
- [x] D3 `tools/build_world.sh`: pass `"$@"` through to the Blender call; usage comment.
- [x] D4 `src/main/java/com/openworld/debug/DebugHarness.java`: `--dump-collision` user arg
      (parse next to `--auto-walk`, ~L504) + **F9** key → walk tree, print every
      StaticBody3D/CollisionShape3D: name path, global pos, shape type + AABB,
      collision_layer/mask.
- [x] D5 `lib/plateau_import.py`: module constant `GROUND_OVERLAP = 2.0` m applied to the
      **terrain mesh clip only** (`edge_half + GROUND_OVERLAP` at the `_clip_tri_to_square`
      call, ~L176–189) — NOT to building/bridge `edge_margin` perimeter-skip.
- [x] D6 Rebuild master minimal (`tools/build_world.sh`) + verify (see Verification 3/4).

## B. `median` prop + standalone road generator + kitdemo district

- [x] B1 `lib/road_graph.py`: `Edge`/`add_edge` gain `median=0.0`;
      `_lane_offset_from_center(li, lanes, median)` → `-(median/2 + (lanes-li-0.5)*LANE_W)`;
      `generate()` passes `e.median`; `_junction_radius` → metres incl. median
      (`(lanes_f+lanes_r)*LANE_W + median`); `from_curves` reads `median` prop; self-test:
      new median case (F0/R0 at ±(median/2+1.75)) + legacy cases unchanged at median 0.
- [x] B2 `tools/save_roads.py`: export `"median"` key; wrap top-level `main()` in
      `if __name__ == "__main__"` (so it's importable).
- [x] B3 `towns/districts/build_district.py`: `import_roads_src` stamps `ob["median"]`;
      `emit_authored_roads` passes it through.
- [x] B4 `tools/gen_roads_only.py` (new ~90 lines): for hand-authored blends w/o CONFIG —
      collect local `road_*` curves (reuse `save_roads._spline_points`), wipe only
      `lane_<piece>__*`/`intersection_<piece>__*` from local MARKERS,
      `asm.lay_road_graph(rgm.from_curves(...))`, run `save_roads.main()`, save.
- [x] B5 `tools/build_kitdemo.py` (new, reproducible generator) →
      `districts/District_kitdemo_9_9.blend`: MANUAL ground slab ±160 m top z=0 (+colonly),
      visual ribbons, median bumps (3 m model 2 / 3.5 m model 3, +colonly); ROADS_SRC curves:
      `road_plain` (lanes=1, y=+60), `road_dual_e`/`road_dual_w` (oneway pair y=±3, opposite
      order → two separate T-nodes), `road_median` (lanes=1 median=3.5, y=−60), `road_cross`
      (N–S x=0, interior verts at each crossing). Ends by running B4 in-process.
- [x] B6 Optional: `--spawn-all-routes` headless arg in DebugHarness (scriptable F4).
- [x] B7 Bake `tools/build_piece.sh District_kitdemo_9_9` + SoloPiece F4 verify (Verification 5).

## C. `tools/link_world.py` → persistent `world_overview.blend`

- [x] C1 New tool (model: `build_debug_preview.py` L69–146 + `link_neighbors.py` elev math):
      link each existing district's `STREET`(+`MANUAL`) as ONE collection-instance empty
      `Piece_<gx>_<gy>` at `world_grid.district_center(gx,gy)`, **Z = `elev_at(gx,gy)`**;
      skip-warn missing blends; link master `MARKERS` (+`ARTDECK` if present) at origin; link
      each `overlays/Overlay_*.blend` content collection at origin; sun + top ortho camera;
      `asm.wipe_scene()` first (re-runs fully regenerate — file holds only links/empties);
      save `world_overview.blend`; all local collection lookups via `kc.get_coll`.
- [x] C2 Verify (Verification 6): 36 empties at correct elev; edit+save a district source →
      reopen overview → edit visible. Moving `Piece_*` empties = viz-only (runtime positions
      from `world_grid.district_center` — single source of truth).

## A. Curve-driven GN road kit

> **Superseded (2026-07-22).** This phase (procedural GN sweep from a `road_graph.py`-derived
> centerline) is replaced by the mesh-first road-kit approach tracked in `road_blender_godot.md`
> at the repo root — kit pieces are authored as mesh with paired hand-drawn centerline curves,
> not swept from an abstract graph. Left unchecked below for history; do not resume A1-A5.

- [ ] A1 `lib/kit_common.py` `make_road_profile_group()`: node group `GN_RoadProfile` —
      inputs Curve(Object), LanesF, LanesR, Median, LaneW(3.5), materials; Curve-to-Mesh quad
      width `(F+R)*LaneW+Median` at +0.02 z; median bump (Median × 0.25) via Switch; real
      geometry only (exports under the realize pass + `export_apply=True`; precedent:
      `make_barrier_profile_group`).
- [ ] A2 Host object convention: `roadvis_<name>` mesh in an exported collection carries the
      modifier + custom prop `road_ref="<curve name>"`; **bind by name always** (curves are
      rebuilt each regen). Generated districts: `emit_road_visuals(data)` in
      `build_district.py` after `import_roads_src` (hosts → STREET). Hand blends:
      `tools/road_visual_bind.py` (create/update host per local `road_*` curve, rebind).
- [ ] A3 Collision: ribbon none; median bump `kc.colonly_swept(..., median/2, z0=0, z1=0.25)`.
- [ ] A4 Junction pads: rerun `rgm.from_curves+generate()`, one flat pad per `JunctionOut`
      at +0.03 z (kills ribbon z-fighting).
- [ ] A5 Retrofit kitdemo ribbons to GN; re-bake + F4.

## Docs & memory (cross-cutting, after each workstream lands)

- [ ] AUTHORING_GUIDE: §3 build flags; §4 minimal-master caveat + link_world + ground
      overlap/manual seam smoothing + `-colonly` MANUAL vehicle-blocker convention +
      district-vs-zone note; §7 median prop built + `gen_roads_only.py` loop + kitdemo worked
      example + GN road-kit convention.
- [ ] `BLENDER_CONVENTIONS.md`: `roadvis_`/`road_ref` (+ any new reserved names).
- [ ] Memory: update `project_roads_v2` / `project_district_authoring`.

## Verification

1. [x] `python3 lib/road_graph.py` self-test passes incl. median assertions.
2. [x] Round-trip regression: `build_piece.sh industry_5_1` → same lane/connector/junction
       counts; re-save sidecar → git diff shows only added `"median": 0.0` keys.
3. [x] Minimal master default: `tools/build_world.sh` → `mode=minimal`, lanes/deck/floor=0;
       `grep -c StaticBody3D World_master.tscn` = 0; Marker3D collapses from ~8472. Headless
       `WorldMasterDebug --auto-walk`: zones stream, sidecar district (industry_5_1) still
       spawns traffic, others none, no errors. `--dump-collision` prints inventory.
4. [x] `tools/build_world.sh --full` reproduces old counts (15 StaticBody3D, ~8472 Marker3D).
5. [x] Kitdemo: bake + SoloPiece F4 — cars on all routes; model 1 lanes ±1.75 m; model 2 two
       T-nodes + carriageways clear bump; model 3 lanes ±3.5 m clear bump; connectors work.
6. [x] Overview blend checks (C2).
