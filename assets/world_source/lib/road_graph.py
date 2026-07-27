#!/usr/bin/env python3
"""
road_graph.py — abstract road-centerline graph -> traffic lane data (PURE PYTHON, no bpy).

The traffic model is a freeform GRAPH, not a grid (the GTA paths.ipl shape): junction NODES
joined by polyline centerline EDGES annotated with lanes-per-direction / oneway / class.
Three sources feed the same graph:

  * from_town_grid(grid)   — the cell-grid solver (master arterial backbone, any procedural
                             district): maximal straight runs split at junction footprints.
  * from_curves(curves)    — hand-authored Blender `road_<name>` curves drawn over PLATEAU
                             road meshes (districts). Endpoint/mid-polyline touch clustering
                             finds the junctions at build time — NOT at runtime.
  * (Phase 3)              — highway corridor splines, split at every gore.

From the graph, generate() emits everything the Godot side consumes, as plain data the
assembler turns into `lane_` / `intersection_` empties:

  * per-edge per-direction per-lane-index directional LANE routes (keep-left, offset
    (i+0.5)*LANE_W from the centerline, trimmed back at junction stop lines);
  * per-junction TURN CONNECTORS (bezier through the junction box, tangent at both ends)
    wired with explicit next_routes/next_weights — turning is a data lookup at runtime,
    never endpoint-clustering;
  * per-junction intersection markers (position + box size) for IntersectionZone.

Keep-left (Japan) legality: 1-lane approach -> L/S/R as arms exist; >=2 lanes -> curb lane
(index 0) gets L+S, median lane (index n-1) gets R+S, middle lanes S only. Target lane:
L curb->curb, R median->median, S index-clamped — the clamp IS the mixed-lane-count answer.

Run `python3 lib/road_graph.py` for the self-test.
"""
import math

LANE_W = 3.5                  # lane width (m) — matches road_network.LANE_OFF*2
STOP_MARGIN = 1.0             # extra trim (m) behind the junction box edge (stop line)
CONNECT_EPS = 2.0             # endpoint clustering radius (m) for from_curves junctions
BEZ_SAMPLES = 8               # samples per turn-connector bezier
MIN_LINK_LEN = 4.0            # links shorter than this after trimming collapse to 2 points

# straight-biased movement weights (per turn kind); normalized over available movements
TURN_WEIGHTS = {'S': 0.6, 'L': 0.2, 'R': 0.2}


# ── data model ──────────────────────────────────────────────────────────────────────────

class Edge:
    """One road centerline between two junction nodes.

    pts        : [(x, y, z), ...] polyline, ordered a -> b (z carried through; flat = 0)
    a, b       : node ids (indices into RoadGraph.nodes)
    lanes_f    : lane count in the a->b direction
    lanes_r    : lane count in the b->a direction (0 = oneway a->b)
    cls        : 'alley'|'local'|'oneway'|'arterial'|'highway' (informational + signals)
    name       : stable route-name stem (unique within the graph)
    """
    def __init__(self, name, pts, a, b, lanes_f=1, lanes_r=1, cls='local', median=0.0):
        self.name = name
        self.pts = [(_f(p[0]), _f(p[1]), _f(p[2]) if len(p) > 2 else 0.0) for p in pts]
        self.a = a
        self.b = b
        self.lanes_f = lanes_f
        self.lanes_r = lanes_r
        self.cls = cls
        self.median = _f(median)   # physical median width (m); lane packs shift out by median/2


class Node:
    """A junction (or dead end): world position + the edges that touch it."""
    def __init__(self, x, y, z=0.0):
        self.x, self.y, self.z = _f(x), _f(y), _f(z)
        self.edges = []          # [(edge_index, 'a'|'b')] — which end of each edge sits here

    def degree(self):
        return len(self.edges)


