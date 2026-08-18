#!/usr/bin/env python3
"""
smoketest_graph_build.py -- headless check that a solved road graph actually BUILDS geometry.

Asserts on the EVALUATED mesh (what the depsgraph produces after the whole modifier stack), not on
the node tree's shape -- a stack can be wired correctly and still sweep nothing, and every failure
mode worth catching here is silent:

  1. a chain through a `NODE_NONE` shape point is ONE polyline, not two -- the whole reason the
     carrier is emitted in Python instead of via Split Edges,
  2. the carriageway is swept at the width `lane_profile` computed, measured across the ribbon,
  3. a kerb rises ABOVE the road surface rather than hanging below it (Curve to Mesh's profile
     orientation quirk sends an unfixed profile downward),
  4. switching a kerb off on ONE side removes that side only,
  5. a deck adds geometry BELOW the road and nothing above it.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_graph_build.py
"""
import bmesh
import bpy
import os
import sys
import math

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


def _evaluated(obj):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    verts = [(obj.matrix_world @ v.co).copy() for v in me.vertices]
    ev.to_mesh_clear()
    return verts


def _layer_only(carrier, keep):
    """Evaluate with only the head, one named layer, and the finish enabled -- so a measurement
    is attributable to one band instead of to the union of twelve."""
    for m in carrier.modifiers:
        m.show_viewport = m.name in ("Spine", "Finish", keep)
    verts = _evaluated(carrier)
    for m in carrier.modifiers:
        m.show_viewport = True
    return verts



