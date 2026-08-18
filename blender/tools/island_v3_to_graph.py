#!/usr/bin/env python3
"""
island_v3_to_graph.py -> assets/world_source/island_v3_roads.blend

Rebuild the ENTIRE Tokyo-Bay Island v3 road network as ONE mesh graph for the v0.2
`road_kit_authoring` addon: vertices are junctions, edges are road segments, the cross-section
lives on the edge domain, and the whole thing is swept by a single Geometry Nodes stack.

WHAT THIS REPLACES. `island_v3_to_roadkit.py` emitted one road_kit COLLECTION per chunk -- a
separate authored piece per stretch between crossings, each with its own settings, plus a separate
intersection piece per crossing. That model is archived (`addons/road_kit_authoring/legacy/`). Here
the same source polylines become a single mesh, and every junction is derived rather than authored.

THE THREE GRAPH STEPS, which are the whole job (`build_graph`):

1. CROSS -- every pair of segments is tested for an XY crossing. A crossing whose two heights
   differ by more than `Z_CROSS_TOL` is a FLYOVER and is left alone (no shared vertex = not
   connected, which is what a mesh graph already means). A same-grade crossing inserts ONE shared
   vertex into both roads, which is what makes it an intersection.
2. SNAP -- a road that ENDS on another road's interior is a T-junction, and `find_crossings` will
   not see it (it tests strict interiors on both sides, or a shared endpoint would report as a
   crossing every time). Each free endpoint is projected onto nearby segments and welded in.
3. WELD -- free endpoints that coincide with each other join through a spatial hash.

THE SHAPE-POINT DECISION IS WHAT MAKES THIS SCALE. The source polylines are resampled every few
metres, so the island has thousands of vertices. If each were a junction, the solver would trim
both ends of every 12 m segment and drop a patch in between -- tens of thousands of pointless
polygons, and every road eaten away by its own trimming. So every vertex that is NOT a real
junction is stamped `NODE_NONE`: bend the road, build no junction, keep the ribbon continuous. The
graph then has a few hundred real nodes among its thousands of shape points, which is the actual
topology of the island.

RUN:
  blender --background --python blender/tools/island_v3_to_graph.py
  blender --background --python blender/tools/island_v3_to_graph.py -- --spacing 16 --dry-run
  blender --background --python blender/tools/island_v3_to_graph.py -- --only RING,LOOP
"""
import bpy, os, sys, math, time

BLENDER_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # blender/
REPO        = os.path.dirname(BLENDER_SRC)
ROOT        = os.path.join(REPO, "assets", "world_source")
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
sys.path.insert(0, os.path.join(BLENDER_SRC, "addons"))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(BLENDER_SRC, "tools"))   # island_v3_to_roadkit lives here

import bmesh                                                    # noqa: E402
import island_v3_plan as P                                      # noqa: E402
import kit_common                                               # noqa: E402
import road_kit_authoring as rka                                # noqa: E402
from road_kit_authoring import graph_attrs as ga                # noqa: E402
from road_kit_authoring import graph_build as gb                # noqa: E402
from road_kit_authoring import graph_export as gx                # noqa: E402
from road_kit_authoring import graph_solve as gs                # noqa: E402

OUT = os.path.join(ROOT, "island_v3_roads.blend")
BACKUP = os.path.join(ROOT, "island_v3_roads.pre_graph.blend")

#: Viewport far clip baked into the saved .blend. The island spans ~3 km, so the 1 km default
#: clips the map away while you are framing it.
VIEW_CLIP_END = 10000.0
Z_CROSS_TOL = 4.0     # heights differing by more than this are a flyover, not a crossing
#: Auxiliary lane added at every ramp gore, and the distance it takes to open. One lane over 90 m
#: is an ordinary urban-motorway exit taper; both are per-edge attributes afterwards, so a hand
#: edit in Blender overrides this without touching the generator.
AUX_LANES = 1
AUX_TAPER = 90.0
#: WHICH END OF THE CARRIAGEWAY EVERY EXIT/ENTRY LANE OPENS AT. 'KERB' is the ordinary nearside
#: answer -- enter and leave the motorway from the OUTERMOST lane, which is what a driver expects
#: and what keeps the ramp aligned with the lane that opens for it. 'AUTO' measures each ramp and
#: allows offside (left-hand) ramps; use it only where the layout genuinely has them.
AUX_SIDE = 'AUTO'
SNAP_TOL = 26.0       # how far a free endpoint may be from a road before it counts as a T
WELD_TOL = 8.0        # free endpoints closer than this to each other become one node
MERGE_TOL = 12.0      # junctions closer than this are the SAME junction, not two

