#!/usr/bin/env python3
"""
smoketest_graph_solve.py -- headless check for the mesh-graph solver binding (`graph_solve.py`)
and the asset-index mechanism (`graph_assets.py`).

THE TWO CLAIMS THIS EXISTS TO VERIFY, both of which are load-bearing and neither of which is
obvious from reading the code:

  1. TRIMMING USES THE REAL PER-APPROACH WIDTH. A narrow lane crossing a wide arterial must be
     trimmed back by the ARTERIAL's half-width, not by any average of the two. `road_graph_solve`
     asserts the maths; this asserts the whole path -- stamped attributes -> `lane_profile`
     extents -> solver -> attributes written back onto the real mesh.
  2. `Collection Info (Separate Children)` EMITS ASSETS IN THE ORDER `graph_assets.catalog()`
     REPORTS. The per-edge asset index is a positional reference into that palette, so if the two
     orders disagreed every road would silently build with the wrong mesh. Verified by actually
     evaluating a Geometry Nodes tree with `Pick Instance` and checking WHICH mesh came through
     (the three palette assets have deliberately different vertex counts), not by trusting docs.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_graph_solve.py
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
from road_kit_authoring import graph_assets as gas      # noqa: E402
from road_kit_authoring import graph_attrs as ga        # noqa: E402
from road_kit_authoring import graph_solve as gs        # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _cross_graph():
    """A 4-way cross: E-W arterial (edges 0,1), N-S lane (edges 2,3)."""
    me = bpy.data.meshes.new("RoadGraph")
    me.from_pydata([(0, 0, 0), (200, 0, 0), (-200, 0, 0), (0, 200, 0), (0, -200, 0)],
                   [(0, 1), (0, 2), (0, 3), (0, 4)], [])
    me.update()
    obj = bpy.data.objects.new("RoadGraph", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def _stamp(obj, edge_indices, **values):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    layers = ga.ensure_edge_layers(bm)
    for i in edge_indices:
        for k, v in values.items():
            bm.edges[i][layers[k]] = v
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _values(mesh, name):
    return [d.value for d in mesh.attributes[name].data]


def _palette_asset(name, verts):
    """A named collection holding one mesh with a distinctive vertex count."""
    me = bpy.data.meshes.new(name + "_mesh")
    me.from_pydata([(float(i), 0.0, 0.0) for i in range(verts)], [], [])
    me.update()
    obj = bpy.data.objects.new(name + "_obj", me)
    coll = bpy.data.collections.new(name)
    coll.objects.link(obj)
    return coll



def _test_graph_object_resolution(obj):
    """Selecting the generated ROAD must act on its graph, not grey the panel out.

    This is the whole "the addon is broken, only Init and Validate work" report: the graph is an
    edge-only wireframe under the road, so the click lands on the carrier."""
    from road_kit_authoring import graph_build as gb
    gb.build_object(obj)
    ops = ("graph_solve", "graph_build", "graph_auto_aux", "graph_preview_lanes",
           "graph_export_lanekit", "graph_init_attrs", "graph_validate")
    for suffix in (gs.SUFFIX_CORNERS, gs.SUFFIX_NODES, "_Carrier"):
        gen = bpy.data.objects.get(obj.name + suffix)
        if gen is None:
            continue
        _assert(ga.GENERATED_TAG in gen.keys(),
                "%s must be tagged as generated, or nothing can resolve its owner" % gen.name)
        _assert(ga.graph_object_from(gen) is obj,
                "selecting %s must resolve back to the graph" % gen.name)
        bpy.context.view_layer.objects.active = gen
        for name in ops:
            _assert(getattr(bpy.ops.rka, name).poll() is True,
                    "%s must be available with %s selected -- it is the road you can actually "
                    "click" % (name, gen.name))
    bpy.context.view_layer.objects.active = obj


def _test_empty_layers_skipped(obj):
    """A layer whose width is zero everywhere must not be built.

    GN sweeps a zero-width band happily and emits the polygons anyway, so the corner polylines --
    which carry no carriageway, median, deck or right-hand side -- were swept by the full road
    stack (11,400 concrete polygons totalling 392 m2 of real area)."""
    from road_kit_authoring import graph_build as gb
    corners = bpy.data.objects.get(obj.name + gs.SUFFIX_CORNERS)
    _assert(corners is not None and len(corners.data.vertices), "test needs corner geometry")
    spec = gb.stack_spec()
    kept = [s["name"] for s in spec if gb.layer_has_content(corners.data, s)]
    for absent in ("Carriageway", "Deck", "SidewalkR", "CurbR"):
        _assert(absent not in kept,
                "%s has no attribute on the corner mesh and must be skipped, kept=%s"
                % (absent, kept))
    _assert("SidewalkL" in kept and "CurbL" in kept,
            "a corner DOES carry a kerb and footway; they must survive: %s" % kept)
    on_carrier = [s["name"] for s in spec
                  if gb.layer_has_content(bpy.data.objects[obj.name + "_Carrier"].data, s)]
    _assert("Carriageway" in on_carrier and "SidewalkL" in on_carrier,
            "the real road must keep its own layers: %s" % on_carrier)


def _test_deck_below_road(obj):
    """The structural deck must not be coplanar with the asphalt it carries.

    Measured on the island before this: 73.7% of sampled road surface had asphalt and concrete
    within 5 mm -- z-fighting across the whole network, worst on ordinary (deck-less) road where
    a zero-thickness deck is a bare sheet lying exactly on the carriageway."""
    from road_kit_authoring import graph_build as gb
    deck = next(s for s in gb.stack_spec() if s["name"] == "Deck")
    _assert(deck["z"] < -1e-3,
            "the deck's top must sit below the road surface, got z=%r" % deck["z"])
    median = next(s for s in gb.stack_spec() if s["name"] == "Median")
    _assert(median["z"] > 1e-3,
            "flush painted median must be lifted clear of the asphalt, got z=%r" % median["z"])


def _test_weld_crossings():
    """Two roads laid over each other at the same height do not meet -- connectivity is the
    vertex. `weld_crossings` must insert one and make it a real junction."""
    me = bpy.data.meshes.new("XGraph")
    me.from_pydata([(-100, 0, 0), (100, 0, 0), (0, -100, 0), (0, 100, 0)],
                   [(0, 1), (2, 3)], [])
    me.update()
    ob = bpy.data.objects.new("XGraph", me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    layers = ga.ensure_edge_layers(bm)
    for e in bm.edges:
        for k, v in (("lanes_fwd", 2), ("lanes_bwd", 2)):
            e[layers[k]] = v
    lane_w = layers["lane_width"]
    for e in bm.edges:
        e[lane_w] = 3.5
    _assert(len(gs.rgs().find_crossings(*gs.build_specs(bm), 4.0)) == 1,
            "test setup: the two roads must cross without a shared vertex")
    n = gs.weld_crossings(bm)
    _assert(n == 1, "expected 1 weld, got %d" % n)
    _assert(not gs.rgs().find_crossings(*gs.build_specs(bm), 4.0),
            "no crossing may remain unwelded after the repair")
    bm.verts.ensure_lookup_table()
    mid = [v for v in bm.verts if abs(v.co.x) < 1e-3 and abs(v.co.y) < 1e-3]
    _assert(len(mid) == 1, "the weld must produce exactly ONE shared vertex, got %d" % len(mid))
    _assert(len(mid[0].link_edges) == 4,
            "the welded node must be a 4-way junction, got valency %d" % len(mid[0].link_edges))
    # The split halves must keep the cross-section that was authored on the original edge, or a
    # weld would silently reset the road to defaults.
    el = ga.ensure_edge_layers(bm, fill_defaults=False)
    for e in mid[0].link_edges:
        _assert(e[el["lanes_fwd"]] == 2 and abs(e[el["lane_width"]] - 3.5) < 1e-6,
                "a split half lost its authored cross-section")
    bm.free()
    bpy.data.objects.remove(ob, do_unlink=True)



def _test_median_side_aux():
    """A ramp on the OFFSIDE of its carriageway must still get a connectable aux lane.

    Before `aux_median_*` the generator had only a nearside lane to offer, so an offside ramp
    either got a lane in the carriageway travelling the other way (which nothing fed) or no lane at
    all. Both ends of the model are checked here: the lane is ranked from the median, and the
    mainline then matches lanes from the KERB -- the end its count does not change at."""
    from road_kit_authoring import graph_export as gex
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    attrs = {"lanes_fwd": 2, "lanes_bwd": 0, "lane_width": 3.5, "median_width": 0.0,
             "sidewalk_left_width": 0.0, "sidewalk_right_width": 0.0,
             "aux_lanes_left": 1, "aux_taper_length": 40.0}
    from mathutils import Vector
    line = [Vector(p) for p in pts]
    kerb = gex.chain_lanes(line, dict(attrs, aux_median_left=0), 'LEFT', [1.0, 1.0])
    med = gex.chain_lanes(line, dict(attrs, aux_median_left=1), 'LEFT', [1.0, 1.0])
    kerb_aux = [(sfx, cix, n) for sfx, _d, _p, cix, n, is_aux in kerb if is_aux]
    med_aux = [(sfx, cix, n) for sfx, _d, _p, cix, n, is_aux in med if is_aux]
    _assert(len(kerb_aux) == 1 and kerb_aux[0][1] == 0,
            "a nearside aux lane must be the KERB lane (index 0), got %r" % kerb_aux)
    _assert(len(med_aux) == 1 and med_aux[0][1] == med_aux[0][2] - 1,
            "an offside aux lane must be the MEDIAN lane (index n-1), got %r" % med_aux)

    # ...and the mainline anchor flips with it: with the aux at the median, the through lanes hold
    # their KERB index across the nose, so the kerb lane is fed. Anchoring at the median instead
    # (correct for a nearside aux) left it fed by nothing.
    V = Vector
    def lane(lid, cix, n, is_aux):
        return (lid, V((0, 0, 0)), V((1, 0, 0)), cix, n, is_aux)
    ins = [lane("gA_F0", 0, 2, False), lane("gA_F1", 1, 2, False)]
    outs = [lane("gB_F0", 0, 3, False), lane("gB_F1", 1, 3, False), lane("gB_F2", 2, 3, True)]
    tarms = {"gA", "gB"}
    fed = set()
    for i in ins:
        for o in outs:
            if gex.movement_verdict(i, o, 'S', True, tarms, 1, ins, outs) is None:
                fed.add(o[0])
    _assert(fed == {"gB_F0", "gB_F1", "gB_F2"},
            "every downstream lane of an offside merge must be fed, got %s" % sorted(fed))


def _test_explain_node(obj):
    """The movement explanation must come from the rules the exporter obeys, not a copy."""
    from road_kit_authoring import graph_export as gex
    lines = gex.explain_node(obj, 0)
    _assert(lines and lines[0].startswith("node 0"), "explain_node produced nothing: %r" % lines)
    _assert(any("EMIT" in ln for ln in lines),
            "a 4-way junction must have at least one legal movement:\n%s" % "\n".join(lines))
    _assert(any("skip:" in ln for ln in lines),
            "...and at least one rejected one, with a reason")


def _test_flow_preview(obj):
    """The preview must show DIRECTION, not just position -- chevrons plus per-kind grouping."""
    from road_kit_authoring import graph_export as gex
    stats = gex.preview(obj)
    _assert(stats.get("arrows", 0) > 0, "no direction chevrons were built")
    flow = bpy.data.objects.get(gex.FLOW_OBJECT)
    _assert(flow is not None and len(flow.data.edges) == stats["arrows"] * 2,
            "each chevron is exactly two edges")
    coll = bpy.data.collections.get(gex.PREVIEW_COLLECTION)
    names = {c.name for c in coll.children}
    _assert(any(n.endswith("_through") for n in names),
            "lanes must be grouped by kind for isolation in the outliner: %s" % names)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()

    obj = _cross_graph()
    bpy.ops.rka.graph_init_attrs()

    # A 3+3 lane arterial with wide footways vs a 1+1 lane street with none.
    _stamp(obj, (0, 1), lanes_fwd=3, lanes_bwd=3, lane_width=3.5,
           sidewalk_left_width=4.0, sidewalk_right_width=4.0)
    _stamp(obj, (2, 3), lanes_fwd=1, lanes_bwd=1, lane_width=3.0,
           sidewalk_left_width=0.0, sidewalk_right_width=0.0)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    vl = ga.ensure_vert_layers(bm)
    bm.verts[0][vl["fillet_radius"]] = 6.0
    bm.to_mesh(obj.data)
    bm.free()

    # ---- 1. the solve, and the width numbers it must have used
    result = gs.solve_object(obj)
    art = gs.edge_widths({"lanes_fwd": 3, "lanes_bwd": 3, "lane_width": 3.5,
                          "sidewalk_left_width": 4.0, "sidewalk_right_width": 4.0})
    lane = gs.edge_widths({"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 3.0,
                           "sidewalk_left_width": 0.0, "sidewalk_right_width": 0.0})
    art_outer, lane_outer, fillet = art[0], lane[0], 6.0

    trims = _values(obj.data, "trim_start")
    _assert(abs(trims[2] - (art_outer + fillet)) < 1e-4,
            "the narrow street must be trimmed back by the ARTERIAL's outer half-width + fillet "
            "(%.3f), got %.3f -- an averaged width would give %.3f"
            % (art_outer + fillet, trims[2], (art_outer + lane_outer) / 2.0 + fillet))
    _assert(abs(trims[0] - (lane_outer + fillet)) < 1e-4,
            "the arterial only has to clear the narrow street (%.3f), got %.3f"
            % (lane_outer + fillet, trims[0]))
    _assert(trims[2] > trims[0], "the narrow street must be trimmed back FURTHER than the wide "
            "one -- it is the one whose ribbon would otherwise cross the arterial")
    print("smoketest_graph_solve: asymmetric trim is correct -- arterial %.2f m, narrow street "
          "%.2f m (an averaged width would have used %.2f m for both)"
          % (trims[0], trims[2], (art_outer + lane_outer) / 2.0 + fillet))

    # ---- 2. derived lateral offsets are written, and come from lane_profile
    half = _values(obj.data, "paved_half")
    _assert(abs(half[0] - 3 * 3.5) < 1e-4,
            "arterial paved_half should be 3 lanes x 3.5 m = 10.5, got %.3f" % half[0])
    walk = _values(obj.data, "walk_w_left")
    _assert(abs(walk[0] - 4.0) < 1e-4 and abs(walk[2]) < 1e-4,
            "footway width should be 4.0 on the arterial and 0.0 on the street, got %r"
            % walk[:4])
    kerb = _values(obj.data, "curb_off_left")
    _assert(abs(kerb[0] - 10.5) < 1e-4, "left kerb line sits at the carriageway edge, got %.3f"
            % kerb[0])

    # ---- 3. node classification + generated geometry
    kinds = _values(obj.data, "solved_kind")
    _assert(kinds[0] == 4, "the centre must classify as INTERSECTION (4), got %r" % kinds[0])
    _assert(_values(obj.data, "valency")[0] == 4, "centre valency should be 4")
    nodes_obj = bpy.data.objects.get(obj.name + gs.SUFFIX_NODES)
    corners_obj = bpy.data.objects.get(obj.name + gs.SUFFIX_CORNERS)
    # A pad is emitted as a TRIANGLE FAN, not one n-gon: it is concave and non-planar, and leaving
    # its tessellation to Blender left holes in the middle of the junction (measured 0.38-0.49 m
    # off any triangle at island node 58 -- a turning car driving through a gap in the asphalt).
    # So the count is "one fan", i.e. every face is a triangle and they share a single hub vertex.
    _assert(nodes_obj is not None and len(nodes_obj.data.polygons) >= 3
            and all(len(p.vertices) == 3 for p in nodes_obj.data.polygons)
            and len(set.intersection(*[set(p.vertices) for p in nodes_obj.data.polygons])) == 1,
            "one triangle fan for the one junction, got %r"
            % (None if nodes_obj is None else len(nodes_obj.data.polygons)))
    _assert(corners_obj is not None and len(corners_obj.data.edges) > 0,
            "kerb corner polylines should have been generated")
    _assert("corner_radius" in corners_obj.data.attributes,
            "corner polylines must carry the concentric footway radius")
    print("smoketest_graph_solve: node patch (%d verts) + %d corner polyline edges generated"
          % (len(nodes_obj.data.vertices), len(corners_obj.data.edges)))

    # ---- 4. regeneration swaps mesh data IN PLACE so a GN stack on the generated object survives
    stack = nodes_obj.modifiers.new("Probe", 'NODES')
    gs.solve_object(obj)
    _assert(bpy.data.objects.get(obj.name + gs.SUFFIX_NODES) is nodes_obj,
            "re-solving must reuse the generated object, not replace it")
    _assert(len(nodes_obj.modifiers) == 1 and nodes_obj.modifiers[0].name == "Probe",
            "re-solving must not disturb the generated object's modifier stack")
    nodes_obj.modifiers.remove(stack)
    print("smoketest_graph_solve: re-solve swapped mesh data in place, modifier stack survived")

    # ---- 5. a SHAPE POINT is not a junction
    me = bpy.data.meshes.new("Bend")
    me.from_pydata([(-60, 0, 0), (0, 0, 0), (0, 60, 0)], [(0, 1), (1, 2)], [])
    me.update()
    bend = bpy.data.objects.new("Bend", me)
    bpy.context.scene.collection.objects.link(bend)
    bpy.context.view_layer.objects.active = bend
    ga.ensure_mesh_attributes(me)
    me.attributes["node_type"].data[1].value = ga.NODE_NONE
    gs.solve_object(bend)
    _assert(_values(me, "trim_end")[0] == 0.0 and _values(me, "trim_start")[1] == 0.0,
            "a NODE_NONE shape point must not trim its edges")
    _assert(len(bpy.data.objects[bend.name + gs.SUFFIX_NODES].data.polygons) == 0,
            "a shape point must not emit a junction patch")
    print("smoketest_graph_solve: NODE_NONE shape point trims nothing and patches nothing")

    # ---- 6. asset palette: catalogue order == Collection Info (Separate Children) order
    for name, n in (("Zzz_Third", 3), ("Aaa_First", 7), ("Mmm_Second", 11)):
        gas.add_asset(gas.ROLE_CURB, _palette_asset(name, n))
    cat = gas.catalog(gas.ROLE_CURB)
    _assert(cat == ["Aaa_First", "Mmm_Second", "Zzz_Third"],
            "catalogue must be name-sorted, got %r" % cat)
    _assert(gas.index_of(gas.ROLE_CURB, "Mmm_Second") == 1, "index lookup")

    picked = _pick_instance_vertex_count(gas.registry(gas.ROLE_CURB), index=1)
    _assert(picked == 11,
            "Pick Instance index 1 must resolve to catalogue[1] ('Mmm_Second', 11 verts) -- got "
            "%r, so the node tree's asset order does NOT match graph_assets.catalog() and every "
            "per-edge asset index would select the wrong mesh" % picked)
    print("smoketest_graph_solve: Collection Info separate-children order matches catalog() -- "
          "index 1 -> %r (%d verts)" % (cat[1], picked))

    _test_graph_object_resolution(obj)
    _test_empty_layers_skipped(obj)
    _test_deck_below_road(obj)
    _test_weld_crossings()
    _test_median_side_aux()
    _test_explain_node(obj)
    _test_flow_preview(obj)
    print("smoketest_graph_solve: panel resolves from generated objects; empty layers skipped; "
          "deck clear of the asphalt; crossings weld into real junctions")

    print("SMOKETEST OK")


def _pick_instance_vertex_count(collection, index):
    """Evaluate the real node mechanism -- Collection Info (Separate Children) -> Instance on
    Points (Pick Instance) -> Realize -- on a single point, and report how many vertices the
    picked asset contributed. That count identifies WHICH palette entry was chosen."""
    ng = bpy.data.node_groups.new("GN_PickProbe", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput")
    nout = ng.nodes.new("NodeGroupOutput")
    L = ng.links.new

    ci = ng.nodes.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = collection
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True

    iop = ng.nodes.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True
    # `Instance Index` MUST BE LINKED, not assigned via `default_value`: it is an implicit-field
    # socket, so an unlinked socket falls back to the `Index` field and silently ignores whatever
    # default was written. Measured -- with `default_value` set to 0/1/2 the probe returned the
    # SAME asset every time (instance 0, i.e. the point's own index), which as a road generator
    # would mean every edge quietly built with palette entry 0 regardless of its stamp.
    idx_node = ng.nodes.new("FunctionNodeInputInt")
    idx_node.integer = index
    L(idx_node.outputs["Integer"], iop.inputs["Instance Index"])
    L(nin.outputs["Geometry"], iop.inputs["Points"])
    L(ci.outputs["Instances"], iop.inputs["Instance"])

    real = ng.nodes.new("GeometryNodeRealizeInstances")
    L(iop.outputs["Instances"], real.inputs["Geometry"])
    L(real.outputs["Geometry"], nout.inputs["Geometry"])

    me = bpy.data.meshes.new("ProbePoint")
    me.from_pydata([(0.0, 0.0, 0.0)], [], [])
    me.update()
    probe = bpy.data.objects.new("ProbePoint", me)
    bpy.context.scene.collection.objects.link(probe)
    mod = probe.modifiers.new("Probe", 'NODES')
    mod.node_group = ng

    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = probe.evaluated_get(deps).to_mesh()
    count = len(evaluated.vertices)
    probe.evaluated_get(deps).to_mesh_clear()
    # The probe point itself is not instanced away -- Instance on Points keeps the points only if
    # asked, and here the output is realized instances only, so the count is the asset's.
    return count


if __name__ == "__main__":
    main()
