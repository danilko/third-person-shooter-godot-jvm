"""Write the skeleton CONTRACT's rest pose to `assets/characters/skeleton_rest.json`.

    blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \
        --python blender/tools/dump_skeleton_rest.py

The contract every body presents is bone NAMES plus rest ORIENTATIONS (see
`blender/SKELETON_CONTRACT.md`), and the rig that owns those is whichever `.blend` the shared clip
library was authored on. This reads it out so that `import_vrm_body.py` -- and any later body tool
-- has one derived copy to conform to, instead of a table typed into a script that goes stale the
day the rig is re-authored.

Positions ARE recorded, and they are the reference, not the contract: a body's own bone lengths are
free (that is what a second body is for). They are here so a tool can report how far a new body
differs, which is a measurement worth having and never a correction to apply.
"""
import bpy
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "assets/characters/skeleton_rest.json")

# The contract is the name the RUNTIME uses, and for one bone that is not the name Blender uses:
# the reference .glb carries a MESH node called `head` beside the bone, so Godot's glTF importer
# renames the bone to `head_2`. Every track in the shared library, every AnimationTree filter and
# the ragdoll's `Physical Bone head_2` say `head_2`, so this file does too.
GODOT_ALIASES = {"head": "head_2"}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = OUT
    for i, a in enumerate(argv):
        if a == "--out":
            out = argv[i + 1]

    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        raise SystemExit("[rest] expected one armature, found %s" % [a.name for a in arms])
    arm = arms[0]

    data = {}
    for b in arm.data.bones:
        m = arm.matrix_world @ b.matrix_local
        data[GODOT_ALIASES.get(b.name, b.name)] = {
            "blender": b.name,
            "head": [round(v, 6) for v in m.translation],
            "x": [round(v, 6) for v in m.col[0].xyz.normalized()],
            "y": [round(v, 6) for v in m.col[1].xyz.normalized()],
            "z": [round(v, 6) for v in m.col[2].xyz.normalized()],
            "length": round(b.length, 6),
            "parent": GODOT_ALIASES.get(b.parent.name, b.parent.name) if b.parent else None,
        }
    doc = {
        "_": "DERIVED by blender/tools/dump_skeleton_rest.py -- do not hand-edit.",
        "rig": arm.name,
        "source": bpy.data.filepath.replace(REPO + "/", ""),
        "bones": len(data),
        "rest": data,
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    print("[rest] %s: %d bones -> %s" % (arm.name, len(data), out))


main()
