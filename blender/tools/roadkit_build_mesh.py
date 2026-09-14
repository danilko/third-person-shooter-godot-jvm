"""roadkit_build_mesh.py -- the MODEL half of road option B (PLAN.md 3.1): record in, meshes out.

Roads are authored in the Godot editor (`addons/road_kit/`) and solved by the pure-python3
`roadkit_cli.py`. Blender's only job left is the one thing that needs it -- sweeping the road
geometry: carriageway, pads, kerbs, footways, barriers, markings and the `-colonly` proxies. So this
script loads a `.roads.json`, builds it, and saves the piece `.blend` that `build_piece.sh` exports
and bakes. It changes NO authored fact: ground heights come from the record (the plugin samples
Terrain3D), and a red gate refuses to build, exactly as the Blender panel's Build does.

    blender --background --python-exit-code 1 --python blender/tools/roadkit_build_mesh.py -- \
        --record path/to/network.roads.json --out assets/world_source/pieces/<Piece>.blend
"""
import argparse
import os
import sys

import bpy

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(BP, "lib"), os.path.join(BP, "addons")):
    if p not in sys.path:
        sys.path.insert(0, p)

import road_kit_authoring as rka  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="roadkit_build_mesh.py")
    ap.add_argument("--record", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.types.Object, "rka_pt"):
        rka.register()
    # The Empties are the kit's VIEW of the record; `point_build` reads the network through them.
    print("== load record:", bpy.ops.rka.load_record(filepath=os.path.abspath(a.record)))
    res = bpy.ops.rka.point_build()
    print("== build:", res)
    if res != {'FINISHED'}:
        raise SystemExit("roadkit_build_mesh.py: the gate refused the build -- see the report above")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("== saved", a.out)


if __name__ == "__main__":
    main()
