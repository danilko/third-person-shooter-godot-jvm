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
# ONLY where C1 is central to the city (user): its SOUTH half -- the JCT road and the south-west road, i.e. the south
# side, both lower corners and the lower half of each side -- faces downtown and the station area. The north half faces
# the farmland and the mountains and keeps the preset's 1.1 m barrier for the view, as do the ramps, the spur and the
# bridge. C1's four roads are the cuts the ring already has (the JCT, both sides at y 300, the north overpass).
SOUND_WALL_ROADS = (PREFIX + "c1", PREFIX + "c1__4")
C1_SPEED = 60.0         # km/h: the inner ring is signed below the outer network's 80, as 首都高's C1 is (50-60 in the
                        # core, 80 outside). Set AFTER the build, so the aux-slot tapers stay sized for 80 (longer)
RAMP_LANES = 2          # every exit and entrance is two lanes wide (user, 3.13: a wider ramp for racing)
JCT_X = PL.JCT_X       # the airport JCT on C1's south side
SPUR_OFF = 5.5         # each spur carriageway's centre off the spur's centreline: its lanes run OUTWARD from it,
                       # so the outer lane's edge is SPUR_OFF + 2 x 4.5 = 14.5 m, inside the Rainbow Bridge's upper-deck
                       # corridor (|local z| < 15, library_landmarks). At 8.0 it stood 17 m out (3.30 L2).
AUX_CLOSE = (320.0, 440.0)   # no spur station in this arclength range: the loop's acceleration lanes (a 2-lane
                       # entrance at s 190) end at the first span long enough for their taper, and at the spur's
                       # ~60 m station spacing none was -- they ran all 2 km, four lanes over the bridge
BRIDGE_Z = 24.0        # the Rainbow Bridge's upper deck (library_landmarks.RB_ROAD_UPPER; 32 until 2026-09-29)
# THE SPUR (2026-09-29, user: "combine early as one road to reach the bridge ... the rail below the bridge", then
# "combine them as much as possible"): ONE divided road from the C1 JCT across the bridge -- the loop's merge and the
# Wangan's two ramps are aux lanes on its carriageways, and at the JCT end it splits at a joint into the two C1 ramps --
# and on the airport island a peel off the rail, a descent, a U-turn and the forecourt loop (see `build`).
SPUR_JOINT_X = 1130.0       # where the corner onto the bridge axis starts (the carriageways used to join here)
WANGAN_DIVERGE_DX = 10.0    # the westbound exit to the Wangan leaves 10 m east of the eastbound entrance: one ramp per
                            # station (the diamond's rule), the two aux slots on opposite carriageways
