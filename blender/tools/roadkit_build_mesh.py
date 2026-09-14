"""roadkit_build_mesh.py -- the MODEL half of road option B (PLAN.md 3.1): record in, meshes out.

Roads are authored in the Godot editor (`addons/road_kit/`) and solved by the pure-python3
`roadkit_cli.py`. Blender's only job left is the one thing that needs it -- sweeping the road
geometry: carriageway, pads, kerbs, footways, barriers, markings and the `-colonly` proxies. So this
script loads a `.roads.json`, builds it, and saves the piece `.blend` that `build_piece.sh` exports
and bakes. It changes NO authored fact: ground heights come from the record (the plugin samples
Terrain3D), and a red gate refuses to build, exactly as the Blender panel's Build does.

    blender --background --python-exit-code 1 --python blender/tools/roadkit_build_mesh.py -- \
        --record path/to/network.roads.json --out assets/world_source/pieces/<Piece>.blend

B6 zones: `--zones <stem>.zones.json --prefix Roads_<network> --out-dir assets/world_source/pieces`
builds one `.blend` per piece `point_zones` cuts, in ONE Blender session (the network is loaded and
solved per piece; only what streams with that zone is emitted), named by `point_zones.piece_name`.

B6b ground: `--ground <stem>.ground.json` is the Terrain3D height grid the plugin sampled
(`point_ground`). It replaces the raycast -- this session has no terrain -- so every support is
derived from the ground under each sample rather than a lerp of the stations' `ground_z`.
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
    ap.add_argument("--out", default="")
    ap.add_argument("--zones", default="")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--ground", default="")
    a = ap.parse_args(argv)
    if not a.prefix and not a.out:
        raise SystemExit("roadkit_build_mesh.py: pass --out, or --prefix and --out-dir (with --zones to cut by zone)")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.types.Object, "rka_pt"):
        rka.register()
    # The Empties are the kit's VIEW of the record; `point_build` reads the network through them.
    print("== load record:", bpy.ops.rka.load_record(filepath=os.path.abspath(a.record)))
    ground = os.path.abspath(a.ground) if a.ground else ""
    if ground and not os.path.exists(ground):
        raise SystemExit("roadkit_build_mesh.py: no ground sidecar at %s" % ground)
    print("== ground:", ground or "none (station ground_z lerped between stations)")
    if a.prefix:
        from road_kit_authoring import point_model as pm, point_zones as pz
        zones = pz.load_zones(a.zones) if a.zones and os.path.exists(a.zones) else []
        part = pz.partition(pm.load_network(os.path.abspath(a.record)), zones)
        for zone in sorted(part.pieces()):
            piece = pz.piece_name(a.prefix, zone)
            res = bpy.ops.rka.point_build(zones_path=os.path.abspath(a.zones) if zones else "", zone=zone,
                                          ground_path=ground)
            print("== build %s (zone '%s'): %s" % (piece, zone, res))
            if res != {'FINISHED'}:
                raise SystemExit("roadkit_build_mesh.py: the gate refused the build -- see the report above")
            out = os.path.join(os.path.abspath(a.out_dir), piece + ".blend")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=out)
            print("== saved", out)
        return
    res = bpy.ops.rka.point_build(ground_path=ground)
    print("== build:", res)
    if res != {'FINISHED'}:
        raise SystemExit("roadkit_build_mesh.py: the gate refused the build -- see the report above")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("== saved", a.out)


if __name__ == "__main__":
    main()
