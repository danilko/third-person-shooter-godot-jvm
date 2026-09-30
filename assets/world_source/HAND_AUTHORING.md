# Hand-authoring the island: roads, lanes, buildings, terrain

The island was GENERATED: `tools/island_world.sh` runs land → layout → terrain → roads → sites → buildings → ground,
and each stage rewrites its outputs from scratch. When the overall generation is finished, the world is handed over
to hand work: level designers and artists edit it in place, and the generators stop running over it. This guide says
**where each thing is edited, and what has to be re-run afterwards**.

> **Read this first — the handover is not done yet (PLAN.md NEXT, item 12 -- the last piece).** Until it is, `tools/island_world.sh` and
> `tools/island_layout.py` still OWN the island's roads and buildings, and anything edited in their outputs is lost
> the next time they run. Each section below says what works today and what changes at the handover. Everything
> about building TYPES, interiors, stations and DebugWorld is already hand-owned and safe to edit.

## 1. What owns what

| thing | source of truth (edit this) | editor | re-run afterwards |
|---|---|---|---|
| island roads, lanes, junctions, ramps | `assets/world_source/pieces/IslandRoads.roads.json` via `World.tscn` → `IslandRoads` | Godot, Road Kit dock | Build Piece, then §3's downstream list |
| (until the handover) the arterial INPUT | `IslandRoads.arterials.roads.json` via `World.tscn` → `IslandRoadsArterials` (hidden) | Godot, Road Kit dock | `tools/island_world.sh --from layout` |
| rail lines | `IslandRail.roads.json` via `World.tscn` → `IslandRail` | Godot, Road Kit dock | rail build, then roads (the rail is stamped FIRST) |
| DebugWorld roads | `DebugRoads.roads.json` via `DebugWorld.tscn` → `DebugRoads` | Godot, Road Kit dock | Build Piece, Stamp Terrain (already hand-owned) |
| where each town building stands | `assets/world_source/buildings/IslandBuildings.json` | text editor (today) | `python3 tools/island_buildings.py write` |
| unique sites (landmarks, stations, container terminal, air base, …) | `IslandSites.json` (frozen x, y, yaw) | text editor | `python3 tools/island_sites.py` |
| civic / mission plots (police, bank, hospital, safe houses, …) | `IslandCivicSites.json` (frozen) | text editor, or `island_civic_sites.py --resite=<id>` | `island_buildings.py write` |
| ground a generator must leave empty | `tools/island_plan.py` `RESERVES` (Godot boxes) | text editor | re-derive (until the handover) |
| a building TYPE (shape, doors, interior) | `kits/<kit>/<kit>.blend` + `buildings/building_types.json` | Blender + text | `tools/building_kit/build_buildings.sh` |
| an enterable interior | `kits/interiors/<Id>.blend` (Empties: `DOOR_`, `EXIT_`, `LIFT_`, `MARK_*`) | Blender | `tools/building_kit/build_interiors_only.sh <Id>` |
| a station | `kits/stations/*.blend` (generated once, then hand-owned) | Blender | `tools/building_kit/build_stations.sh` |
| terrain shape | `assets/world_source/terrain/island_natural.f32` (the NATURAL ground) | Godot, Terrain3D tools (see §5) | re-stamp roads and rail, then the ground stage |
| street furniture, signals, lamps, trees | derived from each road's fields + `kits/road_kit/furniture.json` | Road Kit Inspector / text | Build Piece |

Scene files never store a road or a point: the `.roads.json` record is the only copy, and **saving the scene saves the
record** (atomically, only if it changed). The record is safe to commit with the editor open.

## 2. Roads and lanes in the Godot editor

Open `src/main/resources/com/openworld/world/World.tscn` (or `DebugWorld.tscn`). The **Road Kit** dock sits on the
right, and the full editing how-to is `addons/road_kit/README.md`. In short:

* **Select**: click a point (a cross in the viewport) or a road's centreline. Alt-click selects a whole junction.
* **Lanes**:
  * a point's two side handles set `lanes_fwd` / `lanes_bwd` (drag one sideways past a lane width), or type them in
    the Inspector (`Road Point`);
  * to change a whole road at once, select a station and use **Apply Cross-Section**, or pick a **Road Type**
    preset (`expressway`, `trunk`, `arterial`, `block`, `lane`, `farm`, `coast`, `rail`);
  * an AUX (acceleration or deceleration) lane is `aux_fwd` / `aux_bwd` on the stations it spans;
  * lane width, median, footways, kerbs and barriers come from the ROAD's base section, not the point. Change them on
    the road node.
* **Add a road**: *Draw Road* in the viewport toolbar (click the ground for each station, Esc to finish), then
  *Connect* its end to another road's point to make a junction. *Connect* on two ends of one road joins them.
* **Add a ramp**: *Branch Ramp Here* on a mainline station (lanes, carriageway, entrance). Keep-left decides the
  side, and one ramp per carriageway per run.
* **Move / bend**: drag a point; rotate it to bend its road (it becomes MANUAL). A junction mouth has a stop-line
  handle and a fillet handle, and the junction's centre handles move or rotate the whole crossing.
* **Check**: *Validate* (the gate; a build refuses to run on errors) and *Flow Report* (broken, misjoined or
  unreached lanes). A lane is only real to traffic when *Flow Report* is clean.
* **Build**: *Build Piece (changed zones)* rebuilds only the streamed road pieces your edit actually changed, then
  save the scene. *Preview Pieces* shows the built result in place.