def _test_pillar_height_derived(straight):
    """A support column's height is `deck soffit - ground`, resolved PER POINT.

    The kit's `Kit_Pillar_*` meshes are a fixed 9 m, so instancing them can only be right at one
    elevation -- under this island's 12 m loop they would hang short and under a ramp near grade
    they would stand in mid-air. So the column is built from the numbers, and this measures that it
    lands on the authored ground and stops at the soffit."""
    for v in straight.data.vertices:
        v.co.z = 12.0
    straight.data.update()
    _stamp_edges(straight, deck_thickness=1.5, pillar_spacing=15.0, pillar_width=2.0,
                 ground_z=0.0, pillar_asset_idx=-1)
    gb.build_object(straight)
    carrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    col = _layer_only(carrier, "Pillars")
    _assert(col, "no columns under a 12 m viaduct")
    zs = [v.z for v in col]
    _assert(abs(min(zs)) < 1e-3, "column base must sit on the ground (0.0), got %.3f" % min(zs))
    _assert(abs(max(zs) - 10.5) < 1e-3,
            "column top must meet the soffit at 12.0 - 1.5 = 10.50, got %.3f" % max(zs))

    # RAISE THE GROUND and the same road grows a shorter column -- the whole point of deriving it.
    _stamp_edges(straight, ground_z=6.0)
    gb.build_object(straight)
    carrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    zs = [v.z for v in _layer_only(carrier, "Pillars")]
    _assert(abs(min(zs) - 6.0) < 1e-3, "column base must follow ground_z=6, got %.3f" % min(zs))
    _assert(abs(max(zs) - 10.5) < 1e-3, "...while its top still meets the soffit: %.3f" % max(zs))

    # A ROAD ON GRADE ASKS FOR NO COLUMNS, with no separate "is this a bridge" flag anywhere: its
    # soffit is at or below the ground, so the derived height is zero and the layer drops out.
    for v in straight.data.vertices:
        v.co.z = 0.0
    straight.data.update()
    _stamp_edges(straight, deck_thickness=0.0, pillar_spacing=0.0, ground_z=0.0)
    gb.build_object(straight)
    carrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    _assert("Pillars" not in [m.name for m in carrier.modifiers],
            "a road on grade must not even carry the pillar layer")
    print("smoketest_graph_build: column height derives from soffit - ground (10.50 m at 12 m up, "
          "4.50 m once the ground rises to 6 m, none on grade)")


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()

    # ---- a straight road with a shape point in the middle, then a real junction at the end
    obj = _graph("RoadGraph",
                 [(0, 0, 0), (100, 0, 0), (200, 0, 0), (200, 100, 0), (200, -100, 0)],
                 [(0, 1), (1, 2), (2, 3), (2, 4)])
    obj.data.attributes["node_type"].data[1].value = ga.NODE_NONE
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=2, lane_width=3.5, curb_height=0.2,
                 sidewalk_left_width=3.0, sidewalk_right_width=3.0)

    result, carrier = gb.build_object(obj)

    # ---- 1. the shape point did NOT break the chain
    cbm = bmesh.new()
    cbm.from_mesh(carrier.data)
    chain_lengths = sorted(len(list(g)) for g in _polylines(cbm))
    cbm.free()
    _assert(3 in chain_lengths,
            "edges 0 and 1 join through the NODE_NONE shape point into ONE 3-point polyline; "
            "got polyline point counts %r" % chain_lengths)
    print("smoketest_graph_build: NODE_NONE shape point kept the chain continuous "
          "(polyline point counts %r)" % chain_lengths)

    # ---- a SEPARATE straight, single-edge graph for every cross-section measurement, so a
    # global extent is unambiguously the road's width and not some other chain's length.
    straight = _graph("Straight", [(0, 0, 0), (100, 0, 0)], [(0, 1)])
    _stamp_edges(straight, lanes_fwd=2, lanes_bwd=2, lane_width=3.5, curb_height=0.2,
                 sidewalk_left_width=3.0, sidewalk_right_width=3.0)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]

    # ---- 2. the carriageway is swept at the width lane_profile computed
    pave = _layer_only(scarrier, "Carriageway")
    _assert(pave, "the carriageway layer produced no geometry at all")
    width = max(v.y for v in pave) - min(v.y for v in pave)
    expected = 4 * 3.5
    _assert(abs(width - expected) < 1e-3,
            "carriageway should span 4 lanes x 3.5 m = %.2f m, measured %.3f m"
            % (expected, width))
    print("smoketest_graph_build: carriageway swept at %.2f m, the width lane_profile computed"
          % width)

    # ---- 3. a kerb rises ABOVE the road, it does not hang below it
    curb = _layer_only(scarrier, "CurbL")
    _assert(curb, "the left kerb layer produced no geometry")
    lo, hi = min(v.z for v in curb), max(v.z for v in curb)
    _assert(abs(lo) < 1e-4 and abs(hi - 0.2) < 1e-4,
            "a 0.2 m kerb must span z=[0.00, 0.20] (base flush with the road, rising up); "
            "measured [%.3f, %.3f] -- negative means Curve to Mesh's profile flip is unfixed"
            % (lo, hi))
    print("smoketest_graph_build: kerb rises from the road surface upward, z span [%.2f, %.2f]"
          % (lo, hi))

    # ---- 3b. the footway sits ON TOP of the kerb, outboard of the carriageway
    walk = _layer_only(scarrier, "SidewalkL")
    _assert(walk, "the left footway layer produced no geometry")
    _assert(abs(min(v.z for v in walk) - 0.2) < 1e-4,
            "the footway must sit at kerb height 0.20, got %.3f" % min(v.z for v in walk))
    _assert(min(v.y for v in walk) >= width / 2.0 - 1e-4,
            "the footway must lie outboard of the carriageway edge (%.2f), got %.3f"
            % (width / 2.0, min(v.y for v in walk)))
    print("smoketest_graph_build: footway sits on the kerb at z=%.2f, outboard from y=%.2f"
          % (min(v.z for v in walk), min(v.y for v in walk)))

    # ---- 4. per-side kerb removal takes out that side ONLY
    _stamp_edges(straight, curb_left_on=0)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    left = _layer_only(scarrier, "CurbL")
    right = _layer_only(scarrier, "CurbR")
    left_h = (max(v.z for v in left) - min(v.z for v in left)) if left else 0.0
    right_h = (max(v.z for v in right) - min(v.z for v in right)) if right else 0.0
    _assert(left_h < 1e-6, "curb_left_on=0 must leave no left kerb, got height %.3f" % left_h)
    _assert(abs(right_h - 0.2) < 1e-4,
            "the RIGHT kerb must survive its neighbour being switched off, got %.3f" % right_h)
    print("smoketest_graph_build: curb_left_on=0 removed the left kerb only (right still %.2f m)"
          % right_h)

    # ---- 5. a deck adds structure below the road and nothing above it
    _stamp_edges(straight, curb_left_on=1, deck_thickness=1.5)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    deck = _layer_only(scarrier, "Deck")
    _assert(deck, "the deck layer produced no geometry")
    # The whole slab hangs from `DECK_Z_BIAS`, not from 0: its top face spans the same width as
    # the carriageway, so sitting it exactly ON the road surface made the two coplanar over the
    # entire network (73.7% of sampled road surface z-fought before the bias).
    want = -1.5 + gb.DECK_Z_BIAS
    _assert(abs(min(v.z for v in deck) - want) < 1e-3,
            "a 1.5 m deck must reach z=%.3f, got %.3f" % (want, min(v.z for v in deck)))
    _assert(max(v.z for v in deck) <= gb.DECK_Z_BIAS + 1e-4,
            "the deck's top must stay BELOW the asphalt it carries (<= %.3f), got %.3f"
            % (gb.DECK_Z_BIAS, max(v.z for v in deck)))
    print("smoketest_graph_build: deck spans z=%.3f..%.3f -- clear of the road surface"
          % (min(v.z for v in deck), max(v.z for v in deck)))

    carrier = scarrier
    # ---- 6. asset rows: a per-edge index picks a palette mesh, spacing controls the count
    from road_kit_authoring import graph_assets as gas
    for name, n in (("Pillar_A", 4), ("Pillar_B", 9)):
        me2 = bpy.data.meshes.new(name + "_m")
        me2.from_pydata([(0.0, 0.0, float(i)) for i in range(n)], [], [])
        me2.update()
        c = bpy.data.collections.new(name)
        c.objects.link(bpy.data.objects.new(name + "_o", me2))
        gas.add_asset(gas.ROLE_PILLAR, c)
    _assert(gas.catalog(gas.ROLE_PILLAR) == ["Pillar_A", "Pillar_B"],
            "palette should hold both pillars, got %r" % gas.catalog(gas.ROLE_PILLAR))

    # `PillarAssets` is the INSTANCED row -- picking `pillar_asset_idx` hands the points to it
    # instead of to the parametric `Pillars` column row, which is how the two stay exclusive.
    _stamp_edges(straight, pillar_spacing=25.0, pillar_asset_idx=1)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    _assert("Pillars" not in [m.name for m in scarrier.modifiers],
            "with an asset picked, the parametric column row must not also build")
    pil = _layer_only(scarrier, "PillarAssets")
    _assert(pil, "a pillar row with spacing 25 m on a 100 m road must instance something")
    _assert(len(pil) % 9 == 0,
            "every instance must be Pillar_B (9 verts, palette index 1) -- got %d verts, which is "
            "not a multiple of 9, so the wrong palette entry was picked" % len(pil))
    count_b = len(pil) // 9
    _assert(count_b >= 4, "100 m at 25 m spacing should place ~5 pillars, got %d" % count_b)

    _stamp_edges(straight, pillar_asset_idx=0)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    pil_a = _layer_only(scarrier, "PillarAssets")
    _assert(len(pil_a) % 4 == 0 and len(pil_a) // 4 == count_b,
            "switching the index to 0 must swap the MESH (4-vert Pillar_A) while keeping the same "
            "instance count %d -- got %d verts" % (count_b, len(pil_a)))
    print("smoketest_graph_build: pillar row placed %d instances; index 1 -> Pillar_B (9v), "
          "index 0 -> Pillar_A (4v) with the same count" % count_b)

    _stamp_edges(straight, pillar_asset_idx=-1)
    gb.build_object(straight)
    scarrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    _assert("PillarAssets" not in [m.name for m in scarrier.modifiers],
            "asset index -1 must instance nothing -- that is how 'no asset' is expressed, and the "
            "parametric column row takes over instead")
    _stamp_edges(straight, pillar_spacing=0.0)
    gb.build_object(straight)
    carrier = bpy.data.objects[straight.name + gb.SUFFIX_CARRIER]
    print("smoketest_graph_build: asset index -1 places nothing (parametric-only edge)")

    # ---- the whole stack together: one road, every band present and in the right place
    full = _evaluated(carrier)
    _assert(full, "the full stack produced nothing")
    span_y = max(v.y for v in full) - min(v.y for v in full)
    expected_y = 4 * 3.5 + 3.0 + 3.0          # carriageway + both footways
    _assert(abs(span_y - expected_y) < 1e-3,
            "the assembled road should span carriageway + both footways = %.2f m, got %.3f"
            % (expected_y, span_y))
    _assert(abs(min(v.z for v in full) - (-1.5 + gb.DECK_Z_BIAS)) < 1e-3
            and abs(max(v.z for v in full) - 0.2) < 1e-3,
            "the assembled road should reach from the deck soffit (-1.50) to the kerb top "
            "(0.20), got [%.3f, %.3f]" % (min(v.z for v in full), max(v.z for v in full)))
    print("smoketest_graph_build: assembled road spans %.2f m wide, z [%.2f, %.2f], "
          "%d vertices across %d layers"
          % (span_y, min(v.z for v in full), max(v.z for v in full),
             len(full), len(carrier.modifiers)))

    _test_corner_footway_side()
    _test_aux_lane_taper()
    _test_chained_gores_keep_their_aux_fed()
    _test_trunk_is_the_wider_road()
    _test_ramp_not_fed_across_the_median()
    _test_gore_merged_into_crossing()
    _test_pillar_height_derived(straight)

    print("SMOKETEST OK")


