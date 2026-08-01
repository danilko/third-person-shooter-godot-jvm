# road_kit_authoring — Blender addon

Interactive placement/authoring addon for the mesh-first road kit (`kit/lane_kit.blend`). See
`road_blender_godot.md` at the repo root for the full plan and phase tracker.

## Dev install (symlink, not copy — edits here take effect immediately, no addon reinstall)

From the repo root:

```bash
blender/tools/install_blender_addon.sh
```

This symlinks this directory into **every** installed Blender version's addons folder
(`~/.config/blender/<version>/scripts/addons/`) and enables it headlessly. **Re-run it after
every Blender upgrade** — Blender's addon config is per-version, so a fresh version directory
(e.g. after 5.1 → 5.2) does not inherit the symlink from the old one and the panel silently
disappears until this is re-run. See the top-level `README.md` "World Authoring Setup" section.

Manual fallback (if you only want one specific Blender version wired up):

```bash
ln -s "$(pwd)/blender/addons/road_kit_authoring" \
    ~/.config/blender/<version>/scripts/addons/road_kit_authoring
```

then enable it in Edit > Preferences > Add-ons, search "Road Kit Authoring".

## Panel

3D Viewport > Sidebar (`N`) > "Road Kit" tab. This is the addon's real current feature set —
it's grown well past initial placement into a full mesh-first hand-authoring workflow
(this is the same tool used to hand-author Piece_5_1's (industry) `MANUAL` road content, the
reference example for how every other district's roads are meant to be authored going forward):

- **Godot Export** — one-click button that regenerates the district's `.lanekit.json` sidecar and
  runs the export/bake/navmesh pipeline (`tools/save_lane_kit.py` + `tools/build_piece.sh`) for
  the currently-open district. Watch the System Console for progress (~20-40s). Requires the file
  to be saved as `District_<theme>_<gx>_<gy>.blend` first.
- **Multi-District Group** — panel front-end for the multi-district combined edit session
  (`tools/open_district_group.py`/`writeback_district_group.py`, see `AUTHORING_GUIDE.md` §4):
  from a district file, check off which built neighbours to include (or type any other district
  stem(s), comma-separated, into "Other Districts" — not just adjacent ones), *Open Group* to
  append them all into one disposable scratch file at their true offsets and open it directly.
  While in that scratch session, *Add District(s)* pulls in more districts on the fly (typed the
  same way) without restarting — for when a fix turns out to reach further than where you
  started. *Write Back Group* saves everything back to each district's own file, rebuilds each,
  and checks the seam — all as background subprocesses (same modal-timer pattern as "Godot
  Export"), watch the System Console.
- **Kit Library / Curb Kit Library** — link every Collection from `kit/lane_kit.blend` /
  the curb-asset kit blend into the current file (true library link, not append — editing a
  piece in the library blend and reopening the district file picks up the change with no
  re-export step). A curb style can be set to "Asset" on any build operator's F9 panel, then
  pointed at a linked curb collection.
- **Placement** — search/pick a linked catalog piece, then *Place Piece* (modal click-to-drop,
  grid-snapped), *Duplicate* (offsets along the piece's own local placement direction, so a run
  continues correctly after a 90° rotation), *Rotate CW/CCW*.
- **Live Edit** — drag an `arm_*` Empty to rotate/reshape its intersection live, or a segment's
  `segend_A/B` to resize/redirect it (or `segbend` to bend/hill it) — all live, no rebuild
  needed. Includes a manual "force update" fallback for when a drag doesn't auto-refresh.
- **Select Piece** — lists every piece in the file by name for one-click whole-piece selection
  (no Outliner click needed first); *Freeze For Move* / *Freeze ALL* suspend live-edit
  regeneration before a Grab/Rotate on one piece or the whole file (required for a whole-file
  move — doing that with live-edit on will crash Blender); *Unfreeze & Rebuild* / *Unfreeze ALL
  & Rebuild* bring geometry back in sync afterward.
- **Multi-lane (seam marking)** — visual lane-direction/count readout per arm/segment end
  (incoming vs. outgoing lanes), plus a lane-map override field for asymmetric arm lane counts.
- **Intersection (prototype)** — `Build Intersection` at the active `arm_*`/`segend_*`/
  `segbend_*` marker or the 3D cursor; F9 to tweak preset/radius/lanes/traffic side right after
  building.
- **Straight Segment / Segment From Curve** — curve-backed pavement (`spine_*` Curve object,
  editable live in Edit Mode); Lanes Backward = 0 makes it one-way. `Segment From Curve` seeds a
  new self-contained spine by sampling an existing Curve object once.
- **Lane Transition** — tapers Lanes A -> Lanes B over its length (pavement + curb together),
  e.g. a 2-lane street narrowing into a 1-lane arm.
- **Extend / Insert** — context-sensitive continuation from whatever's active: a `port_*` Empty,
  an `arm_*` Empty, an Intersection collection, or a Segment collection.
- **Centerline** — builds a centerline from a lane mesh's `lanedata` vertex group.
- **Connectivity (Phase 3, not wired yet)** — `connect_eps` is exported for `lib/lane_kit.py`'s
  endpoint-clustering pass; still not wired to any operator.

Requires `kit/lane_kit.blend` to exist first — build it with
`blender --background --python tools/build_lane_kit.py` (see that script's docstring).

Roughly 20 `smoketest_*.py` scripts (`smoketest_collision.py`, `smoketest_freeze_all.py`,
`smoketest_curb_style_panel.py`, `smoketest_lane_map_panel.py`, `smoketest_open_ended_deck.py`,
`smoketest_transition_and_spine.py`, etc.) cover this feature set headlessly — run one with
`blender --background --python <script>` when touching the corresponding operator.

## Status

Well past the original Phase 1 skeleton — placement, live-edit, freeze/select, intersections,
segments, lane transitions, extend/insert, centerline extraction, and one-click Godot export
(`ops_export.py`, wired into `__init__.py`'s `MODULES`) are all present and in active use.
Still not present: dedicated `ops_connect.py`/`ops_validate.py`/`overlay_draw.py` modules and the
Phase 3 `connect_eps` wiring described above.
