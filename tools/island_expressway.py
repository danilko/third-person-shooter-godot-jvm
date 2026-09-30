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
* **The Wangan** (`shuto_wangan*`): the sketch's outer ring as a coastal HORSESHOE. The sketch closes it over the
  north-west massif, 700 m high with the touge on it; the Road Kit has no tunnels, so the ring stops at the massif's
  foot at both ends and comes down to ground at a terminal junction.
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
C1_Y = C1_CORNERS[0][1]
SOUND_WALL = 3.0        # a city expressway's sound walls (防音壁)
# ONLY where C1 is central to the city (user): its SOUTH half faces downtown and the station area; the north half faces
# the farmland and the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the
# bridge. The ring's roads south of its east / west cuts (see `build`): c1 (775 -> east y 150), c1__5 (west y 375 ->
# south x 400, round the SW corner) and c1__6 (south x 400 -> 775).
RAMP_PIER = "RKA_PIER_round"
SOUND_WALL_ROADS = (PREFIX + "c1", PREFIX + "c1__5", PREFIX + "c1__6")
C1_SPEED = 60.0         # km/h: the inner ring is signed below the outer network's 80, as 首都高's C1 is (50-60 in the
                        # core, 80 outside). Set AFTER the build, so the aux-slot tapers stay sized for 80 (longer)
RAMP_LANES = 2          # every exit and entrance is two lanes wide (user, 3.13: a wider ramp for racing)
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
    pl = rounded_polygon(corners, radii, closed=False)
    cum = arclen(pl, False)
    n = max(2, int(math.ceil(cum[-1] / step)))
    return [at_s(pl, cum, cum[-1] * k / n, False) for k in range(n + 1)]


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


