"""point_mesh.py -- THE ROAD SWEEP, in pure Python: the road build has no Blender (PLAN.md 3.1 B10.7 spike, B11).

Everything `point_build` handed Geometry Nodes was already Python's -- every carrier polyline and its per-sample
attributes (`point_solve`), every edge run (`point_edges`), every pad and gore triangle, every marking chain. What
GN added was the SWEEP: offset a curve, lay a flat or extruded section across it, sweep an artist's profile, stand
a box at spacing. This module does exactly that, from the same inputs and the same layer table (`point_build`'s
`surface_spec` / `edge_spec` / `mark_spec`, restated as data), and B11 measured it against the Blender build on
every sample network, styled included, before the Blender road build was retired (CLAUDE.md "B11").

Output: `{object_name: {material_name: [(a, b, c), ...]}}` in the KIT frame, object names exactly as `point_build`
named them (`<run>__surface`, `<run>__edges_<side>_<n>`, `<run>__marks_w`, `JCT_*__pad`, `JCT_*__edges_c<n>`,
`GORE_*__gore`, and the `<base>-road|walk[-noped]-colonly` proxies), materials by name from each road's STYLE
(`point_kit`, over `road_kit.json`), profile assets swept at their own size (`sweep_profile`). `point_gltf` writes it.

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
    from . import point_model as pm, point_solve as ps, point_edges as ped, point_kit as pk
    from . import point_furniture as pfu
except ImportError:
    import point_furniture as pfu                                            # noqa: E402
    import point_model as pm                                                 # noqa: E402
    import point_solve as ps                                                 # noqa: E402
    import point_edges as ped                                                # noqa: E402
    import point_kit as pk                                                   # noqa: E402

#: Default-style material per layer, as `kit_common.MATS` names them (what the baked pieces carry).
MAT = pk.DEFAULT_MATERIAL

#: `point_build.surface_spec` as data: (layer, kind, style slot, offset_attr, z, z_attr, width_attr, thickness_attr).
SURFACE = (("Carriageway", "band", "surface", "rka_shift", 0.0, "", "rka_halfw", ""),
           ("Median", "band", "median", "", ps.PAINT_Z_BIAS, "rka_med_z", "rka_med_h", ""),
           ("Deck", "deck", "deck", "rka_deck_c", ps.DECK_Z_BIAS, "", "rka_deck_w", "rka_deck_h"))
#: `point_build.edge_spec`.
EDGE = (("Curb", "deck", "kerb", "rka_curb_ol", 0.0, "rka_curb_hl", "rka_curb_tl", "rka_curb_hl"),
        ("Sidewalk", "band", "footway", "rka_walk_cl", 0.0, "rka_walk_zl", "rka_walk_hl", ""),
        ("Barrier", "deck", "barrier", "rka_wall_c", 0.0, "rka_wall_z", "rka_wall_hw", "rka_wall_h"))
PILLAR_MIN_HEIGHT = 0.5

#: `point_build.ASSET_REQUIRE` / `ASSET_Z_ATTR`: what must be non-zero on a carrier for a slot's PROFILE ASSET to
#: build, and the line its section's origin stands on (a kerb and a barrier are anchored by their FOOT).
ASSET_REQUIRE = {"kerb": "rka_curb_hl", "footway": "rka_walk_hl", "barrier": "rka_wall_h", "median": "rka_med_h"}
ASSET_Z_ATTR = {"kerb": "", "footway": "rka_walk_zl", "barrier": "rka_wall_foot", "median": "rka_med_z", "surface": ""}

#: `point_build.SUFFIX_COL` / `NO_PED_SUFFIX` and the two proxy kinds.
SUFFIX_COL = "-colonly"
NO_PED_SUFFIX = "-noped"
COL_ROAD, COL_WALK = "road", "walk"
#: A vehicle-only wall along a barrier (`_edge_run`); `WorldBaker.applyCarWalls` puts it on `CollisionLayers.CAR_WALL`.
COL_CARWALL = "carwall"
CAR_WALL_HEIGHT = 3.0
#: A collision proxy's triangles are filed under this material key: a proxy has no look.
NO_MATERIAL = ""


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
    """Two triangles per quad, split along its SHORTER diagonal: on a warped quad (a taper, a bank change) the long
    diagonal folds the surface up to a metre off the rails' own line, and it is the split Blender makes too."""
    tris = []
    for i in range(len(left) - 1):
        a, b, c, d = left[i], right[i], right[i + 1], left[i + 1]
        if math.dist(a, c) <= math.dist(b, d):
            tris += [(a, c, b), (a, d, c)] if not flip else [(a, b, c), (a, c, d)]
        else:
            tris += [(a, d, b), (b, d, c)] if not flip else [(a, b, d), (b, c, d)]
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


#: A `WALL` median's barrier: this wide (clamped to the island), the road's `barrier_height` tall, on the island's top.
MEDIAN_WALL_HALF = 0.3


