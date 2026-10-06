#!/usr/bin/env python3
"""island_local_fixes.py -- hand-directed corrections to the DERIVED road record, each one a place the generators get
wrong and a user marked on the map. A layout step (island_layout.derive, after island_site_access), so they are made
again on every derive; each finds its place by GEOMETRY (never by a generated name, which a layout change renumbers)
and does nothing, saying so, when the place is not there.

    python3 tools/island_local_fixes.py <record> [--late]

* industry_corner (user, 2026-10-06, postal 13-15..13-17, a picture marked in red): the dike's side road
  (teibo_sokudo_1) came down from the north-east, crossed kojo_waku's north-south leg at a shallow angle, ran 20-30 m
  WEST of it for 110 m and crossed kojo_waku's east-west leg 31 m short of its corner -- two parallel roads, a 5-arm
  pad (the station access joined it too) and a jog at each end. Now:
    - the parallel piece goes (the buildings move into the ground it held);
    - the lower junction moves onto kojo_waku's corner, so the north-south leg runs STRAIGHT through it, its east-west
      leg a T from the west;
    - the side road south of it is laid again: straight on south, one even curve (CURVE_R), straight to where it ended
      (it went south, turned 90 deg in one span and then wiggled up and down 17 m).
  The station access has its own T on kojo_waku (island_rail_layout.HUB_ACCESS["Industry"]), so no pad has 5 arms.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

# industry_corner (record frame)
IC_PAD = (95.0, -800.0)         # the lower junction is the pad whose centre is within IC_REACH of this
IC_REACH = 30.0
IC_MOUTH = 14.0                 # initial mouth distance from the corner (the setback solves the real one)
IC_TURN_Y = -880.0              # the curve's corner on the straight south
CURVE_R = 45.0
ARC_STEP = 8.0


def _centre(net, comp):
    xs = [net.points[u].pos for u in comp]
    return (sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs))


def _arm(net, road, u):
    pts = list(road.points)
    return pts if pts[0] == u else pts[::-1]


def _heading(net, road, u):
    a = _arm(net, road, u)
    p, q = net.points[a[0]].pos, net.points[a[1]].pos
    L = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
    return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def _clear_after(net, road, u, gap=10.0):
    """A mouth moved along its arm: the stations it passed or now crowds (within `gap`) go."""
    a = _arm(net, road, u)
    m = net.points[u].pos
    k = 1
    while k < len(a) - 1 and math.hypot(net.points[a[k]].pos[0] - m[0], net.points[a[k]].pos[1] - m[1]) < gap:
        nxt = a[k + 1]
        net.unlink(u, a[k])
        net.remove_point(a[k])
        net.link(u, nxt)
        k += 1


def _relay(net, road, pts, ground):
    """Replace a road's interior stations by `pts` [(x, y)] (its two ends are kept, their links too)."""
    first, last = road.points[0], road.points[-1]
    for u in list(road.points[1:-1]):
        net.remove_point(u)
    net.unlink(first, last)
    before = net.points[first]
    for i, (x, y) in enumerate(pts):
        z = ground.z(x, y) or 0.0
        p = net.add_station(road, (x, y, max(0.0, z)))
        p.ground_z, p.has_ground_z = z, True
        road.points.remove(p.uid)
        road.points.insert(1 + i, p.uid)
        net.link(before.uid, p.uid)
        before = p
    net.link(before.uid, last)


