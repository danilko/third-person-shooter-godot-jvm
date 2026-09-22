#!/usr/bin/env python3
"""island_network.py -- the island's ARTERIAL layer, built from the final plan's lines (PLAN.md 3.30 L2).

    python3 tools/island_network.py [--out <record>] [--preview <png>] [--check]

ONE-SHOT, the `import_melee_pack.py` contract. It writes `IslandRoads.arterials.roads.json` -- the INPUT of
`island_layout.py`, the record the editor edits (World.tscn `IslandRoadsArterials`, PLAN.md R5) -- from
`island_plan.arterial_lines()`: the pre-redo arterials deformed to the plan and the plan's new roads. After it has
run, the input is hand-owned again; re-running it throws the hand edits away, so it only writes with no `--out`
when asked (`--write`).

A LINE is a named polyline and a road type. The builder turns the set into a network by rules, never by a
coordinate typed per junction:
  1. each line is CLIPPED to land (the land grid, `island_reshape.LAND`, with `SHORE_M` of land to spare), keeping
     the runs longer than `MIN_RUN`;
  2. a free END within `SNAP_M` of another line (and not near that line's own end) is extended straight onto it: a T;
  3. every crossing of two lines is a junction; crossings within `MERGE_M` of each other are one junction;
  4. a STUB -- the part of a line past its last junction, shorter than `STUB_M`, ending free -- is trimmed at the
     junction (a road that crossed the coastal ring and ran on 100 m to the seawall becomes a T on the ring);
  5. each line is cut at its junctions into roads (`<name>`, `<name>__2`, ...) whose ends are the junction mouths,
     `MOUTH_M` from the centre (`roadkit_cli.py setback` solves them later); a junction of 3+ mouths is a pad
     (`island_roadgen.make_junction`), and 2 mouths (two lines meeting end to end) are a JOINT, SEGMENT-linked;
  6. every station stands on the natural ground (record z, never under the sea line).
A road still ending free is left for `island_turnarounds.py`, which gives it a loop.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from island_roadgen import Ground, make_junction, sample_ground   # noqa: E402
import island_plan as PL                            # noqa: E402
import point_model as pm                            # noqa: E402
import point_presets as ppr                         # noqa: E402

OUT = os.path.join(PL.PIECES, "IslandRoads.arterials.roads.json")
SHORE_M = 20.0          # a road stands at least this far inside the land
MIN_RUN = 120.0         # a clipped run shorter than this is dropped
BRIDGE_M = 70.0         # a wet gap this short inside a line is bridged, not cut
SNAP_M = 130.0          # a free end this near another line is extended onto it
END_CLEAR = 60.0        # ...unless the nearest point is this near that line's own end (then it is an end-to-end join)
JOIN_M = 30.0           # two free ends this near are joined end to end
MERGE_M = 60.0          # crossings nearer than this are one junction
STUB_M = 260.0          # a free-ending tail past the last junction shorter than this is trimmed
MOUTH_M = 26.0          # a mouth's first distance from its junction centre
STATION_M = 60.0        # stations along a road between junctions (the lines are densified: 6 m vertices)
ARTERIAL_BASE = {"median_width": 3.0, "left_walk_width": 4.0, "right_walk_width": 4.0}


# ------------------------------------------------------------------ geometry
def cumlen(pts):
    c = [0.0]
    for a, b in zip(pts, pts[1:]):
        c.append(c[-1] + math.dist(a, b))
    return c


def at(pts, cum, s):
    s = max(0.0, min(cum[-1], s))
    for i in range(len(pts) - 1):
        if cum[i + 1] >= s:
            f = (s - cum[i]) / max(1e-9, cum[i + 1] - cum[i])
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f)
    return pts[-1]


def densify(pts, step):
    cum = cumlen(pts)
    n = max(1, int(math.ceil(cum[-1] / step)))
    return [at(pts, cum, cum[-1] * k / n) for k in range(n + 1)]


def seg_x(a, b, c, d):
    """Parameter (t on ab, u on cd) of the crossing of two segments, or None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, u
    return None


