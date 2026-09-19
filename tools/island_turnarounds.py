#!/usr/bin/env python3
"""island_turnarounds.py -- every road end is a turnaround (PLAN.md 3.3b).

    python3 tools/island_turnarounds.py <record> [--check]

A dead end is where a car stops being traffic: the ambient brain finishes its lane and `ZoneManager` reclaims it as
route-finished. So every road end that joins nothing (a station at a chain end with one SEGMENT link and no JUNCTION or
AUX link, i.e. not a joint, not a mouth) gets the summit's treatment (`island_shrine_touge.summit_loop`), generalised
here: the end station becomes a junction MOUTH, and a TEARDROP loop road (`<road>_loop`, one lane each way, the stem's
lane width) leaves and rejoins a 3-arm junction `LOOP_GAP` past it. Its two arms leave `ARM_DEG` either side of an
axis, and the axis and the loop's reach are SEARCHED (`AXIS_MAX` either side of straight on, `REACHES`) for the
candidate that stays on land, keeps `CLEAR` from every other road's centreline and sits flattest. An end with no
candidate is reported, not forced. `roadkit_cli.py setback` then solves the mouths (the island pipeline in PLAN.md).

A facility at an end (the airport terminal, the container wharf) is a short stub off its loop, built with the
facility itself (3.6); a plain end gets only the loop. Idempotent: a road end that already has a loop is not an end.
`--check` exits 1 if any end is left.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from island_roadgen import *    # noqa: E402,F401,F403
import point_model as pm        # noqa: E402

LOOP_GAP = 30.0                   # the junction centre this far past the stem's end; the loop's arms leave it this far out
ARM_DEG = 35.0                    # the loop's arms, either side of its axis
AXIS_MAX = 150                    # the axis may turn this far either side of straight on
REACHES = (55.0, 70.0, 90.0, 110.0)   # the loop's far corners this far out along its axis
FLAT = 3.0                        # the ground under a loop stays within this of the end's own height
CORNER_R = 40.0                   # the loop's two far corners
CLEAR = 30.0                      # a loop keeps this far from any other road's centreline
SHORE = 13.0                      # ... and this far from the water: its paved half + the stamp's 6 m verge
LAND_MIN = -0.3                   # ... and stays on ground at least this high (not over the sea)


def open_ends(net):
    """[(uid, road name, unit direction OUT of the road)] for every end station that joins nothing."""
    out = []
    for name, r in net.roads.items():
        if len(r.points) < 2:
            continue
        for end, nxt in ((r.points[0], r.points[1]), (r.points[-1], r.points[-2])):
            p = net.points[end]
            links = p.links
            if len(links) != 1 or links[0].type != pm.LINK_SEGMENT or p.role != pm.SEGMENT:
                continue
            q = net.points[nxt].pos
            dx, dy = p.pos[0] - q[0], p.pos[1] - q[1]
            L = math.hypot(dx, dy)
            out.append((end, name, (dx / L, dy / L)))
    return out


def _rot(u, deg):
    a = math.radians(deg)
    return (u[0] * math.cos(a) - u[1] * math.sin(a), u[0] * math.sin(a) + u[1] * math.cos(a))


def loop_line(end_xy, u, axis, reach):
    J = (end_xy[0] + u[0] * LOOP_GAP, end_xy[1] + u[1] * LOOP_GAP)
    ua = _rot(u, axis)
    a_l, a_r = _rot(ua, ARM_DEG), _rot(ua, -ARM_DEG)
    H = (J[0] + a_l[0] * LOOP_GAP, J[1] + a_l[1] * LOOP_GAP)
    T = (J[0] + a_r[0] * LOOP_GAP, J[1] + a_r[1] * LOOP_GAP)
    far = reach / math.cos(math.radians(ARM_DEG))
    A = (J[0] + a_l[0] * far, J[1] + a_l[1] * far)
    B = (J[0] + a_r[0] * far, J[1] + a_r[1] * far)
    return rounded_polygon([H, A, B, T], CORNER_R, closed=False), J


def best_loop(net, ground, end, stem_name, u, others):
    p = net.points[end].pos
    best = None
    for axis in range(-AXIS_MAX, AXIS_MAX + 1, 5):
        for reach in REACHES:
            line, J = loop_line(p, u, axis, reach)
            probe = densify([J] + line, 4.0)
            gz = [ground.z(x, y) for x, y in probe]
            if any(g is None or g < LAND_MIN for g in gz):
                continue
            # the band and the stamp's flat verge must be on land too, or the stamp fills the sea under them (measured:
            # futo_dori_loop, 175 harbour cells raised up to 28 m, its centreline on the quay and its verge over it)
            if any((ground.z(x + SHORE * math.cos(a), y + SHORE * math.sin(a)) or -1e9) < LAND_MIN
                   for x, y in probe[::2] for a in (0.0, 1.571, 3.1416, 4.712, 0.785, 2.356, 3.927, 5.498)):
                continue
            near = min((math.hypot(x - ox, y - oy) for x, y in probe for (on, ox, oy) in others
                        if abs(x - ox) < CLEAR and abs(y - oy) < CLEAR), default=1e9)
            if near < CLEAR:
                continue
            flat = max(abs(g - p[2]) for g in gz)
            if flat > FLAT:
                continue
            score = flat + abs(axis) * 0.01
            if best is None or score < best[0]:
                best = (score, axis, reach, line, flat)
    return best


def build(net, ground):
    ends = open_ends(net)
    done, failed = [], []
    for end, name, u in ends:
        others = []
        for n2, r2 in net.roads.items():
            if n2 == name:
                continue
            for x, y in densify([net.points[v].pos[:2] for v in r2.points], 8.0):
                others.append((n2, x, y))
        best = best_loop(net, ground, end, name, u, others)
        trimmed = 0
        # no room at the very end (a road run out onto a strip between a slope and the sea): shorten the road a
        # station at a time until a loop fits, never below two stations
        stem = net.roads[name]
        while best is None and len(stem.points) > 2 and trimmed < 3:
            at_head = stem.points[0] == end
            net.remove_point(end)
            trimmed += 1
            end = stem.points[0] if at_head else stem.points[-1]
            nxt = stem.points[1] if at_head else stem.points[-2]
            a, b = net.points[end].pos, net.points[nxt].pos
            L = math.hypot(a[0] - b[0], a[1] - b[1])
            u = ((a[0] - b[0]) / L, (a[1] - b[1]) / L)
            best = best_loop(net, ground, end, name, u, others)
        if best is None:
            failed.append(name)
            continue
        if trimmed:
            print("island_turnarounds: %s shortened by %d station(s) to fit its loop" % (name, trimmed))
        _s, axis, reach, line, flat = best
        loop_name = name.split("__")[0] + "_loop"
        k = 2
        while loop_name in net.roads:
            loop_name = "%s_loop%d" % (name.split("__")[0], k)
            k += 1
        pts = [(x, y, round(max(ground.z(x, y) or 0.0, 0.0) if net.points[end].pos[2] < 1.0
                            else net.points[end].pos[2], 3)) for x, y in line]
        r = chain_road(net, loop_name, pts, preset=None)
        r.road_class = stem.road_class
        r.base = stem.base.copy()
        r.base.lanes_fwd = r.base.lanes_bwd = 1
        r.base.median_width = 0.0
        for v in r.points:
            net.points[v].lanes_fwd, net.points[v].lanes_bwd = 1, 1
        make_junction(net, [end, r.points[0], r.points[-1]], signal=False)
        done.append((name, loop_name, axis, reach, flat))
    return done, failed


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    ground = Ground()
    if "--check" in argv:
        ends = open_ends(net)
        for end, name, _u in ends:
            print("island_turnarounds: %s ends at %s with no turnaround" % (name, end))
        sys.exit(1 if ends else 0)
    done, failed = build(net, ground)
    sample_ground(net, ground, prefix="\0")
    pm.save_network(net, path)
    for name, loop, axis, reach, flat in done:
        print("island_turnarounds: %-28s -> %-22s axis %+3d deg, reach %3.0f m, ground within %.1f m"
              % (name, loop, axis, reach, flat))
    for name in failed:
        print("island_turnarounds: %s -- NO loop fits (sea, or another road within %.0f m); left as an end" % (name, CLEAR))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