def median_wall(road, pts, values, lats):
    """The barrier a `WALL` median stands (`point_solve`: "RAISED, and a barrier stands on it"). The solve had always
    said so and nothing built it: an expressway's divide was a 0.16 m island a car drove straight over into the other
    carriageway (3.13). A solid prism on the island's centre, `point_solve.MEDIAN_WALL_HEIGHT` tall, built as its own
    `-noped-colonly` proxy: a car meets a continuous wall, and what it SEES is the kit's median panel, tiled along it
    by `point_furniture._median_walls` (a fence panel's posts and rails are no collider to scrape at speed)."""
    bh = ps.MEDIAN_WALL_HEIGHT
    if getattr(road, "median_style", None) != pm.MED_WALL:
        return []
    mv = []
    for v in values:
        mh = float(v.get("rka_med_h", 0.0))
        on = mh > 1e-6
        mv.append({"rka_mw_z": float(v.get("rka_med_z", 0.0)) + bh if on else 0.0,
                   "rka_mw_hw": min(MEDIAN_WALL_HALF, mh) if on else 0.0, "rka_mw_h": bh if on else 0.0})
    return sweep(pts, mv, "deck", "", 0.0, "rka_mw_z", "rka_mw_hw", "rka_mw_h", lats)


#: A rock shed's parts, past the deck outline (PLAN.md 3.15): the columns stand this far outboard on the open side, the
#: wall this far on the closed side, and the roof reaches this far past the wall -- over the stamp's flat verge
#: (`road_kit_stamp.VERGE`, 6 m past the paved edge) to the cut face, so no daylight shows between roof and rock.
SHED_EDGE = 0.8
SHED_BACK = 5.0
SHED_COL = 0.8
SHED_WALL_HALF = 0.3
#: Lamps under the soffit: a warm panel every this many metres, in two rows over the lanes.
SHED_LAMP_SPACING = 10.0
SHED_LAMP_MATERIAL = "M_TunnelLamp"


def _obox(c, fwd, half_len, half_wid, h):
    """A box whose TOP centre is `c`, `half_len` along the horizontal `fwd`, `half_wid` across, `h` deep."""
    lat = (-fwd[1], fwd[0], 0.0)
    corners = []
    for z in (c[2] - h, c[2]):
        for sl, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corners.append((c[0] + fwd[0] * half_len * sl + lat[0] * half_wid * sw,
                            c[1] + fwd[1] * half_len * sl + lat[1] * half_wid * sw, z))
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
         (3, 0, 4), (3, 4, 7)]
    ctr = (c[0], c[1], c[2] - h / 2)
    out = []
    for a, b, cc in f:
        t = (corners[a], corners[b], corners[cc])
        m = tuple((t[0][k] + t[1][k] + t[2][k]) / 3 for k in range(3))
        out.append(_orient(t, _sub(m, ctr)))
    return out


def _spans(values, key):
    """`[(i0, i1, code)]`: maximal runs of samples whose `key` is one non-zero code, each carried on to the next sample
    (a station's flag holds up to the next station, whose own sample is the first one without it)."""
    out, i, n = [], 0, len(values)
    while i < n:
        code = int(round(float(values[i].get(key, 0.0))))
        if code == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and int(round(float(values[j + 1].get(key, 0.0)))) == code:
            j += 1
        out.append((i, min(j + 1, n - 1), code))
        i = j + 1
    return out


