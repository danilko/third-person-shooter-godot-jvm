"""S18 castle group: move shrine_touge's first hairpin (stations 27..34, the west bend at (-505, 10)) clear of the
squared Shuri Castle (IslandSites yaw 90 at (-570, -40)), re-fillet, re-station and re-profile ONLY that window.
    python3 tools/scratch/s18/hairpin.py <dx> <dy> [--write <out.json>]
Prints the clearance to the castle's site box, the window's worst grade, the kinks, and cut/fill against the land."""
import json, math, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import island_touges as T            # noqa: E402
import island_shrine_touge as ST     # noqa: E402

CASTLE = dict(x=-570.0, y=-40.0, yaw=90.0, size=(158.0, 128.0))
LEG_IN, ARC, LEG_OUT = (20, 24), (27, 34), (38, 42)       # station indices (held IslandTouge.json)


def box_dist(x, y, c=CASTLE):
    a = math.radians(c["yaw"]); co, si = math.cos(a), math.sin(a)
    dx, dy = x - c["x"], y - c["y"]
    u, v = dx * co + dy * si, -dx * si + dy * co
    hu, hv = c["size"][0] / 2, c["size"][1] / 2
    ou, ov = max(0.0, abs(u) - hu), max(0.0, abs(v) - hv)
    return math.hypot(ou, ov) if (ou or ov) else -min(hu - abs(u), hv - abs(v))


def build(dx, dy, doc):
    st = [tuple(p) for p in doc["stations"]]
    i0, i1 = LEG_IN[0], LEG_OUT[1]
    arc = [(p[0] + dx, p[1] + dy) for p in st[ARC[0]:ARC[1] + 1]]
    ctrl = [p[:2] for p in st[i0:LEG_IN[1] + 1]] + arc + [p[:2] for p in st[LEG_OUT[0]:i1 + 1]]
    keep = set(arc[1:-1])
    line, _ = ST.fillet(ctrl, keep=keep, nodrop=set(arc) | {ctrl[0], ctrl[-1]})
    new = ST._stations(line)
    # z: the held ends, the window profiled on the ground at the limit, then an 80 m moving average spliced in
    raw = T.Land()
    ground = [raw(*p) for p in new]
    fixed = {0: st[i0][2], len(new) - 1: st[i1][2]}
    z = ST._profile(new, ground, fixed)
    full_xy = [p[:2] for p in st[:i0]] + list(new) + [p[:2] for p in st[i1 + 1:]]
    full_z = [p[2] for p in st[:i0]] + z + [p[2] for p in st[i1 + 1:]]
    sm = ST.vertical_curves(full_xy, full_z)
    a, b = i0, i0 + len(new) - 1
    out_z = full_z[:]
    for k in range(a, b + 1):
        out_z[k] = sm[k]
    return st, full_xy, out_z, (a, b), ground


def report(full_xy, z, win, ground, st_old):
    a, b = win
    seg = range(max(0, a - 3), min(len(full_xy) - 1, b + 3))
    g = max(abs(z[k + 1] - z[k]) / (math.dist(full_xy[k], full_xy[k + 1]) or 1) for k in seg)
    clear = min(box_dist(*full_xy[k]) for k in range(a, b + 1))
    clear_old = min(box_dist(*p[:2]) for p in st_old[LEG_IN[0]:LEG_OUT[1] + 1])
    cf = [z[a + i] - ground[i] for i in range(len(ground))]
    kinks = []
    for k in range(a, b):
        if 0 < k < len(full_xy) - 1:
            t = abs(math.degrees(ST._turn(full_xy[k - 1], full_xy[k], full_xy[k + 1])))
            if t > 30.0:
                kinks.append(round(t))
    L = sum(math.dist(full_xy[k], full_xy[k + 1]) for k in range(a, b))
    Lo = sum(math.dist(st_old[k][:2], st_old[k + 1][:2]) for k in range(LEG_IN[0], LEG_OUT[1]))
    print("window %d..%d: %.0f m (was %.0f), worst grade %.1f%%, castle clearance %.1f m (was %.1f with the castle "
          "squared; 25 = SITE_CLEAR), fill %.1f / cut %.1f m, sharp vertex turns %s" % (
              a, b, L, Lo, 100 * g, clear, clear_old, max(cf), -min(cf), kinks or "none"))
    return g, clear


if __name__ == "__main__":
    dx, dy = float(sys.argv[1]), float(sys.argv[2])
    doc = json.load(open(T.ALIGNMENT))
    st, xy, z, win, ground = build(dx, dy, doc)
    report(xy, z, win, ground, st)
    if "--write" in sys.argv:
        out = sys.argv[sys.argv.index("--write") + 1]
        doc["stations"] = [[round(p[0], 2), round(p[1], 2), round(v, 2)] for p, v in zip(xy, z)]
        doc["note"] += (" S18 (2026-10-15): the first hairpin moved (%.0f, %.0f) m clear of the squared Shuri Castle "
                        "(tools/scratch/s18/hairpin.py)." % (dx, dy))
        json.dump(doc, open(out, "w"), indent=1)
        open(out, "a").write("\n")
        print("wrote", out)