def project(pts, cum, p):
    """(distance, arclength) of the nearest point of the polyline to p."""
    best = None
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + dx * t, a[1] + dy * t)
        d = math.dist(q, p)
        if best is None or d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best


# ------------------------------------------------------------------ the land
class Land(object):
    def __init__(self, ground):
        self.g = ground

    def ok(self, x, y):
        v = self.g.z(x, y)
        return v is not None and v > -0.2       # record z: the 0.6 m land base stands at 0.0

    def inland(self, x, y, m=SHORE_M):
        return self.ok(x, y) and all(self.ok(x + m * math.cos(a), y + m * math.sin(a))
                                     for a in (k * math.pi / 4 for k in range(8)))


def clip(line, land):
    """The runs of `line` that stand inland, each longer than MIN_RUN. A wet gap shorter than BRIDGE_M between two dry
    runs is kept: it is a canal or a slot the landfill left (3.29 R10's 運河), and the road bridges it."""
    pts = densify(line, 6.0)
    ok = [land.inland(*p) for p in pts]
    # close short wet gaps
    i = 0
    while i < len(pts):
        if not ok[i]:
            j = i
            while j < len(pts) and not ok[j]:
                j += 1
            if 0 < i and j < len(pts) and math.dist(pts[i - 1], pts[j]) <= BRIDGE_M:
                for k in range(i, j):
                    ok[k] = True
            i = j
        else:
            i += 1
    runs, cur = [], []
    for p, good in zip(pts, ok):
        if good:
            cur.append(p)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if cumlen(r)[-1] >= MIN_RUN]


# ------------------------------------------------------------------ the builder
class Line(object):
    def __init__(self, name, preset, pts):
        self.name, self.preset = name, preset
        self.pts = list(pts)
        self.free = [True, True]          # head, tail end free (no junction yet)

    @property
    def cum(self):
        return cumlen(self.pts)


def build_lines(ground):
    land = Land(ground)
    lines, report = [], []
    for name, preset, _d, pts in PL.arterial_lines(ground.z):
        runs = clip(pts, land)
        if not runs:
            report.append("%s: nothing inland, dropped" % name)
            continue
        for k, r in enumerate(runs):
            lines.append(Line(name if k == 0 else "%s_%d" % (name, k + 1), preset, r))
        if len(runs) > 1:
            report.append("%s: %d runs on land" % (name, len(runs)))
    return lines, report


def join_ends(lines):
    """Two free ends within JOIN_M: the second line is appended to the first (one road through the joint)."""
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if i == j:
                    continue
                if math.dist(a.pts[-1], b.pts[0]) < JOIN_M:
                    a.pts = a.pts + b.pts[1:]
                elif math.dist(a.pts[-1], b.pts[-1]) < JOIN_M:
                    a.pts = a.pts + list(reversed(b.pts))[1:]
                else:
                    continue
                lines.pop(j)
                changed = True
                break
            if changed:
                break


def snap_ends(lines):
    """A free end within SNAP_M of another line's interior is extended straight onto it."""
    n = 0
    for a in lines:
        for end in (0, -1):
            p = a.pts[end]
            best = None
            for b in lines:
                if b is a:
                    continue
                d, s = project(b.pts, b.cum, p)
                if d < SNAP_M and END_CLEAR < s < b.cum[-1] - END_CLEAR and (best is None or d < best[0]):
                    best = (d, b, s)
            if best is None or best[0] < 0.5:
                continue
            q = at(best[1].pts, best[1].cum, best[2])
            # overshoot 1 m so the crossing test finds it
            v = (q[0] - p[0], q[1] - p[1])
            L = math.hypot(*v)
            q2 = (q[0] + v[0] / L, q[1] + v[1] / L)
            if end == 0:
                a.pts.insert(0, q2)
            else:
                a.pts.append(q2)
            n += 1
    return n