SPUR_JOIN_OFF = 0.5         # the one-way carriageways' offset at the joint: half the expressway preset's 1.0 m median
JOINT_CORNER_R = 120.0      # the corner onto the bridge axis (SPUR_JOINT_X = axis x - this)
SPUR_TOP_S = 480.0          # arclength where the hump over the Wangan's underpass reaches SPUR_HUMP_Z
SPUR_HUMP_Z = 27.5          # the spur over wangan_e (which passes under at ~19 m west of S: 5.5 m + the deck)
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

    # --- the spur's plan. ONE divided road from the JCT south, then east along y -500 past the Wangan's ramps
    # (user, 2026-09-29), round the corner onto the bridge axis, across the Rainbow
    # Bridge's upper deck (24 m, the rail on the lower deck at 16 m right under its median), then on the airport island
    # it peels WEST off the rail, descends to the island's ground, U-turns and ends in the forecourt loop beside the
    # station (`airport_forecourt`).
    import island_rainbow_bridge as rb
    centre, axis = rb.crossing_plan()
    half = rb.HALF_LENGTH
    na = (centre[0] - axis[0] * half, centre[1] - axis[1] * half)
    sa = (centre[0] + axis[0] * half, centre[1] + axis[1] * half)
    east_y = PL.SPUR_EAST_Y
    plan = [(JCT_X, C1_Y - 140.0), (JCT_X, east_y), (SPUR_JOINT_X, east_y)]
    cl = rounded_polygon(plan, [0.0, 100.0, 0.0], closed=False)
    ccum = arclen(cl, False)

    def s_of(pt, line=None, cum=None):
        line, cum = (cl, ccum) if line is None else (line, cum)
        best, bs = 1e18, 0.0
        for i in range(len(line) - 1):
            a, b = line[i], line[i + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1e-9:
                continue
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * (b[0] - a[0]) + (pt[1] - a[1]) * (b[1] - a[1])) / (L * L)))
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            d = math.hypot(q[0] - pt[0], q[1] - pt[1])
            if d < best:
                best, bs = d, cum[i] + t * L
        return bs
    # the Wangan's spur stations (wangan_east): the entrance's S, the exit's 10 m east of it, and a joint J before S
    s_wj, s_ws = s_of((PL.WANGAN_J_X, east_y)), s_of((PL.WANGAN_S_X, east_y))
    s_wi = s_of((PL.WANGAN_S_X + WANGAN_DIVERGE_DX, east_y))
    ss = station_at(cl, ccum, False, [0.0, 190.0, s_wj, s_ws, s_wi], loose=[ccum[-1]])
    ss = [v for v in ss if v <= ccum[-1] + 1e-6 and not (AUX_CLOSE[0] < v < AUX_CLOSE[1])]
    # the divided road's plan (record frame)
    d_plan = [(SPUR_JOINT_X, east_y), (sa[0], east_y), (sa[0], PEEL_Y), (U_X, PEEL_Y), (U_X, FORE_Y),
              (FORE_J[0] - MOUTH, FORE_Y)]
    dl = rounded_polygon(d_plan, [0.0, JOINT_CORNER_R, PEEL_R, U_R, U_R, 0.0], closed=False)
    dcum = arclen(dl, False)
    d_na, d_sa = s_of(na, dl, dcum), s_of(sa, dl, dcum)
    span = [d_na + (d_sa - d_na) * k / 12.0 for k in range(13)]
    d_hold = d_sa + PEEL_HOLD                              # the deck height held until the road is off the rail
    d_ground = s_of((U_X, PEEL_Y), dl, dcum) - U_R - 5.0     # reaches the ground before the U-turn's first corner
    # no ramp or joint TAPER is anchored on this road, so nothing is dropped round its first station (a `want` mark
    # would drop the corner's arc samples within MARK_CLEAR of the joint and cut the corner with a chord)
    ds = station_at(dl, dcum, False, [], loose=[0.0] + span + [d_hold, d_ground, dcum[-1]])
    ds = [v for v in ds if v <= dcum[-1] + 1e-6]
    zj, zm = 18.0, 24.0
    s_top = SPUR_TOP_S

    def zat(v):
        """The spur's one profile, over the one-way part's arclength (v <= ccum[-1]) and on over the divided road's
        (ccum[-1] + its own): up from the JCT, the HUMP over the Wangan's underpass (wangan_e passes under both
        carriageways west of S at ~19 m and needs 5.5 m), down to the bridge's upper deck, level across it, held off
        the rail, down to the island's ground."""
        if v <= 190.0:
            return zj + (zm - zj) * v / 190.0
        if v <= s_top:
            return zm + (SPUR_HUMP_Z - zm) * (v - 190.0) / (s_top - 190.0)
        if v <= s_ws:
            return SPUR_HUMP_Z
        vd = v - ccum[-1]
        if vd <= d_na:
            s0, s1 = s_ws, ccum[-1] + d_na
            return SPUR_HUMP_Z + (BRIDGE_Z - SPUR_HUMP_Z) * (v - s0) / (s1 - s0)
        if vd <= d_hold:
            return BRIDGE_Z
        if vd <= d_ground:
            return BRIDGE_Z + (AIR_Z - BRIDGE_Z) * (vd - d_hold) / (d_ground - d_hold)
        return AIR_Z
    # ONE divided road from the JCT all the way to the forecourt (user, 2026-09-29: "combine them as much as possible";
    # the two one-way carriageways used to run 11 m apart from the JCT to x 1130, each with its own piers and a gap
    # between). The loop's merge and the Wangan's ramps are aux lanes on its carriageways; at the JCT end it SPLITS at
    # a joint into the C1 ramps (wb_out in, in_wb out), the Wangan split's pattern.
    cpts = [at_s(cl, ccum, v, False) + (round(zat(v), 2),) for v in ss]
    dpts = [at_s(dl, dcum, v, False) + (round(zat(ccum[-1] + v), 2),) for v in ds]
    spur = chain_road(net, PREFIX + "spur", cpts + dpts[1:])
    merge_uid = spur.points[ss.index(190.0)]
    head = spur.points[0]
    half = net.resolved(head).median_width / 2.0
    h0, h1 = net.points[spur.points[0]].pos, net.points[spur.points[1]].pos
    south = (h1[0] - h0[0], h1[1] - h0[1])

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
    wbo = net.roads[PREFIX + "wb_out"]
    last = wbo.points[-1]
    net.link(last, head)
    # the JOINT: wb_out's last station HALF A MEDIAN to its own (left, east) side of the divided road's head, so its
    # one-way lanes land exactly on the southbound carriageway's -- and one FACING on both (a joint's stations must
    # share a tangent, CLAUDE.md 3.13, or the outer lane ends beside the successor's head)
    L_ = math.hypot(*south) or 1.0
    lx, ly = -south[1] / L_, south[0] / L_                    # the LEFT of travel (south -> east)
    hp = net.points[head].pos
    net.points[last].pos = (hp[0] + lx * half, hp[1] + ly * half, hp[2])
    freeze(net, head, south)
    freeze(net, last, south)
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
    net.points[in_wb.points[0]].pos = (hp[0] - lx * half, hp[1] - ly * half, hp[2])
    net.link(head, in_wb.points[0])
    freeze(net, in_wb.points[0], (-south[0], -south[1]))       # it runs AGAINST the divided road
    # no pier on the split's first span of either ramp: three hammerheads would stand on top of each other (the
    # Wangan split's rule); a station SPLIT_CLEAR out ends the skipped span
    def _lerp(u0, u1, d):
        p0, p1 = net.points[u0].pos, net.points[u1].pos
        Lp = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
        f = min(1.0, d / Lp)
        return tuple(p0[k] + (p1[k] - p0[k]) * f for k in range(3))
    q_ = insert_after(net, wbo, wbo.points[-2], _lerp(wbo.points[-1], wbo.points[-2], SPLIT_CLEAR))
    net.points[q_].pillar_skip = True
    insert_after(net, in_wb, in_wb.points[0], _lerp(in_wb.points[0], in_wb.points[1], SPLIT_CLEAR))
    net.points[in_wb.points[0]].pillar_skip = True
    ro.make_ramp(net, at["in_wb"], in_wb.points[-1], lanes=2)
    diamond(net, at)

    # --- the AIRPORT FORECOURT (user, 2026-09-29: "forecourt like central station"): the divided spur ends at FORE_J,
    # the middle of the west side of a ONE-WAY loop, two lanes, clockwise (Japan keeps left, as the Central rotary):
    # north up the west side, east along the north side, south down the east side -- the kerb beside the station's
    # west wall -- and west along the south side under the terminal's curb canopy, back to J. A one-way road lays its
    # lanes on its LEFT, so the loop's stations are its INNER edge and its 4 m outer footway is the kerb buses and taxis
    # stop at (the station wall, the terminal canopy). The inner island is `AirportForecourt`'s.
    x0, y0, x1, y1 = FORE_BOX
    jx, jy = FORE_J
    loop_plan = [(jx, jy + MOUTH), (jx, y1), (x1, y1), (x1, y0), (x0, y0), (jx, jy - MOUTH)]
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
    # last: it cuts the spur at a joint, and everything above reads the spur's own stations
    wangan_east(net, spur, ground)


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


