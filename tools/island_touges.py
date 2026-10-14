#!/usr/bin/env python3
"""island_touges.py -- the mountain's road: shrine touge, the summit straight, the east descent (PLAN.md 3.29
v13/v14, built by 3.30 L2).

    python3 tools/island_touges.py derive [--land <f32>]     # ONE-SHOT: the alignment + profile -> IslandTouge.json
    python3 tools/island_touges.py add <record> [--from <record>]   # the layout step: the road, into a record
    python3 tools/island_touges.py sculpt <land.f32> <record> <out.f32>   # the mountain shaped to carry it

ONE ROAD, `shrine_touge`, from a T on the city's west arterial up the widened face to the shrine plateau (phase 1,
kept from 3.2d and regraded on the lowered mountain), level across the plateau, up the massif's west flank in
switchbacks to the LEVEL 435 m summit plateau, along the 330 m summit straight, and down the east flank in switchbacks
to a T on the farm arterial. It replaces 3.2d's phase 2 and summit loop: the loop was a dead end's turnaround, and the
two touges now meet at the summit instead (v11 note: "the summit loop becomes the join between the two roads").

The derivation is the plan's sketch (scratchpad `touge/sample3.py`) made a tool, on the repo's own helpers:
`island_v3_terrain.hill_road` walks each flank at <= 10% with 18 m hairpins inside a wedge of that flank, and the
shared `island_shrine_touge` passes round the corners (`fillet`), lay stations (`_stations`), take the profile
(`_profile`: the bench midpoint with the fixed stations held, both grade cones) and round every grade break
(`vertical_curves`). Heights are the LAND grid (`island_reshape.py`), record frame (Godot Y - NET_Y).

`derive` is run once, on purpose, like `island_coast_road.py`'s: the file is the authored alignment and is reviewed.
`add` and `sculpt` are deterministic and run in every layout / terrain build.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import island_reshape as RS                      # noqa: E402
import island_v3_terrain as IT                   # noqa: E402
import island_shrine_touge as ST                 # noqa: E402
import island_plan as PL                         # noqa: E402
from island_roadgen import cut_road, nearest_span, make_junction, NET_Y   # noqa: E402
import point_model as pm                         # noqa: E402
import point_presets as ppr                       # noqa: E402

ALIGNMENT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandTouge.json")
NAME = "shrine_touge"
LIMIT = 0.10
MOUTH = 22.0                    # the road's first/last station this far from its junction (setback re-solves)
LEAD_IN = 40.0                  # level off the junction before climbing (3.2d: a climb at the stop line bent the pad)
# Phase 1's junction. 3.2d's was (-90, 700), where nishi_dori met nogyo_michi; the east descent now comes down to the
# farm arterial 60 m north of it, and on the face between the two there was no room for phase 1's switchbacks (it
# stalled after one hairpin against the east descent's corridor). So phase 1 leaves nishi_dori further south, where
# the widened face is widest, and climbs west between y 250 and 700.
JN_OLD = (-180.0, 250.0)
WEST_FOOT = (-1060.0, 620.0)    # record: the plateau junction, phase 1's top, where the west climb starts (v16: the
                                # moved crest's flank covers the plateau's north half, so on its south half)
EAST_FOOT = (132.0, 729.0)      # record: near the T on the farm arterial (v13)
TOE_Z = 1.2                     # Godot: the widened face "starts" where the ground passes this
TOE_CLEAR = 45.0                # phase 1's legs keep this far west of the toe
FACE_Y = (40.0, 830.0)          # record y: the widened face phase 1 climbs
WEST_WEDGE, EAST_WEDGE = 40.0, 62.0
SEA_CLEAR = 90.0                # the walks keep this far from the sea
# Phase 1 climbs the widened face WEST of this line and the east descent comes down EAST of it: unconstrained, the
# two walks met on the dome's south-east flank and crossed each other 36 m apart in height (measured).
EAST_MIN_Y = 745.0              # record: phase 1 leaves its junction at y ~700 heading south-west; this keeps the
                                # east descent north of it (unconstrained they crossed, 36 m apart in height)
PHASE1_WEDGE = 55.0
ARTERIALS = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")


def phase1_alignment():
    """3.2d's phase 1 (the pre-redo `shrine_touge` and its `__n` continuations), plan points in chain order."""
    lines = PL.pre_redo_lines()
    return [tuple(p) for p in lines["shrine_touge"]]