def _test_aux_lane_taper():
    """An aux lane must OPEN over its taper and the ramp must be reachable only from it.

    Covers the three ways this silently degrades: the lane appearing at full width (no taper at
    all), the taper smeared across whatever segment happens to be last (no vertex at the
    breakpoint, so the authored length means nothing), and the lane's ROUTE staying at its
    full-width offset while the ribbon narrows -- which puts traffic off the asphalt."""
    from road_kit_authoring import graph_export as gx

    TAPER, LW = 100.0, 3.5
    obj = _graph("Ramp",
                 [(0, 0, 0), (-300, 0, 0), (-150, 0, 0), (300, 0, 0), (280, -110, 0)],
                 [(2, 0), (1, 2), (0, 3), (0, 4)])
    obj.data.attributes["node_type"].data[2].value = ga.NODE_NONE      # trunk shape point
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=0, lane_width=LW, aux_taper_length=TAPER,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    layers = ga.ensure_edge_layers(bm)
    for i in (0, 1):                       # only the trunk chain carries the aux lane
        bm.edges[i][layers["aux_lanes_left"]] = 1
    bm.to_mesh(obj.data)
    bm.free()

    result, carrier = gb.build_object(obj)
    _assert(any(n.kind == gs.rgs().KIND_GORE for n in result.nodes),
            "trunk + straight-on + ramp must solve as a gore")

    # ---- 1. the ribbon widens by exactly one lane, and only over the taper
    hw = carrier.data.attributes["rka_halfw"]
    trunk = sorted([(v.co.x, hw.data[i].value) for i, v in enumerate(carrier.data.vertices)
                    if v.co.x <= 0.5 and abs(v.co.y) < 1e-3], key=lambda p: p[0])
    # The mainline continuation's chain also starts at x=0, so take the WIDEST there -- that is
    # the trunk's tapered end; the other is a fresh chain with no aux lane.
    base = trunk[0][1]
    full = max(w for x, w in trunk if abs(x) < 1e-3)
    _assert(abs(full - base - LW / 2.0) < 1e-3,
            "one aux lane must widen the half-width by %.2f m, got %.3f" % (LW / 2.0, full - base))
    at_break = [w for x, w in trunk if abs(x + TAPER) < 1e-3]
    _assert(at_break, "no vertex at the taper breakpoint (x=-%.0f): the authored taper length is "
                      "being smeared across the last segment instead of honoured" % TAPER)
    _assert(abs(at_break[0] - base) < 1e-3,
            "the aux lane must be fully closed where its taper begins, got %.3f" % at_break[0])
    print("smoketest_graph_build: aux lane opens %.2f -> %.2f m over its %.0f m taper"
          % (base, full, TAPER))

    # ---- 2. the aux lane's ROUTE follows the taper, and it alone reaches the ramp
    lanes, _stats = gx.collect(obj)
    by_id = {l["id"]: l for l in lanes}
    trunk_lanes = [l for l in lanes if l["kind"] == "through" and l["id"].startswith("g0_")]
    _assert(len(trunk_lanes) == 3, "trunk should export 2 through lanes + 1 aux, got %d"
            % len(trunk_lanes))
    aux = by_id["g0_F0"]                    # curb index 0 = outermost = the aux lane
    lat = [abs(p[2]) for p in aux["points"]]        # godot z = -blender y
    _assert(abs(max(lat) - min(lat) - LW / 2.0) < 1e-2,
            "the aux route must slide inward by half a lane as its taper closes, moved %.3f"
            % (max(lat) - min(lat)))

    ramp_reached = [lid for lid in ("g0_F0", "g0_F1", "g0_F2")
                    if any("g2_" in nxt for nxt in _reachable(by_id, lid))]
    _assert(ramp_reached == ["g0_F0"],
            "only the aux lane may take the ramp at a gore, but %s can" % ramp_reached)
    print("smoketest_graph_build: ramp reachable only from the aux lane %s" % ramp_reached)


