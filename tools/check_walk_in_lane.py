#!/usr/bin/env python3
"""check_walk_in_lane.py -- no footway triangle stands in a lane's driving band (the lane centre +- a car's half
width): the "pavement poking into the middle of the road" (user, 2026-09-26, postal 9-14). probe_road_clear cannot see
it -- a 0.15 m kerb is below its 0.30 m obstruction band.

    python3 tools/check_walk_in_lane.py [<record>]       # exit 1 on any lane with footway in it

Builds the draft footway (`roadkit_cli bands`) and the lane export (`roadkit_cli lanekit`) of the record itself, so it
judges the record, not whatever pieces were last built.
"""
import json, math, os, subprocess, sys, collections, tempfile
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CLI = os.path.join(ROOT, "blender", "tools", "roadkit_cli.py")
rec = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
CAR_HALF = 1.1
bands = json.loads(subprocess.run([sys.executable, CLI, "bands", rec], capture_output=True, text=True, check=True).stdout)
with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, CLI, "lanekit", rec, os.path.join(d, "l.json")], capture_output=True, check=True)
    lk = json.load(open(os.path.join(d, "l.json")))
w = bands["walk"]
tris = [w[i:i + 9] for i in range(0, len(w), 9)]
grid = collections.defaultdict(list)
for k, t in enumerate(tris):
    xs, zs = t[0::3], t[2::3]
    for gx in range(int(min(xs) // 8), int(max(xs) // 8) + 1):
        for gz in range(int(min(zs) // 8), int(max(zs) // 8) + 1):
            grid[(gx, gz)].append(k)

def inside(t, x, z):
    (ax, ay, az, bx, by, bz, cx, cy, cz) = t
    d1 = (x - bx) * (az - bz) - (ax - bx) * (z - bz)
    d2 = (x - cx) * (bz - cz) - (bx - cx) * (z - cz)
    d3 = (x - ax) * (cz - az) - (cx - ax) * (z - az)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos), (ay + by + cy) / 3.0
hits = collections.defaultdict(list)
for lane in lk["lanes"]:
    P = lane["points"]
    for a, b in zip(P, P[1:]):
        L = math.dist((a[0], a[2]), (b[0], b[2]))
        if L < 1e-6:
            continue
        ux, uz = (b[0] - a[0]) / L, (b[2] - a[2]) / L
        n = int(L // 1.0) + 1
        for m in range(n + 1):
            f = min(m * 1.0 / L, 1.0)
            x, y, z = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
            for off in (-CAR_HALF, 0.0, CAR_HALF):
                px, pz = x - uz * off, z + ux * off
                for k in grid.get((int(px // 8), int(pz // 8)), ()):
                    ok, ty = inside(tris[k], px, pz)
                    if ok and abs(ty - y) < 1.0:
                        hits[lane["id"]].append((round(px, 1), round(pz, 1)))
                        break
print("check_walk_in_lane: %d lane(s) with footway in their driving band" % len(hits))
for lid, ps in sorted(hits.items(), key=lambda kv: -len(kv[1]))[:40]:
    print("  %-60s %3d samples, e.g. godot (%.0f, %.0f)" % (lid, len(ps), ps[0][0], ps[0][1]))
print("check_walk_in_lane: %s" % ("PASS" if not hits else "FAIL"))
sys.exit(1 if hits else 0)
