#!/usr/bin/env python3
"""check_mouth_sides.py -- every junction mouth stands OUTSIDE the carriageway of the roads running through its pad,
and its road leaves the pad AWAY from it (user, 2026-09-26, postal 9-14: jokamachi_dori ended 6.4 m past
rinkai_dori's centreline, so its cap, kerb and footway stood in the middle of rinkai_dori's carriageway -- and the
setback solve, which slides a mouth along its own road, cannot bring back a mouth that has crossed over).

    python3 tools/check_mouth_sides.py [<record>]          # exit 1 on any finding
    python3 tools/check_mouth_sides.py --fix <record>      # move each such mouth out (island_layout runs this)

A mouth is WRONG when
  * its road's first span heads back INTO the pad (towards the pad's centre): the road overshot the crossing, or
  * it is inside the carriageway (lanes + median / 2) of a road that runs THROUGH the pad (two mouths of one road
    name, zone splits and cuts included).
`--fix` moves it to the pad centre + its road's own outward direction x max(MOUTH, that half + MARGIN) and drops the
stations of its road left between it and the pad; `island_layout`'s setback solve then places it for real.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

MOUTH = 22.0          # the provisional mouth distance the generators use
MARGIN = 6.0          # past the through road's carriageway edge
OUT_MIN = 30.0        # a station at least this far from the pad centre gives a road's outward direction


def half(road):
    b = road.base
    return max(b.lanes_fwd, b.lanes_bwd) * b.lane_width + b.median_width / 2.0      # the CARRIAGEWAY's half


def deck_half(road):
    """The PAVED half: carriageway + the wider footway -- the half width of a mouth's CAP (its stop line, kerb and
    footway ends)."""
    b = road.base
    return half(road) + max(getattr(b, "left_walk_width", 0.0), getattr(b, "right_walk_width", 0.0))


HEAD_ON = math.cos(math.radians(145.0))   # two mouths leaving a pad this close to opposite ways are ONE through road


def base(n):
    return n.split("__")[0]


def _pads(net):
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    for cl in net.junction_cliques():
        ps = [net.points[u].pos for u in cl]
        c = (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))
        yield cl, c, road_of


def _outward(net, road, u, c):
    """The unit direction this mouth's road leaves the pad in: towards the first station of its chain (walked from
    the mouth) at least OUT_MIN from the centre, else the chain's far end."""
    ch = road.points if road.points[0] == u else road.points[::-1]
    for q in ch[1:]:
        p = net.points[q].pos
        if math.dist(p[:2], c) >= OUT_MIN:
            d = math.dist(p[:2], c)
            return ((p[0] - c[0]) / d, (p[1] - c[1]) / d), ch
    p = net.points[ch[-1]].pos
    d = math.dist(p[:2], c) or 1.0
    return ((p[0] - c[0]) / d, (p[1] - c[1]) / d), ch


CAP_GAP = 0.5         # m two mouths' caps keep between them


def _cap(net, road_of, u, c, at=None):
    """A mouth's cap as a segment, at `at` (default: where it is): square to its road's outward direction, the road's
    paved half each side."""
    r = net.roads[road_of[u]]
    (ox, oy), _ch = _outward(net, r, u, c)
    p = at or net.points[u].pos
    h = deck_half(r)
    return (p[0] - oy * h, p[1] + ox * h), (p[0] + oy * h, p[1] - ox * h)


def _seg_dist(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    if (cross(a, b, c) > 0) != (cross(a, b, d) > 0) and (cross(c, d, a) > 0) != (cross(c, d, b) > 0):
        return 0.0

    def pt(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / L2))
        return math.hypot(p[0] - q[0] - dx * t, p[1] - q[1] - dy * t)
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def _caps_touch(net, road_of, u, v, c, at=None):
    return _seg_dist(*_cap(net, road_of, u, c, at), *_cap(net, road_of, v, c)) < CAP_GAP