#: Per-tier edge attributes. Lane figures are v3 §5's, unchanged -- this is a change of
#: REPRESENTATION, not of design, so the widths must come out identical to the old pipeline's.
TIER_ATTRS = {
    "T1":   dict(lanes_fwd=2, lanes_bwd=2, lane_width=3.50, median_width=1.2,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb=False),
    "T1C":  dict(lanes_fwd=2, lanes_bwd=0, lane_width=3.50, median_width=0.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb=False),
    "T2":   dict(lanes_fwd=2, lanes_bwd=2, lane_width=3.25, median_width=3.0,
                 sidewalk_left_width=4.0, sidewalk_right_width=4.0, curb=True),
    "T3":   dict(lanes_fwd=1, lanes_bwd=1, lane_width=3.25, median_width=0.0,
                 sidewalk_left_width=3.5, sidewalk_right_width=3.5, curb=True),
    "RAMP": dict(lanes_fwd=1, lanes_bwd=0, lane_width=4.50, median_width=0.0,
                 sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb=False),
    "TOUGE": dict(lanes_fwd=1, lanes_bwd=1, lane_width=2.75, median_width=0.0,
                  sidewalk_left_width=0.0, sidewalk_right_width=0.0, curb=False),
}

#: Road classes with NO at-grade crossings: the expressway deck and its one-way carriageway
#: variant. Every vertex either touches gets `allow_cross = 0` (see `emit`), which is what stops a
#: movement being emitted across the motorway's median into an exit ramp on the far carriageway.
#: A RAMP is not in this set -- its far end is a surface junction that does break its median.
LIMITED_ACCESS_TIERS = frozenset(("T1", "T1C"))

#: Kerb corner radius by the widest tier at a junction -- a bus tracks a wider arc off an
#: arterial than off a lane.
TIER_FILLET = {"T1": 12.0, "T1C": 12.0, "T2": 8.0, "T3": 5.0, "RAMP": 10.0, "TOUGE": 4.0}


# ------------------------------------------------------------------------------- graph assembly