def sheds(pts, values, lats):
    """The rock sheds over one carrier (`rka_shed`, PLAN.md 3.15): `{"concrete": [tri], "lamps": [tri]}`, the concrete
    also being the shed's collider. Per span: a ROOF slab from past the open-side columns to `SHED_BACK` past the
    closed-side wall, its soffit `point_solve.SHED_CLEAR` over the road; a WALL along the closed side from the ground
    to the soffit; a COLUMN every `SHED_COL_SPACING` on the open side; and two rows of lamp panels under the soffit."""
    out = {"concrete": [], "lamps": []}
    clear, roof = ps.SHED_CLEAR, ps.SHED_ROOF
    for i0, i1, code in _spans(values, "rka_shed"):
        if i1 <= i0:
            continue
        sp, sv, sl = pts[i0:i1 + 1], values[i0:i1 + 1], lats[i0:i1 + 1]
        open_sign = 1.0 if code == 1 else -1.0          # +1: the columns on the LEFT (+lateral)
        rv, wv, cols = [], [], []
        for v in sv:
            dc, dw = float(v.get("rka_deck_c", 0.0)), float(v.get("rka_deck_w", 0.0))
            open_e = dc + open_sign * (dw + SHED_EDGE)
            closed_e = dc - open_sign * (dw + SHED_EDGE)
            far_open = open_e + open_sign * SHED_COL / 2
            far_closed = closed_e - open_sign * SHED_BACK
            rv.append({"c": (far_open + far_closed) / 2, "hw": abs(far_open - far_closed) / 2, "z": clear + roof,
                       "t": roof})
            wv.append({"c": closed_e, "hw": SHED_WALL_HALF, "z": clear, "t": clear + 0.5})
            cols.append(open_e)
        out["concrete"] += sweep(sp, rv, "deck", "c", 0.0, "z", "hw", "t", sl)
        out["concrete"] += sweep(sp, wv, "deck", "c", 0.0, "z", "hw", "t", sl)
        # the columns and the lamps, walked along the carrier by arc length
        acc = [0.0]
        for k in range(len(sp) - 1):
            acc.append(acc[-1] + math.dist(sp[k][:2], sp[k + 1][:2]))
        total = acc[-1]

        def at(s):
            k = 0
            while k < len(acc) - 2 and acc[k + 1] < s:
                k += 1
            seg = acc[k + 1] - acc[k]
            u = (s - acc[k]) / seg if seg > 1e-9 else 0.0
            p = tuple(sp[k][q] + (sp[k + 1][q] - sp[k][q]) * u for q in range(3))
            fwd = _norm((sp[k + 1][0] - sp[k][0], sp[k + 1][1] - sp[k][1], 0.0))
            lat = (-fwd[1], fwd[0], 0.0)
            return p, fwd, lat, k, u
        n = max(1, int(round(total / ps.SHED_COL_SPACING)))
        for m in range(n + 1):
            p, fwd, lat, k, u = at(total * m / n)
            off = cols[k] + (cols[k + 1] - cols[k]) * u
            top = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + clear)
            out["concrete"] += _obox(top, fwd, SHED_COL / 2, SHED_COL / 2, clear + 0.5)
        n = int(total / SHED_LAMP_SPACING)
        for m in range(n):
            p, fwd, lat, k, u = at((m + 0.5) * total / n)
            v = sv[k]
            shift, half = float(v.get("rka_shift", 0.0)), float(v.get("rka_halfw", 0.0))
            for off in (shift + half * 0.5, shift - half * 0.5):
                top = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + clear)
                out["lamps"] += _obox(top, fwd, 0.6, 0.18, 0.12)
    return out


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


def pier_placements(pts, values, lats):
    """`GN_PointPillars`' placement: resample the deck-centre curve every `rka_sp_pillar` metres and keep every
    sample the solve said PIER. `[(top, height, box width, forward, deck half-width)]`, `top` the soffit point, the
    column running `height` straight down from it to the ground, `forward` the horizontal travel direction there."""
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
        fwd = _norm((curve[j + 1][0] - curve[j][0], curve[j + 1][1] - curve[j][1], 0.0))
        out.append(((p[0], p[1], p[2] - lerp("rka_deck_h")), lerp("rka_pillar_h"), lerp("rka_pillar_w") or 1.4,
                    fwd, lerp("rka_deck_w")))
    return out


#: A pier whose shaft would be shorter than this is squashed WHOLE (cap included) rather than given a negative shaft.
PIER_MIN_SHAFT = 0.3


def pier_extent(pier):
    """`(lowest z, half-width across the road)` of a pier asset, in its own frame."""
    zs, xs = [], []
    for ts in pier.get("tris", {}).values():
        for t in ts:
            zs += [t[2], t[5], t[8]]
            xs += [abs(t[0]), abs(t[3]), abs(t[6])]
    return (min(zs) if zs else 0.0), (max(xs) if xs else 0.0)


FOOT_REACH = 1.5
FOOT_OFFSETS = ((0.0, 0.0), (FOOT_REACH, 0.0), (-FOOT_REACH, 0.0), (0.0, FOOT_REACH), (0.0, -FOOT_REACH))


def place_pier(pier, top, height, fwd, zb=None, ground=None):
    """One pier asset stood at `top` (the soffit), facing `fwd`, its lowest point `height` below: every vertex above
    `stretch_z` rigid, every one below stretched linearly so the lowest lands on the ground. `{material: [tri]}`.

    With `ground` (`ground(x, y)` -> z or None, the solve's own sampler) each shaft vertex stretches to the ground
    under ITS OWN position, not the centreline's: a portal's side columns stand 5.5 m off the road's line, and over a
    sloping seabed one stretched to the centreline's ground stopped 5 m short (measured, `probe_road_ground`)."""
    if zb is None:
        zb = pier_extent(pier)[0]
    sz = min(0.0, float(pier.get("stretch_z", 0.0)))
    right = (fwd[1], -fwd[0], 0.0)
    if zb < sz and height + sz >= PIER_MIN_SHAFT:
        def zmap(z, wx, wy):
            if z >= sz:
                return z
            foot = -height
            if ground is not None:
                # the LOWEST ground within FOOT_REACH of the vertex: a column over a vertical quay edge (0.6 m land
                # to the -24 m seabed inside one 2 m cell) otherwise left its sea-side bottom vertices 9 m short of
                # the seabed (probe_road_ground, the Wangan at the park quay). Its land side is then buried in the
                # quay, which is how a pier is founded.
                gs = [ground(wx + dx, wy + dy) for dx, dy in FOOT_OFFSETS]
                gs = [v for v in gs if v is not None]
                if gs:
                    foot = min(min(gs) - top[2], sz - PIER_MIN_SHAFT)
            return sz + (z - sz) * (foot - sz) / (zb - sz)
    else:
        k = height / -zb if zb < 0.0 else 1.0
        zmap = lambda z, wx, wy: z * k
    out = {}
    for mat, ts in pier.get("tris", {}).items():
        dst = out.setdefault(mat, [])
        for t in ts:
            tri = []
            for i in (0, 3, 6):
                x, y, z = t[i], t[i + 1], t[i + 2]
                wx, wy = top[0] + right[0] * x + fwd[0] * y, top[1] + right[1] * x + fwd[1] * y
                tri.append((wx, wy, top[2] + zmap(z, wx, wy)))
            dst.append(tuple(tri))
    return out