def _test_chained_gores_keep_their_aux_fed():
    """Two exits in a row: the second's lane must open even though the first's is exit-only.

    An auxiliary lane is entered from the through lane beside it -- normally the kerb lane. Where
    two gores chain, that kerb lane is the PREVIOUS exit's deceleration lane, which leaves by its
    own ramp and is barred from continuing on the trunk. Nothing then moved into the new lane and
    it opened as an unreachable stub: the road visibly widens for an exit no car can enter, which
    is indistinguishable on screen from the ramp being wired to the wrong lane. The island had
    three of these (g26_R0, g30_R0, g33_R0).

    Asserts the property that actually matters and is cheap to keep true -- every auxiliary lane
    is reachable and leads somewhere -- rather than naming which lane feeds which."""
    from road_kit_authoring import graph_export as gx

    # trunk: (-600) -> A(-200) -> B(200) -> (600), with a ramp leaving at A and another at B.
    # Keep-left, travelling east: the kerb is on the LEFT of travel, so a nearside exit departs
    # NORTH (+y) -- matching the kerb-side auxiliary lane stamped below. The ramps must also leave
    # TANGENTIALLY (well inside `GORE_ANGLE_DEG`), or the solver reads each node as an ordinary
    # intersection and none of the gore rules under test ever run.
    obj = _graph("TwoExits",
                 [(-200, 0, 0), (200, 0, 0), (-600, 0, 0), (600, 0, 0),
                  (300, 150, 0), (700, 150, 0)],
                 [(2, 0), (0, 1), (1, 3), (0, 4), (1, 5)])
    _stamp_edges(obj, lanes_fwd=3, lanes_bwd=0, lane_width=3.5, aux_taper_length=120.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm)
    for i in (3, 4):                              # both ramps: one lane, no median
        bm.edges[i][el["lanes_fwd"]], bm.edges[i][el["lanes_bwd"]] = 1, 0
        bm.edges[i][el["lane_width"]] = 4.5
    for i in (0, 1):                              # a deceleration lane into each gore
        bm.edges[i][el["aux_lanes_left"]] = 1
    bm.to_mesh(obj.data)
    bm.free()

    lanes, _stats, ctx = gx.collect(obj, want_context=True)
    by_id = {l["id"]: l for l in lanes}
    fed = set()
    for lane in lanes:
        fed.update(lane["next"])
    aux = set()
    for node_lanes in list(ctx["arrivals"].values()) + list(ctx["departures"].values()):
        aux.update(l[0] for l in node_lanes if l[5])
    _assert(len(aux) >= 2, "both chained gores should carry an auxiliary lane, got %s" % sorted(aux))
    # Judged against the through lanes beside it: a chain that starts or ends at the edge of the
    # network legitimately has no upstream/downstream, and every one of its lanes shares that.
    def _siblings(aid):
        return [l for l in lanes if l["kind"] == "through" and l["id"] != aid
                and l["id"].rsplit("_", 1)[0] == aid.rsplit("_", 1)[0]
                and l["id"].rsplit("_", 1)[1][0] == aid.rsplit("_", 1)[1][0]]
    orphan = sorted(a for a in aux if a in by_id and not by_id[a]["next"]
                    and any(s["next"] for s in _siblings(a)))
    unfed = sorted(a for a in aux if a not in fed
                   and any(s["id"] in fed for s in _siblings(a)))
    _assert(not orphan, "auxiliary lane(s) with no successor beside connected through lanes: %s"
            % orphan)
    _assert(not unfed, "auxiliary lane(s) nothing moves into, beside fed through lanes: %s"
            % unfed)
    _assert(not gx.audit_movements(obj), "the movement audit must be clean here: %s"
            % gx.audit_movements(obj))
    print("smoketest_graph_build: %d chained-gore auxiliary lanes are all fed and all lead "
          "somewhere" % len(aux))