class RoadGraph:
    def __init__(self, driving_side='LEFT'):
        self.nodes = []          # [Node]
        self.edges = []          # [Edge]
        self.driving_side = driving_side   # 'LEFT' | 'RIGHT' -- see generate()'s docstring

    def add_node(self, x, y, z=0.0):
        self.nodes.append(Node(x, y, z))
        return len(self.nodes) - 1

    def node_at(self, x, y, eps=CONNECT_EPS):
        """Existing node within eps of (x,y), else -1."""
        for i, n in enumerate(self.nodes):
            if (n.x - x) ** 2 + (n.y - y) ** 2 <= eps * eps:
                return i
        return -1

    def ensure_node(self, x, y, z=0.0, eps=CONNECT_EPS):
        i = self.node_at(x, y, eps)
        return i if i >= 0 else self.add_node(x, y, z)

    def add_edge(self, name, pts, lanes_f=1, lanes_r=1, cls='local', eps=CONNECT_EPS,
                 median=0.0):
        """Add a centerline; its ends snap to (or create) junction nodes."""
        a = self.ensure_node(pts[0][0], pts[0][1], pts[0][2] if len(pts[0]) > 2 else 0.0, eps)
        b = self.ensure_node(pts[-1][0], pts[-1][1], pts[-1][2] if len(pts[-1]) > 2 else 0.0, eps)
        e = Edge(name, pts, a, b, lanes_f, lanes_r, cls, median)
        self.edges.append(e)
        idx = len(self.edges) - 1
        self.nodes[a].edges.append((idx, 'a'))
        self.nodes[b].edges.append((idx, 'b'))
        return idx


def _f(v):
    return float(v)


# ── geometry helpers ────────────────────────────────────────────────────────────────────

def _seg_len(p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1])


