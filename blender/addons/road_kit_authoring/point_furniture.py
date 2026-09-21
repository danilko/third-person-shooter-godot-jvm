"""point_furniture.py -- ROAD DECALS AND STREET FURNITURE, placed from the solve (PLAN.md 3.6c).

The road GEOMETRY is the solver's sweep (`point_mesh`); what a real street also has -- turn arrows, a stop line,
a zebra crossing, manholes, gutter drains, planters on a wide footway, bollards round a junction corner -- is
PLACED here, from facts the build already owns, never drawn by hand:

  * the approach lanes of every junction arm and the turns their connectors make (the piece's `.lanekit.json`,
    which `roadkit_cli.py pieces` writes before the mesh build) -> an arrow on each lane, a stop line across the
    lanes that arrive, and a zebra crossing across the whole carriageway, on the APPROACH road, so the order a
    driver meets them is arrow, stop line, crossing, junction (the Japanese layout);
  * every road run's kerb/footway edge runs (`point_edges.road_edge_runs`) -> drains in the gutter, planters on a
    footway wide enough to keep walking room;
  * every junction corner (`point_edges.junction_edge_runs`) -> bollards on the corner's footway;
  * every signalised junction arm -> a Japanese mast-arm SIGNAL on the FAR side of the junction (Japan puts the
    vehicle head beyond the crossing, over the arriving lanes, on the driver's left kerb -- keep-left), just past
    the far arm's zebra (`_signals`);
  * every road run -> street LAMPS on the kerbs, staggered side to side, or twin-arm lamps down a raised MEDIAN
    wide enough to stand one (`_lamps`).

Nothing is placed where a barrier stands (the road is elevated there, or has no pavement to walk on), nor over
ground more than `max_above_ground` below the lane when a ground grid is given (a manhole on a bridge deck).

The PROPS and the kit decals are the downloaded kits' own pieces (`assets/world_source/kits/road_kit/furniture.json`
names them; an asset may name its own `kit`, the poles come from `quaternius_zombie_apocalypse`). They leave here as PLACEMENTS -- `{asset, path, pos, fwd, scale}` in the KIT frame -- which `point_gltf`
writes as `mmesh_<asset>` nodes carrying `asset_path`, and `WorldBaker` collapses into one MultiMesh per asset.
The stop line and the zebra are PAINT, triangles in the road's own `mark_w` material, because the Japanese
marks are not in the CC0 kit (a zebra with no side bars, a stop line across the arriving lanes only); the kit's
arrows are close enough to use. A piece that must be solid (`collide`) also gets an oriented box in the piece's
`FURN_props-prop-colonly` proxy -- except a `breakable` pole (PLAN.md 3.11), whose marker carries its pole size, mass,
break speed and respawn time instead, for the runtime `BreakableProps` node that owns its collider.

Everything is DETERMINISTIC (no random phase): a manhole's phase along its lane is a hash of the lane id, so a
rebuild of an unchanged record writes the same file, which is what the build digest relies on.
"""
import fnmatch
import hashlib
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
TABLE_PATH = os.path.join(REPO, "assets", "world_source", "kits", "road_kit", "furniture.json")

try:
    from . import point_edges as ped, point_solve as ps, point_model as pm
except ImportError:
    import point_edges as ped                                                # noqa: E402
    import point_solve as ps                                                 # noqa: E402
    import point_model as pm                                                 # noqa: E402

#: Object names this module adds to a piece.
PAINT_OBJECT = "FURN__marks_w"
COLLISION_OBJECT = "FURN_props-prop-colonly"
#: `point_mesh.NO_MATERIAL` (restated: importing point_mesh here would be a cycle).
NO_MATERIAL = ""
#: How far a cleared zone reaches past the lines it clears, sideways (a centre line sits ON the arriving lanes'
#: edge, and is 0.15 m wide) and past the mouth into the pad (a line ends at the run end, which is the mouth).
CLEAR_MARGIN = 0.3
CLEAR_PAST_MOUTH = 1.0
#: Turn sets the kit has an arrow for. A left + right with no straight (a T's stem) and all three get none.
ARROW_FOR = {frozenset("S"): "arrow_S", frozenset("L"): "arrow_L", frozenset("R"): "arrow_R",
             frozenset("SL"): "arrow_SL", frozenset("SR"): "arrow_SR"}


# ------------------------------------------------------------------------------------------- the table

def res_to_path(res):
    return os.path.join(REPO, res[len("res://"):]) if res.startswith("res://") else res


def _piece_bounds(path):
    """(min, max) of a glTF piece's POSITION accessors, read off the JSON (the accessor carries them)."""
    with open(path) as fh:
        doc = json.load(fh)
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for m in doc.get("meshes", ()):
        for p in m.get("primitives", ()):
            a = doc["accessors"][p["attributes"]["POSITION"]]
            lo = [min(x, y) for x, y in zip(lo, a["min"])]
            hi = [max(x, y) for x, y in zip(hi, a["max"])]
    return lo, hi


class Table(object):
    """`furniture.json`, with each asset's res:// path, filesystem path and glTF bounds resolved."""

    def __init__(self, path=TABLE_PATH):
        self.path = path
        with open(path) as fh:
            doc = json.load(fh)
        self.kit = doc["kit"]
        self.rules = doc["rules"]
        self.assets = {}
        for name, a in doc["assets"].items():
            res = a.get("kit", self.kit) + a["piece"]
            fs = res_to_path(res)
            lo, hi = _piece_bounds(fs)
            self.assets[name] = dict(a, res=res, file=fs, lo=lo, hi=hi,
                                     scale=list(a.get("scale", [1.0, 1.0, 1.0])))

    def files(self):
        """Every file the placements depend on: the table and each piece (the digest salts them)."""
        return [self.path] + sorted({a["file"] for a in self.assets.values()})


def load(path=TABLE_PATH):
    return Table(path) if os.path.exists(path) else None


# ------------------------------------------------------------------------------------------- geometry

def _norm2(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, 0.0)


def _left(f):
    return (-f[1], f[0])


