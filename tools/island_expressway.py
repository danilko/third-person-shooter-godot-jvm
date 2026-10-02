#!/usr/bin/env python3
"""island_expressway.py -- the island's elevated expressway (PLAN.md 3.13 step 2).

    python3 tools/island_expressway.py <record> --from <base record> [--check]

Writes into `<record>` the base record (the island WITHOUT the expressway, e.g. `git show HEAD:...`) plus the
expressway, so a re-run is exact: every road this tool makes is named `shuto_*`, and every ground road it cuts to
land a ramp keeps its name with a `__ic<n>` second half. With no `--from` the record itself is the base, which is
refused if it already carries a `shuto_` road.

What it builds (record frame: x east, y north = -Godot z, z up; see CLAUDE.md "Road types"):

* **C1**, the city loop (`shuto_c1*`): a rounded rectangle inside the arterial frame (chuo_dori west, hama_dori
  east, rinkai_dori south, nogyo_michi north), a closed ring of roads joined at joints.
* **The Wangan** (`shuto_wangan`): the MAINLINE, one divided road from a T on the west-coast dike road along the whole
  south coast (over Harbour station) and up the waterfront to a joint by the airport spur, where T1 / T2 take it to and
  from the spur (the airport). `shuto_wangan_c1`, the CONNECTOR north over chuo_dori's median to C1's west side, is a
  branch: Y1 (Wangan EB ->) and Y2 (-> Wangan WB) are its two halves at its south joint.
* **The airport spur** (`shuto_spur*`): two one-way carriageways from the loop JCT on C1 past the Wangan's junction,
  JOINED into ONE divided road (`shuto_spur`) before the Rainbow Bridge, across its UPPER deck (24 m, the rail on the
  lower deck right under it), then on the airport island a peel west off the rail, a descent, a U-turn and the
  one-way forecourt loop `kuko_rotary` beside the Airport station and the terminal's curb (2026-09-29).
* The interchanges down to the ground roads (diamonds) and the JCTs between the expressways.

Deck heights are DERIVED: the highest natural ground within the deck's half width, plus `CLEAR`, then a grade cone
(`GRADE`) so the deck never climbs faster than a Shuto road. No pier stands on another road: wherever a deck passes
within 3 m of a road more than 4 m below it, the BUILD drops that column (`point_mesh.pier_on_road`), so the
columns stand either side of the road it crosses and the span is only as long as that road needs.

`--check` exits 1 unless the Road Kit gate is 0 errors, the flow has no broken / misjoined / unreached lanes, and
every expressway surface clears every road it crosses by `CLEARANCE` (measured on the built mesh, as the
interchange template is: `roadkit_interchange.crossings`).
"""
import copy
import json
import math
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import point_model as pm        # noqa: E402
import point_presets as pr      # noqa: E402
import point_record_ops as ro   # noqa: E402
import point_validate as pv     # noqa: E402
from island_roadgen import *    # noqa: E402,F401,F403

PIECES = os.path.join(ROOT, "assets", "world_source", "pieces")
RECORD = os.path.join(PIECES, "IslandRoads.roads.json")

CLEARANCE = 5.5       # surface over surface where two roads cross (4.7 m + a 0.8 m deck)
TAPER = 0.25          # expressway taper_factor: the compressed world's choice, a quarter of the book's taper


# ------------------------------------------------------------------------------------------ the layout

import island_plan as PL        # noqa: E402  the final plan's numbers (PLAN.md 3.30 L2): C1 moved with the city
C1_CORNERS = PL.C1_CORNERS
C1_RADIUS = 180.0
C1_ARC_STEP = 10.0      # C1's corner arcs are sampled this finely, so the kit sweeps a true R180 (at the default 30 m
                        # chords, with stations dropped by the ramp clearances, the swept lanes read R 118-122)
C1_Y = C1_CORNERS[0][1]
SOUND_WALL = 3.0        # a city expressway's sound walls (防音壁)
# ONLY where C1 is central to the city (user): its SOUTH half faces downtown and the station area; the north half faces
# the farmland and the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the
# bridge. The ring's roads south of its east / west cuts (see `build`): c1 (775 -> east y 150), c1__5 (west y 375 ->
# south x 400, round the SW corner) and c1__6 (south x 400 -> 775).
RAMP_PIER = "RKA_PIER_round"
# (SOUND_WALL_ROADS is by geometry now: every C1 road whose stations lie mostly on the south half, see `main`)
C1_SPEED = 60.0         # km/h: the inner ring is signed below the outer network's 80, as 首都高's C1 is (50-60 in the
                        # core, 80 outside). Set AFTER the build, so the aux-slot tapers stay sized for 80 (longer)
RAMP_LANES = 2          # an exit, and a JCT ramp that IS a carriageway (a joint), is two lanes wide (user, 3.13: racing)
ENTRY_LANES = 1         # an ENTRANCE from the city (a diamond, Y3, Y4) merges as ONE lane (2026-10-01 review: a 2-lane
                        # entrance onto a 2-lane road forced a merge within 108-164 m)
EXIT_GROUND_LANES = 1   # an exit straight into a signalised ground junction (the Suburb exit)
BRIDGE_Z = 24.0        # the Rainbow Bridge's upper deck (library_landmarks.RB_ROAD_UPPER; 32 until 2026-09-29)
PEEL_HOLD = 30.0            # past the bridge's south end the deck height is held this far, clear of the rail below
PEEL_Y = -1590.0            # the road peels WEST off the rail along this y (the station's north end is at -1625)
PEEL_R = 45.0
U_X = 870.0                 # the descent runs west to here, then a U-turn (two corners of U_R) back east
U_R = 40.0
FORE_Y = -1667.5            # ...along this y to the forecourt loop's junction
FORE_J = (1060.0, -1667.5)  # the junction: the middle of the loop's west side
FORE_BOX = (1060.0, -1710.0, 1215.0, -1625.0)   # the loop's STATIONS (its inner edge): x0, y0, x1, y1 (record frame).
                            # The east side's lanes and 4 m kerb end 6 m short of the station's west wall (x 1234.65),
                            # the south side's under the terminal's curb canopy (z 1725), the north side 10 m from the
                            # descending spur
FORE_R = 15.0
AIR_Z = 8.0            # the airport island's ground
SPLIT_CLEAR = 15.0     # the unpiered first span of each ramp at a joint split (three hammerheads would stand together)

DIAMOND_X = PL.DIAMOND_X
DIAMOND_ROAD = PL.DIAMOND_ROAD              # the trunk the diamond lands on
DIAMOND_J = PL.DIAMOND_J                    # its two junctions (inside C1, outside C1)
MOUTH = 26.0
DIAMOND_PART = 17.0    # a diamond ramp's centreline this far off C1's: its band (4.5 m) has parted from C1's (~11)


PLAN_FACED = {}         # uid -> (plan id, arclength): stations given their design tangent (plan_face); thinning may
PLANS = {}              # still drop them. plan id -> (plan, cum, closed): what road_radius measures between two of them


def plan_face(net, uid, plan, cum, closed):
    """Freeze station `uid` on its design alignment's TANGENT (`plan`, arclengths `cum`): the kit then sweeps the
    designed arc between stations however far apart they are. With chord (AUTO) facings, a corner whose stations were
    thinned or cleared for a ramp's taper was swept as a Bezier ~5 m inside the arc (review P1-3, 2026-10-01: C1's R180
    corners read R 118-122, the Wangan's R150 at the Suburb exit R 64). A station already frozen (a joint) keeps its
    facing; the deck's climb through the station is the kit's (point_profile.stations)."""
    p = net.points[uid]
    if p.tangent_mode == pm.MANUAL:
        return
    s = s_on(plan, cum, p.pos[:2]) if closed else _s_open(plan, cum, p.pos[:2])
    a = at_s(plan, cum, s - 0.5, closed) if (closed or s > 0.5) else at_s(plan, cum, s, closed)
    b = at_s(plan, cum, s + 0.5, closed) if (closed or s < cum[-1] - 0.5) else at_s(plan, cum, s, closed)
    if math.dist(a, b) < 1e-6:
        return
    freeze(net, uid, (b[0] - a[0], b[1] - a[1]))
    PLANS.setdefault(id(plan), (plan, cum, closed))
    PLAN_FACED[uid] = (id(plan), s)


def _s_open(plan, cum, xy):
    best, bs = 1e18, 0.0
    for i in range(len(plan) - 1):
        a, b = plan[i], plan[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-9:
            continue
        t = max(0.0, min(1.0, ((xy[0] - a[0]) * (b[0] - a[0]) + (xy[1] - a[1]) * (b[1] - a[1])) / (L * L)))
        d = math.hypot(a[0] + (b[0] - a[0]) * t - xy[0], a[1] + (b[1] - a[1]) * t - xy[1])
        if d < best:
            best, bs = d, cum[i] + t * L
    return bs


def bezier(p0, d0, p1, d1, n):
    """n+1 points on the cubic from p0 (leaving along d0) to p1 (arriving along d1), heights linear."""
    L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    l0, l1 = math.hypot(*d0) or 1.0, math.hypot(*d1) or 1.0
    k = 0.42 * L
    c0 = (p0[0] + d0[0] / l0 * k, p0[1] + d0[1] / l0 * k)
    c1 = (p1[0] - d1[0] / l1 * k, p1[1] - d1[1] / l1 * k)
    out = []
    for m in range(n + 1):
        t = m / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        z = p0[2] + (p1[2] - p0[2]) * t
        out.append((a * p0[0] + b * c0[0] + c * c1[0] + d * p1[0], a * p0[1] + b * c0[1] + c * c1[1] + d * p1[1],
                    round(z, 2)))
    return out


def s_on(plan, cum, xy):
    """Arclength along the closed `plan` of its point nearest `xy`."""
    best, bs = 1e18, 0.0
    seq = plan + [plan[0]]
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        t = max(0.0, min(1.0, ((xy[0] - a[0]) * (b[0] - a[0]) + (xy[1] - a[1]) * (b[1] - a[1])) / (L * L)))
        d = math.hypot(a[0] + (b[0] - a[0]) * t - xy[0], a[1] + (b[1] - a[1]) * t - xy[1])
        if d < best:
            best, bs = d, cum[i] + t * L
    return bs


def path_z(pts, anchors):
    """A plan path (record x, y) with heights: linear in arclength between the `anchors` {index: height}, and every
    point after the last anchor / before the first held at it. Returns [(x, y, z)]."""
    return _profile(pts, anchors)


def fillet(corners, radii, step=15.0):
    """A plan polyline through `corners` with each interior corner filleted (radius per corner), densified every
    `step` m -- a ramp's path. Returns [(x, y)] including both ends."""
    pl = rounded_polygon(corners, radii, closed=False, full_ends=True, arc_step=4.0)
    cum = arclen(pl, False)
    n = max(2, int(math.ceil(cum[-1] / step)))
    return [at_s(pl, cum, cum[-1] * k / n, False) for k in range(n + 1)]


def mouth_of(net, name):
    """A ramp's mouth station (its first: branch_ramp builds mouth -> far, exits and entrances alike)."""
    return net.points[net.roads[name].points[0]].pos


def on_curve(net, name, path3, lead=40.0):
    """Put the ramp's FAR station (the second, placed by branch_ramp) ON its curve `path3` [(x, y, z)], which starts
    at the mouth, and return the rest of the curve after it: the curve then starts at the gore itself, with no kink
    where branch_ramp's offset station met it (user, 2026-09-30: smooth curves, no jumps)."""
    cum = arclen([q[:2] for q in path3], False)
    k = next((i for i, c in enumerate(cum) if c >= min(lead, cum[-1] / 4.0)), 1)
    fu = net.roads[name].points[1]
    net.points[fu].pos = tuple(path3[k])
    return path3[k + 1:]


def _min_radius(path):
    """The smallest plan radius along a path (circumradius of sample triples at least 6 m apart; a straight is inf)."""
    pts = [path[0]]
    for q in path[1:]:
        if math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) >= 6.0:
            pts.append(q)
    best = 1e9
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        ab, bc, ac = math.dist(a[:2], b[:2]), math.dist(b[:2], c[:2]), math.dist(a[:2], c[:2])
        cr = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if cr > 1e-6:
            best = min(best, ab * bc * ac / (2.0 * cr))
    return best


def _dist_line(q, line):
    (ax, ay), (bx, by) = line
    L = math.hypot(bx - ax, by - ay)
    return abs((bx - ax) * (ay - q[1]) - (by - ay) * (ax - q[0])) / L


def designed_ramp(m, t0, e, te, side, crosses=(), along=None, sep=11.0, z0=0.0, zend=0.0, fly=None,
                  grade=0.05, step=8.0, avoid=None, maxturn=70.0):
    """ONE designed ramp alignment from the gore `m` (leaving along the unit `t0`) to `e` (arriving along `te`), the
    way a Japanese JCT ramp is drawn (user, 2026-09-30: no kink, no wiggle, high-speed curves): a gentle diverge arc
    turning `side` (+1 left of t0, -1 right, 0 none), a straight, a large arc back across, a straight, a large arc onto
    `te`. The corners are searched for the largest smallest radius; a ramp that must fly over `crosses` (lines) first
    holds level beside `along` (the mainline line) until it is `sep` m off it, then climbs at `grade` to `fly` before
    the first crossing and comes down to `zend` after the last. Returns (path3, min radius)."""
    def rot(v, deg):
        a = math.radians(deg)
        return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))
    best = None
    thetas = [0.0] if side == 0 else [4.0, 7.0, 10.0, 14.0, 18.0, 24.0, 30.0]
    for a in (15.0, 25.0, 45.0, 70.0, 100.0):
        A = (m[0] + t0[0] * a, m[1] + t0[1] * a)
        for th in thetas:
            d1 = rot(t0, side * th)
            for l1 in ((0.0,) if side == 0 else (20.0, 40.0, 60.0, 80.0, 100.0, 140.0, 190.0)):
                B = (A[0] + d1[0] * l1, A[1] + d1[1] * l1)
                for c in (20.0, 30.0, 50.0, 80.0, 120.0, 170.0, 230.0):
                    C = (e[0] - te[0] * c, e[1] - te[1] * c)
                    pts = [m[:2], A, B, C, e[:2]] if l1 > 0 else [m[:2], A, C, e[:2]]
                    turns = []
                    ok = True
                    for i in range(1, len(pts) - 1):
                        u = (pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
                        v = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                        nu, nv = math.hypot(*u), math.hypot(*v)
                        if nu < 1.0 or nv < 1.0:
                            ok = False
                            break
                        cosv = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
                        turns.append(math.degrees(math.acos(max(-1.0, min(1.0, cosv)))))
                    if not ok or max(turns) > maxturn:
                        continue
                    path = fillet(pts, [0.0] + [2000.0] * (len(pts) - 2) + [0.0], step=step)
                    if avoid is not None and any(avoid(q) for q in path):
                        continue
                    r = _min_radius(path)
                    cum = arclen(path, False)
                    L = cum[-1]
                    knots = [(L, zend)]
                    if fly is not None and crosses:
                        xs_ = [v for v in (s_cross(path, ln) for ln in crosses) if v is not None]
                        if not xs_:
                            continue
                        s_sep = next((cs for cs, q in zip(cum, path) if _dist_line(q, along) >= sep), None)
                        if s_sep is None:
                            continue
                        s_a, s_b = min(xs_) - 15.0, max(xs_) + 15.0
                        if s_a - s_sep < (fly - z0) / grade or L - s_b < (fly - zend) / (grade * 1.1):
                            continue
                        knots = [(s_sep, z0), (s_a, fly), (s_b, fly), (L, zend)]
                    if best is None or r > best[1]:
                        best = (heights_by(path, knots) if fly is not None else
                                heights_by(path, [(0.0, z0), (L, zend)]), r)
    if best is None:
        raise ValueError("designed_ramp: no alignment fits between %s and %s" % (m[:2], e[:2]))
    return best


def two_arc(m, t0, e, te, avoid=None, step=8.0, reach=400.0):
    """A ramp of exactly two constant arcs joined by a straight (an S or a C), from `m` leaving along the unit `t0` to
    `e` arriving along the unit `te`, with the LARGEST equal radius that fits: the first corner X slides along t0's
    ray, the second C back along te's, and each arc's tangent length fits its share of the straights. Returns
    (plan path, radius)."""
    def turn(u, v):
        nu, nv = math.hypot(*u), math.hypot(*v)
        return math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv))))
    best = None
    for a in range(5, int(reach), 5):
        X = (m[0] + t0[0] * a, m[1] + t0[1] * a)
        for c in range(5, int(reach), 5):
            C = (e[0] - te[0] * c, e[1] - te[1] * c)
            xc = (C[0] - X[0], C[1] - X[1])
            L = math.hypot(*xc)
            if L < 1.0:
                continue
            f1, f2 = turn(t0, xc), turn(xc, te)
            if f1 < 1e-3 or f2 < 1e-3 or f1 > math.radians(100) or f2 > math.radians(100):
                continue
            k1, k2 = math.tan(f1 / 2.0), math.tan(f2 / 2.0)
            R = min(a / k1, c / k2, L / (k1 + k2))
            if best is not None and R <= best[1]:
                continue
            pl = rounded_polygon([m[:2], X, C, e[:2]], [0.0, R * 0.999, R * 0.999, 0.0], closed=False,
                                 full_ends=True, arc_step=4.0)
            if avoid is not None and any(avoid(q) for q in pl):
                continue
            best = (pl, R)
    if best is None:
        raise ValueError("two_arc: nothing fits between %s and %s" % (m[:2], e[:2]))
    pl = best[0]
    cum = arclen(pl, False)
    n = max(2, int(math.ceil(cum[-1] / step)))
    return [at_s(pl, cum, cum[-1] * k / n, False) for k in range(n + 1)], best[1]


