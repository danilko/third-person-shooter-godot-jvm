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
import re
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
WIRE_OBJECT = "FURN__wires"
#: the median hedges (`_median_hedge`): swept into the piece, no collision (the island they stand on is kerbed)
HEDGE_OBJECT = "FURN__hedge"
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


#: The material of an expressway sign's FACE: the runtime draws the text on it (world.TrafficSignals).
SIGN_FACE_MATERIAL = "MI_ExpwyGreen"


def _material_bounds(path, material):
    """(min, max) of the glTF primitives wearing `material` (from the accessors), or None: an expressway sign's PANEL
    is measured off its own model, so an artist may move or resize it in the library with nothing else to update."""
    with open(path) as fh:
        doc = json.load(fh)
    names = [m.get("name", "") for m in doc.get("materials", ())]
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for m in doc.get("meshes", ()):
        for p in m.get("primitives", ()):
            if p.get("material") is None or names[p["material"]].split(".")[0] != material:
                continue
            a = doc["accessors"][p["attributes"]["POSITION"]]
            lo = [min(x, y) for x, y in zip(lo, a["min"])]
            hi = [max(x, y) for x, y in zip(hi, a["max"])]
    return None if lo[0] == math.inf else (lo, hi)


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
            if a.get("sign_panel"):
                pb = _material_bounds(fs, SIGN_FACE_MATERIAL)
                if pb is not None:
                    plo, phi = pb
                    # the face is the panel's +Z side (toward the drivers), in the Godot piece frame
                    self.assets[name]["panel"] = {"centre": [0.5 * (plo[0] + phi[0]), 0.5 * (plo[1] + phi[1]), phi[2]],
                                                  "size": [phi[0] - plo[0], phi[1] - plo[1]]}

    def files(self):
        """Every file the placements depend on: the table and each piece (the digest salts them)."""
        return [self.path, GLYPH_PATH] + sorted({a["file"] for a in self.assets.values()})


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

    def __init__(self, keep_out=()):
        self.paint = {}
        #: `{material: [tri]}` of the overhead wires strung between the 電柱 (`_utility_poles`): the piece's own mesh
        self.wires = {}
        #: `{material: [tri]}` of the hedge boxes on raised medians (`_median_hedge`)
        self.hedge = {}
        self.collision = []
        self.placements = []
        self.counts = {}
        # KEEP-OUT boxes (user, 2026-10-04: "a tree in front of a parking exit blocks part of it"): the car-park
        # entrances `island_buildings.py write` records, as (cx, cy, ux, uy, half_across, half_deep) in the kit frame,
        # u the unit direction INTO the lot. Nothing that stands up is placed in one; a signal or a sign is a lane's
        # (it stands where its junction needs it), and paint, a drain and a manhole are flat.
        self.keep_out = list(keep_out or ())

    def blocked(self, asset, pos):
        if not self.keep_out or "signal" in asset or "sign" in asset or asset in ("drain", "manhole"):
            return False   # a drain or a manhole is a flat grate a car drives over
        for cx, cy, ux, uy, ha, hd in self.keep_out:
            dx, dy = pos[0] - cx, pos[1] - cy
            if abs(dx * ux + dy * uy) <= hd and abs(-dx * uy + dy * ux) <= ha:
                return True
        return False

    def put(self, table, asset, pos, fwd, road=None):
        a = table.assets.get(asset)
        if a is None or (road is not None and excluded(a, road)):
            return False
        if self.blocked(asset, pos):
            self.counts["keep_out_skipped"] = self.counts.get("keep_out_skipped", 0) + 1
            return False
        lift = float(a.get("lift", 0.0)) - a["lo"][1] * a["scale"][1]
        self.placements.append({"asset": asset, "path": a["res"], "pos": (pos[0], pos[1], pos[2] + lift),
                                "fwd": fwd, "scale": list(a["scale"]), "road": road or ""})
        if a.get("rail"):
            # a RAIL (ガードレール): a long thin collider, breakable like a pole, and NOT "solid" to the spacing rules --
            # it runs the kerb's whole length, and a lamp, a pole and a tree stand behind it
            half, height, half_len = [float(x) for x in a["rail"]]
            self.counts[asset] = self.counts.get(asset, 0) + 1
            b = a.get("breakable")
            if b:
                self.placements[-1]["breakable"] = {"pole_half": half, "pole_height": height, "pole_len": half_len,
                                                    "mass": float(b.get("mass", 60.0)),
                                                    "break_speed": float(b.get("break_speed", 5.0)),
                                                    "respawn": float(b.get("respawn", 60.0))}
            else:
                self.collision += _box((pos[0], pos[1], pos[2]), fwd, half_len, half, height)
            return True
        if a.get("collide") or a.get("collide_pole"):
            self.placements[-1]["solid"] = True
        if a.get("collide_pole"):
            self.placements[-1]["pole"] = True
        self.counts[asset] = self.counts.get(asset, 0) + 1
        if a.get("breakable") and (a.get("collide_pole") or a.get("collide")):
            # a knock-down pole (PLAN.md 3.11) has no static box: its batch's BreakableProps node builds a collider
            # per pole at runtime and takes it away when a car knocks the pole down. A breakable BOX prop (a corner
            # bollard) is sized from its own footprint and is not a "pole" to the spacing rules, so a row of them
            # keeps its 1.8 m pitch.
            if a.get("collide_pole"):
                half, height = a["collide_pole"]
            else:
                half = 0.5 * max((a["hi"][0] - a["lo"][0]) * a["scale"][0], (a["hi"][2] - a["lo"][2]) * a["scale"][2])
                height = (a["hi"][1] - a["lo"][1]) * a["scale"][1]
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
    """A zebra needs room for itself -- and `crosswalk_min_lane` of lane behind it: a link that short joins two
    junctions that are really one (user, 2026-10-11, with a picture: a T 72 m from a ramp terminal on a six-lane
    road left a 10 m link carrying TWO zebras back to back and four pedestrian heads within 4 m). People cross at
    the outer arms of the pair."""
    need = max(table.rules["crosswalk_back"][1], float(table.rules.get("crosswalk_min_lane", 0.0)))
    return all(row["length"] >= need for row in arm["rows"])


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


GLYPH_PATH = os.path.join(REPO, "assets", "world_source", "kits", "road_kit", "paint_glyphs.json")
_GLYPHS = {}


def glyphs(path=GLYPH_PATH):
    """The characters a legend can be painted in (tools/build_paint_glyphs.py): `{char: {w, h, tris}}`, em about
    the ink's centre. Empty when the file is missing -- a legend is then simply not painted."""
    if path not in _GLYPHS:
        doc = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh).get("glyphs", {})
        _GLYPHS[path] = doc
    return _GLYPHS[path]


def legend(text, cell_w, cell_len, gap, stacked, table=None):
    """A legend's triangles in ITS OWN frame, `[((right, ahead), (right, ahead), (right, ahead)), ...]` and its
    length along the road: `right` to the reader's right about the legend's centre line, `ahead` the way they
    travel, 0 at the edge they reach first. `stacked` (止まれ) puts one character after another along the lane,
    the FIRST one furthest ahead, so it reads top to bottom from the driver's seat; otherwise (a limit's numerals)
    side by side, left to right. Every character is scaled by the same factors -- the legend's widest ink to
    `cell_w`, its tallest to `cell_len` -- so a road legend is the font's shape stretched along the road, as painted.
    `(None, 0.0)` when a character is not in the glyph file."""
    table_g = glyphs() if table is None else table
    chars = [table_g.get(c) for c in text]
    if not chars or any(c is None for c in chars):
        return None, 0.0
    sx = cell_w / max(c["w"] for c in chars)
    sy = cell_len / max(c["h"] for c in chars)
    n = len(chars)
    total = n * cell_len + (n - 1) * gap if stacked else cell_len
    tris = []
    for i, c in enumerate(chars):
        if stacked:
            cx, cy = 0.0, total - 0.5 * cell_len - i * (cell_len + gap)
        else:
            cx, cy = (i - 0.5 * (n - 1)) * (cell_w + gap), 0.5 * cell_len
        t = c["tris"]
        for k in range(0, len(t) - 2, 3):
            tris.append(tuple((cx + t[k + j][0] * sx, cy + t[k + j][1] * sy) for j in range(3)))
    return tris, total


def _up_tri(a, b, c):
    n = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (a, b, c) if n > 0.0 else (a, c, b)


#: 止まれ is for a street meeting a street: a ramp's or an expressway's mouth merges, it does not stop
NO_STOP_TEXT_CLASSES = ("expressway", "ramp", "rail")
#: how far from straight across (degrees) two arms may be and still be one road through the junction
THROUGH_BEND_MAX = 40.0


def yield_arms(table, lanes, junctions):
    """The arms that must STOP at an unsignalised junction, as a set of `id(arm)` (PLAN.md T4; the Japanese rule
    `_signalised` already names: "the minor approach has a stop line and 止まれ, and that is all"). At a junction
    of three or more arms with no signals, ONE road has priority -- the arm carrying the highest limit and the
    most lanes, with the arm most nearly opposite it, or, when several arms tie, the two of them most nearly
    opposite (then by name, so the answer does not depend on the order of the file) -- and every other arm stops.
    So the stem of a T stops, and at a cross of two equal streets one of them does."""
    out = set()
    for j in junctions:
        arms = [a for a in j.get("arms", ()) if any(i in lanes for i in tuple(a.get("in_lanes", ()))
                                                        + tuple(a.get("out_lanes", ())))]
        if len(arms) < 3 or _signalised(table, j, lanes):
            continue

        def mine_lanes(a):
            return [lanes[i] for i in tuple(a.get("in_lanes", ())) + tuple(a.get("out_lanes", ())) if i in lanes]
        if any(l.get("road_class") in NO_STOP_TEXT_CLASSES for a in arms for l in mine_lanes(a)):
            continue

        def rank(a):
            ls = mine_lanes(a)
            return (max(float(l.get("speed_limit", 0.0)) for l in ls), len(ls))

        def bend(a, b):
            d = abs(float(a.get("bearing", 0.0)) - float(b.get("bearing", 0.0))) % 360.0
            return abs(180.0 - (360.0 - d if d > 180.0 else d))
        best = max(rank(a) for a in arms)
        top = [a for a in arms if rank(a) == best]
        if len(top) >= 2:
            pairs = [(round(bend(a, b), 1), tuple(sorted((str(a.get("road")), str(b.get("road"))))), i, k)
                     for i, a in enumerate(top) for k, b in enumerate(top) if i < k]
            _d, _n, i, k = min(pairs)
            priority = [top[i], top[k]]
        else:
            priority = [top[0]]
            rest = [a for a in arms if a is not top[0]]
            other = min(rest, key=lambda a: (round(bend(top[0], a), 1), str(a.get("road"))))
            if bend(top[0], other) <= THROUGH_BEND_MAX:
                priority.append(other)
        for a in arms:
            if not any(a is q for q in priority) and a.get("in_lanes"):
                out.add(id(a))
    return out


def _junction_marks(fur, table, lanes, junctions, mine, mark_mat):
    r = table.rules
    lift = float(r["paint_lift"])
    stops = yield_arms(table, lanes, junctions) if r.get("stop_text") else set()
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
                    # ---- 止まれ behind it, on an arm that must stop (yield_arms)
                    if id(arm["arm"]) in stops and row["length"] >= r["stop_text_min_lane"]:
                        cw = min(float(r["stop_text_w"]), 2.0 * row["half"] - 2.0 * float(r["stop_text_margin"]))
                        tris, total = legend(str(r["stop_text"]), cw, float(r["stop_text_len"]),
                                             float(r["stop_text_gap"]), True)
                        b0 = sb + sw + float(r["stop_text_back"])
                        if tris and cw > 0.5 and row["length"] >= b0 + total:
                            out = []
                            for tri in tris:
                                vs = []
                                for right, ahead in tri:
                                    back = b0 + total - ahead
                                    x, y = plan(row["lat"] - right, back)
                                    vs.append((x, y, row["sample"](back)[2] + lift))
                                out.append(_up_tri(*vs))
                            fur.paint_tris(mark_mat(row["lane"]), out)
                            fur.counts["stop_text"] = fur.counts.get("stop_text", 0) + 1
                            continue                 # no arrow under the legend
                turns = frozenset(lanes[n].get("turn", "") for n in row["lane"].get("next", ())
                                  if n in lanes and lanes[n].get("kind") == "connector" and lanes[n].get("turn"))
                asset = ARROW_FOR.get(turns)
                if asset and row["length"] >= r["arrow_min_lane"]:
                    pts = _lane_kit(row["lane"])
                    cum = _lengths(pts)
                    p, d, _i = _at(pts, cum, cum[-1] - r["arrow_back"])
                    fur.put(table, asset, p, d)


