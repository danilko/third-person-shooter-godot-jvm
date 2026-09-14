"""build_roadkit_sample_piece.py -> assets/world_source/pieces/RoadKitSample.blend (+ .lanekit.json)

The road-system evaluation of 2026-09-13 (PLAN.md 3.1): the road kit's sample network (two streets
crossing, an elevated highway with a weave, ramps, a shared auxiliary lane -- its committed record,
`RoadKitSample.roads.json`, since B9 retired the `Add Sample Network` button that authored it) built into a
piece so `build_piece.sh RoadKitSample` takes it through the real export -> WorldBaker bake, and
`debug/RoadKitTrafficTestHost` drives traffic on it. No terrain: the question is the lane graph.

    blender --background --python-exit-code 1 --python blender/tools/build_roadkit_sample_piece.py
"""
import bpy, os, sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # blender/
REPO = os.path.dirname(BP)
PIECES = os.path.join(REPO, "assets", "world_source", "pieces")
for p in (os.path.join(BP, "lib"), os.path.join(BP, "addons"), os.path.join(BP, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import road_kit_authoring as rka                                            # noqa: E402


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.types, "RKA_OT_point_build"):
        rka.register()
    print("== sample network:", bpy.ops.rka.load_record(filepath=os.path.join(PIECES, "RoadKitSample.roads.json")))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    print("== auto setback:", bpy.ops.rka.auto_setback())
    print("== build:", bpy.ops.rka.point_build())

    from road_kit_authoring import point_model as pm
    from road_kit_authoring import point_validate as pv
    net = pm.read_network()
    findings = pv.validate(net)
    errs = pv.errors(findings)
    print("== gate: %d error(s), %d warning(s)" % (len(errs), len(findings) - len(errs)))
    for f in findings[:12]:
        print("   %-5s %s" % (getattr(f, "level", "?"), pv.describe(f, net.labels)))

    out = os.path.join(PIECES, "RoadKitSample.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("== saved", out)
    side = os.path.splitext(out)[0] + ".lanekit.json"
    print("== lanekit export:", bpy.ops.rka.export_lanekit(filepath=side), side)


if __name__ == "__main__":
    main()