def reverse_curve(p0, p1, step=12.0, rmax=400.0):
    """A path from p0 to p1, both legs running along y, shifted sideways by p1.x - p0.x: straight, ONE arc, a
    straight diagonal, ONE equal arc back, straight -- with the LARGEST radius the space allows (user, 2026-09-30:
    arcs for high-speed ramps, no wiggles). Returns [(x, y)] from p0 to p1."""
    D = p1[0] - p0[0]
    H = abs(p1[1] - p0[1])
    sy = 1.0 if p1[1] > p0[1] else -1.0
    if abs(D) < 0.5:
        return [p0[:2]] + _straight(p0[:2], p1[:2], step)
    best = (0.0, H / 2.0)
    for k in range(1, 400):
        h = H * k / 400.0
        th = math.atan2(abs(D), h)
        t = min((H - h) / 2.0, math.hypot(D, h) / 2.0)
        R = t / math.tan(th / 2.0)
        if R > best[0]:
            best = (R, h)
    R, h = best
    R = min(rmax, R * 0.97)
    a = (H - h) / 2.0
    A = (p0[0], p0[1] + sy * a)
    B = (p1[0], p1[1] - sy * a)
    return fillet([p0[:2], A, B, p1[:2]], [0.0, R, R, 0.0], step=step)


def best_corner(p0, p1, corner_of, lo, hi, step=12.0, rmax=400.0):
    """ONE arc between two straights: p0 -> C -> p1 with C = corner_of(v) for v in [lo, hi], chosen for the largest
    radius that fits. Returns ([(x, y)], radius)."""
    best = (0.0, None)
    for k in range(0, 201):
        C = corner_of(lo + (hi - lo) * k / 200.0)
        a, b = math.dist(p0[:2], C), math.dist(C, p1[:2])
        if a < 1.0 or b < 1.0:
            continue
        u = ((C[0] - p0[0]) / a, (C[1] - p0[1]) / a)
        w = ((p1[0] - C[0]) / b, (p1[1] - C[1]) / b)
        th = math.acos(max(-1.0, min(1.0, u[0] * w[0] + u[1] * w[1])))
        if th < 1e-3:
            continue
        R = min(a, b) / math.tan(th / 2.0)
        if R > best[0]:
            best = (R, C)
    R = min(rmax, best[0] * 0.97)
    return fillet([p0[:2], best[1], p1[:2]], [0.0, R, 0.0], step=step), R


def s_cross(path, other):
    """Arclength along `path` where it first crosses the polyline `other` (plan), or None."""
    c = 0.0
    for a, b in zip(path, path[1:]):
        for q, r in zip(other, other[1:]):
            d = (b[0] - a[0]) * (r[1] - q[1]) - (b[1] - a[1]) * (r[0] - q[0])
            if abs(d) < 1e-9:
                continue
            t = ((q[0] - a[0]) * (r[1] - q[1]) - (q[1] - a[1]) * (r[0] - q[0])) / d
            u = ((q[0] - a[0]) * (b[1] - a[1]) - (q[1] - a[1]) * (b[0] - a[0])) / d
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                return c + t * math.dist(a[:2], b[:2])
        c += math.dist(a[:2], b[:2])
    return None


def s_crosses(path, other):
    """EVERY arclength along `path` where it crosses the polyline `other` (plan), with the crossing point."""
    out, c = [], 0.0
    for a, b in zip(path, path[1:]):
        for q, r in zip(other, other[1:]):
            d = (b[0] - a[0]) * (r[1] - q[1]) - (b[1] - a[1]) * (r[0] - q[0])
            if abs(d) < 1e-9:
                continue
            t = ((q[0] - a[0]) * (r[1] - q[1]) - (q[1] - a[1]) * (r[0] - q[0])) / d
            u = ((q[0] - a[0]) * (b[1] - a[1]) - (q[1] - a[1]) * (b[0] - a[0])) / d
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                out.append(c + t * math.dist(a[:2], b[:2]))
        c += math.dist(a[:2], b[:2])
    return out


def fly_heights(path, z0, z1, fly, spans, grade=0.055):
    """Heights for a flyover ramp: z0 at the start, z1 at the end, at least `fly` over every arclength span in
    `spans` [(s_a, s_b)], climbing and descending at no more than `grade` (raise-only cone from the spans)."""
    cum = arclen([q[:2] for q in path], False)
    L = cum[-1]
    out = []
    for c in cum:
        z = z0 + (z1 - z0) * c / max(1e-6, L)
        for a, b in spans:
            d = 0.0 if a <= c <= b else min(abs(c - a), abs(c - b))
            z = max(z, fly - grade * d)
        out.append(z)
    return [(q[0], q[1], round(z, 2)) for q, z in zip(path, out)]


def joint_ramp(net, ramp_name, head, face, side, against):
    """End ramp `ramp_name` at a JOINT with the divided road's end station `head`: its last station moved HALF A MEDIAN
    to `side` (+1 = the left of `face`, -1 the right) of `head`, so its one-way lanes land exactly on the divided road's
    carriageway, SEGMENT-linked, and both frozen on one facing (`face`, or its reverse when the ramp's chain runs
    `against` the divided road's -- a station's facing is its own chain's forward direction). The ramp's first span
    off the joint carries no pier (three hammerheads would stand on top of each other)."""
    r = net.roads[ramp_name]
    last = r.points[-1]
    half = net.resolved(head).median_width / 2.0
    L_ = math.hypot(*face) or 1.0
    lx, ly = -face[1] / L_ * side, face[0] / L_ * side
    hp = net.points[head].pos
    net.points[last].pos = (hp[0] + lx * half, hp[1] + ly * half, hp[2])
    net.link(last, head)
    freeze(net, head, face)
    freeze(net, last, (-face[0], -face[1]) if against else face)
    p0, p1 = net.points[last].pos, net.points[r.points[-2]].pos
    Lp = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
    f = min(0.5, SPLIT_CLEAR / Lp)
    q = insert_after(net, r, r.points[-2], tuple(p0[k] + (p1[k] - p0[k]) * f for k in range(3)))
    net.points[q].pillar_skip = True
    return last


def open_ramp(net, at, name, cw, entrance, length=90.0, spread=10.0, lanes=RAMP_LANES):
    """A RAMP off (or onto) C1 / a divided road at station `at`: `branch_ramp` opens the aux slot and places the mouth
    and the far station (level with the mainline through the gore). Returns the far station's position (x, y, z); the
    caller runs the ramp on from there with `extend`."""
    _m, info = ro.branch_ramp(net, at, name=name, aux_lanes=lanes, carriageway=cw, entrance=entrance,
                              length=length, spread=spread, drop=0.0)
    return net.points[info["far"]].pos


def run_on(net, name, pts3):
    extend(net, name, [(x, y, round(z, 2)) for (x, y, z) in pts3])
    return net.roads[name]


def heights_by(path, pieces):
    """Heights along a plan path from `pieces`: [(until arclength, z at that arclength)], linear between (the first
    piece starts at the path's first height). Returns [(x, y, z)]."""
    cum = arclen([p[:2] for p in path], False)
    out = []
    for c, p in zip(cum, path):
        z = pieces[0][1]
        prev = (0.0, pieces[0][1])
        for until, zz in pieces:
            if c <= until:
                t = (c - prev[0]) / max(1e-6, until - prev[0])
                z = prev[1] + (zz - prev[1]) * t
                break
            prev = (until, zz)
        else:
            z = pieces[-1][1]
        out.append((p[0], p[1], z))
    return out


def s_first(path, pred):
    """Arclength along `path` of its first point satisfying `pred((x, y))`."""
    cum = arclen([p[:2] for p in path], False)
    for c, p in zip(cum, path):
        if pred(p):
            return c
    return cum[-1]


def ramp_heights(path, z0, z1, hold0=0.0, hold1=0.0):
    """Heights along a ramp path: `z0` for its first `hold0` metres, `z1` for its last `hold1`, linear between."""
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = cum[-1]
    out = []
    for c in cum:
        if c <= hold0:
            out.append(z0)
        elif c >= L - hold1:
            out.append(z1)
        else:
            out.append(z0 + (z1 - z0) * (c - hold0) / max(1e-6, L - hold0 - hold1))
    return out


def diamond_ramp(net, at_uid, name, cw, ent, mouth, side, length=50.0, spread=18.0, radius=60.0):
    """One diamond ramp, TWO bends only (user, 2026-09-30, PLAN.md item 2: "/------T", not an S): out of the gore on
    one straight diagonal, ONE arc of `radius` onto the junction arm's own line (straights and constant arcs, no
    kinks), then STRAIGHT into the junction mouth `mouth` (x, y). Level with C1 through the gore (drop 0), down to the
    ground at the mouth. Returns the ramp's last station (the junction mouth)."""
    _m, info = ro.branch_ramp(net, at_uid, name=PREFIX + name, aux_lanes=ENTRY_LANES if ent else RAMP_LANES,
                              carriageway=cw, entrance=ent,
                              length=length, spread=spread, drop=0.0)
    far = net.points[info["far"]]
    m = net.points[info["mouth"]].pos
    fp = far.pos
    dx, dy = fp[0] - m[0], fp[1] - m[1]
    dl = math.hypot(dx, dy)
    ux, uy = dx / dl, dy / dl
    t = (mouth[1] - m[1]) / uy                                     # the diagonal meets the arm's line here
    corner = (m[0] + ux * t, mouth[1])
    ax = 1.0 if mouth[0] > corner[0] else -1.0
    th = math.acos(max(-1.0, min(1.0, ux * ax)))
    tl = radius * math.tan(th / 2.0)
    back = max(tl + 8.0, 0.0)
    if t - back < dl * 0.6:                                        # keep the far station clear of the gore
        back = t - dl * 0.6
    far.pos = (corner[0] - ux * back, corner[1] - uy * back, fp[2])
    fp = far.pos
    path = fillet([fp[:2], corner, mouth], [0.0, min(radius, back / max(1e-6, math.tan(th / 2.0)) - 1.0), 0.0],
                  step=20.0)[1:]
    # the climb (or descent) starts where the ramp's paved band has PARTED from C1's (island_grades.level_gores holds
    # it level until then anyway), not at its last corner: the same drop over ~40 m more (2026-10-01 review: 7.3 %)
    whole = [m[:2], fp[:2]] + path
    cumw = arclen(whole, False)
    part = next((c for c, q in zip(cumw, whole) if abs(q[1] - m[1]) >= DIAMOND_PART), cumw[1])
    zs = ramp_heights(whole, m[2], 0.0, hold0=part, hold1=20.0)     # a level foot: queue room at the signal
    far.pos = (fp[0], fp[1], round(zs[1], 2))
    extend(net, PREFIX + name, [(x, y, round(z, 2)) for (x, y), z in zip(path, zs[2:])])
    return net.roads[PREFIX + name].points[-1]

def diamond(net, at):
    """The C1 north-side TIGHT DIAMOND onto naka_hondori (PLAN.md NEXT, 2026-09-29 night): each ramp HUGS the viaduct --
    it leaves the gore parallel to C1, descends beside it and bends onto the cross street at a signalised junction ~45 m
    off C1's centreline. C1 runs WEST along its north side, so its FWD (westbound) carriageway is the south one and
    lands at the junction inside the ring, and BWD (eastbound) on the north lands at the one outside it."""
    x0 = DIAMOND_ROAD[1]
    js, jn = DIAMOND_J
    s_a, s_b = cut_road(net, (x0, js), DIAMOND_ROAD[0], MOUTH)
    n_a, n_b = cut_road(net, (x0, jn), DIAMOND_ROAD[0], MOUTH)
    south, north = [s_a, s_b], [n_a, n_b]
    for name, cw, ent, side, j, jy in (("d_bwd_off", "BWD", False, -1, north, jn), ("d_bwd_on", "BWD", True, 1, north, jn),
                                       ("d_fwd_off", "FWD", False, 1, south, js), ("d_fwd_on", "FWD", True, -1, south, js)):
        j.append(diamond_ramp(net, at[name], name, cw, ent, (x0 + side * MOUTH, jy), side))
    make_junction(net, south)
    make_junction(net, north)


def s_diamond(net, at):
    """The C1 SOUTH-side diamond, the N diamond's mirror (2026-09-30): the inside ramps (FWD, eastbound) land at a
    junction S_DIAMOND_IN_Y inside the ring, the outside ones (BWD) at S_DIAMOND_OUT_Y, each pair on its street
    (S_DIAMOND_W_ROAD for the west pair, naka_hondori for the east; both naka_hondori since eki_minami_dori's
    stretch under C1 was removed). The BWD ramps are built FIRST: the kit breaks a tie between two aux blocks at one
    station toward FWD, so a BWD ramp at a station an FWD lane already runs through was placed on the inner side."""
    iy, oy = PL.S_DIAMOND_IN_Y, PL.S_DIAMOND_OUT_Y
    w_road, wx = PL.S_DIAMOND_W_ROAD
    e_road, ex = DIAMOND_ROAD
    js = {}
    for road, x0 in {(w_road, wx), (e_road, ex)}:
        for y in (oy, iy):
            js[(road, y)] = list(cut_road(net, (x0, y), road, MOUTH))
    for name, cw, ent, side, (road, x0), jy in (("s_bwd_off", "BWD", False, 1, (e_road, ex), oy),
                                                ("s_bwd_on", "BWD", True, -1, (w_road, wx), oy),
                                                ("s_fwd_off", "FWD", False, -1, (w_road, wx), iy),
                                                ("s_fwd_on", "FWD", True, 1, (e_road, ex), iy)):
        js[(road, jy)].append(diamond_ramp(net, at[name], name, cw, ent, (x0 + side * MOUTH, jy), side))
    for mouths in js.values():
        make_junction(net, mouths)


def station_on(net, road, y):
    """A station of `road` (running along y) at record y, inserted into the span that contains it, its height linear
    between the span's ends: a ramp needs its own station on the mainline."""
    ch = road.points
    for a, b in zip(ch, ch[1:]):
        pa, pb = net.points[a].pos, net.points[b].pos
        if min(pa[1], pb[1]) < y < max(pa[1], pb[1]):
            t = (y - pa[1]) / (pb[1] - pa[1])
            return insert_after(net, road, a, tuple(pa[k] + (pb[k] - pa[k]) * t for k in range(3)))
    return min(ch, key=lambda u: abs(net.points[u].pos[1] - y))


