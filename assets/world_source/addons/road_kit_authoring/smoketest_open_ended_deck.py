#!/usr/bin/env python3
"""
smoketest_open_ended_deck.py -- headless regression check for GN_RoadProfile's pavement surface
(2026-07-28, history below).

Originally written for an end-cap-removal fix: once a shading fix stopped hiding it, every
segment's own end cap read as a visible solid wall blocking the road at every connection --
Extrude Mesh automatically walled off ALL open boundary edges of the swept deck, including the two
short curve-endpoint edges, not just the two long sides.

Later the SAME day, a deeper bug surfaced: the whole extruded-deck pipeline never actually had a
genuine top surface. Extrude Mesh RELOCATES the selected face to the offset position and walls its
boundary -- it does not leave a face behind at the original position (standard Blender behavior for
extruding an isolated flat region with nothing else attached to anchor it). So the "road" every
screenshot showed was actually the relocated BOTTOM face (normal still +Z, so it looked plausible),
sitting a full `thickness` below road_z -- a real Godot raycast straight down through the baked
collision confirmed it, falling through to road_z - thickness instead of road_z. This went
undetected through several earlier verification passes because a naive vertex-Z-range check still
shows both heights present (from the side walls' own vertices) even with the top face completely
missing.

The user's own follow-up question ("why is the road a box being pushed down, why not just a
plane, like the intersection pad?") was the actual fix: `GN_RoadProfile` no longer extrudes at
all -- it's a flat Curve-to-Mesh ribbon exactly like `GN_JunctionPad`'s Fill Curve output, with no
side walls, no end caps, and no top/bottom distinction to ever get wrong again. This test now
verifies that flat-plane invariant directly: exactly ONE face per span, every vertex at road_z,
normal facing up, for 2/3/5-point spines (the case counts that broke earlier end-cap-deletion
attempts).

RUN: blender --background --python addons/road_kit_authoring/smoketest_open_ended_deck.py
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
        return None
    faces = [([tuple(round(c, 3) for c in me.vertices[i].co) for i in p.vertices],
              tuple(round(c, 3) for c in p.normal)) for p in me.polygons]
    eo.to_mesh_clear()
    return faces


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    coll = kc.get_coll("TEST")
    road_z = 5.0

    cases = {
        "2-point (single-span)": ([(0.0, 0.0, road_z), (40.0, 0.0, road_z)], 1),
        "3-point": ([(0.0, 0.0, road_z), (20.0, 0.0, road_z), (40.0, 0.0, road_z)], 2),
        "5-point": ([(0.0, 0.0, road_z), (10.0, 0.0, road_z), (20.0, 0.0, road_z),
                     (30.0, 0.0, road_z), (40.0, 0.0, road_z)], 4),
    }

    for i, (label, (pts, n_spans)) in enumerate(cases.items()):
        spine = kc.road_spine("R%d" % i, pts, coll, 5.0)
        faces = _evaluated_mesh(spine)
        _assert(faces is not None, "%s: evaluated mesh was EMPTY (None)" % label)
        _assert(len(faces) == n_spans,
                "%s: expected exactly %d face(s) (one flat span per pair of control points, no "
                "side walls/end caps -- GN_RoadProfile is a flat ribbon now), got %d: %r"
                % (label, n_spans, len(faces), [n for _, n in faces]))
        for verts, normal in faces:
            _assert(all(abs(v[2] - road_z) < 0.01 for v in verts),
                    "%s: a face has a vertex off road_z=%.2f: %r" % (label, road_z, verts))
            _assert(normal[2] > 0.9,
                    "%s: face normal %r should point up (+Z)" % (label, normal))
        print("smoketest_open_ended_deck: %s spine is a flat ribbon, %d face(s), all at "
              "road_z=%.2f facing up" % (label, len(faces), road_z))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
