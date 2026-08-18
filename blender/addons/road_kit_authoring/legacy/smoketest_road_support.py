#!/usr/bin/env python3
"""
smoketest_road_support.py -- headless verification of GN_RoadSupport (kit_common).

The claim under test is the one the whole surface system rests on: what goes UNDERNEATH a road
is DERIVED from `delta = deck_z - ground_z`, and nothing else. So the test builds one spine that
crosses all three regimes over flat terrain -- at grade, embankment height, viaduct height --
and checks that the evaluated modifier produces geometry only where
`island_v3_plan.support_kind()` (the pure-Python SPECIFICATION of the same rule) says it should.

That cross-check is the point. Two implementations of one rule drift silently; pinning the live
GN one to the testable Python one is what stops the piers and the spec disagreeing.

Also covers the property that makes it worth being a modifier at all: RAISING THE SPINE
RE-DERIVES THE SUPPORT with no rebuild step.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_road_support.py
"""
import bpy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(REPO, "tools"))

from road_kit_authoring import spine_io      # noqa: E402
import kit_common as kc
import island_v3_plan as P


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _spine(name, pts, coll):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    obj = bpy.data.objects.new(name, cu)
    coll.objects.link(obj)
    return obj


def _eval_vert_count(obj):
    return _eval_bounds(obj)[0]


def _eval_bounds(obj):
    """`(vert_count, min_z, max_z, lateral_width)` of the evaluated support geometry.

    The vertical reach is what distinguishes a deck from a column -- both are concrete, both come
    out of the same modifier, and a vert count cannot tell them apart. Lateral width is measured
    on Y because every spine in this test runs along X."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, depsgraph=dg)
    n = len(me.vertices)
    if not n:
        bpy.data.meshes.remove(me)
        return 0, 0.0, 0.0, 0.0
    zs = [v.co.z for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    out = (n, min(zs), max(zs), max(ys) - min(ys))
    bpy.data.meshes.remove(me)
    return out


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    coll = bpy.context.scene.collection

    # Flat terrain at z = 0 -- so delta is exactly the spine's own Z and the expected
    # classification is readable straight off the numbers below.
    terrain = kc.box("Terrain", -400, 400, -60, 60, -1.0, 0.0, coll, "dirt")

    # ---------------------------------------------------------------- rule agreement
    cases = [(0.0, P.SUPPORT_NONE), (0.2, P.SUPPORT_NONE), (2.0, P.SUPPORT_FILL),
             (3.9, P.SUPPORT_FILL), (12.0, P.SUPPORT_PIER), (-1.5, P.SUPPORT_CUT),
             (-8.0, P.SUPPORT_TUNNEL)]
    for dz, expect in cases:
        _assert(P.support_kind(dz, 0.0) == expect,
                "spec: delta=%.1f should be %s, got %s" % (dz, expect, P.support_kind(dz, 0.0)))
    print("road_support smoketest: pure-Python rule matches its own table (%d cases)" % len(cases))

    # ------------------------------------------------------- GN emits only where it should
    #
    # ONE STRUCTURE, THICKENING WITH HEIGHT (2026-08-15). The embankment primitive is gone: a road
    # above the ground gets a DECK slab under its full width, and columns appear under that slab
    # only once it is too high to stand on its own. So the test measures the geometry's VERTICAL
    # REACH rather than merely counting verts -- a deck hugs the underside of the road, while a
    # column runs all the way to the terrain, and only that distinction says which was built.
    results = {}
    for label, z in (("at_grade", 0.0), ("low", 2.5), ("viaduct", 12.0)):
        sp = _spine("spine_%s" % label,
                    [(-150.0, 0.0, z), (0.0, 0.0, z), (150.0, 0.0, z)], coll)
        kc.road_support(sp, terrain, half_width=11.0)
        n, lo, hi, wide = _eval_bounds(sp)
        results[label] = (n, lo, hi, wide)
        print("  %-9s deck z=%5.1f -> %4d verts, z %6.2f..%6.2f, width %5.2f"
              % (label, z, n, lo, hi, wide))

    _assert(results["at_grade"][0] == 0,
            "a road AT GRADE must generate no support at all, got %d verts"
            % results["at_grade"][0])

    n, lo, hi, wide = results["low"]
    _assert(n > 0, "a road at +2.5 m must still get its deck")
    _assert(abs(hi - 2.5) < 1e-3, "the deck's TOP face must sit on the driving surface (z=2.5), "
                                   "got %.3f" % hi)
    _assert(abs(lo - (2.5 - P.DECK_THICK)) < 1e-3,
            "a road below the pier threshold must reach down exactly one deck thickness "
            "(z=%.2f), not to the ground -- got %.3f" % (2.5 - P.DECK_THICK, lo))
    _assert(abs(wide - 22.0) < 1e-3,
            "the deck must span the full road width (2 x 11 m), got %.2f" % wide)

    n, lo, hi, wide = results["viaduct"]
    _assert(abs(hi - 12.0) < 1e-3, "the viaduct deck's top must sit on the road, got %.3f" % hi)
    _assert(lo < 0.5, "a road at +12 m must grow columns reaching the terrain, but its support "
                       "stops at z=%.2f -- deck only, no legs" % lo)
    print("road_support smoketest: nothing at grade; DECK alone below the pier threshold; "
          "DECK + columns to the ground above it")

    # ------------------------------------------------- live re-derivation (the whole point)
    sp = _spine("spine_live", [(-150.0, 0.0, 0.0), (0.0, 0.0, 0.0), (150.0, 0.0, 0.0)], coll)
    kc.road_support(sp, terrain, half_width=11.0)
    before = _eval_vert_count(sp)
    _assert(before == 0, "flat spine should start with no support, got %d" % before)
    for pt in spine_io.points(sp):
        pt.co = (pt.co[0], pt.co[1], 12.0, 1.0)
    sp.data.update_tag()
    bpy.context.view_layer.update()
    after = _eval_vert_count(sp)
    _assert(after > 0,
            "raising the spine to +12 m must re-derive piers WITHOUT a rebuild step; "
            "got %d verts (baked, not live?)" % after)
    print("road_support smoketest: raising the spine 0 -> +12 m re-derived support live "
          "(%d -> %d verts)" % (before, after))

    # -------------------------------------------------------- embankment toe widens with height
    for dz, expect in ((1.0, 11.0 + 1.5), (3.0, 11.0 + 4.5)):
        got = P.fill_footprint(dz, 0.0, 11.0)
        _assert(abs(got - expect) < 1e-9,
                "fill toe at delta=%.1f should be %.2f, got %.2f" % (dz, expect, got))
    _assert(P.fill_footprint(12.0, 0.0, 11.0) == 11.0,
            "a PIER stretch has no embankment toe")
    print("road_support smoketest: embankment toe widens 1:%.1f and stops at the pier threshold"
          % P.FILL_SLOPE)

    print("smoketest_road_support: OK")


if __name__ == "__main__":
    main()