def _chuo_line(net):
    """chuo_dori's centreline, south to north, from its own stations (every piece of it): the connector runs over it."""
    pts = []
    for n_, r_ in net.roads.items():
        if n_.startswith("chuo_dori"):
            pts += [net.points[u].pos[:2] for u in r_.points]
    return sorted(pts, key=lambda p: p[1])


def _x_on(line, y):
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        if y0 <= y <= y1:
            t = (y - y0) / max(1e-9, y1 - y0)
            return x0 + (x1 - x0) * t
    return line[0][0] if y < line[0][1] else line[-1][0]


def build(net, ground):
    """The expressway redesign (PLAN.md item 1, 2026-09-30): C1 with its S diamond on the south side and nothing else
    there, the N diamond, the W JCT on its WEST side (the connector over chuo_dori's median from a Y on the coastal
    Wangan) and the E JCT on its EAST side (the airport spur), the Wangan along the whole south coast to a T on the
    spur. C1 meets the Wangan connector ONLY on its west side (W1, W2) and the airport spur ONLY on its east side
    (E1, E2); the corner turn-backs were built and removed (user, 2026-09-30: one access per side)."""
    plan = rounded_polygon(C1_CORNERS, C1_RADIUS, arc_step=C1_ARC_STEP)
    cum = arclen(plan, True)
    xs, xe, yb, yt = C1_CORNERS[0][0], C1_CORNERS[1][0], C1_Y, C1_CORNERS[2][1]
    pts = {"w_bwd_on": (xs, PL.W1_ON_Y), "w_fwd_off": (xs, PL.W2_OFF_Y),
           "e_fwd_on": (xe, PL.E2_ON_Y), "e_bwd_off": (xe, PL.E_BWD_OFF_Y)}
    for k, x in DIAMOND_X.items():
        pts[k] = (x, yt)
    pts.update(PL.S_DIAMOND_MARKS)
    marks = {k: s_on(plan, cum, v) for k, v in pts.items()}
    cut = [s_on(plan, cum, p) for p in PL.C1_CUTS]
    # a ramp station whose added lane is CARRIED through it (AUX_CARRY) has no taper on that side: its clearance is
    # one-sided, so the corner arcs between the pairs keep their stations (FWD travels with the ring's arclength)
    clear = {}
    for ent, ext, field, _n in AUX_CARRY:
        sa, sb = marks[ent], marks[ext]
        up = (sb - sa) % cum[-1] < cum[-1] / 2.0          # the carry runs from sa toward larger arclength
        clear[sa] = (MARK_CLEAR, 15.0) if up else (15.0, MARK_CLEAR)
        clear[sb] = (15.0, MARK_CLEAR) if up else (MARK_CLEAR, 15.0)
    st = ring(net, PREFIX + "c1", plan, ground, marks=list(marks.values()), cut_marks=cut, clear=clear)
    at = {k: st[v] for k, v in marks.items()}
    for n_, r_ in net.roads.items():
        if n_.startswith(PREFIX + "c1"):
            for u in r_.points:
                plan_face(net, u, plan, cum, True)

    def taper():
        # BEFORE any ramp is cut: `open_aux_slot` sizes each ramp's taper from the road's taper_factor, and at the
        # default 1.0 it wants 432 m, so an entrance lane ran on to the next joint and was left with no successor
        for n_, r_ in net.roads.items():
            if n_.startswith(PREFIX):
                r_.taper_factor = TAPER
    taper()

    # --- the WANGAN mainline along the whole south coast, and the connector north over chuo_dori's median to C1
    for n_, r_ in net.roads.items():
        if n_.startswith("chuo_dori"):
            r_.base.median_width = max(r_.base.median_width, PL.CONN_MEDIAN)    # R3: the viaduct's piers stand in it
    wg, wat = wangan_main(net, ground)
    conn = connector_road(net)
    taper()
    y_ramps(net, wat, conn)
    taper()
    conn_n = connector_half_ic(net, conn)
    taper()
    head_n = conn_n.points[-1]
    q1, q0 = net.points[conn_n.points[-1]].pos, net.points[conn_n.points[-2]].pos
    fn = (q1[0] - q0[0], q1[1] - q0[1])

    # --- the W JCT on C1's west straight
    hn = net.points[head_n].pos
    # W1 and W2 are each ONE reverse curve with the largest radius the space allows (user, 2026-09-30: arcs for high
    # speed, no wiggles). W1 the connector NB -> C1 BWD (northbound, outer): from C1 outward (an entrance's chain runs
    # mouth -> joint)
    down = (0.0, -1.0)
    far = open_ramp(net, at["w_bwd_on"], PREFIX + "w_bwd_on", "BWD", True, length=45.0)
    m = mouth_of(net, PREFIX + "w_bwd_on")
    p1, r1 = designed_ramp(m, down, (hn[0] - 0.5, hn[1]), down, 0, z0=m[2], zend=PL.CONN_Z)
    p1 = [q[:2] for q in p1]
    run_on(net, PREFIX + "w_bwd_on", on_curve(net, PREFIX + "w_bwd_on",
                                                 heights_by(p1, [(0.0, m[2]), (arclen(p1, False)[-1], PL.CONN_Z)])))
    joint_ramp(net, PREFIX + "w_bwd_on", head_n, fn, 1, against=True)
    # W2: C1 FWD (southbound, inner) -> the connector SB: leaves inside and flies over C1 and W1 onto the SB half.
    # spread 26 m inside at once: island_grades holds a ramp level with its mainline until their paved bands part
    far = open_ramp(net, at["w_fwd_off"], PREFIX + "w_fwd_off", "FWD", False, length=45.0)
    m = mouth_of(net, PREFIX + "w_fwd_off")
    c1_line = [(xs, -200.0), (xs, 450.0)]
    # it climbs only once its band has parted from C1's (P2-7: begun 11 m off, the grade pass held it level to 20 m and
    # its climb came out 6.7 %)
    c1_at = next(r_ for r_ in net.roads.values() if at["w_fwd_off"] in r_.points)
    p, r2 = designed_ramp(m, down, (hn[0] + 0.5, hn[1]), down, 1, crosses=[c1_line, p1], along=c1_line,
                          z0=m[2], zend=PL.CONN_Z, fly=19.0, sep=part_distance(net, c1_at, RAMP_LANES))
    run_on(net, PREFIX + "w_fwd_off", on_curve(net, PREFIX + "w_fwd_off", p))
    print("island_expressway: W1 R %.0f m, W2 R %.0f m" % (r1, r2))
    joint_ramp(net, PREFIX + "w_fwd_off", head_n, fn, -1, against=True)

    # --- the AIRPORT SPUR: ONE divided road from its joint below C1's SE corner straight down x 1250 onto the Rainbow
    # Bridge's upper deck, then on the airport island a peel west off the rail, a descent, a U-turn and the forecourt
    import island_rainbow_bridge as rb
    centre, axis = rb.crossing_plan()
    half_b = rb.HALF_LENGTH
    na = (centre[0] - axis[0] * half_b, centre[1] - axis[1] * half_b)
    sa = (centre[0] + axis[0] * half_b, centre[1] + axis[1] * half_b)
    bx = sa[0]
    ey = PL.E_JOINT_Y
    d_plan = [(bx, ey), (bx, PEEL_Y), (U_X, PEEL_Y), (U_X, FORE_Y), (FORE_J[0] - MOUTH, FORE_Y)]
    dl = rounded_polygon(d_plan, [0.0, PEEL_R, U_R, U_R, 0.0], closed=False)
    dcum = arclen(dl, False)

    def s_of(pt):
        best, bs = 1e18, 0.0
        for i in range(len(dl) - 1):
            a, b = dl[i], dl[i + 1]
            Lq = math.hypot(b[0] - a[0], b[1] - a[1])
            if Lq < 1e-9:
                continue
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * (b[0] - a[0]) + (pt[1] - a[1]) * (b[1] - a[1])) / (Lq * Lq)))
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            d = math.hypot(q[0] - pt[0], q[1] - pt[1])
            if d < best:
                best, bs = d, dcum[i] + t * Lq
        return bs
    d_na, d_sa = s_of(na), s_of(sa)
    span = [d_na + (d_sa - d_na) * k / 12.0 for k in range(13)]
    d_hold = d_sa + PEEL_HOLD
    d_ground = s_of((U_X, PEEL_Y)) - U_R - 5.0
    ds = [0.0] + span + [d_hold]
    ds += [c for c in dcum if c > d_hold + 15.0 and abs(c - d_ground) > 15.0] + [d_ground]
    ds = sorted(set(round(v, 3) for v in ds if v <= dcum[-1] + 1e-6))
    zj = PL.E_JOINT_Z

    def zat(v):
        if v <= d_na:
            return zj + (BRIDGE_Z - zj) * v / d_na
        if v <= d_hold:
            return BRIDGE_Z
        if v <= d_ground:
            return BRIDGE_Z + (AIR_Z - BRIDGE_Z) * (v - d_hold) / (d_ground - d_hold)
        return AIR_Z
    spur = chain_road(net, PREFIX + "spur", [at_s(dl, dcum, v, False) + (round(zat(v), 2),) for v in ds])
    taper()
    # the spur's own stations for the Wangan's T, and a joint between T2 (NB exit) and T3 (NB merge)
    for y in (PL.T2_OFF_Y, PL.T1_ON_Y, PL.SPUR_CUT_Y, PL.T3_ON_Y, PL.T4_OFF_Y):
        station_on(net, spur, y)
    cut_u = min(spur.points, key=lambda u: abs(net.points[u].pos[1] - PL.SPUR_CUT_Y))
    ro.split_at_joint(net, cut_u, name=PREFIX + "spur__2")
    spur2 = net.roads[PREFIX + "spur__2"]
    head_e = spur.points[0]
    south = (0.0, -1.0)
    # E1 and E2 are each ONE reverse curve with the largest radius the space allows (user, 2026-09-30). E1 C1 BWD
    # (southbound on the east side, outer) -> the spur SB, straight onto the spur's own line and the joint
    far = open_ramp(net, at["e_bwd_off"], PREFIX + "e_bwd_off", "BWD", False, length=45.0)
    m = mouth_of(net, PREFIX + "e_bwd_off")
    pe1, r1 = designed_ramp(m, south, (bx + 0.5, ey), south, 0, z0=m[2], zend=zj)
    pe1 = [q[:2] for q in pe1]
    run_on(net, PREFIX + "e_bwd_off", on_curve(net, PREFIX + "e_bwd_off",
                                                 heights_by(pe1, [(0.0, m[2]), (arclen(pe1, False)[-1], zj)])))
    joint_ramp(net, PREFIX + "e_bwd_off", head_e, south, 1, against=False)
    # E2: the spur NB -> C1 FWD (northbound on the east side, inner), from C1 outward (an entrance's chain): over C1's
    # east straight and over E1, down to the joint
    far = open_ramp(net, at["e_fwd_on"], PREFIX + "e_fwd_on", "FWD", True, length=45.0)
    m = mouth_of(net, PREFIX + "e_fwd_on")
    c1e = [(xe, -200.0), (xe, 450.0)]
    c1_at = next(r_ for r_ in net.roads.values() if at["e_fwd_on"] in r_.points)
    p, r2 = designed_ramp(m, south, (bx - 0.5, ey), south, -1, crosses=[c1e, pe1], along=c1e,
                          z0=m[2], zend=zj, fly=19.5, sep=part_distance(net, c1_at, RAMP_LANES))
    run_on(net, PREFIX + "e_fwd_on", on_curve(net, PREFIX + "e_fwd_on", p))
    print("island_expressway: E1 R %.0f m, E2 R %.0f m" % (r1, r2))
    joint_ramp(net, PREFIX + "e_fwd_on", head_e, south, -1, against=False)
    t_split(net, wg, spur, spur2)
    suburb_exit(net, wat["sb"], ground)
    suburb_entrance(net)
    port_exit(net)
    port_entrance(net, wat["pe"])

    diamond(net, at)
    s_diamond(net, at)
    lane_balance(net, spur, conn, conn_n)

    # --- the AIRPORT FORECOURT (user, 2026-09-29: "forecourt like central station"): the divided spur ends at FORE_J,
    # the middle of the west side of a ONE-WAY loop, two lanes, clockwise (Japan keeps left, as the Central rotary):
    # north up the west side, east along the north side, south down the east side -- the kerb beside the station's
    # west wall -- and west along the south side under the terminal's curb canopy, back to J. A one-way road lays its
    # lanes on its LEFT, so the loop's stations are its INNER edge and its 4 m outer footway is the kerb buses and taxis
    # stop at (the station wall, the terminal canopy). The inner island is `AirportForecourt`'s.
    x0, y0, x1, y1 = FORE_BOX
    jx, jy2 = FORE_J
    loop_plan = [(jx, jy2 + MOUTH), (jx, y1), (x1, y1), (x1, y0), (x0, y0), (jx, jy2 - MOUTH)]
    ll = rounded_polygon(loop_plan, [0.0, FORE_R, FORE_R, FORE_R, FORE_R, 0.0], closed=False)
    lcum = arclen(ll, False)
    n = max(4, int(math.ceil(lcum[-1] / 12.0)))
    lpts = [at_s(ll, lcum, lcum[-1] * k / n, False) + (AIR_Z,) for k in range(n + 1)]
    loop = chain_road(net, "kuko_rotary", lpts, preset="block", one_way=True)
    loop.road_class = "street"
    loop.base.lanes_fwd, loop.base.lanes_bwd = 2, 0
    loop.base.left_walk_width, loop.base.right_walk_width = 4.0, 2.0
    for u in loop.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
    make_junction(net, [spur2.points[-1], loop.points[0], loop.points[-1]])
    # P1-3: the airport hairpin (the peel R45 off the rail, the descent, the R40 U-turn) is its own road, posted for it
    hp = min(spur2.points, key=lambda u: math.dist(net.points[u].pos[:2], (bx, PEEL_Y + PEEL_R + SPEED_SPLIT_PAST)))
    ro.split_at_joint(net, hp, name=PREFIX + "spur__3")


#: P1-1 (review 2026-10-01, Japanese lane balance): an entrance followed by an exit on the same C1 carriageway is ONE
#: added lane (付加車線) from the entrance's gore to the exit's -- a lane addition, then an exit-only lane drop -- never a
#: merge back to two lanes followed by a fresh deceleration lane 400-550 m later. (entrance, exit, aux field, lanes).
#: Each pair straddles a C1 corner joint; the lane hands over across it (point_export.wire_joints).
AUX_CARRY = (("e_fwd_on", "d_fwd_off", "aux_fwd", RAMP_LANES), ("d_fwd_on", "w_fwd_off", "aux_fwd", ENTRY_LANES),
             ("w_bwd_on", "d_bwd_off", "aux_bwd", RAMP_LANES), ("d_bwd_on", "e_bwd_off", "aux_bwd", ENTRY_LANES))
GROUND_GRADE = 0.06    # P2-7: the steepest a ramp to or from the ground climbs (review: <= 6 %)
MERGE_MIN = 260.0     # P1-2: a JCT entrance's added lane runs at least this far before its taper (review: >= 250 m)


def _ring_seq(net):
    """C1's stations in chain order, every road of the ring in turn (a joint's two stations both appear)."""
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    seq, name, seen = [], PREFIX + "c1", set()
    while name and name not in seen:
        seen.add(name)
        r = net.roads[name]
        seq += list(r.points)
        nxt = None
        for l in net.points[r.points[-1]].links:
            o = road_of.get(l.target, "")
            if l.type == pm.LINK_SEGMENT and o.startswith(PREFIX + "c1") and o != name \
                    and net.roads[o].points[0] == l.target:
                nxt = o
        name = nxt
    return seq


