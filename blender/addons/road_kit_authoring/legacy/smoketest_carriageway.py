#!/usr/bin/env python3
"""
smoketest_carriageway.py -- a whole expressway carriageway is ONE piece.

WHY THIS EXISTS. A carriageway used to come out as many pieces: one mainline piece per
interchange, plus an ordinary chunk between each pair. None of that was a property of the road --
measured on `LOOP_A`, a 3,278 m ring with ZERO crossing cuts (flyovers deliberately do not cut it
and nothing meets the deck at grade). It was purely that a piece could carry one lane COUNT, so
every place the count changed had to become a new piece. `carriageway_pieces` puts every
interchange on one profile instead.

The properties worth pinning, in the order they matter:

  * ONE piece, as long as the carriageway it was given
  * the mainline's own lanes never change width anywhere along it
  * each interchange's auxiliary lane opens and closes only around ITS OWN gore
  * OVERLAPPING interchanges coexist -- neither closes the other's lane (this is the case a
    per-interchange "plain elsewhere" profile got wrong, and `JCT_AIRPORT` really does begin 24 m
    before its neighbour's approach ends)
  * every ramp seeds on its own slot, so traffic can drive through the gore

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_carriageway.py
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
from road_kit_authoring.ops_split import carriageway_pieces, GORE_NOSE, NOSE_LENGTH
from road_kit_authoring.ops_intersection import RkaBuildError

LW = 3.5
MAIN = [(float(x), 0.0, 12.0) for x in range(0, 3301, 20)]
# IC_B's ENTRY deliberately overlaps IC_A's EXIT -- the JCT_AIRPORT situation.
ICS = [("IC_A", [(800.0, 0.0, 12.0), (880.0, 40.0, 9.0), (960.0, 90.0, 5.0)], 'split'),
       ("IC_B", [(700.0, 90.0, 5.0), (760.0, 40.0, 9.0), (820.0, 0.0, 12.0)], 'merge'),
       ("IC_C", [(2400.0, 0.0, 12.0), (2480.0, 40.0, 9.0), (2560.0, 90.0, 5.0)], 'split')]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _plen(pts):
    return sum(math.dist(a[:3], b[:3]) for a, b in zip(pts, pts[1:]))


def main():
    bpy.ops.wm.read_homefile(use_empty=True)

    p = carriageway_pieces(MAIN, ICS, lanes=2, lane_width=LW)
    _assert(sorted(k for k in p if not k.startswith("_")) == ["IC_A", "IC_B", "IC_C", "mainline"],
            "one mainline plus one piece per ramp, got %s" % sorted(p))

    ml = p["mainline"]
    L = _plen(ml["pts"])
    _assert(abs(L - _plen(MAIN)) < 1e-6,
            "the carriageway must be ONE piece as long as it was given: %.1f vs %.1f"
            % (_plen(MAIN), L))
    ps = ml["profile_set"]
    fr = [0.0]
    for a, b in zip(ml["pts"], ml["pts"][1:]):
        fr.append(fr[-1] + math.dist(a[:3], b[:3]))
    fr = [s / L for s in fr]

    widths = {round(sum(s.width for s in ps.at(f).slots if s.id.startswith("B")), 6) for f in fr}
    _assert(widths == {round(2 * LW, 6)},
            "the mainline's own lanes must not change width anywhere, got %s" % widths)

    # Every interchange contributes its own slots, and only around its own gore.
    for rid, _pts, kind in ICS:
        run = next((r for r in lp.lane_runs(ps, len(ml["pts"]), fractions=fr)
                    if r["slot_id"] == "%s_A0" % rid), None)
        _assert(run is not None, "%s's ramp lane must appear in the mainline's lane runs" % rid)
        g = p["_gores"][rid]["station"]
        lo, hi = fr[run["i0"]] * L, fr[run["i1"]] * L
        _assert(abs(lo - g) < 400.0 and abs(hi - g) < 400.0,
                "%s's auxiliary lane runs %.0f..%.0f m but its gore is at %.0f m -- a lane must "
                "only exist around its OWN interchange" % (rid, lo, hi, g))

    # THE OVERLAP. IC_A exits at 800 m and IC_B enters at 820 m, so their taper regions overlap.
    # Neither may close the other's lane: before this composed every interchange at every station,
    # each one emitted a "plain" profile for the stretches it did not care about, which asserted
    # something about the WHOLE cross-section and cancelled its neighbour.
    a_gore = p["_gores"]["IC_A"]["station"]
    b_gore = p["_gores"]["IC_B"]["station"]
    _assert(abs(a_gore - b_gore) < 60.0, "the fixture must actually overlap (%.0f vs %.0f)"
            % (a_gore, b_gore))
    a_open = [f for f in fr if ps.at(f).slot("IC_A_A0").width > 1e-6]
    b_open = [f for f in fr if ps.at(f).slot("IC_B_A0").width > 1e-6]
    _assert(a_open and b_open,
            "BOTH overlapping interchanges must keep their auxiliary lane: A=%d stations, "
            "B=%d stations" % (len(a_open), len(b_open)))
    _assert(max(a_open) * L <= a_gore + 1.0,
            "IC_A's exit lane must end AT its gore, not be carried past it by its neighbour")
    _assert(min(b_open) * L >= b_gore - 1.0,
            "IC_B's entry lane must not start before its own gore")

    # The nose is shut while each auxiliary lane runs flush, on a shared piece just as on its own.
    for rid, _pts, kind in ICS:
        g = p["_gores"][rid]["station"]
        probe = (g - NOSE_LENGTH - 20.0) if kind == 'split' else (g + NOSE_LENGTH + 20.0)
        if 0.0 < probe < L:
            pr = ps.at(probe / L)
            if pr.slot("%s_A0" % rid).width > 1e-6:
                _assert(pr.slot("%s_GORE" % rid).width < 1e-6,
                        "%s: the lane must run FLUSH outside the %.0f m nose run (gore was %.2f m "
                        "open at %.0f m)" % (rid, NOSE_LENGTH, pr.slot("%s_GORE" % rid).width,
                                             probe))
        _assert(abs(ps.at(g / L).slot("%s_GORE" % rid).width - GORE_NOSE) < 1e-6,
                "%s: the nose must be fully open exactly at its gore" % rid)

    # Each ramp seeds on its own slot's centreline -- what lets the runtime pair the lanes.
    for rid, _pts, _kind in ICS:
        op = p["_gores"][rid]["profile"]
        want = lp.slot_offset(op, "%s_A0" % rid)
        got = p["_gores"][rid]["offset_a"] + LW / 2.0
        _assert(abs(want - got) < 1e-6,
                "%s's ramp must seed on its own slot: slot %.3f, seed %.3f" % (rid, want, got))
    print("carriageway: ONE %.0f m piece carrying %d interchanges (%d stations), mainline lanes "
          "fixed, overlapping interchanges both keep their lane"
          % (L, len(ICS), len(ps.stations)))

    # ------------------------------------------------------------------------------ refusals
    try:
        carriageway_pieces(MAIN, [("IC_X", [(40.0, 0.0, 12.0), (90.0, 40.0, 9.0)], 'split')],
                           lanes=2, lane_width=LW)
        raise AssertionError("an exit with no room for its taper must be refused")
    except RkaBuildError as exc:
        _assert("taper" in str(exc), "the refusal should say what does not fit: %s" % exc)
    print("carriageway: an interchange with no room for its taper is refused with a reason")

    print("smoketest_carriageway: OK")


if __name__ == "__main__":
    main()