def _lengths(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def _at(pts, cum, s):
    """(point, unit plan direction, segment index) at plan arc length `s` along `pts`."""
    s = max(0.0, min(cum[-1], s))
    for i in range(len(pts) - 1):
        if cum[i + 1] >= s or i == len(pts) - 2:
            seg = cum[i + 1] - cum[i]
            t = (s - cum[i]) / seg if seg > 1e-9 else 0.0
            a, b = pts[i], pts[i + 1]
            p = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
            return p, _norm2(b[0] - a[0], b[1] - a[1]), i
    return tuple(pts[0]), (0.0, 1.0), 0


def _stations(length, spacing, clear, phase=None):
    """Arc lengths every `spacing` m, `clear` m in from both ends; `phase` (default half a spacing) from the start."""
    if length < 2.0 * clear:
        return []
    first = clear + (spacing * 0.5 if phase is None else phase % spacing)
    out, s = [], first
    while s <= length - clear + 1e-9:
        out.append(s)
        s += spacing
    return out


def _quad(p0, p1, p2, p3):
    """Two up-facing triangles over the corners p0..p3 (counter-clockwise from above)."""
    return [(p0, p1, p2), (p0, p2, p3)]


def _up_quad(a, b, c, d):
    q = _quad(a, b, c, d)
    n = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return q if n > 0.0 else [(t[0], t[2], t[1]) for t in q]


def _box(bottom, fwd, half_fwd, half_side, height):
    """An oriented box: `bottom` its base centre, `fwd` its long axis in plan, outward-facing triangles."""
    f, l = fwd, _left(fwd)
    cs = []
    for sf, sl in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        cs.append((bottom[0] + f[0] * half_fwd * sf + l[0] * half_side * sl,
                   bottom[1] + f[1] * half_fwd * sf + l[1] * half_side * sl))
    z0, z1 = bottom[2], bottom[2] + height
    v = [(x, y, z0) for x, y in cs] + [(x, y, z1) for x, y in cs]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
             (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    tris = [(v[a], v[b], v[c]) for a, b, c in faces]
    # the corner order above may run clockwise; flip every face if the bottom does not face down
    a, b, c = tris[0]
    if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0.0:
        tris = [(t[0], t[2], t[1]) for t in tris]
    return tris


def godot_to_kit(p):
    """`point_export.godot`'s inverse: Godot (x, y, z) -> kit (x, -z, y)."""
    return (float(p[0]), -float(p[2]), float(p[1]))


# ------------------------------------------------------------------------------------------- placing

class Furniture(object):
    """What `place` returns for ONE piece: `paint` `{material: [tri]}`, `collision` `[tri]`, `placements`."""

    def __init__(self):
        self.paint = {}
        self.collision = []
        self.placements = []
        self.counts = {}

    def put(self, table, asset, pos, fwd, road=None):
        a = table.assets.get(asset)
        if a is None or (road is not None and excluded(a, road)):
            return False
        lift = float(a.get("lift", 0.0)) - a["lo"][1] * a["scale"][1]
        self.placements.append({"asset": asset, "path": a["res"], "pos": (pos[0], pos[1], pos[2] + lift),
                                "fwd": fwd, "scale": list(a["scale"]), "road": road or ""})
        if a.get("collide") or a.get("collide_pole"):
            self.placements[-1]["solid"] = True
        if a.get("collide_pole"):
            self.placements[-1]["pole"] = True
        self.counts[asset] = self.counts.get(asset, 0) + 1
        if a.get("collide_pole") and a.get("breakable"):
            # a knock-down pole (PLAN.md 3.11) has no static box: its batch's BreakableProps node builds a collider
            # per pole at runtime and takes it away when a car knocks the pole down
            half, height = a["collide_pole"]
            b = a["breakable"]
            self.placements[-1]["breakable"] = {"pole_half": float(half), "pole_height": float(height),
                                                "mass": float(b.get("mass", 250.0)),
                                                "break_speed": float(b.get("break_speed", 5.0)),
                                                "respawn": float(b.get("respawn", 60.0))}
        elif a.get("collide_pole"):
            # a pole's shaft only: a box of the whole footprint would stand a mast arm's reach across the road
            half, height = a["collide_pole"]
            self.collision += _box((pos[0], pos[1], pos[2]), fwd, half, half, height)
        elif a.get("collide"):
            # the piece's plan footprint (its X across, its Z along -- forward is -Z), from its own bounds
            half_side = 0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0]
            half_fwd = 0.5 * (a["hi"][2] - a["lo"][2]) * a["scale"][2]
            height = (a["hi"][1] - a["lo"][1]) * a["scale"][1]
            self.collision += _box((pos[0], pos[1], pos[2] + float(a.get("lift", 0.0))), fwd, half_fwd,
                                   half_side, height)
        return True

    def clear_of(self, pos, radius, poles_only=False):
        """True when no SOLID placement (or, `poles_only`, no pole) already stands within `radius` m of `pos`."""
        key = "pole" if poles_only else "solid"
        for p in self.placements:
            if p.get(key) and math.hypot(p["pos"][0] - pos[0], p["pos"][1] - pos[1]) < radius:
                return False
        return True

    def paint_tris(self, mat, tris):
        self.paint.setdefault(mat, []).extend(tris)


def excluded(asset, road):
    """True when the asset's `exclude_roads` globs name this road."""
    return any(fnmatch.fnmatchcase(road or "", g) for g in asset.get("exclude_roads", ()))


def _lane_kit(lane):
    return [godot_to_kit(p) for p in lane.get("points", ())]


def _grounded(ground, p, limit):
    """True when there is no ground grid, no ground under `p`, or the ground is within `limit` below it."""
    if ground is None:
        return True
    g = ground(p[0], p[1])
    return g is None or p[2] - g <= limit


def _arms(lanes, junctions):
    """Every junction arm with arriving lanes, in the kit frame: `{fwd, left, anchor, ins, rows}`. `fwd` is the
    travel direction into the junction, `anchor` the first arriving lane's stop-line end; each row is one lane at
    the mouth as (lateral offset from the anchor, half width, a sampler of back-distance -> point). The ONE owner
    of an arm's frame, shared by the marks placed here and the paint they keep clear (`clear_zones`)."""
    for j in junctions:
        for arm in j.get("arms", ()):
            ins = [lanes[i] for i in arm.get("in_lanes", ()) if i in lanes]
            outs = [lanes[i] for i in arm.get("out_lanes", ()) if i in lanes]
            if not ins:
                continue
            # the mouth's frame: travel direction into the junction, from the arriving lanes' last segments
            fx = fy = 0.0
            for l in ins:
                pts = _lane_kit(l)
                if len(pts) >= 2:
                    d = _norm2(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
                    fx, fy = fx + d[0], fy + d[1]
            fwd = _norm2(fx, fy)
            if fwd == (0.0, 0.0):
                continue
            left = _left(fwd)
            anchor = _lane_kit(ins[0])[-1]
            rows = []
            for l, arriving in [(l, True) for l in ins] + [(l, False) for l in outs]:
                pts = _lane_kit(l)
                if len(pts) < 2:
                    continue
                cum = _lengths(pts)
                end = pts[-1] if arriving else pts[0]
                lat = (end[0] - anchor[0]) * left[0] + (end[1] - anchor[1]) * left[1]

                def sample(back, pts=pts, cum=cum, arriving=arriving):
                    return _at(pts, cum, cum[-1] - back if arriving else back)[0]
                rows.append({"lane": l, "lat": lat, "half": 0.5 * float(l.get("lane_width", 3.5)),
                             "sample": sample, "length": cum[-1], "arriving": arriving})
            if rows:
                yield {"fwd": fwd, "left": left, "anchor": anchor, "ins": ins, "rows": rows, "junction": j,
                       "arm": arm}


def _has_zebra(table, arm):
    return all(row["length"] >= table.rules["crosswalk_back"][1] for row in arm["rows"])


def _has_stop(table, row):
    return row["arriving"] and row["length"] >= table.rules["stop_back"] + table.rules["stop_width"]


def clear_zones(table, lanes_doc):
    """Where lane and centre LINES must not be painted, as plan rectangles `(anchor, fwd, left, lat_lo, lat_hi,
    back_lo, back_hi)` in the kit frame (PLAN.md 3.6c). The Japanese layout: a line on the arriving side, and the
    centre line, ends at the STOP LINE's upstream edge; nothing is painted across the zebra; a departing lane's
    line starts past it. Derived from the same arm frames and the same placement tests as the marks themselves,
    so a line can only stop where a stop line or a zebra was actually painted."""
    if table is None:
        return []
    r = table.rules
    lanes = {l["id"]: l for l in lanes_doc.get("lanes", ())}
    junctions = [j for _k, j in sorted((j["id"], j) for j in lanes_doc.get("junctions", ()))]
    m = CLEAR_MARGIN
    zones = []
    for arm in _arms(lanes, junctions):
        rows = arm["rows"]
        base = (arm["anchor"], arm["fwd"], arm["left"])
        if _has_zebra(table, arm):
            zones.append(base + (min(w["lat"] - w["half"] for w in rows) - m,
                                 max(w["lat"] + w["half"] for w in rows) + m, -CLEAR_PAST_MOUTH,
                                 r["crosswalk_back"][1]))
        arriving = [w for w in rows if _has_stop(table, w)]
        if arriving:
            zones.append(base + (min(w["lat"] - w["half"] for w in arriving) - m,
                                 max(w["lat"] + w["half"] for w in arriving) + m, -CLEAR_PAST_MOUTH,
                                 r["stop_back"] + r["stop_width"]))
    return zones


def _inside_interval(p, q, zone):
    """The part [t0, t1] of segment p->q inside one zone (Liang-Barsky in the zone's own frame), or None."""
    anchor, fwd, left, lo, hi, b0, b1 = zone
    def lat(v):
        return (v[0] - anchor[0]) * left[0] + (v[1] - anchor[1]) * left[1]
    def back(v):
        return -((v[0] - anchor[0]) * fwd[0] + (v[1] - anchor[1]) * fwd[1])
    t0, t1 = 0.0, 1.0
    for f, a, b in ((lat, lo, hi), (back, b0, b1)):
        v0, v1 = f(p), f(q)
        d = v1 - v0
        if abs(d) < 1e-12:
            if v0 < a or v0 > b:
                return None
            continue
        ta, tb = (a - v0) / d, (b - v0) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 >= t1:
            return None
    return t0, t1


def clip_outside(pts, zones, min_length=0.05):
    """A painted polyline with every part inside any zone removed: a list of the polylines left."""
    if not zones:
        return [list(pts)]

    def lerp(p, q, t):
        return tuple(p[k] + (q[k] - p[k]) * t for k in range(3))
    out, cur = [], []
    eps = 1e-9
    for k in range(len(pts) - 1):
        p, q = pts[k], pts[k + 1]
        inside = sorted(iv for iv in (_inside_interval(p, q, z) for z in zones) if iv is not None)
        keep, t = [], 0.0
        for a, b in inside:
            if a > t:
                keep.append((t, a))
            t = max(t, b)
        if t < 1.0:
            keep.append((t, 1.0))
        if not keep or keep[0][0] > eps:
            if cur:
                out.append(cur)
            cur = []
        for n, (a, b) in enumerate(keep):
            if n and cur:
                out.append(cur)
                cur = []
            if not cur:
                cur = [lerp(p, q, a)]
            cur.append(lerp(p, q, b))
        if keep and keep[-1][1] < 1.0 - eps and cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [c for c in out if len(c) >= 2 and sum(_norm_len(c[i], c[i + 1]) for i in range(len(c) - 1)) >= min_length]


def _norm_len(a, b):
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))