def _speed_text(fur, table, lanes, mine, mark_mat):
    """THE LIMIT, PAINTED IN THE LANE (PLAN.md T4): its numerals in km/h (user, 2026-10-12), `speed_text_from` m
    after a through lane begins -- past the junction and the far arm's zebra -- and again every `speed_text_every`
    m while the lane has `speed_text_end_clear` left before its own stop line, arrow and 止まれ. In every lane of a
    carriageway, as Japan paints it. `speed_text_material` (yellow: a regulation, like the no-overtaking line) or
    the road's own white when that is empty. Off with `speed_text_len` 0."""
    r = table.rules
    cell_len = float(r.get("speed_text_len", 0.0))
    if cell_len <= 0.0:
        return
    lift = float(r["paint_lift"])
    for lid in sorted(lanes):
        l = lanes[lid]
        limit = float(l.get("speed_limit", 0.0))
        if l.get("kind") != "through" or limit <= 0.0 or l.get("road_class") == "rail" or not mine(l):
            continue
        pts = _lane_kit(l)
        if len(pts) < 2:
            continue
        cum = _lengths(pts)
        if cum[-1] < r["speed_text_min_lane"]:
            continue
        text = "%d" % round(limit)
        n = len(text)
        gap = float(r["speed_text_gap"])
        room = float(l.get("lane_width", 3.5)) - 2.0 * float(r["speed_text_margin"])
        cw = min(float(r["speed_text_w"]), (room - (n - 1) * gap) / n)
        tris, total = legend(text, cw, cell_len, gap, False)
        if not tris or cw < 0.3:
            continue
        mat = r.get("speed_text_material") or mark_mat(l)
        s = float(r["speed_text_from"])
        while s + total <= cum[-1] - r["speed_text_end_clear"]:
            p, d, _i = _at(pts, cum, s + 0.5 * total)
            left = _left(d)
            out = []
            for tri in tris:
                vs = []
                for right, ahead in tri:
                    a = ahead - 0.5 * total
                    vs.append((p[0] + d[0] * a - left[0] * right, p[1] + d[1] * a - left[1] * right,
                               _at(pts, cum, s + ahead)[0][2] + lift))
                out.append(_up_tri(*vs))
            fur.paint_tris(mat, out)
            fur.counts["speed_text"] = fur.counts.get("speed_text", 0) + 1
            if r["speed_text_every"] <= 0.0:
                break
            s += float(r["speed_text_every"])


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


#: m past a vehicle entry's ramps kept free of street furniture (a car turning in sweeps wider than the gap)
ENTRY_CLEAR = 1.5


def _edge_samples(pts, walk, kerb, wall, spacing, clear, phase=None):
    """Stations along one edge run: (point, plan direction, walk half width, kerb height), skipping any whose
    segment carries a barrier or no kerb."""
    pts = [tuple(p) for p in pts]
    cum = _lengths(pts)
    out = []
    # a VEHICLE ENTRY (`point_edges.drop_entries`) is kept clear: no drain, planter, tree, lamp or bollard on the dropped
    # kerb, its ramps, or ENTRY_CLEAR past them. Read off the kerb itself -- the dropped vertices carry the dropped-kerb
    # value marks (`point_edges.EntryKerb`) -- so every placer obeys it with nothing else passed in
    drops = [cum[v] for v, k in enumerate(kerb) if isinstance(k, ped.EntryKerb)]
    keep_out = ped.ENTRY_RAMP + ENTRY_CLEAR
    for s in _stations(cum[-1], spacing, clear, phase):
        if any(abs(s - c) <= keep_out for c in drops):
            continue
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


def _edge_props(fur, table, solves, jsolves, bands, mine_run, mine_pad, ground, index=None):
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
                                poles_only=True) and (index is None or index.clear_of(
                                    pos, r.get("prop_lane_clear", 0.0) + half, asset_height(table, "planter"))):
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
                # A turn connector may cut the corner a bollard stands on (`turn_off_pad`), and a car turning
                # there pins its hull against a solid post and never gets free -- measured on the rebuilt island,
                # every traffic car reclaimed as `stalled` (34 in one run) stood beside corner bollards with its
                # throttle on. So a bollard keeps clear of every lane, the rule a tree already had.
                if fur.clear_of(pos, r.get("pole_clearance", 0.0), poles_only=True) and (
                        index is None or index.clear_of(pos, r.get("prop_lane_clear", 0.0), asset_height(table, "bollard"))):
                    fur.put(table, "bollard", pos, d)


def _signalised(table, junction, lanes=None):
    """A junction carries signals when any mouth is authored `traffic_light`, or -- `signal_all_junctions` -- when
    at least `signal_min_arms` of its arms have traffic arriving (a two-arm bend or a dead-end loop is not).
    THE JAPANESE RULE (user, 2026-09-26: "traffic lights to japan flavour"; `signal_needs_major`): a crossing of two
    narrow streets is NOT signalised in Japan -- the minor approach has a stop line and 止まれ, and that is all --
    so a signal also needs one arm that is a major road: `signal_major_lanes` or more lanes arriving on it, or an
    arterial. Asked of the lanes (`lanes`, the lanekit's), so without them the rule stands down."""
    arms = junction.get("arms", ())
    if any(a.get("traffic_light") for a in arms):
        return True
    r = table.rules
    if not (bool(r.get("signal_all_junctions")) and sum(1 for a in arms if a.get("in_lanes")) >= r["signal_min_arms"]):
        return False
    if not r.get("signal_needs_major") or lanes is None:
        return True
    for a in arms:
        ins = [lanes[i] for i in a.get("in_lanes", ()) if i in lanes]
        if len(ins) >= int(r.get("signal_major_lanes", 2)) or any(l.get("road_class") == "arterial" for l in ins):
            return True
    return False


#: How far a pole may be stepped OUTBOARD to get out of a lane before it is dropped instead. A signal must
#: still be readable from its approach and a lamp must still reach the road, so this is a nudge, not a search.
POLE_PUSH_MAX = 2.5
POLE_PUSH_STEP = 0.25


def _pole_half(table, asset):
    """The shaft's own radius (`collide_pole`), which is what a car actually meets."""
    c = (table.assets.get(asset, {}) or {}).get("collide_pole") or [0.2]
    return float(c[0])


def _out_of_lane(index, table, rules, asset, pos, out, push=True):
    """`pos` moved OUTBOARD along `out` until the pole is clear of every lane, or None when it cannot be.

    A functional pole -- a traffic signal, a street lamp -- is placed by its own rule (so far in from the kerb,
    so far past the far mouth) and that rule is about the KERB of one road. It says nothing about a turn
    connector swinging wide over the footway, or about a second road running alongside; `_LaneIndex` is the one
    owner of "is this spot in a carriageway", and until now only the trees and the edge props asked it, so a
    signal or a lamp could stand where a car drives (measured on the island: 12 lanes, 2 of them through lanes).

    The margin is the SHAFT's own radius plus `pole_lane_clear`, not the generous `prop_lane_clear` a bollard
    keeps: the question here is whether a car meets the pole, and a Japanese signal stands AT the kerb by design.
    """
    if index is None:
        return pos
    margin = _pole_half(table, asset) + float(rules.get("pole_lane_clear", 0.15))
    tall = asset_height(table, asset)
    if index.clear_of(pos, margin, tall):
        return pos
    if not push:
        return None
    d = POLE_PUSH_STEP
    while d <= POLE_PUSH_MAX + 1e-9:
        cand = (pos[0] + out[0] * d, pos[1] + out[1] * d, pos[2])
        if index.clear_of(cand, margin, tall):
            return cand
        d += POLE_PUSH_STEP
    return None


def _signals(fur, table, lanes, junctions, mine, ground, index=None):
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
        if not _signalised(table, arm["junction"], lanes):
            continue
        ins = [w for w in arm["rows"] if w["arriving"]]
        outs = [w for w in arm["rows"] if not w["arriving"]]
        # which side the kerb is on: the side of the arriving lanes AWAY from the departing ones
        ksign = 1.0
        if outs and sum(w["lat"] for w in ins) / len(ins) < sum(w["lat"] for w in outs) / len(outs):
            ksign = -1.0
        asset = "signal"
        if ksign < 0.0:
            # right-hand traffic: the pole stands on the RIGHT kerb and the mirrored piece's arm reaches left over
            # the lanes (`signal_r`, tools/mirror_piece.py). Without the twin the arm would hang over the verge.
            asset = "signal_r"
            if asset not in table.assets:
                fur.counts["signal_skipped_right_hand"] = fur.counts.get("signal_skipped_right_hand", 0) + 1
                continue
        kerb = (max if ksign > 0.0 else min)(ins, key=lambda w: w["lat"])
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
            side = (ksign * side[0], ksign * side[1])            # the kerb this traffic keeps to
            pos = (end[0] + d[0] * r["signal_past_mouth"] + side[0] * (half + off),
                   end[1] + d[1] * r["signal_past_mouth"] + side[1] * (half + off), end[2])
            fwd = d
            out = side
        else:
            # no straight-ahead movement (the stem of a T, a Y): there is no far side to stand on, so the signal is
            # NEAR-side -- on this arm's own kerb, just junction-side of its zebra, as Japan does where the far
            # side is not visible or not there
            fwd, left, anchor = arm["fwd"], arm["left"], arm["anchor"]
            back = r["crosswalk_back"][0] - r["signal_near_inside"]
            lat = kerb["lat"] + ksign * (kerb["half"] + off)
            z = kerb["sample"](max(0.0, back))[2]
            pos = (anchor[0] + left[0] * lat - fwd[0] * back, anchor[1] + left[1] * lat - fwd[1] * back, z)
            out = (ksign * left[0], ksign * left[1])
        moved = _out_of_lane(index, table, r, asset, pos, out)
        if moved is None:
            fur.counts["signal_in_lane"] = fur.counts.get("signal_in_lane", 0) + 1
            continue
        if moved[0] != pos[0] or moved[1] != pos[1]:
            fur.counts["signal_moved_clear"] = fur.counts.get("signal_moved_clear", 0) + 1
        pos = moved
        if not _grounded(ground, pos, r["max_above_ground"]):
            continue
        if fur.put(table, asset, pos, fwd, lane.get("road_name", "")):
            fur.placements[-1].update({"junction": arm["junction"]["id"], "arm": _arm_index(arm)})


def _arm_index(arm):
    """The arm's index in its junction's `arms` list (the lanekit's order: the runtime's key)."""
    return next(k for k, a in enumerate(arm["junction"].get("arms", ())) if a is arm["arm"])


#: The vehicle signal pieces. ONE since 2026-09-27: the vehicle pole carries no pedestrian head (see
#: `_ped_signals`), so there are no corner-pole variants.
SIGNAL_ASSETS = ("signal", "signal_r")


def _clear_of_signal(fur, table, pos, back):
    """`pos` stepped back along `back` (a unit vector away from the junction) until no vehicle signal pole stands within
    `ped_signal_pole_clear` of it (at most 3 m), so a crosswalk end's own pole never stands in the vehicle pole."""
    clear = float(table.rules.get("ped_signal_pole_clear", 1.2))
    for k in range(13):
        q = (pos[0] + back[0] * 0.25 * k, pos[1] + back[1] * 0.25 * k, pos[2])
        if not any(p.get("asset") in SIGNAL_ASSETS and math.hypot(p["pos"][0] - q[0], p["pos"][1] - q[1]) < clear
                   for p in fur.placements):
            return q
    return None


def _ped_signals(fur, table, lanes, junctions, mine, ground, index=None):
    """歩行者用信号 (user, 2026-09-26: "enable both pedestrian + traffic light"): at a signalised junction, a
    pedestrian signal at EACH END of every zebra, on the footway `signal_kerb_offset` out from the kerb and level with
    the zebra's middle, its head facing across the crosswalk at the far end's pedestrians. ALWAYS its own pole
    (`PedSignal_JP`), ONE head per crosswalk end and direction (user, 2026-09-27: "avoid 2 formats / 2 pedestrian
    lights for the same direction"): Japan mounts a pedestrian head on the vehicle-signal pole only where that pole
    stands AT the crosswalk end, and ours stand at the far-side corner, so the vehicle pole carries none. A pole that
    would stand on a vehicle pole steps back from the junction (`_clear_of_signal`). Tagged with the junction and the
    arm whose crosswalk it serves."""
    if "ped_signal" not in table.assets:
        return
    r = table.rules
    off = float(r["signal_kerb_offset"])
    b0, b1 = r["crosswalk_back"]
    back = 0.5 * (b0 + b1)
    for arm in _arms(lanes, junctions):
        if not _signalised(table, arm["junction"], lanes) or not _has_zebra(table, arm) or not mine(arm["ins"][0]):
            continue
        fwd, left, anchor, rows = arm["fwd"], arm["left"], arm["anchor"], arm["rows"]
        lo = min(w["lat"] - w["half"] for w in rows) - off
        hi = max(w["lat"] + w["half"] for w in rows) + off
        near = min(rows, key=lambda w: abs(w["lat"]))
        z = near["sample"](min(back, near["length"]))[2]
        for lat, face in ((lo, (left[0], left[1])), (hi, (-left[0], -left[1]))):
            pos = (anchor[0] + left[0] * lat - fwd[0] * back, anchor[1] + left[1] * lat - fwd[1] * back, z)
            pos = _clear_of_signal(fur, table, pos, (-fwd[0], -fwd[1]))
            if pos is None:
                fur.counts["ped_signal_on_signal"] = fur.counts.get("ped_signal_on_signal", 0) + 1
                continue
            out = (-face[0], -face[1])
            moved = _out_of_lane(index, table, r, "ped_signal", pos, out)
            if moved is None:
                fur.counts["ped_signal_in_lane"] = fur.counts.get("ped_signal_in_lane", 0) + 1
                continue
            # the piece's head faces -fwd (Godot +Z): toward the far end is `face`, so fwd is its opposite
            if fur.put(table, "ped_signal", moved, out, arm["ins"][0].get("road_name", "")):
                fur.placements[-1].update({"junction": arm["junction"]["id"], "arm": _arm_index(arm)})


