#!/usr/bin/env python3
"""island_dike.py -- THE RING ROAD IS THE DIKE (user, 2026-09-26, with a Japanese container-terminal schematic).

    python3 tools/island_dike.py raise  <record>                     # layout: dike heights + every ramp onto them
    python3 tools/island_dike.py sculpt <in.f32> <record> <out.f32>  # natural: the embankment and its ramps

A coastal embankment road (二線堤, the shape Sendai's east-coast roads were rebuilt to after 3.11): the island's
coastal ring (`ring_kita`, `kaigan_machi`) is the protection line, and it runs on the dike's crest.

    sea  <- 1:25 beach <- +3 m <- 1:3 <- outside-dike land (+5.6, the harbour aprons too) <- 1:2 face | parapet |
           rail strip | road | 1:1.5 slope -> the town (+5.6)

  * CREST 12 m where the ring faces the bay, 14.7 m where it faces the open ocean (the open-sea fraction within 1 km,
    `island_reshape.EXPOSURE_*`), eased along the road no steeper than RAMP_GRADE.
  * THE CREST CARRIES the road on its LAND-side half and a reserved RAIL strip (RAIL_W) on its SEA-side half, with a
    wave-return parapet at the outer edge: a rail line along the coast then crosses nothing, every road junction is
    on the land side of the track.
  * THE HARBOURS ARE OUTSIDE THE DIKE, as in the schematic: their aprons stay at +5.6 m (a terminal deck is +4 to +6
    m T.P.) with vertical quays, and their roads ramp DOWN from the crest.
  * ONLY ROADS THAT JOIN THE RING CLIMB IT: every road meeting a dike station at a junction or a joint is ramped at
    RAMP_GRADE from the junction's crest height (a station is inserted where the ramp meets its own profile). Block
    streets keep clear of the embankment (`island_streets` reads the corridor this writes) and end at their last
    cross street, so the ring is not a string of steep T's.

`raise` writes CORRIDOR (the centrelines the street planner keeps clear of); `sculpt` builds the terrain under the
dike roads and the ramps (fill only; the dike may stand in the sea's edge, a revetment) and records the embankment's
cells in island_dike.json under "cells" (painted concrete by `island_ground`, kept clear of blocks and buildings).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import island_reshape as RS     # noqa: E402
import point_model as pm        # noqa: E402

DIKE_ROADS = ("ring_kita", "kaigan_machi")
RAMP_GRADE = 0.05
RAIL_W = 12.0            # the rail strip on the crest's sea side (double track + walkway)
PARAPET = 1.0            # the wave-return wall beyond it
SHOULDER = 1.5           # crest past the road's land-side edge
LAND_SLOPE = 1.5         # the town-side slope, horizontal per vertical
SEA_SLOPE = 2.0          # the sea-side face
RAMP_VERGE = 3.0         # a ramp's embankment top past its paved edge
REACH = 400.0            # a ramp may reach this far along the joining road
CORRIDOR = os.path.join(rg.ROOT, "assets", "world_source", "island_dike_line.json")
DIKE_JSON = RS.DIKE_JSON


def is_dike_road(name):
    return name.split("__")[0] in DIKE_ROADS


def _half(road):
    b = road.base
    return (max(b.lanes_fwd, b.lanes_bwd) * b.lane_width + b.median_width / 2.0
            + max(b.left_walk_width, b.right_walk_width))


# ------------------------------------------------------------------ the crest
_EXPO = None


def exposure(x, y):
    """The open-sea fraction within island_reshape.EXPOSURE_R of record (x, y), from the LAND grid."""
    global _EXPO
    if _EXPO is None:
        h = RS.load(RS.LAND)
        ocean = RS.open_sea(~(h > RS.LAND_Z))
        k = 16
        n = RS.N // k
        oc = ocean[:n * k, :n * k].reshape(n, k, n, k).mean(axis=(1, 3))
        _EXPO = (RS.box_mean(oc, int(RS.EXPOSURE_R / (k * RS.STEP))), k)
    f, k = _EXPO
    i = int((x - RS.X0) / (k * RS.STEP))
    j = int((-y - RS.Z0) / (k * RS.STEP))
    i, j = min(max(i, 0), f.shape[1] - 1), min(max(j, 0), f.shape[0] - 1)
    return float(f[j, i])


def crest_at(x, y):
    """The dike's crest (Godot y) at record (x, y): 12 m facing the bay, 14.7 m facing the open ocean."""
    t = float(RS.ramp(exposure(x, y), *RS.EXPOSURE_OPEN))
    return RS.DIKE_CREST_BAY + (RS.DIKE_CREST_OPEN - RS.DIKE_CREST_BAY) * t


