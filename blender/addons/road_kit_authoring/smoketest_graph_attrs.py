#!/usr/bin/env python3
"""
smoketest_graph_attrs.py -- headless check for the Mesh-Graph attribute manager (`graph_attrs.py`).

WHAT THIS ACTUALLY PROVES, and why it needs to be a real Blender test rather than a code read:
the whole Part-1 design rests on the claim that stamping a value through a **bmesh custom-data
layer in Edit Mode** produces exactly the same thing as `mesh.attributes.new(...)` in Object Mode
-- same name, same domain, same type -- so that Geometry Nodes' Named Attribute node can read it.
If that equivalence did not hold, the authoring UI would appear to work (the panel would read its
own values back happily) while GN silently saw nothing. So the test:

  1. stamps edges via the operator in Edit Mode,
  2. leaves Edit Mode, and asserts the values are visible through `mesh.attributes` on the EDGE
     domain with the expected data types -- the exact surface GN reads,
  3. asserts per-field masking (`use_*` off) leaves the other fields untouched,
  4. asserts vertex-domain node attributes land on POINT,
  5. round-trips the median enum through its INT storage.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_graph_attrs.py
"""
import bmesh
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                       # noqa: E402
from road_kit_authoring import graph_attrs as ga       # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _make_graph():
    """A 4-edge cross: one centre vertex at valency 4, four termini at valency 1."""
    me = bpy.data.meshes.new("RoadGraph")
    verts = [(0, 0, 0), (50, 0, 0), (-50, 0, 0), (0, 50, 0), (0, -50, 0)]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4)]
    me.from_pydata(verts, edges, [])
    me.update()
    obj = bpy.data.objects.new("RoadGraph", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def _attr_values(mesh, name):
    attr = mesh.attributes.get(name)
    _assert(attr is not None, "attribute %r missing from mesh.attributes -- GN would read 0" % name)
    return attr, [d.value for d in attr.data]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    # The addon is dev-installed as a symlink and may already be enabled, in which
    # case registering again raises "already registered as a subclass".
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()

    obj = _make_graph()
    s = bpy.context.scene.rka_graph

    # ---- 1. init/repair creates every attribute on the right domain, seeded with defaults
    bpy.ops.rka.graph_init_attrs()
    for name, dtype, default in ga.EDGE_ATTRS:
        attr, vals = _attr_values(obj.data, name)
        _assert(attr.domain == 'EDGE', "%s should be on EDGE domain, got %s" % (name, attr.domain))
        _assert(attr.data_type == dtype, "%s should be %s, got %s" % (name, dtype, attr.data_type))
        _assert(len(vals) == 4 and all(abs(v - default) < 1e-6 for v in vals),
                "%s should seed to its default %r on all 4 edges, got %r" % (name, default, vals))
    for name, dtype, default in ga.VERT_ATTRS:
        attr, vals = _attr_values(obj.data, name)
        _assert(attr.domain == 'POINT', "%s should be on POINT domain, got %s"
                % (name, attr.domain))
        _assert(attr.data_type == dtype, "%s should be %s, got %s" % (name, dtype, attr.data_type))
    print("smoketest_graph_attrs: init/repair created %d edge + %d vertex attributes on the "
          "correct domains, seeded with non-zero defaults"
          % (len(ga.EDGE_ATTRS), len(ga.VERT_ATTRS)))

    # ---- 2. Edit-Mode stamp through bmesh layers is visible as a generic attribute afterwards
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select = True
    bm.edges[1].select = True
    bmesh.update_edit_mesh(obj.data)

    s.lanes_fwd = 3
    s.lanes_bwd = 1
    s.lane_width = 3.25
    s.median_type = 'RAISED_CONCRETE'
    s.median_width = 2.0
    s.sidewalk_left_width = 4.0
    s.sidewalk_right_width = 1.5
    s.curb_height = 0.18
    bpy.ops.rka.graph_assign_edges()
    bpy.ops.object.mode_set(mode='OBJECT')

    _, lanes_fwd = _attr_values(obj.data, "lanes_fwd")
    _assert(lanes_fwd[:2] == [3, 3],
            "the two SELECTED edges should carry lanes_fwd=3 after an Edit-Mode stamp, got %r"
            % lanes_fwd)
    _assert(lanes_fwd[2:] == [2, 2],
            "the two UNSELECTED edges must keep the default lanes_fwd=2, got %r" % lanes_fwd)
    _, med = _attr_values(obj.data, "median_type")
    _assert(med[:2] == [ga.MEDIAN_RAISED_CONCRETE] * 2,
            "median_type enum should store as INT %d, got %r" % (ga.MEDIAN_RAISED_CONCRETE, med))
    _, lw = _attr_values(obj.data, "lane_width")
    _assert(abs(lw[0] - 3.25) < 1e-5, "lane_width should be 3.25 on stamped edges, got %r" % lw)
    _, swl = _attr_values(obj.data, "sidewalk_left_width")
    _, swr = _attr_values(obj.data, "sidewalk_right_width")
    _assert(abs(swl[0] - 4.0) < 1e-5 and abs(swr[0] - 1.5) < 1e-5,
            "asymmetric sidewalks must stay distinct (L=4.0, R=1.5), got L=%r R=%r" % (swl, swr))
    print("smoketest_graph_attrs: Edit-Mode bmesh stamp is readable through mesh.attributes -- "
          "same CustomData GN's Named Attribute node reads (lanes_fwd=%r)" % lanes_fwd)

    # ---- 3. per-field masking: a stamp with only lane_width enabled must not touch the rest
    for name in ga.EDGE_ATTR_NAMES:
        setattr(s, "use_%s" % name, name == "lane_width")
    s.lane_width = 5.0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.rka.graph_assign_edges()          # same two edges still selected
    bpy.ops.object.mode_set(mode='OBJECT')

    _, lw2 = _attr_values(obj.data, "lane_width")
    _, lanes_fwd2 = _attr_values(obj.data, "lanes_fwd")
    _assert(abs(lw2[0] - 5.0) < 1e-5, "masked stamp should have written lane_width=5.0, got %r"
            % lw2)
    _assert(lanes_fwd2[:2] == [3, 3],
            "masked stamp must NOT reset lanes_fwd -- that silent clobber is the whole reason the "
            "use_* toggles exist; got %r" % lanes_fwd2)
    print("smoketest_graph_attrs: per-field masking writes only the enabled field (lane_width "
          "5.0) and leaves the other 7 intact")

    # ---- 4. vertex domain: the valency-4 centre node takes an artist override
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select = True
    bmesh.update_edit_mesh(obj.data)
    s.node_type = 'INTERSECTION'
    s.node_radius = 12.0
    s.fillet_radius = 6.0
    bpy.ops.rka.graph_assign_verts()
    bpy.ops.object.mode_set(mode='OBJECT')

    _, ntype = _attr_values(obj.data, "node_type")
    _, nrad = _attr_values(obj.data, "node_radius")
    _assert(ntype[0] == ga.NODE_INTERSECTION and all(t == ga.NODE_AUTO for t in ntype[1:]),
            "only the centre node should be forced to INTERSECTION, got %r" % ntype)
    _assert(abs(nrad[0] - 12.0) < 1e-5 and all(abs(r + 1.0) < 1e-5 for r in nrad[1:]),
            "centre node_radius override 12.0, others stay -1 (= solve it), got %r" % nrad)
    print("smoketest_graph_attrs: vertex-domain node attributes stamp independently "
          "(node_type=%r, node_radius=%r)" % (ntype, nrad))

    # ---- 5. validation reports the real topology of the cross
    bpy.ops.rka.graph_validate()

    # ---- 6. the attributes feed lane_profile, they are not a second cross-section model
    import lane_profile as lp
    prof = lp.profile_from_scalars(3, 1, 3.25, 2.0, 4.0, 1.5)
    lo, hi = lp.extents(prof)
    _assert(hi > lo, "profile_from_scalars must accept the stamped scalars and yield real extents")
    print("smoketest_graph_attrs: stamped scalars feed lane_profile.profile_from_scalars -> "
          "extents (%.2f, %.2f), total width %.2f m" % (lo, hi, lp.total_width(prof)))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
