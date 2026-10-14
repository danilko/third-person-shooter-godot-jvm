#!/usr/bin/env python3
"""island_market_corner.py -- a ONE-SHOT edit of the arterials input (PLAN S11 P12-4, 2026-10-13): the coast (dike) road
`ring_kita__9`'s corner west of the fish market becomes ONE EVEN ARC.

    python3 tools/island_market_corner.py [<arterials record>] [--dry]

The corner was three chords -- stations at Godot (325.2, 672) (275.8, 687.5) (239.3, 721.9), turning 17, 26 and 45 deg:
a bend that tightens as it goes, which the user marked on the map ("roads straight + clean curves, no wiggle"). It is
now one arc of R tangent to the z 672 straight and to the north-south leg through (239.3, 721.9)-(235.7, 839.7), both
legs UNSHIFTED (moving the leg west puts the dike's land toe on Industry station's box: 9 m clear at 0, 0 at 10 m).
R 60: the planner's first choice (a 40 km/h corner on a 2+2; R 45 would be signed 30), and the largest that leaves the
car-park T at x 375 (island_site_access `ichiba_chushajo`) a straight approach past the arc's end at x 299. The arc
lies INSIDE the old chords (nearer the corner), on the crest that is already there: it needs no new land.

Five stations on the arc (start, 1/4, 1/2, 3/4, end), each faced on the arc's own tangent (MANUAL), so the kit sweeps
the circle and `island_fillet_corners.py` finds nothing to round. Refuses to run twice (no station left at (275.8, 687.5)).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
sys.path.insert(0, HERE)
import point_model as pm        # noqa: E402
import island_roadgen as rg     # noqa: E402

INPUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
ROAD = "ring_kita__9"
RADIUS = 60.0
OLD = ((325.2, -672.0), (275.8, -687.5), (239.3, -721.9))     # record (x, y) of the three chord stations
LEG = ((239.3, -721.9), (235.7, -839.7))                       # the north-south leg's line (two of its stations)
STRAIGHT_Y = -672.0


def arc():
    """[(x, y, tx, ty)] x 5: the arc's stations and unit tangents, in the chain's order (east -> south)."""
    (ax, ay), (bx, by) = LEG
    ux, uy = bx - ax, by - ay
    L = math.hypot(ux, uy)
    ux, uy = ux / L, uy / L                          # along the leg, southward
    t = (STRAIGHT_Y - ay) / uy
    pi = (ax + ux * t, STRAIGHT_Y)                   # the two tangents' corner
    t0 = (-1.0, 0.0)                                 # the chain runs WEST along the straight into the corner
    phi = math.acos(max(-1.0, min(1.0, t0[0] * ux + t0[1] * uy)))
    T = RADIUS * math.tan(phi / 2.0)
    s = (pi[0] - t0[0] * T, pi[1] - t0[1] * T)       # arc start, on the straight
    side = 1.0 if t0[0] * uy - t0[1] * ux > 0 else -1.0
    c = (s[0] - t0[1] * side * RADIUS, s[1] + t0[0] * side * RADIUS)
    out = []
    for k in range(5):
        a = side * phi * k / 4.0
        ca, sa = math.cos(a), math.sin(a)
        rx, ry = s[0] - c[0], s[1] - c[1]
        out.append((c[0] + rx * ca - ry * sa, c[1] + rx * sa + ry * ca, t0[0] * ca - t0[1] * sa, t0[0] * sa + t0[1] * ca))
    return out, pi, math.degrees(phi)


def side_line(run):
    """The dike road's line as `island_dike.sokudo` should OFFSET it: the arc's five stations put back on the three old
    chord points. The 側道 (teibo_sokudo) is the ring's line offset ~158 m to the town side, and the streets and blocks
    behind this corner end on it: offset from the arc it moved up to 40 m (a core street lost its T, 58 m away), for a
    change that is about the corner's own kerb line. `run` = [(x, y, z)] in chain order; returned likewise."""
    pts = arc()[0]
    idx = [next((i for i, q in enumerate(run) if math.dist(q[:2], p[:2]) < 0.5), None) for p in pts]
    if None in idx:
        return run
    lo, hi = min(idx), max(idx)
    old = [(x, y, run[lo][2]) for x, y in (OLD if idx[0] < idx[-1] else OLD[::-1])]
    return run[:lo] + old + run[hi + 1:]


def main(argv):
    path = next((a for a in argv if not a.startswith("--")), INPUT)
    net = pm.load_network(path)
    road = net.roads[ROAD]

    def at(xy):
        return next((u for u in road.points if math.dist(net.points[u].pos[:2], xy) < 1.0), None)
    us = [at(xy) for xy in OLD]
    if None in us:
        raise SystemExit("island_market_corner: already applied (no %s station at one of %s)" % (ROAD, OLD))
    pts, pi, phi = arc()
    z = net.points[us[0]].pos[2]
    # the three old stations become the arc's start, middle and end; the quarter points are inserted between them
    for u, k in zip(us, (0, 2, 4)):
        net.points[u].pos = (pts[k][0], pts[k][1], z)
    q1 = rg.insert_after(net, road, us[0], (pts[1][0], pts[1][1], z))
    q3 = rg.insert_after(net, road, us[1], (pts[3][0], pts[3][1], z))
    for u, k in zip((us[0], q1, us[1], q3, us[2]), range(5)):
        p = net.points[u]
        p.tangent_mode = pm.MANUAL
        p.tangent = (pts[k][2], pts[k][3], 0.0)
    print("island_market_corner: %s corner = one arc R %.0f, %.1f deg about (%.1f, %.1f): %s"
          % (ROAD, RADIUS, phi, pi[0], -pi[1], " ".join("(%.1f, %.1f)" % (q[0], -q[1]) for q in pts)))
    if "--dry" not in argv:
        pm.save_network(net, path)
        print("island_market_corner: -> %s" % path)


if __name__ == "__main__":
    main(sys.argv[1:])