# ------------------------------------------------------------------ the record
def dike_corridors(net):
    """[(roads, chain)]: every dike road's chain, joined across JOINTS into one ordered corridor (island_grades'
    walk), so the crest eases along the whole ring rather than per zone-split piece."""
    import island_grades as ig
    out = []
    for _name, nodes in ig.corridors(net):
        roads = {n for ps in nodes for p in ps for n, r in net.roads.items() if p.uid in r.points}
        if any(is_dike_road(n) for n in roads):
            out.append(nodes)
    return out


def raise_dike(net):
    """Every dike station at its crest (record z = crest - NET_Y), eased along the corridor at RAMP_GRADE. A corridor
    walked across joints may run on into a road that is NOT a dike road (the coast road where the ring meets the
    mountain): those stations are left to `ramps`. Returns the set of dike uids."""
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    dike = set()
    for nodes in dike_corridors(net):
        idx = [i for i, ps in enumerate(nodes) if is_dike_road(road_of[ps[0].uid])]
        if not idx:
            continue
        s = [0.0]
        for a, b in zip(nodes, nodes[1:]):
            s.append(s[-1] + math.dist(a[0].pos[:2], b[0].pos[:2]))
        want = {i: crest_at(*nodes[i][0].pos[:2]) - rg.NET_Y for i in idx}
        # ease: no station more than RAMP_GRADE x its distance off its neighbours' targets (a min-max pass each way)
        z = dict(want)
        for _ in range(2):
            order = idx + idx[::-1]
            for k in range(1, len(order)):
                i, j = order[k - 1], order[k]
                d = abs(s[i] - s[j])
                if d > 0 and abs(z[j] - z[i]) > RAMP_GRADE * d:
                    z[j] = z[i] + math.copysign(RAMP_GRADE * d, z[j] - z[i])
        for i in idx:
            for p in nodes[i]:
                p.pos = (p.pos[0], p.pos[1], round(z[i], 3))
                dike.add(p.uid)
    return dike


def _walk(net, road, start_uid):
    """The road's chain as (uid list) walked away from `start_uid` (one of its ends or any station)."""
    ch = list(net.roads[road].points)
    i = ch.index(start_uid)
    if i == len(ch) - 1 or (i != 0 and i >= len(ch) / 2):
        return ch[:i + 1][::-1]
    return ch[i:]


def _ramp_road(net, road, start_uid, jz):
    """Ramp `road` from `start_uid` (set to jz) outward at RAMP_GRADE: a forward pass, each station kept within
    RAMP_GRADE x its span of the station before it, out to REACH or the next junction (a station already within the
    grade is left alone, so an ordinary road is untouched past its ramp -- stopping at the FIRST such station left a
    steeper span behind it, 7.6 % on eki_minami_dori). Another junction's mouth ends it (set too, and reported)."""
    order = _walk(net, road, start_uid)
    P = net.points
    P[start_uid].pos = (P[start_uid].pos[0], P[start_uid].pos[1], jz)
    d, prev = 0.0, jz
    for k in range(1, len(order)):
        a, b = P[order[k - 1]], P[order[k]]
        seg = math.dist(a.pos[:2], b.pos[:2])
        d += seg
        zo = b.pos[2]
        nz = min(max(zo, prev - RAMP_GRADE * seg), prev + RAMP_GRADE * seg)
        if abs(nz - zo) >= 1e-3:
            b.pos = (b.pos[0], b.pos[1], round(nz, 3))
        prev = nz
        if str(b.role) == "INTERSECTION" or d > REACH:
            if str(b.role) == "INTERSECTION":
                print("island_dike: WARN %s ramp reaches another junction %.0f m out" % (road, d))
            break
    _level_at_crossings(net, road, order, jz)
    return d


LX_HOLD = 15.0           # a road is LEVEL at the rail's height this far either side of a 踏切 it crosses
RAMP_STEEP = 0.08        # ... and a ramp may steepen to this to get down to it (a local road's limit at 40 km/h)
_RAIL_GRADE = None


def _rail_grade_samples():
    """The reserve's corridor samples where the rail is AT GRADE (a road meeting it there crosses on a 踏切)."""
    global _RAIL_GRADE
    if _RAIL_GRADE is None:
        _RAIL_GRADE = []
        if os.path.exists(RAIL_RESERVE):
            doc = json.load(open(RAIL_RESERVE))
            _RAIL_GRADE = [(q[0], q[1], q[2]) for c in doc["corridors"] for q in c["pts"] if abs(q[2] - q[3]) < 1.0]
    return _RAIL_GRADE