LANES = {"lanes_fwd": 1, "lanes_bwd": 1}


# ------------------------------------------------------------------ the field (record frame)
class Land(object):
    def __init__(self, path=RS.LAND, smooth_m=0.0):
        g = RS.load(path).astype(np.float64)
        if smooth_m:
            g = RS.box_mean(g, max(1, int(round(smooth_m / RS.STEP))))
        self.h = g                              # Godot rows (z), columns (x), heights Godot Y

    def __call__(self, x, y):
        """Record z (Godot Y - NET_Y), bilinear; the seabed off the grid."""
        fi, fj = (x - RS.X0) / RS.STEP, (-y - RS.Z0) / RS.STEP
        i, j = int(math.floor(fi)), int(math.floor(fj))
        if not (0 <= i < RS.N - 1 and 0 <= j < RS.N - 1):
            return RS.SEABED - NET_Y
        tx, ty = fi - i, fj - j
        h = self.h
        return float((h[j, i] * (1 - tx) + h[j, i + 1] * tx) * (1 - ty)
                     + (h[j + 1, i] * (1 - tx) + h[j + 1, i + 1] * tx) * ty) - NET_Y


def sea_distance(path=RS.LAND):
    land = RS.load(path) > RS.LAND_Z
    d = RS.distance_from(~land, 400.0)
    d[~np.isfinite(d)] = 400.0

    def at(x, y):
        i, j = int(round((x - RS.X0) / RS.STEP)), int(round((-y - RS.Z0) / RS.STEP))
        return float(d[j, i]) if 0 <= i < RS.N and 0 <= j < RS.N else 0.0
    return at


SITE_CLEAR = 25.0               # a walk keeps this far outside a frozen site's footprint (PLAN.md 3.33: v16's re-walk
                                # ran 113 m of phase 1 through Shuri Castle)


def site_free():
    """(x, y) record -> False inside any frozen site (IslandSites.json) grown by SITE_CLEAR."""
    path = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandSites.json")
    rects = []
    if os.path.exists(path):
        for st in json.load(open(path)).get("sites", []):
            a = math.radians(st.get("yaw", 0.0))
            sx, sy = (st.get("size") or [0.0, 0.0])[:2]
            rects.append((st["x"], st["y"], math.cos(a), math.sin(a), sx / 2.0 + SITE_CLEAR, sy / 2.0 + SITE_CLEAR))

    def f(x, y):
        for cx, cy, c, s_, hx, hy in rects:
            dx, dy = x - cx, y - cy
            if abs(dx * c + dy * s_) <= hx and abs(-dx * s_ + dy * c) <= hy:
                return False
        return True
    return f


def arterial_point(arts, at):
    """`(x, y, z)` on the arterial network nearest the plan point `at` -- its OWN surface, not the ground.

    A T MUST ARRIVE AT THE ROAD IT MEETS, and that height is the arterial's, which is not the ground's:
    an arterial is draped and then smoothed (`island_grades`), and the two part company by metres at a
    mountain toe. Measured on v16, the touge's east end was pinned to `raw(EAST_FOOT)` = **2.26 m** while
    `nishi_dori__6` sits at **0.00 m** 19 m away, so the pad between them came out **19.9 % steep** on its
    left movement -- `island_layout.py`'s own `pad_grade` finding (PLAN.md 0.10 / tier B6). The plan point
    is already interpolated along the nearest SPAN for x and y; this returns its z from the same span,
    which is the one place the two can agree by construction.
    """
    name, i, t, _d = nearest_span(arts, at, "")
    pa, pb = (arts.points[u].pos for u in arts.roads[name].points[i:i + 2])
    return tuple(pa[k] + (pb[k] - pa[k]) * t for k in range(3))


def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def wedge(c, dirv, half):
    a0 = math.atan2(dirv[1], dirv[0])

    def f(x, y):
        a = math.atan2(y - c[1], x - c[0])
        return abs((a - a0 + math.pi) % (2 * math.pi) - math.pi) <= math.radians(half)
    return f


def crest_record():
    A, B = RS.crest()
    return (float(A[0]), -float(A[1])), (float(B[0]), -float(B[1]))


