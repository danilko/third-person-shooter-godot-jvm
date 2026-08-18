#!/usr/bin/env python3
"""
smoketest_markings.py -- headless verification for the road_kit_authoring addon's dashed-white /
solid-yellow lane-boundary markings (see lib/intersection_kit.build_segment_lane_markings,
lib/kit_common.marking_ribbon, ops_segment._populate_lane_markings).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_markings.py
"""
import bmesh
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # .../addons/road_kit_authoring
ADDONS_DIR = os.path.dirname(HERE)                           # .../addons
ROOT = os.path.dirname(ADDONS_DIR)                            # blender
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                     # noqa: E402
from road_kit_authoring import ops_segment as opseg  # noqa: E402
import kit_common as kc                               # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _island_count(obj):
    """Number of edge-connected vertex components in obj's mesh -- 1 for a continuous solid
    strip, >1 for a dashed strip (each dash is its own disconnected quad run)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    visited = set()
    islands = 0
    for v in bm.verts:
        if v.index in visited:
            continue
        islands += 1
        stack = [v]
        while stack:
            cur = stack.pop()
            if cur.index in visited:
                continue
            visited.add(cur.index)
            for e in cur.link_edges:
                other = e.other_vert(cur)
                if other.index not in visited:
                    stack.append(other)
    bm.free()
    return islands


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context
    rka_settings = context.scene.rka
    rka_settings.marking_dash_length = 3.0
    rka_settings.marking_gap_length = 3.0
    rka_settings.lane_marking_width = 0.15

    pts = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)]
    result = opseg._build_segment_from_points(
        context, scene_coll, pts, lane_width=5.0, lanes=2, lanes_backward=1,
        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    coll_name = result["coll"].name
    spine_name = result["spine_obj"].name

    coll = bpy.data.collections.get(coll_name)
    marks = [o for o in coll.objects if o.name.startswith("mark_")]
    # `_line_y_` / `_line_w_`, not `_yellow_` / `_white_`: marking objects are named after the
    # MATERIAL KEY they carry, so the name and the material cannot disagree. See
    # `smoketest_median_marking._MARK_MATKEY` -- the hardcoded colour words went silently stale.
    #
    # The COUNT is not asserted: how many ribbons a centreline is drawn with is the cross-section's
    # business (a divided two-way road takes a DOUBLE_Y, i.e. two of them). What IS asserted, right
    # after the gap edit below, is that a rebuild produces the same set as the build -- see there.
    _assert(any("_line_y_" in o.name for o in marks) and any("_line_w_" in o.name for o in marks),
            "expected both a yellow centreline and a white lane boundary, got %r"
            % sorted(o.name for o in marks))
    build_marks = {o.name for o in marks}
    yellow = next(o for o in marks if "_line_y_" in o.name)
    white = next(o for o in marks if "_line_w_" in o.name)

    yellow_islands = _island_count(yellow)
    white_islands = _island_count(white)
    _assert(yellow_islands == 1, "yellow (solid) marking should be 1 continuous strip, got %d islands"
            % yellow_islands)
    _assert(white_islands > 1, "white (dashed) marking should be multiple disjoint dashes, got %d island(s)"
            % white_islands)
    print("markings smoketest: yellow solid = %d island, white dashed = %d islands"
          % (yellow_islands, white_islands))

    # --- resolution: marking_ribbon must NOT resample at a fixed spacing -- a solid line over a
    # straight 2-point spine should be exactly one quad (4 verts), matching the pavement's own
    # control-point density, not the ~160 verts a 0.25m fixed-step densify over 40m would produce.
    yellow_verts = len(yellow.data.vertices)
    _assert(yellow_verts == 4, "solid marking over a straight 2-point spine should be exactly one "
                                "quad (4 verts) -- got %d (fixed-spacing resampling regression?)"
                                % yellow_verts)
    print("markings smoketest: solid marking over a straight spine is 1 quad (%d verts), no "
          "fixed-spacing over-subdivision" % yellow_verts)

    # --- gap persistence: set rka_marking_gaps, rebuild, verify no geometry in [0.4, 0.6] and no
    # accumulation across repeated rebuilds.
    coll["rka_marking_gaps"] = [[0.4, 0.6]]
    opseg.rebuild_segment_gn_in_place(context, coll)
    coll = bpy.data.collections.get(coll_name)
    marks_after = [o for o in coll.objects if o.name.startswith("mark_")]
    # BUILD AND REBUILD MUST AGREE (fixed 2026-08-14, migration Step 2). This used to differ: the
    # build drew a single solid yellow centreline and the very first rebuild replaced it with a
    # DOUBLE yellow, because `_populate_lane_markings` branched on `profile_set` -- absent on the
    # build (scalar markings from `intersection_kit.build_segment_lane_markings`), present on every
    # rebuild, since `custom_props.read_profile` SYNTHESIZES a ProfileSet from the same scalars
    # (profile markings from `_profile_lane_markings`, where `DOUBLE_Y` is two ribbons). Two owners
    # of one cross-section question, disagreeing -- `ROAD_KIT_REDESIGN.md` defect 1. The build now
    # hands the markings the same ProfileSet the piece itself was built from, so a road no longer
    # changes appearance the first time it is dragged.
    _assert({o.name for o in marks_after} == build_marks,
            "a rebuild must produce the SAME markings as the build, got %r after vs %r at build "
            "-- the two derivations have diverged again"
            % (sorted(o.name for o in marks_after), sorted(build_marks)))
    white_after = next(o for o in marks_after if "_line_w_" in o.name)
    xs = [v.co.x for v in white_after.data.vertices]
    gap_x0, gap_x1 = 0.4 * 40.0, 0.6 * 40.0
    in_gap = [x for x in xs if gap_x0 + 0.3 < x < gap_x1 - 0.3]   # small margin for sample spacing
    _assert(not in_gap, "found marking geometry inside the excluded gap range: %s" % in_gap)

    opseg.rebuild_segment_gn_in_place(context, coll)
    coll = bpy.data.collections.get(coll_name)
    marks_twice = [o for o in coll.objects if o.name.startswith("mark_")]
    # THE assertion of this block: a second rebuild with nothing changed must produce the SAME set
    # of marking objects, not another copy of them. Compared against the previous rebuild's own
    # count rather than a literal, so it stays a leak check and does not double as an assertion
    # about which marking layout is correct (see the divergence note above).
    _assert(len(marks_twice) == len(marks_after),
            "a second rebuild with nothing changed should leave the marking set alone: %d objects "
            "after the first rebuild, %d after the second (accumulation?)"
            % (len(marks_after), len(marks_twice)))
    _assert({o.name for o in marks_twice} == {o.name for o in marks_after},
            "the second rebuild renamed/replaced markings instead of rebuilding them in place: "
            "%r -> %r" % (sorted(o.name for o in marks_after),
                          sorted(o.name for o in marks_twice)))
    print("markings smoketest: gap [0.4, 0.6] persisted across rebuild, no geometry in gap, and a "
          "second rebuild left the same %d marking object(s) in place (no accumulation)"
          % len(marks_twice))

    # --- one-way segment: zero markings (no same-direction internal boundary, no opposing
    # boundary since lanes_backward=0).
    result_ow = opseg._build_segment_from_points(
        context, scene_coll, pts, lane_width=5.0, lanes=1, lanes_backward=0,
        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    coll_ow = bpy.data.collections.get(result_ow["coll"].name)
    marks_ow = [o for o in coll_ow.objects if o.name.startswith("mark_")]
    _assert(len(marks_ow) == 0, "one-way segment should have 0 markings, got %d" % len(marks_ow))
    print("markings smoketest: one-way segment (lanes=1, lanes_backward=0) -> 0 markings")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