def _main_of(net, ramp, on=None):
    """The mainline station a ramp hangs off (on road `on` when given: Y3 leaves the Wangan AND joins the connector)."""
    pts = set(net.roads[PREFIX + ramp].points)
    return next(m for m, r in net.aux_pairs() if r in pts and (on is None or m in on.points))


def _raise_aux(net, uid, field, lanes):
    p = net.points[uid]
    setattr(p, field, max(getattr(p, field), lanes))


def _carry(net, road, k, step, field, lanes, length, taper=0.0):
    """Hold `field` >= `lanes` from station index `k` of `road` along its chain (`step` +1 / -1) for `length` metres,
    inserting a station where it ends; then clear the stations within `taper` after it, so the lane's drop is one span
    of at least that length. Returns the length held."""
    ch = road.points
    s, i = 0.0, k
    _raise_aux(net, ch[i], field, lanes)
    end = None
    while True:
        j = i + step
        if not 0 <= j < len(ch):
            return s
        a, b = net.points[ch[i]].pos, net.points[ch[j]].pos
        d = math.dist(a[:2], b[:2])
        if s + d >= length:
            f = (length - s) / d
            if s + d - length > 10.0 and f > 0.05:
                pos = tuple(a[q] + (b[q] - a[q]) * f for q in range(3))
                end = insert_after(net, road, ch[i] if step > 0 else ch[j], pos)
                setattr(net.points[end], field, 0)
            else:
                end = ch[j]
            _raise_aux(net, end, field, lanes)
            s = length
            break
        s += d
        i = j
        _raise_aux(net, ch[i], field, lanes)
    if taper > 0.0:
        ch = road.points
        e = ch.index(end)
        run, j = 0.0, e
        while 0 <= j + step < len(ch) and run < taper:
            run += math.dist(net.points[ch[j]].pos[:2], net.points[ch[j + step]].pos[:2])
            j += step
        for u in list(ch[min(e, j) + 1:max(e, j)]):
            if any(l.type != pm.LINK_SEGMENT for l in net.points[u].links):
                continue
            q = ch.index(u)
            a_, b_ = ch[q - 1], ch[q + 1]
            net.remove_point(u)
            if u in ch:
                ch.remove(u)
            net.link(a_, b_)
    return s


def _carry_room(net, ramp, taper):
    """How far an added lane carried into a JCT ramp at its joint end may run before it drops: the lane's taper must
    end short of the ramp's GORE-HOLD zone (`part_distance` from its mainline mouth), or `island_grades.level_gores`
    inserts its parting station inside the one-span taper (W1, 2026-10-02: a 14.6 m taper)."""
    import island_grades as IG
    ch = ramp.points
    pts = [net.points[u].pos[:2] for u in ch]
    cum = arclen(pts, False)
    main = next(r for r in net.roads.values() for m, q in net.aux_pairs() if q == ch[0] and m in r.points)
    mline = [net.points[u].pos[:2] for u in main.points]
    need = IG._road_half(main) + IG._road_half(ramp) + IG.GORE_MARGIN
    s_part = next((c for c in (k * 2.0 for k in range(int(cum[-1] / 2.0)))
                   if _side(at_s(pts, cum, c, False), mline)[1] >= need), cum[-1])
    return cum[-1] - s_part - taper - 15.0


def lane_balance(net, spur, conn, conn_n):
    """Japanese lane balance on the JCT ramps (review P1-1 / P1-2): every C1 entrance -> exit pair carries its added
    lane(s) through to the exit (AUX_CARRY); T3's added lane on the spur NB runs on across the E joint into E2 and
    drops there, >= MERGE_MIN m after T3's gore (it had 125 m before the spur ran into E2); Y3's on the connector runs
    MERGE_MIN m (it had 139 m)."""
    for ent, ext, field, lanes in AUX_CARRY:
        seq = _ring_seq(net)                            # again each time: a pair may remove stations
        n = len(seq)
        a, b = seq.index(_main_of(net, ent)), seq.index(_main_of(net, ext))
        fwd, bwd = (b - a) % n, (a - b) % n
        rng = [seq[(a + i) % n] for i in range(fwd + 1)] if fwd <= bwd else [seq[(b + i) % n] for i in range(bwd + 1)]
        if fwd > bwd:
            rng = rng[::-1]                             # in TRAVEL order: the entrance's station first
        bm = seq[b]
        big = getattr(net.points[bm], field)            # the exit's own block (its open_aux_slot ran at build time)
        for u in rng:
            setattr(net.points[u], field, lanes)
        setattr(net.points[bm], field, max(big, lanes))
        if big > lanes:
            # the exit's extra slot(s) open over ONE span just before its gore: the stations inside that span go
            res = net.resolved(bm)
            want = pv.taper_min_length((big - lanes) * res.lane_width, res.design_speed, TAPER) + 2.0
            run, j = 0.0, len(rng) - 1
            while j > 0 and run < want:
                run += math.dist(net.points[rng[j]].pos[:2], net.points[rng[j - 1]].pos[:2])
                j -= 1
            for u in rng[j + 1:-1]:
                if any(l.type != pm.LINK_SEGMENT for l in net.points[u].links):
                    continue
                r_ = next(r for r in net.roads.values() if u in r.points)
                q = r_.points.index(u)
                if q == 0 or q == len(r_.points) - 1:
                    continue
                x_, y_ = r_.points[q - 1], r_.points[q + 1]
                net.remove_point(u)
                if u in r_.points:
                    r_.points.remove(u)
                net.link(x_, y_)
        L = sum(math.dist(net.points[p].pos[:2], net.points[q].pos[:2]) for p, q in zip(rng, rng[1:])
                if p in net.points and q in net.points)
        print("island_expressway: %s -> %s: %d added lane(s) carried %.0f m%s"
              % (ent, ext, lanes, L, "" if big <= lanes else ", the exit's %d more open over %.0f m" % (big - lanes, run)))
    # T3: the spur NB is its BWD carriageway, running toward the chain's start (the E joint)
    k = spur.points.index(_main_of(net, "t3", spur))
    on_spur = _carry(net, spur, k, -1, "aux_bwd", T_LANES, 1e9)
    e2 = net.roads[PREFIX + "e_fwd_on"]
    res = net.resolved(e2.points[-1])
    want = pv.taper_min_length(T_LANES * res.lane_width, res.design_speed, TAPER) + 2.0
    on_e2 = _carry(net, e2, len(e2.points) - 1, -1, "aux_bwd", T_LANES,
                   min(MERGE_MIN - on_spur, _carry_room(net, e2, want)), taper=want)
    print("island_expressway: T3's added lane %.0f m on the spur + %.0f m into E2" % (on_spur, on_e2))
    # Y3: the connector NB is its FWD carriageway
    k = conn.points.index(_main_of(net, "y3", conn))
    res = net.resolved(conn.points[k])
    want = pv.taper_min_length(ENTRY_LANES * res.lane_width, res.design_speed, TAPER) + 2.0
    print("island_expressway: Y3's added lane %.0f m on the connector"
          % _carry(net, conn, k, 1, "aux_fwd", ENTRY_LANES, MERGE_MIN, taper=want))
    # the connector's NB entrance (P2-5): its added lane runs on across the W joint into W1 and drops there
    k = conn_n.points.index(_main_of(net, "c_nb_on", conn_n))
    on_c = _carry(net, conn_n, k, 1, "aux_fwd", ENTRY_LANES, 1e9)
    w1 = net.roads[PREFIX + "w_bwd_on"]
    res = net.resolved(w1.points[-1])
    want = pv.taper_min_length(ENTRY_LANES * res.lane_width, res.design_speed, TAPER) + 2.0
    on_w1 = _carry(net, w1, len(w1.points) - 1, -1, "aux_bwd", ENTRY_LANES,
                   min(MERGE_MIN - on_c, _carry_room(net, w1, want)), taper=want)
    print("island_expressway: the connector entrance's added lane %.0f m on the connector + %.0f m into W1"
          % (on_c, on_w1))


#: P1-3: a road's posted speed from its tightest design radius. Japan's minimum radius at 80 km/h is 230-280 m and at
#: 60 km/h 120-150 m; the island is compressed (as its taper_factor is) and the thresholds are scaled to ~0.75 of the
#: book's, so the review's own reading holds: R 180-260 sweepers stay 80, R 92-120 is 60, the airport hairpin 40.
SPEED_BY_RADIUS = ((170.0, 80.0), (90.0, 60.0), (60.0, 50.0), (30.0, 40.0))
SPEED_FLOOR = 30.0
SPEED_SPLIT_PAST = 60.0     # a speed split stands this far past the tight curve's end


