#!/usr/bin/env python3
"""island_nishi_dori_blue.py -- a ONE-SHOT edit of the arterials input (2026-10-05, PLAN.md step (c) / R-2): nishi_dori
crosses the Blue line at 65 deg instead of 34.

    python3 tools/island_nishi_dori_blue.py [<arterials record>]

nishi_dori__3 left its joint with nishi_dori__2 (record (-505, -222)) heading ENE and crossed the Blue line (y -160)
at (-361, -160) on a 34 deg diagonal -- a 踏切 the layout gate refuses (LX_MIN_ANGLE 60, island_layout.level_crossings):
a skew crossing is long, and a wheel meets the rails' flangeways at an angle. The stretch from the joint to
(-205, -28) is laid again as a chain of cubics through:
  * the crossing at (-430, -160), heading 65 deg from the line on a straight 24 m stretch (the search below maximised the smallest radius with
    the angle >= 62: ~90 m, the arterial's 50 km/h minimum is 80);
  * (-305, -90) heading 15 deg, the turn back toward the road's old line;
  * (-205, -28) on its old heading -- p_c3e3cf14 and everything after it is kept, links and all.
The joint keeps its facing; the plain stays at record z 0 (the old stations were 0.00 too).

Refuses to run twice (nishi_dori__3's second station is no longer the one this was written against).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
JOINT = "p_5abb8afd"       # nishi_dori__3's first station, the joint with nishi_dori__2 (kept)
SECOND = "p_455b5688"      # its old second station (removed)
KEEP = "p_c3e3cf14"        # (-205.3, -27.7): from here on the road is unchanged
CROSS = ((-430.0, -160.0), 65.0)
CROSS_HALF = 12.0         # a STRAIGHT stretch this far either side of the crossing: stations on its ends, so the chord IS
                          # the crossing angle (40 m AUTO chords read the first, curved version as 54 deg)
TURN = ((-320.0, -90.0), 10.0)
H_IN, H_OUT = 30.0, 45.0  # handle lengths before / after the straight (searched: smallest radius ~80 m, the 50 km/h min)
STEP = 12.0                # dense: a 40 m chord kinked the turns into the straight crossing stretch


def bezier(p0, p1, p2, p3, n=200):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def heading(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def chain(wps):
    out = []
    for (p, h, ho), (q, g, gi) in zip(wps, wps[1:]):
        d0 = (math.cos(math.radians(h)), math.sin(math.radians(h)))
        d1 = (math.cos(math.radians(g)), math.sin(math.radians(g)))
        seg = bezier(p, (p[0] + d0[0] * ho, p[1] + d0[1] * ho), (q[0] - d1[0] * gi, q[1] - d1[1] * gi), q)
        out += seg if not out else seg[1:]
    return out


def resample(poly, step):
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    n = max(1, int(round(cum[-1] / step)))
    out, j = [], 0
    for k in range(n + 1):
        s = cum[-1] * k / n
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    r = net.roads["nishi_dori__3"]
    if r.points[0] != JOINT or r.points[1] != SECOND or KEEP not in r.points:
        raise SystemExit("island_nishi_dori_blue: already applied, or nishi_dori__3 is not the road this was written "
                         "against")
    a, keep = net.points[JOINT], net.points[KEEP]
    nxt = net.points[r.points[r.points.index(KEEP) + 1]]
    A, E = (a.pos[0], a.pos[1]), (keep.pos[0], keep.pos[1])
    hA = heading(A, net.points[SECOND].pos)
    hE = heading(E, nxt.pos)
    (cx, cy), ch = CROSS
    d = (math.cos(math.radians(ch)), math.sin(math.radians(ch)))
    pa = (cx - d[0] * CROSS_HALF, cy - d[1] * CROSS_HALF)
    pb = (cx + d[0] * CROSS_HALF, cy + d[1] * CROSS_HALF)
    p1 = chain([(A, hA, H_IN), (pa, ch, H_IN)])
    p3 = chain([(pb, ch, H_OUT), (TURN[0], TURN[1], H_OUT), (E, hE, H_OUT)])
    inner = resample(p1, STEP)[1:] + resample(p3, STEP)[:-1]
    for u in r.points[1:r.points.index(KEEP)]:
        net.remove_point(u)
    before = a
    for i, (x, y) in enumerate(inner):
        p = net.add_station(r, (x, y, 0.0))
        p.ground_z, p.has_ground_z = 0.0, True
        r.points.remove(p.uid)
        r.points.insert(1 + i, p.uid)
        net.link(before.uid, p.uid)
        before = p
    net.link(before.uid, keep.uid)
    pm.save_network(net, path)
    print("island_nishi_dori_blue: nishi_dori__3 re-laid, %d new station(s), crossing the Blue line at (%.0f, %.0f) "
          "at %.0f deg -> %s" % (len(inner), CROSS[0][0], CROSS[0][1], CROSS[1], path))


if __name__ == "__main__":
    main(sys.argv[1:])
