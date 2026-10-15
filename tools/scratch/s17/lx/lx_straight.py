import sys, math, json
sys.path.insert(0, "tools"); import island_layout as IL
W = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
def polys(path):
    d = json.load(open(path)); P = {p["uid"]: p["pos"] for p in d["points"]}
    return {r["name"]: [P[u][:2] for u in r["points"] if u in P] for r in d["roads"]}
roads, rails = polys(IL.OUTPUT), polys(IL.RAIL_RECORD)
def turn_near(pts, x, y, w):
    """max heading change (deg) along the polyline within +-w m (arc) of its closest point to (x, y)"""
    best, cum, acc = None, [0.0], 0.0
    for a, b in zip(pts, pts[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1]); cum.append(acc)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]; n = vx * vx + vy * vy or 1e-9
        t = max(0, min(1, ((x - a[0]) * vx + (y - a[1]) * vy) / n))
        dd = math.hypot(x - a[0] - vx * t, y - a[1] - vy * t)
        if best is None or dd < best[0]: best = (dd, cum[i] + t * math.sqrt(n))
    s0 = best[1]
    hs = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(pts, pts[1:])
          if cum[pts.index(b)] >= s0 - w and cum[pts.index(a)] <= s0 + w]
    if not hs: return 0.0
    ref = hs[0]; dev = [((h - ref + 180) % 360) - 180 for h in hs]
    return max(dev) - min(dev)
for r in IL.level_crossings(IL.OUTPUT, IL.RAIL_RECORD, IL.arterial_names()):
    road, rail, (x, y), ang = r[0], r[1], r[2], r[3]
    tr = turn_near(rails[rail], x, y, W) if rail in rails else float("nan")
    td = turn_near(roads[road], x, y, W) if road in roads else float("nan")
    bad = [k for k, v in (("RAIL bends", tr), ("ROAD bends", td)) if v > 2.0] + (["angle %.0f" % ang] if ang < 80 else [])
    print("%-22s x %-14s at (%7.1f, %7.1f)  angle %3.0f  rail turns %5.1f deg  road turns %5.1f deg within +-%.0f m  %s"
          % (road, rail, x, y, ang, tr, td, W, "  <- " + ", ".join(bad) if bad else "ok"))