SPLIT_CLEAR = 15.0     # the unpiered span at the Wangan's split (m)


def wangan_east(net, spur, ground=None):
    """THE WANGAN (PLAN.md 3.30 L2; `island_plan.WANGAN_*`): ONE divided 2+2 expressway with C1's centre wall (user,
    2026-09-25), from ONE T on the west-coast ring, offshore round the south-west corner and along the south
    waterfront, parting at `WANGAN_SPLIT_X` (where the two really diverge) into two one-way carriageways for a PARTIAL JCT on the spur's east leg:

    * airport -> Wangan: `shuto_wangan_w` LEAVES the spur's westbound carriageway 10 m east of S to its own left (south), descends
      south-west into the corridor's south lane line, and runs west to the split;
    * Wangan -> airport: `shuto_wangan_e` leaves the split, runs the corridor's north lane line, passes UNDER both
      spur west of S (the spur is ~26.6 m there, this ~19 m) and joins its eastbound carriageway from its own left
      (north) at S. The spur is cut at a joint J before S, because the loop JCT's acceleration lane is eastbound too
      and one run carries one aux slot.
    Wangan <-> C1 is not a movement here (two loops); it is reached through the ring and the city."""
    u_out_s = _nearest(net, spur, _g(PL.WANGAN_S_X, -PL.SPUR_EAST_Y))
    u_in_s = _nearest(net, spur, _g(PL.WANGAN_S_X + WANGAN_DIVERGE_DX, -PL.SPUR_EAST_Y))
    y_out = net.points[u_out_s].pos
    z_s = y_out[2]
    gz = (lambda x, y: max(0.0, ground.z(x, y) or 0.0)) if ground is not None else (lambda x, y: 0.0)
    cen = [(x, -z) for x, z in PL.WANGAN_CENTRE]
    cl = rounded_polygon(cen, PL.WANGAN_RADII, closed=False)
    cum = arclen(cl, False)
    n = max(2, int(round(cum[-1] / 45.0)))
    cp = [at_s(cl, cum, cum[-1] * k / n, False) for k in range(n + 1)]

    def off(i, side, d=SPUR_OFF):
        a_, b_ = cp[max(0, i - 1)], cp[min(len(cp) - 1, i + 1)]
        dx, dy = b_[0] - a_[0], b_[1] - a_[1]
        L = math.hypot(dx, dy)
        return (cp[i][0] - dy / L * d * side, cp[i][1] + dx / L * d * side)
    left = [off(i, 1) for i in range(len(cp))]          # eastbound lane line (north / north-west)
    right = [off(i, -1) for i in range(len(cp))]        # westbound lane line (south / south-east)
    deck = 11.0
    low = PL.WANGAN_LOW
    # cp runs from the corridor's north-west end (on the west shore), south, round the corner and east
    i_deck = min(i for i in range(len(cp)) if cp[i][0] >= PL.WANGAN_DECK_FROM_X)
    i_low = min(i for i in range(len(cp)) if cp[i][0] >= PL.WANGAN_LOW_FROM_X)
    k_j = min(i for i in range(len(cp)) if -cp[i][1] >= PL.WANGAN_JOIN_Z)
    i_split = min(i for i in range(len(cp)) if cp[i][0] >= PL.WANGAN_SPLIT_X)
    i_rise = min(i for i in range(len(cp)) if cp[i][0] >= PL.WANGAN_RISE_X)
    top = len(cp) - 1
    assert k_j < i_low < i_deck < i_rise < i_split < top, (k_j, i_low, i_deck, i_rise, i_split, top)
    # --- THE WANGAN ITSELF: one divided 2+2 road with C1's centre wall (user, 2026-09-25), from ONE T on the
    # west-coast ring, offshore into the corridor, round the south-west corner and along the waterfront to the split
    t = PL.WANGAN_T
    m = (t[0] - MOUTH, -t[1])
    c_plan = [m, (t[0] - MOUTH - 50.0, -(t[1] + 25.0))] + cp[k_j:i_split + 1]
    c = _profile(c_plan, {0: gz(*m), 2: low, 2 + i_low - k_j: low, 2 + i_deck - k_j: deck, 2 + i_rise - k_j: deck,
                          len(c_plan) - 1: PL.WANGAN_SPLIT_Z})
    wc = chain_road(net, PREFIX + "wangan", c)
    a, b = cut_road(net, (t[0], -t[1]), "ring_", MOUTH)
    make_junction(net, [a, b, wc.points[0]])
    # --- THE SPLIT: a divided road's end station joined to two one-way roads, each starting HALF A MEDIAN to its own
    # side. A one-way station lays its lanes out from itself outward with no median, so there each carriageway's
    # lanes are exactly where the divided road's were and `point_export.wire_joints` hands every lane over with no
    # gap. (Its tolerance is 4.5 m, so the wrong side would pass it 1 m off: `island_layout` asserts the gap.) Both
    # then flare out to the pair's lines over one 45 m span to take their own ways to the JCT.
    end = wc.points[-1]
    half = net.resolved(end).median_width / 2.0
    face = (cp[i_split + 1][0] - cp[i_split - 1][0], cp[i_split + 1][1] - cp[i_split - 1][1])
    # --- eastbound: from the split -> the corridor's north lane line -> under the spur -> S
    e_plan = [off(i_split, 1, half)] + left[i_split + 1:]
    k_top = len(e_plan) - 1
    e_plan += [(815.0, -512.0), (838.0, -478.0), (872.0, -464.0), (925.0, -463.0), (965.0, -472.0)]
    k_under = k_top + 1
    e_plan.append((PL.WANGAN_S_X, y_out[1] + 8.0 + SPUR_OFF))     # 8 m past the eastbound lanes' old centre
    e = _profile(e_plan, {0: PL.WANGAN_SPLIT_Z, k_top: max(14.0, PL.WANGAN_SPLIT_Z), k_under: 18.5, k_under + 1: 19.0,
                          len(e_plan) - 1: z_s})
    we = chain_road(net, PREFIX + "wangan_e", e, one_way=True)
    for u in we.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
    ro.make_ramp(net, u_out_s, we.points[-1], lanes=RAMP_LANES)
    # --- westbound: off the spur 10 m east of S -> down into the corridor -> west -> the split
    # Built as its own road and attached by `make_ramp`, like wangan_e: `branch_ramp` starts the mouth ON the spur's
    # centreline, and on a DIVIDED road which carriageway it is on is then a tie -- it landed on the eastbound side and
    # claimed the entrance's aux slots (aux_slot_shared). A mouth that starts south of the spur is unambiguously the
    # westbound carriageway's.
    sp = net.points[u_in_s].pos
    mouth = (sp[0], sp[1] - SPUR_OFF - 4.0)
    far = (sp[0] - 90.0, sp[1] - SPUR_OFF - 14.0)
    rw = [right[i] for i in range(top, i_split, -1)]
    w_plan = [mouth, far, (872.0, -540.0)] + rw + [off(i_split, -1, half)]
    # one steady climb from the split to the spur: the carriageways leave the split level (one deck)
    w = _profile(w_plan, {0: sp[2], 1: sp[2] - 0.5, len(w_plan) - 1: PL.WANGAN_SPLIT_Z})
    wr = chain_road(net, PREFIX + "wangan_w", w, one_way=True)
    wr.road_class = "ramp"
    for u in wr.points:
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = RAMP_LANES, 0
    ro.make_ramp(net, u_in_s, wr.points[0], lanes=RAMP_LANES)
    # it is born a RAMP (`branch_ramp`), so it never took the expressway preset's pier: stand its partner's. A plain
    # box pillar is sized from the ground at the deck's centreline only, and on a steep seabed two stopped 19 m short
    # of it (probe_road_ground); an asset pier founds each shaft vertex on the ground under itself.
    wr.pillar_asset = we.pillar_asset
    # the joint: both links, one facing on all three stations (a joint's stations must agree on it), and no pier on
    # the first span of either carriageway -- three hammerheads would stand on top of each other at the split
    for u in (we.points[0], wr.points[-1]):
        net.link(end, u)
    # a station's facing IS its forward direction, and a one-way road lays its lanes out from it: the westbound
    # carriageway runs AGAINST the divided road, so its station faces the opposite way (frozen eastward like the
    # others, its lanes landed beside the eastbound's and both its lanes were `broken`)
    freeze(net, end, face)
    freeze(net, we.points[0], face)
    freeze(net, wr.points[-1], (-face[0], -face[1]))
    # ...and ONLY a short first span: skipping the whole 45 m flare left the westbound deck 35 m up with no column
    # within 25 m (probe_road_ground). A station SPLIT_CLEAR from the split ends the skipped span; the flare past it
    # takes its own piers, by then far enough apart not to collide.
    def lerp(u0, u1, d):
        p0, p1 = net.points[u0].pos, net.points[u1].pos
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
        f = min(1.0, d / L)
        return tuple(p0[k] + (p1[k] - p0[k]) * f for k in range(3))
    insert_after(net, we, we.points[0], lerp(we.points[0], we.points[1], SPLIT_CLEAR))
    net.points[we.points[0]].pillar_skip = True
    qw = insert_after(net, wr, wr.points[-2], lerp(wr.points[-1], wr.points[-2], SPLIT_CLEAR))
    net.points[qw].pillar_skip = True
    # --- the joint on the spur between the loop JCT's merge and the Wangan's
    ro.split_at_joint(net, _nearest(net, spur, _g(PL.WANGAN_J_X, -PL.SPUR_EAST_Y)), name=PREFIX + "spur_e")


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
