#!/usr/bin/env python3
"""check_street_trees.py -- no street tree stands on a lane, and none stands where the rule forbids one
(PLAN.md 3.16 step 4).

`point_furniture._street_trees` derives where a 街路樹 goes from the footway's own width and the kerb; a checker
that re-derived the same thing would test nothing (the W8 lesson). So this measures the RESULT against facts from
the other side of the pipeline -- the EXPORTED LANES (`point_export`, the same `Curve3D`s a car drives) and the
record's authored cross-section:

  * no tree is within half a lane's width of any lane centreline, plus the trunk's own radius: a tree in a lane
    is the one failure a driver meets at speed, and the lanes are not what the placer read;
  * every tree's road authors a footway at least `tree_min_footway` wide;
  * and a tree is street furniture, not a tree dropped in a field: it stands no further from the nearest lane
    than that lane's half width plus the road's footway plus `OUTBOARD_SLACK`.

    python3 blender/tools/check_street_trees.py <record.roads.json> --lanekits <dir> [--ground g.json] [--control]

`--control` puts the kerb gap INSIDE the kerb AND turns the placer's own lane guard off, so the trees really do
land in lanes; it must fail the first check -- a gate that has never been seen to fire is not a gate.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "lib"), os.path.join(ROOT, "addons", "road_kit_authoring")):
    sys.path.insert(0, p)

import point_model as pm          # noqa: E402
import point_edges as ped         # noqa: E402
import point_ground as pg         # noqa: E402
import point_furniture as pfu     # noqa: E402

TRUNK_R = 0.35          # the trunk's own half width (furniture.json `collide_pole`)
OUTBOARD_SLACK = 2.5    # a footway's outer edge, plus the kerb gap and the run's own resampling
DEFAULT_LANE_W = 4.5


def road_walk(net, owner):
    r = net.roads.get(str(owner))
    if r is None:
        return 0.0
    b = r.base
    return max(float(getattr(b, "left_walk_width", 0.0) or 0.0), float(getattr(b, "right_walk_width", 0.0) or 0.0))


def _seg_dist(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    n = vx * vx + vy * vy
    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / n))
    return math.hypot(p[0] - (a[0] + vx * t), p[1] - (a[1] + vy * t))


def load_lanes(directory, prefix=""):
    """[(plan points, half width)] over this network's lanekits in the directory, in the KIT frame."""
    out = []
    for f in sorted(os.listdir(directory)):
        if not f.endswith(".lanekit.json") or not f.startswith(prefix):
            continue
        with open(os.path.join(directory, f)) as fh:
            doc = json.load(fh)
        for lane in doc.get("lanes", ()):
            pts = [pfu.godot_to_kit(p) for p in lane.get("points", ())]
            if len(pts) >= 2:
                out.append(([(p[0], p[1]) for p in pts], 0.5 * float(lane.get("lane_width", DEFAULT_LANE_W))))
    return out


def nearest_lane(lanes, p):
    """(distance, that lane's half width) to the nearest lane centreline."""
    best = (1e18, 0.0)
    for pts, half in lanes:
        for a, b in zip(pts, pts[1:]):
            d = _seg_dist(p, a, b)
            if d < best[0]:
                best = (d, half)
    return best


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--lanekits", required=True)
    ap.add_argument("--prefix", default="",
                    help="only lanekits named <prefix>*: every network's sidecars share one folder, "
                         "and another world's lanes overlap these coordinates")
    ap.add_argument("--ground")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args(argv)

    net = pm.load_network(a.record)
    grid = pg.load_ground(a.ground) if a.ground else None
    table = pfu.load()
    if a.control:
        # the kerb gap INSIDE the kerb, and the placer's own lane guard off, so trees really do land in lanes
        table.rules = dict(table.rules, tree_kerb_gap=-2.5, tree_lane_clear=-99.0)
    solved = ped.solve_all(net, grid)
    lanes_doc = {"lanes": [], "junctions": []}
    for f in sorted(os.listdir(a.lanekits)):
        if f.endswith(".lanekit.json") and f.startswith(a.prefix):
            with open(os.path.join(a.lanekits, f)) as fh:
                d = json.load(fh)
            lanes_doc["lanes"] += d.get("lanes", [])
            lanes_doc["junctions"] += d.get("junctions", [])
    fur = pfu.place(table, solved, lanes_doc, lambda l: True, lambda s: True, lambda j: True,
                    lambda l: "M_LineW", grid)
    names = set(table.rules.get("tree_assets", ()))
    trees = [p for p in fur.placements if p["asset"] in names]
    stem = os.path.basename(a.record)
    if not trees:
        print("check_street_trees: %s -- no footway wide enough for a street tree (0 placed)" % stem)
        return 0
    lanes = load_lanes(a.lanekits, a.prefix)
    if not lanes:
        print("check_street_trees: %s -- FAIL, no lanekit in %s" % (stem, a.lanekits))
        return 1
    on_lane, narrow, adrift = 0, 0, 0
    worst_in, worst_out, thinnest = 0.0, 0.0, 1e9
    for t in trees:
        d, half = nearest_lane(lanes, t["pos"])
        walk = road_walk(net, t.get("road", ""))
        if d < half + TRUNK_R:
            on_lane += 1
            worst_in = max(worst_in, half + TRUNK_R - d)
        if d > half + walk + OUTBOARD_SLACK:
            adrift += 1
            worst_out = max(worst_out, d - (half + walk + OUTBOARD_SLACK))
        if walk + 1e-6 < table.rules["tree_min_footway"]:
            narrow += 1
            thinnest = min(thinnest, walk)
    ok = on_lane == 0 and narrow == 0 and adrift == 0
    print("check_street_trees: %s -- %d trees; in a lane %d (worst %.2f m in), adrift of the footway %d "
          "(worst %.2f m out), on a footway under %.1f m %d%s -- %s"
          % (stem, len(trees), on_lane, worst_in, adrift, worst_out, table.rules["tree_min_footway"], narrow,
             "" if thinnest > 1e8 else " (thinnest %.2f m)" % thinnest, "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