def open_ramp(net, at, name, cw, entrance, length=90.0, spread=10.0):
    """A RAMP off (or onto) C1 / a divided road at station `at`: `branch_ramp` opens the aux slot and places the mouth
    and the far station (level with the mainline through the gore). Returns the far station's position (x, y, z); the
    caller runs the ramp on from there with `extend`."""
    _m, info = ro.branch_ramp(net, at, name=name, aux_lanes=RAMP_LANES, carriageway=cw, entrance=entrance,
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


def diamond(net, at):
    """The C1 north-side TIGHT DIAMOND onto naka_hondori (PLAN.md NEXT, 2026-09-29 night): each ramp HUGS the viaduct --
    it leaves the gore parallel to C1, descends beside it and bends onto the cross street at a signalised junction ~45 m
    off C1's centreline (the old diamond swung ~100 m sideways and carved the blocks between). C1 runs WEST along its
    north side, so its FWD (westbound) carriageway is the south one and lands at the junction inside the ring, and BWD
    (eastbound) on the north lands at the one outside it. Exits leave before the overpass, entrances join after."""
    x0 = DIAMOND_ROAD[1]
    js, jn = DIAMOND_J
    s_a, s_b = cut_road(net, (x0, js), DIAMOND_ROAD[0], MOUTH)
    n_a, n_b = cut_road(net, (x0, jn), DIAMOND_ROAD[0], MOUTH)
    south, north = [s_a, s_b], [n_a, n_b]
    ramps = (  # name, carriageway, entrance, junction side (-1 west mouth, +1 east mouth), junction
        ("d_bwd_off", "BWD", False, -1, north),
        ("d_bwd_on", "BWD", True, 1, north),
        ("d_fwd_off", "FWD", False, 1, south),
        ("d_fwd_on", "FWD", True, -1, south),
    )
    for name, cw, ent, side, j in ramps:
        # level with C1 through the diverge (drop 0): a ramp already 2 m down while it still shares the gore with the
        # mainline left a lip a straddling car launched off (probe_road_launch, 3.1 m/s); it descends after the gore
        # the far station 16 m out and 60 m along: its paved band has parted from C1's there (island_grades.level_gores
        # holds a ramp level with its mainline until they part -- at 8 m out the inside ramps never did, and came down
        # 11 m over their last 30 m onto a 59 % pad), so the ramp descends over its whole ~170 m run (~6.5 %)
        _m, info = ro.branch_ramp(net, at[name], name=PREFIX + name, aux_lanes=RAMP_LANES, carriageway=cw, entrance=ent,
                                  length=60.0, spread=16.0, drop=0.0)
        fp = net.points[info["far"]].pos
        jy = jn if j is north else js
        mouth = (x0 + side * MOUTH, jy)
        # parallel to C1 (the far station's own line) until 70 m short of the cross road, then a gentle S onto the
        # junction's arm; the chain runs gore -> junction
        bend_x = mouth[0] + side * 70.0
        path = [(fp[0] + (bend_x - fp[0]) * k / 3.0, fp[1]) for k in range(1, 4)]
        s_curve = bezier((bend_x, fp[1], 0.0), (-side, 0.0), (mouth[0], mouth[1], 0.0), (-side, 0.0), 4)[1:]
        path += [(p[0], p[1]) for p in s_curve]
        zs = ramp_heights([(fp[0], fp[1])] + path, fp[2], 0.0, hold1=12.0)[1:]
        extend(net, PREFIX + name, [(x, y, round(z, 2)) for (x, y), z in zip(path, zs)])
        j.append(net.roads[PREFIX + name].points[-1])
    make_junction(net, south)
    make_junction(net, north)


def build(net, ground):
    """C1 with its four access points (PLAN.md NEXT, 2026-09-29 night): the N tight diamond, the W JCT (the Wangan), the
    E JCT (the airport spur), and the Wangan and the spur themselves."""
    # --- C1: a closed ring, counter-clockwise in the record (FWD = the inner carriageway), a station at every ramp's
    # mark and cut into roads at joints so no run carries two ramps on one carriageway (one aux slot per run)
    plan = rounded_polygon(C1_CORNERS, C1_RADIUS)
    cum = arclen(plan, True)
    xs, xe, yb, yt = C1_CORNERS[0][0], C1_CORNERS[1][0], C1_Y, C1_CORNERS[2][1]
    pts = {
        "w_bwd_on": (PL.W_BWD_ON_X, yb), "w_bwd_off": (PL.W_BWD_OFF_X, yb), "w_fwd_on": (PL.W_FWD_ON_X, yb),
        "w_fwd_off": (xs, PL.W_FWD_OFF_Y),
        "e_fwd_off": (PL.E_FWD_OFF_X, yb), "e_bwd_on": (PL.E_BWD_ON_X, yb), "e_bwd_off": (xe, PL.E_BWD_OFF_Y),
    }
    for k, x in DIAMOND_X.items():
        pts[k] = (x, yt)
    marks = {k: s_on(plan, cum, v) for k, v in pts.items()}
    cut_at = [(PL.C1_SOUTH_CUT_X, yb), (xe, PL.C1_SIDE_CUT_Y), (xe, 365.0), (DIAMOND_ROAD[1], yt), (xs, 375.0),
              (400.0, yb)]
    cut = [s_on(plan, cum, p) for p in cut_at]
    st = ring(net, PREFIX + "c1", plan, ground, marks=list(marks.values()), cut_marks=cut)
    at = {k: st[v] for k, v in marks.items()}
    for n_, r_ in net.roads.items():
        if n_.startswith(PREFIX):
            r_.taper_factor = TAPER
    zc = lambda k: net.points[at[k]].pos[2]    # noqa: E731

    # --- the WANGAN, from its west-coast T to the leg's joint below C1 (its two C1 ramps attach there)
    wangan, marks_w = wangan_road(net, ground)
    for n_, r_ in net.roads.items():
        if n_.startswith(PREFIX):
            r_.taper_factor = TAPER
    head_w = wangan.points[-1]
    hw = net.points[head_w].pos
    zw = hw[2]
    north = (0.0, 1.0)
    L = PL.W_LEG_X
    jy = PL.W_JOINT_Y
    # W1: leg NB -> C1 BWD (westbound, outer). Built from C1 outward: branch_ramp's entrance chain runs mouth -> far ->
    # the joint (traffic the other way), so its lanes are BWD. From the far station (45 m east of the mouth, 10 m
    # south) it bends round onto x L - 0.5 heading south and down to the joint.
    far = open_ramp(net, at["w_bwd_on"], PREFIX + "w_bwd_on", "BWD", True, length=45.0)
    p = fillet([far[:2], (L - 0.5, far[1]), (L - 0.5, jy)], [0.0, 45.0, 0.0])
    run_on(net, PREFIX + "w_bwd_on", heights_by(p, [(0.0, far[2]), (1e9, zw)])[1:])
    joint_ramp(net, PREFIX + "w_bwd_on", head_w, north, 1, against=True)
    # W2: C1 BWD -> leg SB: out south of C1 and west, round onto x L + 0.5 heading south, down to the joint
    far = open_ramp(net, at["w_bwd_off"], PREFIX + "w_bwd_off", "BWD", False)
    p = fillet([far[:2], (L + 0.5, far[1]), (L + 0.5, jy)], [0.0, 55.0, 0.0])
    run_on(net, PREFIX + "w_bwd_off", heights_by(p, [(0.0, far[2]), (1e9, zw)])[1:])
    joint_ramp(net, PREFIX + "w_bwd_off", head_w, north, -1, against=True)
    # W3 (its run down the leg's east side is 28 m off the leg's centre, so the paved bands part and level_gores lets
    # it keep its height over the leg): C1 FWD -> the Wangan: exits C1's WEST side (heading south, to the inside), a flyover diagonally across the SW
    # quadrant, over C1's south side (x ~300, clear of the Bay station's box to its south), over the NB ramp and the
    # leg, then south on the leg's east side and onto its SB carriageway from the east (keep-left)
    fz = PL.W_FLY_Z
    merge_y = marks_w["fwd_merge"]
    far = open_ramp(net, at["w_fwd_off"], PREFIX + "w_fwd_off", "FWD", False)
    p = fillet([far[:2], (xs + 30.0, 60.0), (150.0, -20.0), (255.0, -62.0), (320.0, -150.0), (352.0, -265.0),
                (L + 28.0, -335.0), (L + 28.0, merge_y + 50.0), (L + 14.0, merge_y)],
               [0.0, 80.0, 90.0, 70.0, 80.0, 60.0, 40.0, 0.0, 0.0])
    s1 = s_first(p, lambda q: q[1] <= -60.0)                       # at W_FLY_Z before C1's south side
    s2 = s_first(p, lambda q: q[1] <= -335.0)                      # ...and still up once past the leg
    fw = run_on(net, PREFIX + "w_fwd_off", heights_by(p, [(0.0, far[2]), (s1, fz), (s2, fz), (1e9, zw)])[1:])
    ro.make_ramp(net, marks_w["fwd_merge_uid"], fw.points[-1], lanes=RAMP_LANES)
    # W4: the Wangan -> C1 FWD: leaves the leg's NB carriageway (to its left, west) south of the ring, climbs north on
    # the west side, crosses over the leg diagonally (south of the W3 merge's taper), north up its east side over the SB
    # ramp and C1, then east along the ring's inside and onto C1's FWD carriageway from the inside
    far = open_ramp(net, marks_w["fwd_div_uid"], PREFIX + "w_fwd_on", "FWD", False, length=60.0)
    # it climbs on the WEST side first and crosses the leg only once it is up: a ramp crossing its own mainline while
    # still low runs through the median wall (probe_road_clear), and island_grades.level_gores holds it at the
    # mainline's height until the two paved bands part, so the west run is 28 m off the leg's centre
    p = fillet([far[:2], (L - 28.0, far[1] + 50.0), (L - 28.0, -520.0), (L + 45.0, -430.0), (L + 45.0, -175.0),
                (445.0, -112.0), (520.0, -82.0), (PL.W_FWD_ON_X - 40.0, -80.0)],
               [0.0, 40.0, 50.0, 60.0, 60.0, 60.0, 60.0, 0.0])
    s1 = s_first(p, lambda q: q[1] >= -520.0)                      # at W_FLY_Z before it turns across the leg
    s2 = s_first(p, lambda q: q[0] >= 470.0)
    wf = run_on(net, PREFIX + "w_fwd_on", heights_by(p, [(0.0, far[2]), (s1, fz), (s2, fz), (1e9, zc("w_fwd_on"))])[1:])
    ro.make_ramp(net, at["w_fwd_on"], wf.points[-1], lanes=RAMP_LANES)

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
    s_merge = ey - PL.E_FWD_MERGE_Y
    s_tap = ey - PL.SPUR_T_CLEAR[0]            # the merge's taper ends here; nothing of the spur's own until the bridge
    span = [d_na + (d_sa - d_na) * k / 12.0 for k in range(13)]
    d_hold = d_sa + PEEL_HOLD
    d_ground = s_of((U_X, PEEL_Y)) - U_R - 5.0
    ds = [0.0, s_merge, s_tap] + span + [d_hold]
    # the peel / U-turn / forecourt part keeps its plan vertices (the corners' arcs), clear of the marks
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
    for n_, r_ in net.roads.items():
        if n_.startswith(PREFIX):
            r_.taper_factor = TAPER
    head_e = spur.points[0]
    south = (0.0, -1.0)
    merge_uid = spur.points[ds.index(round(s_merge, 3))]
    # E1: C1 BWD (southbound on the east side, outer) -> the spur SB: out east of C1, over ring_kita (the dike along
    # x ~1235) and straight down x 1266 -- 13 m clear of the ring's paved edge, so its piers stand off the ring's band --
    # then onto x 1250.5 and the joint
    far = open_ramp(net, at["e_bwd_off"], PREFIX + "e_bwd_off", "BWD", False)
    p = fillet([far[:2], (1266.0, 60.0), (1266.0, -150.0), (bx + 0.5, ey + 40.0), (bx + 0.5, ey)],
               [0.0, 80.0, 60.0, 60.0, 0.0])
    s1 = s_first(p, lambda q: q[0] >= 1225.0)
    run_on(net, PREFIX + "e_bwd_off", heights_by(p, [(0.0, far[2]), (s1, zj), (1e9, zj)])[1:])
    joint_ramp(net, PREFIX + "e_bwd_off", head_e, south, 1, against=False)
    # E2: the spur NB -> C1 BWD (westbound on the south side, outer): from the joint north on x 1249.5, round west over
    # the ring, along the outside of C1's SE corner, onto C1 from the south
    far = open_ramp(net, at["e_bwd_on"], PREFIX + "e_bwd_on", "BWD", True)
    p = fillet([far[:2], (bx - 0.5, far[1]), (bx - 0.5, ey)], [0.0, 80.0, 0.0])
    s1 = s_first(p, lambda q: q[0] >= 1150.0)
    run_on(net, PREFIX + "e_bwd_on", heights_by(p, [(0.0, far[2]), (s1, zj), (1e9, zj)])[1:])
    joint_ramp(net, PREFIX + "e_bwd_on", head_e, south, -1, against=False)
    # E3: C1 FWD (eastbound on the south side, inner) -> the airport: a flyover off the inside, round the inside of the
    # SE corner climbing, out over C1's east side (y ~5), over the ring and the E1 ramp, round south on x 1285 and down
    # onto the spur's SB carriageway from the east
    ez = PL.E_FLY_Z
    far = open_ramp(net, at["e_fwd_off"], PREFIX + "e_fwd_off", "FWD", False)
    p = fillet([far[:2], (1070.0, yb + 30.0), (1140.0, -35.0), (1215.0, 10.0), (1285.0, 10.0),
                (1285.0, PL.E_FWD_MERGE_Y + 50.0), (1276.0, PL.E_FWD_MERGE_Y)],
               [0.0, 90.0, 70.0, 60.0, 60.0, 0.0, 0.0])
    s1 = s_first(p, lambda q: q[0] >= 1150.0)
    s2 = s_first(p, lambda q: q[1] <= -60.0 and q[0] >= 1280.0)
    zm = net.points[merge_uid].pos[2]
    ef = run_on(net, PREFIX + "e_fwd_off", heights_by(p, [(0.0, far[2]), (s1, ez), (s2, ez), (1e9, zm)])[1:])
    ro.make_ramp(net, merge_uid, ef.points[-1], lanes=RAMP_LANES)
    diamond(net, at)

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
    make_junction(net, [spur.points[-1], loop.points[0], loop.points[-1]])


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


def wangan_road(net, ground=None):
    """THE WANGAN (PLAN.md NEXT, 2026-09-29 night; `island_plan.WANGAN_*`): ONE divided 2+2 expressway with C1's centre
    wall, from a T on the west-coast ring's straight (a mouth due west), offshore round the south-west corner, east
    along the south waterfront past the port platform, then NORTH up the leg beside the rail corridor to its joint below
    C1 (`W_JOINT_Y`), where the W JCT's two C1 ramps join it. Returns (the road, {"fwd_merge": record y,
    "fwd_merge_uid": the leg station the C1 -> Wangan flyover merges at (SB carriageway), "fwd_div_uid": the leg station
    the Wangan -> C1 flyover leaves (NB carriageway)})."""
    t = PL.WANGAN_T
    a, b = cut_road(net, (t[0], -t[1]), "ring_", MOUTH)
    z_ring = (net.points[a].pos[2] + net.points[b].pos[2]) / 2.0
    cen = [(x, -z) for x, z in PL.WANGAN_CENTRE]
    cl = rounded_polygon(cen, PL.WANGAN_RADII, closed=False)
    cum = arclen(cl, False)
    L = PL.W_LEG_X

    def s_at_y(y):          # the leg is straight up x L: arclength of record y on it
        return cum[-1] - (PL.W_JOINT_Y - y)
    y_merge = -440.0                           # the C1 -> Wangan flyover merges here (SB)
    y_div = -740.0                             # the Wangan -> C1 flyover leaves here (NB)
    want = [s_at_y(y_merge), s_at_y(y_div)]
    n = max(2, int(round(cum[-1] / 45.0)))
    base = [cum[-1] * k / n for k in range(n + 1)]
    ss = sorted(set([round(c, 3) for c in base if all(abs(c - m) > MARK_CLEAR for m in want)] +
                    [round(m, 3) for m in want]))
    pts = [at_s(cl, cum, v, False) for v in ss]
    # heights: the ring's own at the mouth, down to the low sea viaduct, up to 11 m over the port platform, 14 m where it
    # crosses ring_kita's corner (x ~236, 7.8 m on the dike), and the leg at W_LEG_Z north of y -760
    zs = []
    for (x, y), v in zip(pts, ss):
        if v == ss[0]:
            z = z_ring
        elif x < PL.WANGAN_LOW_FROM_X:
            z = PL.WANGAN_LOW
        elif x < PL.WANGAN_DECK_FROM_X:
            z = PL.WANGAN_LOW + (11.0 - PL.WANGAN_LOW) * (x - PL.WANGAN_LOW_FROM_X) / (PL.WANGAN_DECK_FROM_X - PL.WANGAN_LOW_FROM_X)
        elif x < PL.WANGAN_RING_X - 150.0:
            z = 11.0
        elif abs(x - L) > 1.0 or y < -800.0:
            z = min(14.0, 11.0 + 3.0 * max(0.0, x - (PL.WANGAN_RING_X - 150.0)) / 150.0)
        else:
            z = max(PL.W_LEG_Z, 14.0 - (14.0 - PL.W_LEG_Z) * (y + 800.0) / 80.0)
        zs.append(z)
    # the first offshore stations ease from the ring's height down to the low viaduct
    zs[1] = (z_ring + PL.WANGAN_LOW) / 2.0 if len(zs) > 2 else zs[1]
    w = chain_road(net, PREFIX + "wangan", [(x, y, round(z, 2)) for (x, y), z in zip(pts, zs)])
    make_junction(net, [a, b, w.points[0]])
    uid_of = {round(v, 3): u for v, u in zip(ss, w.points)}
    return w, {"fwd_merge": y_merge, "fwd_merge_uid": uid_of[round(want[0], 3)],
               "fwd_div_uid": uid_of[round(want[1], 3)]}


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
    for name, r in net.roads.items():
        if name.startswith(PREFIX):
            r.taper_factor = TAPER
        if name in SOUND_WALL_ROADS:
            r.barrier_height = SOUND_WALL      # the city side: 防音壁, sound walls, not a parapet
        if name.startswith(PREFIX + "c1"):
            r.base.design_speed = C1_SPEED
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
