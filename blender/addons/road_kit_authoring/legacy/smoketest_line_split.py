#!/usr/bin/env python3
"""
smoketest_line_split.py -- headless verification of ops_split: one line becoming two, and two
lines becoming one.

The property under test is what separates a SPLIT from an INTERSECTION: at a split the branches
leave TANGENT to the trunk and part at a gore nose, so traffic neither turns nor stops. If a
branch departs at an angle, the geometry is an intersection wearing a split's name.

Because the primitive is topological rather than ramp-specific, the same code has to serve very
different shapes, so the test drives all of them through one function:

  * off-ramp        trunk 2 -> 2 + 1, auxiliary lane tapered in first
  * Y-fork / JCT    trunk 4 -> 2 + 2, pure split, NO widening
  * carriageway     trunk 2 -> 1 + 1, symmetric
  * on-ramp (merge) 2 + 1 -> trunk 2, longer auxiliary lane than the split's

Plus the invariants: branch offsets are symmetric when the branches are, they collapse to the
off-ramp geometry when one branch is a single lane, a split may never DROP lanes, and a trunk too
short to widen is refused with a reason.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_line_split.py
"""
import bpy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import kit_common as kc
import road_kit_authoring as rka
from road_kit_authoring.ops_split import (line_split_pieces, line_merge_pieces,
                                          branch_seed_offsets, gore_profile,
                                          GORE_NOSE, NOSE_LENGTH)
from road_kit_authoring.ops_intersection import RkaBuildError

LW = 3.5


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _plen(pts):
    return sum(math.dist(a[:3], b[:3]) for a, b in zip(pts, pts[1:]))


def _full_width_run(piece, slot_id, width, samples=2000):
    """Metres of `piece` over which `slot_id` carries (very nearly) `width`.

    Measured by sampling the ProfileSet rather than reading a dedicated `trunk_aux` piece: the
    auxiliary stretch is no longer a collection of its own, it is a range of STATIONS on the one
    trunk piece, so its length has to be measured the way the geometry actually derives it."""
    L = _plen(piece["pts"])
    ps = piece["profile_set"]
    hits = 0
    for i in range(samples + 1):
        s = ps.at(i / float(samples)).slot(slot_id)
        if s is not None and abs(s.width - width) < 1e-6:
            hits += 1
    return L * hits / float(samples + 1)


def _curve(name, pts, coll):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    return obj