def _through(net, cl, c, road_of):
    """[([mouth, mouth], paved half)]: the roads running THROUGH this pad -- two mouths of one road name, or two
    otherwise unpaired mouths leaving it close to head-on (a road that changes its name at the pad)."""
    by = {}
    for u in cl:
        by.setdefault(base(road_of[u]), []).append(u)
    thru = [(ms, half(net.roads[road_of[ms[0]]])) for ms in by.values() if len(ms) == 2]
    # a through road may change its NAME at the pad (ring_kita__12__x1 -> kaigan_dori__8): any two otherwise
    # unpaired mouths leaving it close to head-on are one road through it
    paired = {q for ms, _h in thru for q in ms}
    free = [u for u in cl if u not in paired and len(net.roads[road_of[u]].points) >= 2]
    outs = {u: _outward(net, net.roads[road_of[u]], u, c)[0] for u in free}
    best = None
    for i, u in enumerate(free):
        for v in free[i + 1:]:
            dot = outs[u][0] * outs[v][0] + outs[u][1] * outs[v][1]
            if dot < HEAD_ON and (best is None or dot < best[0]):
                best = (dot, u, v)
    if best is not None:
        _d, u, v = best
        thru.append(([u, v], min(half(net.roads[road_of[u]]), half(net.roads[road_of[v]]))))
    return thru


def findings(net):
    """[(uid, road, why, needed distance from the pad centre, godot (x, z))]."""
    out = []
    for cl, c, road_of in _pads(net):
        thru = _through(net, cl, c, road_of)
        for u in cl:
            r = net.roads[road_of[u]]
            if len(r.points) < 2:
                continue
            p = net.points[u].pos
            nxt = net.points[r.points[1] if r.points[0] == u else r.points[-2]].pos
            need, why = 0.0, None
            # the road's first span heads back into the pad: it overshot the crossing
            if (nxt[0] - p[0]) * (p[0] - c[0]) + (nxt[1] - p[1]) * (p[1] - c[1]) < 0 \
                    and math.dist(p[:2], c) > 1.0:
                why, need = "its road heads back into the pad", MOUTH
            for ms, hw in thru:
                if u in ms:
                    continue
                a, b = net.points[ms[0]].pos, net.points[ms[1]].pos
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy)
                if L < 1.0:
                    continue
                sd = ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / L
                d = abs(sd)
                if d < hw:
                    why = why or "inside %s's carriageway (%.1f of %.1f m)" % (road_of[ms[0]], d, hw)
                    need = max(need, hw + MARGIN)
                # ...and on ITS OWN ROAD'S side of it: a lopsided pad (eki_minami_dori's mouth 11.7 m PAST the ring
                # road, while a quay street's mouths 63 m south dragged the pad centre past it) hides an overshoot from
                # the "heads back into the pad" test
                ch = r.points if r.points[0] == u else r.points[::-1]
                far = None
                for q in ch[1:]:
                    qp = net.points[q].pos
                    if abs(((qp[0] - a[0]) * dy - (qp[1] - a[1]) * dx) / L) >= OUT_MIN:
                        far = qp
                        break
                if far is not None:
                    sf = ((far[0] - a[0]) * dy - (far[1] - a[1]) * dx) / L
                    if sf * sd < 0:
                        why = why or "past %s's centreline (%.1f m on the far side)" % (road_of[ms[0]], d)
                        need = max(need, hw + MARGIN)
            # TWO MOUTHS' CAPS OVERLAP: a minor road's stop line laid across a through road's kerb and footway (rinkai_dori
            # into ring_kita's cap where the ring bends through the pad, probe_road_clear 2026-09-28). The minor mouth
            # moves out; of two minor mouths, the one nearer the centre.
            if not why and u not in {q for ms, _h in thru for q in ms}:
                for v in cl:
                    if v == u:
                        continue
                    if _caps_touch(net, road_of, u, v, c):
                        vmin = v not in {q for ms, _h in thru for q in ms}
                        if not vmin or math.dist(p[:2], c) <= math.dist(net.points[v].pos[:2], c):
                            why = "its cap overlaps %s's cap" % road_of[v]
                            need = max(need, math.dist(p[:2], c) + 4.0)
                            break
            if why:
                out.append((u, road_of[u], why, max(need, MOUTH), (round(p[0]), round(-p[1]))))
    return out


