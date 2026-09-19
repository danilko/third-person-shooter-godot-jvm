#!/usr/bin/env python3
"""island_trunk_grid.py -- the city's TRUNK GRID (PLAN.md 3.13 step 3): 幹線道路, 3 lanes each way.

    python3 tools/island_trunk_grid.py <record> --from <base record> [--check]

Writes into `<record>` the base record plus the grid, so a re-run is exact; refused on a record that already has it
(a road named `*_hondori` / `ekimae_dori`). Inside the C1 loop (the city, `island_expressway.py`) the sketch draws a
grid of large roads. The existing arterials already frame it (rinkai_dori south, nogyo_michi north, chuo_dori west,
hama_dori east, yamate_dori across the middle), so the grid adds:

* three NORTH-SOUTH trunks from rinkai_dori to nogyo_michi: `nishi_hondori` (x 400), `naka_hondori` (x 725, the one
  the C1 diamond lands on) and `higashi_hondori` (x 1100);
* one EAST-WEST trunk, `ekimae_dori` (y 250), from chuo_dori to hama_dori;
* `yamate_dori` upgraded to the trunk section.

Every crossing is a signalised junction: a crossing of two new trunks is built as one, an existing road is CUT to land
one (`island_roadgen.cut_road`), and a trunk meeting an arterial end-on makes a T. The trunk section is the `trunk`
preset (`point_presets`: 3 + 3 lanes, raised median, 4 m footways). Junction mouths start `MOUTH` from the centre;
`roadkit_cli.py setback` solves them afterwards (the island pipeline in PLAN.md).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from island_roadgen import *    # noqa: E402,F401,F403
import point_model as pm        # noqa: E402
import point_presets as pr      # noqa: E402
import point_validate as pv     # noqa: E402

MOUTH = 26.0          # a junction mouth's first distance from the centre (setback re-solves it)
SPACING = 90.0        # stations along a trunk between junctions
NS = (("nishi_hondori", 400.0), ("naka_hondori", 725.0), ("higashi_hondori", 1100.0))
EW = ("ekimae_dori", 250.0)
UPGRADE = ("yamate_dori",)


def crossing_y(net, prefix, x):
    """y where the road `prefix*` crosses the vertical line x (its chain is monotone in x there)."""
    best = None
    for name, r in net.roads.items():
        if not name.startswith(prefix):
            continue
        pts = [net.points[u].pos for u in r.points]
        for a, b in zip(pts, pts[1:]):
            if (a[0] - x) * (b[0] - x) <= 0 and a[0] != b[0]:
                t = (x - a[0]) / (b[0] - a[0])
                return a[1] + (b[1] - a[1]) * t
    return best


def crossing_x(net, prefix, y):
    for name, r in net.roads.items():
        if not name.startswith(prefix):
            continue
        pts = [net.points[u].pos for u in r.points]
        for a, b in zip(pts, pts[1:]):
            if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
                t = (y - a[1]) / (b[1] - a[1])
                return a[0] + (b[0] - a[0]) * t
    return None


def trunk_road(net, name, a, b, ground):
    """A trunk road from mouth a to mouth b (plan points), stations every ~SPACING, draped on the ground."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    k = max(1, int(round(L / SPACING)))
    pts = []
    for m in range(k + 1):
        x, y = a[0] + (b[0] - a[0]) * m / k, a[1] + (b[1] - a[1]) * m / k
        pts.append((x, y, max(0.0, ground.z(x, y) or 0.0)))
    r = chain_road(net, name, pts, preset="trunk")
    return r.points[0], r.points[-1]


def build(net, ground):
    for name in list(net.roads):
        if any(name.startswith(p) for p in UPGRADE):
            pr.apply_preset(net, name, "trunk")
    junctions = {}                                   # centre (x, y) -> [mouth uids]

    def add(c, u):
        junctions.setdefault((round(c[0], 1), round(c[1], 1)), []).append(u)
    # the lines and where they meet what: a list of (param, centre, kind) along each line
    lines = []
    ew_name, ew_y = EW
    ew_x0 = crossing_x(net, "chuo_dori", ew_y)
    ew_x1 = crossing_x(net, "hama_dori", ew_y)
    for name, x in NS:
        y0 = crossing_y(net, "rinkai_dori", x)
        y1 = crossing_y(net, "nogyo_michi", x)
        ym = crossing_y(net, "yamate_dori", x)
        stops = [(y0, "rinkai_dori"), (ew_y, None), (ym, "yamate_dori"), (y1, "nogyo_michi")]
        lines.append((name, [((x, y), cut) for y, cut in stops], "y"))
    stops = [((ew_x0, ew_y), "chuo_dori")] + [((x, ew_y), None) for _n, x in NS] + [((ew_x1, ew_y), "hama_dori")]
    lines.append((ew_name, stops, "x"))
    # cut the existing roads at every stop that lands on one (once per centre)
    cut_done = set()
    for _name, stops, _ax in lines:
        for c, cut in stops:
            key = (round(c[0], 1), round(c[1], 1))
            if cut and key not in cut_done:
                ma, mb = cut_road(net, c, cut, MOUTH)
                add(c, ma)
                add(c, mb)
                cut_done.add(key)
    # the trunk roads between consecutive stops
    for name, stops, _ax in lines:
        seg = 0
        for (c0, _k0), (c1, _k1) in zip(stops, stops[1:]):
            dx, dy = c1[0] - c0[0], c1[1] - c0[1]
            L = math.hypot(dx, dy)
            ux, uy = dx / L, dy / L
            a = (c0[0] + ux * MOUTH, c0[1] + uy * MOUTH)
            b = (c1[0] - ux * MOUTH, c1[1] - uy * MOUTH)
            seg += 1
            ua, ub = trunk_road(net, name if seg == 1 else "%s__%d" % (name, seg), a, b, ground)
            add(c0, ua)
            add(c1, ub)
    for c, mouths in junctions.items():
        make_junction(net, mouths)
    return junctions


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out = argv[0]
    base = argv[argv.index("--from") + 1] if "--from" in argv else out
    net = pm.load_network(base)
    if any(n.startswith(NS[0][0]) or n.startswith(EW[0]) for n in net.roads):
        raise SystemExit("island_trunk_grid: %s already carries the grid; pass --from <base record>" % base)
    ground = Ground()
    j = build(net, ground)
    for name, r in net.roads.items():
        for u in r.points:
            p = net.points[u]
            if not p.has_ground_z:
                g = ground.z(p.pos[0], p.pos[1])
                if g is not None:
                    p.ground_z, p.has_ground_z = round(g, 3), True
    pm.save_network(net, out)
    print("island_trunk_grid: %d junctions, %d roads, %d stations -> %s" % (len(j), len(net.roads), len(net.points), out))
    if "--fast" in argv:
        return
    errs = pv.errors(pv.validate(net))
    for f in errs:
        print("  ERROR %s" % f.message[:200])
    flow = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "blender", "tools", "roadkit_cli.py"), "flow",
                                      out], capture_output=True, text=True).stdout)["report"]
    if flow:
        print("island_trunk_grid: flow %d lanes, %s" % (flow["lanes"], {k: len(flow[k]) for k in
              ("broken", "misjoined", "unreached", "ramp_orphans", "open_end")}))
    if "--check" in argv and (errs or not flow or flow["broken"] or flow["misjoined"]):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
