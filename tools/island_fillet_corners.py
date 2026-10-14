#!/usr/bin/env python3
"""island_fillet_corners.py -- round the street corners a car cannot drive (PLAN.md S9 "TIGHT CORNERS").

    python3 tools/island_fillet_corners.py [--write] [--min-radius 9] [--target 14] [--record <roads.json>]

A generated block street turns a right angle through ONE record point with ~15 m legs: the solved centreline bends
at 5 m of radius, its inside lane at 2.9 m. A car swings into the oncoming lane there (census trace 2026-10-12:
opposing cars touching at koba_waku_w__x2, one into the building on the corner, a queue behind). User, 2026-10-12:
fillet them, and a building in the way may be "squashed / reduced".

For every run of every STREET (not a ramp, not the mountain road: its hairpins are a different decision) this finds
each place the solved centreline (`point_profile.centreline_runs`, the curve the mesh and the lanes are built on)
bends under --min-radius, and fixes the record there, measuring after each try and keeping the first that reaches
--target (or the best):

    1. the corner point is REMOVED and its two neighbours joined: the curve then turns across the whole of both legs;
    2. the neighbours are slid back along their own legs (to 1.5x, 2x, 3x the leg, never past the next point) so the
       turn has more room.

Only a plain interior point is touched (two SEGMENT links, no junction, no role). Without --write it prints what it
would do. With it the record is saved; then: tools/island_roads_stage.sh, and the buildings / lots on the inside of
each corner (the list is printed with the area the road now covers).
"""
import argparse
import copy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
for p in (os.path.join(ROOT, "blender", "addons", "road_kit_authoring"), os.path.join(ROOT, "blender", "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)
import point_model as pm          # noqa: E402
import point_profile as pp        # noqa: E402

RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
from island_plan import MOUNTAIN_ROADS  # noqa: E402
SKIP = ("shuto",) + MOUNTAIN_ROADS        # ramps; the mountain roads' hairpins
SKIP_HAS = ("rotary",)                 # a roundabout is meant to be a small circle


def radius(a, b, c):
    A, B, C = math.dist(a[:2], b[:2]), math.dist(b[:2], c[:2]), math.dist(a[:2], c[:2])
    s = (A + B + C) / 2.0
    ar = max(0.0, s * (s - A) * (s - B) * (s - C)) ** 0.5
    return A * B * C / (4.0 * ar) if ar > 1e-9 else 1e9


def tight_spots(net, road_name, limit):
    """[(radius, position)] -- the local minima of the solved centreline's radius under `limit` on one road."""
    out = []
    for name, pts, _uids in pp.centreline_runs(net, step=1.0, with_uids=True):
        if name != road_name or len(pts) < 5:
            continue
        rs = [1e9, 1e9] + [radius(pts[i - 2], pts[i], pts[i + 2]) for i in range(2, len(pts) - 2)] + [1e9, 1e9]
        i = 2
        while i < len(pts) - 2:
            if rs[i] < limit:
                j = i
                while j + 1 < len(pts) - 2 and rs[j + 1] < limit:
                    j += 1
                k = min(range(i, j + 1), key=lambda q: rs[q])
                out.append((rs[k], pts[k]))
                i = j + 1
            else:
                i += 1
    return out


def worst_near(net, road_name, pos, reach=45.0):
    near = [r for r, p in tight_spots(net, road_name, 1e8) if math.dist(p[:2], pos[:2]) < reach]
    best = 1e9
    for name, pts, _ in pp.centreline_runs(net, step=1.0, with_uids=True):
        if name != road_name:
            continue
        for i in range(2, len(pts) - 2):
            if math.dist(pts[i][:2], pos[:2]) < reach:
                best = min(best, radius(pts[i - 2], pts[i], pts[i + 2]))
    return min([best] + near)


def plain(net, uid):
    p = net.points[uid]
    links = list(p.links)
    return len(links) == 2 and all(l.type == pm.LINK_SEGMENT for l in links) and getattr(p, "role", "SEGMENT") in ("", "SEGMENT")


def slide(net, uid, toward_uid, limit_uid, factor, corner):
    """Moves `uid` along its leg away from the corner to `factor` x its distance from it, stopping 6 m short of
    `limit_uid` (the next point on that side)."""
    p, lim = net.points[uid], net.points[limit_uid]
    d = [p.pos[k] - corner[k] for k in range(3)]
    leg = math.hypot(d[0], d[1])
    room = math.dist(p.pos[:2], lim.pos[:2]) - 6.0
    extra = min(leg * (factor - 1.0), max(0.0, room))
    if leg < 1e-6 or extra <= 0.0:
        return
    u = (lim.pos[0] - p.pos[0], lim.pos[1] - p.pos[1])
    ul = math.hypot(*u) or 1.0
    p.pos = (p.pos[0] + u[0] / ul * extra, p.pos[1] + u[1] / ul * extra, p.pos[2])


def face_legs(net, a0, a, b, b0):
    """The corner's two remaining points faced down their OWN legs (MANUAL): `a` along a0 -> a, `b` along b -> b0
    (PLAN S13 D4). Left AUTO, each was faced on the chord of its neighbours, which leans into the corner, and the kit's
    curve then bent 3-8 deg the WRONG way on each leg before turning the corner (an S at every rounded corner)."""
    for u, p0, p1 in ((a, a0, a), (b, b, b0)):
        q0, q1 = net.points[p0].pos, net.points[p1].pos
        d = (q1[0] - q0[0], q1[1] - q0[1])
        L = math.hypot(*d)
        if L > 1e-6:
            net.points[u].tangent_mode = pm.MANUAL
            net.points[u].tangent = (d[0] / L, d[1] / L, 0.0)


def fix(net, road, corner_uid, target):
    """Tries the fixes on a copy; returns (network to keep, radius reached, what was done) or None."""
    uids = road.points
    i = uids.index(corner_uid)
    if i < 2 or i > len(uids) - 3 or not all(plain(net, u) for u in uids[i - 1:i + 2]):
        return None
    corner = tuple(net.points[corner_uid].pos)
    best = None
    for factor in (1.0, 1.5, 2.0, 3.0):
        trial = copy.deepcopy(net)
        a, b = uids[i - 1], uids[i + 1]
        trial.remove_point(corner_uid)
        trial.link(a, b, pm.LINK_SEGMENT)
        if factor > 1.0:
            slide(trial, a, corner_uid, uids[i - 2], factor, corner)
            slide(trial, b, corner_uid, uids[i + 2], factor, corner)
        face_legs(trial, uids[i - 2], a, b, uids[i + 2])
        r = worst_near(trial, road.name, corner)
        what = "corner point removed" + ("" if factor == 1.0 else ", neighbours slid back x%.1f" % factor)
        if best is None or r > best[1]:
            best = (trial, r, what)
        if r >= target:
            break
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default=RECORD)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--min-radius", type=float, default=9.0, help="a centreline bend under this is fixed (m)")
    ap.add_argument("--target", type=float, default=14.0, help="what a fix aims for (m)")
    a = ap.parse_args()
    net = pm.load_network(a.record)
    done = left = 0
    for name in sorted(net.roads):
        if name.startswith(SKIP) or any(k in name for k in SKIP_HAS):
            continue
        guard = 0
        while guard < 6:
            guard += 1
            spots = tight_spots(net, name, a.min_radius)
            if not spots:
                break
            road = net.roads[name]
            progressed = False
            for r0, pos in spots:
                cands = [u for u in road.points if u in net.points and math.dist(net.points[u].pos[:2], pos[:2]) < 12.0]
                cands.sort(key=lambda u: math.dist(net.points[u].pos[:2], pos[:2]))
                got = None
                for u in cands[:1]:
                    got = fix(net, road, u, a.target)
                if got is None or got[1] <= r0 + 0.5:
                    print("LEFT  %-30s %5.1f m at record (%.0f, %.0f): %s" % (
                        name, r0, pos[0], pos[1], "no plain interior point there" if got is None else
                        "best try reached only %.1f m" % got[1]))
                    left += 1
                    continue
                net, r1, what = got
                print("FIXED %-30s %5.1f -> %5.1f m at record (%.0f, %.0f) = Godot (%.0f, %.0f): %s" % (
                    name, r0, r1, pos[0], pos[1], pos[0], -pos[1], what))
                done += 1
                progressed = True
                break            # the network changed: measure this road again
            if not progressed:
                break
    print("%d corner(s) fixed, %d left%s" % (done, left, "" if a.write else " (dry run: --write saves the record)"))
    if a.write and done:
        pm.save_network(net, a.record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