def road_radius(net, r):
    """A road's tightest radius: from the turn of two frozen design tangents over their span, or, between chord-faced
    stations, the circumradius of station triples (`_min_radius`)."""
    ch = net.chain(r)
    best = 1e9
    run = [ch[0].pos]
    for a, b in zip(ch, ch[1:]):
        fa, fb = PLAN_FACED.get(a.uid), PLAN_FACED.get(b.uid)
        if fa and fb and fa[0] == fb[0]:
            # between two stations on one design alignment: that alignment's own radius, however long the span
            plan, cum, closed = PLANS[fa[0]]
            s0, s1 = fa[1], fb[1]
            if closed and s1 < s0:
                s1 += cum[-1]
            # the alignment's own VERTICES across the span (+ one chord each side): the arcs are sampled there
            L = cum[-1]
            seg = []
            for k in (range(-len(plan), 2 * len(plan)) if closed else range(len(plan))):
                c = cum[k % len(plan)] + (L * (k // len(plan)) if closed else 0.0)
                if s0 - 12.0 <= c <= s1 + 12.0:
                    seg.append(plan[k % len(plan)])
            if len(seg) >= 3:
                best = min(best, _min_radius(seg))
            best = min(best, _min_radius(run))
            run = [b.pos]
        else:
            run.append(b.pos)
    return min(best, _min_radius(run))


def post_speeds(net):
    """Every expressway road (not a ramp: the export posts those at RAMP_SPEED) takes the speed its tightest radius
    allows (SPEED_BY_RADIUS), never above its own design speed; C1 is C1_SPEED at most."""
    out = []
    for name in sorted(net.roads):
        r = net.roads[name]
        if not name.startswith(PREFIX) or r.road_class == "ramp":
            continue
        R = road_radius(net, r)
        v = next((sp for rr, sp in SPEED_BY_RADIUS if R >= rr), SPEED_FLOOR)
        if name.startswith(PREFIX + "c1"):
            v = min(v, C1_SPEED)
        v = min(v, r.base.design_speed or 80.0)
        out.append((name, R, v))
    return out


def part_distance(net, main_road, ramp_lanes):
    """How far a ramp's centreline must be from its mainline's before `island_grades.level_gores` lets it leave the
    mainline's height: the generator holds it level that far itself, or the grade pass compresses its climb into
    what is left (P2-7: W2 read 6.7 % because it began climbing 11 m off C1, the pass held it to 20 m)."""
    import island_grades as IG
    return IG._road_half(main_road) + ramp_lanes * main_road.base.lane_width + IG.GORE_MARGIN


def ground_ramp(net, at_uid, name, cw, ent, end_xy, end_dir, mouths, lanes=1, grade=GROUND_GRADE, landing=15.0,
                avoid=None, reach=400.0, side=None, path=None):
    """A ramp between the expressway station `at_uid` and a GROUND junction (P2-5, P2-6, P3-8): `branch_ramp` opens
    the aux slot and places the mouth level with the mainline; then two equal arcs and a straight (`two_arc`) to
    `end_xy`, the ramp's last station, arriving along `end_dir` (its chain's direction there); level until its band has
    parted from the mainline's (`part_distance`), then one straight grade down (or up) to the junction's height with a
    level landing. The ramp's last station joins `mouths` (a new T: `cut_road`'s two mouths) as one junction. Returns
    (length m, grade, radius m)."""
    road = next(r for r in net.roads.values() if at_uid in r.points)
    _m, info = ro.branch_ramp(net, at_uid, name=PREFIX + name, aux_lanes=lanes, carriageway=cw, entrance=ent,
                              length=45.0, spread=10.0, drop=0.0)
    m = net.points[info["mouth"]].pos
    fp = net.points[info["far"]].pos
    # the ramp leaves along the MAINLINE's own axis at the gore (the side it lies on is branch_ramp's far station's):
    # it meets the mainline tangentially and parts from it on its first arc
    k = road.points.index(at_uid)
    qa = net.points[road.points[max(0, k - 1)]].pos
    qb = net.points[road.points[min(len(road.points) - 1, k + 1)]].pos
    t0 = (qb[0] - qa[0], qb[1] - qa[1])
    tl = math.hypot(*t0)
    t0 = (t0[0] / tl, t0[1] / tl)
    if t0[0] * (fp[0] - m[0]) + t0[1] * (fp[1] - m[1]) < 0.0:
        t0 = (-t0[0], -t0[1])
    el = math.hypot(*end_dir)
    te = (end_dir[0] / el, end_dir[1] / el)
    if path is not None:
        p, R = path(m, t0), None
        R = _min_radius(p)
    elif side is None:
        p, R = two_arc(m, t0, end_xy, te, avoid=avoid, reach=reach)
    else:
        # a gentle diverge to `side` first (designed_ramp): in a narrow corridor two_arc's corner sits on the
        # mainline's own line, so the ramp would never part from it before its last turn (R1: 8 m off for 240 m)
        p3, R = designed_ramp(m, t0, end_xy, te, side, avoid=avoid)
        p = [q[:2] for q in p3]
    zj = sum(net.points[u].pos[2] for u in mouths) / len(mouths)
    mline = [net.points[u].pos[:2] for u in road.points]
    need = part_distance(net, road, lanes)
    cum = arclen(p, False)
    L = cum[-1]
    s_sep = next((c for c, q in zip(cum, p) if _side(q, mline)[1] >= need), L * 0.3)
    g = abs(m[2] - zj) / max(1.0, L - landing - s_sep)
    run_on(net, PREFIX + name, on_curve(net, PREFIX + name,
                                         heights_by(p, [(0.0, m[2]), (s_sep, m[2]), (L - landing, zj), (L, zj)])))
    end = net.roads[PREFIX + name].points[-1]
    net.points[end].pos = (end_xy[0], end_xy[1], zj)
    make_junction(net, list(mouths) + [end])
    if g > grade + 1e-6:
        print("island_expressway: WARN %s descends %.1f %% (limit %.1f %%)" % (name, g * 100.0, grade * 100.0))
    return L, g, R


def _thin_near(net, road, keep_uids, clear=MARK_CLEAR):
    """Remove `road`'s interior stations within `clear` of any station in `keep_uids` (a ramp's taper is one span)."""
    for u in list(road.points[1:-1]):
        if u in keep_uids or any(l.type != pm.LINK_SEGMENT for l in net.points[u].links):
            continue
        if any(math.dist(net.points[u].pos[:2], net.points[k].pos[:2]) < clear for k in keep_uids):
            k = road.points.index(u)
            a_, b_ = road.points[k - 1], road.points[k + 1]
            net.remove_point(u)
            if u in road.points:
                road.points.remove(u)
            net.link(a_, b_)


def _t_arm(net, a, b, toward, mouth=MOUTH):
    """Where a T's new arm's mouth stands, and the direction a ramp arrives in to reach it: MOUTH from the centre of
    the cut (`a`, `b`, the road's two mouths), square to the road, on the side of `toward` (a point)."""
    pa, pb = net.points[a].pos, net.points[b].pos
    cx, cy = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    if nx * (toward[0] - cx) + ny * (toward[1] - cy) < 0:
        nx, ny = -nx, -ny
    return (cx + nx * mouth, cy + ny * mouth), (-nx, -ny)


def station_by_x(net, road, x):
    """A station of `road` at record x (inserted into the span that holds it), as `station_on` does for y."""
    ch = road.points
    for a, b in zip(ch, ch[1:]):
        pa, pb = net.points[a].pos, net.points[b].pos
        if min(pa[0], pb[0]) < x < max(pa[0], pb[0]):
            t = (x - pa[0]) / (pb[0] - pa[0])
            return insert_after(net, road, a, tuple(pa[k] + (pb[k] - pa[k]) * t for k in range(3)))
    return min(ch, key=lambda u: abs(net.points[u].pos[0] - x))


def suburb_entrance(net):
    """P2-6 (review 2026-10-01): the Suburb's WESTBOUND entrance, completing a west-facing half interchange with the
    Suburb exit. East of the Wangan's crossing the dike road (ring_kita) is already on the SEA side of the mainline, so
    the ramp leaves a new T there (SB_ON_T) heading south, swings south-west and merges onto the WB carriageway's
    left at SB_ON_X: ~280 m after J0, ~460 m before Y3's diverge, a 4 % climb that crosses nothing."""
    road = next(r for n, r in net.roads.items() if n == PREFIX + "wangan__3")
    st = station_by_x(net, road, PL.SB_ON_X)
    _thin_near(net, road, [st])
    a, b = cut_road(net, PL.SB_ON_T, "ring_kita", MOUTH)
    end, te = _t_arm(net, a, b, (PL.SB_ON_T[0], PL.SB_ON_T[1] - 100.0))
    L, g, R = ground_ramp(net, st, "sb_on", "BWD", True, end, te, [a, b])
    print("island_expressway: Suburb WB entrance %.0f m %.1f %% R %.0f" % (L, g * 100.0, R))


def port_exit(net):
    """P3-8 (review 2026-10-01, PLAN R5 (a)): the port's WESTBOUND exit to the port loop (kichi_dori__2). Y2 already
    holds the strip south of the mainline between x -500 and -250, and the loop's south leg is only ~100 m away, so the
    exit leaves the WB's left at PORT_OFF_X -- right under Y2's flyover, where Y2 is highest --, runs west inside the
    loop south of Y2 and lands at a new T on the loop's WEST leg (PORT_T) from the east: ~300 m at ~4 %, an exit
    before Y2's merge (no weave). A mainline joint at WG_CUT4_X keeps it off Y3's run (both WB exits)."""
    road = net.roads[PREFIX + "wangan__2"]
    st = station_by_x(net, road, PL.PORT_OFF_X)
    cut = station_by_x(net, road, PL.WG_CUT4_X)
    _thin_near(net, road, [st, cut] + [u for u in road.points if net.points[u].targets(pm.LINK_AUX)])
    ro.split_at_joint(net, cut, name=PREFIX + "wangan__2b")
    a, b = cut_road(net, PL.PORT_T, "kichi_dori", MOUTH)
    end, te = _t_arm(net, a, b, (PL.PORT_T[0] + 100.0, PL.PORT_T[1]))
    L, g, R = ground_ramp(net, st, "port_off", "BWD", False, end, te, [a, b], lanes=EXIT_GROUND_LANES)
    print("island_expressway: port WB exit %.0f m %.1f %% R %.0f" % (L, g * 100.0, R))


PORT_ON_MOUTH = 16.0   # the T's arm on the dike road: short, so the arc into it has room in the corridor
PORT_ON_OFF = 22.0     # how far off the mainline's centreline the entrance runs while it climbs
PORT_ON_R = 30.0       # its arc into the T (a ground ramp's own turn, 30 km/h)


def port_entrance(net, st):
    """R1 (review 2026-10-02): the port's EASTBOUND entrance, from a new T on the dike road west of the port
    (PORT_ON_T), merging onto the EB carriageway's left (north) at PORT_ON_X. Its added lane is carried across the
    WG_CUT5_X joint into Y1 and leaves with it (lane balance, AUX_CARRY's shape): port -> C1 by Y1, port -> the airport
    straight on."""
    road = next(r for r in net.roads.values() if st in r.points)
    a, b = cut_road(net, PL.PORT_ON_T, "ring_kita", PORT_ON_MOUTH)
    end, te = _t_arm(net, a, b, (PL.PORT_ON_T[0], PL.PORT_ON_T[1] - 100.0), mouth=PORT_ON_MOUTH)

    def path(m, t0):
        # the corridor between the mainline and the dike road is ~55 m wide: a short diverge, a run PORT_ON_OFF m
        # off the mainline (parted from it, so the climb can start), then one arc into the T
        nl = (-t0[1], t0[0])                                            # left of t0 (west) is south: north = -nl
        nn = (-nl[0], -nl[1]) if (end[0] - m[0]) * nl[0] + (end[1] - m[1]) * nl[1] < 0 else nl
        A = (m[0] + t0[0] * 25.0, m[1] + t0[1] * 25.0)
        B = (A[0] + t0[0] * 70.0 + nn[0] * PORT_ON_OFF, A[1] + t0[1] * 70.0 + nn[1] * PORT_ON_OFF)
        # the run's line meets the arrival line (through `end` along te) at C
        den = t0[0] * te[1] - t0[1] * te[0]
        f = ((end[0] - B[0]) * te[1] - (end[1] - B[1]) * te[0]) / den
        C = (B[0] + t0[0] * f, B[1] + t0[1] * f)
        rr = min(PORT_ON_R, 0.95 * math.dist(C, end[:2]), 0.45 * math.dist(B, C))
        pl = rounded_polygon([m[:2], A, B, C, end[:2]], [0.0, 120.0, 120.0, rr, 0.0], closed=False, full_ends=True,
                             arc_step=4.0)
        cum = arclen(pl, False)
        n = max(2, int(math.ceil(cum[-1] / 8.0)))
        return [at_s(pl, cum, cum[-1] * k / n, False) for k in range(n + 1)]
    L, g, R = ground_ramp(net, st, "port_on", "FWD", True, end, te, [a, b], lanes=ENTRY_LANES, path=path)
    # the added lane on to the joint, and from the joint to Y1's gore (Y1's second lane opens over that one span)
    k = road.points.index(st)
    for u in road.points[k:]:
        _raise_aux(net, u, "aux_fwd", ENTRY_LANES)
    nxt = net.roads[PREFIX + "wangan__1b"]
    y1 = _main_of(net, "y1", nxt)
    for u in nxt.points[:nxt.points.index(y1) + 1]:
        _raise_aux(net, u, "aux_fwd", ENTRY_LANES)
    # Y2's westbound merge lane (2 lanes on wangan__1b) used to close before the next joint 1 km west; now it meets
    # the WG_CUT5_X joint, so it is carried across into wangan__1 and dropped there with a full taper
    w1 = road
    res = net.resolved(w1.points[-1])
    want = pv.taper_min_length(RAMP_LANES * res.lane_width, res.design_speed, TAPER) + 2.0
    held = _carry(net, w1, len(w1.points) - 1, -1, "aux_bwd", RAMP_LANES, 75.0, taper=want)
    print("island_expressway: Y2's added lanes carried %.0f m into wangan__1 before their taper" % held)
    print("island_expressway: port EB entrance %.0f m %.1f %% R %.0f, its lane carried %.0f m into Y1"
          % (L, g * 100.0, R, math.dist(net.points[st].pos[:2], net.points[y1].pos[:2])))
    if nxt.points.index(y1) != 1:
        print("island_expressway: WARN a station between the WG_CUT5 joint and Y1 (%d)" % nxt.points.index(y1))


def connector_half_ic(net, conn):
    """P2-5 (review 2026-10-01): the connector's half interchange to the west city. chuo_dori under it has a
    junction every 25-60 m between y -630 and -226, so a slip ramp onto its kerb lanes would pass 3-6 m over cross
    streets; the two ramps land diamond-style at junctions on the ARTERIALS either side instead:
      * the SB exit (connector SB -> wangan_dori, east of chuo): off the SB carriageway's left at CONN_EXIT_Y, an S
        east and south, landing at a new T on wangan_dori at CONN_EXIT_X;
      * the NB entrance (rinkai_dori, west of chuo -> connector NB): from a new T on rinkai_dori at CONN_ENT_X, north
        and east under nothing, merging onto the NB carriageway's left at CONN_ENT_Y; its added lane is carried across
        the W joint into W1 and dropped there, MERGE_MIN m after its gore (T3 -> E2's shape).
    A connector joint at CONN_CUT_Y keeps them off Y3's / Y4's runs (one ramp per carriageway per run)."""
    cut = station_on(net, conn, PL.CONN_CUT_Y)
    ex = station_on(net, conn, PL.CONN_EXIT_Y)
    en = station_on(net, conn, PL.CONN_ENT_Y)
    _thin_near(net, conn, [cut, ex, en])
    ro.split_at_joint(net, cut, name=PREFIX + "wangan_c1__2")
    north = net.roads[PREFIX + "wangan_c1__2"]
    # the SB exit: the connector's chain runs south -> north, so SB is its BWD carriageway
    a, b = cut_road(net, PL.CONN_EXIT_T, "wangan_dori", MOUTH)
    end, te = _t_arm(net, a, b, (PL.CONN_EXIT_T[0], PL.CONN_EXIT_T[1] + 100.0))
    L1, g1, R1 = ground_ramp(net, ex, "c_sb_off", "BWD", False, end, te, [a, b])
    # the NB entrance: an entrance's chain runs from its gore (mouth) out to the ground, so it ARRIVES at the T heading
    # south; its traffic runs the other way
    a, b = cut_road(net, PL.CONN_ENT_T, "rinkai_dori", MOUTH)
    end, te = _t_arm(net, a, b, (PL.CONN_ENT_T[0], PL.CONN_ENT_T[1] + 100.0))
    L2, g2, R2 = ground_ramp(net, en, "c_nb_on", "FWD", True, end, te, [a, b])
    print("island_expressway: connector half IC: SB exit %.0f m %.1f %% R %.0f, NB entrance %.0f m %.1f %% R %.0f"
          % (L1, g1 * 100.0, R1, L2, g2 * 100.0, R2))
    return north


def _g(x, z, h=0.0):
    """GODOT (x, z) + a record height -> a record point."""
    return (float(x), -float(z), float(h))


def _nearest(net, road, xy):
    return min(road.points, key=lambda u: math.hypot(net.points[u].pos[0] - xy[0], net.points[u].pos[1] - xy[1]))


def _profile(pts, anchors):
    """Heights along the plan points `pts` (record x, y): linear in arclength between `anchors` {index: height}."""
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    keys = sorted(anchors)
    out = []
    for i, c in enumerate(cum):
        lo = max([k for k in keys if k <= i], default=keys[0])
        hi = min([k for k in keys if k >= i], default=keys[-1])
        if lo == hi:
            out.append(anchors[lo])
        else:
            t = (c - cum[lo]) / max(1e-9, cum[hi] - cum[lo])
            out.append(anchors[lo] + (anchors[hi] - anchors[lo]) * t)
    return [(p[0], p[1], round(z, 2)) for p, z in zip(pts, out)]


def straight_arc(start, u, S, R, V, step=10.0, arc_step=5.0):
    """`start` -> S m straight along the unit `u`, then ONE LEFT arc of radius R tangent to it, ending where its
    tangent points at V. Returns (points, the arc's end)."""
    A = (start[0] + u[0] * S, start[1] + u[1] * S)
    O = (A[0] - u[1] * R, A[1] + u[0] * R)
    base = math.atan2(V[1] - O[1], V[0] - O[0])
    beta = math.acos(min(1.0, R / math.dist(O, V)))
    for sg in (1, -1):
        th = base + sg * beta
        T = (O[0] + R * math.cos(th), O[1] + R * math.sin(th))
        if -(T[1] - O[1]) * (V[0] - T[0]) + (T[0] - O[0]) * (V[1] - T[1]) > 0:
            break
    a0 = math.atan2(A[1] - O[1], A[0] - O[0])
    sweep = (math.atan2(T[1] - O[1], T[0] - O[0]) - a0) % (2 * math.pi)
    k = max(1, int(S // step))
    pts = [(start[0] + u[0] * S * i / k, start[1] + u[1] * S * i / k) for i in range(k + 1)] if S >= 1.0 else [start]
    m = max(2, int(math.ceil(sweep * R / arc_step)))
    pts += [(O[0] + R * math.cos(a0 + sweep * i / m), O[1] + R * math.sin(a0 + sweep * i / m)) for i in range(1, m + 1)]
    return pts, T


def wangan_main(net, ground):
    """THE WANGAN MAINLINE (user, 2026-09-30: "the Wangan from the airport spur to the west coastline the main line"):
    ONE divided 2+2 expressway from a T on the dike road (ring_kita) at WG_TERMINAL, along the south coast in long
    sweepers (R1), over Harbour station, up the waterfront corridor to its east end WG_MAIN[-1], a joint where T1
    and T2 take it to and from the airport spur. Stations every 45 m, and one at each ramp mark with no other within
    MARK_CLEAR (a ramp's taper is one span). Returns (road, {mark: uid})."""
    t = PL.WG_TERMINAL
    a, b = cut_road(net, t, "ring_", MOUTH)
    z_ring = (net.points[a].pos[2] + net.points[b].pos[2]) / 2.0
    c0 = PL.WG_MAIN[0]
    d = (c0[0] - t[0], c0[1] - t[1])
    L0 = math.hypot(*d)
    start = (t[0] + d[0] / L0 * MOUTH, t[1] + d[1] / L0 * MOUTH)
    u = (d[0] / L0, d[1] / L0)
    wpath = getattr(PL, "WG_WEST_PATH", None)
    if wpath:
        # the west end as CORNERS (user, 2026-10-02: the T further north-west on the west coast, the mainline down the
        # land strip outside the dike): straights and constant arcs from the T's mouth through WG_WEST_PATH onto the
        # coast line; `west` is everything up to the last west corner's arc
        cl = rounded_polygon([start] + list(wpath) + PL.WG_MAIN[1:],
                             [0.0] + list(PL.WG_WEST_RADII) + PL.WG_MAIN_R[1:], closed=False, full_ends=True,
                             arc_step=4.0)
        cw_ = arclen(cl, False)
        # the speed split goes just past the T's own bend (the first corner): only that bend is posted low
        k_ = min(range(len(cl)), key=lambda i: math.dist(cl[i], wpath[0]))
        s_end = cw_[k_] + PL.WG_WEST_RADII[0]
        west = [q for q, c in zip(cl, cw_) if c <= s_end]
    else:
        west, tw = straight_arc(start, u, PL.WG_WEST_STRAIGHT, PL.WG_WEST_R, PL.WG_MAIN[1])
        cl = west + rounded_polygon([tw] + PL.WG_MAIN[1:], [0.0] + PL.WG_MAIN_R[1:], closed=False, arc_step=4.0)[1:]
    cum = arclen(cl, False)

    def s_at_x(x):
        for i in range(len(cl) - 1):
            if (cl[i][0] - x) * (cl[i + 1][0] - x) <= 0.0 and cl[i + 1][0] != cl[i][0]:
                f = (x - cl[i][0]) / (cl[i + 1][0] - cl[i][0])
                return cum[i] + f * (cum[i + 1] - cum[i])
        raise SystemExit("island_expressway: the Wangan does not reach x %.0f" % x)
    marks = {"y1": s_at_x(PL.Y1_OFF_X), "y2": s_at_x(PL.Y2_ON_X), "y4": s_at_x(PL.Y4_ON_X),
             "y3": s_at_x(PL.Y3_OFF_X), "sb": s_at_x(PL.SB_OFF_X), "pe": s_at_x(PL.PORT_ON_X)}
    cut_s = s_at_x(PL.WG_CUT_X)
    cut5_s = s_at_x(PL.WG_CUT5_X)
    cut2_s = s_at_x(PL.WG_CUT2_X)
    cut3_s = s_at_x(PL.WG_CUT3_X)
    n = max(2, int(round(cum[-1] / 45.0)))
    base = [cum[-1] * k / n for k in range(n + 1)]
    ss = [c for c in base if all(abs(c - m) > MARK_CLEAR for m in marks.values())
          and all(abs(c - v) > 15.0 for v in (cut_s, cut2_s, cut3_s, cut5_s))]
    ss = sorted(set(round(v, 3) for v in ss + list(marks.values()) + [cut_s, cut2_s, cut3_s, cut5_s]))
    pts = [at_s(cl, cum, v, False) for v in ss]
    # a FIXED coastal profile, not `deck_profile`: that reads the coastal dike's crest within the deck's half width as
    # ground and put the whole coast at 17 m, leaving Y2 no room to fly over it; the crossings are gated instead
    s_hb = s_at_x(PL.WG_HARBOUR_X)
    zs = []
    for v in ss:
        f = min(PL.WG_Z, z_ring + (PL.WG_Z - z_ring) * v / 120.0)
        k = max(0.0, min(1.0, (v - (cum[-1] - PL.WG_EAST_RISE)) / PL.WG_EAST_RISE))
        hump = PL.WG_HARBOUR_Z - max(0.0, abs(v - s_hb) - 60.0) * 0.035      # over Harbour station, 3.5 % each way
        zs.append(round(max(f, PL.WG_Z + (PL.WG_EAST_Z - PL.WG_Z) * k, hump) if v >= 120.0 else f, 2))
    w = chain_road(net, PREFIX + "wangan", [(x, y, z) for (x, y), z in zip(pts, zs)])
    for u in w.points:
        plan_face(net, u, cl, cum, False)
    west_u = w.points[min(range(len(ss)), key=lambda i: abs(ss[i] - arclen(west, False)[-1] - SPEED_SPLIT_PAST))]
    make_junction(net, [a, b, w.points[0]])
    at = {k: w.points[ss.index(round(v, 3))] for k, v in marks.items()}
    # a joint between the Y's west ramps and Y4: one ramp per carriageway per run (Y1 and Y4 are both on EB)
    cut2_u = w.points[ss.index(round(cut2_s, 3))]
    cut3_u = w.points[ss.index(round(cut3_s, 3))]
    ro.split_at_joint(net, w.points[ss.index(round(cut_s, 3))], name=PREFIX + "wangan__2")
    # and one between Y4 (EB merge) and the Suburb exit, and one between the Suburb exit and T3 (all three on EB)
    ro.split_at_joint(net, cut3_u, name=PREFIX + "wangan__3")
    ro.split_at_joint(net, cut2_u, name=PREFIX + "wangan__4")
    # R1: and one between the port's EB entrance and Y1, so the entrance's added lane hands over to Y1 at a joint
    ro.split_at_joint(net, w.points[ss.index(round(cut5_s, 3))], name=PREFIX + "wangan__1b")
    # P1-3: the west end (the T, its descent and the R100 corner over the sea) is its own road, posted for that corner;
    # the coast straight after it keeps the mainline's speed
    ro.split_at_joint(net, west_u, name=PREFIX + "wangan__1")
    return net.roads[PREFIX + "wangan__4"], at


def connector_road(net):
    """THE CONNECTOR to C1 west (R3): a divided road from its south joint at CONN_J_Y north OVER chuo_dori's median
    (its piers in the median) to CONN_N_Y, the W JCT's joint on C1's west side. Its south end parts into Y1 / Y2."""
    chuo = _chuo_line(net)
    ys = [y for (_x, y) in chuo if PL.CONN_S_Y + 40.0 < y < PL.CONN_N_Y - 40.0]
    cpts = [(_x_on(chuo, PL.CONN_S_Y), PL.CONN_S_Y)] + [(_x_on(chuo, y), y) for y in ys] + \
           [(_x_on(chuo, PL.CONN_N_Y), PL.CONN_N_Y)]
    k = min(len(cpts) - 1, 2)
    slope = (cpts[k][0] - cpts[0][0]) / (cpts[k][1] - cpts[0][1])
    south = (cpts[0][0] + slope * (PL.CONN_J_Y - cpts[0][1]), PL.CONN_J_Y)
    pts = [south] + cpts if math.dist(south, cpts[0]) > 15.0 else cpts
    return chain_road(net, PREFIX + "wangan_c1", [(x, y, PL.CONN_Z) for (x, y) in pts])


def y_ramps(net, wat, conn):
    """The coast's Y between the mainline and the connector, each ramp ONE arc of the largest radius the space allows
    (user, 2026-09-30): Y1 Wangan EB -> the connector NB (an exit to the north, one straight diagonal over the dike's
    kichi_dori junction, one arc north into the connector's west half); Y2 the connector SB -> Wangan WB (south out of
    its east half, one arc west round the mainline at Y2_Z, merging from its own side); Y4 the connector SB -> Wangan
    EB (off the connector's east side at Y4_OFF_Y, one arc east, merging onto EB from the north at Y4_ON_X) -- which
    closes the outer loop C1 -> connector -> Wangan -> spur -> C1. The connector's south end is a joint like the spur's:
    Y1 and Y2 are its two halves."""
    head = conn.points[0]
    cp = net.points[head].pos
    p1 = net.points[conn.points[1]].pos
    face = (p1[0] - cp[0], p1[1] - cp[1])
    # Y1
    far = open_ramp(net, wat["y1"], PREFIX + "y1", "FWD", False, length=60.0, spread=14.0)
    m = mouth_of(net, PREFIX + "y1")
    # the corner no lower than y -1040: below that the diagonal runs ALONG the dike road (ring_kita, y -1083..-1106)
    p, _r = best_corner(m, (cp[0] - 0.5, cp[1]), lambda v: (cp[0] - 0.5, v), -1040.0, cp[1] - 5.0)
    L = arclen(p, False)[-1]
    p_y1 = p
    run_on(net, PREFIX + "y1", on_curve(net, PREFIX + "y1", heights_by(p, [(0.0, m[2]), (L, cp[2])])))
    joint_ramp(net, PREFIX + "y1", head, face, 1, against=False)
    # Y2 (an entrance of the mainline: its chain runs from the merge to the joint)
    far = open_ramp(net, wat["y2"], PREFIX + "y2", "BWD", True, length=60.0, spread=14.0)
    m = mouth_of(net, PREFIX + "y2")
    # the corner SOUTH of the mainline, on the joint's own line: Y2 then rises straight north into the connector's east
    # half and never crosses Y1 (a corner further west put the crossing right at the joint, 4.6 m above it)
    p, _r = best_corner(m, (cp[0] + 0.5, cp[1]), lambda v: (cp[0] + 0.5, v), -1230.0, -1160.0)
    wl = [net.points[u].pos[:2] for n_ in (PREFIX + "wangan", PREFIX + "wangan__1", PREFIX + "wangan__1b",
                                                         PREFIX + "wangan__2")
          for u in net.roads[n_].points]
    spans = [(v - 20.0, v + 20.0) for v in (s_cross(p, wl), s_cross(p, p_y1)) if v is not None]
    run_on(net, PREFIX + "y2", on_curve(net, PREFIX + "y2", fly_heights(p, m[2], cp[2], PL.Y2_Z, spans)))
    joint_ramp(net, PREFIX + "y2", head, face, -1, against=False)
    # Y4: off the connector SB (its BWD carriageway) to the east, south, one arc east onto the mainline's north side
    off = station_on(net, conn, PL.Y4_OFF_Y)
    # its taper is one span: no connector station within MARK_CLEAR of the diverge, either side
    for u in list(conn.points[1:-1]):
        y = net.points[u].pos[1]
        if u != off and abs(y - PL.Y4_OFF_Y) < MARK_CLEAR:
            k = conn.points.index(u)
            a_, b_ = conn.points[k - 1], conn.points[k + 1]
            net.remove_point(u)
            if u in conn.points:
                conn.points.remove(u)
            net.link(a_, b_)
    far = open_ramp(net, off, PREFIX + "y4", "BWD", False, length=50.0, spread=14.0, lanes=ENTRY_LANES)
    wg = net.roads[PREFIX + "wangan__2"]
    on = min(wg.points, key=lambda u: abs(net.points[u].pos[0] - PL.Y4_ON_X))
    op = net.points[on].pos
    k = wg.points.index(on)
    q0 = net.points[wg.points[max(0, k - 1)]].pos
    q1 = net.points[wg.points[min(len(wg.points) - 1, k + 1)]].pos
    ux, uy = q1[0] - q0[0], q1[1] - q0[1]
    ul = math.hypot(ux, uy)
    ux, uy = ux / ul, uy / ul
    nx, ny = -uy, ux                                                # the mainline's left (north) side
    g = (op[0] + nx * 22.0 - ux * 40.0, op[1] + ny * 22.0 - uy * 40.0)
    corner_of = lambda v: (far[0], g[1] + (far[0] - g[0]) * uy / ux if abs(ux) > 1e-6 else v)
    C = corner_of(0.0)
    a, b = math.dist(far[:2], C), math.dist(C, g)
    th = math.acos(max(-1.0, min(1.0, ((C[0] - far[0]) * (g[0] - C[0]) + (C[1] - far[1]) * (g[1] - C[1])) / (a * b))))
    R = min(250.0, 0.97 * min(a, b) / math.tan(th / 2.0))
    m = mouth_of(net, PREFIX + "y4")
    C = (m[0] + 6.0, C[1])
    p = fillet([m[:2], C, g], [0.0, R, 0.0], step=12.0)
    L = arclen(p, False)[-1]
    run_on(net, PREFIX + "y4", on_curve(net, PREFIX + "y4", heights_by(p, [(0.0, m[2]), (L, op[2])])))
    ro.make_ramp(net, on, net.roads[PREFIX + "y4"].points[-1], lanes=ENTRY_LANES)
    y3_ramp(net, wat["y3"], conn)


Y3_MERGE_DEG = 8.0   # Y3's last straight converges onto the connector at this angle


def y3_ramp(net, off, conn):
    """Y3, Wangan WB -> the connector NB (toward C1 west): off the waterfront straight's south side, straight on west
    while the mainline bends away south-west beneath it, ONE large right-hand turn over the mainline, Y4 and the
    connector (`two_arc`, both arcs right), merging into the connector's west (NB) side at Y3_ON_Y."""
    # its taper is one span: no connector station within MARK_CLEAR of the merge
    on = station_on(net, conn, PL.Y3_ON_Y)
    for u in list(conn.points[1:-1]):
        y = net.points[u].pos[1]
        if u != on and abs(y - PL.Y3_ON_Y) < MARK_CLEAR and not net.points[u].targets(pm.LINK_AUX):
            k = conn.points.index(u)
            a_, b_ = conn.points[k - 1], conn.points[k + 1]
            net.remove_point(u)
            if u in conn.points:
                conn.points.remove(u)
            net.link(a_, b_)
    far = open_ramp(net, off, PREFIX + "y3", "BWD", False, length=45.0, lanes=ENTRY_LANES)
    m = mouth_of(net, PREFIX + "y3")
    road = next(r for r in net.roads.values() if off in r.points)
    k = road.points.index(off)
    q0 = net.points[road.points[k + 1]].pos                        # WB runs toward the chain's start
    t0 = (m[0] - q0[0], m[1] - q0[1])
    tl = math.hypot(*t0)
    t0 = (t0[0] / tl, t0[1] / tl)
    op = net.points[on].pos
    # the connector's own heading INTO the merge (it is not due north): the ramp's last straight runs parallel to it,
    # SEP m off its west side -- far enough that the two paved bands have parted, or island_grades.level_gores holds
    # the whole parallel run at the connector's height (measured: 7-13 m off held Y3 1.1 m over Y4)
    k_on = conn.points.index(on)
    pp = net.points[conn.points[k_on - 1]].pos
    te = (op[0] - pp[0], op[1] - pp[1])
    tel = math.hypot(*te)
    te = (te[0] / tel, te[1] / tel)
    left = (-te[1], te[0])
    # it arrives on a straight converging onto the merge at MERGE_DEG (no corner where the curve meets the taper),
    # ending where the ramp's own mouth will sit (its lanes beside the connector's, half a carriageway off)
    a = math.radians(Y3_MERGE_DEG)
    tm = (te[0] * math.cos(a) + te[1] * math.sin(a), -te[0] * math.sin(a) + te[1] * math.cos(a))
    g = (op[0] + left[0] * 9.0, op[1] + left[1] * 9.0)
    wl = [net.points[u].pos for n_ in sorted(net.roads) if n_.startswith(PREFIX + "wangan")
          and not n_.startswith(PREFIX + "wangan_c") for u in net.roads[n_].points]
    # it may not drift over the mainline it leaves before it has had the length to climb over it (2026-10-01: the old
    # alignment was over the mainline's deck ~80 m after its gore, a shallow crossing no grade can make): within
    # Y3_CLIMB m of the gore it keeps its station Y3_KEEP m off the mainline's centreline
    wxy = [q[:2] for q in wl]
    keep = _side(m[:2], wxy)[1] - 0.5                             # never closer than at its own gore
    p, r = two_arc(m, t0, g, tm, avoid=lambda q: math.dist(q, m[:2]) < PL.Y3_CLIMB and _side(q, wxy)[1] < keep)
    lines = [wl, [net.points[u].pos for u in net.roads[PREFIX + "y4"].points], [net.points[u].pos for u in conn.points]]
    # each crossing at the height THAT road needs (its own deck + 5.5 m + margin), holding 15 m either side
    # each crossing is the whole span where the two decks OVERLAP in plan (a shallow crossing overlaps far longer than
    # +-15 m: Y3 passed 4.9 m over the mainline with fixed windows), at the highest deck under it + 6.3 m
    xs_, spans = [], []
    for ln in lines:
        lxy = [q[:2] for q in ln]
        cr = s_crosses(p, lxy)
        # the ramp's station line is its INNER edge (its one lane lies on its left, away from where it left): it is
        # over the other deck from where its station comes within that deck's half width (13 m) to where its whole
        # band (+5.5 m) has passed beyond it -- a span that holds an actual centreline crossing (not the gore beside)
        outs = _overlap_spans(p, lxy, 18.5)
        for a_, _b, j in _overlap_spans(p, lxy, 13.0):
            hit = [v for v in cr if a_ - 1.0 <= v <= _b + 1.0]
            if not hit:
                continue                      # beside it (the gore, the merge), not over it
            b_ = max((bb for aa, bb, _jj in outs if aa <= hit[0] <= bb), default=_b)
            zo = max(q[2] for q in ln[max(0, j - 3):j + 5])
            spans.append([a_ - 8.0, b_ + 8.0, max(zo + 6.3, op[2])])
            xs_.append(((a_ + b_) / 2.0, zo + 6.3))
    xs_.sort()
    spans.sort()
    L = arclen(p, False)[-1]
    # overlapping windows are ONE window at the higher height, or the profile dips between two close crossings
    win = []
    for a_, b_, z in spans:
        if win and a_ <= win[-1][1]:
            win[-1] = [win[-1][0], max(win[-1][1], b_), max(win[-1][2], z)]
        else:
            win.append([a_, b_, z])
    # heights: each crossing window is a MINIMUM with 5 % cones either side (no knot list: two windows 7 m apart at
    # different heights made a 31 % step), over a base level with the gore for its first 40 m, then down to the merge
    cum = arclen(p, False)
    base = [(q[0], q[1], m[2] if c <= 40.0 else m[2] + (op[2] - m[2]) * (c - 40.0) / max(1.0, L - 40.0))
            for q, c in zip(p, cum)]
    prof = []
    for (x, y, z), c in zip(base, cum):
        for a0, a1, zw in win:
            d = 0.0 if a0 <= c <= a1 else min(abs(c - a0), abs(c - a1))
            z = max(z, zw - 0.05 * d)
        prof.append((x, y, round(z, 2)))
    knots = [(round(a0), round(zw, 1)) for a0, _a1, zw in win]
    run_on(net, PREFIX + "y3", on_curve(net, PREFIX + "y3", prof))
    ro.make_ramp(net, on, net.roads[PREFIX + "y3"].points[-1], lanes=ENTRY_LANES)

def _arc(c, r, a0, a1, step=10.0):
    """Points on the circle (c, r) from angle a0 to a1 (radians, either way), every ~step m, excluding a0."""
    n = max(2, int(math.ceil(abs(a1 - a0) * r / step)))
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * k / n), c[1] + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(1, n + 1)]


def _tangent_cw(p, c, r):
    """The point where a straight from p meets the circle (c, r) tangentially, for CLOCKWISE travel round it."""
    dx, dy = p[0] - c[0], p[1] - c[1]
    d = math.hypot(dx, dy)
    base = math.atan2(dy, dx)
    off = math.acos(r / d)
    for a in (base + off, base - off):
        t = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        cw = (math.sin(a), -math.cos(a))                           # clockwise tangent direction at angle a
        if (t[0] - p[0]) * cw[0] + (t[1] - p[1]) * cw[1] > 0.0:
            return t, a
    raise SystemExit("island_expressway: no clockwise tangent")


T_LANES = 1           # each T ramp is ONE lane: the 2+2 Wangan splits lane by lane at J0
T_HALF = 4.0          # a one-lane ramp's paved half width (lane 4.5 + shoulders), for overlap spans
T_FLY = 5.8           # surface-over-surface target where one T ramp passes over another road (gate: 5.5)
T_GRADE = 0.05        # the steepest a T ramp climbs or falls
T_PAIR = 6.0          # two T ramps closer than this (station to centreline) are one carriageway: one height


def _spur_z(net, roads, y):
    """The spur's station height at record y (linear between its stations)."""
    pts = sorted((net.points[u].pos for r in roads for u in r.points), key=lambda p: p[1])
    for a, b in zip(pts, pts[1:]):
        if a[1] <= y <= b[1]:
            return a[2] + (b[2] - a[2]) * (y - a[1]) / max(1e-9, b[1] - a[1])
    return pts[0][2] if y < pts[0][1] else pts[-1][2]


def _overlap_spans(path, other, reach):
    """Arclength spans of `path` (plan) whose samples lie within `reach` of the polyline `other`, each with the
    nearest point's index on `other` at its deepest sample: [(s_a, s_b, j)]."""
    cum = arclen([q[:2] for q in path], False)
    near = []
    for c, q in zip(cum, path):
        best, bj = 1e18, 0
        for j, (a, b) in enumerate(zip(other, other[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / max(1e-9, dx * dx + dy * dy)))
            d = math.hypot(a[0] + dx * t - q[0], a[1] + dy * t - q[1])
            if d < best:
                best, bj = d, j
        near.append((c, best <= reach, bj))
    spans, cur = [], None
    for c, hit, j in near:
        if hit and cur is None:
            cur = [c, c, j]
        elif hit:
            cur[1], cur[2] = c, j
        elif cur is not None:
            spans.append(tuple(cur))
            cur = None
    if cur is not None:
        spans.append(tuple(cur))
    return spans


def _densify(pl, step=12.0):
    cum = arclen(pl, False)
    n = max(2, int(math.ceil(cum[-1] / step)))
    return [at_s(pl, cum, cum[-1] * k / n, False) for k in range(n + 1)]


def _line_hit(p, u, q, v):
    """Where the line p + s u meets q + t v (plan)."""
    den = u[0] * v[1] - u[1] * v[0]
    s = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / den
    return (p[0] + u[0] * s, p[1] + u[1] * s)


def _heights(path, z0, z1, over, grade=T_GRADE):
    """z0 -> z1 linear along `path`, raised over every (s_a, s_b, z_min) in `over` with a `grade` cone each way."""
    cum = arclen([q[:2] for q in path], False)
    L = cum[-1]
    out = []
    for c, q in zip(cum, path):
        z = z0 + (z1 - z0) * c / max(1e-6, L)
        for a, b, zm in over:
            d = 0.0 if a <= c <= b else min(abs(c - a), abs(c - b))
            z = max(z, zm - grade * d)
        out.append((q[0], q[1], round(z, 2)))
    return out


def _side(q, path):
    """(signed side, distance) of `q` against the nearest segment of `path` (plan, in its own direction): > 0 left."""
    best = (1e18, 0.0)
    for a, b in zip(path, path[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / max(1e-9, dx * dx + dy * dy)))
        d = math.hypot(a[0] + dx * t - q[0], a[1] + dy * t - q[1])
        if d < best[0]:
            best = (d, dx * (q[1] - a[1]) - dy * (q[0] - a[0]))
    return best[1], best[0]


def _wrong_side(q, path, want, clear):
    """True if `q` is within `clear` of `path` or on the other side of it from `want` (+1 left, -1 right)."""
    sd, d = _side(q, path)
    return d < clear or sd * want < 0


def _one_lane_road(net, name, pts3):
    r = chain_road(net, name, pts3, one_way=True)
    r.road_class = "ramp"
    r.base.lanes_fwd, r.base.lanes_bwd = T_LANES, 0
    r.base.design_speed = 60.0
    for u in r.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = T_LANES, 0
    return r


def t_split(net, wg, spur, spur2):
    """THE LANE-SPLIT T (user, 2026-10-01, a Japanese 分岐 / 合流): the 2+2 Wangan ENDS at J0 on its straight waterfront
    diagonal and each carriageway splits lane by lane into four ONE-LANE ramps, NW -> SE at J0:
      T3 (EB outer lane -> the spur NB)  |  T1 (EB inner -> the spur SB, the airport)  |  median  |
      T4 (the spur SB -> WB inner)       |  T2 (the spur NB -> WB outer)
    No forced merge anywhere: a split has no through lane, and WB is the two ramps joined into two lanes (a lane
    addition). Three flyovers: T1 over T4 a little past J0 (they swap sides), T4 over the spur at the top, T1 over the
    spur on its loop. Every ramp is straights and constant arcs (two_arc / fillet)."""
    head = wg.points[-1]
    hp = net.points[head].pos
    q0 = net.points[wg.points[-2]].pos
    u = (hp[0] - q0[0], hp[1] - q0[1])
    ul = math.hypot(*u)
    u = (u[0] / ul, u[1] / ul)
    n = (-u[1], u[0])                                              # the mainline's left (NW)
    res = net.resolved(head)
    m2, w = res.median_width / 2.0, res.lane_width
    z0 = hp[2]
    off = lambda k: (hp[0] + n[0] * k, hp[1] + n[1] * k)
    s3, s1, e4, e2 = off(m2 + w), off(m2), off(-m2), off(-m2 - w)
    spur_line = [(1250.0, 0.0), (1250.0, -800.0)]
    spurs = [spur, spur2]
    reach = 13.0                    # over the spur: within its half width (~12.5 with shoulders) of its centreline

    # T3 (EB outer -> spur NB): straight on along the diagonal, then the S onto the spur's west side (two_arc)
    on3 = min(spur.points, key=lambda k: abs(net.points[k].pos[1] - PL.T3_ON_Y))
    o3 = net.points[on3].pos
    g3 = (o3[0] - 22.0, o3[1] - 40.0)
    st3 = (s3[0] + u[0] * PL.T3_STRAIGHT, s3[1] + u[1] * PL.T3_STRAIGHT)
    p3, r3 = two_arc(st3, u, g3, (0.0, 1.0), avoid=lambda q: q[0] > 1040.0 and q[1] < -365.0)
    p3 = _densify([s3, st3], 12.0) + p3[1:]
    t3 = _heights(p3, z0, o3[2], [])

    # T1 (EB inner -> spur SB, the airport): along the diagonal from J0 to a corner T1_SWAP m out, then a large right arc
    # onto a straight that crosses OVER T4 (still low by J0) and runs to ONE clockwise circle over the spur (centre
    # T1_LOOP_Y), straight down the spur's east side to the merge
    on1 = min(spur2.points, key=lambda k: abs(net.points[k].pos[1] - PL.T1_ON_Y))
    mp = net.points[on1].pos
    r = PL.T1_R
    c = (PL.T1_LEG_X - r, PL.T1_LOOP_Y)
    P = (s1[0] + u[0] * PL.T1_SWAP, s1[1] + u[1] * PL.T1_SWAP)
    T, aT = _tangent_cw(P, c, r)
    lead = fillet([s1, P, T], [0.0, PL.T1_SWAP_R, 0.0], step=12.0)
    p1 = lead + _arc(c, r, aT, 0.0) + [(PL.T1_LEG_X, y) for y in _ys(c[1] - 20.0, mp[1] + 45.0)]
    p1x = [q[:2] for q in p1]
    p3x = [q[:2] for q in p3]

    # T4 (spur SB -> WB inner), traffic order: off the spur's east side heading south, ONE S of two equal arcs over the
    # spur onto J0's line -- between T3 (its NW) and T1 (its SE) -- then straight into J0 (where T1 passes over it)
    of4 = min(spur.points, key=lambda k: abs(net.points[k].pos[1] - PL.T4_OFF_Y))
    o4 = net.points[of4].pos
    # geometric order J0 -> spur: the WB pair (T4 beside T2) PEELS OFF south-east at J0 onto the east line T_EAST_Y
    # (so the EB pair can climb beside nothing), then T4 turns north-east (C), passes UNDER T1's lead nearly square,
    # crosses the spur heading north-east and turns north up its east side (F) to the gore
    tA = (PL.T_EAST_Y - e4[1]) / u[1]
    A = (e4[0] + u[0] * tA, e4[1] + u[1] * tA)
    hA = math.atan2(u[1], u[0])
    rA = 0.95 * tA / math.tan(hA / 2.0)
    C = (PL.T4_NORTH_X, PL.T_EAST_Y)
    F = (o4[0] + 16.0, PL.T4_TURN_Y)
    G = (o4[0] + 15.0, o4[1])
    p4 = fillet([e4, A, C, F, G], [0.0, rA, PL.T4_RC, PL.T4_RF, 0.0], step=12.0)[::-1]
    r4 = min(rA, PL.T4_RC, PL.T4_RF)
    cum4 = arclen(p4, False)
    over4 = [(a, b_, max(_spur_z(net, spurs, at_s(p4, cum4, a, False)[1]),
                         _spur_z(net, spurs, at_s(p4, cum4, b_, False)[1])) + T_FLY + 0.6)
             for a, b_, _j in _overlap_spans(p4, spur_line, reach)]
    t4 = _heights(p4, o4[2], z0, over4)

    cum1 = arclen(p1x, False)
    over1 = [(a, b_, max(_spur_z(net, spurs, at_s(p1x, cum1, a, False)[1]),
                         _spur_z(net, spurs, at_s(p1x, cum1, b_, False)[1])) + T_FLY + 0.3)
             for a, b_, _j in _overlap_spans(p1x, spur_line, reach)]
    # T1 over T4: T1 sits beside T4 across the 1 m median from J0, so a plan overlap test reads "over it" from J0 on
    # (which lifted T1's head off the joint). The crossing really starts where T1 DRIFTS off J0's line toward T4 (s_a)
    # and ends where its band has cleared T4's (s_b); T1 must be T_FLY above T4 there, climbing from J0 at <= 5 %
    lat = [(q[0] - s1[0]) * n[0] * -1.0 + (q[1] - s1[1]) * n[1] * -1.0 for q in p1x]      # + = right of J0's line
    s_a = next(c for c, l_ in zip(cum1, lat) if l_ > 0.5)
    # ...and over T4 where T4 really crosses under it (a span holding a centreline crossing, past the pair at J0)
    t4xy = [q[:2] for q in t4]
    cr4 = [v for v in s_crosses(p1x, t4xy) if v > 40.0]
    for a_, b_, j in _overlap_spans(p1x, t4xy, 12.0):
        if any(a_ - 1.0 <= v <= b_ + 1.0 for v in cr4):
            z4 = max(q[2] for q in t4[max(0, j - 4):j + 5])
            over1.append((a_ - 6.0, b_ + 6.0, z4 + T_FLY))
            if a_ - 6.0 < (z4 + T_FLY - z0) / T_GRADE + PL.T_HOLD:
                print("island_expressway: WARN T1 crosses T4 %.0f m from J0, wants %.0f m to climb"
                      % (a_, (z4 + T_FLY - z0) / T_GRADE + PL.T_HOLD))
    t1 = _heights(p1, z0, mp[2], over1)
    t1 = [(x, y, z0 if c <= PL.T_HOLD else z) for c, (x, y, z) in zip(cum1, t1)]   # level beside the peeling WB pair
    # T3 rides LEVEL with T1 (one carriageway, the split's two lanes) until T1 drifts off at s_a, then on its own
    cum3 = arclen([q[:2] for q in p3], False)
    t1z = [q[2] for q in t1]
    t3 = [(q[0], q[1], round(max(q[2], t1z[min(range(len(cum1)), key=lambda i: abs(cum1[i] - c))]
                                 if c <= s_a else q[2]), 2)) for q, c in zip(t3, cum3)]
    zt3 = max(z for c, (_x, _y, z) in zip(cum3, t3) if c <= s_a + 1.0)
    st3 = next(c for c in cum3 if c >= s_a)
    t3 = [(x, y, z if c <= s_a else round(max(o3[2], zt3 + (o3[2] - zt3) * (c - st3) / max(1.0, cum3[-1] - st3)), 2))
          for c, (x, y, z) in zip(cum3, t3)]

    # T2 (spur NB -> WB outer), traffic order: off the spur's west side heading north, two arcs SOUTH of T1 onto
    # J0's line, straight into J0
    of2 = min(spur2.points, key=lambda k: abs(net.points[k].pos[1] - PL.T2_OFF_Y))
    o2 = net.points[of2].pos
    # T2 runs beside T4 off J0 (the WB pair) onto the east line, T_PAIR_GAP south of it, then straight on east INSIDE
    # T1's loop and ONE right arc south onto the spur's west side (geometric order J0 -> spur, then reversed)
    yE2 = PL.T_EAST_Y - w
    tA2 = (yE2 - e2[1]) / u[1]
    A2 = (e2[0] + u[0] * tA2, e2[1] + u[1] * tA2)
    rA2 = 0.95 * tA2 / math.tan(hA / 2.0)
    C2 = (o2[0] - 13.0, yE2)
    rC2 = 0.95 * min(math.dist(A2, C2) - rA2 * math.tan(hA / 2.0), math.dist(C2, (o2[0] - 13.0, o2[1])))
    p2 = fillet([e2, A2, C2, (o2[0] - 13.0, o2[1])], [0.0, rA2, min(PL.T2_RC, rC2), 0.0], step=12.0)[::-1]
    r2 = min(rA2, PL.T2_RC, rC2)
    t2 = _heights(p2, o2[2], z0, [])
    # T2 rides LEVEL with T4 (one carriageway) where the two are side by side by J0: within T_PAIR of T4's line
    t4xy_ = [q[:2] for q in t4]
    cum2 = arclen([q[:2] for q in t2], False)
    pair = [(c, min(t4, key=lambda q: math.dist(q[:2], (x, y)))[2]) for c, (x, y, _z) in zip(cum2, t2)
            if _side((x, y), t4xy_)[1] < T_PAIR]
    if pair:
        s_p = min(c for c, _z in pair)                             # where (coming from the spur) T2 meets T4
        z_p = dict(pair)
        zp0 = z_p[s_p]
        t2 = [(x, y, round(z_p[c] if c in z_p else min(z, zp0 + T_GRADE * (s_p - c)), 2))
              for c, (x, y, z) in zip(cum2, t2)]

    print("island_expressway: T split at J0 %s: T3 R %.0f m, T4 R %.0f m, T2 R %.0f m, T1 loop R %.0f m"
          % (tuple(round(v) for v in hp[:2]), r3, r4, r2, r))
    for name, pts, at_j0_first in (("t3", t3, True), ("t1", t1, True), ("t4", t4, False), ("t2", t2, False)):
        rd = _one_lane_road(net, PREFIX + name, [(x, y, z) for (x, y, z) in pts])
        last = rd.points[0] if at_j0_first else rd.points[-1]
        net.link(last, head)
        freeze(net, last, u if at_j0_first else (-u[0], -u[1]))
    freeze(net, head, u)
    ro.make_ramp(net, on3, net.roads[PREFIX + "t3"].points[-1], lanes=T_LANES)
    ro.make_ramp(net, on1, net.roads[PREFIX + "t1"].points[-1], lanes=T_LANES)
    ro.make_ramp(net, of4, net.roads[PREFIX + "t4"].points[0], lanes=T_LANES)
    ro.make_ramp(net, of2, net.roads[PREFIX + "t2"].points[0], lanes=T_LANES)
    # no pier on the first span off J0 (four columns would stand together)
    for name in ("t3", "t1"):
        net.points[net.roads[PREFIX + name].points[0]].pillar_skip = True
    for name in ("t4", "t2"):
        net.points[net.roads[PREFIX + name].points[-2]].pillar_skip = True


SB_GRADE = 0.06   # the Suburb exit's steepest descent (P2-7: <= 6 %)
SB_LANDING = 0.0  # a level landing before the stop line: 0 -- a level foot sits inside the dike pass's clearance
                  # zone and island_dike lifted the whole exit 5 m off its junction (layout 2026-10-01: a 74 % pad)
SB_CLEAR = 6.3    # over the dike road, held across the whole overlap (island_dike.PLANNED_OVER accepts it)


def suburb_exit(net, off, ground=None):
    """The Suburb exit, Wangan EB -> the ground (user, 2026-09-30): off the north side of the waterfront diagonal, ONE S
    of two equal arcs beside the mainline, level until its band has parted from the mainline's, then down into the
    junction of teibo_sokudo_2 / kogai_michi by Suburb station as that junction's fourth (south-west) arm."""
    far = open_ramp(net, off, PREFIX + "sb_off", "FWD", False, length=45.0, lanes=EXIT_GROUND_LANES)
    m = mouth_of(net, PREFIX + "sb_off")
    road = next(r for r in net.roads.values() if off in r.points)
    k = road.points.index(off)
    q1 = net.points[road.points[k + 1]].pos
    t0 = (q1[0] - m[0], q1[1] - m[1])
    tl = math.hypot(*t0)
    t0 = (t0[0] / tl, t0[1] / tl)
    cx, cy = PL.SB_JUNCTION
    # the junction is the side road's (island_dike.sokudo) pad nearest SB_JUNCTION: its mouth and the clique linked to it
    side = min((u for n_, r in net.roads.items() if n_.startswith("teibo_sokudo") for u in r.points
                if net.points[u].role == pm.INTERSECTION),
               key=lambda u: math.dist(net.points[u].pos[:2], (cx, cy)))
    members = [side] + [l.target for l in net.points[side].links if l.type == pm.LINK_JUNCTION]
    cx, cy = (sum(net.points[u].pos[0] for u in members) / len(members),
              sum(net.points[u].pos[1] for u in members) / len(members))
    zj = sum(net.points[u].pos[2] for u in members) / max(1, len(members))
    mline = [net.points[u].pos[:2] for u in road.points]
    # it passes over ring_kita (the dike road) right after the gore and may only come down after it: the arrival heading
    # is searched for the gentlest descent from there into the junction
    # the dike step (island_dike.clear_crossings) later holds every expressway sample within both half widths + 4 m
    # of a dike road at OVER_CLEAR over it: the exit is planned by THAT rule here, or the step lifts its end 7 m off
    # the junction (layout16: a 133 % pad)
    import island_dike as ID
    rsegs = [(a_.pos, b_.pos, ID._half(r_)) for n_, r_ in net.roads.items() if n_.startswith("ring_kita")
             for a_, b_ in zip(net.chain(r_), net.chain(r_)[1:])
             if min(math.dist(a_.pos[:2], m[:2]), math.dist(b_.pos[:2], m[:2])) < 700.0]
    half_ramp = EXIT_GROUND_LANES * 4.5 / 2.0 * 2.0       # a one-way 2-lane ramp's paved width (island_dike._half's measure)

    def dike_window(p):
        """(first s, last s, highest dike z) of the samples of `p` within reach of a dike road, or None."""
        cum = arclen(p, False)
        hit = []
        for k in range(int(cum[-1] // 5.0) + 1):
            q = at_s(p, cum, k * 5.0, False)
            for a_, b_, hd in rsegs:
                dx, dy = b_[0] - a_[0], b_[1] - a_[1]
                t = min(max(((q[0] - a_[0]) * dx + (q[1] - a_[1]) * dy) / (dx * dx + dy * dy or 1.0), 0.0), 1.0)
                if math.hypot(a_[0] + dx * t - q[0], a_[1] + dy * t - q[1]) <= half_ramp + hd + 4.0:
                    hit.append((k * 5.0, a_[2] + (b_[2] - a_[2]) * t))
        if not hit:
            return None
        zr = max(z for _s, z in hit)
        if ground:
            zr = max([zr] + [ground.z(*at_s(p, cum, s_, False)) or 0.0 for s_, _z in hit])
        return hit[0][0], hit[-1][0], zr
    best = None
    for dh in range(-30, 50, 5):
        a = math.radians(dh)
        te = (t0[0] * math.cos(a) - t0[1] * math.sin(a), t0[0] * math.sin(a) + t0[1] * math.cos(a))
        e = (cx - te[0] * MOUTH, cy - te[1] * MOUTH)
        # a fourth arm, not beside another: at least 30 deg from every arm already at the junction
        arms = [(cx - net.points[u].pos[0], cy - net.points[u].pos[1]) for u in members]
        if any(math.degrees(math.acos(max(-1.0, min(1.0, (te[0] * a_[0] + te[1] * a_[1]) / max(1e-9, math.hypot(*a_))))))
               < 30.0 for a_ in arms):
            continue
        try:
            p, r = two_arc(m, t0, e, te, reach=300.0)
        except ValueError:
            continue
        if r < 60.0:
            continue
        cum = arclen(p, False)
        win = dike_window(p)
        zc, s0, sr = m[2], 0.0, None
        if win:
            sr, s0 = win[0], win[1]
            zc = max(m[2], win[2] + SB_CLEAR)
        gr = (zc - zj) / max(1.0, cum[-1] - s0 - SB_LANDING)
        # the largest radius whose descent is legal (7 %, a 40 km/h ramp), else the gentlest descent
        key = (0, -r) if gr <= SB_GRADE else (1, gr)
        if best is None or key < best[0]:
            best = (key, p, r, e, s0, zc, sr)
    _gr, p, r, e, s_ring, z_cross, s_x = best
    cum = arclen(p, False)
    def off_line(q):
        best = 1e18
        for a, b in zip(mline, mline[1:]):
            L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            t = max(0.0, min(1.0, ((q[0] - a[0]) * (b[0] - a[0]) + (q[1] - a[1]) * (b[1] - a[1])) / max(1e-9, L2)))
            best = min(best, math.dist(q, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
        return best
    # level until the two paved bands have parted (island_grades.level_gores holds it there anyway)
    s_sep = next((c for c, q in zip(cum, p) if off_line(q) >= 16.0), cum[-1] * 0.4)
    knots = [(0.0, m[2]), (s_sep, m[2])]
    if s_x is not None and z_cross > m[2]:
        knots = [(0.0, m[2]), (max(s_sep, s_x), z_cross), (s_ring, z_cross)]
    s_sep = max(s_sep, s_ring)
    knots += [(cum[-1] - SB_LANDING, zj), (cum[-1], zj)]
    grade = (knots[-3][1] - zj) / max(1.0, cum[-1] - SB_LANDING - knots[-3][0])
    print("island_expressway: Suburb exit R %.0f m, %.0f m long, over the dike at %.1f m, level/held %.0f m then "
          "%.1f %%, into %s" % (r, cum[-1], z_cross, knots[-3][0], grade * 100.0, members))
    run_on(net, PREFIX + "sb_off", on_curve(net, PREFIX + "sb_off", heights_by(p, knots)))
    end = net.roads[PREFIX + "sb_off"].points[-1]
    net.points[end].pos = (e[0], e[1], zj)
    make_junction(net, members + [end])


def _straight(a, b, step=40.0):
    n = max(1, int(math.ceil(math.dist(a, b) / step)))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]


def _ys(y0, y1, step=40.0):
    n = max(1, int(math.ceil(abs(y1 - y0) / step)))
    return [y0 + (y1 - y0) * k / n for k in range(n + 1)]

def bridge_skip(net):
    """The spur rides the Rainbow Bridge's UPPER deck: inside the suspension structure the bridge carries it, so its
    stations there are `pillar_skip` by `island_rainbow_bridge`'s own rule (a station skips when the span it starts lies
    wholly inside the structure), as `kuko_dori`'s on the lower deck are."""
    import island_rainbow_bridge as irb
    centre, axis = irb.crossing_plan()
    n = 0
    for name, r in net.roads.items():
        if not name.startswith(PREFIX + "spur"):
            continue
        pts = [net.points[u] for u in r.points]
        for i, p in enumerate(pts):
            nxt = pts[i + 1] if i + 1 < len(pts) else None
            along = lambda q: (q.pos[0] - centre[0]) * axis[0] + (q.pos[1] - centre[1]) * axis[1]
            want = (nxt is not None and abs(along(p)) <= irb.HALF_LENGTH and abs(along(nxt)) <= irb.HALF_LENGTH
                    and p.pos[2] >= irb.DECK_MIN_Z and nxt.pos[2] >= irb.DECK_MIN_Z)
            p.pillar_skip = want
            n += 1 if want else 0
    return n


THIN_SPAN = 60.0      # thinning (2026-10-01, fewer stations = a lighter record and build): the longest span kept...
THIN_TURN = 8.0      # ...the most the ORIGINAL alignment may turn within one kept span (degrees): the kit's facings
                      # (central chords) fit an arc closely at this, where the chord itself would cut the corner
THIN_DZ = 0.08        # ...and the most any removed station may stand off the straight-line height between the kept ones


def thin(net):
    """Drop expressway stations the SHAPE does not need. The generators sample every curve every 8-12 m for the
    alignment solve, which the Road Kit does not need: it faces each station along its neighbours' chord and sweeps a
    smooth curve, so an arc keeps its shape at one station per <= THIN_TURN degrees. A station with any role is kept:
    a road's ends, anything linked off its own chain (gore, joint, junction mouth), a MANUAL facing, a station whose
    lanes / aux slot / pillar_skip differ from a neighbour's (a taper or a pier span starts there). Returns the count
    removed."""
    removed = 0

    def sig(p):
        return (p.lanes_fwd, p.lanes_bwd, p.aux_fwd, p.aux_bwd, bool(p.pillar_skip), p.role, p.profile_mode)

    def heading(a, b):
        return math.atan2(b.pos[1] - a.pos[1], b.pos[0] - a.pos[0])

    for name in sorted(net.roads):
        if not name.startswith(PREFIX):
            continue
        r = net.roads[name]
        ch = net.chain(r)
        if len(ch) < 4:
            continue
        uid_ch = [p.uid for p in ch]
        keep = [False] * len(ch)
        keep[0] = keep[-1] = True
        for i, p in enumerate(ch):
            nb = set(uid_ch[max(0, i - 1):i]) | set(uid_ch[i + 1:i + 2])
            if any(l.type != pm.LINK_SEGMENT or l.target not in nb for l in p.links):
                keep[i] = True
            if p.tangent_mode == pm.MANUAL and p.uid not in PLAN_FACED:
                keep[i] = True
            if (i > 0 and sig(ch[i - 1]) != sig(p)) or (i + 1 < len(ch) and sig(ch[i + 1]) != sig(p)):
                keep[i] = True
            if p.aux_fwd or p.aux_bwd:
                keep[i] = True
        s = [0.0]
        for a, b in zip(ch, ch[1:]):
            s.append(s[-1] + math.dist(a.pos[:2], b.pos[:2]))
        a = 0
        while a < len(ch) - 1:
            b = a + 1
            while b + 1 < len(ch) and not keep[b]:
                c = b + 1
                if s[c] - s[a] > THIN_SPAN:
                    break
                turn = 0.0
                for k in range(a, c - 1):
                    d = (heading(ch[k + 1], ch[k + 2]) - heading(ch[k], ch[k + 1]) + math.pi) % (2 * math.pi) - math.pi
                    turn += abs(d)
                if math.degrees(turn) > THIN_TURN:
                    break
                za, zc = ch[a].pos[2], ch[c].pos[2]
                if any(abs(ch[k].pos[2] - (za + (zc - za) * (s[k] - s[a]) / max(1e-9, s[c] - s[a]))) > THIN_DZ
                       for k in range(a + 1, c)):
                    break
                b = c
            keep[b] = True
            a = b
        for i, p in enumerate(ch):
            if not keep[i]:
                net.remove_point(p.uid)
                removed += 1
        # relink the kept chain (a removed station took its two SEGMENT links with it)
        kept = [p for i, p in enumerate(ch) if keep[i]]
        for x, y in zip(kept, kept[1:]):
            if not x.has_link(y.uid):
                net.link(x.uid, y.uid)
    return removed


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out = argv[0]
    base = argv[argv.index("--from") + 1] if "--from" in argv else out
    net = pm.load_network(base)
    if any(n.startswith(PREFIX) for n in net.roads):
        raise SystemExit("island_expressway: %s already carries the expressway; pass --from <base record>" % base)
    ground = Ground()
    build(net, ground)
    speeds = post_speeds(net)
    n0 = sum(len(r.points) for n_, r in net.roads.items() if n_.startswith(PREFIX))
    k = 0 if "--no-thin" in argv else thin(net)
    print("island_expressway: thinned %d of %d expressway stations" % (k, n0))
    for name, r in net.roads.items():
        if name.startswith(PREFIX):
            r.taper_factor = TAPER
        south_half = name.startswith(PREFIX + "c1") and (
            sum(net.points[u].pos[1] for u in r.points) / max(1, len(r.points)) < 150.0)
        if south_half:
            r.barrier_height = SOUND_WALL      # the city side: 防音壁, sound walls, not a parapet
    for name, R, v in speeds:
        net.roads[name].base.design_speed = v
    print("island_expressway: posted " + ", ".join("%s %d (R %.0f)" % (n_[len(PREFIX):], v, R) for n_, R, v in speeds
                                                     if v < 80.0))
    for name, r in net.roads.items():
        # a RAMP is born by `branch_ramp` / `joint_ramp` and takes no road preset, so it would stand on plain BOX
        # pillars, which are sized from the ground at the deck's CENTRELINE only: over the coastal dike's steep face
        # the E JCT's ramps hung 1.18 m over the ground (probe_road_ground). A pier ASSET founds every shaft vertex
        # on the ground under itself; a ramp takes the kit's single round column (a hammerhead's 12 m cap would
        # overhang a one-way deck)
        if name.startswith(PREFIX) and not r.pillar_asset:
            r.pillar_asset = RAMP_PIER
    # No pier stands on another road: the BUILD drops each column that would (`point_mesh.pier_on_road`). The
    # station-span pass this used to run (`island_roadgen.clear_piers`) could only switch off a whole span.
    for a_, b_ in net.aux_pairs():
        ro.align_ramp(net, a_, b_)
    bridge_skip(net)
    sample_ground(net, ground)
    pm.save_network(net, out)
    print("island_expressway: %d roads, %d stations -> %s" % (len(net.roads), len(net.points), out))
    if "--fast" in argv:
        return
    findings = pv.validate(net)
    errs = pv.errors(findings)
    for f in findings:
        if f.severity == "ERROR" or f.code not in ("ground_unsampled", "pier_skipped"):
            print("  %s %s" % (f.severity, f.message[:200]))
    print("island_expressway: %d errors" % len(errs))
    flow = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "blender", "tools", "roadkit_cli.py"), "flow",
                                      out], capture_output=True, text=True).stdout)["report"]
    bad = {k: len(flow[k]) for k in ("broken", "misjoined", "unreached", "ramp_orphans", "open_end")}
    print("island_expressway: flow %d lanes, %d junctions, %s" % (flow["lanes"], flow["junctions"], bad))
    for k in ("broken", "misjoined", "unreached", "ramp_orphans"):
        for row in flow[k]:
            print("   ", k, row)
    if "--check" in argv and (errs or bad["broken"] or bad["misjoined"] or bad["unreached"] or bad["ramp_orphans"]):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
