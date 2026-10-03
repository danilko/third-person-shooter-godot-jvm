#!/usr/bin/env python3
"""island_grades.py -- round every GRADE BREAK in the island's road profiles, and rank what is left
(PLAN.md 0.7 cause 3).

    python3 tools/island_grades.py smooth <record> [--length 80] [--dry]
    python3 tools/island_grades.py rank <lanekit.json>... [--window 12] [--top N] [--all-kinds]
    python3 tools/island_grades.py ramps <record> <lanekit.json>... [--check]

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

**A ramp is solved, not averaged** (`ramp_curves`, NEXT PASS step 1): every break on an expressway ramp -- the gore
exit included, which the average could never reach -- is a vertical curve of K >= RAMP_K, its grade <= 7 % to the
ground and <= 6 % between expressways, and `ramps` measures that on the exported lanes.

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
GORE_MIN_SPAN = 6.0   # m: the parting station is never inserted closer than this to the station after it
_GORE_HELD = set()    # uids `level_gores` fixed: anchors for `held_indices`
_PAIR_HELD = set()    # uids `pair_held` held beside a parallel expressway road (a subset of _GORE_HELD)
_RAIL = None


def _near_level_crossing(pos):
    """Is this station within island_dike.LX_HOLD of an at-grade rail sample? Such a station is held: the dike pins
    a ramp's to the rail's height there, and a smoothed road would climb across the tracks again."""
    global _RAIL
    if _RAIL is None:
        import island_dike
        _RAIL = (island_dike.LX_HOLD, island_dike._rail_grade_samples())
    h, rail = _RAIL
    return any(abs(q[0] - pos[0]) < h and abs(q[1] - pos[1]) < h and math.hypot(q[0] - pos[0], q[1] - pos[1]) < h
               for q in rail)


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


GORE_VERTICAL = 2.0    # m: a ramp this far above or below its mainline's surface is on its own level, not in a gore


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
                md, mz = main_at(x, y)
                # parted SIDEWAYS, or VERTICALLY: a ramp that runs beside its mainline and then crosses over (or under)
                # it is on another level there, and holding it at the mainline's height flattened the Wangan's T1
                # into the airport spur it flies over (27.9 m -> 21.2 m, a flat crossing, probe_road_clear)
                if md >= need or abs(pa[2] + (pb[2] - pa[2]) * t - mz) > GORE_VERTICAL:
                    clear = (a, b, t if md >= need else 0.0, x, y)   # parted vertically: hold only up to `a`
                    break
            if clear:
                break
            s += L
        if clear is None:
            out.append("%s: never parts from %s (whole ramp held)" % (ramp.name, main.name))
            clear = (chain[-2], chain[-1], 1.0) + tuple(net.points[chain[-1]].pos[:2])
        a, b, t, x, y = clear
        # a parting station within GORE_MIN_SPAN of the next one is not inserted: that one is held instead, or the
        # climb out of the gore begins over a 4.5 m span no vertical curve fits in (E2 / W2: K 1.5, the shipped
        # lanekits, 2026-10-02)
        if 0.05 < t < 0.95 and math.dist((x, y), net.points[b].pos[:2]) > GORE_MIN_SPAN:
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


# ------------------------------------------------------------------------------------ ramp vertical curves

RAMP_K = 6.0          # m per %: every ramp grade break is a vertical curve at least this flat (NEXT PASS step 1)
RAMP_K_GROUND = 6.5   # ...for a ramp to the ground, whose grade is the tighter budget (7 % with both curves)
RAMP_K_SOLVE = 9.0    # what `ramp_curves` aims for, so the exported Hermite between stations still clears RAMP_K
RAMP_GROUND_GRADE = 0.07   # a ramp to or from the ground at 40 km/h (道路構造令: 7 %)
RAMP_JCT_GRADE = 0.06      # an expressway-to-expressway ramp
CROSS_DZ = 3.0        # m: a road this far above or below the ramp, across its band, is one it crosses (else a gore)
CROSS_OVERLAP = 0.5   # m: the two paved bands overlap by at least this much in plan
CROSS_MIN = 5.7       # m: the least surface-over-surface the solve keeps at a crossing (roadkit_interchange 5.5)
CROSS_WANT = 5.9      # m: ...and the most it asks for (no more than the generator's own profile had)
FLOOR_WEIGHT = 1e3    # the one-sided spring holding a ramp's profile on its dike floor, against the curvature
RAMP_STEP = 2.0       # m: the dense profile `ramp_curves` solves on
RAMP_STATION = 6.0   # m: the longest span left inside a vertical curve (the Path3D follows stations)
RAMP_MOUTH_CLEAR = 12.0   # m: no station is inserted this close to a junction or ramp mouth (station_crowds_mouth)


def _is_ramp(name, road):
    return str(name).startswith("shuto_") and str(road.road_class) == "ramp"


def _local_k(s, f, i, h=6.0):
    """K (m per %) at dense sample i: h either side over the change in grade there."""
    a = next((j for j in range(i, -1, -1) if s[i] - s[j] >= h), None)
    b = next((j for j in range(i, len(s)) if s[j] - s[i] >= h), None)
    if a is None or b is None:
        return 1e9
    g0 = (f[i] - f[a]) / (s[i] - s[a])
    g1 = (f[b] - f[i]) / (s[b] - s[i])
    d = abs(g1 - g0) * 100.0
    return 1e9 if d < 1e-6 else (s[b] - s[a]) / d


def ramp_curves(net, k_target=None):
    """EVERY RAMP GRADE BREAK IS A VERTICAL CURVE (PLAN.md NEXT PASS step 1).

    The corridor average (`smooth_corridor`) holds a ramp's anchors -- its gore (level with the mainline until the bands
    part, `level_gores`), a lane-split pair, a junction mouth -- and averages only BETWEEN them, so the break AT an
    anchor is never rounded: measured on the shipped lanekits, E2 and W2 climbed out of their gores at K 1.5 (a 10 %
    kink in 4.5 m, the inserted parting station beside the generator's own). Here each ramp's resolved centreline is
    sampled every RAMP_STEP m and its profile solved as a SMOOTHING SPLINE: every sample of a held span (both ends
    held) is FIXED, so the free profile leaves each anchor tangentially; the rest minimises curvature against staying
    near its own heights, the curvature weight raised until every break is at least `k_target` flat. Then each free
    station takes the solved height and stations are inserted every RAMP_STATION m where the curve bends, because the
    exported Path3D only follows stations. Every station of a ramp is then held for the corridor average.

    Returns report lines."""
    import numpy as np
    import point_profile as pp
    import road_points as rp
    import island_roadgen as rg
    import island_dike
    out = []
    road_of = {q: n for n, r in net.roads.items() for q in r.points}
    # the dike's clearance over the ring, as a FLOOR under the solved profile: `island_dike.py raise` runs after this
    # pass and lifts what is still short with a linear cone, which is a kink (Y1, E1: K 3.5 / 4.4 on the lanekits)
    needs = island_dike.crossing_needs(net, every=True)
    # ...and every OTHER road it flies over or passes under, as a floor or a ceiling: the solve lowers a crest and lifts
    # a sag, and the first gate run had E2 and W2 at 4.1 / 4.3 m over C1 (roadkit_interchange.crossings, 5.5 m)
    seg_grid = {}
    for on, orr in net.roads.items():
        pts = [net.points[q].pos for q in orr.points if q in net.points]
        h_ = _road_half(orr)
        for a_, b_ in zip(pts, pts[1:]):
            for gx in range(int(min(a_[0], b_[0]) // 40) - 1, int(max(a_[0], b_[0]) // 40) + 2):
                for gy in range(int(min(a_[1], b_[1]) // 40) - 1, int(max(a_[1], b_[1]) // 40) + 2):
                    seg_grid.setdefault((gx, gy), []).append((on, a_, b_, h_))
    for name in sorted(net.roads):
        road = net.roads[name]
        if not _is_ramp(name, road) or len(road.points) < 3:
            continue
        uids = list(road.points)
        # a held station on a held span takes that span's CHORD slope as its tangent before anything is sampled: an
        # AUTO tangent reaches across to the free station beyond, and the Hermite then bends up inside the gore (T4:
        # level for 6 m, then 4.5 % at the gore's end, K 4.4 with nothing the solve could move)
        hs = [i for i, u in enumerate(uids)
              if (u in _GORE_HELD and u not in _PAIR_HELD) or str(net.points[u].role) in ("RAMP", "INTERSECTION")]
        for i in hs:
            P = net.points[uids[i]]
            if not 0 < i < len(uids) - 1 or str(P.role) != "SEGMENT":
                continue
            j = i - 1 if i - 1 in hs else (i + 1 if i + 1 in hs else None)
            if j is None:
                continue
            Q = net.points[uids[j]]
            d = math.dist(P.pos[:2], Q.pos[:2])
            if d < 1e-6:
                continue
            g = (P.pos[2] - Q.pos[2]) / d if j < i else (Q.pos[2] - P.pos[2]) / d
            a_, b_ = net.points[uids[i - 1]].pos, net.points[uids[i + 1]].pos
            plan = (b_[0] - a_[0], b_[1] - a_[1])
            if P.tangent_mode == pm.MANUAL and P.tangent is not None and math.hypot(*P.tangent[:2]) > 1e-9:
                plan = P.tangent[:2]
            m = math.hypot(*plan)
            P.tangent_mode = pm.MANUAL
            P.tangent = (plan[0] / m, plan[1] / m, g)
        ground = any(str(net.points[u].role) == "INTERSECTION" for u in (uids[0], uids[-1]))
        kt = k_target or (RAMP_K_GROUND if ground else RAMP_K_SOLVE)
        rpts = [net.resolved(u) for u in uids]
        sts = pp.stations(rpts, False, end_axes=pp.run_end_axes(net, rpts))
        smp = rp.resample(sts, False, step=RAMP_STEP)
        if len(smp) < 8:
            continue
        s = [q.s for q in smp]
        z = [q.pos[2] for q in smp]
        st_i = {q.at_station: k for k, q in enumerate(smp) if q.at_station is not None}
        n_st = len(uids)
        held = set()
        for i, u in enumerate(uids):
            P = net.points[u]
            if ((u in _GORE_HELD and u not in _PAIR_HELD) or str(P.role) in ("RAMP", "INTERSECTION") or P.pillar_skip
                    or _near_level_crossing(P.pos) or i in (0, n_st - 1)):
                held.add(i)
            if P.pillar_skip:
                held.add(min(i + 1, n_st - 1))
        fixed = {}
        for i in held:
            fixed[st_i[i]] = z[st_i[i]]
        for i in range(n_st - 1):
            if i in held and i + 1 in held:
                for k in range(st_i[i], st_i[i + 1] + 1):
                    fixed[k] = z[k]
        # each END continues something: a joint continues the joined road's grade, a junction mouth arrives level on
        # its pad; fixed samples past the end make the free profile meet that tangentially
        ext_s, ext_z = [], []
        for side in (0, 1):
            u = uids[0] if side == 0 else uids[-1]
            k0 = 0 if side == 0 else len(s) - 1
            g = None
            P = net.points[u]
            if str(P.role) == "INTERSECTION":
                g = 0.0
            else:
                for l in P.links:
                    if str(l.type) != "SEGMENT" or l.target not in road_of or road_of[l.target] == name:
                        continue
                    o = net.roads[road_of[l.target]]
                    j = o.points.index(l.target)
                    nb = o.points[j + 1] if j + 1 < len(o.points) else (o.points[j - 1] if j else None)
                    if nb is None:
                        continue
                    a_, b_ = net.points[l.target].pos, net.points[nb].pos
                    d = math.dist(a_[:2], b_[:2])
                    if d > 1e-6:
                        g = (b_[2] - a_[2]) / d           # the joined road's grade, going AWAY from this ramp
                    break
            if g is None:
                continue
            for m in range(1, 6):
                d = m * RAMP_STEP
                if side == 0:
                    ext_s.insert(0, s[0] - d)
                    ext_z.insert(0, z[0] + g * d)
                else:
                    ext_s.append(s[-1] + d)
                    ext_z.append(z[-1] + g * d)
        n0 = sum(1 for v in ext_s if v < 0.0)
        S = ext_s[:n0] + s + ext_s[n0:]
        Z = ext_z[:n0] + z + ext_z[n0:]
        F = {k + n0: v for k, v in fixed.items()}
        for k in range(n0):
            F[k] = Z[k]
        for k in range(n0 + len(s), len(S)):
            F[k] = Z[k]
        N = len(S)
        if all(k in F for k in range(N)):
            continue
        h = RAMP_STEP
        rows = []                                   # second differences over every interior sample
        for k in range(1, N - 1):
            rows.append((k - 1, k, k + 1, S[k] - S[k - 1], S[k + 1] - S[k]))

        floor = {}
        if name in needs:
            _ch, ns, need = needs[name]
            # the need's arclength is along the station chord; map it through the stations onto this curve's s
            st_s = [s[st_i[i]] for i in range(n_st)]

            def to_s(v):
                for i in range(n_st - 1):
                    if ns[i] <= v <= ns[i + 1]:
                        f_ = (v - ns[i]) / max(1e-9, ns[i + 1] - ns[i])
                        return st_s[i] + (st_s[i + 1] - st_s[i]) * f_
                return st_s[-1]
            for sn, zmin in need:
                c = to_s(sn)
                for k in range(len(s)):
                    if abs(s[k] - c) <= RAMP_STEP * 2.0:
                        floor[k + n0] = max(floor.get(k + n0, -1e9), zmin)

        ceil = {}
        rh = _road_half(road)
        # the roads joined at this ramp's ends, and the other halves of the same split (its siblings at a joint): they
        # run beside it at their own heights there, and a station polyline with a symmetric half width cannot say
        # whether a ONE-WAY band (its lanes laid to one side of its stations) is over another one or beside it
        kin = set()
        for e in (uids[0], uids[-1]):
            tg = {l.target for l in net.points[e].links if str(l.type) == "SEGMENT"}
            for t_ in tg:
                kin.add(road_of.get(t_))
                kin.update(road_of.get(l.target) for l in net.points[t_].links if l.target in road_of)
        for k in range(len(s)):
            x, y = smp[k].pos[0], smp[k].pos[1]
            best = {}
            for on, a_, b_, h_ in seg_grid.get((int(x // 40), int(y // 40)), ()):
                if on == name or on in kin:
                    continue
                dx, dy = b_[0] - a_[0], b_[1] - a_[1]
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - a_[0]) * dx + (y - a_[1]) * dy) / L2))
                d = math.hypot(a_[0] + dx * t - x, a_[1] + dy * t - y)
                if d > h_ + rh - CROSS_OVERLAP:
                    continue                                  # beside it, not over it: the two paved bands do not meet
                zo = a_[2] + (b_[2] - a_[2]) * t
                dz = z[k] - zo
                if abs(dz) <= CROSS_DZ:
                    continue                                  # beside it at its level: a gore, a joint, a pair
                # never asked for more than the profile had, never less than the rule's margin
                need = max(CROSS_MIN, min(abs(dz), CROSS_WANT))
                if dz > 0:
                    floor[k + n0] = max(floor.get(k + n0, -1e9), zo + need)
                else:
                    ceil[k + n0] = min(ceil.get(k + n0, 1e9), zo - need)

        def solve(w, Fx, act=()):
            fr = [k for k in range(N) if k not in Fx]
            ix = {k: j for j, k in enumerate(fr)}
            A = np.zeros((len(fr), len(fr)))
            b = np.zeros(len(fr))
            lam = 1.0 / w                          # the data term's weight against the curvature's
            for j, k in enumerate(fr):
                A[j, j] += lam
                b[j] += lam * Z[k]
            for k, v in dict(act).items():         # a bound this sample would cross: a stiff one-sided spring
                if k in ix:
                    A[ix[k], ix[k]] += FLOOR_WEIGHT
                    b[ix[k]] += FLOOR_WEIGHT * v
            for a_, c_, e_, h0, h1 in rows:        # w * (D2 f)^2, D2 in m/m^2 scaled to the sample step
                coef = {a_: 2.0 / (h0 * (h0 + h1)), c_: -2.0 / (h0 * h1), e_: 2.0 / (h1 * (h0 + h1))}
                coef = {k: v * h * h for k, v in coef.items()}
                fk = {k: v for k, v in coef.items() if k in ix}
                const = sum(v * Fx[k] for k, v in coef.items() if k not in ix)
                for k1, v1 in fk.items():
                    b[ix[k1]] -= v1 * const
                    for k2, v2 in fk.items():
                        A[ix[k1], ix[k2]] += v1 * v2
            x = np.linalg.solve(A, b) if fr else []
            f = [Fx.get(k, Z[k]) for k in range(N)]
            for j, k in enumerate(fr):
                f[k] = float(x[j])
            return f

        def solve_floored(w):
            # f >= floor as a one-sided penalty: active where the solution dips under, released where it rises off
            act = {}
            f_ = solve(w, F)
            for _ in range(25):
                # a floor's spring only ever PUSHES UP, a ceiling's DOWN: one the solution has left is released
                nxt = {k: v for k, v in floor.items() if k not in F and (f_[k] < v - 0.001 or (k in act and f_[k] < v))}
                nxt.update({k: v for k, v in ceil.items() if k not in F and (f_[k] > v + 0.001 or (k in act and f_[k] > v))})
                if nxt == act:
                    break
                act = nxt
                f_ = solve(w, F, act)
            return f_

        # K is judged where the profile is FREE: a held span is its mainline's (a gore) and no weight changes it
        # (and where a held span MEETS the free profile: that is the break this pass exists for)
        near_free = set()
        for k in range(N):
            if k not in F:
                near_free.update(range(max(3, k - 4), min(N - 3, k + 5)))
        judged = sorted(near_free)
        w, f = 1.0, None
        for _ in range(16):
            f = solve_floored(w)
            kmin = min((_local_k(S, f, k) for k in judged), default=1e9)
            if kmin >= kt:
                break
            w *= 3.0
        fs = f[n0:n0 + len(s)]
        kmin = min(_local_k(s, fs, k) for k in range(len(s)))

        def slope_at(k, side=0):
            # side -1 / +1: one-sided, along the HELD span on that side (a held station keeps its gore's slope)
            a, b = max(0, k - (1 if side <= 0 else 0)), min(len(s) - 1, k + (1 if side >= 0 else 0))
            return (fs[b] - fs[a]) / max(1e-9, s[b] - s[a])

        def face(P, k, plan, side=0):
            # the station's TANGENT carries the solved slope: with a chord (AUTO) tangent the exported Hermite bends
            # its own way between stations, and a break the solve rounded to K 8 read K 5.4 on the lanekit (W1)
            if P.tangent_mode == pm.MANUAL and P.tangent is not None and math.hypot(*P.tangent[:2]) > 1e-9:
                plan = P.tangent[:2]
            m = math.hypot(*plan)
            if m < 1e-9:
                return
            P.tangent_mode = pm.MANUAL
            P.tangent = (plan[0] / m, plan[1] / m, slope_at(k, side))

        # write: every free station takes the solved height, and every interior non-mouth station its slope
        for i, u in enumerate(uids):
            P = net.points[u]
            if i not in held:
                P.pos = (P.pos[0], P.pos[1], round(fs[st_i[i]], 3))
            if 0 < i < n_st - 1 and str(P.role) == "SEGMENT":
                if i in held and (i - 1 in held or i + 1 in held):
                    continue                       # faced on its held span's chord, above
                face(P, st_i[i], smp[st_i[i]].tangent[:2])
        # insert where the curve bends inside a long span (never in a held span, never near a mouth)
        mouths = [net.points[u].pos for u in uids if str(net.points[u].role) in ("RAMP", "INTERSECTION")]
        added = 0
        for i in range(n_st - 1):
            if i in held and i + 1 in held:
                continue
            k0, k1 = st_i[i], st_i[i + 1]
            span = s[k1] - s[k0]
            if span <= RAMP_STATION:
                continue
            pa, pb = net.points[uids[i]], net.points[uids[i + 1]]
            if (pa.lanes_fwd, pa.lanes_bwd) != (pb.lanes_fwd, pb.lanes_bwd) or rg._tapers(pa, pb):
                continue                           # a lane taper: its length is the span the author put there
            bend = min(_local_k(s, fs, k) for k in range(k0, k1 + 1))
            if bend > 60.0:
                continue
            m = int(math.ceil(span / RAMP_STATION))
            prev = uids[i]
            for j in range(1, m):
                target = s[k0] + span * j / m
                k = min(range(k0, k1 + 1), key=lambda q: abs(s[q] - target))
                pos = smp[k].pos
                if any(math.dist(pos[:2], mp[:2]) < RAMP_MOUTH_CLEAR for mp in mouths):
                    continue
                prev = rg.insert_after(net, road, prev, (pos[0], pos[1], round(fs[k], 3)))
                face(net.points[prev], k, smp[k].tangent[:2])
                added += 1
        for u in road.points:
            _GORE_HELD.add(u)
        kk = min(range(len(s)), key=lambda q: _local_k(s, fs, q))
        near = min(range(n_st), key=lambda i: abs(s[st_i[i]] - s[kk]))
        out.append("%s: K %.1f at s %.0f (station %d/%d %s%s), w %.0f, %d station(s) added"
                   % (name, kmin, s[kk], near, n_st, net.points[uids[near]].role, " held" if near in held else "",
                      w, added))
    return out


# ------------------------------------------------------------------------------------ smooth

def held_indices(nodes):
    """Which stations of this corridor may not move (see the module docstring)."""
    held = {0, len(nodes) - 1}
    deck = set()
    for i, ps in enumerate(nodes):
        if any(p.uid in _GORE_HELD for p in ps):          # level_gores: the ramp still shares its mainline's paving
            held.add(i)
        if any(_near_level_crossing(p.pos) for p in ps):   # a 踏切: the road is level at the rail (island_dike)
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


PAIR_DZ = 0.3          # m: two expressway roads running side by side at one height (a lane-split pair)


def pair_held(net):
    """TWO RAMPS SIDE BY SIDE AT ONE HEIGHT STAY AT ONE HEIGHT. A lane split (the Wangan's T4 + T2) peels two ramps off
    together at one level; the 80 m average then lifted one of them by the climb that starts just past the pair
    (T2 0.8 m over T4, 4.3 m apart: its edge a wall in T4's lane, probe_road_clear). Every station of an expressway
    road (shuto_*) whose bands overlap another one's within PAIR_DZ is held. Returns the number held."""
    roads = [r for n, r in net.roads.items() if str(n).startswith("shuto_") and len(r.points) > 1]
    polys = {r.name: [net.points[q].pos for q in r.points] for r in roads}
    # a ramp and the mainline it leaves or joins are level_gores' business, not a pair: holding the MAINLINE there
    # pinned the Wangan's crest at Y3's gore and left Y3 0.3 m under its paving (probe_road_clear)
    road_of = {q: str(n) for n, r in net.roads.items() for q in r.points}
    gore = set()
    for u, p in net.points.items():
        for l in p.links:
            if str(l.type) == "AUX" and u in road_of and l.target in road_of:
                gore.add(frozenset((road_of[u], road_of[l.target])))
    n = 0
    for r in roads:
        for q in r.points:
            P = net.points[q].pos
            for o in roads:
                if o is r or frozenset((str(r.name), str(o.name))) in gore:
                    continue
                d, z = _nearest(polys[o.name], P[0], P[1])
                if d < _road_half(r) + _road_half(o) + GORE_MARGIN and abs(z - P[2]) < PAIR_DZ:
                    if q not in _GORE_HELD:
                        _GORE_HELD.add(q)
                        _PAIR_HELD.add(q)
                        n += 1
                    break
    return n


def cmd_smooth(argv):
    rec = argv[0]
    length = float(argv[argv.index("--length") + 1]) if "--length" in argv else LENGTH
    net = pm.load_network(rec)
    for line in level_gores(net):
        print("island_grades: gore " + line)
    print("island_grades: %d station(s) held beside a parallel expressway road at one height" % pair_held(net))
    for line in ramp_curves(net):
        print("island_grades: ramp " + line)
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


RAMP_GORE_GAP = 5.5   # m: a ramp lane sample this close to a mainline lane is still in its gore (the mainline's profile)


def ramp_report(record, lanekits):
    """[(road, kind, length m, max grade, min K, where)] for every expressway ramp, measured on the EXPORTED lanes
    (lane 0 of each through lane), never on the stations `ramp_curves` wrote: the Path3D is what a car drives.

    `kind` is "ground" when either end of the ramp's chain is a junction mouth, else "jct". The grade is the steepest
    over 10 m; K is the flattest break over +-6 m, skipping samples within RAMP_GORE_GAP of an expressway mainline's
    lane (there the ramp IS the mainline's profile, and a mainline's breaks are the corridor average's business)."""
    net = pm.load_network(record)
    kind = {}
    for name, r in net.roads.items():
        if _is_ramp(name, r) and r.points:
            ends = (net.points[r.points[0]], net.points[r.points[-1]])
            kind[name] = "ground" if any(str(p.role) == "INTERSECTION" for p in ends) else "jct"
    lanes, mains = [], []
    for f in lanekits:
        for ln in json.load(open(f))["lanes"]:
            if ln.get("kind") != "through":
                continue
            if ln.get("road_name") in kind and ln.get("lane_index") == 0:
                lanes.append(ln)
            elif ln.get("road_class") == "expressway":
                mains += [(p[0], p[2]) for p in ln["points"]]
    grid = {}
    for x, y in mains:
        grid.setdefault((int(x // 20), int(y // 20)), []).append((x, y))

    def in_gore(x, y):
        gx, gy = int(x // 20), int(y // 20)
        return any(math.hypot(qx - x, qy - y) < RAMP_GORE_GAP
                   for i in (-1, 0, 1) for j in (-1, 0, 1) for qx, qy in grid.get((gx + i, gy + j), ()))
    out = []
    for ln in lanes:
        pts = ln["points"]
        s = [0.0]
        for a, b in zip(pts, pts[1:]):
            s.append(s[-1] + math.dist((a[0], a[2]), (b[0], b[2])))
        if s[-1] < 30.0:
            continue
        xs = [i * 2.0 for i in range(int(s[-1] / 2.0) + 1)]
        zz, pp_ = [], []
        j = 1
        for x in xs:
            while j < len(s) - 1 and s[j] < x:
                j += 1
            t = (x - s[j - 1]) / max(1e-9, s[j] - s[j - 1])
            a, b = pts[j - 1], pts[j]
            zz.append(a[1] + (b[1] - a[1]) * t)
            pp_.append((a[0] + (b[0] - a[0]) * t, a[2] + (b[2] - a[2]) * t))
        g, gi = max(((abs(zz[i + 5] - zz[i]) / 10.0, i) for i in range(len(xs) - 5)), default=(0.0, 0))
        gwhere = (round(pp_[gi][0]), round(zz[gi], 1), round(pp_[gi][1]), round(xs[gi]))
        k, where = 1e9, None
        for i in range(3, len(xs) - 3):
            if in_gore(*pp_[i]):
                continue
            v = _local_k(xs, zz, i)
            if v < k:
                k, where = v, (round(pp_[i][0]), round(zz[i], 1), round(pp_[i][1]))
        out.append((ln["road_name"], kind[ln["road_name"]], s[-1], g, k, where, gwhere))
    return sorted(out)


def cmd_ramps(argv):
    files = [a for a in argv if not a.startswith("--")]
    rows = ramp_report(files[0], [f for a in files[1:] for f in sorted(glob.glob(a))])
    bad = 0
    for name, kind, L, g, k, where, gwhere in rows:
        lim = RAMP_GROUND_GRADE if kind == "ground" else RAMP_JCT_GRADE
        fail = g > lim + 1e-4 or k < RAMP_K
        bad += fail
        print("  %s %-18s %-6s L %4.0f  grade %4.1f%% (<= %.0f%%) at %s  K %5.1f (>= %.0f) at %s"
              % ("FAIL" if fail else "ok  ", name, kind, L, g * 100, lim * 100, gwhere, min(k, 999.0), RAMP_K,
                 where))
    print("island_grades: %d ramp lane(s), %d over the ramp rule" % (len(rows), bad))
    if "--check" in argv and bad:
        sys.exit(1)
    return rows


def main(argv):
    cmds = {"smooth": cmd_smooth, "rank": cmd_rank, "ramps": cmd_ramps}
    if not argv or argv[0] not in cmds:
        print(__doc__)
        sys.exit(2)
    cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
