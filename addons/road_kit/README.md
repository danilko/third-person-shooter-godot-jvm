# Road Kit (Godot editor plugin)

Roads are authored here, solved by `blender/tools/roadkit_cli.py` (plain python3) and meshed by headless
Blender (`blender/tools/build_roads_piece.sh`). The `.roads.json` record next to the network is the source
of truth; the `RoadKitNetwork → RoadKitRoad → RoadKitPoint` nodes are its editable view. Design of record:
`CLAUDE.md` "Road Kit — option B". Editor tooling only — nothing here runs in the game.

## How to edit roads

1. **Open the scene** that holds the `RoadKitNetwork` (e.g. `world/DebugWorld.tscn` → `DebugRoads`). Its
   points are loaded from `<network>.roads.json` as the scene opens — they are in the Scene dock under each
   road, and every point is drawn as a cross you can **click in the viewport** (yellow = junction mouth,
   cyan = ramp, red = terminus). The selected point is labelled with its road, index, role and uid. The
   **Road Kit** dock is on the right.
   **Names say what a point is.** `<road>_pNNN` is its place along the road, and a tag follows:
   `_jct` a junction mouth (a stop line of a pad), `_ramp` a ramp's mouth, `_aux` a mainline station a
   ramp leaves from, `_end` a road end that joins nothing; a plain station along the road has no tag. Hover
   a point in the Scene dock for its role and every link. Each junction also has a yellow label floating
   over it listing its mouths — the mouths of ONE junction are usually 15–30 m apart, one per road.
   **Viewport tools** — the **Road Kit:** buttons in the 3D viewport's toolbar. *Select*: click a road's
   centreline to select the road, Alt-click a junction mouth to select the whole junction. *Draw Road*:
   click on the ground to start, click again for each station, Esc or right-click to finish (stations land
   on the natural ground). *Insert*: click a centreline to add a station there. *Delete*: click a point.
   *Connect*: click two points — two ends of one road join; points of two roads make a junction (or a ramp,
   when one is a mainline station with aux lanes). Every click is one undo step. *Off* hands the viewport
   back to the editor.
2. **Saving the scene saves the record.** The scene file never stores a road or a point — the record is the
   only copy — so there is nothing to keep in sync. (Load Record re-reads the file, discarding unsaved
   edits.)
3. **Edit.** Move or rotate points with the ordinary gizmo (a point's local −Z is the travel direction) and
   edit a point's own fields in the Inspector (`Road Point`: lanes, widths, kerbs, fillet radius, setback
   lock, tangent mode, handles). The overlay and draft surface **follow the drag** (the solver runs off the
   editor's thread, so the editor never waits for it). When you
   release a point you dragged sideways it settles onto the ground at its new place, keeping its height
   above the ground (a bridge or pier station keeps the height you gave it), and a junction mouth you moved
   is marked `setback_locked` so Auto Setback leaves it.
   **Handles** (select a point): the two small handles either side of it set its **lane counts** — drag
   one sideways past a lane width. On a **junction mouth** there are four more: the one above the point
   slides the **stop line** along its road (and locks it), the one beside it sets the corner **fillet**
   radius, and the pair at the junction's centre **moves** and **rotates** the whole crossing (every
   mouth together; nothing is turned into MANUAL). Every drag is one undo step.
   **Move a whole road** by selecting its road node and dragging it: on release the move is written into its
   points, and (with *Dragging a road moves its junctions*, on by default) the other roads' mouths at its
   junctions come along.
   **Delete a point or a road the ordinary way** — Delete in the Scene dock or the viewport. The record
   forgets every link to it, an interior station's two neighbours stay joined (a road is never cut), a
   junction keeps its other mouths, and names renumber. Ctrl+Z brings it all back exactly.
   Or use the dock: New Road, Extend Road (either end), Insert Point After, Delete Point, Connect
   (SEGMENT / JUNCTION / AUX), Make Intersection, Make Ramp, Branch Ramp Here (from any station; lanes,
   carriageway, entrance), Merge Points, Split To New Road, Select Junction (then move/rotate the whole
   crossing), Follow Road (Auto), Apply Cross-Section (tick the groups; the point selected LAST is the
   source). Every gesture is one undo step.
   **Rotating a point bends its road**: an AUTO point you turn becomes MANUAL and its facing shapes the
   curve; its gizmo handles (drag along the arrow) set `handle_in` / `handle_out`. Follow Road (Auto)
   hands the facing back to the tool. **Repair:** Tidy Roads, Renumber Roads (chain order from the
   links), Repair Links.
   **Refresh Preview** redraws on demand (edits and gestures redraw by themselves). With ZoneMarkers in the
   scene the centrelines are coloured by the zone each run streams with; white = no zone (the resident
   piece, which nothing streams), an orange strip above = past that zone's load radius, magenta = a lane
   whose successor lives in the other zone's piece. Each marker's box and load/unload rings are drawn too.
4. **Validate** — the kit's gate. Click a finding to select its point. A build refuses to run on errors.
   A junction's corners round as far as its turning cars need (every legal movement stays a metre inside
   the pad), so a pad can come out bigger than `fillet_radius` suggests. When no corner can round far
   enough, **`turn_off_pad`** names the mouth standing in a movement's way — turn that mouth to face the
   crossing, or move it out of the path.
   **Flow Report** lists broken / misjoined / unreached lanes and ramp orphans in the exported lane graph.
5. **Build Piece (changed zones)** — rebuilds only the zone pieces whose roads actually came out different
   since their last build (nothing changed: a few seconds, no Blender); **Rebuild All Pieces** forces every
   one. It samples the Terrain3D ground (stations and a 2 m grid under the whole network, so
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

**The record is safe to commit with the editor open.** It is written atomically (a crash mid-save leaves
the old file whole) and only when it changed; if the file changes on disk behind the editor (a git
checkout, a merge) the network RELOADS from it (one undo step) instead of writing its own copy over it.

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
