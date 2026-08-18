#!/usr/bin/env python3
"""
smoketest_carriageway_chunks.py -- the expressway as a CHAIN OF SEGMENTS.

WHY THIS EXISTS. `carriageway_pieces`/`two_way_carriageway_pieces` build a whole expressway as ONE
piece whose ProfileSet carries every interchange. That works, and it makes the expressway the only
road on the map that is not shaped like the rest of it: everything else is ordinary segments
meeting at authored joints. `carriageway_chunk_pieces` builds the same road out of those same
ordinary segments -- plain deck chunks, and one chunk per interchange carrying ONE EXTRA LANE on
the side that needs it.

WHAT IS ASSERTED, and why each one is the property that actually matters rather than a count:

  * consecutive chunks SHARE AN ENDPOINT. If they do not, there is no seam to author and the
    expressway is a row of disconnected roads -- the exact failure the island already had once
    (`ROAD_KIT_MIGRATION_STATUS.md` Step 5, defect 2).
  * every chunk begins and ends on the PLAIN cross-section. This is what makes a chunk boundary an
    ordinary segment<->segment joint: lane edges on both sides of the seam line up because both
    sides are the same road. A chunk that ended mid-taper would hand over a cross-section nothing
    matches, and `lane_joints` would report it MISALIGNED.
  * the FINAL SPAN of every chunk is a real span, not the 1 cm one the one-piece model leaves at
    each gore. A port's direction is read from the last two points; 1 cm of taper is not the road's
    heading. This is what `GORE_RUNOUT` is for.
  * an interchange chunk carries exactly one extra DRIVABLE slot, on the requested side, reaching
    full lane width -- "a different segment with an extra lane on the required side".
  * the auxiliary lane STOPS AT ITS GORE. Past the gore that lane is the ramp; a lane exported
    alongside the ramp would be a phantom the traffic graph can drive down.
  * an interchange sitting across the ring's SEAM still comes out as one contiguous chunk.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_carriageway_chunks.py
(the flag matters -- blender exits 0 on an uncaught script exception without it)
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
from road_kit_authoring.ops_split import (carriageway_chunk_pieces, GORE_NOSE, GORE_RUNOUT,
                                          DECEL_LENGTH, TAPER_LENGTH)
from road_kit_authoring.ops_intersection import RkaBuildError

LW = 3.5
MED = 1.2
# A straight 3,300 m deck along +X, so |y| reads directly as lateral offset.
MAIN = [(float(x), 0.0, 12.0) for x in range(0, 3301, 20)]
# IC_B's ENTRY deliberately overlaps IC_A's EXIT -- the JCT_AIRPORT situation, which must come out
# as ONE chunk carrying both auxiliary lanes rather than two chunks fighting over the same stretch.
ICS = [("IC_A", [(800.0, 0.0, 12.0), (880.0, 40.0, 9.0), (960.0, 90.0, 5.0)], 'split', lp.FWD),
       ("IC_B", [(700.0, 90.0, 5.0), (760.0, 40.0, 9.0), (820.0, 0.0, 12.0)], 'merge', lp.FWD),
       ("IC_C", [(2400.0, 0.0, 12.0), (2480.0, 40.0, 9.0), (2560.0, 90.0, 5.0)], 'split',
        lp.REV)]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _plen(pts):
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:]))


def _fractions(pts):
    st = [0.0]
    for a, b in zip(pts, pts[1:]):
        st.append(st[-1] + math.dist(a[:2], b[:2]))
    total = st[-1] or 1.0
    return [s / total for s in st]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)

    out = carriageway_chunk_pieces(MAIN, ICS, lanes=2, lane_width=LW, median=MED)
    chunks, ramps, gores = out["chunks"], out["ramps"], out["gores"]

    _assert(sorted(ramps) == ["IC_A", "IC_B", "IC_C"],
            "one piece per ramp, got %s" % sorted(ramps))
    _assert(len(chunks) >= 4, "a deck with 3 interchanges is at least 4 chunks, got %d"
            % len(chunks))

    # --- the chain: one road, cut into pieces that meet ---------------------------------------
    total = _plen(MAIN)
    covered = sum(_plen(c["pts"]) for c in chunks)
    _assert(abs(covered - total) < 1.0,
            "the chunks must cover the whole carriageway exactly once: %.1f m of chunk for a "
            "%.1f m deck" % (covered, total))
    for a, b in zip(chunks, chunks[1:]):
        gap = math.dist(a["pts"][-1][:3], b["pts"][0][:3])
        _assert(gap < 1e-3,
                "consecutive chunks must SHARE their endpoint (there is no seam to author "
                "otherwise) -- %.4f m apart" % gap)

    # --- every chunk hands over on the PLAIN cross-section -------------------------------------
    plain = None
    for c in chunks:
        if not c["interchanges"]:
            plain = c["profile_set"].at(0.0)
            break
    _assert(plain is not None, "the fixture must produce at least one plain deck chunk")
    want = lp.paved_extents(plain)
    for i, c in enumerate(chunks):
        for label, t in (("start", 0.0), ("end", 1.0)):
            got = lp.paved_extents(c["profile_set"].at(t))
            _assert(abs(got[0] - want[0]) < 1e-6 and abs(got[1] - want[1]) < 1e-6,
                    "chunk %d (%s) must hand over on the plain cross-section at its %s: "
                    "%.3f..%.3f against the deck's %.3f..%.3f"
                    % (i, ",".join(c["interchanges"]) or "plain", label,
                       got[0], got[1], want[0], want[1]))

    # --- no chunk ends on a 1 cm span (that is what GORE_RUNOUT bought) -------------------------
    for i, c in enumerate(chunks):
        for label, (p, q) in (("first", (c["pts"][0], c["pts"][1])),
                              ("last", (c["pts"][-2], c["pts"][-1]))):
            d = math.dist(p[:2], q[:2])
            _assert(d > 1.0,
                    "chunk %d's %s span is %.3f m -- a port's direction is read from it, so it "
                    "may not be a taper stub" % (i, label, d))

    # --- an interchange chunk IS a segment with one extra lane on the required side -------------
    for rid, _pts, kind, side in ICS:
        c = next((c for c in chunks if rid in c["interchanges"]), None)
        _assert(c is not None, "%s must live on some chunk" % rid)
        ps = c["profile_set"]
        fr = _fractions(c["pts"])
        runs = lp.lane_runs(ps, len(c["pts"]), fractions=fr)
        mine = [r for r in runs if r["slot_id"] == "%s_A0" % rid]
        _assert(len(mine) == 1, "%s must contribute exactly one drivable lane, got %d"
                % (rid, len(mine)))
        run = mine[0]
        _assert(run["dir"] == side,
                "%s's extra lane must be on the %s side, got %s" % (rid, side, run["dir"]))
        _assert(abs(max(run["widths"]) - LW) < 1e-6,
                "%s's extra lane must reach a full lane width, peaked at %.3f"
                % (rid, max(run["widths"])))
        # It is an EXTRA lane: the chunk carries one more drivable slot than the plain deck.
        n_plain = len([s for s in plain.slots if s.is_drivable()])
        _assert(len(runs) == n_plain + len(c["interchanges"]),
                "chunk carrying %s must have %d + %d drivable lanes, got %d"
                % (rid, n_plain, len(c["interchanges"]), len(runs)))

        # --- and it stops at its own gore ------------------------------------------------------
        # `station` is measured along the whole deck; the chunks tile it in order, so the chunk's
        # own start station is the length of everything before it.
        L = _plen(c["pts"])
        s_gore = gores[rid]["station"]
        chunk_s0 = sum(_plen(x["pts"]) for x in chunks[:chunks.index(c)])
        lo, hi = fr[run["i0"]] * L + chunk_s0, fr[run["i1"]] * L + chunk_s0
        if kind == 'split':
            _assert(hi <= s_gore + 1.0,
                    "%s's exit lane must end AT its gore (%.1f m), not run %.1f m past it"
                    % (rid, s_gore, hi - s_gore))
        else:
            _assert(lo >= s_gore - 1.0,
                    "%s's entry lane must not start before its own gore (%.1f m vs %.1f m)"
                    % (rid, lo, s_gore))

        # --- the nose is fully open exactly at the gore ----------------------------------------
        g_t = (s_gore - chunk_s0) / L
        _assert(abs(ps.at(g_t).slot("%s_GORE" % rid).width - GORE_NOSE) < 1e-3,
                "%s: the gore island must be fully open at its gore, got %.3f"
                % (rid, ps.at(g_t).slot("%s_GORE" % rid).width))

    # --- the overlapping pair share ONE chunk --------------------------------------------------
    shared = next((c for c in chunks if "IC_A" in c["interchanges"]), None)
    _assert("IC_B" in shared["interchanges"],
            "IC_A's exit and IC_B's entry overlap, so they must be ONE chunk carrying both "
            "auxiliary lanes -- got %s" % shared["interchanges"])
    _assert(shared["exits"] == ["IC_A"] and shared["entries"] == ["IC_B"],
            "a chunk must record which of its interchanges are exits and which are entries: "
            "%s / %s" % (shared["exits"], shared["entries"]))

    # --- each ramp seeds on its own slot's centreline -------------------------------------------
    for rid, _pts, _kind, _side in ICS:
        op = gores[rid]["profile"]
        want_off = lp.slot_offset(op, op.index_of("%s_A0" % rid))
        got = gores[rid]["offset_a"] + (LW / 2.0 if gores[rid]["side"] == lp.FWD else -LW / 2.0)
        _assert(abs(want_off - got) < 1e-6,
                "%s's ramp must seed on its own slot: slot %.3f, seed %.3f" % (rid, want_off, got))

    print("carriageway chunks: %d segments (%d plain, %d interchange) covering %.0f m, "
          "%d ramps, every seam shared and every hand-over plain"
          % (len(chunks), len([c for c in chunks if not c["interchanges"]]),
             len([c for c in chunks if c["interchanges"]]), covered, len(ramps)))

    # ---------------------------------------------------------------- the ring seam ------------
    # A closed ring whose ONLY interchange sits right at the authored start point. Unrolled
    # naively, its window is split between station 0 and station `total` -- half an auxiliary lane
    # at each end of the road, meeting nothing. The seam is moved instead.
    R = 600.0
    ring = [(R * math.cos(a * math.pi / 180.0), R * math.sin(a * math.pi / 180.0), 12.0)
            for a in range(0, 360, 3)]
    seam_ic = [("IC_S", [(R, 0.0, 12.0), (R + 60.0, 40.0, 9.0), (R + 120.0, 90.0, 5.0)],
                'split', lp.FWD)]
    ring_out = carriageway_chunk_pieces(ring, seam_ic, lanes=2, lane_width=LW, median=MED,
                                        closed=True)
    ic_chunks = [c for c in ring_out["chunks"] if "IC_S" in c["interchanges"]]
    _assert(len(ic_chunks) == 1,
            "an interchange on the ring's authored seam must still be ONE chunk, got %d"
            % len(ic_chunks))
    c = ic_chunks[0]
    want_len = DECEL_LENGTH + TAPER_LENGTH + GORE_RUNOUT
    _assert(abs(_plen(c["pts"]) - want_len) < 5.0,
            "the seam interchange chunk must be its whole window long (%.0f m), got %.0f m"
            % (want_len, _plen(c["pts"])))
    ring_total = _plen(ring) + math.dist(ring[-1][:2], ring[0][:2])
    covered = sum(_plen(x["pts"]) for x in ring_out["chunks"])
    _assert(abs(covered - ring_total) < 1.0,
            "the ring's chunks must cover it exactly once: %.1f vs %.1f" % (covered, ring_total))
    print("ring seam: interchange at the authored start point comes out as one %.0f m chunk; "
          "%d chunks cover the %.0f m ring" % (_plen(c["pts"]), len(ring_out["chunks"]),
                                               ring_total))

    # ------------------------------------------------------------------------------ refusals
    try:
        carriageway_chunk_pieces(MAIN, [("IC_X", [(40.0, 0.0, 12.0), (90.0, 40.0, 9.0)],
                                         'split', lp.FWD)], lanes=2, lane_width=LW, median=MED)
        raise AssertionError("an exit with no room for its taper must be refused")
    except RkaBuildError as exc:
        _assert("needs" in str(exc), "the refusal should say what does not fit: %s" % exc)

    print("SMOKETEST carriageway_chunks: OK")


main()
