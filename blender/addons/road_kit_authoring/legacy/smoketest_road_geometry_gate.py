#!/usr/bin/env python3
"""
smoketest_road_geometry_gate.py -- a ramp that no car can hold at its design speed must FAIL the
build, and the report must say which fix applies.

WHY THIS IS A GATE AND NOT A WARNING. A too-tight ramp looks completely normal in the viewport --
it is a smooth curve, correctly paved, joined at both ends, and it passes every check the project
had. What is wrong with it is a number that only appears when you divide: `IC_RINKAI_E_ramp_001`
runs at a 20.6 m radius, and asking 45 km/h of it needs 56% superelevation. There is no bank that
rescues that; the geometry has to change. So the check has to distinguish the three cases, because
they have three different fixes and lumping them together makes the report useless:

    GRADE      too steep over a real distance   -> the climb needs more length
    SUPERELEV  needs more bank than the norm    -> bank it (it is achievable)
    RADIUS     needs more bank than physics     -> open the curve, or sign it slower

Only RADIUS fails the build; the other two are reported to be worked through.

IT RUNS ON THE LANE, NOT THE PIECE. The points checked are the ones `Preview Lane Curves` draws as
`lanepreview_<piece>_<slot>` -- a car drives a lane, and on a curve the inner lane is tighter than
the centreline it was offset from, so checking the spine flatters the geometry.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_road_geometry_gate.py
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

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import lane_export                 # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
import kit_common as kc                                    # noqa: E402
import road_geometry as rg                                 # noqa: E402

LW = 4.5


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _ramp(context, coll, radius, sweep_deg, drop_m, n=24, x0=0.0, speed=45.0, name=None):
    """A one-lane ramp: a constant-radius curve of `sweep_deg` losing `drop_m` over its length."""
    pts = []
    for i in range(n):
        t = i / float(n - 1)
        a = math.radians(sweep_deg) * t
        pts.append((x0 + radius * math.sin(a), radius * (1.0 - math.cos(a)), 12.0 - drop_m * t))
    res = opseg._build_segment_from_points(
        context, coll, pts, LW, 1, 0, 'NONE', 'NONE', 0.15, 0.25, False, "", "",
        base_name=name)
    res["coll"]["rka_design_speed"] = float(speed)
    return res["coll"]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    scene_coll = context.scene.collection

    # ------------------------------------------------------------------ three ramps, one of each
    # verdict, so the test pins that they are TOLD APART rather than all called "bad".
    _ramp(context, scene_coll, radius=120.0, sweep_deg=90.0, drop_m=8.0, name="ramp_good")
    _ramp(context, scene_coll, radius=58.0, sweep_deg=90.0, drop_m=4.0, x0=400.0,
          name="ramp_bankable")
    _ramp(context, scene_coll, radius=20.6, sweep_deg=90.0, drop_m=6.0, x0=800.0,
          name="ramp_hopeless")

    pieces = lane_export.collect_pieces("smoketest", context.scene, bpy.data, godot_space=False)
    _assert(len(pieces) == 3, "expected 3 ramp pieces, got %d" % len(pieces))

    verdicts = {}
    for coll_name, d, _z in pieces:
        for lane in d.get("lanes", []):
            _assert(lane.get("design_speed"),
                    "every lane must carry design_speed or the check silently skips it -- %s"
                    % coll_name)
            res = rg.analyse(lane["points"], float(lane["design_speed"]))
            verdicts.setdefault(coll_name, set()).update(c for c, _d in res["problems"])

    def _of(prefix):
        return next(v for k, v in verdicts.items() if k.startswith(prefix))

    _assert(not _of("ramp_good"),
            "a 120 m radius ramp at 45 km/h with a 4%% grade is a good ramp, got %r"
            % (_of("ramp_good"),))
    _assert(_of("ramp_bankable") == {"SUPERELEV"},
            "a 58 m radius ramp is bankable into compliance -- SUPERELEV, not RADIUS -- got %r"
            % (_of("ramp_bankable"),))
    _assert("RADIUS" in _of("ramp_hopeless"),
            "a 20.6 m radius ramp at 45 km/h cannot be banked into compliance at all and must be "
            "reported as RADIUS, got %r" % (_of("ramp_hopeless"),))
    print("smoketest_road_geometry_gate: the three verdicts are told apart -- good=clean, "
          "R=58m -> SUPERELEV (bank it), R=20.6m -> RADIUS (geometry must change)")

    # --------------------------------------------------------- the report must be ACTIONABLE: it
    # names the radius that would work and the speed this one honestly carries.
    hopeless = [c for c_name, d, _z in pieces if c_name.startswith("ramp_hopeless")
                for lane in d["lanes"]
                for c in [rg.analyse(lane["points"], float(lane["design_speed"]))]]
    detail = next(d for code, d in hopeless[0]["problems"] if code == "RADIUS")
    _assert("59" in detail and "km/h" in detail,
            "the RADIUS report must name the radius that WOULD work and an honest speed for the "
            "one that exists, got %r" % detail)
    print("smoketest_road_geometry_gate: %s" % detail)

    # ---------------------------------------------------------------- grade is judged over a real
    # distance. A ramp dropping 12 m over 190 m is 6.3% -- legal; the same drop over 90 m is not.
    steep = _ramp(context, scene_coll, radius=300.0, sweep_deg=17.0, drop_m=12.0, x0=1600.0,
                  name="ramp_steep")
    pieces2 = lane_export.collect_pieces("smoketest", context.scene, bpy.data, godot_space=False)
    d = next(d for n, d, _z in pieces2 if n == steep.name)
    res = rg.analyse(d["lanes"][0]["points"], 45.0)
    _assert(any(c == "GRADE" for c, _x in res["problems"]),
            "12 m of drop over ~89 m is a 13%% grade and must be reported, got %r"
            % (res["problems"],))
    print("smoketest_road_geometry_gate: a %.1f%% ramp grade is caught (%s)"
          % (res["max_grade"] * 100.0,
             next(x for c, x in res["problems"] if c == "GRADE")))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