def fix(net, lock=False):
    """Move every wrong mouth out (see the module docstring); `lock` also locks its setback, so a later solve cannot
    slide it back in. Returns how many moved."""
    moved = 0
    for u, name, _why, need, _g in findings(net):
        if u not in net.points:
            continue
        r = net.roads[name]
        c = None
        for cl, cc, _ro in _pads(net):
            if u in cl:
                c = cc
                break
        if c is None:
            continue
        (ox, oy), ch = _outward(net, r, u, c)
        p = net.points[u]
        # out along its own road until it clears every through road's carriageway by MARGIN (the pad centre of a T is
        # not on the through road's centreline, so a distance from the centre alone can fall short)
        lines = []
        road_of = {q: n for n, rr in net.roads.items() for q in rr.points}
        for cl, cc, _ro in _pads(net):
            if u not in cl:
                continue
            # the side of each through line this road comes from: its first station OUT_MIN off that line
            for ms, hw in _through(net, cl, cc, road_of):
                if u in ms:
                    continue
                a, b = net.points[ms[0]].pos, net.points[ms[1]].pos
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1.0
                side = 0.0
                for q in ch[1:]:
                    qp = net.points[q].pos
                    sq = ((qp[0] - a[0]) * dy - (qp[1] - a[1]) * dx) / L
                    if abs(sq) >= OUT_MIN:
                        side = math.copysign(1.0, sq)
                        break
                lines.append((a, b, hw, side))
        others = [q for cl, _cc, _ro in _pads(net) if u in cl for q in cl if q != u]
        for _ in range(60):
            tx, ty = c[0] + ox * need, c[1] + oy * need
            ok = not any(_caps_touch(net, road_of, u, q, c, (tx, ty)) for q in others)
            for a, b, hw, side in lines:
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1.0
                sd = ((tx - a[0]) * dy - (ty - a[1]) * dx) / L
                if abs(sd) < hw + MARGIN or (side and sd * side < 0):
                    ok = False
            if ok:
                break
            need += 2.0
        target = (c[0] + ox * need, c[1] + oy * need)
        # the stations between the pad and the new mouth (or behind it) go; the end keeps its links
        for q in list(ch[1:-1]):
            qp = net.points[q].pos
            if (qp[0] - c[0]) * ox + (qp[1] - c[1]) * oy < need + 8.0:
                i = r.points.index(q)
                nb = [r.points[i - 1], r.points[i + 1]]
                net.remove_point(q)
                if q in r.points:
                    r.points.remove(q)
                net.link(nb[0], nb[1])
            else:
                break
        p.pos = (round(target[0], 3), round(target[1], 3), p.pos[2])
        if lock:
            p.setback_locked = True
        moved += 1
    return moved


def main(argv):
    if argv[:1] in (["--fix"], ["--fix-lock"]):
        path = argv[1] if len(argv) > 1 else rg.RECORD
        net = pm.load_network(path)
        n = fix(net, lock=argv[0] == "--fix-lock")
        pm.save_network(net, path)
        left = findings(net)
        print("check_mouth_sides: moved %d mouth(s) out of the road they meet; %d left" % (n, len(left)))
        for u, name, why, _n, g in left[:10]:
            print("check_mouth_sides:   LEFT %s at godot %s: %s" % (name, g, why))
        return 0
    path = argv[0] if argv else rg.RECORD
    bad = findings(pm.load_network(path))
    for u, name, why, _n, g in bad:
        print("check_mouth_sides: %s's mouth at godot %s: %s" % (name, g, why))
    print("check_mouth_sides: %d mouth(s) wrong -> %s" % (len(bad), "FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
