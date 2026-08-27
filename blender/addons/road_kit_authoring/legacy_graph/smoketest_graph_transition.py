#!/usr/bin/env python3
"""
smoketest_graph_transition.py -- how a road's WIDTH varies along a chain.

Three things share one mechanism (`graph_build.chain_lane_counts`, a per-point lane count fed to
`graph_solve.offsets_for_counts`), and each fails silently in its own way:

  1. A LANE COUNT CHANGE IS A TAPER, NOT A STEP. Two edges stamped 2 and 4 lanes used to jump the
     ribbon's width at the vertex between them -- a wall across half the carriageway. It must open
     one lane at a time (2 -> 3 -> 4), with a real vertex at the whole-lane state in between.
  2. THE TWO CARRIAGEWAYS TAPER INDEPENDENTLY. A stretch between two gores carries an auxiliary
     lane on EACH side, each serving its own ramp at its own end. One shared scale necessarily
     opened one of them at the wrong end -- measured on the island, both sides full at both ends
     and shut in the middle, which closes the exit lane in front of the car meant to take it.
  3. A SHORT WEAVE STAYS OPEN. Where the same side is served at both ends and the gap is short,
     the auxiliary lane is one continuous lane (the "normal 3 lane" stretch between an entry and
     the next exit), not one that shuts and reopens over a few hundred metres.

RUN: blender --background --python-exit-code 1 --python \\
       addons/road_kit_authoring/smoketest_graph_transition.py
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

import road_kit_authoring as rka                        # noqa: E402
from road_kit_authoring import graph_attrs as ga        # noqa: E402
from road_kit_authoring import graph_build as gb        # noqa: E402
from road_kit_authoring import graph_solve as gs        # noqa: E402


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


def _stamp_edges(obj, **values):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layers = ga.ensure_edge_layers(bm)
    for e in bm.edges:
        for k, v in values.items():
            e[layers[k]] = v
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _pt(attrs, forward=True):
    return (attrs, forward)


def _chain(attr_runs, step=10.0):
    """`[(co, (attrs, forward)), ...]` -- `attr_runs` is `[(attrs, point count), ...]`."""
    from mathutils import Vector
    out = []
    for attrs, n in attr_runs:
        for _ in range(n):
            out.append((Vector((step * len(out), 0.0, 0.0)), _pt(attrs)))
    return out


def test_lane_transition_is_stepped():
    """2 -> 4 lanes opens one lane at a time over one `lane_transition_length` each."""
    T = 60.0
    a = {"lanes_fwd": 2, "lanes_bwd": 0, "lane_width": 3.5, "lane_transition_length": T}
    b = dict(a, lanes_fwd=4)
    pts = _chain([(a, 21), (b, 20)])          # 200 m of 2-lane, then 200 m of 4-lane
    out, counts, _opens = gb.chain_lane_counts(pts, (0, 1), set())
    dists, total = gb._arclengths(out)
    at = dict(zip([round(d, 3) for d in dists], [c[0] for c in counts]))
    _assert(abs(at.get(140.0, -1) - 2.0) < 1e-6,
            "the transition must begin one transition-length per lane before the joint, got %r"
            % at.get(140.0))
    _assert(abs(at.get(200.0, -1) - 3.0) < 1e-6,
            "a 2 -> 4 change must pass through a whole 3-lane state at the joint, got %r"
            % at.get(200.0))
    _assert(abs(at.get(260.0, -1) - 4.0) < 1e-6,
            "the transition must finish one transition-length per lane after the joint, got %r"
            % at.get(260.0))
    steps = [abs(counts[i + 1][0] - counts[i][0]) for i in range(len(counts) - 1)]
    _assert(max(steps) < 1.0,
            "the lane count must never step by a whole lane between two points, worst %.2f"
            % max(steps))
    print("smoketest_graph_transition: 2 -> 3 -> 4 lanes over %.0f m, no step > %.2f lane"
          % (2 * T, max(steps)))


def test_transition_geometry_never_jumps():
    """The same thing measured on the BUILT ribbon, which is what a player drives on."""
    T, LW = 60.0, 3.5
    obj = _graph("Widen", [(0, 0, 0), (200, 0, 0), (400, 0, 0)], [(0, 1), (1, 2)])
    obj.data.attributes["node_type"].data[1].value = ga.NODE_NONE
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=0, lane_width=LW, lane_transition_length=T,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb_left_on=0,
                 curb_right_on=0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    layers = ga.ensure_edge_layers(bm)
    bm.edges[1][layers["lanes_fwd"]] = 4
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    _result, carrier = gb.build_object(obj)
    hw = carrier.data.attributes["rka_halfw"]
    row = sorted([(v.co.x, hw.data[i].value) for i, v in enumerate(carrier.data.vertices)])
    _assert(abs(row[0][1] - LW) < 1e-3 and abs(row[-1][1] - 2 * LW) < 1e-3,
            "the ribbon must be 2 lanes wide at one end and 4 at the other, got %.2f / %.2f"
            % (row[0][1], row[-1][1]))
    mid = [w for x, w in row if abs(x - 200.0) < 1e-3]
    _assert(mid and abs(mid[0] - 1.5 * LW) < 1e-3,
            "there must be a vertex at the joint carrying exactly the 3-lane half-width "
            "(%.2f), got %r" % (1.5 * LW, mid))
    # MEASURED PER METRE, not per point: a taper is a straight edge and needs only its two ends,
    # so "no big step between adjacent points" would pass on a ribbon that doubles its width
    # across a 1 m segment. The rate is what makes it a taper.
    rate = max(abs(row[i + 1][1] - row[i][1]) / max(row[i + 1][0] - row[i][0], 1e-6)
               for i in range(len(row) - 1))
    _assert(rate <= (LW / 2.0) / T + 1e-6,
            "the ribbon must not widen faster than one lane per transition length (%.4f m/m), "
            "got %.4f" % ((LW / 2.0) / T, rate))
    print("smoketest_graph_transition: swept ribbon %.2f -> %.2f m half-width, widening at most "
          "%.4f m/m" % (row[0][1], row[-1][1], rate))
    bpy.data.objects.remove(obj, do_unlink=True)


def test_sides_taper_independently():
    """Each carriageway's aux lane is full width at ITS OWN gore and closed at the other."""
    a = {"lanes_fwd": 2, "lanes_bwd": 2, "lane_width": 3.5, "aux_lanes_left": 1,
         "aux_lanes_right": 1, "aux_taper_length": 90.0}
    pts = _chain([(a, 101)])                                    # 1000 m, gores at both ends
    # The gore at node 0 serves the BACKWARD group, the one at node 1 the FORWARD group.
    services = {(0, 7): {False}, (1, 7): {True}}
    _out, counts, _opens = gb.chain_lane_counts(pts, (0, 1), {0, 1}, services, 7)
    f, b = [c[0] for c in counts], [c[1] for c in counts]
    _assert(abs(f[-1] - 3.0) < 1e-6 and abs(f[0] - 2.0) < 1e-6,
            "the forward aux lane must be full at ITS gore and closed at the other, got %.2f -> "
            "%.2f" % (f[0], f[-1]))
    _assert(abs(b[0] - 3.0) < 1e-6 and abs(b[-1] - 2.0) < 1e-6,
            "the backward aux lane must be full at ITS gore and closed at the other, got %.2f -> "
            "%.2f" % (b[0], b[-1]))
    print("smoketest_graph_transition: sides taper independently -- fwd %.1f->%.1f, bwd %.1f->%.1f"
          % (f[0], f[-1], b[0], b[-1]))