def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _seg_cross(a0, a1, b0, b1):
    """(t, u, x, y, z_on_a, z_on_b) for two segments crossing in plan, else None."""
    rx, ry = a1[0] - a0[0], a1[1] - a0[1]
    sx, sy = b1[0] - b0[0], b1[1] - b0[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qpx, qpy = b0[0] - a0[0], b0[1] - a0[1]
    t = (qpx * sy - qpy * sx) / den
    u = (qpx * ry - qpy * rx) / den
    if not (1e-6 < t < 1 - 1e-6 and 1e-6 < u < 1 - 1e-6):
        return None
    return (t, u, a0[0] + rx * t, a0[1] + ry * t,
            a0[2] + (a1[2] - a0[2]) * t, b0[2] + (b1[2] - b0[2]) * u)


def _project(p, a0, a1):
    """(t clamped to the segment, distance in XY, projected 3D point)."""
    rx, ry = a1[0] - a0[0], a1[1] - a0[1]
    L2 = rx * rx + ry * ry
    if L2 < 1e-12:
        return 0.0, float('inf'), a0
    t = ((p[0] - a0[0]) * rx + (p[1] - a0[1]) * ry) / L2
    t = max(0.0, min(1.0, t))
    q = (a0[0] + rx * t, a0[1] + ry * t, a0[2] + (a1[2] - a0[2]) * t)
    return t, math.hypot(p[0] - q[0], p[1] - q[1]), q


def build_graph(roads, z_tol=Z_CROSS_TOL, snap_tol=SNAP_TOL, weld_tol=WELD_TOL):
    """{name: {tier, pts, closed}} -> (verts, edges, edge_tier, junction_verts).

    `junction_verts` is the set of vertex indices that are REAL nodes; everything else is a shape
    point and gets stamped `NODE_NONE` by the caller."""
    lines = [(nm, d["tier"], [tuple(p) for p in d["pts"]], d["closed"])
             for nm, d in sorted(roads.items())]
    jpts, ins = [], {i: [] for i in range(len(lines))}

    def jid_for(pt):
        """Reuse a junction already placed within `MERGE_TOL`, else make a new one.

        Three roads meeting at almost-but-not-quite one spot otherwise produce a cluster of
        junctions a metre or two apart, and the chain between them is then far too short to carry
        either one's setback -- the island reported 0.6 m chains wanting 150 m of trim. Merging
        them is what makes that a single real junction."""
        for k, q in enumerate(jpts):
            if math.dist(pt[:2], q[:2]) < MERGE_TOL and abs(pt[2] - q[2]) <= z_tol:
                return k
        jpts.append(pt)
        return len(jpts) - 1

    def segs(pts, closed):
        n = len(pts)
        return [(k, pts[k], pts[(k + 1) % n]) for k in range(n if closed else n - 1)]

    # ---- 1. CROSS
    n_cross = 0
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            for si, a0, a1 in segs(lines[i][2], lines[i][3]):
                for sj, b0, b1 in segs(lines[j][2], lines[j][3]):
                    hit = _seg_cross(a0, a1, b0, b1)
                    if hit is None:
                        continue
                    t, u, x, y, za, zb = hit
                    if abs(za - zb) > z_tol:
                        continue          # flyover: leave them unconnected, on purpose
                    jid = jid_for((x, y, (za + zb) / 2.0))
                    ins[i].append((si, t, jid))
                    ins[j].append((sj, u, jid))
                    n_cross += 1

    # ---- 2. SNAP free endpoints onto nearby roads (T-junctions)
    n_snap, endpoint_jid = 0, {}
    for i, (nm, tier, pts, closed) in enumerate(lines):
        if closed:
            continue
        for which, p in ((0, pts[0]), (-1, pts[-1])):
            best = None
            for j, (nm2, t2, pts2, closed2) in enumerate(lines):
                if j == i:
                    continue
                for sj, b0, b1 in segs(pts2, closed2):
                    t, dist, q = _project(p, b0, b1)
                    if dist < snap_tol and abs(q[2] - p[2]) <= z_tol and (
                            best is None or dist < best[0]):
                        best = (dist, j, sj, t, q)
            if best is None:
                continue
            _d, j, sj, t, q = best
            jid = jid_for(q)
            ins[j].append((sj, t, jid))
            endpoint_jid[(i, which)] = jid
            n_snap += 1

    # ---- 3. emit, welding every junction and every coincident free endpoint
    verts, edges, edge_tier, jvert, free = [], [], [], {}, {}
    junction_verts = set()

    def vert_for_junction(jid):
        if jid not in jvert:
            jvert[jid] = len(verts)
            verts.append(jpts[jid])
            junction_verts.add(jvert[jid])
        return jvert[jid]

    def vert_for_free(co):
        key = (round(co[0] / weld_tol), round(co[1] / weld_tol), round(co[2] / weld_tol))
        if key in free:
            junction_verts.add(free[key])
            return free[key]
        free[key] = len(verts)
        verts.append(co)
        return free[key]

    for i, (nm, tier, pts, closed) in enumerate(lines):
        by_seg = {}
        for si, t, jid in ins[i]:
            by_seg.setdefault(si, []).append((t, jid))
        seq = []                      # (coord, junction id or None, is a free endpoint)
        n = len(pts)
        last = n if closed else n - 1
        for k in range(last):
            is_head = (k == 0 and not closed)
            seq.append((pts[k], endpoint_jid.get((i, 0)) if is_head else None, is_head))
            for t, jid in sorted(by_seg.get(k, [])):
                seq.append((jpts[jid], jid, False))
        if not closed:
            seq.append((pts[-1], endpoint_jid.get((i, -1)), True))

        # A JUNCTION THAT LANDS EXACTLY ON A POLYLINE VERTEX MUST REPLACE IT, NOT FOLLOW IT.
        # Appending it leaves two coincident points, and the edge between them is dropped by the
        # length guard below -- so the junction ends up attached to nothing on one side and the
        # road arrives at it as a dead end. That used to be unreachable (a projection landing
        # exactly on a vertex was a coincidence) and is now the NORMAL case for every interchange:
        # `island_v3_to_roadkit.pin_gores` puts a deck vertex at each gore on purpose, so the
        # ramp's endpoint projects onto it at t = 0 exactly. Without this the pinning turned all
        # eight ramps into dead ends (CAP 17 -> 25) and their gores into valency-2 bends.
        merged_seq = []
        for co, jid, is_end in seq:
            if merged_seq and _dist(co, merged_seq[-1][0]) <= 1e-6:
                p_co, p_jid, p_end = merged_seq[-1]
                if p_jid is None:                       # plain shape point: the junction wins
                    merged_seq[-1] = (co, jid, p_end or is_end)
                elif jid is None:
                    merged_seq[-1] = (p_co, p_jid, p_end or is_end)
                continue
            merged_seq.append((co, jid, is_end))
        seq = merged_seq

        idx = []
        for co, jid, is_end in seq:
            if jid is not None:
                idx.append(vert_for_junction(jid))
            elif is_end:
                idx.append(vert_for_free(co))
            else:
                idx.append(_append(verts, co))
        if closed:
            idx.append(idx[0])
        for a, b in zip(idx, idx[1:]):
            if a != b and _dist(verts[a], verts[b]) > 1e-6:
                edges.append((a, b))
                edge_tier.append(tier)

    # A vertex where three or more edges meet is a junction even if no step above named it one.
    deg = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    for v, d in deg.items():
        if d != 2:
            junction_verts.add(v)
    return verts, edges, edge_tier, junction_verts, dict(crossings=n_cross, snaps=n_snap)


def _append(verts, co):
    verts.append(co)
    return len(verts) - 1


def _dist(a, b):
    return math.dist(a, b)


# ---------------------------------------------------------------------------------- the emitter

def emit(verts, edges, edge_tier, junction_verts, name="IslandRoads"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], edges, [])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    ga.ensure_mesh_attributes(me)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm)
    vl = ga.ensure_vert_layers(bm)

    ground = _ground()
    for k, e in enumerate(bm.edges):
        tier = edge_tier[k]
        a = TIER_ATTRS.get(tier, TIER_ATTRS["T3"])
        for key in ("lanes_fwd", "lanes_bwd", "lane_width", "median_width",
                    "sidewalk_left_width", "sidewalk_right_width"):
            e[el[key]] = a[key]
        e[el["median_type"]] = (ga.MEDIAN_RAISED_CONCRETE if a["median_width"] >= 2.0
                                else ga.MEDIAN_PAINTED if a["median_width"] > 0.0
                                else ga.MEDIAN_NONE)
        e[el["curb_left_on"]] = 1 if a["curb"] else 0
        e[el["curb_right_on"]] = 1 if a["curb"] else 0
        e[el["curb_height"]] = 0.15 if a["curb"] else 0.0
        # SUPPORT IS DERIVED, NOT AUTHORED -- v3 section 6's rule, one number in, one decision
        # out: a surface high enough above its ground gets a deck and piers, and lowering it takes
        # them away again with no separate "is this a bridge" flag anywhere.
        mid = (e.verts[0].co + e.verts[1].co) / 2.0
        g = ground(mid.x, mid.y)
        kind = P.support_kind(mid.z, g)
        # The ground the piers land on, stored so the column height can be resolved per point
        # (`soffit - ground_z`) instead of a kit piece guessing one fixed length for the whole
        # island -- the loop deck is 12 m up and a ramp near its touchdown is a metre or two.
        e[el["ground_z"]] = g
        if kind == P.SUPPORT_PIER:
            e[el["deck_thickness"]] = 1.5
            e[el["pillar_spacing"]] = 40.0
            e[el["pillar_width"]] = 1.8
        elif kind == P.SUPPORT_FILL:
            e[el["deck_thickness"]] = 0.8
            e[el["pillar_spacing"]] = 0.0
        else:
            e[el["deck_thickness"]] = 0.0
            e[el["pillar_spacing"]] = 0.0

    # NO NODE ON THE EXPRESSWAY BREAKS ITS MEDIAN. `allow_cross` is the vertex-domain switch for
    # "may a movement here cross the opposing stream?", and it defaults to yes, which is right for
    # a surface junction and wrong for every metre of a limited-access road: an exit ramp hangs off
    # ONE carriageway, and traffic on the other cannot reach it without driving over the centre of
    # the motorway. Left unstamped, that is exactly what the exporter emitted -- at IC_YAMATE and
    # JCT_AIRPORT the ramp leaves too steeply to classify as a gore, so intersection rules applied
    # and the far carriageway got a right turn into the exit.
    #
    # Stamped from the ROAD CLASS rather than per interchange, so it holds for every node the
    # expressway ever grows, including ones no one has authored yet. A ramp touching down on a
    # surface arterial keeps `allow_cross = 1`: a diamond's on-ramp genuinely is entered from both
    # directions of the cross street, because that junction does break its median.
    limited = {v.index for k, e in enumerate(bm.edges) if edge_tier[k] in LIMITED_ACCESS_TIERS
               for v in e.verts}

    fillet_of = {}
    for k, e in enumerate(bm.edges):
        r = TIER_FILLET.get(edge_tier[k], 5.0)
        for v in e.verts:
            fillet_of[v.index] = max(fillet_of.get(v.index, 0.0), r)
    for v in bm.verts:
        if v.index in limited:
            v[vl["allow_cross"]] = 0
        if v.index in junction_verts:
            v[vl["node_type"]] = ga.NODE_AUTO
            v[vl["fillet_radius"]] = fillet_of.get(v.index, 5.0)
        else:
            # The resampled interior of a polyline: bend the road, build no junction. Without
            # this every 12 m sample would be trimmed from both ends and patched.
            v[vl["node_type"]] = ga.NODE_NONE
    bm.to_mesh(me)
    bm.free()
    me.update()
    return obj