def _junction_marks(fur, table, lanes, junctions, mine, mark_mat):
    r = table.rules
    lift = float(r["paint_lift"])
    for arm in _arms(lanes, junctions):
            fwd, left, anchor, ins, rows = arm["fwd"], arm["left"], arm["anchor"], arm["ins"], arm["rows"]

            def z_at(lat, back):
                near = min(rows, key=lambda row: abs(row["lat"] - lat))
                return near["sample"](min(back, near["length"]))[2]

            def plan(lat, back):
                return (anchor[0] + left[0] * lat - fwd[0] * back, anchor[1] + left[1] * lat - fwd[1] * back)

            # ---- the zebra: across the whole carriageway, bars running along the road
            b0, b1 = r["crosswalk_back"]
            if _has_zebra(table, arm) and mine(ins[0]):
                lo = min(row["lat"] - row["half"] for row in rows) + r["crosswalk_margin"]
                hi = max(row["lat"] + row["half"] for row in rows) - r["crosswalk_margin"]
                bar, gap = r["crosswalk_bar"], r["crosswalk_gap"]
                n = int((hi - lo + gap) // (bar + gap))
                start = lo + 0.5 * ((hi - lo) - (n * bar + (n - 1) * gap))
                for k in range(max(0, n)):
                    s0 = start + k * (bar + gap)
                    s1 = s0 + bar
                    corners = []
                    for lat, back in ((s0, b1), (s1, b1), (s1, b0), (s0, b0)):
                        x, y = plan(lat, back)
                        corners.append((x, y, z_at(0.5 * (s0 + s1), back) + lift))
                    fur.paint_tris(mark_mat(ins[0]), _up_quad(*corners))
                fur.counts["crosswalk"] = fur.counts.get("crosswalk", 0) + 1
            # ---- the stop line: across the ARRIVING lanes only, then an arrow on each
            for row in rows:
                if not row["arriving"] or not mine(row["lane"]):
                    continue
                sb, sw = r["stop_back"], r["stop_width"]
                if _has_stop(table, row):
                    corners = []
                    for lat, back in ((row["lat"] - row["half"], sb + sw), (row["lat"] + row["half"], sb + sw),
                                      (row["lat"] + row["half"], sb), (row["lat"] - row["half"], sb)):
                        x, y = plan(lat, back)
                        corners.append((x, y, row["sample"](back)[2] + lift))
                    fur.paint_tris(mark_mat(row["lane"]), _up_quad(*corners))
                    fur.counts["stop_line"] = fur.counts.get("stop_line", 0) + 1
                turns = frozenset(lanes[n].get("turn", "") for n in row["lane"].get("next", ())
                                  if n in lanes and lanes[n].get("kind") == "connector" and lanes[n].get("turn"))
                asset = ARROW_FOR.get(turns)
                if asset and row["length"] >= r["arrow_min_lane"]:
                    pts = _lane_kit(row["lane"])
                    cum = _lengths(pts)
                    p, d, _i = _at(pts, cum, cum[-1] - r["arrow_back"])
                    fur.put(table, asset, p, d)


def _lane_props(fur, table, lanes, mine, ground):
    """Covers laid IN a through lane. Off by default (PLAN.md 3.18k, user: "in Japan / a modern city the manhole
    is on the kerb side, not in the middle of the road -- remove it"): a Japanese carriageway's covers sit in the
    gutter beside the kerb, which is what the `drain` run already lays. The placement is kept, behind
    `manhole_spacing = 0`, because a service cover down the lane IS correct on some roads (an older trunk road,
    a tunnel) and it is data, not code, that should decide."""
    r = table.rules
    if r.get("manhole_spacing", 0.0) <= 0.0:
        return
    for l in lanes.values():
        if l.get("kind") != "through" or not mine(l):
            continue
        pts = _lane_kit(l)
        if len(pts) < 2:
            continue
        cum = _lengths(pts)
        phase = int(hashlib.sha1(l["id"].encode()).hexdigest()[:8], 16) % 1000 / 1000.0 * r["manhole_spacing"]
        for s in _stations(cum[-1], r["manhole_spacing"], r["manhole_end_clear"], phase):
            p, d, _i = _at(pts, cum, s)
            if _grounded(ground, p, r["max_above_ground"]):
                fur.put(table, "manhole", p, d, l.get("road_name", ""))


def _edge_samples(pts, walk, kerb, wall, spacing, clear, phase=None):
    """Stations along one edge run: (point, plan direction, walk half width, kerb height), skipping any whose
    segment carries a barrier or no kerb."""
    pts = [tuple(p) for p in pts]
    cum = _lengths(pts)
    out = []
    for s in _stations(cum[-1], spacing, clear, phase):
        p, d, i = _at(pts, cum, s)
        j = min(i + 1, len(pts) - 1)
        if max(float(wall[i]), float(wall[j])) > 0.0:
            continue
        k = min(float(kerb[i]), float(kerb[j]))
        w = min(float(walk[i]), float(walk[j]))
        out.append((p, d, w, k))
    return out


def _barrier_samples(pts, walk, wall, spacing, clear, phase=None):
    """Stations along one edge run where it CARRIES a barrier (both ends of the segment): (point, plan direction,
    barrier height, footway width). The footway width is what says where the barrier -- and the CAR WALL on its
    line -- actually stands: `point_mesh` puts the barrier's centre `2*walk + BARRIER_THICKNESS/2` outboard of the
    edge line, so its car wall's INBOARD face is at `2*walk`."""
    pts = [tuple(p) for p in pts]
    cum = _lengths(pts)
    out = []
    for s in _stations(cum[-1], spacing, clear, phase):
        p, d, i = _at(pts, cum, s)
        j = min(i + 1, len(pts) - 1)
        h = min(float(wall[i]), float(wall[j]))
        if h > 0.0:
            out.append((p, d, h, min(float(walk[i]), float(walk[j]))))
    return out


def _edge_props(fur, table, solves, jsolves, bands, mine_run, mine_pad, ground):
    r = table.rules
    for s in solves:
        if not mine_run(s):
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, r["drain_spacing"], r["drain_end_clear"]):
                if k <= 0.0 or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                lat = _left(d)
                off = -sgn * r["drain_inset"]
                fur.put(table, "drain", (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2]), d, s.road.name)
            for p, d, w, k in (_edge_samples(pts, walk, kerb, wall, r["planter_spacing"], r["planter_end_clear"])
                               if r.get("planter_spacing", 0.0) > 0.0 else ()):
                if 2.0 * w < r["planter_min_footway"] or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                a = table.assets["planter"]
                half = 0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0]
                lat = _left(d)
                off = sgn * (r["planter_kerb_gap"] + half)
                pos = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k)
                if fur.clear_of(pos, r.get("pole_clearance", 0.0) + 0.5 * (a["hi"][2] - a["lo"][2]) * a["scale"][2],
                                poles_only=True):
                    fur.put(table, "planter", pos, d, s.road.name)
    for j in jsolves:
        if not mine_pad(j):
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.junction_edge_runs(j):
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, r["bollard_spacing"], r["bollard_end_clear"]):
                if w <= 0.0 or k <= 0.0:
                    continue
                lat = _left(d)
                off = sgn * r["bollard_inset"]
                pos = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k)
                if fur.clear_of(pos, r.get("pole_clearance", 0.0), poles_only=True):
                    fur.put(table, "bollard", pos, d)