#: A column never stands on another road (PLAN.md 3.13): it keeps this far outside that road's paved edge, wherever that
#: road runs more than `PIER_ROAD_DZ` below the deck. Decided per COLUMN by the build, which knows every paved band --
#: switching columns off per station span (`island_roadgen.clear_piers`, retired) could only skip a whole span, and a
#: taper span cannot be split, so C1 flew 120 m and a loop ramp 250 m over the city with no column at all.
PIER_ROAD_CLEAR = 3.0
PIER_ROAD_DZ = 4.0


def pier_on_road(bands, own, top, fwd, half):
    """Would a column at `top` (the soffit), `half` wide across `fwd`, stand on or beside another road's paved band
    that runs more than `PIER_ROAD_DZ` below it? `own` names the bands that do not count (this road's)."""
    rx, ry = fwd[1], -fwd[0]
    reach = half + PIER_ROAD_CLEAR
    n = max(1, int(math.ceil(2.0 * half / 2.0)))
    probes = [(top[0] + rx * (-half + 2.0 * half * k / n), top[1] + ry * (-half + 2.0 * half * k / n)) for k in range(n + 1)]
    for b in bands:
        if b.owner in own or not b.bbox_hit(top[0], top[1], reach):
            continue
        for x, y in probes:
            if ped._signed_depth(b.poly, x, y) > -PIER_ROAD_CLEAR and b.surface_z(x, y) < top[2] - PIER_ROAD_DZ:
                return True
    return False


def pillars(pts, values, lats, pier=None, ground=None, blocked=None):
    """`GN_PointPillars`: a column at every pier placement -- the road's PIER ASSET when it names one, else a
    `rka_pillar_w` box. `({material or None: [tri]}, worst overhang, columns dropped)`: the box is filed under None (the
    caller's deck material), and `worst overhang` is how far the asset reaches past the deck edge (metres, 0 when it
    does not). `blocked(top, fwd, half)` -> True drops a column (one that would stand on another road)."""
    out, over, dropped = {}, 0.0, 0
    zb, half = pier_extent(pier) if pier is not None else (0.0, 0.0)
    for top, h, w, fwd, deck_half in pier_placements(pts, values, lats):
        if blocked is not None and blocked(top, fwd, half if pier is not None else w / 2.0):
            dropped += 1
            continue
        if pier is None:
            out.setdefault(None, []).extend(_box(top, w, h))
            continue
        for mat, ts in place_pier(pier, top, h, fwd, zb, ground).items():
            out.setdefault(mat, []).extend(ts)
        over = max(over, half - deck_half)
    return out, over, dropped


def _add(objs, name, mat, tris):
    """File `tris` under object `name`, material NAME `mat`."""
    if tris:
        objs.setdefault(name, {}).setdefault(mat, []).extend(tris)


