#!/usr/bin/env python3
"""save_lane_kit.py -- combine every road_kit_authoring piece in the open .blend (a district OR
the future arterial overlay -- same mechanism, just a different file/stem) into ONE combined
git-diffable sidecar `<stem>.lanekit.json`, replacing `tools/save_roads.py`/`gen_roads_only.py`'s
role for the OLD `road_graph.py` pipeline (see road_blender_godot.md Phase 6 for the full
replacement plan). `WorldBaker`'s sidecar loader consumes this file exactly as it already
consumes a single piece's own `export_*_json` output -- no Java changes needed.

Authoring loop:
  1. Build/edit intersections/segments/transitions with the road_kit_authoring addon as usual (no
     export_path needed on the individual build operators -- this tool supersedes per-piece export).
  2. Run:  blender <district_or_overlay>.blend --background --python tools/save_lane_kit.py
  3. Rebuild (tools/build_piece.sh <piece-id> -- handles every piece uniformly now, grid or
     freestanding) -- P6.6 wires `lanekit_path` in automatically once `<stem>.lanekit.json`
     exists next to the .blend.

2026-08: the actual per-piece dict reconstruction (`export_piece_dict`/`collect_pieces`) moved to
`addons/road_kit_authoring/lane_export.py` -- this script is now a thin wrapper, so the
interactive addon's own "Preview Lane Curves" button (`ops_lane_preview.py`) can call the SAME
logic without re-deriving it or needing `tools/` on `sys.path`. See that module's docstring for
the per-piece dict shape.

Every lane/arm id is namespaced `<piece>__<id>` and tagged `zone_id` (`lib/lane_kit.py`'s
`combine_pieces`) -- the property-based replacement for the old `<stem>__` name-prefix convention
`WorldZoneManager.findRoute` used to rely on. `zone_id` defaults to this file's own stem, override
per-piece via a manually-added `rka_zone_id` custom property on that piece's collection (same
"hand-edit via the Custom Properties panel" convention `rka_lane_map` overrides already use).

Connectivity between pieces (and eventually between an overlay and its neighboring districts) is
never asserted by this tool -- it's geometry-derived at Godot runtime by `LaneGraph`'s own
endpoint-proximity clustering, same as always. What this tool DOES check, via `lane_kit.py`'s
authoring-time equivalent of that same clustering: whether two pieces' lane endpoints land close
enough to plausibly be an intended connection, and flags anything that isn't a clean 1:1 pairing
(`isolated` = dangling end, informational; `ambiguous` = 3+ candidates, needs manual review) --
printed to stdout, never fatal (a `.lanekit.json` is still written either way; use your judgement,
or route it through `ops_connect.py`'s review UI once that exists).
"""
import bpy, json, os, sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # blender
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "addons"))
import lane_kit                                    # noqa: E402
import road_kit_authoring as rka                    # noqa: E402
from road_kit_authoring import lane_export          # noqa: E402


def main():
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    blend = bpy.data.filepath
    if not blend:
        raise SystemExit("save_lane_kit.py: open a district/overlay .blend first")
    stem = os.path.splitext(os.path.basename(blend))[0]
    out_path = os.path.join(os.path.dirname(blend), stem + ".lanekit.json")

    pieces = lane_export.collect_pieces(stem, bpy.context.scene, bpy.data)
    if not pieces:
        raise SystemExit("save_lane_kit.py: no road_kit_authoring pieces found in %s.blend" % stem)

    combined, reports = lane_kit.combine_pieces(pieces)
    for line in lane_kit.summarize_reports(reports):
        print(line)

    # WHICH PIECES THE USER MEANT TO CONNECT, recorded alongside the lanes. Only the .blend knows
    # this (it lives on the marker Empties), and it is the one thing the sidecar cannot be checked
    # for without it: a joint no lane crosses leaves NO link to measure, so a gate reading only the
    # lane graph sees a clean file with a hole in it. Written so `tools/check_road_network.py` can
    # make that call in CI, with no Blender.
    unjoined = lane_export.unjoined_joints(combined["lanes"], bpy.data)
    combined["joints"] = [{"a": a, "b": b} for a, b in
                          lane_export.authored_joints({p[0] for p in pieces}, bpy.data)]
    for a, b in unjoined:
        print("save_lane_kit: WARNING '%s' and '%s' are linked, but NO lane crosses the seam -- "
              "their ribbons do not meet edge-to-edge anywhere" % (a, b))

    with open(out_path, "w") as f:
        json.dump(combined, f, indent=1)
    print("save_lane_kit: wrote %d lane(s) from %d piece(s) -> %s"
          % (len(combined["lanes"]), len(pieces), out_path))


if __name__ == "__main__":
    main()
