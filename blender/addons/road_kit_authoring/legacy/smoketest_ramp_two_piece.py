#!/usr/bin/env python3
"""
smoketest_ramp_two_piece.py -- an on/off ramp is TWO pieces, and the mainline is not cut.

WHY THIS EXISTS. `line_split_pieces` is a symmetric primitive: a trunk divides into branch A and
branch B. That is right for a Y-fork, where neither outgoing line is "the road". At an off-ramp it
is wrong in a way that costs real editing pain -- branch B *is* the mainline carrying on, so the
mainline gains a seam, a new collection and a new identity at every exit. Measured on
`island_v3_roads.blend`: `IC_YAMATE_split_trunk_001` ends at exactly the point
`IC_YAMATE_split_branch_b_001` begins, and the two are one carriageway.

`ramp_split_pieces` / `ramp_merge_pieces` express the exit the way the road behaves instead: ONE
mainline piece whose cross-section gains an auxiliary lane, opens a nose, and then reverts once
the ramp has taken that pavement away. The properties worth pinning are all about that one piece:

  * it is UNCUT -- as long as the mainline it was given
  * the mainline's own lanes never change width anywhere along it
  * the exit lane runs FLUSH (nose shut) until the final nose run
  * past the gore the cross-section STEPS back, rather than tapering the ramp away in mid-air
  * the ramp seeds exactly on the slot it continues, within the runtime's junction radius

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_ramp_two_piece.py
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

import lane_profile as lp
import road_kit_authoring as rka  # noqa: F401
from road_kit_authoring.ops_split import (ramp_split_pieces, ramp_merge_pieces,
                                          GORE_NOSE, NOSE_LENGTH, DECEL_LENGTH, ACCEL_LENGTH)
from road_kit_authoring.ops_intersection import RkaBuildError

LW = 3.5
MAIN = [(float(x), 0.0, 12.0) for x in range(0, 1201, 20)]
OFF_RAMP = [(600.0, 0.0, 12.0), (680.0, 30.0, 10.0), (760.0, 74.0, 7.0), (820.0, 130.0, 4.0)]
ON_RAMP = [(820.0, 130.0, 4.0), (760.0, 74.0, 7.0), (680.0, 30.0, 10.0), (600.0, 0.0, 12.0)]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _plen(pts):
    return sum(math.dist(a[:3], b[:3]) for a, b in zip(pts, pts[1:]))


def _main_width(profile):
    return sum(s.width for s in profile.slots if s.id.startswith("B"))


def main():
    bpy.ops.wm.read_homefile(use_empty=True)

    # ------------------------------------------------------------------------------ OFF-RAMP
    off = ramp_split_pieces(MAIN, OFF_RAMP, lanes=2, ramp_lanes=1, lane_width=LW)
    _assert(sorted(k for k in off if not k.startswith("_")) == ["mainline", "ramp"],
            "an off-ramp is TWO pieces, got %s" % sorted(off))

    ml = off["mainline"]
    L = _plen(ml["pts"])
    _assert(abs(L - _plen(MAIN)) < 1e-6,
            "the mainline must be UNCUT: %.1f m in, %.1f m out" % (_plen(MAIN), L))
    ps = ml["profile_set"]

    widths = {round(_main_width(ps.at(i / 200.0)), 6) for i in range(201)}
    _assert(widths == {round(2 * LW, 6)},
            "the mainline's own lanes must not change width anywhere along the piece, got %s"
            % widths)

    s_gore = off["_gore"]["station"]
    _assert(abs(ps.at(0.0).slot("A0").width) < 1e-9, "no exit lane at the start of the mainline")
    _assert(abs(ps.at((s_gore - 1.0) / L).slot("A0").width - LW) < 1e-6,
            "the exit lane must be at full width just before the gore")
    _assert(abs(ps.at((s_gore - 1.0) / L).slot("GORE").width - GORE_NOSE) > 1e-6,
            "the nose must not already be at full width a metre before the gore")

    # FLUSH: wherever the exit lane carries width before the nose run, the gore is still shut.
    for i in range(1001):
        d = L * i / 1000.0
        pr = ps.at(d / L)
        if pr.slot("A0").width > 1e-6 and d < s_gore - NOSE_LENGTH - 1e-6:
            _assert(pr.slot("GORE").width < 1e-6,
                    "at %.1f m the exit lane is %.2f m wide but the gore is %.2f m open -- the "
                    "deceleration lane must run FLUSH against the mainline"
                    % (d, pr.slot("A0").width, pr.slot("GORE").width))

    # THE STEP: the ramp takes its pavement with it AT the gore, it does not taper away in mid-air.
    after = ps.at(min(1.0, (s_gore + 1.0) / L))
    _assert(after.slot("A0").width < 1e-6 and after.slot("GORE").width < 1e-6,
            "one metre past the gore the mainline must be back to its own lanes, got A0=%.2f "
            "GORE=%.2f" % (after.slot("A0").width, after.slot("GORE").width))
    _assert(abs(lp.total_width(ps.at(1.0)) - 2 * LW) < 1e-6,
            "the mainline must END at its plain width")

    # The ramp seeds on the slot it continues -- the runtime pairs lanes by endpoint proximity
    # (LaneGraph.JUNCTION_RADIUS = 4.5 m), so this is what makes traffic able to drive through.
    at_gore = off["_gore"]["profile"]
    want = lp.slot_offset(at_gore, "A0")
    got = off["_gore"]["offset_a"] + LW / 2.0     # seed is the slot's inner edge, centre is +w/2
    _assert(abs(want - got) < 1e-6,
            "the ramp must seed on A0's own centreline: slot says %.3f, seed gives %.3f"
            % (want, got))
    _assert(math.dist(off["ramp"]["pts"][0][:2], off["_gore"]["position"][:2]) < 20.0,
            "the ramp's first point must sit at the gore, not somewhere down the road")
    print("ramp_two_piece: OFF-RAMP  mainline %.0f m UNCUT, 2 lanes fixed, exit lane flush until "
          "the last %.0f m, steps back past the gore" % (L, NOSE_LENGTH))

    # ------------------------------------------------------------------------------- ON-RAMP
    on = ramp_merge_pieces(MAIN, ON_RAMP, lanes=2, ramp_lanes=1, lane_width=LW)
    _assert(sorted(k for k in on if not k.startswith("_")) == ["mainline", "ramp"],
            "an on-ramp is TWO pieces, got %s" % sorted(on))
    mps = on["mainline"]["profile_set"]
    Lm = _plen(on["mainline"]["pts"])
    _assert(abs(Lm - _plen(MAIN)) < 1e-6, "the on-ramp mainline must be UNCUT too")
    widths = {round(_main_width(mps.at(i / 200.0)), 6) for i in range(201)}
    _assert(widths == {round(2 * LW, 6)}, "on-ramp mainline lanes must not move either")

    g = on["_gore"]["station"]
    before = mps.at(max(0.0, (g - 1.0) / Lm))
    _assert(before.slot("A0").width < 1e-6 and before.slot("GORE").width < 1e-6,
            "a metre BEFORE an on-ramp gore the mainline is plain, got A0=%.2f GORE=%.2f"
            % (before.slot("A0").width, before.slot("GORE").width))
    _assert(abs(mps.at(g / Lm).slot("GORE").width - GORE_NOSE) < 1e-6,
            "the nose is fully open AT the gore, where traffic joins")
    _assert(abs(mps.at((g + NOSE_LENGTH) / Lm).slot("GORE").width) < 1e-6,
            "and closed %.0f m later, leaving the joining lane flush" % NOSE_LENGTH)
    _assert(abs(mps.at((g + ACCEL_LENGTH) / Lm).slot("A0").width - LW) < 1e-6,
            "the joining lane is held at full width for the whole acceleration run")
    _assert(mps.at(1.0).slot("A0").width < 1e-6, "and tapered away by the end")

    # An on-ramp gets MORE lane than an off-ramp: joining traffic has to reach mainline speed.
    _assert(ACCEL_LENGTH > DECEL_LENGTH, "accel must exceed decel")
    print("ramp_two_piece: ON-RAMP   mainline %.0f m UNCUT, nose closes over %.0f m, joining lane "
          "held %.0f m then tapered" % (Lm, NOSE_LENGTH, ACCEL_LENGTH))

    # ------------------------------------------------------------------------------ refusals
    for pts, ramp, why in (
            (MAIN, [(30.0, 0.0, 12.0), (90.0, 40.0, 9.0)], "gore too close to the start"),
            (MAIN, [(1200.0, 0.0, 12.0), (1260.0, 40.0, 9.0)], "gore at the very end")):
        try:
            ramp_split_pieces(pts, ramp, lanes=2, ramp_lanes=1, lane_width=LW)
            raise AssertionError("expected a refusal: %s" % why)
        except RkaBuildError:
            pass
    print("ramp_two_piece: a gore with no room for its taper, or at the road's end, is refused")

    print("smoketest_ramp_two_piece: OK")


if __name__ == "__main__":
    main()