def _signalised(table, junction):
    """A junction carries signals when any mouth is authored `traffic_light`, or -- `signal_all_junctions` -- when
    at least `signal_min_arms` of its arms have traffic arriving (a Japanese arterial crossing is signalised; a
    two-arm bend or a dead-end loop is not)."""
    arms = junction.get("arms", ())
    if any(a.get("traffic_light") for a in arms):
        return True
    r = table.rules
    return bool(r.get("signal_all_junctions")) and sum(1 for a in arms if a.get("in_lanes")) >= r["signal_min_arms"]


def _signals(fur, table, lanes, junctions, mine, ground):
    """One Japanese mast-arm signal per signalised arm, on the FAR side of the junction: the pole on the kerb
    the arriving traffic keeps to (keep-left: its left), `signal_past_mouth` beyond the far mouth (past the far
    arm's zebra), the arm reaching back over the arriving lanes and the heads facing them. Where the arm has a
    straight-ahead movement the far point is where the kerb lane's STRAIGHT connector ends (the road it leads
    into, however that road bends); with none (the stem of a T, a Y) the pole stands NEAR-side on
    the arm's own kerb, just junction-side of its zebra."""
    if "signal" not in table.assets:
        return
    r = table.rules
    # How far in from the kerb the pole stands. 0.7 m, not 1.0: on a 2 m block-street footway a 1.0 m offset put
    # the pole's far face 1.2 m out, and a 0.7 m walking capsule does not fit in the 0.8 m left -- measured, 118
    # of 450 signals stood exactly on the crowd's walk line (PLAN.md 3.18a). 0.7 leaves +0.20 m and is if
    # anything the more Japanese placement: a signal pole stands AT the kerb, not out in the footway.
    off = float(r["signal_kerb_offset"])
    for arm in _arms(lanes, junctions):
        if not _signalised(table, arm["junction"]):
            continue
        ins = [w for w in arm["rows"] if w["arriving"]]
        outs = [w for w in arm["rows"] if not w["arriving"]]
        # which side the kerb is on: the side of the arriving lanes AWAY from the departing ones
        ksign = 1.0
        if outs and sum(w["lat"] for w in ins) / len(ins) < sum(w["lat"] for w in outs) / len(outs):
            ksign = -1.0
        if ksign < 0.0:
            # right-hand traffic: the piece's arm reaches right of forward, so it would stand over the verge
            fur.counts["signal_skipped_right_hand"] = fur.counts.get("signal_skipped_right_hand", 0) + 1
            continue
        kerb = max(ins, key=lambda w: w["lat"])
        lane = kerb["lane"]
        if not mine(lane):
            continue
        conns = [lanes[n] for n in lane.get("next", ()) if n in lanes and lanes[n].get("kind") == "connector"]
        straight = [c for c in conns if c.get("turn") == "S" and len(c.get("points", ())) >= 2]
        if straight:
            pts = _lane_kit(straight[0])
            end = pts[-1]
            d = _norm2(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
            if d == (0.0, 0.0):
                continue
            tgt = [lanes[n] for n in straight[0].get("next", ()) if n in lanes]
            half = 0.5 * float(tgt[0].get("lane_width", 2.0 * kerb["half"])) if tgt else kerb["half"]
            side = _left(d)
            pos = (end[0] + d[0] * r["signal_past_mouth"] + side[0] * (half + off),
                   end[1] + d[1] * r["signal_past_mouth"] + side[1] * (half + off), end[2])
            fwd = d
        else:
            # no straight-ahead movement (the stem of a T, a Y): there is no far side to stand on, so the signal is
            # NEAR-side -- on this arm's own kerb, just junction-side of its zebra, as Japan does where the far
            # side is not visible or not there
            fwd, left, anchor = arm["fwd"], arm["left"], arm["anchor"]
            back = r["crosswalk_back"][0] - r["signal_near_inside"]
            lat = kerb["lat"] + kerb["half"] + off
            z = kerb["sample"](max(0.0, back))[2]
            pos = (anchor[0] + left[0] * lat - fwd[0] * back, anchor[1] + left[1] * lat - fwd[1] * back, z)
        if not _grounded(ground, pos, r["max_above_ground"]):
            continue
        fur.put(table, "signal", pos, fwd, lane.get("road_name", ""))


def _lamps(fur, table, solves, bands, mine_run, ground):
    """Street lighting. A run with a raised median wide enough (`median_lamp_min_half`) gets twin-arm lamps down
    the median every `median_lamp_spacing`; the others get single lamps on both kerbs every `lamp_spacing`,
    staggered half a spacing side to side, `lamp_inset` behind the kerb line, arm over the road. A lamp keeps
    `pole_clearance` from any solid prop already standing (a signal pole, a planter). Where an edge carries a barrier
    the lamp stands ON it instead, every `barrier_lamp_spacing` (0 = none), its shaft `barrier_lamp_clear` outboard
    of the car wall that stands on the barrier's line."""
    r = table.rules
    for s in solves:
        if not mine_run(s) or len(s.samples) < 2:
            continue
        road = s.road.name
        on_median = 0
        if "lamp_twin" in table.assets:
            pts = [tuple(sm.pos) for sm in s.samples]
            cum = _lengths(pts)
            for st in _stations(cum[-1], r["median_lamp_spacing"], r["lamp_end_clear"]):
                p, d, i = _at(pts, cum, st)
                j = min(i + 1, len(pts) - 1)
                mh = min(s.values[i]["rka_med_h"], s.values[j]["rka_med_h"])
                mz = min(s.values[i]["rka_med_z"], s.values[j]["rka_med_z"])
                # a WALL median (an expressway's divide) is narrow but carries its barrier: the lamp stands on the
                # barrier's top (`point_mesh.median_wall`), which is where a Japanese expressway's median lamps are
                wall = getattr(s.road, "median_style", None) == pm.MED_WALL
                need = r.get("median_wall_lamp_min_half", 0.45) if wall else r["median_lamp_min_half"]
                if mh < need or mz <= 0.0:
                    continue
                if wall:
                    mz += ps.MEDIAN_WALL_HEIGHT
                pos = (p[0], p[1], p[2] + mz)
                if fur.clear_of(pos, r["pole_clearance"]) and fur.put(table, "lamp_twin", pos, d, road):
                    on_median += 1
        if (on_median and not r.get("lamp_kerb_with_median")) or "lamp" not in table.assets:
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            spacing = r["lamp_spacing"]
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, spacing, r["lamp_end_clear"],
                                            0.5 * spacing if sgn > 0 else 0.0):
                if k <= 0.0 or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                lat = _left(d)
                o = sgn * r["lamp_inset"]
                pos = (p[0] + lat[0] * o, p[1] + lat[1] * o, p[2] + (k if w > 0.0 else 0.0))
                if fur.clear_of(pos, r["pole_clearance"]):
                    fur.put(table, "lamp", pos, (-sgn * lat[0], -sgn * lat[1]), road)
            # ON THE BARRIER: where the edge carries one (an elevated deck, a ramp, a bridge) the kerb lamp above is
            # skipped, and an expressway was unlit end to end. The lamp's base stands on the barrier's top, its arm
            # over the road; staggered side to side like the kerb lamps (3.13, user: lamps "from side and middle").
            spacing = r.get("barrier_lamp_spacing", 0.0)
            if not spacing:
                continue
            # WHERE it stands is DERIVED, not authored: a barrier lamp's shaft must clear the vehicle-only CAR
            # WALL that `point_mesh` builds on the barrier's line, whose inboard face is at `2*walk` from the edge
            # line. A fixed 0.15 m inset happened to be right for a road with no footway and no car wall, and once
            # both existed the 0.18 m shaft stood 3 cm INSIDE the wall -- a post in the carriageway that a car
            # scraping the parapet at 35 m/s caught and was flipped off a bridge by (PLAN.md 0.8, measured on
            # DebugRoads' `link`: 5 pole contacts and 2 falls). The shaft now starts `barrier_lamp_clear` outboard
            # of that face, which on a 0.32 m parapet still sits it on the barrier.
            half_pole = float((table.assets.get("lamp", {}).get("collide_pole") or [0.18])[0])
            for p, d, h, w_b in _barrier_samples(pts, walk, wall, spacing, r["lamp_end_clear"],
                                                 0.5 * spacing if sgn > 0 else 0.0):
                lat = _left(d)
                o = sgn * (2.0 * w_b + half_pole + r["barrier_lamp_clear"])
                pos = (p[0] + lat[0] * o, p[1] + lat[1] * o, p[2] + h)
                if fur.clear_of(pos, r["pole_clearance"]):
                    fur.put(table, "lamp", pos, (-sgn * lat[0], -sgn * lat[1]), road)