def test_short_weave_stays_open():
    """Entry then exit close together: one continuous auxiliary lane, not two."""
    a = {"lanes_fwd": 2, "lanes_bwd": 0, "lane_width": 3.5, "aux_lanes_left": 1,
         "aux_taper_length": 90.0}
    short = _chain([(a, 31)])                                   # 300 m between the two gores
    _o, counts, _op = gb.chain_lane_counts(short, (0, 1), {0, 1}, {(0, 3): {True}, (1, 3): {True}}, 3)
    _assert(min(c[0] for c in counts) > 2.999,
            "an auxiliary lane served at both ends of a short weave must stay open, dipped to "
            "%.2f" % min(c[0] for c in counts))
    long_ = _chain([(a, 121)])                                  # 1200 m: too far to hold
    _o2, counts2, _op2 = gb.chain_lane_counts(long_, (0, 1), {0, 1}, {(0, 3): {True}, (1, 3): {True}}, 3)
    _assert(min(c[0] for c in counts2) < 2.001,
            "over %.0f m the lane must be dropped in the middle, held at %.2f"
            % (gb.AUX_WEAVE_HOLD, min(c[0] for c in counts2)))
    _assert(abs(counts2[0][0] - 3.0) < 1e-6 and abs(counts2[-1][0] - 3.0) < 1e-6,
            "...and still be full width at both gores, got %.2f / %.2f"
            % (counts2[0][0], counts2[-1][0]))
    print("smoketest_graph_transition: weave held open over 300 m, dropped over 1200 m")


