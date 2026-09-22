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
* **The airport spur** (`shuto_spur*`): C1 to the Rainbow Bridge's UPPER deck (32 m) and down onto the airport.
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
# ONLY where C1 is central to the city (user): its SOUTH half -- the JCT road and the south-west road, i.e. the south
# side, both lower corners and the lower half of each side -- faces downtown and the station area. The north half faces
# the farmland and the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the
# bridge. C1's four roads are the cuts the ring already has (the JCT, both sides at y 300, the north overpass).
SOUND_WALL_ROADS = (PREFIX + "c1", PREFIX + "c1__4")
RAMP_LANES = 2          # every exit and entrance is two lanes wide (user, 3.13: a wider ramp for racing)
JCT_X = PL.JCT_X       # the airport JCT on C1's south side
SPUR_OFF = 5.5         # each spur carriageway's centre off the spur's centreline: its lanes run OUTWARD from it,
                       # so the outer lane's edge is SPUR_OFF + 2 x 4.5 = 14.5 m, inside the Rainbow Bridge's upper-deck
                       # corridor (|local z| < 15, library_landmarks). At 8.0 it stood 17 m out (3.30 L2).
AUX_CLOSE = (320.0, 440.0)   # no spur station in this arclength range: the loop's acceleration lanes (a 2-lane
                       # entrance at s 190) end at the first span long enough for their taper, and at the spur's
                       # ~60 m station spacing none was -- they ran all 2 km, four lanes over the bridge
BRIDGE_Z = 32.0        # the Rainbow Bridge's upper deck
# The airport end (3.30 L2): the spur leaves the bridge heading SOUTH on the island, turns WEST along its south side
# (descending: the upper deck is 32 m, the island 8 m, and 4% needs ~600 m), and its carriageways part onto an airport
# road SOUTH of it -- the westbound spur's left (south) carriageway turns down to junction A; the city-bound one comes
# up from junction B further west, passing north of A's arm, so the two never cross (the pre-redo end, turned).
SPUR_TURN_Y = -1850.0       # the spur's west-running stretch on the island
AIR_P = (1050.0, -1850.0)   # where the spur's carriageways part
AIR_A = (990.0, -1935.0)    # the airport-bound spur's junction on the airport road
AIR_B = (890.0, -1935.0)    # the bridge-bound spur's junction
AIR_DROP = 2.5              # the spur's tails descend this last bit off the parting point
AIR_Z = 8.0            # the airport island's ground


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


def diamond(net, at):
    """The C1 north-side DIAMOND onto naka_hondori (the `roadkit_interchange` diamond, turned): C1 runs WEST along its
    north side, so its FWD (westbound) carriageway is the south one and lands at the junction inside the ring, and
    BWD (eastbound) on the north lands at the one outside it. Exits leave before the overpass, entrances join after."""
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
        _m, info = ro.branch_ramp(net, at[name], name=PREFIX + name, aux_lanes=RAMP_LANES, carriageway=cw, entrance=ent,
                                  length=90.0, spread=10.0, drop=0.0)
        mp = net.points[info["mouth"]].pos
        fp = net.points[info["far"]].pos
        jy = jn if j is north else js
        mouth = (x0 + side * MOUTH, jy, 0.0)
        # a smooth curve from the far station (heading on from the gore) to the mouth (heading along the trunk's
        # cross road, i.e. arriving along x); the chain runs gore -> junction
        d0 = (fp[0] - mp[0], fp[1] - mp[1])
        d1 = (-side, 0.0)
        path = bezier(fp, d0, mouth, d1, 5)
        j.append(extend(net, PREFIX + name, path[1:]))
    make_junction(net, south)
    make_junction(net, north)


def c1_s(x):
    """Arclength of C1's south side at x (the ring starts at the end of the south-west corner's arc)."""
    return x - C1_CORNERS[0][0] - C1_RADIUS