def _test_trunk_is_the_wider_road():
    """At a gore, the mainline is the multi-lane road -- not whichever arm happens to be straight.

    `_gore_trunk`/`_gore_mainline` pick the trunk from tangency, and where the ramp is the
    straightest thing at the node they pick it as a TRUNK arm and a real carriageway as the ramp.
    Every rule downstream then reads inverted: the carriageway's auxiliary lane gets rejected as a
    deceleration lane that must leave by the ramp, and the through lanes take the exit instead --
    the exit connecting to the middle of the road rather than to the lane that opens for it.

    Built with the ramp deliberately straight and the mainline bending through the node, which is
    the arrangement that fools tangency (island gore 331)."""
    from road_kit_authoring import graph_export as gx

    obj = _graph("StraightRamp",
                 [(0, 0, 0), (-300, 40, 0), (300, 60, 0), (300, 0, 0)],
                 [(0, 1), (0, 2), (0, 3)])
    _stamp_edges(obj, lanes_fwd=3, lanes_bwd=3, lane_width=3.5, aux_taper_length=100.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm)
    ramp = bm.edges[2]                            # (0, 3): dead straight, and only one lane
    ramp[el["lanes_fwd"]], ramp[el["lanes_bwd"]] = 1, 0
    ramp[el["lane_width"]] = 4.5
    bm.edges[0][el["aux_lanes_left"]] = 1         # the mainline arm that feeds the exit
    bm.to_mesh(obj.data)
    bm.free()

    _lanes, _stats, ctx = gx.collect(obj, want_context=True)
    clusters = [c for cs in ctx["gore_clusters"].values() for c in cs]
    _assert(clusters, "a tangential three-arm split must produce a gore cluster")
    trunk, arms = clusters[0]
    ramp_arms = set(arms) - set(trunk)
    _assert(len(trunk) == 2 and len(ramp_arms) == 1,
            "a gore has two trunk arms and one ramp, got trunk=%s ramp=%s"
            % (sorted(trunk), sorted(ramp_arms)))
    widths = {}
    for lane in ctx["arrivals"].get(0, []) + ctx["departures"].get(0, []):
        a = lane[0].rsplit("_", 1)[0]
        widths[a] = max(widths.get(a, 0), lane[4])
    narrowest_trunk = min(widths.get(a, 0) for a in trunk)
    widest_ramp = max(widths.get(a, 0) for a in ramp_arms)
    _assert(narrowest_trunk > widest_ramp,
            "the single-lane arm was chosen as the mainline: trunk lane counts %s, ramp %s"
            % ({a: widths.get(a) for a in sorted(trunk)},
               {a: widths.get(a) for a in sorted(ramp_arms)}))
    print("smoketest_graph_build: the gore's trunk is the %d-lane road, not the straight %d-lane "
          "ramp" % (narrowest_trunk, widest_ramp))