def sweep_profile(pts, values, profile, flip, offset_attr, z, z_attr, require_attr, lats=None):
    """`GN_PointProfile` over one carrier: the artist's section swept at its OWN size, not scaled by a design width.

    The section is drawn in its XY plane, +X outward and +Y up, origin at the line the road hands it. Along the
    offset curve (the same offset stage as a parametric layer: along the carrier's stored lateral, and straight up)
    the section's +X is the curve's LEFT, `cross(N, T)`, and its +Y is the curve's Z-up normal `N` (perpendicular to
    the tangent -- `Set Curve Normal` 'Z Up' then `Curve to Mesh`, with `_PROFILE_FIX`'s half turn). `flip` mirrors
    the section for the right-hand flank. Open sections sweep open (no caps, `Fill Caps` off). Each face is wound
    so its normal leaves the section on the left of the direction the points were drawn -- outward for the kit's
    sections, which are all drawn around their solid clockwise."""
    if require_attr and not any(abs(float(v.get(require_attr, 0.0))) > 1e-6 for v in values):
        return []
    lats = lats or [_lateral(t) for t in poly_tangents(pts)]
    curve = _offset_curve(pts, lats, values, offset_attr, z, z_attr)
    tans = poly_tangents(curve)
    frames = []
    for t in tans:
        up = _norm((-t[2] * t[0], -t[2] * t[1], 1.0 - t[2] * t[2]))
        left = _norm((up[1] * t[2] - up[2] * t[1], up[2] * t[0] - up[0] * t[2], up[0] * t[1] - up[1] * t[0]))
        frames.append((left, up))
    sgn = -1.0 if flip else 1.0
    out = []
    for sp in profile.get("splines", ()):
        sec = [(float(x), float(y)) for x, y in sp.get("points", ())]
        if sp.get("cyclic") and len(sec) > 2:
            sec = sec + sec[:1]
        rings = [[(c[0] + left[0] * sgn * x + up[0] * y, c[1] + left[1] * sgn * x + up[1] * y,
                   c[2] + left[2] * sgn * x + up[2] * y) for x, y in sec]
                 for c, (left, up) in zip(curve, frames)]
        for j in range(len(sec) - 1):
            dx, dy = sec[j + 1][0] - sec[j][0], sec[j + 1][1] - sec[j][1]
            for i in range(len(curve) - 1):
                left, up = frames[i]
                ox, oy = -dy, dx
                outward = tuple(left[k] * sgn * ox + up[k] * oy for k in range(3))
                a, b, c, d = rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j]
                out += [_orient((a, b, c), outward), _orient((a, c, d), outward)]
    return out


def _layer(objs, name, style, slot, kind, offset_attr, z, z_attr, width_attr, thickness_attr, pts, values,
           lats=None, flip=False):
    """One layer, the way `point_build._styled` builds it: the slot's PROFILE ASSET when the road names one (its
    material off the asset), else the parametric band/deck in the slot's material."""
    asset = style.asset(slot) if style is not None else None
    if asset is not None:
        mat = asset.get("material") or style.material(slot)
        require = ASSET_REQUIRE.get(slot, "") or width_attr
        _add(objs, name, mat, sweep_profile(pts, values, asset, flip, offset_attr, z,
                                            ASSET_Z_ATTR.get(slot, z_attr), require, lats))
        return
    mat = style.material(slot) if style is not None else MAT[pk.SLOT_DEFAULT[slot]]
    _add(objs, name, mat, sweep(pts, values, kind, offset_attr, z, z_attr, width_attr, thickness_attr, lats))


def collision_name(base, kind, ped_access):
    """`point_build.collision_name`: `<base>-<kind>[-noped]-colonly`."""
    return "%s-%s%s%s" % (base, kind, "" if ped_access else NO_PED_SUFFIX, SUFFIX_COL)


def _collision(objs, surface_names, edge_names, name, ped_access):
    """`point_build.build_collision`: one proxy for what a car drives on, one for the kerb and footway -- never one
    merged, so the navmesh and the impact resolver can tell them apart. Every material of the objects, as one
    material-less mesh."""
    for names, kind, ped in ((surface_names, COL_ROAD, False), (edge_names, COL_WALK, ped_access)):
        tris = [t for n in names for ts in objs.get(n, {}).values() for t in ts]
        _add(objs, collision_name(name + "_" + kind, kind, ped), NO_MATERIAL, tris)