def _lamps(fur, table, solves, bands, mine_run, ground, index=None):
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
                # A median lamp cannot be nudged -- its place IS the median -- so one that lands in a lane
                # (a lamp correct on its own road standing in a second road that runs alongside) is dropped.
                if _out_of_lane(index, table, r, "lamp_twin", pos, (0.0, 0.0), push=False) is None:
                    fur.counts["lamp_twin_in_lane"] = fur.counts.get("lamp_twin_in_lane", 0) + 1
                    continue
                if fur.clear_of(pos, r["pole_clearance"]) and fur.put(table, "lamp_twin", pos, d, road):
                    on_median += 1
        if (on_median and not r.get("lamp_kerb_with_median")) or "lamp" not in table.assets:
            continue
        # a street lit from its 電柱 (a 防犯灯 on every pole, `denchu_kind`) stands no separate lamp on its kerbs
        on_poles = denchu_kind(table, s.road) == "lamp"
        open_edge = getattr(s.road, "barrier_style", "") == "RAIL"
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            spacing = r["lamp_spacing"]
            for p, d, w, k in (() if on_poles else _edge_samples(pts, walk, kerb, wall, spacing, r["lamp_end_clear"],
                                                                 0.5 * spacing if sgn > 0 else 0.0)):
                # an open-edged RAIL road (the coast road: no kerb, a guardrail) is lit like a kerbed one
                if (k <= 0.0 and not open_edge) or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                lat = _left(d)
                o = sgn * r["lamp_inset"]
                pos = (p[0] + lat[0] * o, p[1] + lat[1] * o, p[2] + (k if w > 0.0 else 0.0))
                pos = _out_of_lane(index, table, r, "lamp", pos, (sgn * lat[0], sgn * lat[1]))
                if pos is None:
                    fur.counts["lamp_in_lane"] = fur.counts.get("lamp_in_lane", 0) + 1
                    continue
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
                pos = _out_of_lane(index, table, r, "lamp", pos, (sgn * lat[0], sgn * lat[1]))
                if pos is None:
                    fur.counts["lamp_in_lane"] = fur.counts.get("lamp_in_lane", 0) + 1
                    continue
                if fur.clear_of(pos, r["pole_clearance"]):
                    fur.put(table, "lamp", pos, (-sgn * lat[0], -sgn * lat[1]), road)


# ------------------------------------------------------------------------------------------- 電柱 and wires

#: The four pole pieces: (lit from the pole?, carries a transformer?) -> asset.
DENCHU_ASSETS = {(False, False): "denchu", (False, True): "denchu_tr",
                 (True, False): "denchu_lamp", (True, True): "denchu_tr_lamp"}


def denchu_kind(table, road):
    """What 電柱 a road carries (PLAN.md T1): None, "lamp" (a block street: a 防犯灯 on every pole, and no separate
    street lamp) or "plain" (a wider road that keeps its own lamps and trees).

    The Japanese rule this follows: overhead distribution lines run down ordinary streets and two-lane-each-way
    roads; a trunk road and an expressway are undergrounded (無電柱化 starts with the widest roads). So it is the
    LANE COUNT, `denchu_max_lanes` each way, and never the road's class name."""
    r = table.rules
    if float(r.get("denchu_spacing", 0.0)) <= 0.0 or "denchu" not in table.assets:
        return None
    if getattr(road, "road_class", "") in ("expressway", "ramp", "rail"):
        return None
    if not getattr(road, "ped_access", True) and getattr(road, "barrier_style", "") != "RAIL":
        return None                                              # fenced with a wall: no verge to stand a pole on
    if excluded(table.assets["denchu"], road.name):
        return None
    base = road.base
    lanes = max(int(base.lanes_fwd), int(base.lanes_bwd))
    if lanes > int(r.get("denchu_max_lanes", 2)):
        return None
    walk = max(float(base.left_walk_width), float(base.right_walk_width))
    lit = lanes <= int(r.get("denchu_lamp_max_lanes", 1)) and walk > 0.0 and "denchu_lamp" in table.assets
    return "lamp" if lit else "plain"


def denchu_side(name):
    """Which kerb a road's FIRST line of poles stands on (+1 = the left of its direction): one side per ROAD, by a
    hash of its name with any `__n` split suffix dropped, so a road cut into several records keeps its side."""
    return 1.0 if int(hashlib.sha1(name.split("__")[0].encode()).hexdigest()[:8], 16) % 2 else -1.0


def denchu_sides(table, road):
    """The kerbs a road's poles stand on, first line first. BOTH in town (user, 2026-10-11: "thought it should be
    both sides") -- the second line is staggered half a pitch from the first; ONE on the roads
    `denchu_one_side_roads` names (a mountain road: the line follows one verge)."""
    first = denchu_side(road.name)
    r = table.rules
    if not r.get("denchu_both_sides", False) or any(
            fnmatch.fnmatchcase(road.name, g) for g in r.get("denchu_one_side_roads", ())):
        return (first,)
    return (first, -first)


def denchu_stations(length, kind, rules, stagger=False):
    """Arc lengths of the poles along one kerb run; `stagger` is the SECOND kerb's line, half a pitch on.

    "lamp": every `denchu_spacing`, CENTRED in the run, so the first and the last pole are equally near the two
    junctions and the span over each junction is as short as it can be.
    "plain": the road has lamps every `lamp_spacing` on this kerb or the other (half a pitch apart) and trees on
    the half pitch between, all counted from `lamp_end_clear` -- so a pole a QUARTER of the lamp pitch on is
    midway between a lamp and a tree, on either kerb. Poles go on that lattice every lamp pitch, and one more on
    the last free lattice point before the run's end, which closes the gap to the junction."""
    clear = float(rules["denchu_end_clear"])
    if kind == "lamp":
        spacing = float(rules["denchu_spacing"])
        if length < 2.0 * clear:
            return []
        n = int((length - 2.0 * clear) // spacing) + 1
        first = 0.5 * (length - (n - 1) * spacing)
        if stagger and n > 1:
            return [first + (k + 0.5) * spacing for k in range(n - 1)]
        return [first + k * spacing for k in range(n)]
    pitch = float(rules["lamp_spacing"])
    first = float(rules["lamp_end_clear"]) + (0.75 if stagger else 0.25) * pitch
    out, st = [], first
    while st <= length - clear + 1e-9:
        out.append(st)
        st += pitch
    if out and out[-1] + 0.5 * pitch <= length - clear + 1e-9:
        out.append(out[-1] + 0.5 * pitch)
    return out


def _denchu_spot(fur, table, index, ground, pts, cum, walk, kerb, wall, drops, sgn, st, open_edge=False):
    """Where a pole at arc length `st` of a kerb run stands -- (pos, along) -- or None when it may not: on a
    barrier, at no kerb, over a drop, in a vehicle entry, a car-park keep-out or a lane, or on another solid."""
    r = table.rules
    if st < 0.0 or st > cum[-1] or any(abs(st - c) <= ped.ENTRY_RAMP + ENTRY_CLEAR for c in drops):
        return None
    p, d, i = _at(pts, cum, st)
    j = min(i + 1, len(pts) - 1)
    if max(float(wall[i]), float(wall[j])) > 0.0:
        return None
    k = min(float(kerb[i]), float(kerb[j]))
    w = min(float(walk[i]), float(walk[j]))
    if (k <= 0.0 and not open_edge) or not _grounded(ground, p, r["max_above_ground"]):
        return None
    lat = _left(d)
    # on an open edge the pole stands BEHIND the guardrail, not at a kerb
    o = sgn * float(r["denchu_inset"] if k > 0.0 else r.get("denchu_inset_open", 1.0))
    pos = (p[0] + lat[0] * o, p[1] + lat[1] * o, p[2] + (k if w > 0.0 else 0.0))
    pos = _out_of_lane(index, table, r, "denchu", pos, (sgn * lat[0], sgn * lat[1]))
    if pos is None or fur.blocked("denchu", pos) or not fur.clear_of(pos, r["pole_clearance"]):
        return None
    return pos, d


def wire_span(a, b, rules):
    """The triangles of every wire in `denchu_wires` between two poles `a`, `b` -- each `(foot, fwd)` in the kit
    frame, `fwd` the piece's forward, so its +X (the road side, where the 腕金 reaches) is `(fwd.y, -fwd.x)`.

    A wire is a three-sided tube (it must read from below, from the side and end on), hanging in a parabola whose
    sag grows with the square of the span -- the catenary of a wire at one tension. Outward-facing triangles."""
    tris = []
    span = math.hypot(b[0][0] - a[0][0], b[0][1] - a[0][1])
    if span < 1.0:
        return tris
    segs = max(3, min(8, int(math.ceil(span / 6.0))))
    k_sag = (span / float(rules.get("denchu_sag_span", 30.0))) ** 2
    ax, ay = (b[0][0] - a[0][0]) / span, (b[0][1] - a[0][1]) / span
    sx, sy = -ay, ax                                              # horizontal, across the wire
    for w in rules.get("denchu_wires", ()):
        ends = []
        for foot, f in (a, b):
            ends.append((foot[0] + f[1] * w["x"], foot[1] - f[0] * w["x"], foot[2] + w["z"]))
        t = float(w["t"])
        rings = []
        for n in range(segs + 1):
            u = n / float(segs)
            c = [ends[0][q] + (ends[1][q] - ends[0][q]) * u for q in range(3)]
            c[2] -= 4.0 * float(w["sag"]) * k_sag * u * (1.0 - u)
            rings.append(((c[0], c[1], c[2] + 0.58 * t),
                          (c[0] + sx * 0.5 * t, c[1] + sy * 0.5 * t, c[2] - 0.29 * t),
                          (c[0] - sx * 0.5 * t, c[1] - sy * 0.5 * t, c[2] - 0.29 * t)))
        for r0, r1 in zip(rings, rings[1:]):
            for q in range(3):
                # seen from outside with the wire running away, the ring top -> +side -> -side is clockwise
                p0, p1, q0, q1 = r0[q], r0[(q + 1) % 3], r1[q], r1[(q + 1) % 3]
                tris += [(p0, q0, q1), (p0, q1, p1)]
    return tris


def _utility_poles(fur, table, solves, bands, mine_run, ground, index):
    """電柱 on one kerb of every road `denchu_kind` names, and the wires between them (PLAN.md T1; the notes in
    `furniture.json` say what stands where and why). Runs after the signals and the lamps -- a pole keeps
    `pole_clearance` from anything solid already standing, and is slid along the kerb (`denchu_shift`) before it
    is given up -- and before the trees, which keep clear of it like any pole.

    The WIRES go from each pole to the next of the same road, in the order the road runs, across the gaps the
    kerb runs leave (a vehicle entry, a junction) while the two poles are within `denchu_max_span`; a span to a
    pole in ANOTHER piece is not strung (each piece is built from what it owns), which leaves a gap only where a
    zone boundary happens to fall between two poles."""
    r = table.rules
    shifts = [float(x) for x in r.get("denchu_shift", (0.0,))]
    every = int(r.get("denchu_tr_every", 0))
    mat = r.get("denchu_wire_material", "")
    roads = {}
    for s in solves:
        kind = denchu_kind(table, s.road)
        if kind is None or len(s.samples) < 2:
            continue
        sides = denchu_sides(table, s.road)
        open_edge = getattr(s.road, "barrier_style", "") == "RAIL"
        if not mine_run(s):
            for sd in sides:                                     # another piece's run: the wire stops here
                roads.setdefault((s.road.name.split("__")[0], sd), []).append(None)
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            if sgn not in sides:
                continue
            chain = roads.setdefault((s.road.name.split("__")[0], sgn), [])
            pts = [tuple(q) for q in pts]
            cum = _lengths(pts)
            drops = [cum[v] for v, k in enumerate(kerb) if isinstance(k, ped.EntryKerb)]
            last = -math.inf
            for st in denchu_stations(cum[-1], kind, r, stagger=sgn != sides[0]):
                spot = None
                for sh in shifts:
                    if st + sh > last + 8.0:                     # a slid pole never lands on the one before it
                        spot = _denchu_spot(fur, table, index, ground, pts, cum, walk, kerb, wall, drops, sgn, st + sh,
                                            open_edge)
                    if spot is not None:
                        last = st + sh
                        break
                if spot is None:
                    fur.counts["denchu_skipped"] = fur.counts.get("denchu_skipped", 0) + 1
                    continue
                pos, d = spot
                n = sum(1 for c in chain if c is not None)
                asset = DENCHU_ASSETS[(kind == "lamp", every > 0 and n % every == every // 2)]
                fwd = (sgn * d[0], sgn * d[1])                   # the piece's +X (its arm, its lamp) toward the road
                if fur.put(table, asset, pos, fwd, s.road.name):
                    chain.append((pos, fwd))
    if not mat:
        return
    reach = float(r.get("denchu_max_span", 60.0))
    for name in sorted(roads):
        prev = None
        for node in roads[name]:
            if node is not None and prev is not None and math.hypot(
                    node[0][0] - prev[0][0], node[0][1] - prev[0][1]) <= reach:
                tris = wire_span(prev, node, r)
                if tris:
                    fur.wires.setdefault(mat, []).extend(tris)
                    fur.counts["wire_spans"] = fur.counts.get("wire_spans", 0) + 1
            prev = node


# ------------------------------------------------------------------------------------------- ガードレール

def guardrail_kind(table, road):
    """Where a road carries the white guardrail (the notes in `furniture.json`): None, "drop" (a mountain road: the
    valley side only), "edge" (a no-pedestrian road whose `barrier_style` is RAIL: every ground-level edge the solver
    left without a wall) or "kerb" (a wide city road: between the carriageway and the footway). "drop" is every
    edge of a mountain road except where the HILL stands beside it."""
    r = table.rules
    a = table.assets.get("guardrail")
    if a is None or getattr(road, "road_class", "") in ("expressway", "ramp", "rail") or excluded(a, road.name):
        return None
    if any(fnmatch.fnmatchcase(road.name, g) for g in r.get("guardrail_drop_roads", ())):
        return "drop"
    if not getattr(road, "ped_access", True):
        return "edge" if getattr(road, "barrier_style", "") == "RAIL" else None
    base = road.base
    if (max(int(base.lanes_fwd), int(base.lanes_bwd)) >= int(r.get("guardrail_min_lanes", 2))
            and max(float(base.left_walk_width), float(base.right_walk_width)) > 0.0):
        return "kerb"
    return None


def _guardrails(fur, table, solves, bands, mine_run, ground, index):
    """White ガードレール modules laid end to end along the edges `guardrail_kind` names, each turned to its edge and
    pitched to its grade. Runs LAST: a rail keeps nothing away and asks only where it may not be -- on a barrier's
    line, in a vehicle entry or a car-park keep-out, in a lane, within `guardrail_end_clear` of a run's end (the
    crossing, where people step into the road)."""
    a = table.assets.get("guardrail")
    if a is None:
        return
    r = table.rules
    length = (a["hi"][2] - a["lo"][2]) * a["scale"][2]
    inset, clear = float(r.get("guardrail_inset", 0.25)), float(r.get("guardrail_end_clear", 9.0))
    rise, reach = float(r.get("guardrail_hill_rise", 1.0)), float(r.get("guardrail_hill_reach", 4.0))
    if length <= 0.5:
        return
    for s in solves:
        kind = guardrail_kind(table, s.road)
        if kind is None or not mine_run(s) or len(s.samples) < 2:
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.road_edge_runs(s, bands):
            pts = [tuple(q) for q in pts]
            cum = _lengths(pts)
            n = int((cum[-1] - 2.0 * clear) // length)
            if n <= 0:
                continue
            drops = [cum[v] for v, k in enumerate(kerb) if isinstance(k, ped.EntryKerb)]
            start = 0.5 * (cum[-1] - n * length) + 0.5 * length
            for m in range(n):
                st = start + m * length
                if any(abs(st - c) <= ped.ENTRY_RAMP + ENTRY_CLEAR + 0.5 * length for c in drops):
                    continue
                p, d, i = _at(pts, cum, st)
                j = min(i + 1, len(pts) - 1)
                if max(float(wall[i]), float(wall[j])) > 0.0:
                    continue
                k = min(float(kerb[i]), float(kerb[j]))
                w = min(float(walk[i]), float(walk[j]))
                if kind == "kerb" and (k <= 0.0 or w <= 0.0):
                    continue                                     # a level crossing, a dropped kerb: no rail across it
                if not _grounded(ground, p, r["max_above_ground"]):
                    continue
                lat = _left(d)
                out = (sgn * lat[0], sgn * lat[1])
                if kind == "drop" and ground is not None:
                    g = ground(p[0] + out[0] * reach, p[1] + out[1] * reach)
                    if g is not None and g - p[2] >= rise:
                        continue                                 # the hill stands here (the inner side): no rail
                pos = (p[0] + out[0] * inset, p[1] + out[1] * inset, p[2] + (k if w > 0.0 else 0.0))
                # the module's ENDS too (its posts): a 4 m module whose centre is clear can still stand its end post
                # in a lane -- measured S17, probe_rail_track: 4 guardrail posts in the train's gauge at 踏切
                hh, ends = 0.5 * length, [pos]
                ends += [(pos[0] + d[0] * e * hh, pos[1] + d[1] * e * hh, pos[2]) for e in (-1.0, 1.0)]
                if index is not None and not all(index.clear_of(q, 0.1, asset_height(table, "guardrail"))
                                                 for q in ends):
                    fur.counts["guardrail_in_lane"] = fur.counts.get("guardrail_in_lane", 0) + 1
                    continue
                # the piece's +X (the beam) toward the road, so its forward runs WITH the edge on the left kerb and
                # against it on the right; the pitch is the edge's own grade along that forward
                seg = math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])
                grade = (pts[j][2] - pts[i][2]) / seg if seg > 1e-6 else 0.0
                if fur.put(table, "guardrail", pos, (sgn * d[0], sgn * d[1]), s.road.name):
                    fur.placements[-1]["pitch"] = round(math.atan(sgn * grade), 5)


class _LaneIndex(object):
    """Every exported lane's plan segments on a coarse grid, for "is this spot in a lane".

    A footway is a fact about ONE road, so a spot on it can still be in the CARRIAGEWAY of another that runs
    alongside -- a ramp beside its mainline is the case (measured on the sample network: a tree on `demo_main`'s
    footway stood 0.23 m off `demo_ramp_b_F0`'s centreline). A lamp post there is bad; a 9 m tree is worse.

    The question is asked in THREE dimensions when the caller says how tall its thing is (`height`): a lane that
    passes OVER the spot with room for the thing under its deck, or runs under the deck the spot stands on, is
    not in the way. Asked in plan only, a street under a viaduct lost one whole kerb of furniture (measured on the
    island 2026-10-12: `chuo_dori__3` under the expressway carried 6 rail modules on one kerb and 50 on the other,
    1 lamp against 7, no tree against 6)."""

    CELL = 20.0
    #: what hangs below a lane's surface where it is a deck (slab + girder): a thing under it must end below this
    DECK_DEPTH = 1.6
    #: air between a thing's top and the underside of the deck above it
    HEADROOM = 0.3

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

    def clear_of(self, p, margin, height=None, spread=0.0):
        """True when `p` is more than that lane's half width plus `margin` from every lane centreline. With a
        `height` (the thing's top above `p`), a lane on another LEVEL does not count: one whose deck clears the
        thing's top, or one more than a deck's depth below the spot. `spread` is how far the thing's TOP reaches
        in plan (a tree's crown): a deck that close overhead without room for the top refuses the spot too (seven
        9 m trees stood beside a viaduct's edge with their crowns in its deck, check_street_trees 2026-10-12)."""
        i0, j0 = int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))
        for i in range(i0 - 1, i0 + 2):
            for j in range(j0 - 1, j0 + 2):
                for a, b, half in self.cells.get((i, j), ()):
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    n = vx * vx + vy * vy
                    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / n))
                    dist = math.hypot(p[0] - (a[0] + vx * t), p[1] - (a[1] + vy * t))
                    levelled = height is not None and len(p) > 2 and len(a) > 2 and len(b) > 2
                    z = a[2] + (b[2] - a[2]) * t if levelled else 0.0
                    if dist < half + margin:
                        if levelled and (z - self.DECK_DEPTH >= p[2] + height + self.HEADROOM
                                         or z <= p[2] - self.DECK_DEPTH):
                            continue
                        return False
                    if levelled and spread > 0.0 and dist < half + spread and z > p[2] + self.DECK_DEPTH \
                            and z - self.DECK_DEPTH < p[2] + height + self.HEADROOM:
                        return False
        return True


