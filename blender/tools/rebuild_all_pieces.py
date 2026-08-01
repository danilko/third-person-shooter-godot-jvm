#!/usr/bin/env python3
"""rebuild_all_pieces.py -- force every road_kit_authoring piece in the open .blend to regenerate
its geometry (via `ops_intersection._rebuild_piece_in_place`'s existing dispatch, the same one
every single-piece 'Rebuild From Handles'/live-edit drag already uses) and save the file.

Needed whenever an addon geometry-generation CHANGE (not an authoring edit) should retroactively
apply to a .blend built before that change -- e.g. the pavement-collision fix
(`kit_common.colonly_swept_between`, 2026-07-27): a piece's mesh data is baked into the .blend at
build/rebuild time, so `save_lane_kit.py`/`build_piece.sh` alone only re-export/bake whatever is
ALREADY there. Nothing in the normal authoring loop calls this -- a live-edit drag or 'Rebuild
From Handles' already regenerates the ONE piece it touches; this is for "regenerate everything,
nothing was dragged."

RUN: blender <district_or_overlay>.blend --background --python tools/rebuild_all_pieces.py
"""
import os
import sys

import bpy

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # blender
sys.path.insert(0, os.path.join(BP, "addons"))
import road_kit_authoring as rka                    # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402


def main():
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    blend = bpy.data.filepath
    if not blend:
        raise SystemExit("rebuild_all_pieces.py: open a district/overlay .blend first")

    context = bpy.context
    colls = sorted((c for c in bpy.data.collections
                     if c.library is None and opint._is_piece_collection(c)),
                    key=lambda c: c.name)
    if not colls:
        raise SystemExit("rebuild_all_pieces.py: no road_kit_authoring pieces found in %s"
                          % blend)

    for coll in colls:
        opint._rebuild_piece_in_place(context, coll)
        print("  rebuilt %s" % coll.name)

    bpy.ops.wm.save_mainfile()
    print("rebuild_all_pieces: rebuilt %d piece(s), saved %s" % (len(colls), blend))


if __name__ == "__main__":
    main()