def _test_ramp_not_fed_across_the_median():
    """A one-way ramp off a divided road may only be reached from the carriageway it hangs on.

    An exit that leaves too steeply to read as a tangential diverge is classified as an ordinary
    INTERSECTION, and intersection rules happily hand the FAR carriageway a right turn into it --
    a drive across the middle of a motorway. On the island that was IC_YAMATE and JCT_AIRPORT, and
    it is invisible in the mesh: the geometry is perfectly well formed, only the movements are
    impossible.

    `allow_cross` on the vertex is the switch that says whether the median may be crossed here,
    and both halves are asserted, because the rule is only right if it is a rule and not a
    blanket ban: with crossing allowed (a surface junction, where a diamond's on-ramp genuinely is
    entered from both directions) both carriageways reach the ramp; with it off (a limited-access
    road, where no node breaks the median) only the near one does. `audit_movements` must report
    the bad case as well, so a graph that grows one later says so instead of hiding it."""
    from road_kit_authoring import graph_export as gx

    def _build(allow):
        obj = _graph("MedianRamp",
                     [(0, 0, 0), (-300, 0, 0), (300, 0, 0), (200, -160, 0)],
                     [(0, 1), (0, 2), (0, 3)])
        _stamp_edges(obj, lanes_fwd=2, lanes_bwd=2, lane_width=3.5, median_width=1.2,
                     sidewalk_left_width=0.0, sidewalk_right_width=0.0)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        el = ga.ensure_edge_layers(bm)
        ramp = bm.edges[2]                       # the (0, 3) arm -- one-way, no median
        ramp[el["lanes_fwd"]], ramp[el["lanes_bwd"]] = 1, 0
        ramp[el["lane_width"]], ramp[el["median_width"]] = 4.5, 0.0
        for v in bm.verts:
            v[ga.ensure_vert_layers(bm)["allow_cross"]] = allow
        bm.to_mesh(obj.data)
        bm.free()
        return obj

    def _carriageways_reaching_ramp(obj):
        lanes, _stats, ctx = gx.collect(obj, want_context=True)
        by_id = {l["id"]: l for l in lanes}
        ramp_ids = {l["id"] for l in lanes if l["kind"] == "through"
                    and abs(l["points"][-1][2] + -160.0) < 60.0}      # godot z = -blender y
        feeders = set()
        for lid, lane in by_id.items():
            if lane["kind"] != "through" or lid in ramp_ids:
                continue
            if any(n in ramp_ids for n in _reachable(by_id, lid)):
                feeders.add((lid.rsplit("_", 1)[0], lid.rsplit("_", 1)[1][0]))
        return ramp_ids, feeders

    open_ramp, open_feeders = _carriageways_reaching_ramp(_build(1))
    _assert(open_ramp, "the ramp arm must export a lane")
    _assert(len(open_feeders) > 1,
            "with crossing allowed both carriageways should reach the ramp, got %s" % open_feeders)

    shut = _build(0)
    _shut_ramp, shut_feeders = _carriageways_reaching_ramp(shut)
    _assert(shut_feeders, "closing the median must not orphan the ramp -- the near carriageway "
                          "still has to reach it")
    _assert(len(shut_feeders) == 1,
            "allow_cross is off, so only the carriageway the ramp hangs on may reach it, got %s"
            % sorted(shut_feeders))
    reported = gx.audit_movements(_build(1))
    _assert(not reported, "a surface junction that allows crossing must not be reported: %s"
            % reported)
    print("smoketest_graph_build: a ramp off a divided road is reached from %d carriageway(s) "
          "when the median may be crossed and %d when it may not"
          % (len(open_feeders), len(shut_feeders)))


