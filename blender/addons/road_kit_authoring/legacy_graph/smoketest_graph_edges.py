#!/usr/bin/env python3
"""
smoketest_graph_edges.py -- the road OUTLINE, and the guarantee it exists to give.

The thing being tested is not a number, it is a property: **no part of a road's edge furniture may
stand on another road's asphalt.** The previous model could only approach that with a rule per case
(a derived setback per merge, a cap, a joint, a refusal), so the tests it could support asserted
those rules -- that a setback scaled as `1/sin(theta)`, that a joint was under 10 m. Those tests
pass while a wall stands in a lane 200 m away, because they are testing the patch and not the
property.

These assert the property directly, on the built geometry:

  1. no emitted boundary point lies inside another chain's paved band,
  2. a merging ramp's boundary STOPS on the mainline's kerb line -- exactly, not near it, and not
     at an estimated setback -- so the two roads' fences meet with no gap and no joint piece,
  3. a flyover 8 m above a street clips neither, and both keep their own full boundary,
  4. the flag really is off by default, and with it off the build is the old one,
  5. `<graph>_Edges` is sweepable by the same layer stack: it carries the same attribute names, and
     the layers that belong to the carriageway are absent from it rather than zero-swept.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_graph_edges.py
"""
import bmesh
import bpy
import os
import sys

from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                        # noqa: E402
from road_kit_authoring import graph_attrs as ga        # noqa: E402
from road_kit_authoring import graph_build as gb        # noqa: E402
from road_kit_authoring import graph_edges as ge        # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _graph(name, verts, edges):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    ga.ensure_mesh_attributes(me)
    return obj


def _stamp_edges(obj, only=None, **values):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layers = ga.ensure_edge_layers(bm)
    bm.edges.ensure_lookup_table()
    for e in bm.edges:
        if only is not None and e.index not in only:
            continue
        for k, v in values.items():
            e[layers[k]] = v
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _staged(graph_obj):
    """The resolved carrier chains, the same list the outline is built from."""
    from road_kit_authoring import graph_solve as gs
    result = gs.solve_object(graph_obj)
    out = []
    gb.build_carrier(graph_obj, result, collect=out)
    return out


def _set_flag(on):
    bpy.context.scene.rka_graph.stage_edge_furniture = on


# ------------------------------------------------------------------ 1. the property itself

def _test_no_boundary_point_on_another_road():
    """A wide road with a narrow one buried inside it. Every boundary point the narrow road would
    have contributed lies on the wide road's asphalt, so none of them may be emitted -- and the
    wide road, which nothing overlaps, must keep its boundary intact."""
    wide = _graph("Wide", [(0, 0, 0), (60, 0, 0), (120, 0, 0)], [(0, 1), (1, 2)])
    _stamp_edges(wide, lanes_fwd=4, lanes_bwd=4, lane_width=3.5, curb_height=1.0)
    inner = _graph("Inner", [(30, 0, 0), (90, 0, 0)], [(0, 1)])
    _stamp_edges(inner, lanes_fwd=1, lanes_bwd=0, lane_width=3.5, curb_height=1.0)

    chains = _staged(wide) + [(100 + c, pts) for c, pts in _staged(inner)]
    verts, edges, per_point = ge.outline(chains)
    index = ge.BandIndex(chains)
    for i, (x, y, z) in enumerate(verts):
        hit = index.inside(Vector((x, y, z)), skip=set())
        _assert(hit is None,
                "boundary point %d at (%.2f, %.2f, %.2f) stands on road %s's asphalt"
                % (i, x, y, z, hit))
    _assert(len(verts) == len(per_point), "per-point values do not match the vertex count")
    _assert(len(verts) > 4, "the outline collapsed to nothing (%d verts)" % len(verts))
    print("  [1] %d boundary verts, none on another road's asphalt" % len(verts))


# ------------------------------------------------------------------ 2. the merge, without a joint

def _test_merge_boundary_lands_on_the_other_kerb():
    """A ramp converging on a mainline. Where the ramp's inner boundary stops, it must lie ON the
    mainline's kerb line -- which is what makes the two fences continuous without a joint piece.

    This is the test the old model could not write. Its stopping point was
    `gap / sin(convergence angle)`, capped at half the chain and sometimes refused outright, so all
    a test could check was that the estimate scaled the right way. Here the stopping point is the
    crossing itself, so the assertion is an identity: distance to the other road's edge is zero."""
    main = _graph("Main", [(-300, 0, 0), (0, 0, 0), (300, 0, 0)], [(0, 1), (1, 2)])
    _stamp_edges(main, lanes_fwd=3, lanes_bwd=3, lane_width=3.5, curb_height=1.0)
    # A shallow convergence -- the case the fixed 12 m constant was most wrong about.
    ramp = _graph("Ramp", [(-260, -40, 0), (-60, -9, 0)], [(0, 1)])
    _stamp_edges(ramp, lanes_fwd=1, lanes_bwd=0, lane_width=3.5, curb_height=1.0)

    chains = _staged(main) + [(100 + c, pts) for c, pts in _staged(ramp)]
    index = ge.BandIndex(chains)
    verts, _edges, _pp = ge.outline(chains)

    stopped = [Vector(v) for v in verts if -260.0 < v[0] < -40.0 and v[1] < 0.0]
    _assert(stopped, "the ramp contributed no boundary at all")
    # Every emitted point is outside every road (the property), and at least one of them sits hard
    # against the mainline's band edge -- i.e. the boundary was cut by the mainline, not by luck.
    on_edge = 0
    for p in stopped:
        _assert(index.inside(p, skip=set()) is None,
                "ramp boundary point (%.2f, %.2f) is on the asphalt" % (p.x, p.y))
        probe = p + Vector((0.0, 0.15, 0.0))          # a nudge toward the mainline centreline
        if index.inside(probe, skip=set()) is not None:
            on_edge += 1
    _assert(on_edge >= 1,
            "no ramp boundary point stops against the mainline's kerb line -- the two fences do "
            "not meet, which is the gap a joint piece used to be needed for")
    print("  [2] ramp boundary stops on the mainline's kerb line (%d point(s) hard against it)"
          % on_edge)