def build(net, ground=None, part=None, zone=None, kit=None, report=None, solved=None, clear=None):
    """Every object `point_build.build_network` emits, as triangles: `{object: {material name: [tri]}}`, the KIT
    frame, collision proxies included (material `NO_MATERIAL`). Same solve, same cut (`part` + `zone` emit one
    piece of a zoned network, the WHOLE network still solved), same styles (`kit`, default `point_kit.load()`).
    `report`, a dict, collects `missing_style` rows. `solved`, `point_edges.solve_all(net, ground)` already run,
    saves re-solving the network for every piece of it. `clear` (`point_furniture.clear_zones`) is where lane and
    centre lines stop at a junction mouth -- the stop line and the zebra -- which only the lane graph knows."""
    kit = kit if kit is not None else pk.load()
    solves, jsolves, gsolves, bands = solved if solved is not None else ped.solve_all(net, ground)
    styles = {n: pk.resolve(r, kit) for n, r in net.roads.items()}
    objs = {}
    by_road = {}
    for s in solves:
        by_road.setdefault(s.road.name, []).append(s)

    def mine_run(s):
        return part is None or part.run_zone(s.uids) == zone

    for road_name, runs in by_road.items():
        if not any(mine_run(s) for s in runs):
            continue
        style = styles.get(road_name)
        if report is not None:
            for slot, kind, missing in style.missing():
                report.setdefault("missing_style", []).append((road_name, slot, kind, missing))
        med_slot = "mark_y" if getattr(style.road, "median_style", None) == pm.MED_PAINT else "median"
        for i, s in enumerate(runs):
            if not mine_run(s):
                continue
            name = road_name if len(runs) == 1 else "%s_%d" % (road_name, i)
            pts, values = ps.carrier_points(s)
            lats = [_lateral(t) for t in poly_tangents(pts)]
            surf = name + "__surface"
            for layer, kind, slot, oa, z, za, wa, ta in SURFACE:
                _layer(objs, surf, style, med_slot if slot == "median" else slot, kind, oa, z, za, wa, ta,
                       pts, values, lats)
            # the median wall is a COLLIDER only: what is seen is the kit panel `point_furniture` tiles along it
            _add(objs, collision_name(name + "_median", COL_ROAD, False), NO_MATERIAL,
                 median_wall(style.road, pts, values, lats))
            if any(float(v.get("rka_shed", 0.0)) > 0.0 for v in values):
                sh = sheds(pts, values, lats)
                _add(objs, name + "__shed", style.material("deck"), sh["concrete"])
                _add(objs, name + "__shed", SHED_LAMP_MATERIAL, sh["lamps"])
                _add(objs, collision_name(name + "_shed", COL_ROAD, False), NO_MATERIAL, sh["concrete"])
            if any(float(v.get("rka_pillar_param", 0.0)) > 0.0 for v in values):
                own = {road_name}
                cols, over, dropped = pillars(pts, values, lats, style.pier(), ground,
                                              blocked=lambda top, fwd, half: pier_on_road(bands, own, top, fwd, half))
                if dropped and report is not None:
                    report.setdefault("pier_on_road", []).append((name, dropped))
                for mat, tris in cols.items():
                    _add(objs, surf, style.material("deck") if mat is None else mat, tris)
                if over > 0.0 and report is not None:
                    report.setdefault("pier_overhang", []).append((name, style.pier()["name"], round(over, 2)))
            edge_names = []
            for sfx, epts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
                edge_names.append("%s__edges_%s" % (name, sfx))
                _edge_run(objs, edge_names[-1], epts, walk, kerb, wall, sgn, style)
            for yellow in (False, True):
                for r in (r for r in ps.solve_marks(s) if r.yellow is yellow):
                    for line in pfu.clip_outside(list(r.points), clear):
                        vals = [{"rka_mark_w": ps.MARK_WIDTH / 2.0}] * len(line)
                        _add(objs, "%s__marks_%s" % (name, "y" if yellow else "w"),
                             style.material("mark_y" if yellow else "mark_w"),
                             sweep(line, vals, "band", "", ps.PAINT_Z_BIAS, "", "rka_mark_w", ""))
            _collision(objs, [surf], edge_names, name, bool(s.road.ped_access))
    for j in jsolves:
        if part is not None and part.pad_zone(j.uids) != zone:
            continue
        name = "JCT_" + j.uids[0][:8]
        road = net.road_of(j.uids[0])
        style = styles.get(road.name) if road is not None else pk.resolve(object(), kit)
        _add(objs, name + "__pad", style.material("surface"), _face_up([t for t in j.fan if abs(_up(t)) > 1e-9]))
        edge_names = []
        for sfx, epts, walk, kerb, wall, sgn in ped.junction_edge_runs(j):
            edge_names.append("%s__edges_%s" % (name, sfx))
            _edge_run(objs, edge_names[-1], epts, walk, kerb, wall, sgn, style)
        _collision(objs, [name + "__pad"], edge_names, name, True)
    for g in gsolves:
        if part is not None and part.gore_zone(g.ramp_uid) != zone:
            continue
        name = "GORE_" + g.ramp_uid[:8]
        road = net.road_of(g.ramp_uid)
        style = styles.get(road.name) if road is not None else pk.resolve(object(), kit)
        tris = _face_up([t for t in g.tris if abs(_up(t)) >= 1e-3])
        if not tris:
            continue
        _add(objs, name + "__gore", style.material("surface"), tris)
        edge_names = []
        for sfx, epts, walk, kerb, wall, sgn in ped.gore_edge_runs(g):
            edge_names.append("%s__edges_%s" % (name, sfx))
            _edge_run(objs, edge_names[-1], epts, walk, kerb, wall, sgn, style)
        _collision(objs, [name + "__gore"], edge_names, name, g.ped_access)
    return objs