def asset_height(table, asset):
    """How far an asset's top stands above its foot, metres (the piece's own bounds, Y up, scaled)."""
    a = table.assets.get(asset) or {}
    if "hi" not in a:
        return None
    return max(0.0, float(a["hi"][1]) * float(a.get("scale", (1.0, 1.0, 1.0))[1]))


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
                off = sgn * tree_kerb_offset(table)
                pos = (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k)
                if fur.clear_of(pos, r["tree_clearance"]) and index.clear_of(
                        pos, r["tree_lane_clear"], asset_height(table, asset), float(r.get("tree_crown_radius", 3.5))):
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


def tree_kerb_offset(table):
    """Where a street tree's CENTRE stands, metres in from the kerb line: `tree_kerb_gap`, pushed out so that the
    planter it stands in (`tree_planter`) keeps `planter_kerb_gap` of footway between its kerb-side face and the kerb.

    User-reported 2026-10-06: "the vehicle driving along the kerb is damaged sometimes, not other times". Measured
    (`probe_road_launch.gd` with OW_CRASH_TRACE): every damaging contact was this planter, never the kerb -- the tree
    stood 0.90 m in and the planter is 0.898 m across-half, so its face was FLUSH with the kerb line (2 mm) and a car
    with its tyre on the kerb scraped a 0.6 m concrete box every 18 m. One owner, read by `island_buildings
    .furniture_strip` too, so the crowd's walk line moves with it."""
    r = table.rules
    off = float(r["tree_kerb_gap"])
    if r.get("tree_planter", True) and "planter" in table.assets:
        a = table.assets["planter"]
        half = 0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0]
        off = max(off, float(r.get("planter_kerb_gap", 0.3)) + half)
    return off


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


def _median_hedge(fur, table, solves, mine_run, index=None):
    """植樹帯: a clipped hedge down every RAISED median wide enough for one (PLAN.md T3, the half the guardrail did
    not take). Boxes `median_hedge_unit` long with `median_hedge_gap` between them, `median_hedge_height` tall, as
    wide as the island allows up to `median_hedge_half` and never nearer its kerb than `median_hedge_kerb_gap`;
    none within `median_hedge_end_clear` of a run's end (the junction: a driver turning must see over the median),
    none round a median lamp (`pole_clearance`), none where a lane or a track crosses the island. Swept INTO the
    piece like the wires (`HEDGE_OBJECT`, no collision: the island is kerbed and a hedge is soft); placed after the
    lamps so it yields to them."""
    r = table.rules
    unit = float(r.get("median_hedge_unit", 0.0))
    mat = r.get("median_hedge_material", "")
    if unit <= 0.0 or not mat:
        return
    gap, tall = float(r.get("median_hedge_gap", 1.0)), float(r.get("median_hedge_height", 0.8))
    half_max, kerb_gap = float(r.get("median_hedge_half", 0.6)), float(r.get("median_hedge_kerb_gap", 0.4))
    for s in solves:
        if not mine_run(s) or len(s.samples) < 2 or getattr(s.road, "median_style", None) != pm.MED_RAISED:
            continue
        pts = [tuple(sm.pos) for sm in s.samples]
        cum = _lengths(pts)
        for st in _stations(cum[-1], unit + gap, float(r.get("median_hedge_end_clear", 12.0))):
            p, d, i = _at(pts, cum, st)
            j = min(i + 1, len(pts) - 1)
            mh = min(s.values[i]["rka_med_h"], s.values[j]["rka_med_h"])
            mz = min(s.values[i]["rka_med_z"], s.values[j]["rka_med_z"])
            half = min(half_max, mh - kerb_gap)
            if mz <= 0.0 or half < float(r.get("median_hedge_min_half", 0.3)):
                continue
            pos = (p[0], p[1], p[2] + mz)
            if not fur.clear_of(pos, r["pole_clearance"] + 0.5 * unit):
                continue
            if index is not None and not index.clear_of(pos, 0.0, tall):
                continue
            fur.hedge.setdefault(mat, []).extend(_box(pos, d, 0.5 * unit, half, tall))
            fur.counts["median_hedge"] = fur.counts.get("median_hedge", 0) + 1


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


