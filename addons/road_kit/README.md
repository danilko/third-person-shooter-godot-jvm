# Road Kit (Godot editor plugin)

Roads are authored here, solved by `blender/tools/roadkit_cli.py` (plain python3) and meshed by headless
Blender (`blender/tools/build_roads_piece.sh`). The `.roads.json` record next to the network is the source
of truth; the `RoadKitNetwork → RoadKitRoad → RoadKitPoint` nodes are its editable view. Design of record:
`CLAUDE.md` "Road Kit — option B". Editor tooling only — nothing here runs in the game.

## How to edit roads

1. **Open the scene** that holds the `RoadKitNetwork` (e.g. `world/DebugWorld.tscn` → `DebugRoads`) and
   select it. The **Road Kit** dock is on the right.
2. **Load Record** — the network node is empty in the saved scene; this reads `<network>.roads.json`
   into point nodes and draws the solver's centrelines.
3. **Edit.** Move or rotate points with the ordinary gizmo (a point's local −Z is the travel direction),
   or use the dock: New Road, Extend Road (either end), Insert Point After, Delete Point, Connect
   (SEGMENT / JUNCTION / AUX), Make Intersection, Make Ramp, Branch Ramp Here (from any station; lanes,
   carriageway, entrance), Merge Points, Split To New Road, Select Junction (then move/rotate the whole
   crossing), Follow Road (Auto), Apply Cross-Section (tick the groups; the point selected LAST is the
   source). Every gesture is one undo step.
   **Rotating a point bends its road**: an AUTO point you turn becomes MANUAL and its facing shapes the
   curve; its gizmo handles (drag along the arrow) set `handle_in` / `handle_out`. Follow Road (Auto)
   hands the facing back to the tool. **Repair:** Tidy Roads, Renumber Roads (chain order from the
   links), Repair Links.
   **Refresh Preview** redraws after a gizmo drag (gestures redraw by themselves). With ZoneMarkers in the
   scene the centrelines are coloured by the zone each run streams with; white = no zone (the resident
   piece, which nothing streams), an orange strip above = past that zone's load radius, magenta = a lane
   whose successor lives in the other zone's piece. Each marker's box and load/unload rings are drawn too.
4. **Validate** — the kit's gate. Click a finding to select its point. A build refuses to run on errors.
   **Flow Report** lists broken / misjoined / unreached lanes and ramp orphans in the exported lane graph.
5. **Build Piece** — samples the Terrain3D ground (stations and a 2 m grid under the whole network, so
   bridges and piers stand on the real ground), writes `<network>.zones.json` from the markers, runs the
   whole build on a thread (python3 lanes → Blender meshes → export + bake, ~30 s for DebugRoads) and
   wires each built piece into its ZoneMarker's `Zone` in one undo step. Save the scene afterwards.
   **Draft Surface** (on by default) draws the solver's tarmac, pads, gores, footways and kerb lines on
   every refresh — exactly what Build will sweep, so a junction's pad, setbacks and fillets show while you
   tweak. It wears the kit's own materials, taken off the built pieces (Preview Pieces); before any build
   it is the engine's default grey.
6. **Preview Pieces** — tick it to see the BUILT roads (tarmac, kerbs, piers) placed exactly where
   `ZoneManager` will stream them. It is never saved and refreshes itself after each Build.
7. **Stamp Terrain** writes the roads into the Terrain3D height field (cut and fill, derived from the
   natural ground the Build sampled — press it again any time, it re-derives; **Restore Terrain** puts the
   natural ground back). Bridges keep open ground under them.
8. **Play the scene** to walk the zones: the runtime `ZoneMarker` box is green while its zone is loaded and
   cyan while idle.

Save Record writes the record without building. Auto Setback solves junction stop lines — press it once;
it is not idempotent (W17).

## Headless

```bash
G=/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64
W=res://src/main/resources/com/openworld/world/DebugWorld.tscn
$G --headless --path . --script tools/godot/write_roadkit_zones.gd  -- $W DebugRoads
$G --headless --path . --script tools/godot/write_roadkit_ground.gd -- $W DebugRoads
blender/tools/build_roads_piece.sh assets/world_source/pieces/DebugRoads.roads.json Roads_DebugRoads \
    assets/world_source/pieces/DebugRoads.zones.json assets/world_source/pieces/DebugRoads.ground.json
$G --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- $W DebugRoads   # [--restore]
python3 blender/tools/roadkit_cli.py flow assets/world_source/pieces/DebugRoads.roads.json
```

Gate: `blender/tools/check_roads.sh` runs the kit's tests and every plugin test under `tools/godot/`
(`test_roadkit_*`, `probe_road_ground`, `probe_road_stamp`); the runtime probes `probe_road_zones.gd` and
`probe_traffic_spawn.gd` run with `--fixed-fps 60`.