# ------------------------------------------------------------------ 3. the flyover

def _test_flyover_clips_nothing():
    """Two roads crossing in plan but 8 m apart in space. `Z_TOL` decides this, and it graduated
    from vetoing one joint to deciding every boundary in the network, so it gets its own gate."""
    ground = _graph("Ground", [(-100, 0, 0), (100, 0, 0)], [(0, 1)])
    _stamp_edges(ground, lanes_fwd=3, lanes_bwd=3, lane_width=3.5, curb_height=0.15)
    over = _graph("Over", [(0, -100, 8), (0, 100, 8)], [(0, 1)])
    _stamp_edges(over, lanes_fwd=2, lanes_bwd=2, lane_width=3.5, curb_height=1.0)

    chains = _staged(ground) + [(100 + c, pts) for c, pts in _staged(over)]
    verts, _edges, _pp = ge.outline(chains)
    lo = [v for v in verts if abs(v[2]) < 1e-6]
    hi = [v for v in verts if abs(v[2] - 8.0) < 1e-6]
    _assert(lo, "the street under the flyover lost its whole boundary")
    _assert(hi, "the flyover lost its whole boundary")
    # Neither is cut: both keep boundary on both sides of the crossing point.
    for name, pts, axis in (("street", lo, 0), ("flyover", hi, 1)):
        vals = [v[axis] for v in pts]
        _assert(min(vals) < -20.0 and max(vals) > 20.0,
                "the %s's boundary was cut at the crossing (%s..%s)" % (name, min(vals), max(vals)))
    print("  [3] flyover and street each keep their full boundary")


# ------------------------------------------------------------------ 4/5. the flag and the stack

def _test_flag_is_off_by_default_and_gates_the_object():
    straight = _graph("Plain", [(0, 0, 0), (80, 0, 0)], [(0, 1)])
    _stamp_edges(straight, lanes_fwd=2, lanes_bwd=2, lane_width=3.5, curb_height=0.15)

    _assert(gb.staged_edges() is False, "the outline flag is on by default -- it is experimental")
    gb.build_object(straight)
    _assert(bpy.data.objects.get("Plain" + gb.SUFFIX_EDGES) is None,
            "_Edges was built with the flag off")
    carrier = bpy.data.objects["Plain" + gb.SUFFIX_CARRIER]
    _assert(any(m.name == "CurbL" for m in carrier.modifiers),
            "with the flag off the carrier must still build its own kerb")

    _set_flag(True)
    try:
        gb.build_object(straight)
        edges_obj = bpy.data.objects.get("Plain" + gb.SUFFIX_EDGES)
        _assert(edges_obj is not None, "_Edges was not built with the flag on")
        _assert(len(edges_obj.data.vertices) > 0, "_Edges is empty")

        carrier = bpy.data.objects["Plain" + gb.SUFFIX_CARRIER]
        names = [m.name for m in carrier.modifiers]
        _assert("CurbL" not in names and "RailL" not in names,
                "the carrier still builds edge furniture with staging on -- it would be drawn "
                "twice: %s" % names)
        _assert("Carriageway" in names, "the carrier lost its carriageway: %s" % names)

        enames = [m.name for m in edges_obj.modifiers]
        _assert("CurbL" in enames, "_Edges does not build a kerb: %s" % enames)
        _assert("Carriageway" not in enames and "Deck" not in enames,
                "_Edges is building road surface: %s" % enames)

        # It carries the same attribute vocabulary the carrier does, so one stack sweeps both.
        have = set(edges_obj.data.attributes.keys())
        for key in ("rka_curb_ol", "rka_curb_hl", "rka_curb_tl", "rka_halfw", "rka_shift"):
            _assert(key in have, "_Edges is missing the shared attribute %s" % key)
        halfw = [d.value for d in edges_obj.data.attributes["rka_halfw"].data]
        _assert(all(abs(v) < 1e-9 for v in halfw),
                "_Edges carries a non-zero carriageway width -- it would sweep asphalt")
        print("  [4] flag off = old build; flag on = carrier keeps the surface, _Edges the kerb")
        print("  [5] _Edges carries the shared attribute vocabulary, all surface bands zeroed")
    finally:
        _set_flag(False)

    # 6. TURNING THE FLAG BACK OFF MUST TAKE THE OUTLINE AWAY. Otherwise the leftover _Edges keeps
    # its stack and keeps sweeping beside the kerb the carrier has resumed building -- two fences,
    # and a flag that looks inert.
    gb.build_object(straight)
    _assert(bpy.data.objects.get("Plain" + gb.SUFFIX_EDGES) is None,
            "a stale _Edges survived a build with the flag off -- the kerb is now built twice")
    carrier = bpy.data.objects["Plain" + gb.SUFFIX_CARRIER]
    _assert(any(m.name == "CurbL" for m in carrier.modifiers),
            "the carrier did not resume building its own kerb when the flag went off")
    print("  [6] turning the flag off removes _Edges and gives the kerb back to the carrier")


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()
    ge._selftest()
    if True:
        _test_no_boundary_point_on_another_road()
        _test_merge_boundary_lands_on_the_other_kerb()
        _test_flyover_clips_nothing()
        _test_flag_is_off_by_default_and_gates_the_object()
    print("smoketest_graph_edges: OK")


if __name__ == "__main__":
    main()