def place(table, solved, lanes_doc, mine_lane, mine_run, mine_pad, mark_mat, ground=None, keep_clear=None,
          keep_out=None):
    """One piece's furniture. `solved` is `point_edges.solve_all`'s tuple; `lanes_doc` the WHOLE network's lanes and
    junctions (a mouth's connectors may stream with the pad's piece); `mine_*` say what belongs to this piece;
    `mark_mat(lane)` is the paint material of that lane's road. `keep_clear` is ANOTHER network's lanes (the rail's
    tracks, 2026-09-26): nothing solid of this network stands in them, but nothing is placed FOR them either.
    `keep_out`: boxes nothing that stands up is placed in (`Furniture.keep_out`: car-park entrances)."""
    fur = Furniture(keep_out)
    if table is None:
        return fur
    solves, jsolves, _gsolves, bands = solved
    # a RAIL road (PLAN.md R1) carries none of the street's furniture: its platforms are footways to the kit (R3), and
    # a platform must not grow street trees, planters or 10 m street lamps
    solves = [sv for sv in solves if getattr(sv.road, "road_class", "") != "rail"]
    lanes = {l["id"]: l for l in lanes_doc.get("lanes", ()) if l.get("road_class") != "rail"}
    junctions = {j["id"]: j for j in lanes_doc.get("junctions", ())}
    ordered = [junctions[k] for k in sorted(junctions)]
    _junction_marks(fur, table, lanes, ordered, mine_lane, mark_mat)
    _speed_text(fur, table, lanes, mine_lane, mark_mat)
    # the signals first: every later solid prop (planter, bollard, lamp) keeps clear of a pole already standing
    # ONE lane index, shared: "may a solid thing stand here" is one question, and a functional pole that skips
    # it is how a signal came to stand in a turn connector and a median lamp in a neighbouring road's lane.
    index = _LaneIndex(dict(lanes, **{"~" + str(l["id"]): l for l in keep_clear or ()}))
    fur.lane_index = index          # ...asked again by crossing_signals, which runs after `place`
    _signals(fur, table, lanes, ordered, mine_lane, ground, index)
    _ped_signals(fur, table, lanes, ordered, mine_lane, ground, index)
    for site in expressway_sign_sites(table, lanes, lanes_doc.get("traffic_side") == "right"):
        if mine_lane(lanes[site["lane"]]) and fur.put(table, site["asset"], site["pos"], site["fwd"], site["road"]):
            fur.placements[-1].update({k: site[k] for k in ("sign", "dest", "route", "lane")})
    _lane_props(fur, table, dict(sorted(lanes.items())), mine_lane, ground)
    _edge_props(fur, table, solves, jsolves, bands, mine_run, mine_pad, ground, index)
    _lamps(fur, table, solves, bands, mine_run, ground, index)
    _utility_poles(fur, table, solves, bands, mine_run, ground, index)
    # the trees ask the SAME lanes as every pole, the other network's tracks included (a tree and its pit stood 1.9 m
    # off a rail track, probe_rail_track's gauge 2026-09-26)
    _street_trees(fur, table, solves, bands, mine_run, ground, dict(lanes, **{"~" + str(l["id"]): l for l in keep_clear or ()}))
    _median_walls(fur, table, solves, mine_run)
    _median_hedge(fur, table, solves, mine_run, index)
    _guardrails(fur, table, solves, bands, mine_run, ground, index)
    return fur


# ------------------------------------------------------------------------------------------- expressway signs

def _is_expressway(lane):
    return lane.get("road_class") in ("expressway", "ramp")


def _kerbward(d, right=False):
    """The unit direction from a lane toward the kerb its traffic keeps to: its left, or -- `right` -- its right."""
    l = _left(d)
    return (-l[0], -l[1]) if right else l


def _leftmost_edge(lanes, q, d, half, right=False):
    """How far KERBWARD of `q` (kit frame, travel direction `d`) the outer edge of the outermost lane running beside
    it is: every lane with a sample within 6 m along and 3 m in height of `q`, on that side of it, counts; at least
    `half`. Kerbward is left on a keep-left network, right on a right-hand one."""
    lft = _kerbward(d, right)
    best = half
    for l in lanes.values():
        hw = 0.5 * float(l.get("lane_width", 4.5))
        for p in _lane_kit(l):
            vx, vy = p[0] - q[0], p[1] - q[1]
            if abs(vx * d[0] + vy * d[1]) > 6.0 or abs(p[2] - q[2]) > 3.0:
                continue
            lat = vx * lft[0] + vy * lft[1]
            if 0.0 < lat < 15.0:
                best = max(best, lat + hw)
    return best


def _walk(lanes, preds, lane, dist, back):
    """The point `dist` m from `lane`'s start (`back` = False: along it and on through its first successor of the same
    road class) or from its start BACKWARD through its first predecessor (`back` = True), in the KIT frame, with the
    travel direction there: ((x, y, z), (dx, dy), lane id) or None."""
    cur, left = lane, dist
    for _hop in range(40):
        pts = _lane_kit(cur)
        if len(pts) < 2:
            return None
        seq = list(reversed(pts)) if back else pts
        cum = _lengths(seq)
        if cum[-1] >= left:
            q, d, _i = _at(seq, cum, left)
            if back:
                d = (-d[0], -d[1])
            return (q, d, cur["id"])
        left -= cum[-1]
        if back:
            nxt = [lanes[i] for i in preds.get(cur["id"], ()) if _is_expressway(lanes[i])]
        else:
            nxt = [lanes[n] for n in cur.get("next", ()) if n in lanes and _is_expressway(lanes[n])]
        if not nxt:
            return None
        cur = sorted(nxt, key=lambda l: l["id"])[0]
    return None


def _destination(lanes, lane):
    """Where a ramp leads: the first road that is not a ramp, following the ramp's lanes forward (through a junction's
    connector to the road it lands on). (road name, is_expressway) or (None, False)."""
    cur, seen = lane, set()
    for _hop in range(60):
        if cur["id"] in seen:
            break
        seen.add(cur["id"])
        if cur.get("road_class") != "ramp" and cur.get("kind") != "connector":
            return cur.get("road_name"), cur.get("road_class") == "expressway"
        nxt = [lanes[n] for n in cur.get("next", ()) if n in lanes]
        if not nxt:
            break
        if any(l.get("kind") == "connector" for l in nxt):
            # a junction: the street the ramp lands on wins over a U-turn back up the other ramp of a diamond
            def lands(c):
                t = [lanes[n] for n in c.get("next", ()) if n in lanes]
                return bool(t) and all(x.get("road_class") not in ("ramp", "expressway") for x in t)
            street = [c for c in nxt if lands(c)]
            if street:
                nxt = street
        # a connector's straight movement first, else the first
        cur = sorted(nxt, key=lambda l: (l.get("turn") not in ("S", ""), l["id"]))[0]
    return None, False


def expressway_sign_sites(table, lanes, right=False):
    """Japanese expressway GUIDE signs (PLAN.md item 1g, user 2026-09-30): white letters on green, text drawn at run
    time. For every RAMP (a lane of `road_class` "ramp" whose own road does not feed it):
      * fed by an EXPRESSWAY lane (an exit, or a JCT ramp): an `expwy_sign` cantilever on the mainline
        `expwy_sign_before` m before the diverge, its post at the LEFT edge (keep-left: exits leave on the left) and its
        panel over the lanes -- 出口 + the destination street, or JCT + the destination expressway;
      * fed by a STREET junction's connector (an entrance): an `expwy_entrance_sign` `expwy_entrance_in` m up the ramp
        on its left kerb, facing the traffic turning in -- 入口 + the expressway it joins.
    Deterministic and network-wide (every piece asks the same question; each keeps the sites on its own lanes)."""
    if "expwy_sign" not in table.assets and "expwy_entrance_sign" not in table.assets:
        return []
    r = table.rules
    before = float(r.get("expwy_sign_before", 120.0))
    cantilever = "expwy_sign_r" if right and "expwy_sign_r" in table.assets else "expwy_sign"
    edge = float(r.get("expwy_sign_edge", 1.2))
    inset = float(r.get("expwy_entrance_in", 12.0))
    preds = {}
    for l in lanes.values():
        for n in l.get("next", ()):
            preds.setdefault(n, []).append(l["id"])
    out, done = [], set()
    for lid in sorted(lanes):
        lane = lanes[lid]
        if lane.get("road_class") != "ramp" or lane.get("kind") == "connector":
            continue
        road = lane.get("road_name", "")
        feeders = [lanes[i] for i in preds.get(lid, ()) if lanes[i].get("road_name") != road]
        if not feeders or road in done:
            continue
        dest, dest_expwy = _destination(lanes, lane)
        main = [f for f in feeders if f.get("road_class") == "expressway"]
        street = [f for f in feeders if f.get("kind") == "connector"]
        if main and cantilever in table.assets:
            m = sorted(main, key=lambda l: l["id"])[0]
            w = _walk(lanes, preds, m, before, back=True)
            if w is None or dest is None:
                continue
            # a LANE SPLIT (分岐, the Wangan's T): two ramps leave the same carriageway at one joint, so both signs would
            # stand on one spot -- the next one stands `expwy_sign_stagger` m further back, so a driver reads them in turn
            k = 1
            while w is not None and any(math.dist(w[0][:2], o["pos"][:2]) < 12.0 for o in out
                                        if o["asset"] == cantilever):
                w = _walk(lanes, preds, m, before + k * float(r.get("expwy_sign_stagger", 60.0)), back=True)
                k += 1
            if w is None:
                continue
            q, d, at = w
            half = 0.5 * float(lanes[at].get("lane_width", 4.5))
            lft = _kerbward(d, right)
            # the post stands outside the OUTERMOST lane at this cross-section, not just the lane walked back along: a
            # lane carried across a joint (lane balance) runs kerbward of it, and the post stood in that lane
            off = _leftmost_edge(lanes, q, d, half, right) + edge
            pos = (q[0] + lft[0] * off, q[1] + lft[1] * off, q[2])
            out.append({"asset": cantilever, "pos": pos, "fwd": d, "road": m.get("road_name", ""), "lane": m["id"],
                        "sign": "jct" if dest_expwy else "exit", "dest": dest, "route": m.get("road_name", "")})
            done.add(road)
        elif street and "expwy_entrance_sign" in table.assets:
            w = _walk(lanes, preds, lane, inset, back=False)
            route = dest if dest_expwy else None
            if w is None or route is None:
                continue
            q, d, at = w
            half = 0.5 * float(lane.get("lane_width", 4.5))
            lft = _kerbward(d, right)
            # a roadside sign, not an overhang: its whole panel clears the kerb -- of the OUTERMOST lane there (a ramp is
            # two lanes now, and the sign stood in the second one, probe_road_clear 2026-10-04)
            e2 = float(r.get("expwy_entrance_edge", 2.9))
            off = _leftmost_edge(lanes, q, d, half, right) + e2
            pos = (q[0] + lft[0] * off, q[1] + lft[1] * off, q[2])
            out.append({"asset": "expwy_entrance_sign", "pos": pos, "fwd": d, "road": road, "lane": lid,
                        "sign": "entrance", "dest": route, "route": route})
            done.add(road)
    return out


_LANE_ID = re.compile(r"_([FR])(\d+)$")


def _lane_dest(lanes, lane):
    """Where a lane at a lane split LEADS, as a driver reads it: the expressway it carries on to. Follow the lane (its
    chain successor first, then a ramp's) and keep the distinct expressway roads met, by base name; the destination is
    the SECOND of them when there is one (the T3 lane runs on along the airport link for 300 m and becomes the C1 loop:
    "Loop"), else the first (the T1 lane IS the airport link and leaves it at the forecourt: "Airport Link")."""
    cur, seen, bases = lane, set(), []
    for _hop in range(40):
        if cur["id"] in seen:
            break
        seen.add(cur["id"])
        if cur.get("road_class") == "expressway" and cur.get("kind") != "connector":
            b = cur.get("road_name", "").split("__")[0]
            if not bases or bases[-1] != b:
                bases.append(b)
                if len(bases) == 2:
                    break
        nxt = [lanes[n] for n in cur.get("next", ()) if n in lanes]
        if not nxt or not any(l.get("road_class") in ("expressway", "ramp") for l in nxt):
            break
        kinds = dict(zip(cur.get("next", ()), cur.get("next_kinds") or ()))
        nxt = [l for l in nxt if l.get("road_class") in ("expressway", "ramp")]
        cur = sorted(nxt, key=lambda l: (kinds.get(l["id"]) == "ramp", l["id"]))[0]
    return bases[-1] if bases else None


def lane_splits(lanes):
    """Every expressway carriageway that ENDS by splitting lane by lane into ramps (分岐, the Wangan's T at J0, review
    P1-4): [(lead lane, [destination per lane, LEFT to right])]. A carriageway is its road's through lanes of one
    direction; it splits when each lane hands over to a ramp and the ramps are not all one road."""
    groups = {}
    for l in lanes.values():
        if l.get("road_class") != "expressway" or l.get("kind") == "connector":
            continue
        m = _LANE_ID.search(l["id"])
        if m:                                   # (an aux slot's id, `_AF0`, does not match: through lanes only)
            groups.setdefault((l.get("road_name"), m.group(1)), []).append(l)
    out = []
    for _k, ls in sorted(groups.items()):
        succ = []
        for l in ls:
            rs = [lanes[n] for n in l.get("next", ()) if n in lanes and lanes[n].get("road_class") == "ramp"
                  and lanes[n].get("road_name") != l.get("road_name")]
            if len(rs) != 1:
                break
            succ.append((l, rs[0]))
        else:
            if len(succ) < 2 or len({r.get("road_name") for _l, r in succ}) < 2:
                continue
            # left to right at the split: keep-left, the left lane is the one a driver reads first
            ends = [_lane_kit(l)[-1] for l, _r in succ]
            q = _lane_kit(succ[0][0])
            d = _norm2(q[-1][0] - q[-2][0], q[-1][1] - q[-2][1])
            lf = _left(d)
            cx = sum(e[0] for e in ends) / len(ends)
            cy = sum(e[1] for e in ends) / len(ends)
            order = sorted(succ, key=lambda lr: -((_lane_kit(lr[0])[-1][0] - cx) * lf[0]
                                                  + (_lane_kit(lr[0])[-1][1] - cy) * lf[1]))
            dests = [_lane_dest(lanes, r) for _l, r in order]
            if all(dests) and len(set(dests)) > 1:
                out.append((order[0][0], dests))
    return out