class _LaneIndex(object):
    """Every exported lane's plan segments on a coarse grid, for "is this spot in a lane".

    A footway is a fact about ONE road, so a spot on it can still be in the CARRIAGEWAY of another that runs
    alongside -- a ramp beside its mainline is the case (measured on the sample network: a tree on `demo_main`'s
    footway stood 0.23 m off `demo_ramp_b_F0`'s centreline). A lamp post there is bad; a 9 m tree is worse."""

    CELL = 20.0

    def __init__(self, lanes):
        self.cells = {}
        for lane in lanes.values():
            pts = _lane_kit(lane)
            half = 0.5 * float(lane.get("lane_width", 4.5) or 4.5)
            for a, b in zip(pts, pts[1:]):
                lo_x, hi_x = sorted((a[0], b[0]))
                lo_y, hi_y = sorted((a[1], b[1]))
                for i in range(int(math.floor(lo_x / self.CELL)), int(math.floor(hi_x / self.CELL)) + 1):
                    for j in range(int(math.floor(lo_y / self.CELL)), int(math.floor(hi_y / self.CELL)) + 1):
                        self.cells.setdefault((i, j), []).append((a, b, half))

    def clear_of(self, p, margin):
        """True when `p` is more than that lane's half width plus `margin` from every lane centreline."""
        i0, j0 = int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))
        for i in range(i0 - 1, i0 + 2):
            for j in range(j0 - 1, j0 + 2):
                for a, b, half in self.cells.get((i, j), ()):
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    n = vx * vx + vy * vy
                    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / n))
                    if math.hypot(p[0] - (a[0] + vx * t), p[1] - (a[1] + vy * t)) < half + margin:
                        return False
        return True


