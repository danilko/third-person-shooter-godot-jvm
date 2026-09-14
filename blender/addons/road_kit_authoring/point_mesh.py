"""point_mesh.py -- the road sweep in PURE PYTHON (PLAN.md 3.1 B10.7, a measured SPIKE).

The question being measured: is Blender still needed to turn a solved network into meshes? Everything
`point_build` hands Geometry Nodes is already Python's -- every carrier polyline and its per-sample
attributes (`point_solve`), every edge run (`point_edges`), every pad and gore triangle, every marking
chain. What GN adds is the SWEEP: offset a curve, lay a flat or extruded section across it, instance a box
at spacing. This module does exactly that, from the same inputs and the same layer table (`point_build`'s
`surface_spec` / `edge_spec` / `mark_spec`, restated as data here because those tables build node groups),
so the result can be compared with the baked pieces layer by layer (`tools/roadkit_mesh_parity.py`).

Output: `{object_name: {material_name: [(a, b, c), ...]}}` in the KIT frame, object names exactly as
`point_build` names them (`<run>__surface`, `<run>__edges_<side>_<n>`, `<run>__marks_w`, `JCT_*__pad`,
`JCT_*__edges_c<n>`, `GORE_*__gore`), materials by the default style (no profile assets, no style slots --
the spike's stated scope).

TWO THINGS IT DOES DIFFERENTLY, ON PURPOSE, because the spike found them wrong in the Blender build:
an extruded layer (deck, kerb, barrier) is a CLOSED prism -- top, a down-facing bottom and side walls on
the region's boundary. `GN_PointDeck` uses `Extrude Mesh` with `Individual` at its default (on), which
MOVES each face down and walls it separately: a kerb swept at its top height and extruded down ends with
its only horizontal face at ROAD level (a hollow kerb, measured 10.46 vs walls to 10.61 on DebugRoads), and
a deck's only horizontal face is its soffit still facing UP, so a bridge seen from below has no underside.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib"))

try:
    from . import point_model as pm, point_solve as ps, point_edges as ped
except ImportError:
    import point_model as pm                                                 # noqa: E402
    import point_solve as ps                                                 # noqa: E402
    import point_edges as ped                                                # noqa: E402

#: Default-style material per layer, as `kit_common.MATS` names them (what the baked pieces carry).
MAT = {"asphalt": "M_Asphalt", "concrete": "M_Concrete", "footway": "M_ConcreteTile", "median": "M_Median",
       "barrier": "M_Barrier", "line_w": "M_LineW", "line_y": "M_LineY"}

#: `point_build.surface_spec` as data: (layer, kind, material, offset_attr, z, z_attr, width_attr, thickness_attr).
SURFACE = (("Carriageway", "band", "asphalt", "rka_shift", 0.0, "", "rka_halfw", ""),
           ("Median", "band", "median", "", ps.PAINT_Z_BIAS, "rka_med_z", "rka_med_h", ""),
           ("Deck", "deck", "concrete", "rka_deck_c", ps.DECK_Z_BIAS, "", "rka_deck_w", "rka_deck_h"))
#: `point_build.edge_spec`.
EDGE = (("Curb", "deck", "concrete", "rka_curb_ol", 0.0, "rka_curb_hl", "rka_curb_tl", "rka_curb_hl"),
        ("Sidewalk", "band", "footway", "rka_walk_cl", 0.0, "rka_walk_zl", "rka_walk_hl", ""),
        ("Barrier", "deck", "barrier", "rka_wall_c", 0.0, "rka_wall_z", "rka_wall_hw", "rka_wall_h"))
PILLAR_MIN_HEIGHT = 0.5


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def poly_tangents(pts):
    """A poly curve's tangents as Blender evaluates them: the normalised sum of the two adjoining segment
    directions, one segment's direction at an end."""
    n = len(pts)
    out = []
    for i in range(n):
        d = (0.0, 0.0, 0.0)
        if i > 0:
            a = _norm(_sub(pts[i], pts[i - 1]))
            d = (d[0] + a[0], d[1] + a[1], d[2] + a[2])
        if i < n - 1:
            b = _norm(_sub(pts[i + 1], pts[i]))
            d = (d[0] + b[0], d[1] + b[1], d[2] + b[2])
        out.append(_norm(d))
    return out


def _lateral(t):
    """`GN_PointSpine`'s `rka_lat`: normalize(cross(+Z, tangent)) -- horizontal, to the left of travel."""
    return _norm((-t[1], t[0], 0.0))


def _offset_curve(pts, lats, values, offset_attr, z, z_attr):
    """`wrap_layer`'s offset stage: along the carrier's stored lateral, and straight up."""
    out = []
    for p, lat, v in zip(pts, lats, values):
        off = float(v.get(offset_attr, 0.0)) if offset_attr else 0.0
        dz = z + (float(v.get(z_attr, 0.0)) if z_attr else 0.0)
        out.append((p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + lat[2] * off + dz))
    return out


