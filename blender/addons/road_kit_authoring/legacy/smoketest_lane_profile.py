#!/usr/bin/env python3
"""
smoketest_lane_profile.py -- `custom_props.read_profile` must describe a piece's ACTUAL geometry.

WHY THIS EXISTS. `lane_profile.py` replaces the scalar cross-section description (`rka_lanes`,
`rka_lanes_backward`, `rka_median_width`, `rka_sidewalk_*_width`, plus an `_end` twin for each)
with one ordered slot list that every consumer reads. The danger in that swap is silent geometric
drift: a migration that is merely *plausible* -- off by a median half-width, or anchored in the
mirrored frame the old pavement sweep used -- produces roads that still build, still export, and
are simply in the wrong place. `lane_profile.py`'s own self-test already pins the pure math
against `intersection_kit.carriageway_extents`; this pins it against BUILT GEOMETRY, which is the
only thing that proves the migration is faithful for content that already exists.

WHAT IS ASSERTED, for a spread of real cross-sections:
  1. the profile read back off a freshly built piece has the same extents as its swept pavement;
  2. every exported lane centreline lands on the `slot_offset` of the slot it corresponds to
     (`travel_lanes` order == export order) -- this is the assertion that would have caught
     defect 3, the split gore seeded in a different lateral frame from the lanes;
  3. a `_end` twin that differs produces a TWO-station set that reproduces both ends;
  4. a stored `rka_profile` wins over the scalars and round-trips exactly.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_lane_profile.py
(the flag matters -- blender exits 0 on an uncaught script exception without it)
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import lane_profile as lpr
import road_kit_authoring as rka  # noqa: F401  (registers the addon's operators)
from road_kit_authoring import custom_props, lane_export
from road_kit_authoring.ops_segment import _build_segment_from_points

STRAIGHT = [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (120.0, 0.0, 0.0)]   # along +X, so |y| is lateral
TOL = 1e-4


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _swept_span(ctx, spine_obj):
    dg = ctx.evaluated_depsgraph_get()
    me = spine_obj.evaluated_get(dg).to_mesh()
    ys = [(spine_obj.matrix_world @ v.co).y for v in me.vertices]
    return min(ys), max(ys)


def main():
    ctx = bpy.context
    scene_coll = ctx.scene.collection

    # (name, lanes, lanes_backward, lane_width)
    cases = [
        ("prof_oneway_3f", 3, 0, 3.5),
        ("prof_sym_2f2b", 2, 2, 3.25),
        ("prof_asym_3f2b", 3, 2, 3.5),
        ("prof_oneway_1f", 1, 0, 4.0),
    ]
    for name, fwd, back, lw in cases:
        r = _build_segment_from_points(
            ctx, scene_coll, STRAIGHT, lw, fwd, back, 'NONE', 'NONE', 0.15, 0.25,
            False, "", "", base_name=name, traffic_side='LEFT')
        coll, spine_obj = r["coll"], r["spine_obj"]

        ps = custom_props.read_profile(coll)
        _assert(ps is not None, "%s: read_profile returned None for a segment piece" % name)
        _assert(len(ps.profiles) == 1,
                "%s: no `_end` twin differs, so this must be a ONE-station set, got %d"
                % (name, len(ps.profiles)))
        prof = ps.at(0.0)

        # 1. the profile's paved extents must equal the pavement that was actually swept.
        neg, pos = lpr.paved_extents(prof)
        lo, hi = _swept_span(ctx, spine_obj)
        _assert(abs((neg + pos) - (hi - lo)) < TOL,
                "%s: profile says the carriageway is %.3f m wide (neg %.3f + pos %.3f) but the "
                "swept pavement measures %.3f m -- the migration changed the geometry"
                % (name, neg + pos, neg, pos, hi - lo))

        # 2. THE assertion: exported lane centrelines sit exactly on their slot offsets.
        #    `travel_lanes` order is forward-then-reverse, each counting outward from the divide,
        #    which is the order `intersection_kit.build_segment_from_spine` exports in.
        d = lane_export.export_piece_dict(coll, ctx.scene, godot_space=False)
        _assert(d is not None and len(d["lanes"]) == fwd + back,
                "%s: expected %d exported lanes, got %r"
                % (name, fwd + back, None if d is None else len(d["lanes"])))
        expected = lpr.travel_lanes(prof)
        _assert(len(expected) == len(d["lanes"]),
                "%s: profile describes %d drivable slots but %d lanes were exported"
                % (name, len(expected), len(d["lanes"])))
        for (slot, off, direction, k), lane in zip(expected, d["lanes"]):
            ys = set(round(p[1], 4) for p in lane["points"])
            _assert(len(ys) == 1,
                    "%s: lane %s is not a straight constant-offset line (%r)"
                    % (name, lane["id"], sorted(ys)))
            actual = ys.pop()
            _assert(abs(actual - off) < TOL,
                    "%s: lane %s (%s#%d, slot %r) is exported at y=%.4f but the profile puts "
                    "slot %r at %.4f -- lane data and the profile are in DIFFERENT lateral "
                    "frames, which is exactly the split-gore defect"
                    % (name, lane["id"], direction, k, slot.id, actual, slot.id, off))
        print("lane_profile: %-16s %dfwd/%dback -> extents (%.2f, %.2f), all %d lanes on their "
              "slot offsets" % (name, fwd, back, neg, pos, len(d["lanes"])))

    # ------------------------------------------------- an `_end` twin becomes a SECOND station
    r = _build_segment_from_points(
        ctx, scene_coll, STRAIGHT, 3.5, 2, 2, 'NONE', 'NONE', 0.15, 0.25,
        False, "", "", base_name="prof_taper", traffic_side='LEFT', lanes_end=3)
    coll = r["coll"]
    ps = custom_props.read_profile(coll)
    _assert(len(ps.profiles) == 2,
            "a piece whose lanes_end differs must read back as TWO stations, got %d"
            % len(ps.profiles))
    a, b = ps.at(0.0), ps.at(1.0)
    _assert(len(lpr.travel_lanes(a)) == 4 and len(lpr.travel_lanes(b)) == 5,
            "the two stations must carry 4 and 5 drivable slots, got %d and %d"
            % (len(lpr.travel_lanes(a)), len(lpr.travel_lanes(b))))
    mid = ps.at(0.5)
    _assert(abs(mid.slot("F2").width - 3.5 / 2.0) < TOL,
            "the added lane must be half width at the midpoint, got %.4f" % mid.slot("F2").width)
    _assert(abs(lpr.slot_offset(a, "F0") - lpr.slot_offset(b, "F0")) < TOL,
            "the lanes that persist across a taper must NOT move")
    print("lane_profile: an `_end` twin migrates to a 2-station set with a continuous width ramp")

    # ------------------------------------------------------ a stored profile wins and round-trips
    custom = lpr.ProfileSet([
        lpr.Profile([lpr.Slot("R0", lpr.TRAVEL, 3.0, lpr.REV),
                     lpr.Slot("MED", lpr.MEDIAN, 1.5),
                     lpr.Slot("F0", lpr.TRAVEL, 3.0, lpr.FWD),
                     lpr.Slot("RAMP", lpr.AUX, 0.0, lpr.FWD)]),
        lpr.Profile([lpr.Slot("R0", lpr.TRAVEL, 3.0, lpr.REV),
                     lpr.Slot("MED", lpr.MEDIAN, 1.5),
                     lpr.Slot("F0", lpr.TRAVEL, 3.0, lpr.FWD),
                     lpr.Slot("RAMP", lpr.AUX, 3.0, lpr.FWD)]),
    ], [0.0, 1.0])
    custom_props.write_profile(coll, custom)
    back = custom_props.read_profile(coll)
    _assert(back.to_dict() == custom.to_dict(),
            "a stored rka_profile must round-trip through Blender's IDProperties byte-for-byte:\n"
            "  wrote %r\n  read  %r" % (custom.to_dict(), back.to_dict()))
    _assert(back.slot_ids() == ["R0", "MED", "F0", "RAMP"], back.slot_ids())
    _assert(abs(back.at(0.5).slot("RAMP").width - 1.5) < TOL,
            "the stored profile must win over the piece's scalars, not be merged with them")
    print("lane_profile: a stored rka_profile overrides the scalars and round-trips exactly")

    print("smoketest_lane_profile: OK")


if __name__ == "__main__":
    main()