def _street_trees(fur, table, solves, bands, mine_run, ground, lanes):
    """街路樹: one species per STREET, at `tree_spacing` along every footway at least `tree_min_footway` wide,
    `tree_kerb_gap` in from the kerb so the canopy overhangs the carriageway rather than the lot.

    Which species is a hash of the ROAD's name, not of the spot: a Japanese street is planted with one tree, and
    a per-spot choice reads as scrub. It runs after the signals and the lamps because those are functional and own
    their place; a tree keeps `tree_clearance` from any solid prop already standing (a pole OR a planter), which
    is the one rule that stops a tree growing through a lamp post."""
    r = table.rules
    names = [n for n in r.get("tree_assets", ()) if n in table.assets]
    if not names or r.get("tree_spacing", 0.0) <= 0.0:
        return
    index = _LaneIndex(lanes)
    pit_mat = r.get("tree_pit_material", "")
    for s in solves:
        if not mine_run(s):
            continue
        asset = names[int(hashlib.sha1(s.road.name.encode()).hexdigest()[:8], 16) % len(names)]
        # A tree whose station lands on a lamp's is simply dropped by the clearance below, which leaves the
        # avenue with a hole every other tree (measured: 1270 of 2044 on the island). Start the run half a tree
        # spacing past where the LAMPS start and the two interleave instead.
        clear = max(r["tree_end_clear"], r["lamp_end_clear"] + 0.5 * r["tree_spacing"])
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, r["tree_spacing"], clear):
                if 2.0 * w < r["tree_min_footway"] or k <= 0.0 or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                lat = _left(d)
                off = sgn * r["tree_kerb_gap"]
                pos = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k)
                if fur.clear_of(pos, r["tree_clearance"]) and index.clear_of(pos, r["tree_lane_clear"]):
                    if fur.put(table, asset, pos, d, s.road.name):
                        # The planter IS the tree's socket (PLAN.md 3.18m, user-reported with a screenshot: a
                        # tree and a planter standing side by side on one footway "appear at the same time and
                        # is kind of awkward"). A Japanese street tree stands in a 植樹枡 -- an open box at its
                        # foot -- so the two were never two props; the planter had its own spacing rule and the
                        # tree had another, and where both fired they simply stood next to each other. Now the
                        # planter is placed ON the tree and its own run is off (`planter_spacing = 0`), so a
                        # planter only ever appears as what it is.
                        if r.get("tree_planter", True) and "planter" in table.assets:
                            fur.put(table, "planter", pos, d, s.road.name)
                        else:
                            _tree_pit(fur, r, pos, d, pit_mat)


