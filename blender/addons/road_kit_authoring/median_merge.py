"""median_merge.py -- one CONTINUOUS median wall mesh spanning a whole linked chain of segments,
instead of one small median-wall object per piece (2026-08, user-reported: "change the current
median to [a] single mesh of curb instead of curb on each way" -- explicitly chosen to be fully
automatic/always live-synced, run every `live_edit._flush_rebuilds` after the normal per-piece
rebuild dispatch, not a manual one-shot button).

This is the ONE deliberate exception to this addon's otherwise-universal "each piece owns its own
small generated objects" convention (see `ops_intersection.build_junction_curb_segments`'s own
docstring) -- a median wall specifically has a visible seam at every joint if left as separate
per-piece objects (each with its own flat end cap), which position/tangent/Z sync alone (see
ROAD_JOINT_TRANSITION_STUDY.md) cannot fix -- only ONE continuous mesh with no interior end caps
can. Scope, deliberately narrow: ONLY the median WALL (`median_style` BOX/ASSET, matching
`ops_segment._build_segment_from_points`'s own median-wall styles) is merged -- a flush/NONE-style
median is just painted lane-marking stripes (`intersection_kit.build_segment_lane_markings`), which
already read continuously across a joint for free once the underlying `median_width`/`_end` taper
agrees on both sides (the earlier median-joint-sync fix) -- there is no wall object to seam in the
first place, so NONE-style needs nothing from this module. ASSET-style (a repeated instanced curb
piece, not a swept mesh) doesn't have the same "flat end cap" seam either, but restarting its
spacing pattern at every piece boundary still looks broken -- left as a known follow-up, not
implemented (see `_mergeable_edges` below).

Delete+recreate is safe here (unlike the crash-surface `clear_generated_mesh_objects` was fixed
for) because this module is only ever called from `live_edit._flush_rebuilds`, which itself only
ever runs OUTSIDE the depsgraph callback -- on Blender's main-loop timer queue, once drag activity
has already settled (see that function's own docstring) -- never while a modal Transform operator
is still holding live references to these objects."""
import bpy


MEDIAN_CHAIN_COLLECTION = "RKA_MedianChains"