def crossings(lines):
    """[(point, [(line index, arclength)])] -- every crossing, merged within MERGE_M."""
    raw = []
    for i, a in enumerate(lines):
        ca = a.cum
        for j in range(i + 1, len(lines)):
            b = lines[j]
            cb = b.cum
            for k in range(len(a.pts) - 1):
                for m in range(len(b.pts) - 1):
                    x = seg_x(a.pts[k], a.pts[k + 1], b.pts[m], b.pts[m + 1])
                    if x is None:
                        continue
                    t, u = x
                    p = (a.pts[k][0] + (a.pts[k + 1][0] - a.pts[k][0]) * t,
                         a.pts[k][1] + (a.pts[k + 1][1] - a.pts[k][1]) * t)
                    raw.append((p, [(i, ca[k] + t * (ca[k + 1] - ca[k])), (j, cb[m] + u * (cb[m + 1] - cb[m]))]))
    nodes = []
    for p, members in raw:
        for nd in nodes:
            if math.dist(nd[0], p) < MERGE_M:
                nd[1].extend(m for m in members if m[0] not in {x[0] for x in nd[1]})
                break
        else:
            nodes.append((p, list(members)))
    return nodes


def merge_close(lines, nodes, min_span=2 * MOUTH_M + 50.0):
    """Two junctions closer than `min_span` ALONG a line leave no room for a road between their mouths: one junction."""
    parent = list(range(len(nodes)))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    for i, ln in enumerate(lines):
        cs = sorted((project(ln.pts, ln.cum, p)[1], k) for k, (p, mem) in enumerate(nodes) if i in {m[0] for m in mem})
        for (s0, k0), (s1, k1) in zip(cs, cs[1:]):
            if s1 - s0 < min_span:
                parent[find(k1)] = find(k0)
    groups = {}
    for k in range(len(nodes)):
        groups.setdefault(find(k), []).append(k)
    out = []
    for ks in groups.values():
        pts = [nodes[k][0] for k in ks]
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        mem = {}
        for k in ks:
            for li, s in nodes[k][1]:
                mem.setdefault(li, s)
        out.append((c, list(mem.items())))
    return out


def trim_stubs(lines, nodes):
    """A free-ending tail shorter than STUB_M past a line's first/last junction is cut off at that junction."""
    n = 0
    for i, ln in enumerate(lines):
        ss = sorted(s for _p, mem in nodes for (li, s) in mem if li == i)
        if not ss:
            continue
        L = ln.cum[-1]
        lo, hi = ss[0], ss[-1]
        # cut 2 m PAST the junction, so the crossing is still a crossing (an end exactly on the other line reads as
        # t = 1.0000001 and is lost)
        new_lo = max(0.0, lo - 2.0) if 0 < lo < STUB_M else 0.0
        new_hi = min(L, hi + 2.0) if 0 < L - hi < STUB_M else L
        if new_lo == 0.0 and new_hi == L:
            continue
        cum = ln.cum
        keep = [at(ln.pts, cum, new_lo)] + [p for p, c in zip(ln.pts, cum) if new_lo < c < new_hi] + \
               [at(ln.pts, cum, new_hi)]
        ln.pts = keep
        n += 1
    return n


