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
| Empty named `waypoint_<route>_<n>` | NavAgent waypoint | I3 `VehicleAIController` |
| Empty named `zonetrigger_<beatId>` | `ZoneTrigger` (`Area3D`) | F3 |
| Mesh suffixed `-col` | `CollisionShape3D` | all world geometry |

A Godot `EditorScenePostImport` script should walk each imported scene and
convert these by name/prefix into the right node + script attachment. Renaming
hundreds of already-placed objects after the fact is exactly the retrofit cost
this document exists to avoid — lock the prefix scheme down first.

## Zone chunking

- `WorldZoneManager` (PLAN.md E1) streams geometry per `WorldZone` based on
  `loadRadius` (200 m) / `unloadRadius` (350 m, hysteresis). Author and export
  geometry in chunks matching the chosen zone-grid size — **not** as one
  monolithic scene — or E1 has nothing to stream in/out.
- Decide the zone-grid size *before* any real geometry is modeled; it constrains
  border layout, road continuity (I3), and region-transition placement (I4).

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