def _level_at_crossings(net, road, order, jz):
    """A ramp that runs into a 踏切 does not climb ACROSS the rails: the two tracks sit 4 m apart, and a road on a
    5 % ramp puts them 0.2 m apart in height, so the road stands proud of one (probe_rail_track's gauge on
    nishi_dori__9, 2026-09-26). Every station within LX_HOLD of an at-grade rail sample is pinned to the rail's
    height, and the stations back toward the dike are brought down to it at up to RAMP_STEEP."""
    P = net.points
    rail = _rail_grade_samples()
    if not rail:
        return
    pin = {}
    for k, u in enumerate(order):
        x, y = P[u].pos[0], P[u].pos[1]
        near = [q for q in rail if abs(q[0] - x) < LX_HOLD and abs(q[1] - y) < LX_HOLD
                and math.hypot(q[0] - x, q[1] - y) < LX_HOLD]
        if near:
            pin[k] = min(near, key=lambda q: math.hypot(q[0] - x, q[1] - y))[2]
    if not pin:
        return
    for k, z in pin.items():
        a = P[order[k]]
        a.pos = (a.pos[0], a.pos[1], round(z, 3))     # island_grades holds it by the same rule
    last = max(pin)
    for k in range(last - 1, -1, -1):
        if k in pin:
            continue
        a, b = P[order[k]], P[order[k + 1]]
        cap = b.pos[2] + RAMP_STEEP * math.dist(a.pos[:2], b.pos[:2])
        if a.pos[2] > cap:
            if k == 0:
                print("island_dike: WARN %s cannot come down to its 踏切 at %.0f %% (start %.2f m over %.2f m)"
                      % (road, RAMP_STEEP * 100, a.pos[2], cap))
                break
            a.pos = (a.pos[0], a.pos[1], round(cap, 3))
    print("island_dike: %s level across its 踏切 (%d station(s) pinned to the rail)" % (road, len(pin)))


def ramps(net, dike):
    """Every road meeting a dike station -- at a junction pad or a joint -- ramped from the dike's height."""
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    P = net.points
    done, out = set(), []
    for u in sorted(dike):
        p = P[u]
        for l in p.links:
            v = l.target
            if v not in P or v in dike or v in done:
                continue
            q = P[v]
            if l.type == pm.LINK_JUNCTION:
                members = [u] + [t for t in p.targets(pm.LINK_JUNCTION) if t in dike]
                jz = sum(P[m].pos[2] for m in members) / len(members)
            elif l.type == pm.LINK_SEGMENT and road_of.get(v) != road_of.get(u) \
                    and math.dist(p.pos[:2], q.pos[:2]) < 0.5:
                jz = p.pos[2]                                   # a joint: the other road continues the dike road
            else:
                continue
            done.add(v)
            name = road_of[v]
            L = _ramp_road(net, name, v, round(jz, 3))
            out.append((name, L))
    return out