def _band_rails(curve, widths):
    """The two rails of a flat band of per-point half-width across `curve` (Z-up frame: horizontal)."""
    tans = poly_tangents(curve)
    left, right = [], []
    for q, t, w in zip(curve, tans, widths):
        b = _lateral(t)
        left.append((q[0] + b[0] * w, q[1] + b[1] * w, q[2]))
        right.append((q[0] - b[0] * w, q[1] - b[1] * w, q[2]))
    return left, right


def _strip(left, right, flip=False):
    tris = []
    for i in range(len(left) - 1):
        a, b, c, d = left[i], right[i], right[i + 1], left[i + 1]
        tris += [(a, c, b), (a, d, c)] if not flip else [(a, b, c), (a, c, d)]
    return tris


def _up(tri):
    a, b, c = tri
    u, v = _sub(b, a), _sub(c, a)
    return u[0] * v[1] - u[1] * v[0]


def _face_up(tris, up=True):
    """Wind every triangle so its normal faces up (or down)."""
    out = []
    for t in tris:
        s = _up(t)
        out.append(t if (s >= 0.0) == up else (t[0], t[2], t[1]))
    return out


def sweep(pts, values, kind, offset_attr, z, z_attr, width_attr, thickness_attr, lats=None):
    """One layer over one carrier. A `band` is a flat strip; a `deck` is that strip extruded DOWN by the
    per-point thickness into a closed prism (top up, bottom down, walls on the boundary)."""
    if not any(abs(float(v.get(width_attr, 0.0))) > 1e-6 for v in values):
        return []
    if thickness_attr and not any(abs(float(v.get(thickness_attr, 0.0))) > 1e-6 for v in values):
        return []
    lats = lats or [_lateral(t) for t in poly_tangents(pts)]
    curve = _offset_curve(pts, lats, values, offset_attr, z, z_attr)
    left, right = _band_rails(curve, [float(v.get(width_attr, 0.0)) for v in values])
    top = _face_up(_strip(left, right))
    if kind == "band":
        return top
    th = [float(v.get(thickness_attr, 0.0)) for v in values]
    lb = [(p[0], p[1], p[2] - t) for p, t in zip(left, th)]
    rb = [(p[0], p[1], p[2] - t) for p, t in zip(right, th)]
    bottom = _face_up(_strip(lb, rb), up=False)
    # Walls face OUT of the prism: away from the curve at each quad, and back / forward past the two caps.
    tans = poly_tangents(curve)
    walls = []
    for rail, base, sign in ((left, lb, 1.0), (right, rb, -1.0)):
        for i in range(len(rail) - 1):
            b = _lateral(tans[i])
            out = (b[0] * sign, b[1] * sign, 0.0)
            walls += [_orient((rail[i], base[i], base[i + 1]), out), _orient((rail[i], base[i + 1], rail[i + 1]), out)]
    t0, t1 = tans[0], tans[-1]
    walls += [_orient((left[0], right[0], rb[0]), (-t0[0], -t0[1], -t0[2])), _orient((left[0], rb[0], lb[0]), (-t0[0], -t0[1], -t0[2])),
              _orient((left[-1], rb[-1], right[-1]), t1), _orient((left[-1], lb[-1], rb[-1]), t1)]
    return top + bottom + walls


def _orient(tri, out):
    """`tri` wound so its normal points along `out`."""
    a, b, c = tri
    u, v = _sub(b, a), _sub(c, a)
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return tri if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0.0 else (a, c, b)


def _box(c, w, h):
    """A w x w x h box whose TOP centre is `c`."""
    x0, x1, y0, y1 = c[0] - w / 2, c[0] + w / 2, c[1] - w / 2, c[1] + w / 2
    z1, z0 = c[2], c[2] - h
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [(v[a], v[b], v[cc]) for a, b, cc in f]


def pillars(pts, values, lats):
    """`GN_PointPillars`: resample the deck-centre curve every `rka_sp_pillar` metres and stand a
    `rka_pillar_w` box of height `rka_pillar_h` under the soffit wherever the solve said PIER."""
    curve = _offset_curve(pts, lats, values, "rka_deck_c", 0.0, "")
    acc = [0.0]
    for i in range(len(curve) - 1):
        acc.append(acc[-1] + math.dist(curve[i], curve[i + 1]))
    total = acc[-1]
    spacing = max(0.05, float(values[0].get("rka_sp_pillar", 30.0)))
    count = max(1, int(total / spacing))
    out = []
    j = 0
    for k in range(count + 1):
        s = total * k / count
        while j < len(acc) - 2 and acc[j + 1] < s:
            j += 1
        seg = acc[j + 1] - acc[j]
        u = (s - acc[j]) / seg if seg > 1e-9 else 0.0
        va, vb = values[j], values[j + 1]
        lerp = lambda key: float(va.get(key, 0.0)) + (float(vb.get(key, 0.0)) - float(va.get(key, 0.0))) * u
        if lerp("rka_pillar_param") <= 0.5 or lerp("rka_pillar_h") < PILLAR_MIN_HEIGHT:
            continue
        p = tuple(curve[j][i] + (curve[j + 1][i] - curve[j][i]) * u for i in range(3))
        top = (p[0], p[1], p[2] - lerp("rka_deck_h"))
        out += _box(top, lerp("rka_pillar_w") or 1.4, lerp("rka_pillar_h"))
    return out