def test_a_lane_that_is_not_open_rides_its_neighbour():
    """A lane the road does not have yet runs ON the lane beside it, not on the road edge.

    An auxiliary lane has no entrance of its own -- nothing flows into a route that begins in
    mid-carriageway -- so its route reaches back to the junction behind it, and where the lane is
    closed the only honest place for it is the through lane the exit traffic is actually sitting
    in. The previous rule parked it on the ROAD EDGE, half a lane further out, which is a car
    driving down the edge line with two wheels off the asphalt for the whole closed stretch."""
    from road_kit_authoring import graph_export as gx
    from mathutils import Vector

    LW = 3.5
    line = [Vector((x, 0.0, 0.0)) for x in (0.0, 100.0, 200.0, 300.0)]
    attrs = {"lanes_fwd": 3, "lanes_bwd": 0, "lane_width": LW, "median_width": 0.0,
             "sidewalk_left_width": 0.0, "sidewalk_right_width": 0.0}
    counts = [(1.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    built = gx.chain_lanes(line, attrs, 'LEFT', counts)
    by = {b[0]: b for b in built}
    lat = lambda lid: [abs(p.y) for p in by[lid][2]]
    _assert(all(abs(v - 0.5 * LW) < 1e-6 for v in lat("F2")),
            "the lane that exists everywhere must never move, got %r" % lat("F2"))
    _assert(abs(lat("F0")[0] - 0.5 * LW) < 1e-6 and abs(lat("F0")[-1] - 2.5 * LW) < 1e-6,
            "the last lane to open must ride the only lane there is and end at its own centre, "
            "got %r" % lat("F0"))
    _assert(all(len(b[2]) == len(line) for b in built),
            "every lane's route must reach both ends of the chain -- an auxiliary lane cut back "
            "to where it opens has no way in")
    _assert(by["F0"][3] and not by["F2"][3],
            "a lane that is not open for the whole chain is auxiliary; one that is, is not")
    print("smoketest_graph_transition: a closed lane rides its neighbour (%.2f m) and slides out "
          "to its own centre (%.2f m)" % (lat("F0")[0], lat("F0")[-1]))


def test_authored_width_step_becomes_a_taper():
    """The hand-authoring case: draw a road, stamp 2 lanes on one edge and 4 on the next.

    The vertex between them is an ordinary AUTO vertex -- nobody stamps "shape point" on the
    place a road widens -- and it used to end the chain, so the two halves were built as separate
    ribbons with a step between them and the solver reported a `width_steps` defect it could not
    fillet. It has to come out as ONE continuous ribbon that tapers."""
    obj = _graph("StepAuto", [(0, 0, 0), (200, 0, 0), (400, 0, 0)], [(0, 1), (1, 2)])
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=0, lane_width=3.5, lane_transition_length=60.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb_left_on=0,
                 curb_right_on=0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    layers = ga.ensure_edge_layers(bm)
    bm.edges[1][layers["lanes_fwd"]] = 4
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    result, carrier = gb.build_object(obj)
    _assert(not result.width_steps,
            "a straight lane-count change must be a taper, not an unbuildable width step: %r"
            % (result.width_steps,))
    _assert(len(carrier.data.vertices) == len(carrier.data.edges) + 1,
            "the road must be ONE polyline through the change, got %d points / %d segments"
            % (len(carrier.data.vertices), len(carrier.data.edges)))
    hw = carrier.data.attributes["rka_halfw"]
    row = sorted([(v.co.x, hw.data[i].value) for i, v in enumerate(carrier.data.vertices)])
    rate = max(abs(row[i + 1][1] - row[i][1]) / max(row[i + 1][0] - row[i][0], 1e-6)
               for i in range(len(row) - 1))
    _assert(rate <= (3.5 / 2.0) / 60.0 + 1e-6,
            "the ribbon must not widen faster than one lane per transition length, got %.4f m/m"
            % rate)
    print("smoketest_graph_transition: an AUTO vertex where only the width changes builds one "
          "continuous tapered ribbon (%d points, widening at most %.4f m/m)"
          % (len(carrier.data.vertices), rate))
    bpy.data.objects.remove(obj, do_unlink=True)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()
    test_lane_transition_is_stepped()
    test_sides_taper_independently()
    test_short_weave_stays_open()
    test_a_lane_that_is_not_open_rides_its_neighbour()
    test_transition_geometry_never_jumps()
    test_authored_width_step_becomes_a_taper()
    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