def build(net, ground):
    # --- C1, with the JCT's ramp stations on its south side and the diamond's on its north side, cut into roads at
    # the JCT and half way up its east side
    plan = rounded_polygon(C1_CORNERS, C1_RADIUS)
    cum = arclen(plan, True)
    rel = {"in_wb": -330.0, "eb_loop": -120.0, "wb_out": 220.0}
    marks = {k: c1_s(JCT_X + v) for k, v in rel.items()}
    for k, x in DIAMOND_X.items():
        marks[k] = s_on(plan, cum, (x, C1_CORNERS[2][1]))
    top = C1_CORNERS[2][1]
    cut = [c1_s(JCT_X), s_on(plan, cum, (C1_CORNERS[1][0], PL.C1_SIDE_CUT_Y)), s_on(plan, cum, (DIAMOND_ROAD[1], top)),
           s_on(plan, cum, (C1_CORNERS[0][0], PL.C1_SIDE_CUT_Y))]
    st = ring(net, PREFIX + "c1", plan, ground, marks=list(marks.values()), cut_marks=cut)
    at = {k: st[v] for k, v in marks.items()}
    z1 = net.points[at["eb_loop"]].pos[2]

    def A(x, y, z):            # JCT-relative -> record
        return (JCT_X + x, C1_Y + y, z)

    # --- the spur's plan: south from the JCT, east at y -396, onto the bridge axis at its north anchorage, along it,
    # then south, west and north into the airport junction
    import island_rainbow_bridge as rb
    centre, axis = rb.crossing_plan()
    half = rb.HALF_LENGTH
    na = (centre[0] - axis[0] * half, centre[1] - axis[1] * half)
    sa = (centre[0] + axis[0] * half, centre[1] + axis[1] * half)

    def on_axis_at_y(y):
        t = (y - na[1]) / axis[1]
        return (na[0] + axis[0] * t, na[1] + axis[1] * t)
    east_y = PL.SPUR_EAST_Y
    corner_ne = on_axis_at_y(east_y)
    corner_se = on_axis_at_y(SPUR_TURN_Y)
    plan = [(JCT_X, C1_Y - 140.0), (JCT_X, east_y), corner_ne, corner_se, AIR_P]
    radii = [0.0, 100.0, 140.0, 120.0, 0.0]
    cl = rounded_polygon(plan, radii, closed=False)
    ccum = arclen(cl, False)
    # stations: the plan's vertices, plus the merge station 190 m down (the loop ramp joins there), plus the two
    # anchorages and the bridge's own station spacing across the span
    def s_of(pt):
        best, bs = 1e18, 0.0
        for i in range(len(cl) - 1):
            a, b = cl[i], cl[i + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1e-9:
                continue
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * (b[0] - a[0]) + (pt[1] - a[1]) * (b[1] - a[1])) / (L * L)))
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            d = math.hypot(q[0] - pt[0], q[1] - pt[1])
            if d < best:
                best, bs = d, ccum[i] + t * L
        return bs
    s_na, s_sa = s_of(na), s_of(sa)
    span = [s_na + (s_sa - s_na) * k / 12.0 for k in range(13)]
    # the Wangan's two spur stations (wangan_east): its ramps' station S, and a joint J on spur_out before it
    s_wj, s_ws = s_of((PL.WANGAN_J_X, east_y)), s_of((PL.WANGAN_S_X, east_y))
    ss = station_at(cl, ccum, False, [0.0, 190.0, s_wj, s_ws], loose=span + [ccum[-1]])
    ss = [v for v in ss if v <= ccum[-1] + 1e-6 and not (AUX_CLOSE[0] < v < AUX_CLOSE[1])]
    zj, zm = 18.0, 24.0

    def zat(v):
        if v <= 190.0:
            return zj + (zm - zj) * v / 190.0
        if v <= s_na:
            return zm + (BRIDGE_Z - zm) * (v - 190.0) / (s_na - 190.0)
        if v <= s_sa:
            return BRIDGE_Z
        return BRIDGE_Z + (AIR_Z + AIR_DROP - BRIDGE_Z) * (v - s_sa) / (ccum[-1] - s_sa)
    cpts = [at_s(cl, ccum, v, False) for v in ss]

    def offset(i, side):
        a = cpts[max(0, i - 1)]
        b = cpts[min(len(cpts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L                     # the LEFT of travel
        p = cpts[i]
        return (p[0] + nx * SPUR_OFF * side, p[1] + ny * SPUR_OFF * side, round(zat(ss[i]), 2))
    out_pts = [offset(i, 1) for i in range(len(cpts))]
    in_pts = [offset(i, -1) for i in range(len(cpts))][::-1]
    # the two carriageways PART at the airport: each meets the airport road at its own T (two parallel arms on one
    # pad is a pad no ring fits). The airport-bound one runs on west to junction A, the bridge-bound one leaves
    # junction B further east.
    tail = rounded_polygon([out_pts[-1][:2], (AIR_A[0], out_pts[-1][1]), (AIR_A[0], AIR_A[1] + MOUTH)], 30.0,
                           closed=False)[1:]
    out_pts += [(x, y, round(AIR_Z + AIR_DROP * (1.0 - (k + 1) / len(tail)), 2)) for k, (x, y) in enumerate(tail)]
    head = rounded_polygon([(AIR_B[0], AIR_B[1] + MOUTH), (AIR_B[0], in_pts[0][1]), in_pts[0][:2]], 30.0,
                           closed=False)[:-1]
    in_pts = [(x, y, round(AIR_Z + AIR_DROP * k / len(head), 2)) for k, (x, y) in enumerate(head)] + in_pts
    spur_out = chain_road(net, PREFIX + "spur_out", out_pts, one_way=True)
    spur_in = chain_road(net, PREFIX + "spur_in", in_pts, one_way=True)
    for r in (spur_out, spur_in):
        for u in r.points:
            net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
    merge_uid = spur_out.points[ss.index(190.0)]

    # the expressway's taper factor BEFORE its ramps: `open_aux_slot` sizes each aux slot's taper from the road's own
    # factor, and set only after the build (as it was) every slot here was sized for the book's 432 m, so the loop's
    # acceleration lanes found no span that long and ran the whole spur (3.30 L2)
    for n_, r_ in net.roads.items():
        if n_.startswith(PREFIX):
            r_.taper_factor = TAPER
    # --- the JCT (the LOOP template, `roadkit_interchange.build_loop`, three of its four movements)
    ro.branch_ramp(net, at["wb_out"], name=PREFIX + "wb_out", aux_lanes=2, carriageway="BWD", length=90.0,
                   spread=10.0, drop=0.5)
    end = extend(net, PREFIX + "wb_out", [A(60.0, -75.0, 15.5), A(SPUR_OFF, -110.0, 17.0), A(SPUR_OFF, -140.0, 18.0)])
    net.points.pop(end)
    net.roads[PREFIX + "wb_out"].points.remove(end)
    for p_ in net.points.values():
        p_.unlink(end)
    net.link(net.roads[PREFIX + "wb_out"].points[-1], spur_out.points[0])
    # wb_out's last station and spur_out's first are the JOINT: make them one position, one facing
    last = net.roads[PREFIX + "wb_out"].points[-1]
    net.points[last].pos = net.points[spur_out.points[0]].pos
    # ...and one FACING: a joint's two end stations must share a tangent (CLAUDE.md, 3.13), or the outer lane ends
    # beside the successor's head -- after the land redo the ramp met the spur at a 41 deg kink and wb_out_F1 was broken
    s0, s1 = net.points[spur_out.points[0]].pos, net.points[spur_out.points[1]].pos
    for u in (last, spur_out.points[0]):
        freeze(net, u, (s1[0] - s0[0], s1[1] - s0[1]))
    ro.branch_ramp(net, at["eb_loop"], name=PREFIX + "eb_loop", aux_lanes=RAMP_LANES, carriageway="FWD", length=80.0,
                   spread=8.0, drop=0.5)
    pts = [A(150.0, 45.0, z1)] + [A(x - JCT_X, y - C1_Y, z) for (x, y, z) in
                                   arc(JCT_X + 150.0, C1_Y + 125.0, 80.0, -90.0, 180.0, z1, 20.0, 9)]
    pts += [A(70.0, 40.0, 21.0), A(70.0, -110.0, 23.0), A(35.0, -250.0, 23.8), A(26.0, -300.0, 24.0)]
    extend(net, PREFIX + "eb_loop", pts)
    ro.make_ramp(net, merge_uid, net.roads[PREFIX + "eb_loop"].points[-1], lanes=RAMP_LANES)
    in_wb = chain_road(net, PREFIX + "in_wb", [A(-SPUR_OFF, -140.0, 18.0), A(-SPUR_OFF, -110.0, 17.0),
                                               A(-40.0, -70.0, 14.0), A(-110.0, -40.0, 12.5),
                                               A(-160.0, -22.0, 11.5)], one_way=True)
    in_wb.road_class = "ramp"
    for u in in_wb.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
    net.points[in_wb.points[0]].pos = net.points[spur_in.points[-1]].pos
    net.link(spur_in.points[-1], in_wb.points[0])
    ro.make_ramp(net, at["in_wb"], in_wb.points[-1], lanes=2)
    diamond(net, at)
    for a_, b_ in ((net.roads[PREFIX + "wb_out"].points[-2], spur_out.points[1]),
                   (spur_in.points[-2], in_wb.points[1])):
        pass

    # --- the airport road, ON the island only (R7: the bridge's lower deck is rail, cars cross on the spur): from its
    # east end through junction B (the bridge-bound spur leaves) and junction A (the airport-bound spur arrives), then
    # on to the terminal. Its east end is a free end the turnaround pass loops.
    def toward(c, q, d):
        L = math.hypot(q[0] - c[0], q[1] - c[1])
        return (c[0] + (q[0] - c[0]) / L * d, c[1] + (q[1] - c[1]) / L * d, AIR_Z)
    east_end = (AIR_A[0] + 140.0, AIR_A[1])
    road0 = chain_road(net, "airport_dori", [east_end + (AIR_Z,), toward(AIR_A, east_end, MOUTH)], preset=None)
    road0.road_class = "arterial"
    road0.base.median_width, road0.base.left_walk_width, road0.base.right_walk_width = 3.0, 4.0, 4.0
    # West of junction A the airport road is ONE-WAY and turns north at B straight into the bridge-bound spur (a
    # joint). There used to be a two-way stub on west past B to a turnaround loop, but the island ends at x ~815 there:
    # the loop could only turn 90 deg off the stub, its connector was a ~125 deg turn inside a small pad, and traffic
    # ran onto its kerb (`probe_traffic_spawn`, reclaimed `stalled` twice). Now every movement on the airport side is a
    # through route: spur out -> A -> east to the terminal (and its loop), or -> west -> B -> spur in.
    j = net.points[spur_in.points[0]].pos
    bend = rounded_polygon([toward(AIR_A, AIR_B, MOUTH)[:2], AIR_B, j[:2]], 20.0, closed=False)
    road1 = chain_road(net, "airport_dori__2", [(x, y, AIR_Z) for x, y in bend[:-1]] + [tuple(j)], preset=None,
                       one_way=True)
    road1.road_class = "arterial"
    road1.base.lanes_fwd, road1.base.lanes_bwd = 2, 0
    road1.base.left_walk_width, road1.base.right_walk_width = 4.0, 4.0
    for v in road1.points:
        net.points[v].lanes_fwd, net.points[v].lanes_bwd = 2, 0
    make_junction(net, [road0.points[-1], road1.points[0], spur_out.points[-1]])
    # the joint: coincident end stations sharing one facing (a joint's two ends must agree, or the outer lane breaks)
    up = (j[0] - AIR_B[0], j[1] - AIR_B[1])
    freeze(net, road1.points[-1], up)
    freeze(net, spur_in.points[0], up)
    net.link(road1.points[-1], spur_in.points[0])
    # last: it cuts spur_out at a joint, and everything above reads spur_out's own ends
    wangan_east(net, spur_out, spur_in, ground)


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


def wangan_east(net, spur_out, spur_in, ground=None):
    """THE WANGAN (PLAN.md 3.30 L2; `island_plan.WANGAN_*`): two one-way elevated carriageways, like the spur, from a
    PARTIAL JCT on the spur's east leg along the south waterfront (offshore of the park), over the gulf and the ring's
    port-corner bend, then west along the port platform's north strip, each coming down to its own T on the ring (two
    parallel one-way arms on one pad is a pad no ring fits -- the airport end's rule).

    * airport -> Wangan: `shuto_wangan_w` LEAVES spur_in (westbound there) at S to its own left (south), descends
      south-west into the corridor's south lane line, and runs west to its T;
    * Wangan -> airport: `shuto_wangan_e` rises from its T, runs the corridor's north lane line, passes UNDER both
      spur carriageways west of S (the spur is ~26.6 m there, this ~19 m) and joins spur_out from its own left
      (north) at S. spur_out is cut at a joint J before S, because the loop JCT's acceleration lane is on spur_out too
      and one run carries one aux slot.
    Wangan <-> C1 is not a movement here (two loops); it is reached through the ring and the city."""
    u_out_s = _nearest(net, spur_out, _g(PL.WANGAN_S_X, 494.0))
    u_in_s = _nearest(net, spur_in, _g(PL.WANGAN_S_X, 506.0))
    y_out = net.points[u_out_s].pos
    z_s = y_out[2]
    gz = (lambda x, y: max(0.0, ground.z(x, y) or 0.0)) if ground is not None else (lambda x, y: 0.0)
    cen = [(x, -z) for x, z in PL.WANGAN_CENTRE]
    cl = rounded_polygon(cen, PL.WANGAN_RADII, closed=False)
    cum = arclen(cl, False)
    n = max(2, int(round(cum[-1] / 45.0)))
    cp = [at_s(cl, cum, cum[-1] * k / n, False) for k in range(n + 1)]

    def off(i, side):
        a_, b_ = cp[max(0, i - 1)], cp[min(len(cp) - 1, i + 1)]
        dx, dy = b_[0] - a_[0], b_[1] - a_[1]
        L = math.hypot(dx, dy)
        return (cp[i][0] - dy / L * SPUR_OFF * side, cp[i][1] + dx / L * SPUR_OFF * side)
    left = [off(i, 1) for i in range(len(cp))]          # eastbound lane line (north / north-west)
    right = [off(i, -1) for i in range(len(cp))]        # westbound lane line (south / south-east)
    deck = 11.0
    i_deck = min(i for i in range(len(cp)) if cp[i][0] >= PL.WANGAN_DECK_FROM_X)
    top = len(cp) - 1
    # --- eastbound: its T on the ring -> the corridor -> under the spur -> the gore at S
    te = PL.WANGAN_T_E
    m_e = (te[0], -(te[1] + MOUTH))
    e_plan = [m_e, (te[0] + 25.0, -(te[1] + MOUTH + 22.0))] + left
    k_top = len(e_plan) - 1
    e_plan += [(815.0, -512.0), (838.0, -478.0), (872.0, -464.0), (925.0, -463.0), (965.0, -472.0)]
    k_under = k_top + 1
    e_plan.append((PL.WANGAN_S_X, y_out[1] + 8.0))
    e = _profile(e_plan, {0: gz(*m_e), 2 + i_deck: deck, k_top: 14.0, k_under: 18.5, k_under + 1: 19.0,
                          len(e_plan) - 1: z_s})
    we = chain_road(net, PREFIX + "wangan_e", e, one_way=True)
    for u in we.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
    ro.make_ramp(net, u_out_s, we.points[-1], lanes=RAMP_LANES)
    # --- westbound: off spur_in at S -> down into the corridor -> west -> its T
    _m, info = ro.branch_ramp(net, u_in_s, name=PREFIX + "wangan_w", aux_lanes=RAMP_LANES, carriageway="FWD",
                              length=90.0, spread=10.0, drop=-0.5)
    far = net.points[info["far"]].pos
    tw = PL.WANGAN_T_W
    m_w = (tw[0], -(tw[1] + MOUTH))
    w_plan = [(far[0], far[1]), (872.0, -540.0)] + right[::-1] + [(tw[0] + 40.0, -(tw[1] + 70.0)),
                                                                   (tw[0] + 10.0, -(tw[1] + 45.0)), m_w]
    j_deck = 2 + (top - i_deck)
    i600 = min(range(len(cp)), key=lambda i: abs(cp[i][0] - 600.0) + abs(cp[i][1] + 800.0))
    w = _profile(w_plan, {0: far[2], 2: 21.5, 2 + (top - i600): deck, j_deck: deck, len(w_plan) - 1: gz(*m_w)})
    extend(net, PREFIX + "wangan_w", w[1:])
    wr = net.roads[PREFIX + "wangan_w"]
    for u in wr.points[1:]:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = RAMP_LANES, 0
    # --- the two T's on the ring along the port's north edge
    for t, arm in ((te, we.points[0]), (tw, wr.points[-1])):
        a, b = cut_road(net, (t[0], -t[1]), "ring_", MOUTH)
        make_junction(net, [a, b, arm])
    # --- the joint on spur_out between the loop JCT's merge and the Wangan's
    ro.split_at_joint(net, _nearest(net, spur_out, _g(PL.WANGAN_J_X, 494.0)), name=PREFIX + "spur_out_w")


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