def build_net(ground, lines, report):
    nodes = merge_close(lines, crossings(lines))
    # re-measure every member's arclength on the (possibly trimmed) lines
    net = pm.NetworkData()
    cuts = {i: [] for i in range(len(lines))}         # line -> [(arclength, node index)]
    for k, (p, mem) in enumerate(nodes):
        for i, _s in mem:
            d, s = project(lines[i].pts, lines[i].cum, p)
            cuts[i].append((s, k))
    mouths = {k: [] for k in range(len(nodes))}
    made = 0
    for i, ln in enumerate(lines):
        cum = ln.cum
        L = cum[-1]
        marks = sorted(cuts[i])
        spans = []
        prev = (0.0, None)
        for s, k in marks:
            spans.append((prev, (s, k)))
            prev = (s, k)
        spans.append((prev, (L, None)))
        seg = 0
        for (s0, k0), (s1, k1) in spans:
            a = s0 + (MOUTH_M if k0 is not None else 0.0)
            b = s1 - (MOUTH_M if k1 is not None else 0.0)
            if b - a < 30.0:
                if k0 is None or k1 is None:
                    continue                         # a vanishing stub at an end: the junction takes it
                report.append("%s: span %.0f..%.0f too short between two junctions" % (ln.name, s0, s1))
                continue
            n = max(1, int(round((b - a) / STATION_M)))
            ss = [a + (b - a) * m / n for m in range(n + 1)]
            pts = [at(ln.pts, cum, s) for s in ss]
            pts3 = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
            seg += 1
            name = ln.name if seg == 1 else "%s__%d" % (ln.name, seg)
            while name in net.roads:
                name += "b"
            r = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
            if ln.preset:
                ppr.apply_preset(net, name, ln.preset)
            else:
                for f, v in ARTERIAL_BASE.items():
                    setattr(r.base, f, v)
                r.road_class = "arterial"
            prevu = None
            for q in pts3:
                p = net.add_station(r, q)
                if prevu is not None:
                    net.link(prevu, p.uid)
                prevu = p.uid
            if k0 is not None:
                mouths[k0].append(r.points[0])
            if k1 is not None:
                mouths[k1].append(r.points[-1])
            made += 1
    pads = joints = 0
    for k, ms in mouths.items():
        if len(ms) >= 3:
            make_junction(net, ms, signal=True)
            pads += 1
        elif len(ms) == 2:
            net.link(ms[0], ms[1])
            joints += 1
    report.append("%d roads, %d junctions, %d joints" % (made, pads, joints))
    return net


def build(ground):
    lines, report = build_lines(ground)
    join_ends(lines)
    report.append("%d end(s) snapped onto a road" % snap_ends(lines))
    nodes = crossings(lines)
    report.append("%d stub(s) trimmed" % trim_stubs(lines, nodes))
    net = build_net(ground, lines, report)
    sample_ground(net, ground, prefix="")
    return net, lines, report


def preview(lines, net, path):
    import numpy as np
    from PIL import Image, ImageDraw
    import island_reshape as R
    o = R.load(R.LAND)
    land = o > 0.35
    S = 0.5
    rgb = np.zeros(o.shape + (3,), np.uint8)
    rgb[:] = (20, 36, 60)
    v = np.clip(o / 435, 0, 1)[..., None]
    col = (np.array([60, 80, 55]) * (1 - v) + np.array([150, 130, 100]) * v).astype(np.uint8)
    rgb[land] = col[land]
    img = Image.fromarray(rgb).resize((int(4608 * S), int(4608 * S)))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((x + 2304) * S, (-y + 2304) * S)
    for name, r in net.roads.items():
        q = [P(*net.points[u].pos[:2]) for u in r.points]
        d.line(q, fill=(255, 200, 60), width=3)
        for u in (r.points[0], r.points[-1]):
            p = P(*net.points[u].pos[:2])
            jn = any(l.type == pm.LINK_JUNCTION for l in net.points[u].links)
            c = (255, 80, 80) if jn else (80, 200, 255)
            d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=c)
    img.save(path)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--write", action="store_true", help="overwrite the arterials input (throws hand edits away)")
    ap.add_argument("--preview", default="")
    a = ap.parse_args(argv)
    ground = Ground()
    net, lines, report = build(ground)
    for r in report:
        print("island_network: " + r)
    out = a.out or (OUT if a.write else "")
    if a.preview:
        preview(lines, net, a.preview)
    if out:
        pm.save_network(net, out)
        print("island_network: -> %s" % out)
    elif not a.preview:
        print("island_network: nothing written (--out <record> or --write)")


if __name__ == "__main__":
    main(sys.argv[1:])