def _add(objs, name, mat, tris):
    if tris:
        objs.setdefault(name, {}).setdefault(MAT[mat], []).extend(tris)


def build(net, ground=None):
    """Every object `point_build.build_network` emits (default style), as triangles. Same solve."""
    solves, jsolves, gsolves, bands = ped.solve_all(net, ground)
    objs = {}
    by_road = {}
    for s in solves:
        by_road.setdefault(s.road.name, []).append(s)
    for road_name, runs in by_road.items():
        for i, s in enumerate(runs):
            name = road_name if len(runs) == 1 else "%s_%d" % (road_name, i)
            pts, values = ps.carrier_points(s)
            lats = [_lateral(t) for t in poly_tangents(pts)]
            for layer, kind, mat, oa, z, za, wa, ta in SURFACE:
                _add(objs, name + "__surface", mat, sweep(pts, values, kind, oa, z, za, wa, ta, lats))
            if any(float(v.get("rka_pillar_param", 0.0)) > 0.0 for v in values):
                _add(objs, name + "__surface", "concrete", pillars(pts, values, lats))
            for sfx, epts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
                _edge_run(objs, "%s__edges_%s" % (name, sfx), epts, walk, kerb, wall, sgn)
            for yellow in (False, True):
                for r in (r for r in ps.solve_marks(s) if r.yellow is yellow):
                    vals = [{"rka_mark_w": ps.MARK_WIDTH / 2.0}] * len(r.points)
                    _add(objs, "%s__marks_%s" % (name, "y" if yellow else "w"), "line_y" if yellow else "line_w",
                         sweep(list(r.points), vals, "band", "", ps.PAINT_Z_BIAS, "", "rka_mark_w", ""))
    for j in jsolves:
        name = "JCT_" + j.uids[0][:8]
        _add(objs, name + "__pad", "asphalt", _face_up([t for t in j.fan if abs(_up(t)) > 1e-9]))
        for sfx, epts, walk, kerb, wall, sgn in ped.junction_edge_runs(j):
            _edge_run(objs, "%s__edges_%s" % (name, sfx), epts, walk, kerb, wall, sgn)
    for g in gsolves:
        name = "GORE_" + g.ramp_uid[:8]
        _add(objs, name + "__gore", "asphalt", _face_up([t for t in g.tris if abs(_up(t)) >= 1e-3]))
        for sfx, epts, walk, kerb, wall, sgn in ped.gore_edge_runs(g):
            _edge_run(objs, "%s__edges_%s" % (name, sfx), epts, walk, kerb, wall, sgn)
    return objs


def _edge_run(objs, name, pts, walk, kerb, wall, sgn):
    """`point_build.build_edge_run` without Blender: the same per-vertex values (`edge_run_values`, restated
    here because `point_build` imports bpy), the same three layers."""
    half_t = ps.BARRIER_THICKNESS * 0.5
    values = []
    for k in range(len(kerb)):
        h, w, wl = float(kerb[k]), float(walk[k]), float(wall[k])
        values.append({"rka_curb_ol": 0.0, "rka_curb_hl": h, "rka_curb_tl": h * ps.KERB_THICKNESS,
                       "rka_walk_cl": sgn * w, "rka_walk_hl": w, "rka_walk_zl": h, "rka_wall_h": wl,
                       "rka_wall_hw": half_t if wl > 0.0 else 0.0, "rka_wall_c": sgn * (2.0 * w + half_t),
                       "rka_wall_z": h + wl})
    pts = [tuple(p) for p in pts]
    for layer, kind, mat, oa, z, za, wa, ta in EDGE:
        _add(objs, name, mat, sweep(pts, values, kind, oa, z, za, wa, ta))


def self_test():
    try:
        from . import point_validate as pv
    except ImportError:
        import point_validate as pv                                          # noqa: E402
    net, mp, cp, rr = pv.build_testbed()
    objs = build(net)
    surf = [n for n in objs if n.endswith("__surface")]
    assert surf and all("M_Asphalt" in objs[n] for n in surf), surf
    print("OK: every run sweeps its carriageway (%d objects, %d surfaces)" % (len(objs), len(surf)))
    # A closed deck prism: as much area faces down as faces up.
    deck = sweep([(0.0, 0.0, 5.0), (10.0, 0.0, 5.0), (20.0, 0.0, 5.0)], [{"w": 3.0, "t": 1.0}] * 3, "deck",
                 "", 0.0, "", "w", "t")
    up = sum(_up(t) for t in deck if _up(t) > 0) / 2.0
    down = -sum(_up(t) for t in deck if _up(t) < 0) / 2.0
    assert abs(up - 120.0) < 1e-6 and abs(down - 120.0) < 1e-6, (up, down)
    assert min(p[2] for t in deck for p in t) == 4.0 and max(p[2] for t in deck for p in t) == 5.0
    print("OK: an extruded layer is a CLOSED prism (top 120 m2 up, bottom 120 m2 down)")
    return 2


if __name__ == "__main__":
    print("point_mesh.py: %d checks PASS" % self_test())