**Today, on the island:** `IslandRoads` is marked `generated`, so the dock REFUSES to save an edit over it and names
the input to edit instead. Edit `IslandRoadsArterials` (make it visible in the Scene dock) for arterial changes and
re-run `tools/island_world.sh --from layout`. Block streets, the expressway, ramps and turnarounds are regenerated by
that run. **After the handover:** untick `generated` on `IslandRoads` and edit it directly; the layout run is then
retired for the island.

## 3. After a road or lane edit: the downstream list

The dock's Build rebuilds the road pieces. The rest of the world reads the roads, so after an island road edit, run:

1. **Terrain**:
   * DebugWorld: *Stamp Terrain* in the dock.
   * Island: the block ground (`island_ground.py`) sits on top of the road stamp, and the dock's Stamp refuses while
     `urban_paint.marker` exists. Run `tools/island_world.sh --from terrain` instead; it re-lays natural ground,
     re-stamps rail then roads, and re-runs sites, buildings and ground. Unchanged road pieces are skipped.
2. **Traffic zones**: `python3 tools/island_traffic_zones.py` (spawn clusters from the lane entries).
3. **Map and GPS**: `godot --headless --path . --script tools/godot/bake_road_map.gd -- --world=island`.
4. **Sidewalk crowd lines**: `python3 tools/island_buildings.py sidewalks`.
5. **No building on a road**: `python3 tools/island_buildings.py roads` (and re-site a civic plot the edit cut:
   `python3 tools/island_civic_sites.py --check`, then `--resite=<id> --avoid-streets`).
6. **Gates**: `probe_road_clear.gd`, `probe_road_ground.gd`, `probe_gps_route.gd -- --world=island`,
   `probe_traffic_spawn.gd -- --world=island` (CLAUDE.md "Standard gates").

`--from terrain` already runs steps 2–5; the list is for when you run pieces by hand.

## 4. Buildings

* **Move, turn, retype or delete one town building**:
  1. Find it in `IslandBuildings.json` (`buildings[]`: `type`, `pos` Godot x/y/z, `yaw` degrees, `lot`, `tone`,
     `key`). Its postal code (Ctrl+F9 in game) helps you locate it.
  2. Edit or remove the entry.
  3. Run `python3 tools/island_buildings.py write` (no terrain dump needed). Then `island_buildings.py lots --check`
     and `roads`.

  **Today** a re-derive (`island_world.sh`'s buildings stage runs `derive`) throws hand edits away. **After the
  handover** the record is hand-owned and `derive` is retired for the island.
* **Keep ground free** (a plaza, a future site): add a box to `tools/island_plan.py` `RESERVES`. The street planner and
  the building placer both stay out of it.
* **Place a unique building by hand, in Godot**:
  1. In `World.tscn`, add your own holder node (e.g. `HandPlaced`). Never use one of the generators' holders:
     `SiteZones`, `BuildingZones`, `PedZones`, `TrafficZones`, `RoadZones`, `RailZones` are rewritten by name.
  2. Under it, add a `ZoneMarker` whose `Zone` has `geometry_path` = the building scene (`…/world/buildings/<Id>.tscn`,
     or `<Id>_Open.tscn` locked for a mission, or `<Id>_Shop.tscn` open), `geometry_world_placed` on,
     `geometry_world_transform` where it stands, and load / unload radii.
  3. Reserve its ground (above) so no generated building lands on it.
* **Move a unique site or a civic plot**: edit its `x`, `y`, `yaw` in `IslandSites.json` / `IslandCivicSites.json`.
  These are RECORD axes: record y = −Godot z. Then run `python3 tools/island_sites.py` (only the height is
  re-sampled) or `island_buildings.py write`.
* **A new building type, or a change to one**: shape in `kits/<kit>/<kit>.blend`, the row in
  `buildings/building_types.json`, then `tools/building_kit/build_buildings.sh` (it probes every scene;
  `ACCEPT_BOUNDS=1` for a deliberate size change). See `assets/world_source/buildings/README.md`.
* **An enterable interior**: `kits/interiors/<Id>.blend` (read `kits/interiors/ARTIST_NOTES.md`). Mission markers are
  `MARK_<kind>_` Empties (weapon / spawn / cover / objective / vehicle). Rebuild fast with
  `tools/building_kit/build_interiors_only.sh <Id>`.

## 5. Terrain

Sculpt with the Terrain3D tools in the editor, but only on the NATURAL ground. The island's terrain is the natural
ground plus the rail and road stamps plus the block ground, and any stamp re-derives from the natural ground. So:

1. Restore to natural ground: `tools/island_world.sh --only terrain` lays `terrain/island_natural.f32` down.
2. Sculpt.
3. Dump the result into `island_natural.f32` (`tools/godot/dump_height_grid.gd -- <out> -2304 -2304 2305 2305 2`:
   2305 x 2305 vertices at 2 m, Godot axes, float32).
4. Run `tools/island_world.sh --from terrain`.

A sculpt made on top of the stamped terrain is lost on the next stamp. Painting is the same: `paint_terrain.gd` refuses
while `urban_paint.marker` exists, and the block and soil paint come from `island_ground.py`.

## 6. Checks before you commit

`./gradlew build test`, `blender/tools/check_roads.sh`, `python3 tools/island_layout.py --check` (roads),
`tools/building_kit/build_buildings.sh` (building types), and the island probes listed in §3. Commit the record, the
built pieces and the manifest (`*.build.json`) together.