def _median_chain_collection(context):
    """The one dedicated (hidden-from-the-piece-list) collection every merged median wall object
    lives in, created + linked to the scene root on first use."""
    coll = bpy.data.collections.get(MEDIAN_CHAIN_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(MEDIAN_CHAIN_COLLECTION)
    if coll.name not in context.scene.collection.children:
        context.scene.collection.children.link(coll)
    return coll


def _segment_collections():
    """Every LOCAL (non-linked-library), plain GN segment collection in the file -- has
    `rka_curve_object`, is NOT a lane-count transition piece (`rka_lanes_a` in keys, a separate,
    more complex per-end shape this module doesn't apply to)."""
    return [c for c in bpy.data.collections
            if c.library is None and "rka_curve_object" in c.keys() and "rka_lanes_a" not in c.keys()]


def _dependent_spine_end(obj):
    """Local copy of `live_edit._dependent_spine_end`'s exact rule (not imported, to keep this
    module import-independent of `live_edit` -- it's `live_edit` that calls INTO this module, at
    the tail of a flush, so the reverse import would be circular): `'end'` for `port_B`, `'start'`
    for everything else (origin marker / `port_A`)."""
    return "end" if obj.get("rka_port") == "B" else "start"


def _segment_end_state(coll, end):
    """(style, width, active) for one END of a segment -- `style` is `rka_median_style` (shared
    for the whole piece), `width` is the END-AWARE `rka_median_width`/`rka_median_width_end`
    (falls back to start, same convention as `ops_segment._effective_end_median`), `active` = a
    REAL median there (width > 0 AND genuinely two-way -- the same gate
    `intersection_kit.Arm.median_half`/`build_segment_from_spine` both apply, so this module can
    never disagree with what the piece's own geometry actually built)."""
    style = coll.get("rka_median_style", "BOX")
    if end == "end":
        width = coll.get("rka_median_width_end", coll.get("rka_median_width", 0.0))
        lanes_f = coll.get("rka_lanes_end", coll.get("rka_lanes", 1))
        lanes_b = coll.get("rka_lanes_backward_end", coll.get("rka_lanes_backward", 0))
    else:
        width = coll.get("rka_median_width", 0.0)
        lanes_f = coll.get("rka_lanes", 1)
        lanes_b = coll.get("rka_lanes_backward", 0)
    active = width > 0.0 and lanes_f > 0 and lanes_b > 0
    return style, width, active


def _mergeable_edges(RKA_LINKED_TO_KEY, ORIGIN_MARKER_KEY):
    """`[(collA_name, endA, collB_name, endB), ...]` -- every LIVE link between two DIFFERENT
    segments' own ends where BOTH sides have an ACTIVE median in the SAME mergeable style ('BOX'
    only for now -- see module docstring). A style mismatch, either side inactive, or the target
    being an ARM (arms carry no median WALL geometry of their own -- see
    `ROAD_JOINT_TRANSITION_STUDY.md`'s per-arm-median section) just means the run doesn't extend
    past that joint; the per-piece wall on whichever side is inactive/mismatched stays local."""
    segs = _segment_collections()
    seg_names = {c.name for c in segs}
    edges = []
    for coll in segs:
        for obj in coll.objects:
            if obj.type != 'EMPTY':
                continue
            is_port = obj.get("rka_port") in ("A", "B")
            is_origin = ORIGIN_MARKER_KEY in obj.keys()
            if not (is_port or is_origin):
                continue
            target_name = obj.get(RKA_LINKED_TO_KEY)
            if not target_name:
                continue
            target_obj = bpy.data.objects.get(target_name)
            if target_obj is None or "rka_arm_name" in target_obj.keys():
                continue
            t_is_port = target_obj.get("rka_port") in ("A", "B")
            t_is_origin = ORIGIN_MARKER_KEY in target_obj.keys()
            if not (t_is_port or t_is_origin):
                continue
            target_coll = next((c for c in segs if target_obj.name in c.objects), None)
            if target_coll is None or target_coll.name == coll.name or target_coll.name not in seg_names:
                continue
            this_end = _dependent_spine_end(obj)
            other_end = _dependent_spine_end(target_obj)
            style_a, _, active_a = _segment_end_state(coll, this_end)
            style_b, _, active_b = _segment_end_state(target_coll, other_end)
            if not (active_a and active_b) or style_a != style_b or style_a != 'BOX':
                continue
            edges.append((coll.name, this_end, target_coll.name, other_end))
    return edges


def _build_connectivity(edges):
    """`{(coll_name, end): (other_coll_name, other_end)}`, both directions -- BUT a `(coll, end)`
    that would map to more than one target (two different pieces both linking into the same shared
    port -- a real branch) is dropped from the map entirely rather than picking one arbitrarily, so
    a branch just ends the merge run on every side touching it (safe default: no piece is ever
    silently merged into the wrong neighbor)."""
    multi = {}
    for a_name, a_end, b_name, b_end in edges:
        multi.setdefault((a_name, a_end), []).append((b_name, b_end))
        multi.setdefault((b_name, b_end), []).append((a_name, a_end))
    return {k: v[0] for k, v in multi.items() if len(v) == 1}


def _order_chain(start_coll, conn, visited):
    """Walk one chain starting at `start_coll` (must have exactly ONE of its two ends present in
    `conn` -- a genuine chain terminus). Returns `[(coll_name, aligned), ...]` in chain order,
    `aligned` = True if this piece's own natural spine point order (start->end) already flows in
    the chain's forward direction, False if it must be walked in reverse -- see
    `_oriented_edges`. `None` if `start_coll` isn't a valid terminus or a cycle is hit (a closed
    loop -- not handled, extremely rare for a road median; skipped rather than guessed at)."""
    ends_present = [e for e in ("start", "end") if (start_coll, e) in conn]
    if len(ends_present) != 1:
        return None
    conn_end = ends_present[0]
    aligned = (conn_end == "end")   # natural order flows unconnected-end -> conn_end
    chain = [(start_coll, aligned)]
    visited.add(start_coll)
    cur_coll, cur_exit_end = start_coll, conn_end
    while True:
        nxt = conn.get((cur_coll, cur_exit_end))
        if nxt is None:
            break
        next_coll, arrive_end = nxt
        if next_coll in visited:
            return None   # cycle -- bail, don't attempt to merge a loop
        next_aligned = (arrive_end == "start")
        chain.append((next_coll, next_aligned))
        visited.add(next_coll)
        exit_end = "end" if arrive_end == "start" else "start"
        if (next_coll, exit_end) not in conn:
            break   # this piece's other end has no further connection -- chain ends here
        cur_coll, cur_exit_end = next_coll, exit_end
    return chain


def _median_chains(RKA_LINKED_TO_KEY, ORIGIN_MARKER_KEY):
    """Every mergeable chain of 2+ segments in the file, each `[(coll_name, aligned), ...]` in
    walk order (see `_order_chain`). Starts only from genuine termini (degree-1 nodes in the
    connectivity graph) so every chain is discovered exactly once, from one end."""
    edges = _mergeable_edges(RKA_LINKED_TO_KEY, ORIGIN_MARKER_KEY)
    conn = _build_connectivity(edges)
    starts = sorted({name for (name, _end) in conn.keys()})
    visited = set()
    chains = []
    for name in starts:
        if name in visited:
            continue
        degree = sum(1 for e in ("start", "end") if (name, e) in conn)
        if degree != 1:
            continue   # a middle piece of some other chain, or a branch point -- not a start
        chain = _order_chain(name, conn, visited)
        if chain is not None and len(chain) >= 2:
            chains.append(chain)
    return chains


def _member_median_edges(coll):
    """This segment's own two median-edge polylines (`intersection_kit.build_segment_from_spine`'s
    `median_edges`), from its CURRENT live spine control points -- reuses the exact same tested
    taper math every per-piece median wall already uses, rather than re-deriving it. `(None, None)`
    if the spine is missing/degenerate or the median is inactive at BOTH ends (nothing to merge)."""
    from . import ops_segment
    ik = ops_segment.ik()
    spine_name = coll.get("rka_curve_object")
    spine_obj = bpy.data.objects.get(spine_name) if spine_name else None
    if spine_obj is None or spine_obj.type != 'CURVE':
        return None, None
    pts = ops_segment._spine_control_points(spine_obj)
    if len(pts) < 2:
        return None, None
    seg = ik.build_segment_from_spine(
        pts, lane_width=coll.get("rka_lane_width", 5.0), lanes=coll.get("rka_lanes", 1),
        lanes_backward=coll.get("rka_lanes_backward", 0),
        traffic_side=coll.get("rka_traffic_side", "LEFT"),
        median_width=coll.get("rka_median_width", 0.0),
        median_width_end=ops_segment._effective_end_median(coll),
        lanes_end=ops_segment._effective_end_lanes(coll, backward=False),
        lanes_backward_end=ops_segment._effective_end_lanes(coll, backward=True))
    edges = seg.get("median_edges") or []
    if len(edges) != 2:
        return None, None
    return edges[0], edges[1]


def _oriented_edges(coll_name, aligned):
    """This member's two median-edge polylines, reordered to flow in the CHAIN's forward
    direction AND to land on the same PHYSICAL side as every other member's `edge_0`/`edge_1`.

    2026-08 (fixed after `smoketest_median_chain_merge.py` first caught it): a piece's `edge_0`
    vs `edge_1` identity is NOT a fixed physical label independent of point order -- `lane_perp`/
    `offset_line_tapered` (`intersection_kit.build_segment_from_spine`) compute the per-point
    OFFSET DIRECTION from that spine's own LOCAL, ARRAY-ORDER tangent (`pts[i+1] - pts[i]`), so
    reversing which end is index 0 flips the local tangent -- and therefore flips which physical
    side `edge_0` lands on. `aligned` (this piece's natural order already flows chain-forward)
    keeps that tangent chain-consistent, so `edge_0`/`edge_1` need no swap. NOT aligned means this
    piece's natural array order runs chain-BACKWARD, so its own `edge_0`/`edge_1` are computed
    from a tangent that's already 180 deg off from the chain's flow -- reversing just the POINT
    ORDER within each array (keeping the 0/1 labels) would concatenate two DIFFERENT physical
    sides together. Confirmed concretely: seg1 (aligned) put `edge_0` on the +Y side; seg2 (not
    aligned, spine [92,58,52] -- a DECREASING array, so its own local tangent points -X) put its
    OWN `edge_0` on the -Y side -- the wrong one to concatenate with seg1's +Y `edge_0`. So a
    reversed piece needs BOTH its point order reversed AND `edge_0`<->`edge_1` swapped."""
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return None, None
    e0, e1 = _member_median_edges(coll)
    if e0 is None:
        return None, None
    if aligned:
        return e0, e1
    return list(reversed(e1)), list(reversed(e0))


def _concat_side(chain):
    """`[edges_side0, edges_side1]` -- each a single continuous list of (x,y,z) points spanning
    every member of `chain` in order, with each subsequent member's FIRST point dropped (it should
    coincide exactly with the previous member's LAST point -- the joint-sync fixes elsewhere in
    this addon guarantee that -- so concatenating naively would otherwise leave a degenerate
    zero-length double point at every joint)."""
    sides = [[], []]
    for i, (coll_name, aligned) in enumerate(chain):
        e0, e1 = _oriented_edges(coll_name, aligned)
        if e0 is None:
            return None
        for side_idx, e in enumerate((e0, e1)):
            pts = e if i == 0 else e[1:]
            sides[side_idx].extend(pts)
    return sides


def _clear_member_walls(coll):
    """Delete THIS member's own individual median wall objects (`curb_<coll>_median_A`/`_B`,
    `ops_segment._build_segment_from_points`'s naming) -- they were just (re)built by that piece's
    own normal rebuild earlier in the SAME flush; once a merged chain covers this joint, only the
    merged wall should remain visible, or the two would visibly overlap/z-fight."""
    for tag in ("median_A", "median_B"):
        name = "curb_%s_%s" % (coll.name, tag)
        obj = coll.objects.get(name)
        if obj is None:
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def sync_median_chains(context, RKA_LINKED_TO_KEY, ORIGIN_MARKER_KEY):
    """The one entry point -- called from `live_edit._flush_rebuilds`'s tail, AFTER every normal
    per-piece rebuild this flush already ran (so every member's spine/median properties are
    current). Fully recomputes every median chain from scratch and rebuilds its merged wall(s) --
    delete+recreate every call (see module docstring for why that's safe here specifically)."""
    import kit_common as kc

    chain_coll = _median_chain_collection(context)
    for obj in list(chain_coll.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)

    chains = _median_chains(RKA_LINKED_TO_KEY, ORIGIN_MARKER_KEY)
    for idx, chain in enumerate(chains):
        sides = _concat_side(chain)
        if sides is None:
            continue
        anchor = bpy.data.collections.get(chain[0][0])
        if anchor is None:
            continue
        curb_height = anchor.get("rka_curb_height", 0.15)
        curb_thickness = anchor.get("rka_curb_thickness", 0.25)
        curb_matkey = anchor.get("rka_curb_matkey", "concrete")
        median_style = anchor.get("rka_median_style", "BOX")
        base = "curb_medianchain_%d" % idx
        for side_idx, pts in enumerate(sides):
            if len(pts) < 2:
                continue
            name = "%s_%s" % (base, "A" if side_idx == 0 else "B")
            kc.curb_loop(name, [(p[0], p[1], p[2], 0.0) for p in pts], chain_coll,
                         curb_style=median_style, curb_height=curb_height,
                         curb_thickness=curb_thickness, matkey=curb_matkey, closed=False)
        for coll_name, _aligned in chain:
            coll = bpy.data.collections.get(coll_name)
            if coll is not None:
                _clear_member_walls(coll)
