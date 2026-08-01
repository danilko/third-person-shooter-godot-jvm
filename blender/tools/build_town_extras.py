#!/usr/bin/env python3
"""
build_town_extras.py -> townextra_kit.blend

Town variety & landscape: pitched gable roofs, concrete block property wall,
trees (trunk + canopy), hedge, and the shrine torii-gate parts. Pivots match
their class (roofs: footprint corner like walls; trees/hedge/torii: bottom centre).

RUN: blender --background --python tools/build_town_extras.py
"""
import bpy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

COLL = "EXTRAS"
BAY, T, R_H = kc.R_BAY, kc.T, kc.R_H


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)

    # pitched gable roofs for houses
    r1 = kc.gable("SM_House_Roof_4x4", 4.0, 4.0, 1.7, c); kc.colonly(r1, c)
    r2 = kc.gable("SM_House_Roof_6x4", 6.0, 4.0, 1.9, c); kc.colonly(r2, c)

    # concrete block property wall (tileable fence, face +Y, endpoint pivot)
    bw = kc.box("SM_Env_BlockWall_2x12", 0, BAY, -0.12, 0, 0, 1.2, c, "concrete"); kc.colonly(bw, c)

    # tree (trunk + canopy) + hedge
    tr = kc.cyl("SM_Env_TreeTrunk", 0.15, 0, 2.2, c, "wood", seg=8); kc.colonly(tr, c)
    kc.box("SM_Env_TreeCanopy", -1.1, 1.1, -1.1, 1.1, 1.8, 4.2, c, "leaf")
    hg = kc.box("SM_Env_Hedge_2x1", -1.0, 1.0, -0.4, 0.4, 0, 0.8, c, "leaf"); kc.colonly(hg, c)

    # torii gate parts (red) for the shrine
    tp = kc.box("SM_Env_ToriiPost", -0.15, 0.15, -0.15, 0.15, 0, 5.0, c, "red"); kc.colonly(tp, c)
    kc.box("SM_Env_ToriiTop",  -2.5, 2.5, -0.22, 0.22, 0, 0.45, c, "red")
    kc.box("SM_Env_ToriiNuki", -2.2, 2.2, -0.15, 0.15, 0, 0.30, c, "red")

    vis = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("EXTRAS kit: %d visual pieces, %d -colonly proxies"
          % (len(vis), len(c.objects) - len(vis)))
    if bpy.app.background:
        kc.save_blend(ROOT, "townextra_kit.blend")


if __name__ == "__main__":
    main()