def _tree_pit(fur, r, pos, fwd, material):
    """植樹枡, the square of open ground a street tree stands in (PLAN.md 3.18d, user-reported: "the tree should
    be in a tree trench -- a square space on the street -- otherwise it seems a waste").

    Paint, not a piece: a pit is a hole in the paving, and the cheapest honest way to draw one is the paving's
    own surface replaced by earth over a square. Two triangles per tree (2 430 on the island, merged into the
    piece's one paint object per material), against a modelled kerb ring that would be a second asset and a
    second batch. It is laid on the tree's own square, turned with the footway, at `paint_lift` like every other
    mark -- which is also why it cannot z-fight with the footway it sits on."""
    size = float(r.get("tree_pit", 0.0))
    if size <= 0.0 or not material:
        return
    h = 0.5 * size
    f, l = fwd, _left(fwd)
    z = pos[2] + float(r.get("paint_lift", 0.01))
    cs = [(pos[0] + f[0] * h * sf + l[0] * h * sl, pos[1] + f[1] * h * sf + l[1] * h * sl)
          for sf, sl in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    fur.paint_tris(material, _up_quad(*[(x, y, z) for x, y in cs]))


def _median_walls(fur, table, solves, mine_run):
    """The kit's median panel (`median_wall`, a fence panel fitted to `point_solve.MEDIAN_WALL_HEIGHT`) tiled end to
    end along every `WALL` median, on the island's top: the visible half of the median wall whose collider
    `point_mesh.median_wall` builds. Spaced by the piece's OWN length, so the panels meet; at C1's 180 m corners
    consecutive 1.56 m panels turn ~0.5 deg and the joints stay closed. Placed LAST and never solid, so it keeps no
    lamp or pole away."""
    a = table.assets.get("median_wall")
    if a is None:
        return
    length = (a["hi"][2] - a["lo"][2]) * a["scale"][2]
    r = table.rules
    for s in solves:
        if not mine_run(s) or len(s.samples) < 2 or getattr(s.road, "median_style", None) != pm.MED_WALL:
            continue
        pts = [tuple(sm.pos) for sm in s.samples]
        cum = _lengths(pts)
        n = int(cum[-1] // length)
        start = (cum[-1] - n * length) / 2.0 + length / 2.0
        for k in range(n):
            p, d, i = _at(pts, cum, start + k * length)
            j = min(i + 1, len(pts) - 1)
            mh = min(s.values[i]["rka_med_h"], s.values[j]["rka_med_h"])
            mz = min(s.values[i]["rka_med_z"], s.values[j]["rka_med_z"])
            if mh < r.get("median_wall_min_half", 0.2) or mz <= 0.0:
                continue
            fur.put(table, "median_wall", (p[0], p[1], p[2] + mz), d, s.road.name)


def place(table, solved, lanes_doc, mine_lane, mine_run, mine_pad, mark_mat, ground=None):
    """One piece's furniture. `solved` is `point_edges.solve_all`'s tuple; `lanes_doc` the WHOLE network's lanes and
    junctions (a mouth's connectors may stream with the pad's piece); `mine_*` say what belongs to this piece;
    `mark_mat(lane)` is the paint material of that lane's road."""
    fur = Furniture()
    if table is None:
        return fur
    solves, jsolves, _gsolves, bands = solved
    lanes = {l["id"]: l for l in lanes_doc.get("lanes", ())}
    junctions = {j["id"]: j for j in lanes_doc.get("junctions", ())}
    ordered = [junctions[k] for k in sorted(junctions)]
    _junction_marks(fur, table, lanes, ordered, mine_lane, mark_mat)
    # the signals first: every later solid prop (planter, bollard, lamp) keeps clear of a pole already standing
    _signals(fur, table, lanes, ordered, mine_lane, ground)
    _lane_props(fur, table, dict(sorted(lanes.items())), mine_lane, ground)
    _edge_props(fur, table, solves, jsolves, bands, mine_run, mine_pad, ground)
    _lamps(fur, table, solves, bands, mine_run, ground)
    _street_trees(fur, table, solves, bands, mine_run, ground, lanes)
    _median_walls(fur, table, solves, mine_run)
    return fur


# ------------------------------------------------------------------------------------------- self-test

def self_test():
    # geometry helpers
    pts = [(0.0, 0.0, 0.0), (10.0, 0.0, 1.0), (10.0, 10.0, 1.0)]
    cum = _lengths(pts)
    assert abs(cum[-1] - 20.0) < 1e-9
    p, d, i = _at(pts, cum, 15.0)
    assert abs(p[0] - 10.0) < 1e-9 and abs(p[1] - 5.0) < 1e-9 and d == (0.0, 1.0) and i == 1
    assert _stations(20.0, 5.0, 3.0) == [5.5, 10.5, 15.5]
    assert _stations(5.0, 5.0, 3.0) == []
    # a box faces out: its signed volume is positive
    tris = _box((0.0, 0.0, 0.0), (1.0, 0.0), 1.0, 0.5, 2.0)
    vol = sum((a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
               + a[2] * (b[0] * c[1] - b[1] * c[0])) for a, b, c in tris) / 6.0
    assert abs(vol - 4.0) < 1e-9, vol
    assert all(_up_quad((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))[k][0] is not None for k in range(2))
    q = _up_quad((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))
    a, b, c = q[0]
    assert (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0.0
    assert godot_to_kit((1.0, 2.0, 3.0)) == (1.0, -3.0, 2.0)

    # a synthetic mouth: two arriving lanes heading +X into a junction at x = 50, one lane leaving -X beside them
    table = load()
    assert table is not None, "no furniture table at %s" % TABLE_PATH
    for name, a in table.assets.items():
        assert os.path.exists(a["file"]), a["file"]
    g = lambda p: [p[0], p[2], -p[1]]                          # noqa: E731 -- point_export.godot
    lanes = [{"id": "a_F0", "kind": "through", "lane_width": 4.5, "points": [g((0, -2.25, 0)), g((50, -2.25, 0))],
              "next": ["c1", "c2"]},
             {"id": "a_F1", "kind": "through", "lane_width": 4.5, "points": [g((0, -6.75, 0)), g((50, -6.75, 0))],
              "next": ["c3"]},
             {"id": "a_R0", "kind": "through", "lane_width": 4.5, "points": [g((50, 2.25, 0)), g((0, 2.25, 0))],
              "next": []},
             {"id": "c1", "kind": "connector", "turn": "S", "points": [], "next": []},
             {"id": "c2", "kind": "connector", "turn": "L", "points": [], "next": []},
             {"id": "c3", "kind": "connector", "turn": "R", "points": [], "next": []}]
    doc = {"lanes": lanes, "junctions": [{"id": "j1", "arms": [{"in_lanes": ["a_F0", "a_F1"], "out_lanes": ["a_R0"]}]}]}
    fur = place(table, ([], [], [], []), doc, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    arrows = sorted(p["asset"] for p in fur.placements if p["asset"].startswith("arrow"))
    assert arrows == ["arrow_R", "arrow_SL"], arrows
    for p in fur.placements:
        if p["asset"].startswith("arrow"):
            assert abs(p["pos"][0] - (50.0 - table.rules["arrow_back"])) < 1e-6 and p["fwd"] == (1.0, 0.0)
    assert fur.counts["stop_line"] == 2 and fur.counts["crosswalk"] == 1
    paint = fur.paint["M_LineW"]
    xs = [v[0] for t in paint for v in t]
    ys = [v[1] for t in paint for v in t]
    # the zebra spans the whole carriageway (-9 .. +4.5, less the margin) and stays on the approach side
    assert max(xs) <= 50.0 - table.rules["crosswalk_back"][0] + 1e-6 and min(xs) >= 50.0 - table.rules["stop_back"] - table.rules["stop_width"] - 1e-6
    assert min(ys) >= -9.0 and max(ys) <= 4.5 and max(ys) > 3.0 and min(ys) < -8.0
    for t in paint:
        a, b, c = t
        assert (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0.0, "paint faces down"
    # the stop line covers only the arriving side (y < 0)
    stop = [v for t in paint for v in t if v[0] < 50.0 - table.rules["crosswalk_back"][1] - 1e-6]
    assert stop and max(v[1] for v in stop) <= 1e-6
    # PLAN.md 3.6c: lines stop at the stop line on the arriving side and never cross the zebra
    zones = clear_zones(table, doc)
    assert len(zones) == 2, zones
    sb = table.rules["stop_back"] + table.rules["stop_width"]
    zb = table.rules["crosswalk_back"][1]
    # a lane line between the two arriving lanes (y -4.5) runs 0 -> 50: it must end at the stop line
    kept = clip_outside([(0.0, -4.5, 0.0), (50.0, -4.5, 0.0)], zones)
    assert len(kept) == 1 and abs(kept[0][-1][0] - (50.0 - sb)) < 1e-6, kept
    # the centre line (y 0) also ends at the stop line (it lies on the arriving lanes' edge)
    kept = clip_outside([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)], zones)
    assert abs(kept[0][-1][0] - (50.0 - sb)) < 1e-6, kept
    # a departing-side line (y +2.25, beyond the arriving lanes + margin) stops only at the zebra's far edge
    kept = clip_outside([(0.0, 2.25, 0.0), (50.0, 2.25, 0.0)], zones)
    assert abs(kept[0][-1][0] - (50.0 - zb)) < 1e-6, kept
    # a line wholly inside a zone disappears; a dash straddling the edge is cut at it, keeping its heights
    assert clip_outside([(46.0, -4.5, 1.0), (48.0, -4.5, 1.0)], zones) == []
    kept = clip_outside([(40.0, -4.5, 0.0), (44.0, -4.5, 2.0)], zones)
    assert len(kept) == 1 and abs(kept[0][-1][0] - (50.0 - sb)) < 1e-6 and 0.0 < kept[0][-1][2] < 2.0
    # a line that passes through a zone comes back as two pieces; one far from any mouth is untouched
    kept = clip_outside([(40.0, -4.5, 0.0), (60.0, -4.5, 0.0)], zones)
    assert len(kept) == 2, kept
    assert clip_outside([(0.0, -4.5, 0.0), (20.0, -4.5, 0.0)], zones) == [[(0.0, -4.5, 0.0), (20.0, -4.5, 0.0)]]
    # the control: with no zones nothing is clipped
    assert clip_outside([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)], []) == [[(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)]]
    # an excluded road gets no manhole
    assert excluded({"exclude_roads": ["shrine_touge*"]}, "shrine_touge_2")
    assert not excluded({"exclude_roads": ["shrine_touge*"]}, "chuo_dori")
    # a lane that is not this piece's gets nothing
    none = place(table, ([], [], [], []), doc, lambda l: False, lambda s: False, lambda j: False, lambda l: "M_LineW")
    assert not none.placements and not none.paint
    # a synthetic right-hand arm (the doc above) is refused, not mis-placed
    sig = dict(doc, junctions=[{"id": "j1", "arms": [dict(doc["junctions"][0]["arms"][0], traffic_light=True)]}])
    f = place(table, ([], [], [], []), sig, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    assert f.counts.get("signal_skipped_right_hand") == 1 and not f.counts.get("signal"), f.counts
    # keep-left: two lanes arriving +X on the LEFT (y > 0), one leaving on the right; the kerb lane is y 6.75
    kl = [{"id": "k_F0", "kind": "through", "lane_width": 4.5, "points": [g((0, 2.25, 0)), g((50, 2.25, 0))],
           "next": ["s0"]},
          {"id": "k_F1", "kind": "through", "lane_width": 4.5, "points": [g((0, 6.75, 0)), g((50, 6.75, 0))],
           "next": ["s1", "t1"]},
          {"id": "k_R0", "kind": "through", "lane_width": 4.5, "points": [g((50, -2.25, 0)), g((0, -2.25, 0))],
           "next": []},
          {"id": "s1", "kind": "connector", "turn": "S", "points": [g((50, 6.75, 0)), g((80, 6.75, 0.5))],
           "next": ["far_F1"]},
          {"id": "t1", "kind": "connector", "turn": "L", "points": [g((50, 6.75, 0)), g((60, 20, 0))], "next": []},
          {"id": "s0", "kind": "connector", "turn": "S", "points": [g((50, 2.25, 0)), g((80, 2.25, 0))], "next": []},
          {"id": "far_F1", "kind": "through", "lane_width": 4.5, "points": [g((80, 6.75, 0.5)), g((120, 6.75, 0))],
           "next": []}]
    arms = [{"in_lanes": ["k_F0", "k_F1"], "out_lanes": ["k_R0"]}, {"in_lanes": ["x"]}, {"in_lanes": ["y"]}]
    kd = {"lanes": kl, "junctions": [{"id": "j2", "arms": arms}]}
    f = place(table, ([], [], [], []), kd, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    sigs = [p for p in f.placements if p["asset"] == "signal"]
    assert len(sigs) == 1, f.counts
    want = (80.0 + table.rules["signal_past_mouth"], 6.75 + 2.25 + table.rules["signal_kerb_offset"], 0.5)
    assert all(abs(sigs[0]["pos"][k] - want[k]) < 1e-6 for k in range(2)) and sigs[0]["fwd"] == (1.0, 0.0), sigs
    # a breakable signal (PLAN.md 3.11) has NO static box; its marker carries what BreakableProps needs
    assert not f.collision, len(f.collision)
    b = sigs[0].get("breakable")
    assert b and b["pole_half"] == table.assets["signal"]["collide_pole"][0] and b["mass"] > 0.0, sigs[0]
    # the control: the same signal made unbreakable gets a box round the pole only, not the 5.5 m arm's footprint
    solid = Table.__new__(Table)
    solid.__dict__.update(table.__dict__)
    solid.assets = dict(table.assets, signal={k: v for k, v in table.assets["signal"].items() if k != "breakable"})
    f = place(solid, ([], [], [], []), kd, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    assert not [p for p in f.placements if p.get("breakable")]
    xs = [v[0] for t in f.collision for v in t]
    assert xs and max(xs) - min(xs) < 0.5, xs and (min(xs), max(xs))
    # not signalised when only two arms carry traffic and none is authored
    kd2 = {"lanes": kl, "junctions": [{"id": "j2", "arms": arms[:2]}]}
    f = place(table, ([], [], [], []), kd2, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    assert not f.counts.get("signal"), f.counts
    # the stem of a T (no straight movement): near-side, on the arm's own kerb just past its zebra
    kl3 = [dict(l, next=["t1"]) if l["id"] == "k_F1" else l for l in kl if l["id"] not in ("s0", "s1")]
    kl3 = [dict(l, next=[]) if l["id"] == "k_F0" else l for l in kl3]
    f = place(table, ([], [], [], []), {"lanes": kl3, "junctions": [{"id": "j3", "arms": arms}]},
              lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    sigs = [p for p in f.placements if p["asset"] == "signal"]
    near = 50.0 - (table.rules["crosswalk_back"][0] - table.rules["signal_near_inside"])
    assert len(sigs) == 1 and abs(sigs[0]["pos"][0] - near) < 1e-6, sigs
    assert abs(sigs[0]["pos"][1] - (6.75 + 2.25 + table.rules["signal_kerb_offset"])) < 1e-6, sigs
    row = Furniture()
    for k in range(5):
        pos = (k * table.rules["bollard_spacing"], 0.0, 0.0)
        if row.clear_of(pos, table.rules["pole_clearance"], poles_only=True):
            row.put(table, "bollard", pos, (1.0, 0.0))
    assert row.counts.get("bollard") == 5, row.counts
    assert not row.clear_of((0.5, 0.0, 0.0), table.rules["pole_clearance"])
    print("point_furniture self-test OK")


if __name__ == "__main__":
    self_test()