def _edge_run(objs, name, pts, walk, kerb, wall, sgn, style=None):
    """`point_build.build_edge_run` without Blender: the same per-vertex values (`edge_run_values`, restated
    here because `point_build` imports bpy), the same three layers, each styled."""
    half_t = ps.BARRIER_THICKNESS * 0.5
    values = []
    for k in range(len(kerb)):
        h, w, wl = float(kerb[k]), float(walk[k]), float(wall[k])
        values.append({"rka_curb_ol": 0.0, "rka_curb_hl": h, "rka_curb_tl": h * ps.KERB_THICKNESS,
                       "rka_walk_cl": sgn * w, "rka_walk_hl": w, "rka_walk_zl": h, "rka_wall_h": wl,
                       "rka_wall_hw": half_t if wl > 0.0 else 0.0, "rka_wall_c": sgn * (2.0 * w + half_t),
                       "rka_wall_z": h + wl, "rka_wall_foot": h})
    pts = [tuple(p) for p in pts]
    for layer, kind, slot, oa, z, za, wa, ta in EDGE:
        _layer(objs, name, style, slot, kind, oa, z, za, wa, ta, pts, values, flip=(sgn < 0.0))
    # The CAR WALL: where a barrier stands, a collision-only wall on its line, `CAR_WALL_HEIGHT` tall from its foot, that
    # only vehicle bodies collide with (`CollisionLayers.CAR_WALL`, set by the bake from the `-carwall` name). A car
    # pressed into a 1.15 m parapet at speed caught the wall's top edge with its hull and was thrown up it (measured on
    # the diamond's exit ramp, `probe_road_launch.gd`: a 7.7 m/s rise at 20 m/s, 2 m left of the lane).
    cw = [{"rka_cw_c": v["rka_wall_c"], "rka_cw_hw": v["rka_wall_hw"], "rka_cw_z": v["rka_wall_foot"] + CAR_WALL_HEIGHT,
           "rka_cw_t": CAR_WALL_HEIGHT if v["rka_wall_h"] > 0.0 else 0.0} for v in values]
    _add(objs, collision_name(name + "_carwall", COL_CARWALL, False), NO_MATERIAL,
         sweep(pts, cw, "deck", "rka_cw_c", 0.0, "rka_cw_z", "rka_cw_hw", "rka_cw_t"))


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
    # A pier: the cap rigid, the shaft's foot exactly `height` below the soffit, turned onto the road's heading.
    cap_z = -1.0
    pier = {"stretch_z": cap_z, "tris": {"M_Concrete": [[-3.0, -0.5, 0.0, 3.0, -0.5, 0.0, 3.0, 0.5, cap_z],
                                                          [-0.4, 0.0, cap_z, 0.4, 0.0, cap_z, 0.0, 0.3, -10.0]]}}
    fwd = _norm((1.0, 1.0, 0.0))
    placed = place_pier(pier, (100.0, 50.0, 20.0), 25.0, fwd)["M_Concrete"]
    zs = sorted(p[2] for t in placed for p in t)
    assert abs(zs[0] - (20.0 - 25.0)) < 1e-9 and abs(zs[-1] - 20.0) < 1e-9, zs
    assert sum(1 for z in zs if abs(z - (20.0 + cap_z)) < 1e-9) == 3, "the cap must not stretch"
    cap = placed[0]
    across = _norm(_sub(cap[1], cap[0]))
    assert abs(across[0] * fwd[0] + across[1] * fwd[1]) < 1e-9 and abs(math.dist(cap[0], cap[1]) - 6.0) < 1e-9
    # Over ground falling across the road (x), the shaft vertex at local x = +0.4 reaches the ground under ITSELF.
    slope = lambda x, y: -5.0 - 0.5 * x
    sloped = place_pier(pier, (0.0, 0.0, 20.0), 25.0, (0.0, 1.0, 0.0), ground=slope)["M_Concrete"]
    feet = [p for t in sloped for p in t if p[2] < 20.0 + cap_z - 1e-6]
    # ...to the lowest ground within FOOT_REACH of itself: on this slope, its own ground less 0.5 x FOOT_REACH
    assert feet and all(abs(p[2] - (slope(p[0], p[1]) - 0.5 * FOOT_REACH)) < 1e-9 for p in feet), feet
    # and over a vertical quay edge (land to the seabed inside one cell) no foot is left on the land side
    quay = lambda x, y: 0.0 if x < -0.5 else -24.0
    q = place_pier(pier, (0.0, 0.0, 20.0), 25.0, (0.0, 1.0, 0.0), ground=quay)["M_Concrete"]
    qf = [p for t in q for p in t if p[2] < 20.0 + cap_z - 1e-6]
    assert qf and all(abs(p[2] + 24.0) < 1e-9 for p in qf), qf
    print("OK: with a ground sampler each shaft vertex stretches to the lowest ground within %.1f m of itself" % FOOT_REACH)
    short = place_pier(pier, (0.0, 0.0, 5.0), 0.8, (0.0, 1.0, 0.0))["M_Concrete"]
    assert abs(min(p[2] for t in short for p in t) - 4.2) < 1e-9, "a short pier squashes whole, foot on the ground"
    print("OK: a pier asset keeps its cap, stretches its shaft to the ground and turns onto the road")
    # A rock shed open on the LEFT over samples 1..3 of a road running +x: soffit SHED_CLEAR over the road, the columns
    # on +y (the left of travel), the wall on -y, the roof reaching SHED_BACK past the wall, lamps under the soffit.
    pts = [(10.0 * i, 0.0, 2.0) for i in range(6)]
    vals = [{"rka_deck_c": 0.0, "rka_deck_w": 9.0, "rka_shift": 0.0, "rka_halfw": 9.0,
             "rka_shed": 1.0 if 1 <= i <= 3 else 0.0} for i in range(6)]
    sh = sheds(pts, vals, [_lateral(t) for t in poly_tangents(pts)])
    cz = [p for t in sh["concrete"] for p in t]
    xs = [p[0] for p in cz]
    assert abs(min(xs) - 10.0) < 1.0 and abs(max(xs) - 40.0) < 1.0, (min(xs), max(xs))   # holds to the NEXT station
    roof_under = sorted({round(p[2], 6) for p in cz})
    assert 2.0 + ps.SHED_CLEAR in roof_under and max(roof_under) == 2.0 + ps.SHED_CLEAR + ps.SHED_ROOF, roof_under
    ys = [p[1] for p in cz]
    assert abs(max(ys) - (9.0 + SHED_EDGE + SHED_COL / 2)) < 1e-6, max(ys)
    assert abs(min(ys) - (-(9.0 + SHED_EDGE) - SHED_BACK)) < 1e-6, min(ys)
    cols = [p for t in sh["concrete"] for p in t if p[2] < 2.0 and p[1] > 0.0]
    walls = [p for t in sh["concrete"] for p in t if p[2] < 2.0 and p[1] < 0.0]
    assert cols and walls and all(abs(p[1] - (9.0 + SHED_EDGE)) <= SHED_COL / 2 + 1e-6 for p in cols)
    lz = [p[2] for t in sh["lamps"] for p in t]
    assert lz and max(lz) <= 2.0 + ps.SHED_CLEAR + 1e-6 and min(lz) > 2.0 + ps.SHED_CLEAR - 0.2
    flip = sheds(pts, [dict(v, rka_shed=2.0 if v["rka_shed"] else 0.0) for v in vals],
                 [_lateral(t) for t in poly_tangents(pts)])
    assert max(p[1] for t in flip["concrete"] for p in t) == -min(ys)
    # A column never stands on another road below: a street 10 m under the deck, 12 m wide along y, at x 100.
    street = ped.Band("street", [(94.0, -200.0), (106.0, -200.0), (106.0, 200.0), (94.0, 200.0)],
                      [(100.0, -200.0, 0.0), (100.0, 200.0, 0.0)])
    level = ped.Band("level", [(94.0, -200.0), (106.0, -200.0), (106.0, 200.0), (94.0, 200.0)],
                     [(100.0, -200.0, 8.0), (100.0, 200.0, 8.0)])
    fwd = (1.0, 0.0, 0.0)
    assert pier_on_road([street], {"deck"}, (100.0, 0.0, 10.0), fwd, 0.7)          # on it
    assert pier_on_road([street], {"deck"}, (108.0, 0.0, 10.0), fwd, 0.7)          # 1.3 m past its edge
    assert not pier_on_road([street], {"deck"}, (120.0, 0.0, 10.0), fwd, 0.7)      # 14 m clear
    assert not pier_on_road([level], {"deck"}, (100.0, 0.0, 10.0), fwd, 0.7)       # 2 m below: not a road UNDER it
    assert not pier_on_road([street], {"street"}, (100.0, 0.0, 10.0), fwd, 0.7)    # its own band
    # a portal pier 16 m across, centred 12 m off the street, still reaches over it
    assert pier_on_road([street], {"deck"}, (100.0, 12.0, 10.0), (0.0, 1.0, 0.0), 8.0)
    # A barrier edge run carries a car wall on the same line, CAR_WALL_HEIGHT tall from the barrier's foot; none without.
    objs = {}
    run = [(0.0, 0.0, 5.0), (10.0, 0.0, 5.0), (20.0, 0.0, 5.0)]
    _edge_run(objs, "E", run, [0.0] * 3, [0.15] * 3, [1.0] * 3, 1.0)
    cw = objs.get(collision_name("E_carwall", COL_CARWALL, False), {}).get(NO_MATERIAL, [])
    zs = [p[2] for t in cw for p in t]
    ys = [p[1] for t in cw for p in t]
    assert cw and abs(min(zs) - 5.15) < 1e-6 and abs(max(zs) - (5.15 + CAR_WALL_HEIGHT)) < 1e-6, (min(zs), max(zs))
    assert abs(min(ys) - 0.0) < 1e-6 and abs(max(ys) - ps.BARRIER_THICKNESS) < 1e-6, (min(ys), max(ys))
    objs = {}
    _edge_run(objs, "F", run, [0.0] * 3, [0.15] * 3, [0.0] * 3, 1.0)
    assert not objs.get(collision_name("F_carwall", COL_CARWALL, False), {}).get(NO_MATERIAL), "no barrier, no car wall"
    print("OK: a barrier carries a %.0f m vehicle-only car wall on its line; no barrier, none" % CAR_WALL_HEIGHT)
    print("OK: a column never stands on or within %.0f m of a road more than %.0f m below" % (PIER_ROAD_CLEAR, PIER_ROAD_DZ))
    print("OK: a rock shed: soffit %.1f m over the road, columns on the open side, wall + roof to the rock on the other"
          % ps.SHED_CLEAR)
    return 6


if __name__ == "__main__":
    print("point_mesh.py: %d checks PASS" % self_test())
