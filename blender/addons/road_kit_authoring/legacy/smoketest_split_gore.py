#!/usr/bin/env python3
"""
smoketest_split_gore.py -- a split must produce THREE pieces whose lanes actually meet.

WHY THIS EXISTS. `smoketest_line_split.py` checks branch offsets and departure angle, but never
checks the property that decides whether traffic can drive through the gore: that each branch
lane's first point is close enough to the trunk lane it continues for the runtime's
endpoint-proximity joining (`lane_kit.JUNCTION_RADIUS` / `LaneGraph.JUNCTION_RADIUS = 4.5`) to
pair them. The old `branch_offsets` computed branch centrelines in a CENTRED frame while
`build_segment_from_spine` places one-way lanes EDGE-ANCHORED, so every branch was ~3.25 m out --
geometry and lane data both -- and nothing in the suite noticed, because nothing compared the two.

It also pins the structural change: `trunk_before` / `trunk_taper` / `trunk_aux` are GONE. The
trunk is ONE piece whose auxiliary lane opens as a station of its profile, which is what makes the
merge adjustable and gives it lane data at all.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_split_gore.py
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import lane_kit
import lane_profile as lp
import road_kit_authoring as rka  # noqa: F401
from road_kit_authoring import custom_props, lane_export
from road_kit_authoring.ops_split import (branch_seed_offsets, gore_profile,
                                          line_merge_pieces, line_split_pieces)
from road_kit_authoring.ops_segment import _build_segment_from_points

LW = 3.5
TRUNK = [(x, 0.0, 0.0) for x in (0.0, 200.0, 400.0, 600.0)]
RAMP = [(600.0, 0.0, 0.0), (700.0, 40.0, 0.0), (800.0, 120.0, 0.0)]
AFTER = [(600.0, 0.0, 0.0), (800.0, 0.0, 0.0), (1000.0, 0.0, 0.0)]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _dist(a, b):
    return math.dist(a[:3], b[:3])


def main():
    ctx = bpy.context
    scene_coll = ctx.scene.collection

    # ---------------------------------------------------------------- THREE pieces, not five
    pieces = line_split_pieces(TRUNK, RAMP, AFTER, lanes_a=1, lanes_b=3,
                               lane_width=LW, trunk_lanes=3)
    names = sorted(n for n in pieces if not n.startswith("_"))
    _assert(names == ["branch_a", "branch_b", "trunk"],
            "a split must emit exactly trunk + two branches, got %r -- trunk_before/trunk_taper/"
            "trunk_aux are supposed to be stations of the trunk's profile now" % names)
    ps = pieces["trunk"]["profile_set"]
    _assert(len(ps.profiles) >= 3,
            "the trunk must carry >=3 stations (plain -> taper -> aux held to the gore), got %d"
            % len(ps.profiles))
    print("split_gore: 3 pieces %r, trunk carries %d stations" % (names, len(ps.profiles)))

    # ---------------------------------------------------- the aux lane opens, and only at the end
    first, last = ps.at(0.0), ps.at(1.0)
    _assert(first.slot("A0").width == 0.0,
            "the auxiliary lane must not exist at the start of the trunk (width %.2f)"
            % first.slot("A0").width)
    _assert(abs(last.slot("A0").width - LW) < 1e-6,
            "the auxiliary lane must be full width at the gore, got %.2f" % last.slot("A0").width)
    _assert(abs(last.slot("GORE").width) > 0.0, "the painted nose must open at the gore")
    for sid in ("B0", "B1", "B2"):
        _assert(abs(lp.slot_offset(first, sid) - lp.slot_offset(last, sid)) < 1e-6,
                "mainline lane %s moved sideways between the trunk start and the gore -- the "
                "auxiliary lane must open OUTBOARD of it" % sid)
    print("split_gore: A0 opens 0.00 -> %.2f m with B0..B2 fixed; nose opens to %.2f m"
          % (last.slot("A0").width, last.slot("GORE").width))

    # ------------------------------------------------ the mainline does not shift at the exit
    off_a, off_b = branch_seed_offsets(gore_profile(1, 3, LW, aux_a=1), 1, 3)
    _assert(abs(off_b) < 1e-9,
            "branch B keeps the inner lanes, so its spine must coincide with the trunk's "
            "(offset 0) -- a mainline does not move sideways at an exit. Got %.3f" % off_b)
    _assert(off_a > 3 * LW,
            "branch A must depart OUTBOARD of all three mainline lanes, got %.3f" % off_a)
    print("split_gore: branch B seeds at %.2f (mainline unmoved), branch A at %.2f" % (off_b, off_a))

    # ---------------------------------------------------------------- BUILD, then check lanes MEET
    built = {}
    for name in names:
        spec = pieces[name]
        r = _build_segment_from_points(
            ctx, scene_coll, spec["pts"], LW, spec["lanes"], 0, 'NONE', 'NONE', 0.15, 0.25,
            False, "", "", base_name="SG_%s" % name, traffic_side='LEFT',
            lanes_end=spec["lanes_end"], align=spec["align"],
            profile_set=spec.get("profile_set"))
        built[name] = r["coll"]
        _assert(custom_props.read_profile(r["coll"]) is not None,
                "%s stored no profile" % name)

    exported = {n: lane_export.export_piece_dict(c, ctx.scene, godot_space=False)
                for n, c in built.items()}
    for n, d in exported.items():
        _assert(d is not None and d["lanes"],
                "%s exported NO lane data -- this is the exact defect the redesign exists to "
                "fix (40 of 111 pieces in island_v3_roads.blend were like this)" % n)

    trunk_lanes = {l["slot_id"]: l for l in exported["trunk"]["lanes"]}
    _assert(set(trunk_lanes) == {"B0", "B1", "B2", "A0"},
            "the trunk must export its 3 mainline lanes AND the auxiliary lane, got %r"
            % sorted(trunk_lanes))
    # the auxiliary lane is SHORTER than the piece -- it starts where it opens
    _assert(len(trunk_lanes["A0"]["points"]) < len(trunk_lanes["B0"]["points"]),
            "the auxiliary lane must be shorter than the mainline lanes (it starts partway); "
            "got %d vs %d points"
            % (len(trunk_lanes["A0"]["points"]), len(trunk_lanes["B0"]["points"])))
    print("split_gore: trunk exports %r; A0 runs %d of %d stations"
          % (sorted(trunk_lanes), len(trunk_lanes["A0"]["points"]),
             len(trunk_lanes["B0"]["points"])))

    # THE assertion the suite was missing: every branch lane starts on the trunk lane it continues.
    R = lane_kit.JUNCTION_RADIUS
    for piece, prefix in (("branch_a", "A"), ("branch_b", "B")):
        for lane in exported[piece]["lanes"]:
            sid = lane["slot_id"]
            _assert(sid in trunk_lanes,
                    "%s exports lane %r which the trunk does not carry -- slot ids must survive "
                    "the gore, that is what makes the connection expressible" % (piece, sid))
            head = lane["points"][0]
            tail = trunk_lanes[sid]["points"][-1]
            d = _dist(head, tail)
            _assert(d <= R,
                    "%s lane %s starts %.2f m from where the trunk's own %s ends -- beyond the "
                    "%.1f m the runtime pairs endpoints within, so traffic cannot cross this "
                    "gore. This is the defect `branch_offsets`'s centred frame caused."
                    % (piece, sid, d, sid, R))
    print("split_gore: every branch lane starts within %.1f m of the trunk lane it continues" % R)

    # ---------------------------------------------------------------- the merge mirrors it
    mp = line_merge_pieces(list(reversed(RAMP)), list(reversed(AFTER)),
                           [(x, 0.0, 0.0) for x in (600.0, 800.0, 1000.0, 1200.0)],
                           lanes_a=1, lanes_b=3, lane_width=LW, trunk_lanes=3)
    mnames = sorted(n for n in mp if not n.startswith("_"))
    _assert(mnames == ["branch_a", "branch_b", "trunk"],
            "a merge must emit exactly trunk + two branches, got %r" % mnames)
    mps = mp["trunk"]["profile_set"]
    _assert(abs(mps.at(0.0).slot("A0").width - LW) < 1e-6,
            "the merge's auxiliary lane must be FULL width at the gore, got %.2f"
            % mps.at(0.0).slot("A0").width)
    _assert(mps.at(1.0).slot("A0").width == 0.0,
            "...and gone by the end of the acceleration lane, got %.2f"
            % mps.at(1.0).slot("A0").width)
    print("split_gore: merge mirrors it -- A0 runs %.2f -> %.2f m along one trunk piece"
          % (mps.at(0.0).slot("A0").width, mps.at(1.0).slot("A0").width))

    print("smoketest_split_gore: OK")


if __name__ == "__main__":
    main()