def _test_gore_merged_into_crossing():
    """A gore whose diverge sits a few metres from a crossing must keep its diverge rules.

    The island's expressway exits like this: the ramp splits off, and four metres later the
    mainline meets a surface street. The scrap of road between them is shorter than a lane, so the
    exporter drops it and MERGES the two junctions -- and the merged node then classified as an
    ordinary intersection, which threw away every gore rule. Two things went wrong at once and
    both are asserted here:

      * the gore's own arms were named by the dropped stub's chain, a name no lane is published
        under, so the trunk/ramp distinction matched nothing and EVERY through lane got a
        connector into the ramp (the ramp visibly "sticking into the middle" of the mesh); and
      * the deceleration lane was clamped back onto the through carriageway, so it took the ramp
        AND carried on, feeding an exit lane that another through lane already fed.

    The crossing's own movements must survive intact -- the rules are per movement, not per node,
    so the surface street still turns normally."""
    from road_kit_authoring import graph_export as gx

    LW = 3.5
    obj = _graph("GoreAtCrossing",
                 [(0, 0, 0),        # 0 A -- the gore
                  (-300, 0, 0),     # 1 trunk start
                  (-150, 0, 0),     # 2 trunk shape point
                  (4, 0, 0),        # 3 B -- the crossing, one 4 m stub away
                  (280, -110, 0),   # 4 ramp end
                  (300, 0, 0),      # 5 mainline continuation
                  (4, 200, 0),      # 6 cross street north
                  (4, -200, 0)],    # 7 cross street south
                 [(2, 0), (1, 2), (0, 3), (0, 4), (3, 5), (3, 6), (3, 7)])
    obj.data.attributes["node_type"].data[2].value = ga.NODE_NONE
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=0, lane_width=LW, aux_taper_length=100.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    layers = ga.ensure_edge_layers(bm)
    for i in (0, 1):                       # the aux lane belongs to the trunk feeding the exit
        bm.edges[i][layers["aux_lanes_left"]] = 1
    bm.to_mesh(obj.data)
    bm.free()

    result = gs.solve_object(obj)
    _assert(any(n.index == 0 and n.kind == gs.rgs().KIND_GORE for n in result.nodes),
            "the diverge must still solve as a gore")
    lanes, stats = gx.collect(obj)
    _assert(stats["merged"] >= 1, "the 4 m stub must merge the gore into the crossing")
    by_id = {l["id"]: l for l in lanes}

    def _ends_near(lane, x, y, tol=1.0):
        p = lane["points"][-1]             # godot = (blender x, blender z, -blender y)
        return abs(p[0] - x) < tol and abs(-p[2] - y) < tol

    through = [l for l in lanes if l["kind"] == "through"]
    ramp = [l["id"] for l in through if _ends_near(l, 280, -110, 30.0)]
    ahead = [l["id"] for l in through if _ends_near(l, 300, 0, 30.0)]
    cross = [l["id"] for l in through if abs(l["points"][-1][2]) > 100.0]
    _assert(ramp and ahead and cross, "expected a ramp, a continuation and cross streets, got "
                                      "%s / %s / %s" % (ramp, ahead, cross))
    trunk = sorted(l["id"] for l in through
                   if l["id"] not in set(ramp) | set(ahead) | set(cross))
    _assert(len(trunk) == 3, "the trunk carries 2 through lanes + 1 aux, got %s" % trunk)
    aux = trunk[0]                                     # curb index 0 = outermost = the aux lane

    took_ramp = [lid for lid in trunk
                 if any(n in ramp for n in _reachable(by_id, lid))]
    _assert(took_ramp == [aux],
            "only the aux lane may take a ramp, but %s can -- the merge dropped the gore rules"
            % took_ramp)
    carried_on = [n for n in _reachable(by_id, aux) if n in ahead]
    _assert(not carried_on,
            "the deceleration lane must not also continue on the trunk (reaches %s)" % carried_on)
    turned = [lid for lid in trunk if any(n in cross for n in _reachable(by_id, lid))]
    _assert(turned, "the crossing's own turns must survive: no trunk lane reaches a cross street")
    print("smoketest_graph_build: gore merged into a crossing keeps its rules -- ramp only from "
          "%s, which does not carry on, and %d lane(s) still turn into the cross streets"
          % (aux, len(turned)))


