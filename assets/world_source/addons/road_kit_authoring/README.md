# road_kit_authoring — Blender addon

Interactive placement/authoring addon for the mesh-first road kit (`kit/lane_kit.blend`). See
`road_blender_godot.md` at the repo root for the full plan and phase tracker.

## Dev install (symlink, not copy — edits here take effect immediately, no addon reinstall)

From the repo root:

```bash
tools/install_blender_addon.sh
```

This symlinks this directory into **every** installed Blender version's addons folder
(`~/.config/blender/<version>/scripts/addons/`) and enables it headlessly. **Re-run it after
every Blender upgrade** — Blender's addon config is per-version, so a fresh version directory
(e.g. after 5.1 → 5.2) does not inherit the symlink from the old one and the panel silently
disappears until this is re-run. See the top-level `README.md` "World Authoring Setup" section.

Manual fallback (if you only want one specific Blender version wired up):

```bash
ln -s "$(pwd)/assets/world_source/addons/road_kit_authoring" \
    ~/.config/blender/<version>/scripts/addons/road_kit_authoring
```

then enable it in Edit > Preferences > Add-ons, search "Road Kit Authoring".

## Panel

3D Viewport > Sidebar (`N`) > "Road Kit" tab:

- **Kit Library** — "Link Kit Library" links every Collection from `kit/lane_kit.blend` into the
  current file (a true library link, not append — editing a piece in `lane_kit.blend` and
  reopening the district file picks up the change with no re-export step).
- **Placement**
  - *Piece* — search field over every linked Collection; pick the active piece to place.
  - *Place Piece* — modal: click in the viewport to drop instances snapped to the grid (ray cast
    to the world Z=0 ground plane); Esc / right-click to stop.
  - *Duplicate* — offsets the selected instance(s) one grid step along their own **local**
    placement direction (X+/X-/Y+/Y-, picked next to the button), so continuing a run still works
    correctly after a 90° rotation.
  - *Rotate CW / CCW* — spins the selected instance(s) 90° around world Z, in place.
- **Connectivity** — `connect_eps` is exported now for `lib/lane_kit.py`'s endpoint-clustering
  pass (Phase 3); not wired to any operator yet.

Requires `kit/lane_kit.blend` to exist first — build it with
`blender --background --python kit/build_lane_kit.py` (see that script's docstring).

## Status

Phase 1 (this addon skeleton + placement) — see `road_blender_godot.md` P1.2-P1.5. Centerline
authoring (`ops_centerline.py`), connectivity/export (`ops_connect.py`, `ops_validate.py`,
`ops_export.py`, `overlay_draw.py`) land in later phases and aren't present yet.