def _ground():
    import island_v3_geom as G

    def ground(x, y):
        if G.inside(G.AIRPORT, x, y):
            return P.ISLAND_Z
        if G.inside(G.HARBOUR, x, y):
            return 2.0
        return 0.0
    return ground


# ------------------------------------------------------------------------------------------ run

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    spacing = float(_arg(argv, "--spacing", 14.0))
    only = _arg(argv, "--only", None)
    dry = "--dry-run" in argv

    t0 = time.time()
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()

    import island_v3_to_roadkit as R
    roads = R.collect_roads(spacing)
    if only:
        keep = set(only.split(","))
        roads = {k: v for k, v in roads.items() if k in keep}
    print("[graph] %d roads, %d authored points"
          % (len(roads), sum(len(r["pts"]) for r in roads.values())))

    verts, edges, tiers, jverts, stats = build_graph(roads)
    print("[graph] %d crossings welded, %d endpoints snapped -> %d verts / %d edges / %d junctions"
          % (stats["crossings"], stats["snaps"], len(verts), len(edges), len(jverts)))

    obj = emit(verts, edges, tiers, jverts)
    if dry:
        print("[graph] --dry-run: graph emitted, not solved or built")
        return

    # WELD ANY CROSSING THE BUILDER MISSED. `build_graph` tests pairs of DIFFERENT roads and
    # merges junctions within `MERGE_TOL`, so a crossing a few metres from another junction can
    # end up with no shared vertex -- two roads laid over each other at the same height that cars
    # cannot turn between. Repairing the built graph catches it whatever the cause.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        n_weld = gs.weld_crossings(bm)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    if n_weld:
        print("[graph] welded %d leftover same-grade crossing(s) into real junctions" % n_weld)

    # RAMP GORES GET A TAPERED AUX LANE, derived rather than authored. An express-lane exit that
    # simply peels a lane off the through carriageway is the failure the taper exists to fix, so
    # the island -- the only real test data there is -- should exercise it everywhere it applies.
    # Needs a solve first (only the solver knows which nodes are gores and which arm is the trunk),
    # then a rebuild so the geometry reflects the stamp.
    pre = gs.solve_object(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        n_aux, aux_wrong = gs.auto_aux_lanes(bm, pre, count=AUX_LANES, taper=AUX_TAPER,
                                             side_mode=AUX_SIDE)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    print("[graph] auto aux lanes: %d chain(s) stamped (%d lane, %.0f m taper)"
          % (n_aux, AUX_LANES, AUX_TAPER))
    if aux_wrong:
        # The ramp is on the far side of the carriageway its own traffic uses, so reaching it
        # means crossing the opposing stream. No lane placement can fix that -- the ramp needs
        # moving in the source layout -- so name the nodes rather than quietly building it.
        print("[graph] %d ramp(s) needed a median-side (left-hand) auxiliary lane: %s"
              % (len(aux_wrong),
                 ", ".join("node %d (%.1f deg)" % w for w in aux_wrong[:8])))

    result, carrier = gb.build_object(obj)
    kinds = {}
    for n in result.nodes:
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    print("[graph] node kinds: %s" % ", ".join("%s=%d" % kv for kv in sorted(kinds.items())))
    print("[graph] carrier %d verts / %d polyline points"
          % (len(carrier.data.vertices), len(carrier.data.edges)))
    if result.too_short:
        print("[graph] %d edge(s) too short for their junctions (first 5): %s"
              % (len(result.too_short), result.too_short[:5]))
    if result.width_steps:
        print("[graph] %d width step(s) needing a taper (first 5): %s"
              % (len(result.width_steps), result.width_steps[:5]))
    xs = gs.crossings_for(obj)
    print("[graph] %d unwelded same-grade crossing(s) remaining" % len(xs))

    lanekit = os.path.splitext(OUT)[0] + ".lanekit.json"
    lstats = gx.export(obj, lanekit)
    print("[graph] lanekit: %d lane(s) + %d connector(s) across %d junction(s) -> %s"
          % (lstats["lanes"], lstats["connectors"], lstats["nodes"],
             os.path.basename(lanekit)))
    gx.preview(obj)

    _add_preview_lighting()
    # The island is ~3 km across, so Blender's default 1 km viewport far clip cuts the map in
    # half the moment you zoom out far enough to frame it -- the world looks half-generated when
    # it is not. `setup_view_clip` also lifts the near plane to keep the depth ratio sane.
    kit_common.setup_view_clip(VIEW_CLIP_END)

    if os.path.exists(OUT) and not os.path.exists(BACKUP):
        os.replace(OUT, BACKUP)
        print("[graph] previous network backed up to %s" % os.path.basename(BACKUP))
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("[graph] wrote %s in %.1fs" % (OUT, time.time() - t0))


def _add_preview_lighting():
    """A sun and a grey world, so the saved file is actually viewable.

    This tool starts from an empty homefile (the graph is generated, not authored on top of an
    existing scene), which means no lamp and a black world -- an aerial render of it came out
    entirely black, which reads as "nothing was generated" rather than "nothing is lit"."""
    world = bpy.data.worlds.get("RKA_Preview") or bpy.data.worlds.new("RKA_Preview")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world
    if bpy.data.objects.get("RKA_Sun") is None:
        sun_d = bpy.data.lights.new("RKA_Sun", 'SUN')
        sun_d.energy = 3.0
        sun = bpy.data.objects.new("RKA_Sun", sun_d)
        sun.rotation_euler = (math.radians(50.0), 0.0, math.radians(35.0))
        bpy.context.scene.collection.objects.link(sun)


def _arg(argv, flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default


if __name__ == "__main__":
    main()
