#!/usr/bin/env python3
"""
smoketest_curb_open_ends.py -- headless regression check for GN_CurbLoop's `Fill Caps` fix
(2026-07-28, user-reported: "align is at top of the curb of segment, not at the road level" --
a character walking a straight/curved segment toward an intersection hit a bump, because EVERY
segment's own L/R curb had a solid box-shaped end wall exactly where it meets an intersection/
another segment. Root cause: `make_curb_loop_group()`'s Curve to Mesh had `Fill Caps` hardcoded
True -- fine for a CLOSED intersection curb loop (a cyclic curve has no ends to cap, so the flag
was always a no-op there, which is why "intersection seems to work correctly" while every segment
didn't), but for an OPEN (`closed=False`) segment/transition curb it capped both ends with the
profile's own cross-section shape -- a solid curb-height block right at the connection. Fixed by
setting `Fill Caps = False` unconditionally (safe for the closed case, since there's nothing to
cap there either way).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_curb_open_ends.py
"""
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka   # noqa: E402
import kit_common as kc             # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _evaluated_mesh(obj):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    me = eo.to_mesh()
    if me is None:
        return None, None
    verts = [tuple(obj.matrix_world @ v.co) for v in me.vertices]
    tris = [tuple(p.vertices) for p in me.polygons]
    eo.to_mesh_clear()
    return verts, tris


def _has_cap_face(verts, tris, axis_idx):
    """A cap face's every vertex shares the same coordinate along `axis_idx` (the curve's travel
    direction for these axis-aligned test paths) -- i.e. a face closing off the cross-section."""
    for tri in tris:
        coords = set(round(verts[i][axis_idx], 3) for i in tri)
        if len(coords) == 1:
            return True
    return False


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    coll = kc.get_coll("TEST_OPEN_CURB")
    pts_radius = [(0.0, 0.0, 5.0, 0.0), (40.0, 0.0, 5.0, 0.0)]   # straight, no fillet needed

    for style in ('BOX', 'GUTTER'):
        curb = kc.curb_loop("Curb_%s" % style, pts_radius, coll, curb_style=style,
                             curb_height=0.15, curb_thickness=0.25, closed=False)
        verts, tris = _evaluated_mesh(curb)
        _assert(verts is not None, "%s: evaluated mesh was EMPTY" % style)
        _assert(not _has_cap_face(verts, tris, axis_idx=0),
                "%s: found a cap face at one end (all-same-X triangle) -- Fill Caps should be "
                "False for an open curb" % style)
        xs = sorted(set(round(v[0], 3) for v in verts))
        _assert(xs[0] == 0.0 and xs[-1] == 40.0,
                "%s: curb should still span the full spine length, got X range %r" % (style, xs))
        print("smoketest_curb_open_ends: open %s curb has no end-cap faces, spans %r" %
              (style, xs))

    # Sanity: a CLOSED (intersection) curb loop must still be a complete, non-degenerate mesh --
    # Fill Caps=False must not have broken the case it was always a no-op for.
    boundary = [(0.0, 0.0, 5.0, 2.0), (20.0, 0.0, 5.0, 2.0),
                (20.0, 20.0, 5.0, 2.0), (0.0, 20.0, 5.0, 2.0)]
    closed_curb = kc.curb_loop("Curb_closed", boundary, coll, curb_style='BOX',
                                curb_height=0.15, curb_thickness=0.25, closed=True)
    verts2, tris2 = _evaluated_mesh(closed_curb)
    _assert(verts2 is not None and len(tris2) > 0,
            "closed intersection curb loop broke after the Fill Caps fix (should be unaffected)")
    print("smoketest_curb_open_ends: closed intersection curb loop unaffected (%d faces)" %
          len(tris2))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