RAIL_RESERVE = os.path.join(rg.ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")
RAIL_OVER = 1.5 + 6.0     # the ring's surface over a rail head where it bridges the track: deck + a train's catenary
RAIL_GAP = 4.0            # m past the rail corridor's half width left unfilled under the ring's span


def rail_crossings(net):
    """[(x, y, rail head z, corridor half, ux, uy)]: where the rail (its RESERVE, `island_rail_layout.py --reserve`, record
    frame) crosses a dike road in plan. The rail never climbs the dike (PLAN.md 3.25 R0): the ring bridges it."""
    if not os.path.exists(RAIL_RESERVE):
        return []
    doc = json.load(open(RAIL_RESERVE))
    half = float(doc["corridor_half"])
    dsegs = [(a.pos, b.pos) for n, r in net.roads.items() if is_dike_road(n)
             for a, b in zip(net.chain(r), net.chain(r)[1:])]
    out = []
    for c in doc["corridors"]:
        for q0, q1 in zip(c["pts"], c["pts"][1:]):
            for a, b in dsegs:
                if True:
                    d1 = (q1[0] - q0[0], q1[1] - q0[1]); d2 = (b[0] - a[0], b[1] - a[1])
                    den = d1[0] * d2[1] - d1[1] * d2[0]
                    if abs(den) < 1e-9:
                        continue
                    t = ((a[0] - q0[0]) * d2[1] - (a[1] - q0[1]) * d2[0]) / den
                    u = ((a[0] - q0[0]) * d1[1] - (a[1] - q0[1]) * d1[0]) / den
                    if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
                        continue
                    hit = (q0[0] + d1[0] * t, q0[1] + d1[1] * t, q0[2] + (q1[2] - q0[2]) * t)
                    # only a track passing UNDER the ring: a viaduct over it (the Main line at the airport approach)
                    # is the rail's own clearance, checked by the rail plan
                    if hit[2] >= a[2] + (b[2] - a[2]) * u:
                        continue
                L = math.hypot(*d1) or 1.0
                out.append((hit[0], hit[1], hit[2], half, d1[0] / L, d1[1] / L))
    return out


_RAIL_NO = None


def _rail_no(x, y):
    """Is (x, y) (record) within the rail corridor at a sample the reserve marks 'no' (no street crosses there)?"""
    global _RAIL_NO
    if _RAIL_NO is None:
        _RAIL_NO = []
        if os.path.exists(RAIL_RESERVE):
            doc = json.load(open(RAIL_RESERVE))
            h = float(doc["corridor_half"]) + 2.0
            _RAIL_NO = [(q[0], q[1], h) for c in doc["corridors"] for q in c["pts"] if q[4] == "no"]
    return any(abs(x - qx) < h and abs(y - qy) < h and math.hypot(x - qx, y - qy) < h for qx, qy, h in _RAIL_NO)


def rail_lifts(net, dike):
    """Lift every dike station near a rail crossing so the ring clears the track by RAIL_OVER, eased at RAMP_GRADE
    along the road (never lowered). Returns [(x, y, crest z needed)]."""
    xs = rail_crossings(net)
    for name, r in net.roads.items():
        if not is_dike_road(name):
            continue
        for p in net.chain(r):
            want = max((z + RAIL_OVER - RAMP_GRADE * max(0.0, math.dist(p.pos[:2], (x, y)) - h - RAIL_GAP)
                        for x, y, z, h, _ux, _uy in xs), default=-1e9)
            if want > p.pos[2]:
                p.pos = (p.pos[0], p.pos[1], round(want, 3))
    return [(x, y, z + RAIL_OVER) for x, y, z, _h, _ux, _uy in xs]


MEET_SKIP = 250.0         # m of an expressway's own approach to a T on the ring: a ramp, not a crossing
OVER_CLEAR = 7.5          # an expressway deck's surface over the dike road's (roadkit_interchange.CLEARANCE 5.5 + margin)


def clear_crossings(net):
    """An expressway passing over the ring -- across it, or along the edge of a bend -- stays OVER_CLEAR above its
    crest: its deck was derived from ground sampled at its own stations, which never see the embankment between
    them. Wherever an expressway sample (every 5 m) is within both half widths + 4 m of a dike road in plan, the deck
    is lifted with a cone (rg.GRADE); it is never lowered. Returns [(road, metres lifted)]."""
    dike = {u for n, r in net.roads.items() if is_dike_road(n) for u in r.points}
    dsegs = []
    for name, r in net.roads.items():
        if name.startswith(rg.PREFIX):
            continue
        ch = net.chain(r)
        # the dike roads, and every road ramped onto them (its ramp runs up to the crest beside the ring)
        if is_dike_road(name) or any(l.target in dike for p in ch for l in p.links):
            h = _half(r)
            dsegs += [(a.pos, b.pos, h) for a, b in zip(ch, ch[1:])]
    out = []
    for name, r in net.roads.items():
        if not name.startswith(rg.PREFIX):
            continue
        ch = net.chain(r)
        he = _half(r)
        s = [0.0]
        for a, b in zip(ch, ch[1:]):
            s.append(s[-1] + math.dist(a.pos[:2], b.pos[:2]))
        # where this expressway MEETS the ring (a T onto the crest, the Wangan's west end) it is meant to come down to
        # it: that approach is the ramp's business, not a crossing
        meets = [s[i] for i, p in enumerate(ch) if any(l.target in dike for l in p.links)]
        need = []
        for k, (a, b) in enumerate(zip(ch, ch[1:])):
            L = s[k + 1] - s[k]
            for m in range(int(L // 5.0) + 1):
                t = m * 5.0 / L if L > 0 else 0.0
                x, y = a.pos[0] + (b.pos[0] - a.pos[0]) * t, a.pos[1] + (b.pos[1] - a.pos[1]) * t
                ze = a.pos[2] + (b.pos[2] - a.pos[2]) * t
                for p, q, hd in dsegs:
                    if abs(x - p[0]) > 60.0 and abs(x - q[0]) > 60.0 and (x - p[0]) * (x - q[0]) > 0:
                        continue
                    dx, dy = q[0] - p[0], q[1] - p[1]
                    u = min(max(((x - p[0]) * dx + (y - p[1]) * dy) / (dx * dx + dy * dy or 1.0), 0.0), 1.0)
                    if math.hypot(p[0] + dx * u - x, p[1] + dy * u - y) > he + hd + 4.0:
                        continue
                    zd = p[2] + (q[2] - p[2]) * u
                    sk = s[k] + L * t
                    if any(abs(sk - sm) < MEET_SKIP for sm in meets):
                        continue
                    # above the crest by too little, OR under / through it (the Wangan crossed the south-west
                    # corner at record 4.0 against a 6.4 crest: through the embankment, with no column allowed)
                    if ze - zd < OVER_CLEAR:
                        need.append((sk, zd + OVER_CLEAR))
        if not need:
            continue
        worst = 0.0
        for i, p in enumerate(ch):
            want = max(z - rg.GRADE * abs(s[i] - sn) for sn, z in need)
            if want > p.pos[2]:
                worst = max(worst, want - p.pos[2])
                p.pos = (p.pos[0], p.pos[1], round(want, 3))
        out.append((name, worst))
    return out


def write_corridor(net, dike):
    """The centrelines the street planner keeps clear of: the dike roads (record x, y, and the half width a street
    must keep off: the crest, the slope to the town, a margin) and every ramp (its embankment)."""
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    lines = []
    plain = RS.FLOOR_Z + RS.RAISE - rg.NET_Y
    for name, r in net.roads.items():
        ch = net.chain(r)
        if len(ch) < 2:
            continue
        half = _half(r)
        if is_dike_road(name):
            # [x, y, clear, crest z (record), flat half width]: the last two let `island_roadgen.Ground` stand the
            # crest in the ground an expressway clears
            pts = [[round(p.pos[0], 1), round(p.pos[1], 1),
                    round(half + SHOULDER + (p.pos[2] - plain) * LAND_SLOPE + 4.0, 1),  # the TOWN side's reach
                    round(p.pos[2], 2), round(half + RAIL_W + PARAPET, 1)] for p in ch]
            lines.append({"road": name, "kind": "dike", "pts": pts})
        else:
            raised = [p for p in ch if p.pos[2] - plain > 0.5 and not p.pillar_skip]
            if not raised or name.startswith(rg.PREFIX):
                continue
            near = any(any(t in dike for t in l2) for l2 in ([l.target for l in p.links] for p in ch))
            if not near:
                continue
            # only the RAMP: the raised stations and the one either side of each raised run (the rest of the road
            # is ordinary street a block street may cross -- the whole-road version cut the island's streets by half)
            keep = set()
            for i, p in enumerate(ch):
                if p.pos[2] - plain > 0.5 and not p.pillar_skip:
                    keep.update((max(i - 1, 0), i, min(i + 1, len(ch) - 1)))
            idx = sorted(keep)
            runs, cur = [], [idx[0]]
            for i in idx[1:]:
                if i == cur[-1] + 1:
                    cur.append(i)
                else:
                    runs.append(cur)
                    cur = [i]
            runs.append(cur)
            for run in runs:
                if len(run) < 2:
                    continue
                pts = [[round(ch[i].pos[0], 1), round(ch[i].pos[1], 1),
                        round(half + RAMP_VERGE + max(ch[i].pos[2] - plain, 0.0) * LAND_SLOPE + 4.0, 1)] for i in run]
                lines.append({"road": name, "kind": "ramp", "pts": pts})
    json.dump({"note": "tools/island_dike.py raise: record x, y, clear (m) -- island_streets keeps block streets "
                       "off these", "lines": lines}, open(CORRIDOR, "w"), indent=0)
    return len(lines)


# ------------------------------------------------------------------ the 側道
SIDE_NAME = "teibo_sokudo"   # 堤防側道: the local road along the town side of the embankment
SIDE_FOOT = 30.0             # m past the ramps' foot: where the 側道 meets every arterial at grade
SIDE_STEP = 40.0             # station spacing along it
SIDE_MIN = 120.0             # a piece between two crossings shorter than this is not built
SIDE_ANGLE = 45.0            # it only junctions a road crossing it at least this square
JOIN_GAP = 120.0             # m: two ring corridors across one junction pad


def sokudo(net, ground):
    """The 側道: a block street along the ring on the TOWN side, offset by the ramp length (the crest over the plain at
    RAMP_GRADE) + SIDE_FOOT, so it passes every arterial below its ramp, at grade. Block streets that used to T into the
    ring end on it instead. Built only over dry, low land (not the massif, not a site); each piece runs between two
    at-grade crossings and junctions them (a T on the arterial, cut with `cut_road`). Returns (pieces, junctions)."""
    from shapely.geometry import LineString, Point
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    ocean_d = None
    H = RS.load(RS.LAND)
    ocean = RS.open_sea(~(H > RS.LAND_Z))
    ocean_d = RS.distance_from(ocean, 800.0)
    ocean_d[~np.isfinite(ocean_d)] = 800.0

    def dsea(x, y):
        i = int(round((x - RS.X0) / RS.STEP))
        j = int(round((-y - RS.Z0) / RS.STEP))
        return float(ocean_d[min(max(j, 0), RS.N - 1), min(max(i, 0), RS.N - 1)])
    # every at-grade road a piece may junction: not an expressway, not the dike, level with the plain where it crosses
    targets = []
    for name, r in net.roads.items():
        if name.startswith(rg.PREFIX) or is_dike_road(name):
            continue
        ch = net.chain(r)
        for a, b in zip(ch, ch[1:]):
            targets.append((name, a.pos, b.pos))
    built, jcount, k = 0, 0, 0
    # ONE line round the ring: the corridors are cut at every junction pad, which is exactly where the arterials
    # cross, so they are chained end to end across the pads (the nearest free end within JOIN_GAP)
    runs = []
    for nodes in dike_corridors(net):
        run = [ps[0].pos for ps in nodes if is_dike_road(road_of[ps[0].uid])]
        if len(run) >= 2:
            runs.append([(q[0], q[1], q[2]) for q in run])
    lines_ = []
    while runs:
        runs.sort(key=len)
        cur = runs.pop()
        grown = True
        while grown:
            grown = False
            best = None
            for i, r in enumerate(runs):
                for rev in (False, True):
                    rr = r[::-1] if rev else r
                    for at_tail in (True, False):
                        e = cur[-1] if at_tail else cur[0]
                        f = rr[0] if at_tail else rr[-1]
                        d = math.dist(e[:2], f[:2])
                        if d < JOIN_GAP and (best is None or d < best[0]):
                            best = (d, i, rr, at_tail)
            if best:
                _d, i, rr, at_tail = best
                runs.pop(i)
                cur = cur + rr if at_tail else rr + cur
                grown = True
        lines_.append(cur)
    for pts in lines_:
        if len(pts) < 3:
            continue
        off = []
        for i, (x, y, z) in enumerate(pts):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            L = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / L, tx / L
            side = 1.0 if dsea(x + nx * 60, y + ny * 60) > dsea(x - nx * 60, y - ny * 60) else -1.0
            d = max(z, 0.0) / RAMP_GRADE + SIDE_FOOT
            off.append((x + side * nx * d, y + side * ny * d))
        # a tight concave bend loops the offset back on itself: drop every offset point whose step runs AGAINST
        # the ring's own direction there (repeatedly, as dropping one can expose the next)
        keep = list(range(len(off)))
        for _ in range(20):
            bad = set()
            for a_, b_ in zip(keep, keep[1:]):
                ox, oy = off[b_][0] - off[a_][0], off[b_][1] - off[a_][1]
                rx, ry = pts[b_][0] - pts[a_][0], pts[b_][1] - pts[a_][1]
                if ox * rx + oy * ry <= 0.3 * math.hypot(ox, oy) * math.hypot(rx, ry):
                    bad.add(b_ if b_ != keep[-1] else a_)
            if not bad:
                break
            keep = [i for i in keep if i not in bad]
        line = LineString([off[i] for i in keep]).simplify(2.0)
        if not line.is_simple or line.length < SIDE_MIN:
            continue
        # dry, low land only: cut the line where it leaves it
        cum = [0.0]
        dens = [line.interpolate(t) for t in np.arange(0.0, line.length, 5.0)] + [Point(line.coords[-1])]
        good = []
        for q in dens:
            g = ground.z(q.x, q.y)
            # and not where the rail reserve closes a street (a 踏切 too near a junction, a ramp: PLAN.md 3.25 R0)
            good.append(g is not None and -0.3 < g < 3.0 and not _rail_no(q.x, q.y))
        # crossings with the targets
        hits = []
        for name, a, b in targets:
            seg = LineString([a[:2], b[:2]])
            x = line.intersection(seg)
            if x.is_empty or x.geom_type != "Point":
                continue
            t = ((x.x - a[0]) * (b[0] - a[0]) + (x.y - a[1]) * (b[1] - a[1])) / (
                (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 or 1.0)
            zt = a[2] + (b[2] - a[2]) * t
            gt = ground.z(x.x, x.y)
            ramp = gt is None or zt - gt > 0.5              # still up on its ramp: no junction, no piece across it
            s0 = line.project(x)
            d0, d1 = line.interpolate(max(s0 - 5.0, 0)), line.interpolate(min(s0 + 5.0, line.length))
            ux, uy = d1.x - d0.x, d1.y - d0.y
            vx, vy = b[0] - a[0], b[1] - a[1]
            cosang = abs(ux * vx + uy * vy) / ((math.hypot(ux, uy) * math.hypot(vx, vy)) or 1.0)
            if math.degrees(math.acos(min(1.0, cosang))) < SIDE_ANGLE:
                ramp = True                              # too oblique for a pad: no piece across it either
            hits.append((s0, name, (x.x, x.y), ramp))
        hits.sort()
        # pieces between consecutive crossings, dry the whole way, long enough
        pieces = []
        for (s0, n0, p0, r0), (s1, n1, p1, r1) in zip(hits, hits[1:]):
            if r0 or r1 or s1 - s0 < SIDE_MIN:
                continue
            i0, i1 = int(s0 // 5.0), min(int(s1 // 5.0), len(good) - 1)
            if all(good[i0:i1 + 1]):
                pieces.append((s0, n0, p0, s1, n1, p1))
        # each crossing is cut ONCE; two pieces meeting there share its pad (a 4-way)
        cuts = {}
        for s0, n0, p0, s1, n1, p1 in pieces:
            for n_, p_ in ((n0, p0), (n1, p1)):
                key = (round(p_[0], 1), round(p_[1], 1))
                if key in cuts:
                    continue
                try:
                    cuts[key] = list(rg.cut_road(net, p_, n_.split("__")[0], rg_mouth()))
                except ValueError:
                    cuts[key] = None
        for s0, n0, p0, s1, n1, p1 in pieces:
            k0, k1 = (round(p0[0], 1), round(p0[1], 1)), (round(p1[0], 1), round(p1[1], 1))
            if cuts.get(k0) is None or cuts.get(k1) is None:
                continue
            a, b = s0 + rg_mouth(), s1 - rg_mouth()
            n = max(1, int(round((b - a) / SIDE_STEP)))
            ps = []
            for m in range(n + 1):
                q = line.interpolate(a + (b - a) * m / n)
                ps.append((q.x, q.y, max(0.0, ground.z(q.x, q.y) or 0.0)))
            k += 1
            r = rg.chain_road(net, "%s_%d" % (SIDE_NAME, k), ps, preset="block")
            cuts[k0].append(r.points[0])
            cuts[k1].append(r.points[-1])
            built += 1
        for mouths in cuts.values():
            if mouths and len(mouths) >= 3:
                rg.make_junction(net, mouths, signal=len(mouths) >= 4)
                jcount += 1
            elif mouths:                                  # cut but no piece reached it: rejoin the road
                net.link(mouths[0], mouths[1])
    return built, jcount


def rg_mouth():
    return 22.0          # island_streets.MOUTH: a mouth this far from the crossing


def cmd_raise(path):
    net = pm.load_network(path)
    dike = raise_dike(net)
    for x, y, z in rail_lifts(net, dike):
        print("island_dike: the ring bridges the rail at (%.0f, %.0f), crest to %.1f m" % (x, y, z + rg.NET_Y))
    rs = ramps(net, dike)
    for name, lift in clear_crossings(net):
        print("island_dike: %s lifted up to %.1f m to clear the dike road" % (name, lift))
    n = write_corridor(net, dike)
    pm.save_network(net, path)
    zs = [net.points[u].pos[2] + rg.NET_Y for u in dike]
    print("island_dike: %d dike station(s), crest %.1f..%.1f m; %d ramp(s) (longest %.0f m); corridor %d line(s)"
          % (len(dike), min(zs), max(zs), len(rs), max((L for _n, L in rs), default=0.0), n))
    return 0


# ------------------------------------------------------------------ the terrain
def sculpt(H, net):
    """The embankment under every dike road (asymmetric: road + shoulder to the town, road + rail + parapet to the
    sea, each with its own batter) and every ramp embankment (road + verge, 1:1.5 each side). FILL only: the terrain
    is never lowered. Returns (grid, cells the embankment raised)."""
    H = H.astype(np.float64)
    ocean = RS.open_sea(~(H > RS.LAND_Z))
    dsea = RS.distance_from(ocean, 800.0)
    dsea[~np.isfinite(dsea)] = 800.0
    out = H.copy()
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    segs = []
    dike = {u for u, n in road_of.items() if is_dike_road(n)}
    for name, r in net.roads.items():
        if name.startswith(rg.PREFIX):
            continue
        ch = net.chain(r)
        half = _half(r)
        dk = is_dike_road(name)
        if not dk:
            # a ramp: a road with a station on a dike junction/joint, only the stretch standing above the plain
            if not any(any(l.target in dike for l in p.links) for p in ch):
                continue
        for a, b in zip(ch, ch[1:]):
            if a.pillar_skip:
                continue
            segs.append((a.pos, b.pos, half, dk))
    plain = RS.FLOOR_Z + RS.RAISE
    rails = rail_crossings(net)
    for a, b, half, dk in segs:
        za, zb = a[2] + rg.NET_Y - 0.10, b[2] + rg.NET_Y - 0.10
        if not dk and max(za, zb) < plain + 0.3:
            continue
        ax, az, bx, bz = a[0], -a[1], b[0], -b[1]
        top = max(za, zb) - plain
        if dk:
            wl, ws = half + SHOULDER, half + RAIL_W + PARAPET
            reach = max(wl + top * LAND_SLOPE, ws + top * SEA_SLOPE) + 4.0
        else:
            wl = ws = half + RAMP_VERGE
            reach = wl + top * LAND_SLOPE + 4.0
        i0 = max(0, int((min(ax, bx) - reach - RS.X0) / RS.STEP))
        i1 = min(RS.N, int((max(ax, bx) + reach - RS.X0) / RS.STEP) + 2)
        j0 = max(0, int((min(az, bz) - reach - RS.Z0) / RS.STEP))
        j1 = min(RS.N, int((max(az, bz) + reach - RS.Z0) / RS.STEP) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        jj, ii = np.mgrid[j0:j1, i0:i1]
        x, z = RS.X0 + ii * RS.STEP, RS.Z0 + jj * RS.STEP
        dx, dz = bx - ax, bz - az
        l2 = dx * dx + dz * dz or 1.0
        t = np.clip(((x - ax) * dx + (z - az) * dz) / l2, 0.0, 1.0)
        px, pz = ax + dx * t, az + dz * t
        L = math.sqrt(l2)
        nx, nz = -dz / L, dx / L
        lat = (x - px) * nx + (z - pz) * nz                  # signed lateral offset
        zr = za + (zb - za) * t
        if dk:
            # which side is the sea: the side whose point 60 m out is nearer open water
            mx, mz = (ax + bx) / 2.0, (az + bz) / 2.0

            def dat(qx, qz):
                i = int(round((qx - RS.X0) / RS.STEP))
                j = int(round((qz - RS.Z0) / RS.STEP))
                return dsea[min(max(j, 0), RS.N - 1), min(max(i, 0), RS.N - 1)]
            sea_pos = dat(mx + nx * 60.0, mz + nz * 60.0) < dat(mx - nx * 60.0, mz - nz * 60.0)
            seaward = lat > 0 if sea_pos else lat < 0
            w = np.where(seaward, ws, wl)
            k = np.where(seaward, SEA_SLOPE, LAND_SLOPE)
        else:
            w, k = wl, LAND_SLOPE
        over = np.maximum(np.abs(lat) - w, 0.0)
        # the ends of a segment: past the segment's own ends the embankment falls away along the road too
        along = np.maximum(0.0, np.maximum(-((x - ax) * dx + (z - az) * dz) / L,
                                           ((x - bx) * dx + (z - bz) * dz) / L))
        target = zr - np.hypot(over / k, along / LAND_SLOPE)
        # over the sea only the crest itself is filled: beyond it the dike stands as a vertical revetment (a harbour's
        # quay wall), never a 1:2 face reclaiming the gulf 70 m out
        target = np.where((H[j0:j1, i0:i1] <= RS.LAND_Z) & ((over > 0) | (along > 0)), -np.inf, target)
        # the RAIL passes under the ring here (`rail_lifts`): no embankment over its corridor -- the ring is a bridge
        for rx, ry, _rz, rh, ux, uy in rails:
            # Godot (x, z) = record (x, -y); the track's direction likewise (ux, -uy)
            ex, ez = x - rx, z + ry
            along_r = ex * ux - ez * uy
            across_r = np.abs(ex * uy + ez * ux)
            target = np.where((across_r < rh + RAIL_GAP) & (np.abs(along_r) < 80.0), -np.inf, target)
        win = out[j0:j1, i0:i1]
        np.maximum(win, target, out=win)
    raised = out > H + 0.05
    return out.astype(np.float32), raised


def _runs(mask):
    return RS._runs(mask)


def cmd_sculpt(src, path, dst):
    net = pm.load_network(path)
    H = RS.load(src)
    g, raised = sculpt(H, net)
    d = g - H
    g.tofile(dst)
    doc = json.load(open(DIKE_JSON)) if os.path.exists(DIKE_JSON) else {}
    doc["cells"] = {"x0": RS.X0, "z0": RS.Z0, "step": RS.STEP, "runs": RS._runs(raised)}
    doc["embankment"] = "tools/island_dike.py sculpt: the ring-road dike and its ramps"
    json.dump(doc, open(DIKE_JSON, "w"), separators=(",", ":"))
    print("island_dike: sculpt raised %d cells (%.2f km2, max %.1f m) -> %s"
          % (int(raised.sum()), raised.sum() * RS.STEP * RS.STEP * 1e-6, float(d.max()), dst))
    return 0


def cmd_sokudo(path):
    net = pm.load_network(path)
    built, j = sokudo(net, rg.Ground())
    pm.save_network(net, path)
    print("island_dike: %d 側道 piece(s) along the embankment, %d junction(s)" % (built, j))
    return 0


def main(argv):
    if argv[:1] == ["sokudo"] and len(argv) == 2:
        return cmd_sokudo(argv[1])
    if argv[:1] == ["raise"] and len(argv) == 2:
        return cmd_raise(argv[1])
    if argv[:1] == ["sculpt"] and len(argv) == 4:
        return cmd_sculpt(*argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
