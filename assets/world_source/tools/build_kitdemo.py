#!/usr/bin/env python3
"""build_kitdemo.py -> districts/District_kitdemo_9_9.blend

Reproducible generator for the DIVIDED-ROAD DEMO district (AUTHORING_GUIDE §7 "Divided
roads" worked example) — a flat hand-authored piece, coordinates 9_9 (outside the 6x6 world
grid: never referenced by a master region marker; walk-tested solo via SoloPiece + F4).
It demos the three divided-road models side by side, each crossed by a N-S street so every
model's junction behaviour is exercised too:

  model 1  road_plain   y=+60  one two-way centerline, lanes=1 (plain painted road)
  model 2  road_dual_e/w y=±5  two anti-parallel ONEWAY curves hugging a physical median
                               bump — each curve is the MEDIAN-SIDE EDGE of its carriageway
                               (keep-left: lanes sit LEFT of the curve in travel direction),
                               opposite point order = opposite travel. 10 m apart ⇒ the cross
                               street forms two SEPARATE junction nodes (the wide-median
                               model, no cross-median U-turn connectors).
  model 3  road_median  y=-60  ONE centerline with the `median` custom prop (3.5 m) — the
                               generator shifts each direction's lane pack out by median/2;
                               junctions stay single-node.

The cross street is drawn as PER-CROSSING SEGMENTS (road_xa..xe) whose endpoints land on the
through roads' interior vertices — that is the from_curves junction contract (an endpoint
within 2 m of an interior vertex splits the through road; plain mid-curve crossings do NOT
create a junction). Everything is hand-adjustable afterwards: tweak curves/props in Blender,
then `tools/gen_roads_only.py` + `tools/build_piece.sh District_kitdemo_9_9` (stem form).

RUN: blender --background --python tools/build_kitdemo.py
"""
import bpy, os, sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # assets/world_source
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "tools"))
import kit_common as kc         # noqa: E402
import assemble as asm          # noqa: E402
import gen_roads_only           # noqa: E402

PIECE = "District_kitdemo_9_9"


def poly_curve(coll, name, pts, **props):
    """One road_* POLY centerline with custom props on the OBJECT (the save_roads table)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, (x, y, z) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1.0)
    ob = bpy.data.objects.new(name, cu)
    for k, v in props.items():
        ob[k] = v
    coll.objects.link(ob)
    return ob


def ribbon(coll, name, pts_hw, z=0.05):
    """Cosmetic asphalt ribbon (GN_RoadProfile sweep — a live preview of the curve-driven
    road-kit visual). pts_hw = [(x, y, half_width)]. Traffic NEVER reads these; the lane
    layer is generated from the ROADS_SRC curves."""
    kc.road_from_curve(name, [(x, y, z, 0.0, hw) for (x, y, hw) in pts_hw],
                       coll, thickness=0.1)


def main():
    kc.setup_units()
    asm.wipe_scene()
    manual = kc.get_coll("MANUAL")
    roads = kc.get_coll("ROADS_SRC")

    # ── ground: one flat slab, top z=0, walkable everywhere the demo roads run ──
    g = kc.box(f"{PIECE}_Ground", -160, 160, -160, 160, -0.5, 0.0, manual, "concrete")
    kc.colonly(g, coll=manual)

    # ── model 2 + 3 median bumps (visual + collision — cars must not cross) ──
    b2 = kc.box("KitDemo_MedianBump_dual", -140, 140, -1.5, 1.5, 0.0, 0.25, manual, "concrete")
    kc.colonly(b2, coll=manual)
    b3 = kc.box("KitDemo_MedianBump_median", -140, 140, -61.5, -58.5, 0.0, 0.25, manual, "concrete")
    kc.colonly(b3, coll=manual)

    # ── cosmetic road surfaces ──
    ribbon(manual, "KitDemo_Vis_plain", [(-140, 60, 3.5), (140, 60, 3.5)])
    ribbon(manual, "KitDemo_Vis_dual_e", [(-140, 6.75, 2.75), (140, 6.75, 2.75)])
    ribbon(manual, "KitDemo_Vis_dual_w", [(-140, -6.75, 2.75), (140, -6.75, 2.75)])
    ribbon(manual, "KitDemo_Vis_median", [(-140, -60, 5.25), (140, -60, 5.25)])
    ribbon(manual, "KitDemo_Vis_cross", [(0, 90, 3.5), (0, -90, 3.5)], z=0.06)

    # ── traffic centerlines (ROADS_SRC — dropped at export; sidecar = source of truth) ──
    # model 1: plain two-way. Interior vertex at x=0 so the cross street can T-split it.
    poly_curve(roads, "road_plain", [(-140, 60, 0), (0, 60, 0), (140, 60, 0)], lanes=1)
    # model 2: dual oneway pair. Median-side edges at y=±5 (bump is ±1.5); opposite point
    # order = opposite travel; keep-left puts each carriageway's lane at y=±6.75.
    poly_curve(roads, "road_dual_e", [(-140, 5, 0), (0, 5, 0), (140, 5, 0)],
               lanes=1, oneway=True)
    poly_curve(roads, "road_dual_w", [(140, -5, 0), (0, -5, 0), (-140, -5, 0)],
               lanes=1, oneway=True)
    # model 3: single centerline + median prop → lanes at y=-60±3.5, strip |dy|<1.75 clear.
    poly_curve(roads, "road_median", [(-140, -60, 0), (0, -60, 0), (140, -60, 0)],
               lanes=1, median=3.5)
    # cross street: one segment per crossing, endpoints ON the through roads' interior
    # vertices (the 2 m junction contract). Shared segment ends cluster into the same node.
    poly_curve(roads, "road_xa", [(0, 90, 0), (0, 60, 0)], lanes=1)
    poly_curve(roads, "road_xb", [(0, 60, 0), (0, 5, 0)], lanes=1)
    poly_curve(roads, "road_xc", [(0, 5, 0), (0, -5, 0)], lanes=1)
    poly_curve(roads, "road_xd", [(0, -5, 0), (0, -60, 0)], lanes=1)
    poly_curve(roads, "road_xe", [(0, -60, 0), (0, -90, 0)], lanes=1)

    # save first (gen_roads_only derives the piece name + sidecar path from the file path)
    kc.save_blend(os.path.join(BP, "districts"), PIECE + ".blend")

    # generate the traffic layer + sidecar in-process, then save again
    gen_roads_only.generate(write_sidecar=True)
    for o in list(bpy.context.view_layer.objects):
        if o is not None:
            o.select_set(False)
    bpy.ops.wm.save_mainfile()
    print(f"build_kitdemo: wrote districts/{PIECE}.blend"
          f" — bake with tools/build_piece.sh {PIECE}")


if __name__ == "__main__":
    main()
