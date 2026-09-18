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
  * every junction corner (`point_edges.junction_edge_runs`) -> bollards on the corner's footway.

Nothing is placed where a barrier stands (the road is elevated there, or has no pavement to walk on), nor over
ground more than `max_above_ground` below the lane when a ground grid is given (a manhole on a bridge deck).

The PROPS and the kit decals are the downloaded kit's own pieces (`assets/world_source/kit/furniture.json` names
them). They leave here as PLACEMENTS -- `{asset, path, pos, fwd, scale}` in the KIT frame -- which `point_gltf`
writes as `mmesh_<asset>` nodes carrying `asset_path`, and `WorldBaker` collapses into one MultiMesh per asset.
The stop line and the zebra are PAINT, triangles in the road's own `mark_w` material, because the Japanese
marks are not in the CC0 kit (a zebra with no side bars, a stop line across the arriving lanes only); the kit's
arrows are close enough to use. A piece that must be solid (`collide`) also gets an oriented box in the piece's
`FURN_props-prop-colonly` proxy.

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
TABLE_PATH = os.path.join(REPO, "assets", "world_source", "kit", "furniture.json")

try:
    from . import point_edges as ped, point_solve as ps
except ImportError:
    import point_edges as ped                                                # noqa: E402
    import point_solve as ps                                                 # noqa: E402

#: Object names this module adds to a piece.
PAINT_OBJECT = "FURN__marks_w"
COLLISION_OBJECT = "FURN_props-prop-colonly"
#: `point_mesh.NO_MATERIAL` (restated: importing point_mesh here would be a cycle).
NO_MATERIAL = ""
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
            res = self.kit + a["piece"]
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
            return
        lift = float(a.get("lift", 0.0)) - a["lo"][1] * a["scale"][1]
        self.placements.append({"asset": asset, "path": a["res"], "pos": (pos[0], pos[1], pos[2] + lift),
                                "fwd": fwd, "scale": list(a["scale"])})
        self.counts[asset] = self.counts.get(asset, 0) + 1
        if a.get("collide"):
            # the piece's plan footprint (its X across, its Z along -- forward is -Z), from its own bounds
            half_side = 0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0]
            half_fwd = 0.5 * (a["hi"][2] - a["lo"][2]) * a["scale"][2]
            height = (a["hi"][1] - a["lo"][1]) * a["scale"][1]
            self.collision += _box((pos[0], pos[1], pos[2] + float(a.get("lift", 0.0))), fwd, half_fwd,
                                   half_side, height)

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


def _junction_marks(fur, table, lanes, junctions, mine, mark_mat):
    r = table.rules
    lift = float(r["paint_lift"])
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
            # every lane at the mouth, as (lateral offset, half width, a sampler of back-distance -> point)
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
            if not rows:
                continue

            def z_at(lat, back):
                near = min(rows, key=lambda row: abs(row["lat"] - lat))
                return near["sample"](min(back, near["length"]))[2]

            def plan(lat, back):
                return (anchor[0] + left[0] * lat - fwd[0] * back, anchor[1] + left[1] * lat - fwd[1] * back)

            # ---- the zebra: across the whole carriageway, bars running along the road
            b0, b1 = r["crosswalk_back"]
            if all(row["length"] >= b1 for row in rows) and mine(ins[0]):
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
                if row["length"] >= sb + sw:
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
    r = table.rules
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


def _edge_samples(pts, walk, kerb, wall, spacing, clear):
    """Stations along one edge run: (point, plan direction, walk half width, kerb height), skipping any whose
    segment carries a barrier or no kerb."""
    pts = [tuple(p) for p in pts]
    cum = _lengths(pts)
    out = []
    for s in _stations(cum[-1], spacing, clear):
        p, d, i = _at(pts, cum, s)
        j = min(i + 1, len(pts) - 1)
        if max(float(wall[i]), float(wall[j])) > 0.0:
            continue
        k = min(float(kerb[i]), float(kerb[j]))
        w = min(float(walk[i]), float(walk[j]))
        out.append((p, d, w, k))
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
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, r["planter_spacing"], r["planter_end_clear"]):
                if 2.0 * w < r["planter_min_footway"] or not _grounded(ground, p, r["max_above_ground"]):
                    continue
                a = table.assets["planter"]
                half = 0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0]
                lat = _left(d)
                off = sgn * (r["planter_kerb_gap"] + half)
                fur.put(table, "planter", (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k), d, s.road.name)
    for j in jsolves:
        if not mine_pad(j):
            continue
        for _sfx, pts, walk, kerb, wall, sgn in ped.junction_edge_runs(j):
            for p, d, w, k in _edge_samples(pts, walk, kerb, wall, r["bollard_spacing"], r["bollard_end_clear"]):
                if w <= 0.0 or k <= 0.0:
                    continue
                lat = _left(d)
                off = sgn * r["bollard_inset"]
                fur.put(table, "bollard", (p[0] + lat[0] * off, p[1] + lat[1] * off, p[2] + k), d)


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
    _junction_marks(fur, table, lanes, [junctions[k] for k in sorted(junctions)], mine_lane, mark_mat)
    _lane_props(fur, table, dict(sorted(lanes.items())), mine_lane, ground)
    _edge_props(fur, table, solves, jsolves, bands, mine_run, mine_pad, ground)
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
    # an excluded road gets no manhole
    assert excluded({"exclude_roads": ["shrine_touge*"]}, "shrine_touge_2")
    assert not excluded({"exclude_roads": ["shrine_touge*"]}, "chuo_dori")
    # a lane that is not this piece's gets nothing
    none = place(table, ([], [], [], []), doc, lambda l: False, lambda s: False, lambda j: False, lambda l: "M_LineW")
    assert not none.placements and not none.paint
    print("point_furniture self-test OK")


if __name__ == "__main__":
    self_test()
