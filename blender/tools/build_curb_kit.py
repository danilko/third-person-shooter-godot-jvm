#!/usr/bin/env python3
"""
build_curb_kit.py -> kit/curb_kit.blend

One Blender Collection per repeatable curb/barrier/fence piece (the same "one
Collection per reusable piece" convention `tools/build_lane_kit.py` established for
`lane_kit.blend`), each holding one visual mesh object + a `<Name>-colonly` collision
proxy (`kit_common.colonly`). Linked (`link=True`) into an authoring file via the
road_kit_authoring addon's "Link Curb Kit Library" button (`ops_placement.RKA_OT_
link_curb_kit_library`), then repeated along a segment/intersection-corner curb line
via `kit_common.curb_asset_row()` (Curb Style = 'Asset' on any build operator).

WORKED-EXAMPLE PIVOT CONVENTION (read this before authoring a new piece — REQUIRED
for a piece to tile correctly along a curved curb):
  * Origin at the piece's own local (0, 0, 0) — its "start corner", same ENDPOINT
    pivot every wall/fence module in walls_kit.blend already uses.
  * Length runs along local +X. `curb_asset_row()` samples the boundary curve at
    ~`spacing` m intervals and applies a per-instance rotation that maps local +X to
    the world tangent direction at each sample point — a piece authored any other
    way will point along the wrong axis the instant it's dropped on a curve.
  * Front/outward face on local +Y. After the heading rotation above, local +Y ends
    up pointing 90 degrees left of the direction of travel. For a road with curbs on
    both sides, ONE side needs `rot_offset_deg=180` (curb_asset_row's own parameter)
    to keep an asymmetric piece's decorated face pointing away from the road on
    both sides — see Kit_Curb_FencePost_L1 below, an intentionally asymmetric piece
    included specifically to demonstrate this (Kit_Curb_JerseyBarrier_L2 is
    symmetric, so its flip is a visual no-op — build/place that one first to
    confirm the repeat-along-curve mechanism works before debugging asymmetry).
  * Base at z=0 (sits directly on the curb boundary curve's own Z, which already
    includes `lane_surface_z` — see ops_segment.py/ops_intersection.py).
  * Tiling: a piece's own local-X bounding-box length should equal (or evenly
    divide) the `spacing` passed to `curb_asset_row()` for seamless tiling — the
    same "instance length == grid size" contract `ops_combine.py`'s Tier-1 lane-tile
    seam marking already documents. Each piece's Collection stores this length as
    `rka_curb_asset_length` so the addon can read it back and suggest a matching
    spacing instead of the user having to measure it by hand.

RUN: blender --background --python tools/build_curb_kit.py
"""
import bpy, os, sys

HERE_CODE = os.path.dirname(os.path.abspath(__file__))       # blender/kit
BLENDER_SRC = os.path.dirname(HERE_CODE)                      # blender
HERE = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source", "kit")  # data out dir
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import kit_common as kc

# (new collection name, mesh object name, local-X length in meters)
PIECES = [
    ("Kit_Curb_JerseyBarrier_L2", "kit_curb_jersey_barrier_l2m", 2.0),
    ("Kit_Curb_FencePost_L1", "kit_curb_fence_post_l1m", 1.0),
]


def jersey_barrier(name, coll, length):
    """A simple trapezoidal jersey-barrier-like solid (two stacked boxes approximating the
    taper -- kit_common has no dedicated taper primitive; a real asset would sculpt this in
    bmesh). SYMMETRIC front/back, so the rot_offset_deg=180 flip on a road's far side is a
    visual no-op for this piece -- the simplest possible worked example."""
    base = kc.box(name, 0.0, length, -0.35, 0.35, 0.0, 0.5, coll, "concrete")
    kc.box(name + "_Cap", 0.0, length, -0.15, 0.15, 0.5, 0.8, coll, "concrete")
    kc.colonly(base, coll)
    return base


def fence_post(name, coll, length):
    """A single vertical post + one horizontal rail spanning `length` -- an ASYMMETRIC worked
    example (the rail sits only on local +Y, the piece's authored 'outward' face). Placed on
    the wrong curb side without a 180-degree rot_offset_deg flip, the rail would face the
    road instead of away from it."""
    kc.box(name + "_Post", 0.0, 0.1, 0.0, 0.1, 0.0, 1.1, coll, "wood")
    rail = kc.box(name, 0.0, length, 0.05, 0.1, 0.7, 0.85, coll, "wood")
    kc.colonly(rail, coll)
    return rail


BUILDERS = {
    "kit_curb_jersey_barrier_l2m": jersey_barrier,
    "kit_curb_fence_post_l1m": fence_post,
}


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    scene_coll = bpy.context.scene.collection

    for coll_name, mesh_name, length in PIECES:
        coll = bpy.data.collections.new(coll_name)
        scene_coll.children.link(coll)
        BUILDERS[mesh_name](mesh_name, coll, length)
        coll["rka_curb_asset_length"] = length

    print("CURB_KIT: %d collections" % len(PIECES))
    if bpy.app.background:
        kc.save_blend(HERE, "curb_kit.blend")


if __name__ == "__main__":
    main()
