#!/usr/bin/env python3
"""
build_lane_kit.py -> kit/lane_kit.blend

Promotes the 7 hand-modeled road-kit pieces out of the throwaway exploratory
`districts/District_manual_1.blend` into a permanent, per-piece kit library —
Phase 1 (P1.1) of `road_blender_godot.md`. One Blender **Collection per reusable
piece**, each holding just its visual mesh, ready to be placed via
`kit_common.link_collections`/`instance_collection` by the `road_kit_authoring`
addon (Phase 1/P1.2+). Centerline curves are NOT added here — that is Phase 2
(`RKA_OT_add_centerline`), authored by hand in `lane_kit.blend` once this
promotion step exists.

No per-piece `-colonly` collision proxy is authored here (deliberate — collision
is deferred to a later Godot-side/bake-time pass that merges whole assembled
road segments into one collision object, rather than one tiny box per placed
tile; see the "Collision strategy note" in `road_blender_godot.md` Phase 1-2).

The `.001` intersection variants turned out NOT to be simplified/LOD meshes as
their naming suggested: the 4-way `.001` only covers one quadrant of the
piece's footprint (X[0,10] Y[-10,0] vs the visual's full X[-10,10] Y[-10,10])
and the 3-way `.001` is a differently-shaped/sized piece entirely, not a
reduction of the other. Kept as plain `_variant` objects in the same collection
for hand review — inspect in `lane_kit.blend` and decide per-piece whether to
keep, merge, or discard before Phase 2 centerline authoring.

DO NOT RE-RUN THIS SCRIPT (2026-07-23): centerline authoring now happens by hand
directly in `lane_kit.blend` -- lane centerlines are marked with a `lanedata`
vertex group on each mesh (one edge-connected tagged region per lane; see
`kit_common.centerlines_from_vertex_group` / the `road_kit_authoring` addon's
`RKA_OT_centerline_from_vertex_group`), and `lane_kit.blend` already carries
hand-authored `lanedata` tagging plus at least one piece
(`Kit_Intersection3Way2Lane`) added directly in that file, NOT present in
`District_manual_1.blend`. This script fully rebuilds `lane_kit.blend` from
`District_manual_1.blend` from scratch (`read_homefile(use_empty=True)`), so
running it again would silently destroy all of that hand work. It's kept only
as a record of the one-time promotion step; if `lane_kit.blend` is ever
legitimately regenerated, hand-authored pieces/tagging must be migrated back
into `District_manual_1.blend` (or re-authored) first.

RUN (historical / do not re-run against the current lane_kit.blend — see above):
  blender --background --python kit/build_lane_kit.py
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))       # assets/world_source/kit
ROOT = os.path.dirname(HERE)                             # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

SRC_BLEND = os.path.join(ROOT, "districts", "District_manual_1.blend")

# (new collection name, source visual object name, source LOD/collision variant or None)
PIECES = [
    ("Kit_LaneStraight5", "kit_single_lane_w5m_l5m", None),
    ("Kit_LaneCurbRightCityGutter5", "kit_single_lane_right_city_gutter_curb_w5m_l5m", None),
    ("Kit_CurbSideCityGutter", "kit_side_ight_city_gutter_curb_w0.6m_l5m", None),
    ("Kit_Intersection4Way2Lane", "kit_intersection_4_way_2_lane_straight_2_lane_side",
     "kit_intersection_4_way_2_lane_straight_2_lane_side.001"),
    ("Kit_Intersection3Way1Lane", "kit_intersection_3_way_1_lane_straight_1_lane_side",
     "kit_intersection_3_way_1_lane_straight_1_lane_side.001"),
]

# The source object name has a truncation typo ("...kit_side_ight_..." is missing "stra") —
# fixed on the promoted copy since this kit library is now the source of truth.
RENAME_VISUAL = {
    "kit_side_ight_city_gutter_curb_w0.6m_l5m": "kit_side_straight_city_gutter_curb_w0p6m_l5m",
}

# kit_single_lane_w5m_l5m's centerline-marker vertex group was authored as "lane" before the
# "lanedata" convention (used by every other piece, and by RKA_OT_centerline_from_vertex_group)
# was settled on — normalize it on promotion so every piece uses one group name.
RENAME_VGROUP = {
    "kit_single_lane_w5m_l5m": {"lane": "lanedata"},
}


def _append(names):
    """Append (copy, not link) named objects from SRC_BLEND into the current file."""
    with bpy.data.libraries.load(SRC_BLEND, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    return {o.name: o for o in dst.objects if o is not None}


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    scene_coll = bpy.context.scene.collection

    want = set()
    for _, visual, variant in PIECES:
        want.add(visual)
        if variant:
            want.add(variant)
    appended = _append(want)

    missing = want - set(appended)
    if missing:
        raise RuntimeError("build_lane_kit: source objects missing from %s: %s" % (SRC_BLEND, missing))

    for coll_name, visual_name, variant_name in PIECES:
        coll = bpy.data.collections.new(coll_name)
        scene_coll.children.link(coll)

        visual = appended[visual_name]
        coll.objects.link(visual)

        for old_vg, new_vg in RENAME_VGROUP.get(visual_name, {}).items():
            vg = visual.vertex_groups.get(old_vg)
            if vg:
                vg.name = new_vg

        new_name = RENAME_VISUAL.get(visual_name)
        if new_name:
            visual.name = new_name

        if variant_name:
            # NOT a collision proxy (see module docstring) — kept as a plain alternate for
            # hand review, un-suffixed so Godot's importer/the addon never mistake it for one.
            variant = appended[variant_name]
            coll.objects.link(variant)
            variant.name = visual.name + "_variant"

    total_objs = sum(1 for c in scene_coll.children for o in c.objects)
    print("LANE_KIT: %d collections, %d objects (no collision proxies — deferred, see docstring)"
          % (len(PIECES), total_objs))
    for coll_name, visual_name, _ in PIECES:
        coll = bpy.data.collections[coll_name]
        for o in sorted(coll.objects, key=lambda o: o.name):
            bb = o.bound_box
            xs = [p[0] for p in bb]; ys = [p[1] for p in bb]; zs = [p[2] for p in bb]
            print("  [%s] %-55s X[%6.2f,%6.2f] Y[%6.2f,%6.2f] Z[%6.2f,%6.2f]"
                  % (coll_name, o.name, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

    if bpy.app.background:
        kc.save_blend(HERE, "lane_kit.blend")


if __name__ == "__main__":
    main()
