#!/usr/bin/env python3
"""island_grades.py -- round every GRADE BREAK in the island's road profiles, and rank what is left
(PLAN.md 0.7 cause 3).

    python3 tools/island_grades.py smooth <record> [--length 80] [--dry]
    python3 tools/island_grades.py rank <lanekit.json>... [--window 12] [--top N] [--all-kinds]

**A grade break is what a car launches off.** A profile is built span by span -- `bench_profile`, a grade cone, a
deck's `CLEAR` over the ground -- and every one of those holds a LIMIT per span and says nothing about the CHANGE
from one span to the next, so a road can meet its 5% limit at every station and still step from -3.13% to +3.12%
across one of them. Driven at 45 m/s that sag hands the wheels 2.8 m/s of vertical velocity in one tick and the
suspension throws the car; measured on the island before this pass, the worst on-road rise was 5.4 m/s.

**The rule is 3.2d's, applied to every road instead of only the touge** (`island_shrine_touge.vertical_curves`):
the profile's moving average over `LENGTH` metres of arc length IS a vertical curve, it turns a break of A into a
parabola `LENGTH` long (K = LENGTH / A), and -- because the derivative of an average is the average of the
derivative -- it can never make a span steeper than the steepest it was built from. So it is safe to run over a
whole network without re-checking every road's grade limit.

**What is HELD, and why each one:**

* a junction MOUTH (`INTERSECTION`), because a pad is solved from its mouths, so moving one silently re-grades
  the pad;
* a ramp MOUTH (`RAMP`) **and the station after it**, because that span is the gore: the ramp and the carriageway
  it leaves share paving there, and dropping the far station tilts it. That is a measured defect, not a worry --
  `island_expressway.diamond` already keeps a diamond ramp level through its diverge because a ramp 2 m down while
  it still shared the gore left a lip a straddling car launched off at 3.1 m/s. The cost is that a ramp's
  level-to-descent break is not rounded (its gore span is 90 m, longer than the curve, so it could not be rounded
  from that side anyway) -- and it is a CREST, which unloads a car rather than throwing it, unlike the sags this
  pass exists for;
* the first and last station of every CORRIDOR. A JOINT -- two coincident stations in two roads, SEGMENT-linked,
  which is how `island_road_zones --split` cuts a long run for the zone grid -- is one road cut in two, so the two
  halves are smoothed as ONE profile and the pair moves together (the terrain stamp already joins corridors at
  joints for the same reason). Only a real road END is held: a junction mouth, a turnaround arm, a dead end;
* every station of a `pillar_skip` span AND THE ONE EITHER SIDE OF IT, because that is a deck fitted to a
  structure (the Rainbow Bridge's road sits at `library_landmarks.RB_ROAD_LOWER` and its own gate asserts that to
  0.5 m over the whole suspension span). The span boundary falls BETWEEN two stations, so holding only the deck's
  own two ends still lets the curve into the approach dip below the deck inside the span -- measured 0.23 m of the
  0.5 m there, which is margin spent for nothing on a road that is four stations long.

**A held station is a BOUNDARY, not a pin with a hole beside it.** The average is taken separately over each
stretch between two held stations, each extended past its ends by its own end SLOPE -- so a stretch that is
straight where it meets the anchor comes back untouched there, and pinning an anchor can never itself introduce
the break this pass exists to remove. (Averaging the whole corridor and pinning the anchors afterwards does: it
took a diamond ramp's 6.15% break to 6.40%, because the station 36 m past the anchor moved and the anchor did
not.) A flat road, or one the average returns unchanged, is left byte-identical, so the pass is idempotent in
effect on anything already smooth.

**A vertical curve needs stations to be followed.** The exported Path3D interpolates between stations, so a break
between two stations 90 m apart cannot be rounded into a 80 m curve -- `smooth` reports every break it could not
take below `REPORT` and names the road, which is a request for more stations there (or a re-graded alignment), not
a silent pass.
"""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

LENGTH = 80.0     # the vertical curve: K = 8 m/% on a 10% break (island_shrine_touge.VC_LENGTH)
WINDOW = 12.0     # `rank`: the grade either side of a lane sample is measured over this much road
REPORT = 0.03     # `smooth` names every station break it leaves above this


# ------------------------------------------------------------------------------------ the vertical curve