def lane_gantry_sites(table, lanes, taken=(), right=False):
    """Lane-designation signs (方面別車線案内) before each lane split: an `expwy_sign` cantilever over the carriageway
    every `expwy_lane_gantries` m back from the split, saying for each lane, left to right, where it goes (kind
    "lanes", destinations joined by "|")."""
    if "expwy_sign" not in table.assets:
        return []
    r = table.rules
    edge = float(r.get("expwy_sign_edge", 1.2))
    preds = {}
    for l in lanes.values():
        for n in l.get("next", ()):
            preds.setdefault(n, []).append(l["id"])
    out = []
    for lead, dests in lane_splits(lanes):
        for back in r.get("expwy_lane_gantries", (300.0, 600.0)):
            w = _walk(lanes, preds, lead, float(back), back=True)      # measured back from the split
            if w is None:
                continue
            q, d, at = w
            if any(math.dist(q[:2], o["pos"][:2]) < 30.0 for o in list(taken) + out):
                continue
            half = 0.5 * float(lanes[at].get("lane_width", 4.5))
            lft = _kerbward(d, right)
            pos = (q[0] + lft[0] * (half + edge), q[1] + lft[1] * (half + edge), q[2])
            out.append({"asset": "expwy_sign_r" if right and "expwy_sign_r" in table.assets else "expwy_sign", "pos": pos, "fwd": d, "road": lead.get("road_name", ""),
                        "lane": lead["id"], "sign": "lanes", "dest": "|".join(dests),
                        "route": lead.get("road_name", "")})
    return out


def expressway_sign_plan(table, lanes_doc):
    """The whole network's expressway signs for the runtime (world.TrafficSignals): each panel's centre and facing in
    the lanekit's frame (Godot axes), its size, and what it says (kind, destination road, route road)."""
    lanes = {l["id"]: l for l in lanes_doc.get("lanes", ()) if l.get("road_class") != "rail"}
    rows = []
    right = lanes_doc.get("traffic_side") == "right"
    sites = expressway_sign_sites(table, lanes, right)
    sites += lane_gantry_sites(table, lanes, sites, right)
    for site in sites:
        a = table.assets[site["asset"]]
        panel = a.get("panel")
        if panel is None:
            continue
        lift = float(a.get("lift", 0.0)) - a["lo"][1] * a["scale"][1]
        pos = (site["pos"][0], site["pos"][1], site["pos"][2] + lift)
        c = _piece_to_godot(pos, site["fwd"], panel["centre"])
        n = _dir_to_godot(site["fwd"], (0.0, 0.0, 1.0))
        rows.append({"kind": site["sign"], "dest": site["dest"], "route": site["route"],
                     "pos": [round(v, 3) for v in c], "normal": [round(v, 5) for v in n],
                     "size": [round(v, 3) for v in panel["size"]]})
    return {"schema": 1, "note": "expressway guide signs (white on green), the lanekit's frame (Godot axes); written "
                                 "by roadkit_cli gltf, read by world.TrafficSignals", "signs": rows}


def _crossing_unit_clear(index, table, r, pos, out, fwd, cross, normal, clear):
    """A 踏切 unit's spot clear of every lane: the nearest of a small search -- outward from the road up to 6 m,
    and along its approach up to 8 m back or 3 m on -- that still stands at least clear - 1 m from the track (a
    junction beside the crossing swings its turn connectors over the corner where the unit stands). The original
    spot when nothing is clear (reported by the probe, never dropped: the crossing needs its unit)."""
    if index is None:
        return pos
    margin = _pole_half(table, "crossing_signal") + float(r.get("pole_lane_clear", 0.15))
    if index.clear_of(pos, margin):
        return pos
    cands = []
    # 6 m out, 8 m back or 3 m on (2026-10-08: a unit beside a junction at Godot (19, 134) found nothing within
    # 4 m / 6 m back / 1 m on and stood 0.12 m from a turn connector's centreline; the nearest clear spot was
    # 2 m on and 2 m out). The track rule below still keeps every candidate `clear - 1` from the rail.
    for k in range(0, 25):
        for a in (0.0, -1.0, -2.0, -3.0, -4.0, -6.0, -8.0, 1.0, 2.0, 3.0):
            d_out = 0.25 * k
            c = (pos[0] + out[0] * d_out + fwd[0] * a, pos[1] + out[1] * d_out + fwd[1] * a, pos[2])
            if abs((c[0] - cross[0]) * normal[0] + (c[1] - cross[1]) * normal[1]) < clear - 1.0:
                continue
            cands.append((math.hypot(d_out, a), c))
    for _d, c in sorted(cands, key=lambda t: t[0]):
        if index.clear_of(c, margin):
            return c
    return pos


def crossing_signals(fur, table, crossings, road_right=False):
    """踏切 signals (PLAN.md R4): at each level crossing a `crossing_signal` (警報機 + 遮断機, boom up) on the LEFT of
    each approach -- Japan drives on the left, so the unit a driver meets stands at their own kerb -- `crossing_track_
    clear` m before the rail's centreline (measured square to the track, so an oblique road takes it further along
    itself) and `crossing_side` m outside the road's paved edge, its lamps facing the traffic. `crossings` are
    `point_mesh`'s report rows: (rail, road, x, y, z, tx, ty, rx, ry, left half, right half)."""
    r = table.rules
    if "crossing_signal" not in table.assets:
        return
    clear = float(r.get("crossing_track_clear", 4.5))
    side = float(r.get("crossing_side", 0.6))
    for c in crossings:
        if len(c) < 11 or (c[7] == 0.0 and c[8] == 0.0):
            continue
        _rail, road, x, y, z, tx, ty, rx, ry, wl, wr = c[:11]
        sin = abs(tx * ry - ty * rx)
        along = clear / max(0.3, sin)
        lx, ly = -ry, rx
        for sgn, w, w_other in ((1.0, wl, wr), (-1.0, wr, wl)):
            # approach heading sgn * r: it comes from -sgn * r, its left is sgn * l. The unit stands at the kerb the
            # ROAD's traffic keeps to: that left, or (`road_right`: the road network is right-hand) the other side
            ks = -1.0 if road_right else 1.0
            if road_right:
                w = w_other
            lx, ly = ks * -ry, ks * rx
            pos = (x - sgn * rx * along + sgn * lx * (w + side), y - sgn * ry * along + sgn * ly * (w + side), z)
            # the unit must stand `clear` from the rail's centreline SQUARE to the rail, whatever the road frame says:
            # at a crossing beside a junction pad the band's spine is not the road's heading, and a pole landed
            # 0.26 m from a track (probe_rail_track's gauge, 2026-09-26). Pushed on out along the rail's normal.
            nx_, ny_ = -ty, tx
            d = (pos[0] - x) * nx_ + (pos[1] - y) * ny_
            want = clear
            if abs(d) < want:
                s_ = 1.0 if d >= 0.0 else -1.0
                pos = (pos[0] + nx_ * s_ * (want - abs(d)), pos[1] + ny_ * s_ * (want - abs(d)), z)
            # ...and off every lane: a junction beside the crossing swings its turn connectors over the footway (a
            # unit stood in one, probe_road_clear 2026-10-06). The rail build sees the ROAD lanes through
            # `--keep-clear-lanekits`. Pushed outward from the road; never dropped (the crossing needs its unit).
            pos = _crossing_unit_clear(getattr(fur, "lane_index", None), table, r, pos, (sgn * lx, sgn * ly),
                                       (sgn * rx, sgn * ry), (x, y), (nx_, ny_), clear)
            if fur.put(table, "crossing_signal", pos, (sgn * rx, sgn * ry), road):
                fur.counts["crossing_units"] = fur.counts.get("crossing_units", 0) + 1


# ------------------------------------------------------------------------------------------- the signal plan

def _asset_lamps(table, asset):
    """An asset's lamp lenses and name plates in its GODOT piece frame: `lamps` inline in furniture.json, or
    `lamps_file` (a JSON the piece's build writes from its .blend, e.g. TrafficLight_JP.lamps.json, whose lenses also
    carry their MESH -- `tris` -- which the runtime lights). `res` is that file's res:// path (None when inline)."""
    a = table.assets.get(asset) or {}
    if a.get("lamps_file"):
        path = os.path.join(os.path.dirname(a["file"]), a["lamps_file"])
        if os.path.exists(path):
            with open(path) as fh:
                d = json.load(fh)
            d["res"] = a["kit"] + os.path.dirname(a["piece"]) + "/" + a["lamps_file"]
            return d
    return a.get("lamps") or {}


def _plates(src):
    """A lamps record's name plates: `plates` (a list, one per side of the arm), or the older single `plate`."""
    if src.get("plates"):
        return src["plates"]
    return [src["plate"]] if src.get("plate") else []


def _yaw(fwd):
    """The Godot Y rotation that puts a piece's -Z on kit direction `fwd` (the basis `_piece_to_godot` applies)."""
    return math.atan2(-fwd[0], fwd[1])


def _piece_to_godot(pos, fwd, q):
    """A point `q` of a piece (Godot piece frame: +X right, +Y up, forward -Z) placed at kit-frame `pos` facing kit
    `fwd`, as a GODOT world point (the lanekit's frame: point_export.godot, no network transform)."""
    fx, fy = fwd
    ox, oy, oz = pos[0], pos[2], -pos[1]
    # Xp = (fy, 0, fx), Yp = up, Zp = (-fx, 0, fy) -- the piece's -Z lands on fwd (godot (fx, 0, -fy))
    return (ox + fy * q[0] - fx * q[2], oy + q[1], oz + fx * q[0] + fy * q[2])


def _dir_to_godot(fwd, n):
    fx, fy = fwd
    return (fy * n[0] - fx * n[2], n[1], fx * n[0] + fy * n[2])


def signal_plan(table, lanes_doc, ground=None):
    """THE SIGNAL PLAN the runtime runs (world.TrafficSignals; user, 2026-09-26: "enable both pedestrian + traffic
    light"): for every signalised junction of the WHOLE network (the same placement as the pieces, all of it, so a
    DIRTY_ONLY build cannot leave the plan partial), in the lanekit's Godot frame:
      * `arms`: each arm with arriving lanes -- its lane ids (a car on one of them obeys this arm's light), its phase
        `group`, the distance back from the lane's end to stop at (the stop line's upstream edge), its road;
      * `groups`: arms facing each other move together (a crossing's two axes; a T's through road and its stem);
      * `lamps`: every lens of every vehicle and pedestrian signal standing for it, world position + facing, with
        the arm it belongs to and its colour -- a pedestrian lens shows WALK while its crosswalk's road is RED;
      * `plates`: each vehicle signal's name plate, with the road it stands over and the road it crosses.
    Times: `signal_green`, `signal_yellow`, `signal_all_red` (s)."""
    if table is None:
        return {"junctions": []}
    r = table.rules
    lanes = {l["id"]: l for l in lanes_doc.get("lanes", ()) if l.get("road_class") != "rail"}
    junctions = [j for _k, j in sorted((j["id"], j) for j in lanes_doc.get("junctions", ()))]
    fur = Furniture()
    index = _LaneIndex(lanes)
    _signals(fur, table, lanes, junctions, lambda l: True, ground, index)
    _ped_signals(fur, table, lanes, junctions, lambda l: True, ground, index)
    lamps_of = {a: _asset_lamps(table, a) for a in SIGNAL_ASSETS + ("ped_signal",)}
    stop_back = float(r["stop_back"]) + float(r["stop_width"])
    by_j = {}
    for arm in _arms(lanes, junctions):
        j = arm["junction"]
        if not _signalised(table, j, lanes):
            continue
        by_j.setdefault(j["id"], (j, []))[1].append(arm)
    out = []
    for jid, (j, arms) in sorted(by_j.items()):
        # the phase groups: an arm and the ONE arm coming at it most nearly head-on (fwd opposite within ~45 deg)
        # move together; every other arm gets a phase of its own (a Y, a 5-arm pad)
        group, g = {}, 0
        for arm in arms:
            k = _arm_index(arm)
            if k in group:
                continue
            group[k] = g
            best, bd = None, -0.7
            for other in arms:
                ko = _arm_index(other)
                dot = arm["fwd"][0] * other["fwd"][0] + arm["fwd"][1] * other["fwd"][1]
                if ko not in group and dot < bd:
                    best, bd = ko, dot
            if best is not None:
                group[best] = g
            g += 1
        rows = []
        for arm in arms:
            k = _arm_index(arm)
            rows.append({"index": k, "group": group[k], "in_lanes": [l["id"] for l in arm["ins"]],
                         "road": arm["ins"][0].get("road_name", ""), "stop_back": round(stop_back, 3),
                         "fwd": [round(arm["fwd"][0], 4), 0.0, round(-arm["fwd"][1], 4)]})
        road_of = {a["index"]: a["road"] for a in rows}
        lamps, plates = [], []
        for p in fur.placements:
            if p.get("junction") != jid:
                continue
            fwd = p["fwd"]
            src = lamps_of.get(p["asset"]) or {}
            # the pole the lens hangs on (its base, where the baked MultiMesh instance stands): the runtime lights a
            # lens only while that pole is streamed in and standing
            pole = [round(v, 3) for v in (p["pos"][0], p["pos"][2], -p["pos"][1])]
            yaw = round(_yaw(fwd), 5)
            for kind in ("vehicle", "pedestrian"):
                for d in src.get(kind, ()):
                    q = _piece_to_godot(p["pos"], fwd, d["pos"])
                    n = _dir_to_godot(fwd, d["normal"])
                    # a pedestrian head serves the crosswalk it was matched to (`ped_arm0` / `ped_arm1`, the second
                    # head of a corner pole); a vehicle lens, its own arm
                    a_k = p["arm"] if kind == "vehicle" else p.get("ped_arm%d" % d.get("head", 0), p["arm"])
                    row = {"kind": kind, "arm": a_k, "colour": d["colour"], "head": d.get("head", 0), "pole": pole,
                           "yaw": yaw,
                           "pos": [round(v, 3) for v in q], "normal": [round(v, 4) for v in n],
                           "radius": d.get("radius", 0.12)}
                    if d.get("tris") and src.get("res"):
                        # the lens MESH: the runtime lights the lens itself (its triangles, in the piece frame of
                        # `lamps`, placed at `pole` turned `yaw`), not a ball in front of it
                        row["lamps"] = src["res"]
                    lamps.append(row)
            if p["asset"] in SIGNAL_ASSETS:
                own = road_of.get(p["arm"], "").split("__")[0]
                others = [road_of[a["index"]] for a in rows if a["group"] != group.get(p["arm"])]
                # the street being CROSSED: another group's road, preferring one that is not this road itself (a
                # road bending through a T is both of its arms)
                cross = next((n for n in others if n.split("__")[0] != own), others[0] if others else "")
                for d in _plates(src):
                    plates.append({"arm": p["arm"], "road": road_of.get(p["arm"], ""), "cross": cross, "pole": pole,
                                   "pos": [round(v, 3) for v in _piece_to_godot(p["pos"], fwd, d["pos"])],
                                   "normal": [round(v, 4) for v in _dir_to_godot(fwd, d["normal"])],
                                   "size": d["size"]})
        c = j.get("center") or [0.0, 0.0, 0.0]
        out.append({"id": jid, "centre": c, "arms": rows, "groups": g, "lamps": lamps, "plates": plates})
    green, yellow, all_red = (float(r.get("signal_green", 22.0)), float(r.get("signal_yellow", 3.0)),
                              float(r.get("signal_all_red", 2.0)))
    coordinate(out, green + yellow + all_red)
    return {"schema": 1, "green": green, "yellow": yellow, "all_red": all_red, "junctions": out,
            "notes": "Written by roadkit_cli gltf (point_furniture.signal_plan); read by world.TrafficSignals. "
                     "Godot frame of the lanekit (the network's own transform is applied at runtime)."}


