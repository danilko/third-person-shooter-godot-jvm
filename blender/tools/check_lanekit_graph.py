#!/usr/bin/env python3
"""
check_lanekit_graph.py -- validate a graph-exported `.lanekit.json` the way Godot will read it.

`python3 blender/tools/check_lanekit_graph.py assets/world_source/island_v3_roads.lanekit.json`

WHAT IT CHECKS, and why each one is the difference between "the file exists" and "cars drive":

  1. GEOMETRY IS WELL FORMED -- every lane has >= 2 points, no zero-length or NaN segments.
     `WorldBaker.buildPathLaneRoute` silently skips a malformed entry, so a broken lane is an
     invisible hole in the network rather than an error.
  2. CONNECTORS ACTUALLY MEET THEIR LANES. A connector's first point must coincide with the
     arriving lane's last point, and its last with the departing lane's first, within
     `LaneGraph.JUNCTION_RADIUS` (4.5 m). This is the ONE thing that makes the network traversable
     at runtime: chains are trimmed back from their junctions, so without connectors that close
     the gap exactly, every car reaches a stop line and finds no successor.
  3. REACHABILITY -- how many lanes have a successor at all, and how many are dead ends. A
     terminus legitimately has none; a through lane with none is a car sink.
  4. HEADING CONTINUITY -- the turn between a lane and its connector must not reverse (a dot
     product below zero means the connector leaves backwards, which reads as a car spinning on
     the spot).
"""
import json
import math
import sys

JUNCTION_RADIUS = 4.5     # keep in sync with LaneGraph.JUNCTION_RADIUS (Java)


def _d(a, b):
    return math.dist(a, b)


def _tan(pts, at_start):
    a, b = (pts[0], pts[1]) if at_start else (pts[-2], pts[-1])
    v = [b[i] - a[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def check(path):
    with open(path) as fh:
        data = json.load(fh)
    lanes = {l["id"]: l for l in data.get("lanes", [])}
    conns = {k: v for k, v in lanes.items() if v.get("kind") == "connector"}
    through = {k: v for k, v in lanes.items() if v.get("kind") != "connector"}
    problems = []

    # ---- 1. well-formed geometry
    for lid, l in lanes.items():
        pts = l.get("points") or []
        if len(pts) < 2:
            problems.append("%s: only %d point(s)" % (lid, len(pts)))
            continue
        if any(any(math.isnan(c) or math.isinf(c) for c in p) for p in pts):
            problems.append("%s: non-finite coordinate" % lid)
        if sum(_d(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) < 1e-4:
            problems.append("%s: zero length" % lid)

    # ---- 2. connectors meet the lanes they claim to join
    gaps = []
    for cid, c in conns.items():
        src = cid.split("__")[0].split("_", 1)[1] if "__" in cid else None
        dst = (c.get("next") or [None])[0]
        if src in lanes:
            g = _d(lanes[src]["points"][-1], c["points"][0])
            gaps.append(g)
            if g > JUNCTION_RADIUS:
                problems.append("%s: %.2f m gap from its source lane %s" % (cid, g, src))
        if dst in lanes:
            g = _d(c["points"][-1], lanes[dst]["points"][0])
            gaps.append(g)
            if g > JUNCTION_RADIUS:
                problems.append("%s: %.2f m gap to its target lane %s" % (cid, g, dst))

    # ---- 3. reachability
    dead = [lid for lid, l in through.items() if not l.get("next")]

    # ---- 4. heading continuity through a connector
    reversed_n = 0
    for cid, c in conns.items():
        src = cid.split("__")[0].split("_", 1)[1] if "__" in cid else None
        if src not in lanes:
            continue
        t_in, t_c = _tan(lanes[src]["points"], False), _tan(c["points"], True)
        if sum(t_in[i] * t_c[i] for i in range(3)) < 0.0:
            reversed_n += 1
            problems.append("%s: leaves its source lane backwards" % cid)

    print("lanes:      %d through, %d connectors" % (len(through), len(conns)))
    print("junction gaps: max %.3f m, mean %.3f m (tolerance %.1f m)"
          % (max(gaps) if gaps else 0.0,
             (sum(gaps) / len(gaps)) if gaps else 0.0, JUNCTION_RADIUS))
    print("dead ends:  %d of %d through lanes (%.0f%%) have no successor"
          % (len(dead), len(through), 100.0 * len(dead) / max(len(through), 1)))
    print("reversed:   %d connector(s) leave their source backwards" % reversed_n)
    if problems:
        print("\nPROBLEMS (%d, first 15):" % len(problems))
        for p in problems[:15]:
            print("  " + p)
        return 1
    print("\nOK -- every connector meets its lanes and no geometry is malformed.")
    return 0


if __name__ == "__main__":
    sys.exit(check(sys.argv[1]))
