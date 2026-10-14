#!/usr/bin/env python3
"""island_align.py -- a road goes STRAIGHT THROUGH a junction (user, 2026-10-05: "straighten the streets so there is
no short wiggle at each junction, |___| rather than \\ / / ----/ -- easier to drive").

    python3 tools/island_align.py <record> [--check]

Measured on the island: 34 junctions where a road's two arms -- a THROUGH PAIR, the two mouths of one clique whose
outward directions are within THROUGH_DEG of opposite -- do not line up: offset up to 23 m sideways and up to 19 deg
apart, so a car drives a jog through every one of them. The roads come from many generators (the arterials input, the
trunk grid, the authored and planned streets, the dike's side roads), each of which cut its T on its own, so the fix is
ONE pass over the result, here, before the setback solve sizes the pads:

* for each through pair (greedily, the straightest pair first, each mouth in one pair), take on each arm the station
  FAR m out along its own road, or the next junction's mouth or the road's end if that comes first (the far station
  itself is never moved);
* the line through those two far stations is the road's line through the junction: the two mouths, and every station
  between a mouth and its far station, are moved onto it (plan only; heights are kept, the grade pass smooths them);
* a pair needing a move over MAX_MOVE, or whose far stations are under MIN_SPAN apart, is left and reported.

Expressways, ramps, rail, the touge, the cliff road, the dike's side roads, rotaries and turnaround loops are left
alone: each of those turns on purpose. `--check` reports the jogs without changing anything (exit 1 if any is over
JOG_TOL).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen  # noqa: E402,F401  (sets up the road kit's path)
import point_model as pm  # noqa: E402

THROUGH_DEG = 25.0      # two arms within this of opposite are one road through the junction
FAR = 50.0              # the station this far out on each arm fixes the road's line
MAX_MOVE = 30.0         # a station moved further than this: left alone, reported
MIN_SPAN = 30.0         # the two far stations at least this far apart
JOG_TOL = 1.0           # m: a through pair offset under this (and under JOG_DEG) is already straight
JOG_DEG = 3.0
CORNER_DEG = 20.0       # an arm whose own heading turns more than this has a corner: its line stops there
ROUNDS = 15              # straightening one pair moves the far station of the next: repeat until nothing moves
from island_plan import MOUNTAIN_ROADS  # noqa: E402
SKIP = ("shuto_", "rail_", "kaigan_dori", "teibo_sokudo", "ring_kita") + MOUNTAIN_ROADS
SKIP_IN = ("rotary", "_loop")


def skip(name):
    return name.startswith(SKIP) or any(s in name for s in SKIP_IN)


WIGGLE_MIN = 1.5        # deg: two consecutive stations turning opposite ways by more than this...
WIGGLE_MAX = 35.0       # ...and less than this (a bigger S is a designed one: reported, not changed)...
WIGGLE_SPAN = 80.0      # ...less than this far apart are an S-WIGGLE
WIGGLE_MOVE = 20.0      # straightened onto the chord of their neighbours when neither moves further than this...
WIGGLE_CLEAR = 25.0     # ...and no other road's station is within this of where they would go


def unwiggle(net, road_of, jl):
    """A road turning one way and then the other within a few tens of metres (user, 2026-10-06: "|, /, \\, |" should
    be "|, |, |" or one even curve): the two stations of such an S go onto the chord between the stations either side
    of them. Junction mouths, joints and road ends are never moved; repeated until nothing changes."""
    def turn(a, b, c):
        h0 = math.atan2(b[1] - a[1], b[0] - a[0])
        h1 = math.atan2(c[1] - b[1], c[0] - b[0])
        return math.degrees((h1 - h0 + math.pi) % (2 * math.pi) - math.pi)

    def anchor(u, name):
        p = net.points[u]
        return bool(jl(u)) or any(l.type != pm.LINK_SEGMENT or road_of.get(l.target) is not road_of[u]
                                  for l in p.links)

    flat = 0
    for _ in range(10):
        changed = 0
        for r in net.roads.values():
            if skip(r.name) or len(r.points) < 4:
                continue
            pts = r.points
            for i in range(1, len(pts) - 2):
                u, v = pts[i], pts[i + 1]
                if anchor(u, r.name) or anchor(v, r.name):
                    continue
                P = [net.points[q].pos for q in pts[i - 1:i + 3]]
                t1, t2 = turn(P[0], P[1], P[2]), turn(P[1], P[2], P[3])
                if t1 * t2 >= 0 or not (WIGGLE_MIN < abs(t1) < WIGGLE_MAX and WIGGLE_MIN < abs(t2) < WIGGLE_MAX):
                    continue
                if math.dist(P[1][:2], P[2][:2]) > WIGGLE_SPAN:
                    continue
                A, B = P[0], P[3]
                L = math.hypot(B[0] - A[0], B[1] - A[1]) or 1.0
                dx, dy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
                proj = []
                for p in (P[1], P[2]):
                    t = (p[0] - A[0]) * dx + (p[1] - A[1]) * dy
                    proj.append((A[0] + dx * t, A[1] + dy * t, p[2]))
                if max(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip((P[1], P[2]), proj)) > WIGGLE_MOVE:
                    continue
                if any(road_of.get(w) is not r and math.hypot(o.pos[0] - q[0], o.pos[1] - q[1]) < WIGGLE_CLEAR
                       for q in proj for w, o in net.points.items()):
                    continue
                net.points[u].pos, net.points[v].pos = proj
                changed += 1
        flat += changed
        if not changed:
            break
    return flat


def main(argv):
    path = argv[0]
    check = "--check" in argv
    net = pm.load_network(path)
    road_of = {q: r for r in net.roads.values() for q in r.points}

    def jl(u):
        return [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION and l.target in road_of]

    def arm(u):
        """The stations of u's road from u outward, as a list starting at u (u is an end of its road)."""
        r = road_of[u]
        pts = list(r.points)
        if pts[0] == u:
            return pts
        if pts[-1] == u:
            return pts[::-1]
        return None

    def xy(u):
        p = net.points[u].pos
        return (p[0], p[1])

    def outward(u):
        a = arm(u)
        if not a or len(a) < 2:
            return None
        p, q = xy(a[0]), xy(a[1])
        L = math.dist(p, q) or 1.0
        return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)

    def far_of(u):
        """The arm's stations up to its far station (inclusive), stopping before another junction's mouth."""
        a = arm(u)
        out, s = [a[0]], 0.0
        h0 = None
        for i in range(1, len(a)):
            p, q = xy(a[i - 1]), xy(a[i])
            h = math.atan2(q[1] - p[1], q[0] - p[0])
            if h0 is None:
                h0 = h
            elif abs((h - h0 + math.pi) % (2 * math.pi) - math.pi) > math.radians(CORNER_DEG):
                break                       # the arm turns a corner: its line ends at the corner station
            s += math.dist(p, q)
            out.append(a[i])
            if s >= FAR or jl(a[i]):
                break                       # far enough, or another junction's mouth: the far station (never moved)
        return out

    cliques, seen = [], set()
    for u in road_of:
        if u in seen or not jl(u):
            continue
        comp, stack = set(), [u]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack += jl(x)
        seen |= comp
        cliques.append(sorted(comp))

    total = 0
    for rnd in range(1 if check else ROUNDS):
        moved = skipped = 0
        jogs = []
        for comp in cliques:
            if any(road_of[q].name.startswith("shuto_") for q in comp):
                continue        # an expressway ramp lands here: its junction is placed for the ramp's grade (Suburb exit)
            cands = []
            for i, u in enumerate(comp):
                for v in comp[i + 1:]:
                    if skip(road_of[u].name) or skip(road_of[v].name):
                        continue
                    du, dv = outward(u), outward(v)
                    if du is None or dv is None:
                        continue
                    dot = du[0] * dv[0] + du[1] * dv[1]
                    if dot > -math.cos(math.radians(THROUGH_DEG)):
                        continue
                    cands.append((dot, u, v))
            used = set()
            for dot, u, v in sorted(cands):
                if u in used or v in used:
                    continue
                used |= {u, v}
                fa, fb = far_of(u), far_of(v)
                A, B = xy(fa[-1]), xy(fb[-1])
                span = math.dist(A, B)
                if span < MIN_SPAN or len(fa) < 2 or len(fb) < 2:
                    continue
                dx, dy = (B[0] - A[0]) / span, (B[1] - A[1]) / span
                stations = fa[:-1] + fb[:-1]
                offs = [abs((xy(q)[0] - A[0]) * dy - (xy(q)[1] - A[1]) * dx) for q in stations]
                ang = math.degrees(math.acos(max(-1.0, min(1.0, -dot))))      # degrees off a straight line
                if max(offs) <= JOG_TOL and ang <= JOG_DEG:
                    continue
                name = "%s / %s" % (road_of[u].name, road_of[v].name)
                jogs.append((round(max(offs), 1), round(ang, 1), name, [round(c) for c in xy(u)]))
                if check:
                    continue
                if max(offs) > MAX_MOVE:
                    skipped += 1
                    print("island_align: LEFT %s at (%.0f, %.0f): would move a station %.1f m" % (name, xy(u)[0], xy(u)[1],
                                                                                               max(offs)))
                    continue
                for q in stations:
                    p = net.points[q].pos
                    t = (p[0] - A[0]) * dx + (p[1] - A[1]) * dy
                    nxp, nyp = A[0] + dx * t, A[1] + dy * t
                    if math.hypot(nxp - p[0], nyp - p[1]) > 0.05:
                        moved += 1
                    net.points[q].pos = (nxp, nyp, p[2])
        total += moved
        if check or moved == 0:
            break
    flat = 0 if check else unwiggle(net, road_of, jl)
    if check:
        bad = [j for j in jogs if j[0] > JOG_TOL]
        print("island_align: %d junction through-pair(s) not straight (worst %s)" % (len(jogs), max(jogs) if jogs else "-"))
        return 1 if bad else 0
    pm.save_network(net, path)
    print("island_align: %d round(s), %d station move(s); %d pair(s) left (move over %.0f m); %d S-wiggle(s) "
          "straightened" % (rnd + 1, total, skipped, MAX_MOVE, flat))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
