"""PLAN.md 3.9 companion to `tools/reorg_assets.py`: re-points a `.blend`'s RELATIVE library links after files move.

    blender -b <file.blend> --python-exit-code 1 --python tools/relink_blends.py -- <old>=<new> [...]

`<old>`/`<new>` are the library path as Blender stores it (`//../kit/road_kit.blend`). A text substitution cannot
reach a `.blend`, so this is the binary half of the move. The file is saved only if a link changed, and it fails if
a re-pointed library does not exist on disk (a relink to nowhere would leave every linked datablock missing).
"""
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
pairs = dict(a.split("=", 1) for a in args)
changed = False
for lib in bpy.data.libraries:
    new = pairs.get(lib.filepath)
    if new is None:
        continue
    if not os.path.exists(bpy.path.abspath(new)):
        raise SystemExit("relink: %s -> %s does not exist" % (lib.filepath, new))
    print("relink %s: %s -> %s" % (bpy.data.filepath, lib.filepath, new))
    lib.filepath = new
    lib.reload()
    changed = True
if changed:
    bpy.ops.wm.save_mainfile()