def industry_corner(net, ground):
    road_of = {u: r for r in net.roads.values() for u in r.points}
    pad = None
    for comp in net.junction_cliques():
        if math.dist(_centre(net, comp), IC_PAD) < IC_REACH:
            pad = comp
    if pad is None:
        return "industry_corner: no pad near (%.0f, %.0f) -- nothing done" % IC_PAD
    arms = {}
    for u in pad:
        h = _heading(net, road_of[u], u)
        side = max((("N", h[1]), ("S", -h[1]), ("E", h[0]), ("W", -h[0])), key=lambda t: t[1])[0]
        arms.setdefault(side, []).append(u)
    # 1. the parallel piece: the arm leaving north that is the dike's side road
    dropped = 0
    for u in arms.get("N", []):
        r = road_of[u]
        if r.name.startswith("teibo_sokudo"):
            for q in list(r.points):
                net.remove_point(q)
            del net.roads[r.name]
            dropped += 1
    if not all(arms.get(k) and len(arms[k]) == 1 for k in ("W", "E", "S")):
        return "industry_corner: the pad's arms are %s, not one each W/E/S -- nothing more done" % (
            {k: len(v) for k, v in arms.items()},)
    w, e, s = arms["W"][0], arms["E"][0], arms["S"][0]
    road_of = {u: r for r in net.roads.values() for u in r.points}
    # 2. the east arm turns north at the corner: its corner station becomes the north arm's mouth
    er = road_of[e]
    a = _arm(net, er, e)
    corner = net.points[a[1]].pos
    h2 = (net.points[a[2]].pos[0] - corner[0], net.points[a[2]].pos[1] - corner[1])
    if h2[1] < 0.7 * math.hypot(*h2):
        return "industry_corner: the east arm does not turn north at its second station -- nothing more done"
    cx, cy = corner[0], corner[1]
    net.unlink(a[0], a[1])
    net.remove_point(a[1])
    net.link(a[0], a[2])
    # the next station may be the next junction's mouth (the station access's T): never closer to it than to the corner
    reach = IC_MOUTH if len(a) > 3 else min(IC_MOUTH, 0.5 * math.dist(corner[:2], net.points[a[2]].pos[:2]))
    net.points[e].pos = (cx, cy + reach, net.points[e].pos[2])
    _clear_after(net, er, e)
    # 3. the west arm's mouth up to the corner
    wp = net.points[w].pos
    net.points[w].pos = (cx - IC_MOUTH, cy, wp[2])
    _clear_after(net, road_of[w], w)
    # 4. the south arm: straight on south, one curve, straight to its far end
    sr = road_of[s]
    if sr.points[0] != s:
        sr.points.reverse()
    end = net.points[sr.points[-1]].pos
    net.points[s].pos = (cx, cy - IC_MOUTH, net.points[s].pos[2])
    poly = rg.rounded_polygon([(cx, cy - IC_MOUTH), (cx, IC_TURN_Y), (end[0], end[1])], CURVE_R, closed=False,
                              arc_step=ARC_STEP)
    _relay(net, sr, poly[1:-1], ground)
    return ("industry_corner: %d parallel piece(s) removed; the junction moved onto the corner (%.0f, %.0f); %s laid "
            "again, %d station(s), a %.0f m curve" % (dropped, cx, cy, sr.name, len(poly) - 2, CURVE_R))


# port_crossing (record frame): the port road (kichi_dori__2, squared 2026-10-05) comes up x -165 into the dike ring's
# crossing with chuo_dori, so the pad is a crossroads whose north arm (chuo_dori) and ENE arm (the ring) are 71 deg
# apart with mouths 20-24 m from its centre: the corner's footway reached 7 m into chuo_dori's southbound lane
# (probe_road_clear, 2026-10-06) and the pad ring folded 5.6 m past its centroid. Those two mouths go out to PC_REACH
# along their own roads and are LOCKED, so the setback keeps them (fold 1.1 m, the ring's own 35 deg bend).
PC_PAD = (-170.0, -1103.0)
PC_REACH = 30.0


def port_crossing(net):
    road_of = {u: r for r in net.roads.values() for u in r.points}
    for comp in net.junction_cliques():
        c = _centre(net, comp)
        if math.dist(c, PC_PAD) > 30.0 or len(comp) != 4:
            continue
        moved = []
        for u in comp:
            r = road_of[u]
            if not (r.name.startswith("chuo_dori") or r.name.startswith("ring_kita__9")):
                continue
            a = _arm(net, r, u)
            m, q = net.points[u].pos, net.points[a[1]].pos
            d0, L = math.dist(m[:2], c), math.dist(m[:2], q[:2])
            if d0 >= PC_REACH or L < 1.0:
                continue
            t = min(0.8, (PC_REACH - d0) / L)
            net.points[u].pos = (m[0] + (q[0] - m[0]) * t, m[1] + (q[1] - m[1]) * t, m[2] + (q[2] - m[2]) * t)
            net.points[u].setback_locked = True
            moved.append("%s %.1f -> %.1f m" % (r.name, d0, math.dist(net.points[u].pos[:2], c)))
        return "port_crossing: %s" % (", ".join(moved) or "nothing to move")
    return "port_crossing: no 4-arm pad near (%.0f, %.0f) -- nothing done" % PC_PAD


def main(argv):
    path = argv[0]
    net = pm.load_network(path)
    if "--late" in argv:
        # after the alignment, before the setback: a mouth placed here is locked and kept by the solve
        print("island_local_fixes: " + port_crossing(net))
    else:
        ground = rg.Ground()
        print("island_local_fixes: " + industry_corner(net, ground))
    pm.save_network(net, path)


if __name__ == "__main__":
    main(sys.argv[1:])