def _departure_deviation(pieces, key):
    p = pieces[key]["pts"]
    t = pieces["_gore"]["tangent"]
    h = math.degrees(math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]))
    m = math.degrees(math.atan2(t[1], t[0]))
    return abs((h - m + 180.0) % 360.0 - 180.0)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    coll = bpy.context.scene.collection

    trunk = [(float(x), 0.0, 12.0) for x in range(0, 801, 20)]
    # Branch A peels LEFT (+Y for +X travel) and descends; branch B carries straight on.
    br_left = [(400.0, 0.0, 12.0), (480.0, 30.0, 10.0), (560.0, 74.0, 7.0), (620.0, 130.0, 4.0)]
    br_right = [(400.0, 0.0, 12.0)] + [(float(x), 0.0, 12.0) for x in range(440, 801, 40)]

    # -------------------------------------------------------------- the seed offsets
    # `branch_offsets` (a second, CENTRED frame) is gone: a branch's seed is now read straight off
    # the gore profile's own slot edges, so there is no formula left to disagree with the builder.
    gp = gore_profile(1, 2, LW, aux_a=1)
    oa, ob = branch_seed_offsets(gp, 1, 2)
    _assert(abs(ob) < 1e-9,
            "branch B keeps the trunk's own datum -- the MAINLINE MUST NOT MOVE SIDEWAYS at an "
            "exit -- so its seed offset is 0, got %+.3f" % ob)
    exp_a = 2 * LW + GORE_NOSE          # past both mainline lanes, then past the painted nose
    _assert(abs(oa - exp_a) < 1e-9,
            "the exiting branch seeds at the nose's outboard edge, %.3f m; got %.3f" % (exp_a, oa))
    _assert(oa > ob, "branch A departs OUTBOARD of branch B in keep-left travel")
    print("line_split smoketest: seeds read off the gore profile (mainline 0.00, ramp %.2f)" % oa)

    # ------------------------------------------------------------------- off-ramp (widened)
    off = line_split_pieces(trunk, br_left, br_right, lanes_a=1, lanes_b=2,
                            lane_width=LW, trunk_lanes=2)
    _assert(sorted(k for k in off if not k.startswith("_")) == ["branch_a", "branch_b", "trunk"],
            "a split is THREE pieces now -- trunk_before/trunk_taper/trunk_aux were stations of "
            "one lane COUNT and are gone; got %s" % sorted(off))
    ps = off["trunk"]["profile_set"]
    _assert(ps.at(0.0).slot("A0").width == 0.0 and
            abs(ps.at(1.0).slot("A0").width - LW) < 1e-9,
            "the auxiliary lane must open 0 -> full along the ONE trunk piece")
    b_widths = {round(sum(s.width for s in ps.at(t / 20.0).slots if s.id.startswith("B")), 6)
                for t in range(21)}
    _assert(len(b_widths) == 1,
            "the MAINLINE lanes must not change width anywhere along the trunk, got %s" % b_widths)
    _assert(off["_gore"]["widened"] is True, "an off-ramp split is a WIDENED split")

    # THE FLUSH PROPERTY -- the reason the nose has its own stations. Wherever the exit lane
    # carries width before the final nose run, the gore must still be SHUT, so the lane is part of
    # the carriageway rather than a strip held clear of it.
    for i in range(101):
        t = i / 100.0
        pr = ps.at(t)
        if pr.slot("A0").width > 1e-6 and t < 1.0 - (NOSE_LENGTH / _plen(off["trunk"]["pts"])) - 1e-6:
            _assert(pr.slot("GORE").width < 1e-6,
                    "at t=%.2f the exit lane is %.2f m wide but the gore is already %.2f m open "
                    "-- the deceleration lane must run FLUSH against the mainline"
                    % (t, pr.slot("A0").width, pr.slot("GORE").width))
    _assert(abs(ps.at(1.0).slot("GORE").width - GORE_NOSE) < 1e-9,
            "the nose must reach full width exactly at the gore")
    dev = _departure_deviation(off, "branch_a")
    _assert(dev < 35.0,
            "the exiting branch must leave TANGENT (a gore is a division, not a corner); "
            "deviates %.1f deg" % dev)
    print("line_split smoketest: off-ramp  trunk 2 -> 2+1 on ONE piece, aux runs flush until the "
          "last %.0f m, branch leaves at %.1f deg" % (NOSE_LENGTH, dev))

    # ---------------------------------------------------------------- Y-fork (pure, no aux)
    fork_l = [(400.0, 0.0, 12.0), (500.0, 40.0, 12.0), (620.0, 96.0, 12.0)]
    fork_r = [(400.0, 0.0, 12.0), (500.0, -40.0, 12.0), (620.0, -96.0, 12.0)]
    fork = line_split_pieces(trunk, fork_l, fork_r, lanes_a=2, lanes_b=2, lane_width=LW)
    _assert("trunk" in fork and "trunk_aux" not in fork,
            "a pure fork must NOT widen — got %s" % sorted(fork))
    _assert(fork["_gore"]["widened"] is False, "2+2 from a 4-lane trunk is not a widening")
    _assert(fork["trunk"]["lanes"] == 4, "the trunk into a 2+2 fork carries 4 lanes")
    # Even with no auxiliary lane to taper, the nose still opens only at the end -- otherwise the
    # two carriageways are born already 3 m apart instead of dividing at a point.
    fps = fork["trunk"]["profile_set"]
    _assert(fps.at(0.0).slot("GORE").width < 1e-6,
            "a fork's gore must be SHUT at the start of the trunk")
    _assert(abs(fps.at(1.0).slot("GORE").width - GORE_NOSE) < 1e-9,
            "a fork's gore must be fully open at the gore point")
    _assert(fork["branch_a"]["lanes"] == 2 and fork["branch_b"]["lanes"] == 2,
            "both fork branches carry 2 lanes")
    print("line_split smoketest: Y-fork    trunk 4 -> 2+2, no auxiliary lane (pure split)")

    # ------------------------------------------------------------- carriageway around island
    car = line_split_pieces(trunk, fork_l, fork_r, lanes_a=1, lanes_b=1, lane_width=LW)
    _assert(car["trunk"]["lanes"] == 2 and car["_gore"]["widened"] is False,
            "a 1+1 carriageway split is also a pure split")
    print("line_split smoketest: island    trunk 2 -> 1+1, same primitive, different numbers")

    # -------------------------------------------------------------------------- merge mirror
    m_left = [(620.0, 130.0, 4.0), (560.0, 74.0, 7.0), (480.0, 30.0, 10.0), (400.0, 0.0, 12.0)]
    m_right = [(float(x), 0.0, 12.0) for x in range(0, 401, 40)]
    trunk_out = [(float(x), 0.0, 12.0) for x in range(400, 1201, 20)]
    mg = line_merge_pieces(m_left, m_right, trunk_out, lanes_a=1, lanes_b=2,
                           lane_width=LW, trunk_lanes=2)
    mps = mg["trunk"]["profile_set"]
    _assert(abs(mps.at(0.0).slot("A0").width - LW) < 1e-9,
            "a merge's auxiliary lane starts at FULL width, at the gore")
    _assert(mps.at(1.0).slot("A0").width == 0.0,
            "and is tapered away by the end of the trunk piece")
    _assert(abs(mps.at(0.0).slot("GORE").width - GORE_NOSE) < 1e-9,
            "a merge's nose is fully open AT the gore and closes downstream -- the mirror of a "
            "split, so joining traffic ends up flush against the mainline before it must merge")
    d_aux = _full_width_run(off["trunk"], "A0", LW)
    m_aux = _full_width_run(mg["trunk"], "A0", LW)
    _assert(m_aux > d_aux,
            "joining traffic must be given MORE auxiliary lane than exiting traffic: "
            "merge %.0f m vs split %.0f m" % (m_aux, d_aux))
    print("line_split smoketest: merge     2+1 -> trunk 2, accel %.0f m > decel %.0f m"
          % (m_aux, d_aux))

    # ------------------------------------------------------------------------- refusals
    try:
        line_split_pieces(trunk, br_left, br_right, lanes_a=1, lanes_b=1,
                          lane_width=LW, trunk_lanes=4)
        raise AssertionError("a split that DROPS lanes (4 -> 1+1) must be refused")
    except RkaBuildError as exc:
        _assert("cannot drop lanes" in str(exc), "wrong refusal message: %s" % exc)
    short = [(0.0, 0.0, 12.0), (60.0, 0.0, 12.0)]
    try:
        line_split_pieces(short, [(55.0, 0.0, 12.0), (100.0, 30.0, 9.0)],
                          [(55.0, 0.0, 12.0), (120.0, 0.0, 12.0)],
                          lanes_a=1, lanes_b=2, lane_width=LW, trunk_lanes=2)
        raise AssertionError("a trunk too short to widen must be refused")
    except RkaBuildError as exc:
        _assert("taper" in str(exc) or "auxiliary" in str(exc),
                "rejection should say what does not fit: %s" % exc)
    print("line_split smoketest: lane-dropping and too-short trunks are refused with reasons")

    # --------------------------------------------------------------------- it actually builds
    tc = _curve("trunkline", trunk, coll)
    ac = _curve("branch_left", br_left, coll)
    bc = _curve("branch_right", br_right, coll)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ret = bpy.ops.rka.build_line_split(
        'EXEC_DEFAULT', trunk_curve=tc.name, branch_a_curve=ac.name, branch_b_curve=bc.name,
        lanes_a=1, lanes_b=2, trunk_lanes=2, lane_width=LW)
    _assert(ret == {'FINISHED'}, "build_line_split did not finish: %s" % (ret,))
    made = [c.name for c in bpy.data.collections if c.name.startswith("Split_")]
    _assert(len(made) == 3, "a split builds exactly 3 collections (trunk + 2 branches), got "
                            "%d (%s)" % (len(made), made))
    print("line_split smoketest: operator built %d piece collection(s)" % len(made))

    print("smoketest_line_split: OK")


if __name__ == "__main__":
    main()