COORD_REACH = 100.0     # signalised junctions this close along one road run as ONE controller (系統制御)
COORD_SPEED = 12.0      # m/s: the progression speed the second junction's green follows the first's at


def coordinate(junctions, phase):
    """NEXT PASS step 6 (2026-10-02): closely spaced signals are coordinated. Each junction's place in the cycle is a
    hash of its id (`SignalTiming.offset`), so two junctions 74 m apart (a diamond's pair) ran at random to each other
    and a platoon let go by one stopped at the next. Junctions within COORD_REACH whose arms carry the SAME road (by
    base name) and the same number of phase groups (so one cycle) join one controller: a spanning tree from its
    lowest id, each junction's offset = its parent's + the shared road's group aligned + the travel time between them
    at COORD_SPEED (a green wave in the tree's direction). Written as `coord` = {"root": id, "rel": s}; the runtime
    takes offset(root) + rel. Mutates `junctions`."""
    import math as _m
    by = {j["id"]: j for j in junctions}

    def road_group(j, road):
        return next((a["group"] for a in j["arms"] if a["road"].split("__")[0] == road), None)

    edges = {}
    for i, a in enumerate(junctions):
        ra = {x["road"].split("__")[0] for x in a["arms"]}
        for b in junctions[i + 1:]:
            if a["groups"] != b["groups"] or a["groups"] < 2:
                continue
            d = _m.dist((a["centre"][0], a["centre"][2]), (b["centre"][0], b["centre"][2]))
            if d > COORD_REACH:
                continue
            shared = sorted(ra & {x["road"].split("__")[0] for x in b["arms"]})
            if not shared:
                continue
            edges.setdefault(a["id"], []).append((b["id"], shared[0], d))
            edges.setdefault(b["id"], []).append((a["id"], shared[0], d))
    seen = set()
    for root in sorted(edges):
        if root in seen:
            continue
        seen.add(root)
        by[root]["coord"] = {"root": root, "rel": 0.0}
        queue = [root]
        while queue:
            a = queue.pop(0)
            ja = by[a]
            for b, road, d in sorted(edges[a]):
                if b in seen:
                    continue
                seen.add(b)
                jb = by[b]
                cyc = phase * jb["groups"]
                rel = ja["coord"]["rel"] - d / COORD_SPEED + (road_group(jb, road) - road_group(ja, road)) * phase
                jb["coord"] = {"root": root, "rel": round(rel % cyc, 3)}
                queue.append(b)


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
    # a KEEP-OUT box (a car-park entrance, deep along +y): a tree inside is refused, beside it allowed, a signal kept
    ko = Furniture([(0.0, 0.0, 0.0, 1.0, 3.0, 2.0)])
    assert ko.blocked("tree", (2.5, 1.5, 0.0)) and not ko.blocked("tree", (3.5, 0.0, 0.0))
    assert not ko.blocked("tree", (0.0, 2.5, 0.0)) and not ko.blocked("ped_signal", (0.0, 0.0, 0.0))
    assert godot_to_kit((1.0, 2.0, 3.0)) == (1.0, -3.0, 2.0)

    # 電柱 (T1): a block street is lit from its poles, a 2+2 keeps its lamps, a 3+3 trunk and a ramp carry none; the
    # stations are centred on a block street and sit a quarter lamp pitch off the lamps on a wider road
    tb = load()
    if tb is not None and "denchu" in tb.assets:
        def road(name, lanes, walk, cls="street", ped=True, style=""):
            base = pm.PointData(uid="")
            base.lanes_fwd = base.lanes_bwd = lanes
            base.left_walk_width = base.right_walk_width = walk
            return pm.RoadData(name, base, (), road_class=cls, ped_access=ped, barrier_style=style)
        assert denchu_kind(tb, road("cho_1", 1, 2.0)) == "lamp" and denchu_kind(tb, road("dori", 2, 4.0)) == "plain"
        assert denchu_kind(tb, road("hondori", 3, 4.0)) is None and denchu_kind(tb, road("r", 1, 0.0, "ramp")) is None
        assert denchu_side("cho_1__2") == denchu_side("cho_1")
        rr = tb.rules
        st = denchu_stations(100.0, "lamp", rr)
        assert st and abs(st[0] - (100.0 - st[-1])) < 1e-9 and st[0] >= rr["denchu_end_clear"], st
        assert denchu_stations(2.0 * rr["denchu_end_clear"] - 1.0, "lamp", rr) == []
        lamps = {rr["lamp_end_clear"] + k * 0.5 * rr["lamp_spacing"] for k in range(40)}       # lamps AND trees
        for stg in (False, True):
            for q in denchu_stations(400.0, "plain", rr, stg):
                assert min(abs(q - x) for x in lamps) >= 0.25 * rr["lamp_spacing"] - 1e-9, q
        a0, a1 = denchu_stations(100.0, "lamp", rr), denchu_stations(100.0, "lamp", rr, True)
        assert a1 and all(min(abs(q - x) for x in a0) >= 0.5 * rr["denchu_spacing"] - 1e-9 for q in a1), (a0, a1)
        assert len(denchu_sides(tb, road("cho_1", 1, 2.0))) == 2 and len(denchu_sides(tb, road("shrine_touge__2", 1, 0.0))) == 1
        assert denchu_kind(tb, road("kaigan", 2, 0.0, "arterial", False, "RAIL")) == "plain"
        assert denchu_kind(tb, road("kaigan", 2, 0.0, "arterial", False)) is None
        # a wire is a closed tube facing out (positive volume), hangs BELOW its two ends, and reaches both poles
        a_, b_ = ((0.0, 0.0, 0.0), (0.0, 1.0)), ((0.0, 30.0, 1.0), (0.0, 1.0))
        tris = wire_span(a_, b_, rr)
        assert len(tris) == len(rr["denchu_wires"]) * 5 * 6, len(tris)
        cx = sum(v[0] for t in tris for v in t) / (3 * len(tris))
        vol = sum(((a[0] - cx) * (b[1] * c[2] - b[2] * c[1]) - a[1] * ((b[0] - cx) * c[2] - b[2] * (c[0] - cx))
                   + a[2] * ((b[0] - cx) * c[1] - b[1] * (c[0] - cx))) for a, b, c in tris) / 6.0
        assert vol > 0.0, vol
        top = max(w["z"] for w in rr["denchu_wires"])
        assert max(v[2] for t in tris for v in t) <= top + 1.0 + 0.05
        assert min(v[1] for t in tris for v in t) == 0.0 and max(v[1] for t in tris for v in t) == 30.0
        # the 腕金 reaches toward the road: forward +Y puts the piece's +X at world +X
        hv = max(w["x"] for w in rr["denchu_wires"])
        assert abs(max(v[0] for t in tris for v in t) - hv) < 0.05
        # ガードレール: a wide street's kerbs, a RAIL-style road's edges, the named mountain road's valley side
        assert guardrail_kind(tb, road("dori", 2, 4.0)) == "kerb" and guardrail_kind(tb, road("cho_1", 1, 2.0)) is None
        assert guardrail_kind(tb, road("kaigan", 2, 0.0, "arterial", False, "RAIL")) == "edge"
        assert guardrail_kind(tb, road("kaigan", 2, 0.0, "arterial", False)) is None
        assert guardrail_kind(tb, road("shrine_touge__3", 1, 0.0, "arterial")) == "drop"
        fq = Furniture()
        assert fq.put(tb, "guardrail", (0.0, 0.0, 0.0), (0.0, 1.0)) and "solid" not in fq.placements[-1]
        assert fq.placements[-1]["breakable"]["pole_len"] == tb.assets["guardrail"]["rail"][2] and fq.clear_of((0, 0, 0), 5.0)
        print("OK: 電柱 kinds, stations off the lamps and trees, wires closed and hanging, guardrail kinds, a rail is "
              "not a solid to the spacing rules")

    # R4: a road along +Y crossing a rail along +X at the origin, 4.5 m of paving each side: one signal on the LEFT
    # of each approach (Japan keeps left), before the track, facing the traffic
    table = load()
    fx = Furniture()
    crossing_signals(fx, table, [("rail", "street", 0.0, 0.0, 0.3, 1.0, 0.0, 0.0, 1.0, 4.5, 4.5)])
    sig = sorted((p_["pos"][:2], p_["fwd"]) for p_ in fx.placements if p_["asset"] == "crossing_signal")
    c_ = table.rules["crossing_track_clear"]
    w_ = 4.5 + table.rules["crossing_side"]
    assert sig == [((-w_, -c_), (0.0, 1.0)), ((w_, c_), (-0.0, -1.0))], sig
    # a 踏切 unit is BREAKABLE (user, 2026-10-05: hit away like a pole): no static box, its marker carries the pole
    assert not fx.collision and all(p_.get("breakable") for p_ in fx.placements if p_["asset"] == "crossing_signal"), \
        "a 踏切 unit is breakable"
    # an oblique road (45 deg) takes the clearance further along itself
    fx = Furniture()
    q = math.sqrt(0.5)
    crossing_signals(fx, table, [("rail", "street", 0.0, 0.0, 0.3, 1.0, 0.0, q, q, 4.5, 4.5)])
    # (the old rule measured `clear` ALONG the road and then stepped the kerb-side offset sideways, which on a 45 deg
    # road put BOTH units 0.9 m from the rail's centreline, i.e. on the tracks)
    # ... and NEITHER unit stands nearer the rail than `clear`, square to it: the kerb-side offset of an oblique road
    # swings one unit back toward the track, and it is pushed out again (the pole 0.26 m off a track, 2026-09-26)
    square = min(abs(p_["pos"][1]) for p_ in fx.placements)
    assert square >= c_ - 1e-9, square
    print("OK: 踏切 signals -- one on the left of each approach, %.1f m before the track, square or oblique" % c_)
    # a synthetic mouth: two arriving lanes heading +X into a junction at x = 50, one lane leaving -X beside them
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
    assert f.counts.get("signal_r") == 1 and not f.counts.get("signal"), f.counts
    rh = [p for p in f.placements if p["asset"] == "signal_r"][0]
    assert table.assets["signal_r"]["hi"][0] < 1.0 < -table.assets["signal_r"]["lo"][0], "the twin's arm reaches -X"
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
    assert not [p for p in f.placements if p.get("breakable") and p["asset"] == "signal"]
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
    # ... and it is pushed OUTBOARD until it is out of every lane. The kerb offset alone puts it at
    # 9.70, which in this junction is 2.18 m from the LEFT-turn connector's centreline -- inside a
    # 2.25 m half lane, i.e. a pole standing in the turn path. That is the island's own defect in
    # miniature (measured 2026-09-22: 12 lanes carried a signal or a lamp), and the remedy is a nudge:
    # the pole ends up clear, on the same kerb, facing the same way.
    authored = 6.75 + 2.25 + table.rules["signal_kerb_offset"]
    idx = _LaneIndex({l["id"]: l for l in kl3})
    margin = _pole_half(table, "signal") + table.rules.get("pole_lane_clear", 0.15)
    assert sigs[0]["pos"][1] > authored + 0.1, sigs
    assert idx.clear_of(sigs[0]["pos"], margin), sigs
    assert not idx.clear_of((sigs[0]["pos"][0], authored, 0.0), margin), "the fixture must carry the defect"
    # A LANE ON ANOTHER LEVEL (2026-10-12): a viaduct 10 m up does not take the kerb under it from a 0.8 m rail or
    # an 8 m lamp's worth of nothing -- asked with a height, only a thing that reaches the deck is "in the lane";
    # asked in plan (the control: no height) the spot under the deck is refused whatever stands there.
    deck = _LaneIndex({"up": {"id": "up", "lane_width": 4.5, "points": [(-50.0, 10.0, 0.0), (50.0, 10.0, 0.0)]}})
    under = (0.0, 0.0, 0.0)
    assert not deck.clear_of(under, 0.1), "the plan-only control must refuse the spot under a deck"
    assert deck.clear_of(under, 0.1, 0.8) and deck.clear_of(under, 0.1, 8.0)
    assert not deck.clear_of(under, 0.1, 8.2) and not deck.clear_of(under, 0.1, 11.67)
    assert deck.clear_of((0.0, 0.0, 12.0), 0.1, 1.0), "a spot on a deck above a lane is not in that lane"
    assert not deck.clear_of((0.0, 0.0, 9.5), 0.1, 1.0), "a spot at the lane's own level is"
    beside = (0.0, 4.5, 0.0)                    # 4.5 m off the deck's centreline: clear of its lane in plan
    assert deck.clear_of(beside, 0.1, 9.0), "a trunk beside a deck is clear of it"
    assert not deck.clear_of(beside, 0.1, 9.0, 3.5), "a 9 m crown 3.5 m wide beside a 10 m deck is in it"
    assert deck.clear_of(beside, 0.1, 6.0, 3.5), "a 6 m tree is under it"
    # THE MEDIAN HEDGE: boxes on a raised median, none at the run's ends, none round a median lamp; off = none.
    class _S(object):
        pass
    hs = _S(); hs.road = _S(); hs.road.name = "hedge"; hs.road.median_style = pm.MED_RAISED
    hs.samples = []
    for k in range(0, 101, 5):
        sm = _S(); sm.pos = (float(k), 0.0, 0.0); hs.samples.append(sm)
    hs.values = [{"rka_med_h": 2.0, "rka_med_z": 0.15}] * len(hs.samples)
    fh = Furniture()
    _median_hedge(fh, table, [hs], lambda s: True, None)
    n_free = fh.counts.get("median_hedge", 0)
    assert n_free >= 10 and len(fh.hedge[table.rules["median_hedge_material"]]) == 12 * n_free, fh.counts
    xs = [t[0][0] for t in fh.hedge[table.rules["median_hedge_material"]]]
    assert min(xs) >= table.rules["median_hedge_end_clear"] - 3.0 and max(xs) <= 100.0 - table.rules["median_hedge_end_clear"] + 3.0
    fl = Furniture()
    assert fl.put(table, "lamp_twin", (50.0, 0.0, 0.15), (1.0, 0.0), "hedge")
    _median_hedge(fl, table, [hs], lambda s: True, None)
    assert fl.counts.get("median_hedge", 0) < n_free, "a hedge must yield to a median lamp"
    t_off = Table(); t_off.rules = dict(table.rules, median_hedge_unit=0.0)
    f0 = Furniture(); _median_hedge(f0, t_off, [hs], lambda s: True, None)
    assert not f0.hedge, "the control: unit 0 lays no hedge"
    # CONTROL: with no index the placer is what it was, and the pole stands in the turn.
    f_ctl = Furniture()
    _signals(f_ctl, table, {l["id"]: l for l in kl3}, [{"id": "j3", "arms": arms}], lambda l: True, None, None)
    ctl = [p for p in f_ctl.placements if p["asset"] == "signal"]
    assert len(ctl) == 1 and abs(ctl[0]["pos"][1] - authored) < 1e-6, ctl
    row = Furniture()
    for k in range(5):
        pos = (k * table.rules["bollard_spacing"], 0.0, 0.0)
        if row.clear_of(pos, table.rules["pole_clearance"], poles_only=True):
            row.put(table, "bollard", pos, (1.0, 0.0))
    assert row.counts.get("bollard") == 5, row.counts
    assert not row.clear_of((0.5, 0.0, 0.0), table.rules["pole_clearance"])
    # ONE pedestrian head per crosswalk end, always on its own pole: a crosswalk end that falls on a vehicle signal
    # pole steps back from the junction until it clears it
    t2 = load()
    f2 = Furniture()
    assert f2.put(t2, "signal", (0.0, 0.0, 0.0), (1.0, 0.0))
    q = _clear_of_signal(f2, t2, (0.3, 0.0, 0.0), (-1.0, 0.0))
    assert q is not None and math.hypot(q[0], q[1]) >= t2.rules["ped_signal_pole_clear"] - 1e-9, q
    assert _clear_of_signal(f2, t2, (5.0, 0.0, 0.0), (-1.0, 0.0))[0] == 5.0
    print("OK: every crosswalk end has its own pedestrian pole, clear of the vehicle signal pole")
    # expressway guide signs: an expressway lane running +x (kit frame; lanekit points are Godot [x, h, -y]) that feeds a
    # ramp, which lands through a junction connector on a street; and a street connector feeding an on-ramp
    if "expwy_sign" in table.assets:
        def ln(i, rc, pts, nxt=(), kind="through", road=None):
            return {"id": i, "road_class": rc, "kind": kind, "road_name": road or i, "lane_width": 4.5,
                    "points": [[x, 10.0, -y] for x, y in pts], "next": list(nxt)}
        L = {l["id"]: l for l in (
            ln("main", "expressway", [(0, 0), (400, 0)], ["off"], road="shuto_x"),
            ln("off", "ramp", [(400, 3), (500, 20)], ["conn"]),
            ln("conn", "street", [(500, 20), (510, 30)], ["street"], kind="connector"),
            ln("street", "street", [(510, 30), (510, 200)], road="naka"),
            ln("sconn", "street", [(600, 0), (610, 5)], ["on"], kind="connector"),
            ln("on", "ramp", [(610, 5), (700, 5)], ["main2"]),
            ln("main2", "expressway", [(700, 5), (900, 5)], road="shuto_y"))}
        sites = expressway_sign_sites(table, L)
        ex = [x for x in sites if x["sign"] == "exit"]
        en = [x for x in sites if x["sign"] == "entrance"]
        assert len(ex) == 1 and ex[0]["dest"] == "naka" and ex[0]["route"] == "shuto_x", sites
        before = float(table.rules.get("expwy_sign_before", 120.0))
        assert abs(ex[0]["pos"][0] - (400 - before)) < 1.0 and ex[0]["pos"][1] > 2.0, ex[0]   # upstream, on the LEFT
        assert len(en) == 1 and en[0]["dest"] == "shuto_y", sites
        plan = expressway_sign_plan(table, {"lanes": list(L.values())})
        assert len(plan["signs"]) == 2 and all(s_["size"][0] > 2.0 for s_ in plan["signs"]), plan
        print("OK: an exit sign 120 m before the diverge on the left, naming the street; an entrance sign on the on-ramp")
    # coordinated signals: a pair 74 m apart on one road shares a controller, the second's offset = the first's +
    # the shared road's group aligned - the travel time; a third far away, or with another cycle, keeps its own
    def jn(i, x, groups, road_group):
        arms = [{"road": "naka", "group": road_group}, {"road": "cross%d" % i, "group": 1 - road_group}]
        return {"id": "j%d" % i, "centre": [x, 0.0, 0.0], "groups": groups, "arms": arms}
    js = [jn(1, 0.0, 2, 0), jn(2, 74.0, 2, 1), jn(3, 400.0, 2, 0), jn(4, 60.0, 3, 0)]
    coordinate(js, 27.0)
    assert js[0]["coord"] == {"root": "j1", "rel": 0.0}
    assert js[1]["coord"]["root"] == "j1" and abs(js[1]["coord"]["rel"] - ((27.0 - 74.0 / COORD_SPEED) % 54.0)) < 1e-3
    assert "coord" not in js[2] and "coord" not in js[3]
    # ---- PLAN.md T4: 止まれ on the arm that must stop, the limit's numerals in the lane
    def ln(i, a, b, limit, nxt=()):
        return {"id": i, "kind": "through", "lane_width": 3.5, "speed_limit": limit, "road_class": "street",
                "points": [g(a), g(b)], "next": list(nxt)}
    t_lanes = [ln("w_F", (-120, -1.75, 0), (-8, -1.75, 0), 50.0), ln("w_R", (-8, 1.75, 0), (-120, 1.75, 0), 50.0),
               ln("e_F", (120, 1.75, 0), (8, 1.75, 0), 50.0), ln("e_R", (8, -1.75, 0), (120, -1.75, 0), 50.0),
               ln("s_F", (1.75, -120, 0), (1.75, -8, 0), 30.0), ln("s_R", (-1.75, -8, 0), (-1.75, -120, 0), 30.0)]
    t_arms = [{"road": "main", "bearing": 180.0, "in_lanes": ["w_F"], "out_lanes": ["w_R"]},
              {"road": "main", "bearing": 0.0, "in_lanes": ["e_F"], "out_lanes": ["e_R"]},
              {"road": "side", "bearing": 270.0, "in_lanes": ["s_F"], "out_lanes": ["s_R"]}]
    t_doc = {"lanes": t_lanes, "junctions": [{"id": "jt", "arms": t_arms}]}
    by_id = {l["id"]: l for l in t_lanes}
    assert not _signalised(table, t_doc["junctions"][0], by_id), "the fixture must be an unsignalised T"
    assert yield_arms(table, by_id, t_doc["junctions"]) == {id(t_arms[2])}, "the slower stem stops, the road does not"
    # equal limits: still the stem (the two arms straight across are the road)
    for l in t_lanes:
        l["speed_limit"] = 30.0
    assert yield_arms(table, by_id, t_doc["junctions"]) == {id(t_arms[2])}
    t_lanes[4]["speed_limit"] = t_lanes[5]["speed_limit"] = 30.0
    for l in t_lanes[:4]:
        l["speed_limit"] = 50.0
    ft = place(table, ([], [], [], []), t_doc, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    assert ft.counts.get("stop_text") == 1, ft.counts
    rr = table.rules
    white = ft.paint["M_LineW"]
    # the legend lies in the stem's arriving lane (x 0 .. 3.5), behind its stop line, and nowhere else
    b_lo = rr["stop_back"] + rr["stop_width"] + rr["stop_text_back"]
    b_hi = b_lo + 3 * rr["stop_text_len"] + 2 * rr["stop_text_gap"]
    in_stem = [t for t in white if all(-8.0 - b_hi - 1e-6 <= v[1] <= -8.0 - b_lo + 1e-6 for v in t)]
    assert len(in_stem) == sum(len(glyphs()[c]["tris"]) // 3 for c in rr["stop_text"]), len(in_stem)
    xs = [v[0] for t in in_stem for v in t]
    assert min(xs) >= rr["stop_text_margin"] - 1e-6 and max(xs) <= 3.5 - rr["stop_text_margin"] + 1e-6, (min(xs), max(xs))
    assert all((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[1][1] - t[0][1]) * (t[2][0] - t[0][0]) > 0 for t in in_stem), \
        "paint faces up"
    # read from the driver's seat (travelling +Y): the first character is the one furthest AHEAD
    first, _tot = legend(rr["stop_text"][0], 1.0, 1.0, 0.0, True)
    tri3, tot3 = legend(rr["stop_text"], 1.0, 1.0, 0.5, True)
    assert abs(tot3 - (len(rr["stop_text"]) * 1.0 + (len(rr["stop_text"]) - 1) * 0.5)) < 1e-9
    assert min(v[1] for t in tri3[:len(first)] for v in t) >= tot3 - 1.0 - 1e-6, "the first character leads"
    # numerals side by side, left to right for the reader, and the whole legend inside its cells
    two, _t = legend("50", 0.8, 3.0, 0.3, False)
    n5 = len(glyphs()["5"]["tris"]) // 3
    assert max(v[0] for t in two[:n5] for v in t) <= 0.0 < min(v[0] for t in two[n5:] for v in t)
    assert legend("?", 1.0, 1.0, 0.0, False) == (None, 0.0), "an unknown character paints nothing"
    # the limit in every through lane long enough, in the regulation colour; control: off paints none
    assert ft.counts.get("speed_text") == 6, ft.counts
    assert len(ft.paint[rr["speed_text_material"]]) == 4 * sum(len(glyphs()[c]["tris"]) // 3 for c in "50") \
        + 2 * sum(len(glyphs()[c]["tris"]) // 3 for c in "30")
    keep = rr["speed_text_len"], rr["stop_text"]
    rr["speed_text_len"], rr["stop_text"] = 0.0, ""
    off = place(table, ([], [], [], []), t_doc, lambda l: True, lambda s: True, lambda j: True, lambda l: "M_LineW")
    rr["speed_text_len"], rr["stop_text"] = keep
    assert "speed_text" not in off.counts and "stop_text" not in off.counts and rr["speed_text_material"] not in off.paint
    print("OK: 止まれ on the stem of an unsignalised T only, read top to bottom; the limit's numerals in each lane")
    print("point_furniture self-test OK")


if __name__ == "__main__":
    self_test()