# ------------------------------------------------------------------ derive
def derive(land_path):
    raw = Land(land_path)
    walk = Land(land_path, smooth_m=20.0)
    dsea = sea_distance(land_path)
    A, B = crest_record()
    plat = RS.PLATEAU_Z + RS.RAISE - NET_Y
    top = plat - 4.0
    # --- phase 1: from its junction up to the shrine plateau. 3.2d's alignment could NOT be kept (v13 hoped to): the
    # new summit dome covers its upper legs, and read on the lowered mountain it ran up to 130 m under the ground
    # (measured at (-580, 805)). So it is re-walked, inside the flank between its junction and the plateau junction
    # (a wedge from WEST_FOOT toward the junction) and south of the east descent.
    arts = pm.load_network(ARTERIALS)
    jn3 = arterial_point(arts, JN_OLD)
    jn = (jn3[0], jn3[1])
    w1 = wedge(WEST_FOOT, (jn[0] - WEST_FOOT[0], jn[1] - WEST_FOOT[1]), PHASE1_WEDGE)

    free = site_free()

    def inside1(x, y):
        return w1(x, y) and y <= EAST_MIN_Y - 45.0 and dsea(x, y) > SEA_CLEAR and free(x, y)
    plateau_z = raw(*WEST_FOOT)
    walk_top = plateau_z - 25.0          # the plateau falls ~20 m from the junction toward the south-west
    uj = unit(jn, WEST_FOOT)
    lead = (jn[0] + uj[0] * LEAD_IN, jn[1] + uj[1] * LEAD_IN)
    s1 = LEAD_IN
    while s1 < 600.0 and not inside1(jn[0] + uj[0] * s1, jn[1] + uj[1] * s1):
        s1 += 10.0
    start1 = (jn[0] + uj[0] * (s1 + 10.0), jn[1] + uj[1] * (s1 + 10.0))
    climb1 = arcs1 = None
    done = False
    for leg in (600.0, 450.0, 350.0, 250.0):
        for g in (LIMIT, 0.095, 0.09, 0.085, 0.08, 0.075):
            climb1, arcs1 = IT.hill_road(walk, start1, walk_top, g, leg=leg, step=10.0, inside=inside1,
                                         radius=ST.HAIRPIN_R, heading=uj, lookahead=ST.HAIRPIN_R + 10.0)
            if walk(*climb1[-1]) >= walk_top - 1.0:
                done = True
                break
        if done:
            break
    # --- the west climb: across the plateau from its junction, then the massif's west flank
    u = unit(WEST_FOOT, A)
    s = 0.0
    while s < 400.0 and walk(WEST_FOOT[0] + u[0] * s, WEST_FOOT[1] + u[1] * s) < walk(*WEST_FOOT) + 12.0:
        s += 10.0
    west_start = (WEST_FOOT[0] + u[0] * s, WEST_FOOT[1] + u[1] * s)
    ww = wedge(A, (WEST_FOOT[0] - A[0], WEST_FOOT[1] - A[1]), WEST_WEDGE)
    west, arcs_w = IT.hill_road(walk, west_start, top, LIMIT, leg=420.0, step=10.0,
                                inside=lambda x, y: dsea(x, y) > SEA_CLEAR and ww(x, y) and free(x, y),
                                radius=ST.HAIRPIN_R,
                                heading=u, lookahead=ST.HAIRPIN_R + 10.0)
    # --- the east descent, walked UP from the farm arterial and reversed
    v = unit(EAST_FOOT, B)
    dv = math.dist(EAST_FOOT, B)
    s = 0.0
    while s < dv - 200.0 and walk(EAST_FOOT[0] + v[0] * s, EAST_FOOT[1] + v[1] * s) < walk(*EAST_FOOT) + 6.0:
        s += 10.0
    east_start = (EAST_FOOT[0] + v[0] * s, EAST_FOOT[1] + v[1] * s)
    we = wedge(B, (EAST_FOOT[0] - B[0], EAST_FOOT[1] - B[1]), EAST_WEDGE)
    east, arcs_e = IT.hill_road(walk, east_start, top, LIMIT, leg=380.0, step=10.0,
                                inside=lambda x, y: (dsea(x, y) > SEA_CLEAR and we(x, y) and x < 330.0
                                                    and y >= EAST_MIN_Y and free(x, y)),
                                radius=ST.HAIRPIN_R, heading=v, lookahead=ST.HAIRPIN_R + 10.0)
    # --- one line: junction -> phase 1 -> plateau junction -> west -> the summit straight -> east -> junction
    pins, keep, nodrop = set(), set(), set()

    def part(pts, arcs):
        p, inner = ST._protect_hairpins(arcs)
        simp = IT.simplify(pts, 3.0, protect=p)
        keep.update(pts[i] for i in inner)
        nodrop.update(pts[i] for i in p)
        return simp
    line = [jn, lead] + part(climb1, arcs1) + [WEST_FOOT] + part(west, arcs_w) + [A, B] + \
        list(reversed(part(east, arcs_e))) + [(EAST_FOOT[0] + v[0] * 20.0, EAST_FOOT[1] + v[1] * 20.0), EAST_FOOT]
    nodrop |= {A, B, WEST_FOOT, jn, EAST_FOOT}
    line, _arc = ST.fillet(line, keep=keep, nodrop=nodrop)
    st = ST._stations(line)
    ground = [raw(*p) for p in st]
    # BOTH ENDS ARE PINNED TO THE ARTERIAL THEY JOIN, never to the ground under them -- see
    # `arterial_point`. `raw()` here is what put the east mouth 2.26 m over `nishi_dori__6`.
    east3 = arterial_point(arts, EAST_FOOT)
    fixed = {k: jn3[2] for k in range(len(st)) if math.dist(st[k], jn) <= LEAD_IN + 0.5}
    fixed.update({k: east3[2] for k in range(len(st)) if math.dist(st[k], EAST_FOOT) <= 20.5})
    ab = (B[0] - A[0], B[1] - A[1])
    L2 = ab[0] ** 2 + ab[1] ** 2
    for k, p in enumerate(st):
        t = max(0.0, min(1.0, ((p[0] - A[0]) * ab[0] + (p[1] - A[1]) * ab[1]) / L2))
        if math.dist(p, (A[0] + ab[0] * t, A[1] + ab[1] * t)) <= 2.0:
            fixed[k] = plat
    z = ST.vertical_curves(st, ST._profile(st, ground, fixed))
    L = [0.0]
    for a, b in zip(st, st[1:]):
        L.append(L[-1] + math.dist(a, b))
    grades = [abs(z[i + 1] - z[i]) / max(1e-6, L[i + 1] - L[i]) for i in range(len(st) - 1)]
    cf = [z[i] - ground[i] for i in range(len(st))]
    rep = {"length_m": round(L[-1]), "stations": len(st), "max_grade_pct": round(100 * max(grades), 1),
           "max_fill_m": round(max(cf), 1), "max_cut_m": round(-min(cf), 1),
           "hairpins": {"phase1": len(arcs1) // IT.HAIRPIN_POINTS, "west": len(arcs_w) // IT.HAIRPIN_POINTS,
                        "east": len(arcs_e) // IT.HAIRPIN_POINTS},
           "reached": {"phase1": walk(*climb1[-1]) >= walk_top - 1.0, "west": walk(*west[-1]) >= top - 1.0,
                       "east": walk(*east[-1]) >= top - 1.0},
           "z": [round(min(z), 1), round(max(z), 1)]}
    doc = {"note": "PLAN.md 3.30 L2: derived once by tools/island_touges.py derive from the land grid; the authored "
                   "alignment of shrine_touge, from its junction on the city's west arterial to its T on the farm "
                   "arterial. Re-derive only on purpose.",
           "junction": [round(jn[0], 2), round(jn[1], 2)], "east_junction": list(EAST_FOOT), "report": rep,
           "stations": [[round(p[0], 2), round(p[1], 2), round(zz, 2)] for p, zz in zip(st, z)]}
    with open(ALIGNMENT, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("island_touges: %s -> %s" % (json.dumps(rep), os.path.relpath(ALIGNMENT, ROOT)))
    ok = max(grades) <= LIMIT + 1e-3 and all(rep["reached"].values())
    return 0 if ok else 1


# ------------------------------------------------------------------ add
def add(net, doc=None):
    doc = doc or json.load(open(ALIGNMENT))
    if NAME in net.roads:
        raise SystemExit("island_touges: %s is already in the record" % NAME)
    sts = [tuple(p) for p in doc["stations"]]
    arms = []
    for c in (tuple(doc["junction"]), tuple(sts[-1][:2])):
        name = nearest_span(net, c, "")[0]
        arms.append(list(cut_road(net, c, name, MOUTH)))
    jn, ej = tuple(doc["junction"]), tuple(sts[-1][:2])
    body = [p for p in sts if math.dist(p[:2], jn) >= MOUTH - 0.5 and math.dist(p[:2], ej) >= MOUTH - 0.5]
    road = net.add_road(pm.RoadData(NAME, pm.PointData(uid=""), ()))
    road.road_class = "arterial"
    road.base.lanes_fwd, road.base.lanes_bwd = 1, 1
    prev = None
    for q in body:
        p = net.add_station(road, q)
        p.lanes_fwd, p.lanes_bwd = 1, 1
        if prev is not None:
            net.link(prev, p.uid)
        prev = p.uid
    make_junction(net, arms[0] + [road.points[0]], signal=False)
    make_junction(net, arms[1] + [road.points[-1]], signal=False)
    ppr.apply_preset(net, NAME, "mountain")                         # S15: no kerb, a 0.75 m shoulder
    return "%s: %d stations, %.0f m, T's at %s and %s" % (NAME, len(road.points), doc["report"]["length_m"],
                                                        [round(v) for v in jn], [round(v) for v in ej])


# ------------------------------------------------------------------ the second mountain road and the 林道 (S15)
#: S15 (user, 2026-10-14: "north road + (A) 中腹林道"; reviewers: no road round the whole mountain, ONE north road
#: summit -> north coast on long legs, <= 10 %, R 18, 4-6 hairpins, T's only). Each is derived ONCE into its own file (IslandTouge_<name>.json) with
#: shrine_touge held fixed (its alignment is read, never rewritten), and `add` lays it after shrine_touge. Its ends are
#: Ts: `ends` = [(record (x, y), the road-name prefix the T is cut in)] in chain order.
#: kita_touge: from the cape T on the north coast road (the game designer's 10-3 point; its 4th arm is the cape's 道の駅,
#: PLAN [I3]) up the north face -- measured on the land grid 2026-10-14: a 90 deg wedge from the summit's east end with
#: 800 m legs gives 4.4 km and 6 hairpins and reaches the summit level (60 deg / 500 m legs: 7.4 km, 13 hairpins, stalled
#: at 367 m against shrine_touge's west climb) -- then LEVEL onto a T on the summit straight (the 展望 point).
EXTRA = {
    "kita_touge": dict(file="IslandTouge_kita_touge.json", foot=(-292.0, 1952.0), foot_road="kaigan_dori",
                       wedge=90.0, leg=800.0, clear=70.0, along=-1.0, grade=0.095,
                       lock_foot=True),
}
#: (the 中腹林道 -- from the shrine plateau (-1005, 713) to the east descent (-316, 1009) along the 220 m contour -- was
#: CUT from S15, measured 2026-10-14: the straight between its ends crosses the summit dome (395 m), and a shortest-path
#: search on a 10 m grid round it found NO route clear of shrine_touge even at 30 m: both ends sit inside stacks of the
#: touge's own switchbacks, so any 林道 there crosses another touge leg -- a 4-arm crossing on a 10 % leg, which the
#: review ruled out. A re-sited 林道 needs ends outside the switchback stacks; see PLAN.md S15.)
EXTRA_ORDER = ("kita_touge",)
RECORD = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.roads.json")


def _touge_clear(d):
    st = [tuple(p[:2]) for p in json.load(open(ALIGNMENT))["stations"]]
    grid = {}
    for p in st:
        grid.setdefault((int(p[0] // 50), int(p[1] // 50)), []).append(p)
    k = int(math.ceil(d / 50.0))

    def f(x, y):
        gx, gy = int(x // 50), int(y // 50)
        for i in range(-k, k + 1):
            for j in range(-k, k + 1):
                for q in grid.get((gx + i, gy + j), ()):
                    if (q[0] - x) ** 2 + (q[1] - y) ** 2 < d * d:
                        return False
        return True
    return f, st


def _on_touge(st_doc, xy):
    """(x, y, z) of the touge's own alignment at its station nearest `xy` (a T arrives at the road it meets)."""
    return min((tuple(p) for p in st_doc), key=lambda p: math.dist(p[:2], xy))


def _finish(name, line, keep, nodrop, raw, fixed_xy_z, ends, report):
    line, _arc = ST.fillet(line, keep=keep, nodrop=nodrop)
    st = ST._stations(line)
    ground = [raw(*p) for p in st]
    fixed = {}
    for xy, z, reach in fixed_xy_z:
        fixed.update({k: z for k in range(len(st)) if math.dist(st[k], xy) <= reach})
    z = ST.vertical_curves(st, ST._profile(st, ground, fixed))
    L = [0.0]
    for a, b in zip(st, st[1:]):
        L.append(L[-1] + math.dist(a, b))
    grades = [abs(z[i + 1] - z[i]) / max(1e-6, L[i + 1] - L[i]) for i in range(len(st) - 1)]
    report.update({"length_m": round(L[-1]), "stations": len(st), "max_grade_pct": round(100 * max(grades), 1),
                   "z": [round(min(z), 1), round(max(z), 1)]})
    doc = {"note": "S15: derived once by tools/island_touges.py derive --extra %s with shrine_touge held fixed. "
                   "Re-derive only on purpose." % name,
           "ends": [{"at": [round(xy[0], 2), round(xy[1], 2)], "on": on} for xy, on in ends], "report": report,
           "stations": [[round(p[0], 2), round(p[1], 2), round(zz, 2)] for p, zz in zip(st, z)]}
    path = os.path.join(os.path.dirname(ALIGNMENT), EXTRA[name]["file"])
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("island_touges: %s %s -> %s" % (name, json.dumps(report), os.path.relpath(path, ROOT)))
    return 0 if max(grades) <= LIMIT + 1e-3 and report.get("reached", True) else 1


def _self_crossings(line):
    """Where a polyline crosses itself (non-adjacent spans; hill_road never looks at its own earlier legs, and a lead
    along the coast then a switchback back over it crossed at grade -- dry layout mo2)."""
    out = []
    for i in range(len(line) - 1):
        for j in range(i + 2, len(line) - 1):
            (ax, ay), (bx, by), (cx, cy), (dx, dy) = line[i][:2], line[i + 1][:2], line[j][:2], line[j + 1][:2]
            den = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
            if abs(den) < 1e-9:
                continue
            t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / den
            u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / den
            if 0.0 < t < 1.0 and 0.0 < u < 1.0:
                out.append([round(ax + (bx - ax) * t), round(ay + (by - ay) * t)])
    return out


def derive_north(land_path):
    spec = EXTRA["kita_touge"]
    raw, walk, dsea, free = Land(land_path), Land(land_path, smooth_m=20.0), sea_distance(land_path), site_free()
    A, B = crest_record()
    plat = RS.PLATEAU_Z + RS.RAISE - NET_Y
    clear, touge = _touge_clear(spec["clear"])
    rec = pm.load_network(RECORD)
    name, i, t, _d = nearest_span(rec, spec["foot"], spec["foot_road"])
    pa, pb = (rec.points[u].pos for u in rec.roads[name].points[i:i + 2])
    foot = tuple(pa[k] + (pb[k] - pa[k]) * t for k in range(3))
    # THE NORTH COAST IS THE MASSIF'S 45 deg FLANK everywhere (measured: ~1 m of rise per metre inland all along the
    # coast road): a walk started inland stood 17-29 m over the T and the lead-in climbed 14-19 %. The road leaves the
    # coast road ALONG it (`along`: -1 = toward the chain's start) and climbs across the slope, as a real 峠 does
    cu = unit(pa[:2], pb[:2])
    v = (cu[0] * spec["along"], cu[1] * spec["along"])
    start = (foot[0] + v[0] * LEAD_IN, foot[1] + v[1] * LEAD_IN)
    wb = wedge(B, (foot[0] - B[0], foot[1] - B[1]), spec["wedge"])
    pts, arcs = IT.hill_road(walk, start, plat - 4.0, spec["grade"], leg=spec["leg"], step=10.0, radius=ST.HAIRPIN_R,
                             inside=lambda x, y: ((dsea(x, y) > 15.0 if math.dist((x, y), foot[:2]) < 350.0
                                                   else dsea(x, y) > 40.0)
                                                  and (wb(x, y) or math.dist((x, y), foot[:2]) < 350.0)
                                                  and free(x, y) and clear(x, y)),
                             heading=v, lookahead=ST.HAIRPIN_R + 10.0)
    end = pts[-1]
    # the T on the summit straight: the walk's end projected square onto A -> B
    ab = (B[0] - A[0], B[1] - A[1])
    tt = max(0.1, min(0.85, ((end[0] - A[0]) * ab[0] + (end[1] - A[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)))
    want = (A[0] + ab[0] * tt, A[1] + ab[1] * tt)
    # ON the touge's own level summit stations, short of B's corner (the crest line A -> B is the touge's design line,
    # and at t 0.95 the built road had already turned off it: the T missed it by 36 m -- dry layout mo1)
    summit = [p for p in json.load(open(ALIGNMENT))["stations"] if p[2] >= plat - 0.5]
    top = tuple(min(summit, key=lambda p: math.dist(p[:2], want))[:2])
    p_, inner = ST._protect_hairpins(arcs)
    simp = IT.simplify(pts, 3.0, protect=p_)
    keep = {pts[i] for i in inner}
    nodrop = {pts[i] for i in p_} | {foot[:2], top}
    lead = (foot[0] + v[0] * LEAD_IN, foot[1] + v[1] * LEAD_IN)
    line = [foot[:2], lead] + simp + [top]
    rep = {"hairpins": len(arcs) // IT.HAIRPIN_POINTS, "reached": walk(*end) >= plat - 5.0,
           "self_crossings": _self_crossings(line)}
    rep["reached"] = rep["reached"] and not rep["self_crossings"]
    return _finish("kita_touge", line, keep, nodrop, raw,
                   [(foot[:2], foot[2], LEAD_IN + 0.5), (top, plat, 2.0)],
                   [(foot[:2], spec["foot_road"]), (top, NAME)], rep)


def add_extra(net):
    """Every EXTRA road whose alignment file exists, after shrine_touge: a 1+1 road with a T cut at each end."""
    out = []
    for name in EXTRA_ORDER:
        path = os.path.join(os.path.dirname(ALIGNMENT), EXTRA[name]["file"])
        if not os.path.exists(path) or name in net.roads:
            continue
        doc = json.load(open(path))
        sts = [tuple(p) for p in doc["stations"]]
        arms = []
        for e in doc["ends"]:
            c = tuple(e["at"])
            rn = nearest_span(net, c, e["on"])[0]
            arms.append(list(cut_road(net, c, rn, MOUTH)))
        e0, e1 = tuple(doc["ends"][0]["at"]), tuple(doc["ends"][1]["at"])
        body = [p for p in sts if math.dist(p[:2], e0) >= MOUTH - 0.5 and math.dist(p[:2], e1) >= MOUTH - 0.5]
        road = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
        road.road_class = "arterial"
        road.base.lanes_fwd, road.base.lanes_bwd = 1, 1
        prev = None
        for q in body:
            p = net.add_station(road, q)
            p.lanes_fwd, p.lanes_bwd = 1, 1
            if prev is not None:
                net.link(prev, p.uid)
            prev = p.uid
        make_junction(net, arms[0] + [road.points[0]], signal=False)
        make_junction(net, arms[1] + [road.points[-1]], signal=False)
        if EXTRA[name].get("lock_foot"):
            # a SHALLOW T: the 45 deg coast leaves the road only one low line, along the slope's toe beside the coast
            # road, so the arm leaves at a few degrees off it; solved, its mouth was thrown 70 m out and folded
            # kaigan_dori (dry layout mo3). All three mouths keep their laid places (the market's J / K trick)
            for u in arms[0] + [road.points[0]]:
                net.points[u].setback_locked = True
        ppr.apply_preset(net, name, "mountain")
        out.append("%s: %d stations, %.0f m" % (name, len(road.points), doc["report"]["length_m"]))
    return "; ".join(out)


# ------------------------------------------------------------------ sculpt
ROAD_HALF = 8.0
VERGE = 6.0
CLEARANCE = 0.10
FILL_SLOPE, CUT_SLOPE = 1.5, 1.0
SCULPT_REACH = 120.0
BLEND = 8.0


def sculpt(H, segs):
    """`island_shrine_touge.sculpt` on the whole-world grid: the ground within the road + verge is the road less
    CLEARANCE, a fill / cut batter runs only as wide as its own fill / cut, and fades back over BLEND; the NEAREST
    segment decides; the sea is never filled. `segs` are ((x, y, z), (x, y, z)) in the record frame."""
    H = H.astype(np.float64)
    best_d = np.full(H.shape, np.inf)
    best_z = np.zeros(H.shape)
    best_c = np.zeros(H.shape)
    W = ROAD_HALF + VERGE
    for a, b in segs:
        ax, az = a[0], -a[1]
        bx, bz = b[0], -b[1]
        x0, x1 = min(ax, bx) - SCULPT_REACH - W, max(ax, bx) + SCULPT_REACH + W
        z0, z1 = min(az, bz) - SCULPT_REACH - W, max(az, bz) + SCULPT_REACH + W
        i0, i1 = max(0, int((x0 - RS.X0) / RS.STEP)), min(RS.N, int((x1 - RS.X0) / RS.STEP) + 1)
        j0, j1 = max(0, int((z0 - RS.Z0) / RS.STEP)), min(RS.N, int((z1 - RS.Z0) / RS.STEP) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        jj, ii = np.mgrid[j0:j1, i0:i1]
        x, z = RS.X0 + ii * RS.STEP, RS.Z0 + jj * RS.STEP
        dx, dz = bx - ax, bz - az
        l2 = dx * dx + dz * dz or 1.0
        t = np.clip(((x - ax) * dx + (z - az) * dz) / l2, 0.0, 1.0)
        px, pz = ax + dx * t, az + dz * t
        d = np.hypot(x - px, z - pz)
        zr = a[2] + (b[2] - a[2]) * t + NET_Y - CLEARANCE
        ci = np.clip(np.round((px - RS.X0) / RS.STEP).astype(int), 0, RS.N - 1)
        cj = np.clip(np.round((pz - RS.Z0) / RS.STEP).astype(int), 0, RS.N - 1)
        win = best_d[j0:j1, i0:i1]
        nearer = d < win
        win[nearer] = d[nearer]
        best_z[j0:j1, i0:i1][nearer] = zr[nearer]
        best_c[j0:j1, i0:i1][nearer] = H[cj, ci][nearer]
    near = best_d <= SCULPT_REACH + W
    over = np.maximum(best_d - W, 0.0)
    fill = np.maximum(best_z - best_c, 0.0)
    cut = np.maximum(best_c - best_z, 0.0)
    target = np.clip(H, best_z - over / FILL_SLOPE, best_z + over / CUT_SLOPE)
    reach = np.where(target > H, fill * FILL_SLOPE, cut * CUT_SLOPE) + 1.0
    w = 1.0 - np.clip((over - reach) / BLEND, 0.0, 1.0)
    w = w * w * (3.0 - 2.0 * w)
    w[best_d <= W] = 1.0
    out = H.copy()
    out[near] = (H + w * (target - H))[near]
    sea = H <= 0.0
    out[sea] = np.minimum(out[sea], H[sea])
    return out.astype(np.float32)


def cmd_sculpt(land_path, record, out):
    net = pm.load_network(record)
    segs = []
    for name, r in net.roads.items():
        if any(name == m or name.startswith(m + "__") for m in PL.MOUNTAIN_ROADS):      # every mountain road
            pts = [net.points[u].pos for u in r.points]
            segs += list(zip(pts, pts[1:]))
    H = RS.load(land_path)
    g = sculpt(H, segs)
    d = g - H
    print("island_touges: sculpt raised %d cells (max %.1f m), lowered %d cells (max %.1f m) -> %s"
          % ((d > 0.05).sum(), d.max(), (d < -0.05).sum(), -d.min(), out))
    g.tofile(out)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["derive", "add", "sculpt"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--land", default=RS.LAND)
    ap.add_argument("--from", dest="src", default="")
    ap.add_argument("--extra", default="", help="derive one of EXTRA (kita_touge) instead")
    a = ap.parse_args(argv)
    if a.cmd == "derive":
        if a.extra == "kita_touge":
            return derive_north(a.land)
        return derive(a.land)
    if a.cmd == "add":
        out = a.args[0]
        net = pm.load_network(a.src or out)
        print("island_touges: " + add(net))
        extra = add_extra(net)
        if extra:
            print("island_touges: " + extra)
        pm.save_network(net, out)
        return 0
    cmd_sculpt(a.args[0], a.args[1], a.args[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