def _reachable(by_id, lid):
    """Lane ids one hop away, following a connector through to what it feeds."""
    out = []
    for nxt in by_id[lid]["next"]:
        out.append(nxt)
        out.extend(by_id[nxt]["next"] if nxt in by_id else [])
    return out


def _test_corner_footway_side():
    """A junction's corner footway must sit OUTBOARD of the kerb return, not in the carriageway.

    Guards a sign that is easy to get backwards and silent when wrong. The kerb-return centre sits
    in the block BEYOND the corner (see `road_graph_solve._build_corners`), so "outboard" means
    *toward* that centre -- the opposite of what it means on a straight road. `build_corner_mesh`
    derives the side from the arc winding, and flipping it lays the footway across the road with
    no error anywhere."""
    obj = _graph("CornerSide", [(0, 0, 0), (80, 0, 0), (-80, 0, 0), (0, 80, 0), (0, -80, 0)],
                 [(0, 1), (0, 2), (0, 3), (0, 4)])
    _stamp_edges(obj, lanes_fwd=2, lanes_bwd=2, lane_width=3.5,
                 sidewalk_left_width=3.0, sidewalk_right_width=3.0, curb_height=0.15)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for v in bm.verts:
        v[ga.ensure_vert_layers(bm)["fillet_radius"]] = 5.0
    bm.to_mesh(obj.data)
    bm.free()

    result, _ = gb.build_object(obj)
    node = next(n for n in result.nodes if n.index == 0)
    _assert(node.corners, "a symmetric 4-way must produce kerb returns")
    c = node.corners[0]
    _assert(math.hypot(c.center[0], c.center[1]) > 7.0,
            "the kerb-return centre must lie beyond the carriageway, got %.2f m from the node"
            % math.hypot(c.center[0], c.center[1]))

    dg = bpy.context.evaluated_depsgraph_get()
    ev = bpy.data.objects[obj.name + gs.SUFFIX_CORNERS].evaluated_get(dg)
    mesh = ev.to_mesh()
    inboard = outboard = 0
    for v in mesh.vertices:
        d = math.hypot(v.co.x - c.center[0], v.co.y - c.center[1])
        if d > c.radius + 3.0 + 0.05:
            continue                       # belongs to another corner
        if d < c.radius - 0.05:
            inboard += 1                   # between kerb and the block -- the footway
        elif d > c.radius + 0.05:
            outboard += 1                  # out in the carriageway -- wrong side
    ev.to_mesh_clear()
    _assert(inboard > outboard,
            "corner footway is on the carriageway side of the kerb (%d vs %d vertices) -- the "
            "winding-to-side sign in build_corner_mesh is inverted" % (inboard, outboard))
    print("smoketest_graph_build: corner footway outboard (%d inboard vs %d carriageway-side)"
          % (inboard, outboard))


def _polylines(bm):
    """Group the carrier's vertices into connected runs, so a chain can be counted."""
    bm.verts.ensure_lookup_table()
    seen, groups = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, group = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for e in cur.link_edges:
                other = e.other_vert(cur)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        groups.append(group)
    return groups


if __name__ == "__main__":
    main()