def moving_average(s, z, length=LENGTH):
    """The piecewise-linear profile z(s) averaged over a window `length` long, evaluated at each s.

    The profile is extended past both ends by its own end SLOPE, not by its end value: a constant extension
    flattens the grade into the end, which is exactly the break this pass removes when the end is a junction
    mouth a road arrives at on a grade. With a linear extension a locally straight end comes back unchanged."""
    n = len(s)
    if n < 3:
        return list(z)
    h = length / 2.0
    g0 = (z[1] - z[0]) / max(1e-9, s[1] - s[0])
    g1 = (z[-1] - z[-2]) / max(1e-9, s[-1] - s[-2])
    xs = [s[0] - h] + list(s) + [s[-1] + h]
    zs = [z[0] - g0 * h] + list(z) + [z[-1] + g1 * h]
    cum = [0.0]                                            # the integral of the extended profile
    for a, b, za, zb in zip(xs, xs[1:], zs, zs[1:]):
        cum.append(cum[-1] + (za + zb) / 2.0 * (b - a))

    def integral(x):
        if x <= xs[0]:
            return cum[0] + (x - xs[0]) * zs[0]
        if x >= xs[-1]:
            return cum[-1] + (x - xs[-1]) * zs[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        f = (x - xs[lo]) / max(1e-9, xs[hi] - xs[lo])
        zx = zs[lo] + (zs[hi] - zs[lo]) * f
        return cum[lo] + (zs[lo] + zx) / 2.0 * (x - xs[lo])

    return [(integral(v + h) - integral(v - h)) / (2.0 * h) for v in s]


def breaks(s, z, window=None):
    """[(break, i)] -- the change in grade across each interior station, over `window` metres either side (the
    stations themselves when `window` is None)."""
    out = []
    for i in range(1, len(s) - 1):
        if window is None:
            a, b = i - 1, i + 1
        else:
            a = next((j for j in range(i, -1, -1) if s[i] - s[j] >= window), 0)
            b = next((j for j in range(i, len(s)) if s[j] - s[i] >= window), len(s) - 1)
            if a == i or b == i:
                continue
        g0 = (z[i] - z[a]) / max(1e-9, s[i] - s[a])
        g1 = (z[b] - z[i]) / max(1e-9, s[b] - s[i])
        out.append((abs(g1 - g0), i, g0, g1))
    return out


# ------------------------------------------------------------------------------------ corridors

JOINT_TOL = 0.05


def corridors(net):
    """Every road's chain, with roads joined at a JOINT walked as ONE profile. Returns [(name, nodes)] where a
    node is the list of PointData that share that station (two at a joint, one everywhere else)."""
    chains = {nm: net.chain(r) for nm, r in net.roads.items() if net.chain(r)}
    ends = {}                                              # uid -> (road, "head"/"tail")
    for nm, ch in chains.items():
        ends[ch[0].uid] = (nm, "head")
        ends[ch[-1].uid] = (nm, "tail")
    join = {}                                              # (road, end) -> (road, end)
    for nm, ch in chains.items():
        for p, side in ((ch[0], "head"), (ch[-1], "tail")):
            for l in p.links:
                if l.type != "SEGMENT" or l.target not in ends:
                    continue
                q = net.points[l.target]
                other = ends[l.target]
                if other[0] == nm or math.dist(p.pos, q.pos) > JOINT_TOL:
                    continue
                join[(nm, side)] = other
    seen, out = set(), []
    for nm in sorted(chains):
        if nm in seen:
            continue
        run = [nm]                                         # walk both ways from this road
        seen.add(nm)
        while True:
            nxt = join.get((run[-1], "tail")) or join.get((run[-1], "head"))
            if not nxt or nxt[0] in seen:
                break
            run.append(nxt[0])
            seen.add(nxt[0])
        while True:
            prv = join.get((run[0], "head")) or join.get((run[0], "tail"))
            if not prv or prv[0] in seen:
                break
            run.insert(0, prv[0])
            seen.add(prv[0])
        nodes = []
        for k, r in enumerate(run):                        # orient each chain to continue the one before it
            ch = list(chains[r])
            if k and math.dist(nodes[-1][0].pos, ch[-1].pos) <= JOINT_TOL:
                ch.reverse()
            elif k == 0 and len(run) > 1 and math.dist(ch[0].pos, chains[run[1]][0].pos) <= JOINT_TOL:
                ch.reverse()
            if nodes and math.dist(nodes[-1][0].pos, ch[0].pos) <= JOINT_TOL:
                nodes[-1].append(ch.pop(0))                # the joint: one station, two points
            nodes += [[p] for p in ch]
        out.append((run[0] if len(run) == 1 else "%s+%d" % (run[0], len(run) - 1), nodes))
    return out


# ------------------------------------------------------------------------------------ the gore is level

GORE_MARGIN = 1.0     # the ramp holds its mainline's height until the two paved bands are this far apart
GORE_GRADE = 0.07     # ...and leaves that height no steeper than this
_GORE_HELD = set()    # uids `level_gores` fixed: anchors for `held_indices`


def _road_half(road):
    b = road.base
    return max(b.lanes_fwd, b.lanes_bwd) * b.lane_width + b.median_width / 2.0 + max(b.left_walk_width,
                                                                                         b.right_walk_width)


def _nearest(poly, x, y):
    """(plan distance, surface z) of the nearest point of polyline `poly` [(x, y, z)] to (x, y)."""
    best = (1e18, 0.0)
    for a, b in zip(poly, poly[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        px, py = a[0] + dx * t, a[1] + dy * t
        d = math.hypot(px - x, py - y)
        if d < best[0]:
            best = (d, a[2] + (b[2] - a[2]) * t)
    return best


def level_gores(net):
    """A RAMP IS LEVEL WITH ITS MAINLINE UNTIL THE TWO PAVED BANDS HAVE PARTED (PLAN.md 0.10(b)).

    Each ramp generator made its ramp level AT ITS MOUTH and then graded it away from there -- and the paving of the
    ramp and of the mainline still overlaps for tens of metres past the mouth. Measured: the diamond's exit
    `shuto_d_fwd_off` was 0.25-1.2 m below C1's deck while still under it (a car on the ramp meets C1's edge in front
    of its bumper, `probe_road_clear`), and the Wangan's merge `shuto_wangan_e__3` ran 0.86 m under
    `shuto_spur_out_w` the same way. So: from every RAMP mouth, along the ramp, every station takes the mainline's own
    surface height until the ramp's centreline is `half(mainline) + half(ramp) + GORE_MARGIN` from the mainline's;
    a station is inserted where that happens inside a span; beyond it the ramp's own profile is pulled into a
    GORE_GRADE cone from the held height. The held stations are anchors for `smooth` (`_GORE_HELD`).

    Returns report lines."""
    import island_roadgen as rg
    road_of = {q: n for n, r in net.roads.items() for q in r.points}
    out = []
    for u, p in list(net.points.items()):
        if str(p.role) != "RAMP" or u not in road_of:
            continue
        src = [m for m, q in net.points.items() for l in q.links if l.target == u and str(l.type) == "AUX"]
        if not src or src[0] not in road_of:
            continue
        main = net.roads[road_of[src[0]]]
        ramp = net.roads[road_of[u]]
        # the mainline and every road joined to it end to end (a zone split cuts C1 into several roads)
        mains = [main]
        for r in net.roads.values():
            if r is main or not r.points:
                continue
            for e in (r.points[0], r.points[-1]):
                if any(math.dist(net.points[e].pos[:2], net.points[m].pos[:2]) < 0.5
                       for m in (main.points[0], main.points[-1])):
                    mains.append(r)
                    break
        polys = [[net.points[q].pos for q in r.points] for r in mains]
        need = _road_half(main) + _road_half(ramp) + GORE_MARGIN
        chain = list(ramp.points)
        if chain[-1] == u:
            chain.reverse()
        if chain[0] != u:
            continue

        def main_at(x, y):
            return min((_nearest(pl, x, y) for pl in polys), key=lambda t: t[0])
        # walk out from the mouth until the bands have parted
        clear, s = None, 0.0
        for a, b in zip(chain, chain[1:]):
            pa, pb = net.points[a].pos, net.points[b].pos
            L = math.dist(pa[:2], pb[:2])
            n = max(1, int(L / 2.0))
            for k in range(1, n + 1):
                t = k / n
                x, y = pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t
                if main_at(x, y)[0] >= need:
                    clear = (a, b, t, x, y)
                    break
            if clear:
                break
            s += L
        if clear is None:
            out.append("%s: never parts from %s (whole ramp held)" % (ramp.name, main.name))
            clear = (chain[-2], chain[-1], 1.0) + tuple(net.points[chain[-1]].pos[:2])
        a, b, t, x, y = clear
        if 0.05 < t < 0.95 and math.dist((x, y), net.points[b].pos[:2]) > 4.0:
            # insert where the bands part, in the ramp's CHAIN order (insert_after follows road.points)
            first, second = (a, b) if ramp.points.index(a) < ramp.points.index(b) else (b, a)
            nu = rg.insert_after(net, ramp, first, (x, y, main_at(x, y)[1]))
            road_of[nu] = ramp.name
            stop = nu
        else:
            stop = b if t >= 0.95 else a
        chain = list(ramp.points)
        if chain[-1] == u:
            chain.reverse()
        k_stop = chain.index(stop)
        moved = 0
        for q in chain[:k_stop + 1]:
            P = net.points[q]
            z = main_at(P.pos[0], P.pos[1])[1] if q != u else P.pos[2]
            if abs(z - P.pos[2]) > 1e-3:
                moved += 1
            P.pos = (P.pos[0], P.pos[1], round(z, 3))
            _GORE_HELD.add(q)
        # beyond: rejoin the ramp's OWN profile at the first station reachable from the held height at no more than
        # GORE_GRADE, with one even grade in between; every station past that one is left as its generator made it.
        # (Re-grading to the ramp road's far end instead flattened the Wangan, which is one long road at this stage
        # and was designed to climb over kichi_dori: 7.1 m of clearance became 1.3 m.)
        rest = chain[k_stop:]
        z0, cum, rejoin = net.points[stop].pos[2], 0.0, None
        for a_, b_ in zip(rest, rest[1:]):
            cum += math.dist(net.points[a_].pos[:2], net.points[b_].pos[:2])
            if cum > 1e-6 and abs(net.points[b_].pos[2] - z0) / cum <= GORE_GRADE:
                rejoin = (b_, cum)
                break
        if rejoin is not None:
            end, L = rejoin
            z1 = net.points[end].pos[2]
            c = 0.0
            for a_, b_ in zip(rest, rest[1:]):
                if b_ == end:
                    break
                c += math.dist(net.points[a_].pos[:2], net.points[b_].pos[:2])
                P = net.points[b_]
                P.pos = (P.pos[0], P.pos[1], round(z0 + (z1 - z0) * c / L, 3))
            out.append("%s: level with %s for %.0f m, then %.1f %% for %.0f m back onto its own profile"
                       % (ramp.name, main.name, s + t * math.dist(net.points[a].pos[:2], net.points[b].pos[:2]),
                          100.0 * abs(z1 - z0) / L, L))
            continue
        z0, d, prev, cone = net.points[stop].pos[2], 0.0, net.points[stop].pos, 0
        for q in chain[k_stop + 1:]:
            P = net.points[q]
            d += math.dist(prev[:2], P.pos[:2])
            prev = P.pos
            lo, hi = z0 - GORE_GRADE * d, z0 + GORE_GRADE * d
            z = min(max(P.pos[2], lo), hi)
            if abs(z - P.pos[2]) < 1e-3:
                break
            P.pos = (P.pos[0], P.pos[1], round(z, 3))
            cone += 1
        out.append("%s: level with %s for %.0f m (%d station(s) moved, %d in the cone)"
                   % (ramp.name, main.name, s + t * math.dist(net.points[a].pos[:2], net.points[b].pos[:2]),
                      moved, cone))
    return out


# ------------------------------------------------------------------------------------ smooth

def held_indices(nodes):
    """Which stations of this corridor may not move (see the module docstring)."""
    held = {0, len(nodes) - 1}
    deck = set()
    for i, ps in enumerate(nodes):
        if any(p.uid in _GORE_HELD for p in ps):          # level_gores: the ramp still shares its mainline's paving
            held.add(i)
        if any(str(p.role) == "INTERSECTION" for p in ps):
            held.add(i)
        if any(str(p.role) == "RAMP" for p in ps):         # the mouth and the far end of its gore span
            held.update((i, max(i - 1, 0), min(i + 1, len(nodes) - 1)))
        if any(p.pillar_skip for p in ps):                 # the flag holds from this station to the NEXT
            deck.update((i, min(i + 1, len(nodes) - 1)))
    # the deck, and the approach station either END of it: the structure's own boundary falls BETWEEN two
    # stations, so the first free station outside the deck still carries lane samples inside the span
    held |= deck | {j + d for j in deck for d in (-1, 1) if 0 <= j + d < len(nodes)}
    return held


def smooth_corridor(nodes, length=LENGTH):
    """Round this corridor's profile. Returns (moved stations, worst move, worst break left, its station index)."""
    chain = [ps[0] for ps in nodes]
    if len(chain) < 3:
        return 0, 0.0, 0.0, -1
    s = [0.0]
    for a, b in zip(chain, chain[1:]):
        s.append(s[-1] + math.dist(a.pos[:2], b.pos[:2]))
    z = [p.pos[2] for p in chain]
    held = sorted(held_indices(nodes))
    moved, worst = 0, 0.0
    out = list(z)
    for a, b in zip(held, held[1:]):                       # one stretch between two anchors at a time
        if b - a < 2:
            continue
        sm = moving_average(s[a:b + 1], z[a:b + 1], length)
        for k in range(1, b - a):
            out[a + k] = sm[k]
            if abs(out[a + k] - z[a + k]) > 1e-4:
                moved += 1
                worst = max(worst, abs(out[a + k] - z[a + k]))
    for ps, v in zip(nodes, out):
        for p in ps:
            p.pos = (p.pos[0], p.pos[1], round(v, 3))
    left = breaks(s, out)
    b, i = max(((v, i) for v, i, _, _ in left), default=(0.0, -1))
    return moved, worst, b, i


def cmd_smooth(argv):
    rec = argv[0]
    length = float(argv[argv.index("--length") + 1]) if "--length" in argv else LENGTH
    net = pm.load_network(rec)
    for line in level_gores(net):
        print("island_grades: gore " + line)
    runs = corridors(net)
    total, worst_move, rough = 0, ("", 0.0), []
    for name, nodes in runs:
        moved, worst, left, i = smooth_corridor(nodes, length)
        total += moved
        if worst > worst_move[1]:
            worst_move = (name, worst)
        if left > REPORT:
            rough.append((left, name, nodes[i][0].pos))
    rough.sort(reverse=True)
    print("island_grades: smoothed %d station(s) in %d corridor(s) over %d road(s); biggest move %.2f m (%s)"
          % (total, len(runs), len(net.roads), worst_move[1], worst_move[0]))
    if rough:
        print("island_grades: %d break(s) still over %.0f%% -- their spans are longer than the %.0f m curve, so the "
              "road needs stations there:" % (len(rough), REPORT * 100, length))
        for b, name, pos in rough[:12]:
            print("    %5.2f%%  %-26s (%.0f, %.0f, %.1f)" % (b * 100, name, pos[0], pos[1], pos[2]))
    if "--dry" not in argv:
        pm.save_network(net, rec)
    return rough


# ------------------------------------------------------------------------------------ rank

def cmd_rank(argv):
    window = float(argv[argv.index("--window") + 1] if "--window" in argv else WINDOW)
    top = int(argv[argv.index("--top") + 1] if "--top" in argv else 20)
    kinds = None if "--all-kinds" in argv else {"through"}
    files = []
    for a in argv:
        if not a.startswith("--") and not a.replace(".", "").isdigit():
            files += sorted(glob.glob(a))
    rows = []
    for f in files:
        for ln in json.load(open(f))["lanes"]:
            if kinds and ln.get("kind") not in kinds:
                continue
            pts = ln["points"]
            s = [0.0]
            for a, b in zip(pts, pts[1:]):
                s.append(s[-1] + math.dist((a[0], a[2]), (b[0], b[2])))
            for br, i, g0, g1 in breaks(s, [p[1] for p in pts], window):
                rows.append((br, ln["id"], pts[i], g0, g1))
    rows.sort(key=lambda r: -r[0])
    over = {t: sum(1 for r in rows if r[0] > t) for t in (0.02, 0.03, 0.04, 0.06)}
    print("island_grades: %d lane samples in %d piece(s); breaks over 2%% %d, 3%% %d, 4%% %d, 6%% %d"
          % (len(rows), len(files), over[0.02], over[0.03], over[0.04], over[0.06]))
    seen = set()
    for br, lid, p, g0, g1 in rows:
        road = lid.rsplit("_", 1)[0]
        if road in seen:
            continue
        seen.add(road)
        print("  %5.2f%%  %-30s (%8.0f,%6.1f,%8.0f)  %+.2f%% -> %+.2f%%"
              % (br * 100, lid, p[0], p[1], p[2], g0 * 100, g1 * 100))
        if len(seen) >= top:
            break
    return rows


def main(argv):
    if not argv or argv[0] not in ("smooth", "rank"):
        print(__doc__)
        sys.exit(2)
    (cmd_smooth if argv[0] == "smooth" else cmd_rank)(argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
