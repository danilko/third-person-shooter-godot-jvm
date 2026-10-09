"""Can every door of every ENTERABLE building be used? (user 2026-10-07: "the konbini store is rarely enterable ...
there should always be room for an emergency exit"). Two measurements over IslandBuildings.json, no Godot:

    python3 tools/island_door_access.py

1. APRON: a door-wide, 1.5 m deep area outside each door free of any neighbour's plinth.
2. REACH: each side/back door reachable on foot (0.5 m grid, a 0.4 m body) from the front door, outside, round the
   neighbours, in a 70 m window. A compound's own yard counts as walkable; car parks and parks are walkable.

2026-10-07: 7 of 345 doors blocked within 1.5 m, 7 of 269 side/back doors unreachable (KonbiniS back x2, KonbiniL
left x1, Koban x2, DepartmentStore x2). Doors and footprints come from layout_buildings.layout_all and the plinths
island_buildings derives, so the check reads the same facts the placement wrote.
"""
import sys, json, math, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "tools", "building_kit"))
import island_buildings as IB, layout_buildings as LB
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from collections import Counter, defaultdict
doc = json.load(open("assets/world_source/buildings/IslandBuildings.json"))
B = doc["buildings"]
lay = {b["id"]: b for b in LB.layout_all("assets/world_source/buildings/building_types.json")["buildings"]}
polys = []
for b in B:
    try: polys.append(IB._plinth_poly(b))
    except Exception as e: polys.append(None)
idx = [i for i, p in enumerate(polys) if p is not None]
tree = STRtree([polys[i] for i in idx])
DEPTH = 1.5
bad = Counter(); total = Counter(); worst = defaultdict(list)
for i, b in enumerate(B):
    sc = IB.scene_of(b)
    if not (sc.endswith("_Shop") or sc.endswith("_Open")): continue
    base = b["type"]
    L = lay.get(base)
    if not L: continue
    a = math.radians(b["yaw"]); c, s = math.cos(a), math.sin(a)
    def w(x, z): return (b["pos"][0] + x * c + z * s, b["pos"][2] - x * s + z * c)
    for d in L["doors"]:
        cx, _, cz = d["center"]; ox, _, oz = d.get("outward", [0, 0, 1])
        hw = d["width"] / 2 + 0.2
        tx, tz = -oz, ox
        q = [(cx + tx * hw + ox * 0.05, cz + tz * hw + oz * 0.05), (cx - tx * hw + ox * 0.05, cz - tz * hw + oz * 0.05),
             (cx - tx * hw + ox * DEPTH, cz - tz * hw + oz * DEPTH), (cx + tx * hw + ox * DEPTH, cz + tz * hw + oz * DEPTH)]
        apron = Polygon([w(*p) for p in q])
        total[(base, d["side"])] += 1
        hit = False
        for k in tree.query(apron):
            j = idx[int(k)]
            if j == i: continue
            # a car park or a park may stand over a door apron (PLAN.md 1g f): it is open ground a body crosses
            if B[j]["type"].startswith(("Parking", "PocketPark", "Park")): continue
            if polys[j].intersection(apron).area > 0.05:
                hit = True; worst[(base, d["side"])].append((B[j]["type"], round(polys[j].intersection(apron).area, 2)))
                break
        if hit: bad[(base, d["side"])] += 1
print("enterable buildings' doors blocked by a neighbour within %.1f m:" % DEPTH)
for k in sorted(total, key=lambda k: -bad[k]):
    if bad[k]: print("  %-24s %-6s %3d of %3d   e.g. %s" % (k[0], k[1], bad[k], total[k], worst[k][:2]))
print("TOTAL", sum(bad.values()), "of", sum(total.values()))

# ---- reachability: from the front door's apron to every other door's apron, outside, round neighbours
import numpy as np
from shapely import prepared
WALK = ("Parking", "PocketPark", "Park")
RES, WIN, R = 0.5, 70.0, 0.4
unreach = Counter(); tested = Counter(); examples = defaultdict(list)
for i, b in enumerate(B):
    sc = IB.scene_of(b)
    if not (sc.endswith("_Shop") or sc.endswith("_Open")): continue
    L = lay.get(b["type"])
    if not L or len(L["doors"]) < 2: continue
    a = math.radians(b["yaw"]); c, s = math.cos(a), math.sin(a)
    def w(x, z): return (b["pos"][0] + x * c + z * s, b["pos"][2] - x * s + z * c)
    import building_door_paths as BDP
    W = BDP.window(polys[i])          # a building wider than WIN gets a wider window (the 72 m department store)
    x0, z0 = b["pos"][0] - W / 2, b["pos"][2] - W / 2
    n = int(round(W / RES))
    occ = np.zeros((n, n), bool)
    from shapely.geometry import box as sbox
    win = sbox(x0, z0, x0 + W, z0 + W)
    for k in tree.query(win):
        j = idx[int(k)]
        if B[j]["type"].startswith(WALK): continue
        if j == i:
            if IB.type_paved(B[j]["type"]): continue      # a compound's own yard is walkable; its doors open into it
            P = polys[j]
        else:
            P = polys[j].buffer(R)
        minx, minz, maxx, maxz = P.bounds
        pp = prepared.prep(P)
        from shapely.geometry import Point
        for gi in range(max(0, int((minx - x0) / RES)), min(n, int((maxx - x0) / RES) + 1)):
            for gj in range(max(0, int((minz - z0) / RES)), min(n, int((maxz - z0) / RES) + 1)):
                if pp.contains(Point(x0 + (gi + .5) * RES, z0 + (gj + .5) * RES)): occ[gi, gj] = True
    def cell(p): return int((p[0] - x0) / RES), int((p[1] - z0) / RES)
    doors = []
    for d in L["doors"]:
        cx, _, cz = d["center"]; ox, _, oz = d.get("outward", [0, 0, 1])
        doors.append((d["side"], cell(w(cx + ox * 1.2, cz + oz * 1.2))))
    front = [p for sd, p in doors if sd == "front"] or [doors[0][1]]
    seen = np.zeros_like(occ); from collections import deque
    dq = deque()
    for p in front:
        if 0 <= p[0] < n and 0 <= p[1] < n: seen[p] = True; dq.append(p)
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            u, v = x+dx, y+dy
            if 0 <= u < n and 0 <= v < n and not seen[u, v] and not occ[u, v]:
                seen[u, v] = True; dq.append((u, v))
    edge_reach = seen[0, :].any() or seen[-1, :].any() or seen[:, 0].any() or seen[:, -1].any()
    for sd, p in doors:
        if sd == "front": continue
        tested[(b["type"], sd)] += 1
        ok = 0 <= p[0] < n and 0 <= p[1] < n and seen[p]
        if not ok:
            unreach[(b["type"], sd)] += 1
            examples[(b["type"], sd)].append((round(b["pos"][0]), round(b["pos"][2])))
print("\nside/back doors NOT reachable outside from the front door (window %.0f m, body radius %.1f m):" % (WIN, R))
for k in sorted(tested, key=lambda k: -unreach[k]):
    print("  %-22s %-6s %3d of %3d unreachable   e.g. %s" % (k[0], k[1], unreach[k], tested[k], examples[k][:3]))
print("TOTAL", sum(unreach.values()), "of", sum(tested.values()))

# a GATE (PLAN.md 1g f, 2026-10-08: both read 0 after the rebuild): run by island_world.sh after the buildings stage
if sum(bad.values()) or sum(unreach.values()):
    print("island_door_access: FAIL")
    sys.exit(1)
print("island_door_access: PASS")