def poly_len(pts):
    return sum(_seg_len(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _norm(vx, vy):
    l = math.hypot(vx, vy)
    return (vx / l, vy / l) if l > 1e-9 else (0.0, 0.0)


def _heading_at(pts, end):
    """Unit travel direction leaving ('a') or arriving ('b') — always pointing a->b."""
    if end == 'a':
        return _norm(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    return _norm(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])


def offset_polyline(pts, off):
    """Offset a polyline laterally by `off` metres to the RIGHT of travel (matching
    VehicleRoute's runtime convention: forward -Z => right +X, i.e. right of (tx,ty) in
    Blender +Y=N coordinates is (ty, -tx)). Negative = left of travel (keep-left lanes)."""
    out = []
    m = len(pts)
    for i in range(m):
        a = pts[max(0, i - 1)]
        b = pts[min(m - 1, i + 1)]
        tx, ty = _norm(b[0] - a[0], b[1] - a[1])
        rx, ry = ty, -tx
        p = pts[i]
        out.append((p[0] + rx * off, p[1] + ry * off, p[2]))
    return out


def trim_polyline(pts, trim_a, trim_b):
    """Cut `trim_a` metres off the start and `trim_b` off the end (arc-length walk).
    Returns at least a 2-point segment (collapses toward the middle when over-trimmed)."""
    total = poly_len(pts)
    trim_a = max(0.0, min(trim_a, total * 0.45))
    trim_b = max(0.0, min(trim_b, total * 0.45))
    return _slice_by_len(pts, trim_a, total - trim_b)


def _slice_by_len(pts, s0, s1):
    """Sub-polyline between arc lengths s0..s1 (with interpolated end points)."""
    out = []
    acc = 0.0
    def lerp(p, q, t):
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t)
    for i in range(len(pts) - 1):
        p, q = pts[i], pts[i + 1]
        sl = _seg_len(p, q)
        if sl < 1e-9:
            continue
        seg0, seg1 = acc, acc + sl
        if seg1 < s0 or seg0 > s1:
            acc = seg1
            continue
        t0 = max(0.0, (s0 - seg0) / sl)
        t1 = min(1.0, (s1 - seg0) / sl)
        a = lerp(p, q, t0)
        b = lerp(p, q, t1)
        if not out:
            out.append(a)
        elif _seg_len(out[-1], a) > 1e-6:
            out.append(a)
        if _seg_len(out[-1], b) > 1e-6:
            out.append(b)
        acc = seg1
    if len(out) < 2:                      # over-trimmed: emit a tiny middle stub
        mid = _slice_by_len(pts, poly_len(pts) * 0.45, poly_len(pts) * 0.55)
        return mid if len(mid) >= 2 else [pts[0], pts[-1]]
    return out


def bezier(p0, h0, p1, h1, n=BEZ_SAMPLES):
    """Cubic bezier from p0 (leaving along unit h0) to p1 (arriving along unit h1); handle
    length dist/3 keeps short left turns and long right arcs tangent at both ends. 3D-lerps z."""
    d = _seg_len(p0, p1)
    hl = d / 3.0
    c0 = (p0[0] + h0[0] * hl, p0[1] + h0[1] * hl, p0[2])
    c1 = (p1[0] - h1[0] * hl, p1[1] - h1[1] * hl, p1[2])
    out = []
    for k in range(n + 1):
        t = k / n
        mt = 1.0 - t
        out.append((
            mt**3 * p0[0] + 3 * mt**2 * t * c0[0] + 3 * mt * t**2 * c1[0] + t**3 * p1[0],
            mt**3 * p0[1] + 3 * mt**2 * t * c0[1] + 3 * mt * t**2 * c1[1] + t**3 * p1[1],
            mt**3 * p0[2] + 3 * mt**2 * t * c0[2] + 3 * mt * t**2 * c1[2] + t**3 * p1[2],
        ))
    return out


def turn_of(h_in, h_out):
    """'L' / 'S' / 'R' from the signed turn between two unit headings (Blender +Y=N frame:
    cross > 0 = left turn)."""
    cross = h_in[0] * h_out[1] - h_in[1] * h_out[0]
    dot = h_in[0] * h_out[0] + h_in[1] * h_out[1]
    if dot > 0.7071 and abs(cross) < 0.7071:
        return 'S'
    return 'L' if cross > 0 else 'R'


def approach_of(h_in):
    """Compass name of the junction ARM a car arrives from, given its unit heading INTO the
    junction (Blender +Y = N): heading south (0,-1) = coming from the north arm = 'N'.
    Phase 2's JunctionArbiter keys its conflict table on this."""
    ax, ay = -h_in[0], -h_in[1]
    if abs(ax) >= abs(ay):
        return 'E' if ax > 0 else 'W'
    return 'N' if ay > 0 else 'S'


def simplify_polyline(pts, angle_eps_deg=2.0, max_gap=30.0):
    """Drop near-collinear interior points but never let two kept points drift more than
    max_gap apart (Catmull-Rom needs intermediate support on long straights). Endpoints
    always survive. Used by the marker emitter so cell-spaced (7 m) grid polylines don't
    bloat the blend/glTF with redundant empties."""
    if len(pts) <= 2:
        return list(pts)
    cos_eps = math.cos(math.radians(angle_eps_deg))
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        h0 = _norm(pts[i][0] - out[-1][0], pts[i][1] - out[-1][1])
        h1 = _norm(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        bend = h0[0] * h1[0] + h0[1] * h1[1] < cos_eps
        if bend or _seg_len(out[-1], pts[i]) >= max_gap:
            out.append(pts[i])
    out.append(pts[-1])
    return out


# ── generation ──────────────────────────────────────────────────────────────────────────

class LaneRoute:
    """One generated directional traffic route (a lane of a link, or a turn connector).

    name        : globally unique within the graph (assembler may add a piece prefix)
    pts         : [(x, y, z), ...] in travel order
    end_behavior: 'CHAIN' | 'DESPAWN'
    next_routes : [route names] (same-graph names, pre-prefix)
    next_weights: [float] parallel to next_routes ([] = uniform)
    turn        : '' for lanes; 'L'/'S'/'R' for connectors
    approach    : '' for lanes; 'N'/'E'/'S'/'W' junction arm the car arrives from (connectors)
    """
    def __init__(self, name, pts, end_behavior='DESPAWN', next_routes=None,
                 next_weights=None, turn='', approach=''):
        self.name = name
        self.pts = pts
        self.end_behavior = end_behavior
        self.next_routes = next_routes or []
        self.next_weights = next_weights or []
        self.turn = turn
        self.approach = approach


class JunctionOut:
    """One generated intersection marker: centre + box footprint (m)."""
    def __init__(self, name, x, y, z, size_x, size_y):
        self.name = name
        self.x, self.y, self.z = x, y, z
        self.size_x, self.size_y = size_x, size_y


def _junction_radius(rg, node):
    """Stop-line distance from the node centre: half the widest crossing carriageway (in
    metres, physical median included) plus a margin, so lane ends sit just outside the paved
    junction box on every arm."""
    widest_m = LANE_W
    for (ei, _end) in node.edges:
        e = rg.edges[ei]
        widest_m = max(widest_m, (e.lanes_f + e.lanes_r) * LANE_W + e.median)
    return widest_m / 2.0 + STOP_MARGIN


def _lane_offset_from_center(lane_idx, lanes, median=0.0, driving_side='LEFT'):
    """Signed right-of-travel offset of lane `lane_idx` (0 = curb/leftmost … lanes-1 =
    median-most). Keep-left (`driving_side='LEFT'`, default): the whole direction sits LEFT of
    the centerline, so offsets are negative; curb lane is farthest left. `driving_side='RIGHT'`
    mirrors the whole lane pack to the positive (right-of-travel) side -- see offset_polyline's
    right-of-travel sign convention this combines with. A physical `median` width pushes the
    whole lane pack a further median/2 out, leaving the strip |offset| < median/2 clear for the
    divider (unaffected by driving_side -- it's symmetric either way)."""
    mag = median / 2.0 + (lanes - lane_idx - 0.5) * LANE_W
    return mag if driving_side == 'RIGHT' else -mag


def generate(rg, radius_fn=None, driving_side=None):
    """RoadGraph -> (lanes: [LaneRoute], junctions: [JunctionOut]).

    Per edge, per direction, per lane index: a trimmed offset polyline route named
    <edge>_<F|R><lane>. Per junction, per incoming lane: turn connectors named
    c<node>_<in-route>_<L|S|R> (SHORT names — the out-lane lives in next_routes, not the
    name, so a district-prefixed lane_ empty stays under Blender's 63-char object-name cap),
    chained in and out with explicit next_routes. Dead ends (degree-1 nodes) leave the
    incoming lanes' end_behavior DESPAWN. radius_fn(rg, node) overrides the derived
    stop-line radius (e.g. the master's 21 m paved arterial footprint). `driving_side`
    ('LEFT'/'RIGHT') overrides `rg.driving_side` when given; None (default) uses whatever the
    graph itself was built with (getattr fallback to 'LEFT' for a RoadGraph predating this
    attribute) -- 'RIGHT' mirrors both the lane-pack offset (_lane_offset_from_center) and the
    turn-legality/lane-mapping below (curb lane turns right instead of left)."""
    rad = radius_fn or _junction_radius
    driving_side = driving_side if driving_side is not None else getattr(rg, 'driving_side', 'LEFT')
    lanes = []
    by_name = {}
    # node id -> list of (in_route_name, edge_idx, dir_flag, lane_idx, end_pt, heading)
    incoming = {}
    # node id -> list of (out_route_name, edge_idx, dir_flag, lane_idx, start_pt, heading, out_lanes)
    outgoing = {}

    for ei, e in enumerate(rg.edges):
        trim_a = rad(rg, rg.nodes[e.a]) if rg.nodes[e.a].degree() > 1 else 0.0
        trim_b = rad(rg, rg.nodes[e.b]) if rg.nodes[e.b].degree() > 1 else 0.0
        center = trim_polyline(e.pts, trim_a, trim_b)
        rev = list(reversed(center))
        for dir_flag, n_lanes, pts, exit_node, entry_node in (
                ('F', e.lanes_f, center, e.b, e.a),
                ('R', e.lanes_r, rev, e.a, e.b)):
            for li in range(n_lanes):
                name = f"{e.name}_{dir_flag}{li}"
                lp = offset_polyline(pts, _lane_offset_from_center(li, n_lanes, e.median, driving_side))
                r = LaneRoute(name, lp)
                lanes.append(r)
                by_name[name] = r
                h_out = _heading_at(lp, 'b')
                h_in = _heading_at(lp, 'a')
                incoming.setdefault(exit_node, []).append((name, ei, dir_flag, li, lp[-1], h_out, n_lanes))
                outgoing.setdefault(entry_node, []).append((name, ei, dir_flag, li, lp[0], h_in, n_lanes))

    junctions = []
    for ni, node in enumerate(rg.nodes):
        if node.degree() < 2:
            continue                              # dead end: lanes stay DESPAWN
        ins = incoming.get(ni, [])
        outs = outgoing.get(ni, [])
        made_any = False
        for (in_name, in_ei, _in_dir, in_li, in_p, in_h, in_lanes) in ins:
            moves = []                            # (turn, out_name, out_p, out_h)
            for (out_name, out_ei, _od, out_li, out_p, out_h, out_lanes) in outs:
                if out_ei == in_ei:
                    continue                      # no U-turn back onto the same edge
                turn = turn_of(in_h, out_h)
                # legality by lane index -- driving_side picks which lane index is the
                # "curb" (turns toward the near side) vs "median" (turns toward the far side)
                if in_lanes >= 2:
                    if driving_side == 'RIGHT':
                        if turn == 'L' and in_li != in_lanes - 1:
                            continue
                        if turn == 'R' and in_li != 0:
                            continue
                    else:
                        if turn == 'L' and in_li != 0:
                            continue
                        if turn == 'R' and in_li != in_lanes - 1:
                            continue
                # lane mapping: curb->curb toward the near side, median->median toward the far
                # side, S clamp (driving_side swaps which physical lane index is which)
                if turn == 'L':
                    want = (out_lanes - 1) if driving_side == 'RIGHT' else 0
                elif turn == 'R':
                    want = 0 if driving_side == 'RIGHT' else (out_lanes - 1)
                else:
                    want = min(in_li, out_lanes - 1)
                if out_li != want:
                    continue
                moves.append((turn, out_name, out_p, out_h))
            if not moves:
                continue
            in_route = by_name[in_name]
            in_route.end_behavior = 'CHAIN'
            weights = []
            dup = {}
            for (turn, out_name, out_p, out_h) in moves:
                k = dup.get(turn, 0)
                dup[turn] = k + 1
                cname = f"c{ni}_{in_name}_{turn}" + (str(k) if k else "")
                cpts = bezier(in_p, in_h, out_p, out_h)
                c = LaneRoute(cname, cpts, end_behavior='CHAIN',
                              next_routes=[out_name], turn=turn,
                              approach=approach_of(in_h))
                lanes.append(c)
                by_name[cname] = c
                in_route.next_routes.append(cname)
                weights.append(TURN_WEIGHTS.get(turn, 0.2))
                made_any = True
            total = sum(weights) or 1.0
            in_route.next_weights = [w / total for w in weights]
        if made_any:
            r = rad(rg, node)
            junctions.append(JunctionOut(f"n{ni}", node.x, node.y, node.z,
                                         2.0 * r, 2.0 * r))
    return lanes, junctions


# ── adapters ────────────────────────────────────────────────────────────────────────────

def from_curves(curves, eps=CONNECT_EPS, driving_side='LEFT'):
    """Hand-authored Blender road curves -> RoadGraph.

    curves: [(name, [(x, y, z), ...], props)] where props may carry
    'lanes' (per direction, default 1), 'oneway' (bool, default False),
    'class' (default 'local'), 'median' (physical divider width in m, default 0 — lane packs
    shift out by median/2 each side). Curves are SPLIT where an interior point of one lies within
    eps of another curve's endpoint (a T junction drawn as one long curve + a side street),
    then every touching endpoint clusters into a junction node. `driving_side` ('LEFT' default,
    or 'RIGHT') is stamped onto the returned RoadGraph -- see generate()'s docstring."""
    # collect split points per curve: any OTHER curve's endpoint near an interior vertex
    endpoints = []
    for name, pts, _props in curves:
        endpoints.append(pts[0])
        endpoints.append(pts[-1])

    rg = RoadGraph(driving_side=driving_side)
    for name, pts, props in curves:
        lanes = int(props.get('lanes', 1) or 1)
        oneway = bool(props.get('oneway', False))
        cls = str(props.get('class', 'local') or 'local')
        median = float(props.get('median', 0.0) or 0.0)
        # split at interior vertices that another curve's endpoint touches
        cuts = [0]
        for i in range(1, len(pts) - 1):
            p = pts[i]
            for q in endpoints:
                if q is pts[0] or q is pts[-1]:
                    continue
                if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= eps * eps:
                    cuts.append(i)
                    break
        cuts.append(len(pts) - 1)
        cuts = sorted(set(cuts))
        for si in range(len(cuts) - 1):
            seg = pts[cuts[si]:cuts[si + 1] + 1]
            if len(seg) < 2 or poly_len(seg) < MIN_LINK_LEN:
                continue
            seg_name = name if len(cuts) == 2 else f"{name}_s{si}"
            rg.add_edge(seg_name, seg, lanes_f=lanes,
                        lanes_r=0 if oneway else lanes, cls=cls, eps=eps, median=median)
    return rg


def from_town_grid(grid, cell=7.0):
    """TownGrid -> RoadGraph: maximal straight runs split at junction cells (any road cell
    with >=3 open sides or a corner), carrying the run's lanes-per-direction and class."""
    junction_cells = set()
    for (cx, cy) in grid.roads:
        opens = grid.open_sides(cx, cy)
        if len(opens) >= 3:
            junction_cells.add((cx, cy))
        elif len(opens) == 2:
            a, b = sorted(opens)
            opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
            if opp[a] != b:
                junction_cells.add((cx, cy))      # corner = a 2-way junction node

    rg = RoadGraph()

    def emit_run(cells, axis):
        # split the ordered run at junction cells (junction cell = node, shared by both sides)
        segs = []
        cur = [cells[0]]
        for c in cells[1:]:
            cur.append(c)
            if c in junction_cells:
                segs.append(cur)
                cur = [c]
        if len(cur) >= 2:
            segs.append(cur)
        for seg in segs:
            if len(seg) < 2:
                continue
            (x0, y0), (x1, y1) = seg[0], seg[-1]
            lanes = min(grid.lanes_of(c) for c in seg)
            cls = grid.class_of(seg[len(seg) // 2])
            name = f"g{axis}{x0}_{y0}_{x1}_{y1}"
            pts = [(c[0] * cell, c[1] * cell, 0.0) for c in seg]
            rg.add_edge(name, pts, lanes_f=lanes,
                        lanes_r=0 if cls == 'oneway' else lanes, cls=cls, eps=cell * 0.45)

    cols = {}
    for (cx, cy) in grid.roads:
        cols.setdefault(cx, []).append(cy)
    for cx, ys in sorted(cols.items()):
        ys = sorted(ys)
        run = [ys[0]]
        for y in ys[1:]:
            if y == run[-1] + 1:
                run.append(y)
            else:
                if len(run) >= 2:
                    emit_run([(cx, y2) for y2 in run], 'v')
                run = [y]
        if len(run) >= 2:
            emit_run([(cx, y2) for y2 in run], 'v')
    rows = {}
    for (cx, cy) in grid.roads:
        rows.setdefault(cy, []).append(cx)
    for cy, xs in sorted(rows.items()):
        xs = sorted(xs)
        run = [xs[0]]
        for x in xs[1:]:
            if x == run[-1] + 1:
                run.append(x)
            else:
                if len(run) >= 2:
                    emit_run([(x2, cy) for x2 in run], 'h')
                run = [x]
        if len(run) >= 2:
            emit_run([(x2, cy) for x2 in run], 'h')
    return rg


# ── self-test ───────────────────────────────────────────────────────────────────────────

def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _selftest():
    # 1) hand-authored curves: 2-lane main E-W road with a 1-lane side road T-ing in from
    #    the south at x=50 (endpoint touches the main's interior vertex).
    main = ("main", [(0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (100.0, 0.0, 0.0)],
            {"lanes": 2})
    side = ("side", [(50.0, -60.0, 0.0), (50.0, 0.0, 0.0)], {"lanes": 1})
    rg = from_curves([main, side])
    _assert(len(rg.edges) == 3, f"T split: expected 3 edges, got {len(rg.edges)}")
    deg3 = [n for n in rg.nodes if n.degree() == 3]
    _assert(len(deg3) == 1, f"T split: expected one degree-3 node, got {len(deg3)}")

    lanes, junctions = generate(rg)
    routes = {r.name: r for r in lanes}
    _assert(len(junctions) == 1, f"expected 1 junction marker, got {len(junctions)}")

    # movement coverage: every incoming lane at the T has >=1 connector; every outgoing
    # lane is some connector's target.
    conns = [r for r in lanes if r.turn]
    _assert(conns, "no connectors generated")
    targets = set()
    for c in conns:
        _assert(len(c.next_routes) == 1, "connector must chain to exactly one out-lane")
        targets.add(c.next_routes[0])
        out = routes[c.next_routes[0]]
        # geometry: connector endpoints coincide with in-lane end / out-lane start
        _assert(_seg_len(c.pts[-1], out.pts[0]) < 1e-6,
                f"connector {c.name} end != out-lane start ({_seg_len(c.pts[-1], out.pts[0]):.3f} m)")
        # tangent alignment at the exit
        h_c = _heading_at(c.pts, 'b')
        h_o = _heading_at(out.pts, 'a')
        dot = h_c[0] * h_o[0] + h_c[1] * h_o[1]
        _assert(dot > 0.9, f"connector {c.name} exit tangent misaligned (dot={dot:.2f})")
    # every in-lane that got connectors chains + is weighted
    for r in lanes:
        if r.turn or not r.next_routes:
            continue
        _assert(r.end_behavior == 'CHAIN', f"{r.name} has next_routes but not CHAIN")
        _assert(len(r.next_weights) == len(r.next_routes), f"{r.name} weights mismatch")
        _assert(abs(sum(r.next_weights) - 1.0) < 1e-6, f"{r.name} weights not normalized")

    # keep-left legality on the 2-LANE main approaches only (a 1-lane approach like the
    # side road may take any turn): curb lane (index 0) never turns R, median lane
    # (index 1) never turns L.
    for c in conns:
        src = [r for r in lanes if c.name in r.next_routes]
        _assert(len(src) == 1, f"connector {c.name} should have exactly 1 source")
        sname = src[0].name
        if not sname.startswith("main"):
            continue                               # 1-lane side road: L/S/R all legal
        if "_F1" in sname or "_R1" in sname:
            _assert(c.turn != 'L', f"median lane {sname} may not turn LEFT ({c.name})")
        if "_F0" in sname or "_R0" in sname:
            _assert(c.turn != 'R', f"curb lane {sname} may not turn RIGHT ({c.name})")

    # opposing lanes must sit on opposite sides: main F0 (eastbound) north of centreline?
    # keep-left, eastbound travel (+x): left = +y … offset negative*right(ty,-tx) => +y. Check.
    f0 = routes["main_s0_F0"] if "main_s0_F0" in routes else routes[[k for k in routes if k.endswith("_F0") and k.startswith("main")][0]]
    r0 = routes[f0.name.replace("_F0", "_R0")]
    _assert(f0.pts[1][1] > 0.1 and r0.pts[1][1] < -0.1,
            f"keep-left sides wrong: F0 y={f0.pts[1][1]:.2f} R0 y={r0.pts[1][1]:.2f}")

    # 1b) SAME graph, RIGHT-hand traffic: mirrors intersection_kit.py's own traffic_side='RIGHT'
    # self-test pattern -- everything above must flip sign/lane-index, nothing else changes.
    lanes_r, junctions_r = generate(rg, driving_side='RIGHT')
    routes_r = {r.name: r for r in lanes_r}
    conns_r = [r for r in lanes_r if r.turn]
    _assert(conns_r, "RIGHT: no connectors generated")
    _assert(len(junctions_r) == len(junctions), "RIGHT: junction count changed")
    f0r = routes_r[[k for k in routes_r if k.endswith("_F0") and k.startswith("main")][0]]
    r0r = routes_r[f0r.name.replace("_F0", "_R0")]
    _assert(f0r.pts[1][1] < -0.1 and r0r.pts[1][1] > 0.1,
            f"RIGHT: keep-right sides wrong: F0 y={f0r.pts[1][1]:.2f} R0 y={r0r.pts[1][1]:.2f}")
    for c in conns_r:
        src = [r for r in lanes_r if c.name in r.next_routes]
        _assert(len(src) == 1, f"RIGHT: connector {c.name} should have exactly 1 source")
        sname = src[0].name
        if not sname.startswith("main"):
            continue                               # 1-lane side road: L/S/R all legal
        if "_F1" in sname or "_R1" in sname:
            _assert(c.turn != 'R', f"RIGHT: median lane {sname} may not turn RIGHT ({c.name})")
        if "_F0" in sname or "_R0" in sname:
            _assert(c.turn != 'L', f"RIGHT: curb lane {sname} may not turn LEFT ({c.name})")
    # regression: re-running the default (no driving_side arg) must be byte-identical to the
    # original LEFT-side result above -- driving_side='RIGHT' must never mutate `rg` itself.
    lanes_again, _j_again = generate(rg)
    f0_again = {r.name: r for r in lanes_again}[f0.name]
    _assert(f0_again.pts[1][1] == f0.pts[1][1], "generate(rg) mutated by a prior RIGHT call")

    # 2) TownGrid: 2-lane EW arterial crossing 1-lane NS local at (10,10)
    import road_network as rn
    g = rn.TownGrid()
    g.road_h(10, 0, 20, cls='local', lanes=2)
    g.road_v(10, 0, 20, cls='local', lanes=1)
    rg2 = from_town_grid(g)
    _assert(len(rg2.edges) == 4, f"grid cross: expected 4 edges, got {len(rg2.edges)}")
    cross_nodes = [n for n in rg2.nodes if n.degree() == 4]
    _assert(len(cross_nodes) == 1, f"grid cross: expected one degree-4 node")
    lanes2, junctions2 = generate(rg2)
    conns2 = [r for r in lanes2 if r.turn]
    # 2-lane arms: curb L+S, median R+S => 2+2 movements per 2-lane approach where arms
    # exist; 1-lane arms: L/S/R = 3. Two 2-lane approaches (E/W) x4 + two 1-lane (N/S) x3.
    _assert(len(conns2) == 4 + 4 + 3 + 3, f"grid cross: expected 14 connectors, got {len(conns2)}")
    # every outgoing lane at the cross is reachable
    out_names = set()
    for c in conns2:
        out_names.add(c.next_routes[0])
    reachable_prefixes = set(n.rsplit('_', 1)[0] for n in out_names)
    _assert(len(out_names) >= 6, f"grid cross: outgoing lanes reachable {len(out_names)} < 6")
    # junction footprint spans the widest carriageway (2+2 lanes * 3.5 = 14 + margins)
    j = junctions2[0]
    _assert(j.size_x >= 14.0, f"junction box too small: {j.size_x:.1f}")

    # every connector carries a compass approach (Phase 2 arbiter key)
    for c in conns2:
        _assert(c.approach in ('N', 'E', 'S', 'W'), f"{c.name} missing approach")

    # 3) median: a 1-lane-per-direction road with a 4 m physical divider — each direction's
    #    lane shifts out by median/2, leaving the |y| < 2 m strip clear for the divider.
    med = ("med", [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], {"lanes": 1, "median": 4.0})
    rg3 = from_curves([med])
    lanes3, _j3 = generate(rg3)
    routes3 = {r.name: r for r in lanes3}
    mf0, mr0 = routes3["med_F0"], routes3["med_R0"]
    _assert(abs(mf0.pts[0][1] - 3.75) < 1e-6 and abs(mr0.pts[0][1] + 3.75) < 1e-6,
            f"median offsets wrong: F0 y={mf0.pts[0][1]:.2f} R0 y={mr0.pts[0][1]:.2f} (want ±3.75)")
    _assert(min(abs(mf0.pts[0][1]), abs(mr0.pts[0][1])) > 2.0,
            "median strip not clear — a lane sits inside |y| < median/2")

    # simplify: a dense 700 m straight collapses to max_gap-spaced support points,
    # endpoints intact; a bend point survives.
    dense = [(x * 7.0, 0.0, 0.0) for x in range(101)]
    simp = simplify_polyline(dense, max_gap=30.0)
    _assert(simp[0] == dense[0] and simp[-1] == dense[-1], "simplify dropped an endpoint")
    _assert(len(simp) <= 27, f"simplify kept too many points ({len(simp)})")
    bent = [(0, 0, 0), (10, 0, 0), (20, 5, 0), (30, 5, 0)]
    _assert((20, 5, 0) in simplify_polyline(bent), "simplify dropped a bend point")

    print("road_graph selftest OK —",
          f"T: {len(rg.edges)} edges/{len(conns)} connectors;",
          f"driving_side='RIGHT' mirrors offsets + turn legality ({len(conns_r)} connectors);",
          f"grid cross: {len(lanes2)} routes/{len(conns2)} connectors,",
          f"box {j.size_x:.1f} m;",
          f"median: F0/R0 at ±{abs(mf0.pts[0][1]):.2f} m")


if __name__ == "__main__":
    _selftest()
