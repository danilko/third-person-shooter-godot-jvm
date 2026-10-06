#!/usr/bin/env python3
"""island_wiggles.py -- measure wiggles on a road record (2026-10-05): chamfered corners (a ~90 deg turn done by one
short diagonal span), S-wiggles, isolated in-road kinks, junction JOGS (a through pair of arms not on one line) and
bends at joints. Report only.

    python3 tools/island_wiggles.py assets/world_source/pieces/IslandRoads.roads.json
"""
import json, math, sys, collections
rec = sys.argv[1]
d = json.load(open(rec)); P = {p["uid"]: p for p in d["points"]}
SKIP = ("shuto_", "rail_", "shrine_touge", "kaigan_dori", "teibo")
def hd(a, b): return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
def turn(h0, h1): return (h1 - h0 + 180) % 360 - 180
out = collections.Counter(); ex = collections.defaultdict(list)
for r in d["roads"]:
    n = r["name"]
    if n.startswith(SKIP) or r.get("road_class") in ("ramp", "rail", "expressway"): continue
    pts = [P[u]["pos"][:2] for u in r["points"]]
    if len(pts) < 3: continue
    L = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    H = [hd(a, b) for a, b in zip(pts, pts[1:])]
    T = [turn(H[i], H[i+1]) for i in range(len(H)-1)]   # turn at station i+1
    for i in range(len(T)-1):
        a, b = T[i], T[i+1]
        # S-wiggle: opposite turns, both > 4 deg, the span between them short
        if a * b < 0 and abs(a) > 4 and abs(b) > 4 and L[i+1] < 80:
            out["s_wiggle"] += 1; ex["s_wiggle"].append((n, [round(v) for v in pts[i+1]], round(a), round(b), round(L[i+1])))
        # chamfer: two same-sign turns totalling 60-120 deg across one span <= 70 m
        if a * b > 0 and 60 <= abs(a + b) <= 120 and L[i+1] <= 70 and abs(a) > 20 and abs(b) > 20:
            out["chamfer"] += 1; ex["chamfer"].append((n, [round(v) for v in pts[i+1]], round(a), round(b), round(L[i+1])))
    for i, t in enumerate(T):
        if 6 < abs(t) < 25 and (i == 0 or abs(T[i-1]) < 3) and (i == len(T)-1 or abs(T[i+1]) < 3):
            out["kink"] += 1; ex["kink"].append((n, [round(v) for v in pts[i+1]], round(t)))
print(dict(out))
for k in ex: print(k, len(ex[k]), ex[k][:12])
# --- across junctions and joints ---
road_of = {}
for r in d["roads"]:
    for u in r["points"]: road_of[u] = r
def outward(u):
    r = road_of[u]; i = r["points"].index(u)
    j = i + 1 if i == 0 else i - 1
    a, b = P[u]["pos"][:2], P[r["points"][j]]["pos"][:2]
    l = math.dist(a, b) or 1.0
    return ((b[0]-a[0])/l, (b[1]-a[1])/l)
seen = set(); jogs = []; bends = []
for u, p in P.items():
    if u not in road_of: continue
    js = [l["target"] for l in p.get("links", []) if l["type"] == "JUNCTION"]
    for v in js:
        if (v, u) in seen or v not in road_of: continue
        seen.add((u, v))
        nu, nv = road_of[u]["name"], road_of[v]["name"]
        if nu.startswith(SKIP) or nv.startswith(SKIP): continue
        du, dv = outward(u), outward(v)
        if du[0]*dv[0] + du[1]*dv[1] > -0.94: continue        # not a through pair (within ~20 deg of opposite)
        a, b = P[u]["pos"][:2], P[v]["pos"][:2]
        off = abs((b[0]-a[0])*du[1] - (b[1]-a[1])*du[0])
        ang = 180 - math.degrees(math.acos(max(-1, min(1, du[0]*dv[0] + du[1]*dv[1]))))
        if off > 1.5 or ang > 6:
            jogs.append((round(off,1), round(ang,1), nu, nv, [round(x) for x in a]))
    for l in p.get("links", []):
        v = l["target"]
        if l["type"] != "SEGMENT" or v not in road_of or road_of[v] is road_of[u] or (v, u) in seen: continue
        seen.add((u, v))
        nu, nv = road_of[u]["name"], road_of[v]["name"]
        if nu.startswith(SKIP) or nv.startswith(SKIP): continue
        du, dv = outward(u), outward(v)
        ang = 180 - math.degrees(math.acos(max(-1, min(1, du[0]*dv[0] + du[1]*dv[1]))))
        if ang > 6: bends.append((round(ang,1), nu, nv, [round(x) for x in P[u]["pos"][:2]]))
jogs.sort(reverse=True); bends.sort(reverse=True)
print("junction jogs (offset m, angle deg):", len(jogs)); [print("  ", j) for j in jogs[:40]]
print("joint bends:", len(bends)); [print("  ", b) for b in bends[:20]]
