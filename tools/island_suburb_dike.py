#!/usr/bin/env python3
"""island_suburb_dike.py -- a ONE-SHOT edit of the arterials input (user, 2026-10-03): THE SUBURB MOVES BEHIND THE DIKE.

    python3 tools/island_suburb_dike.py [<arterials record>]

The coastal ring is the dike (island_dike.py). Round the south-east resort it ran straight along Godot z 672
(`ring_kita__7`) and diagonally up to the ring_kita__5 / wangan_dori pad (`ring_kita__6`), and the suburb's homes, the
hotels and the water resort stood OUTSIDE it on a loop whose legs were dike ramps. Asked whether that is normal: in
Japan the homes stand behind the 防潮堤 and only beach leisure is outside it. So:

* the land reaches further south (island_reshape.SUBURB_FILL, with its own bank and an 80 m dry beach);
* `ring_kita__6` now swings SOUTH round the suburb: from the pad down the east side (Godot x 1185, clear of the Main
  line's viaduct at x 1250), along the south (z 1085, the sea toe ~45 m short of the new shore) and up the west side
  (x 945) to a JOINT with `ring_kita__7` at x 895, 45 m east of the Suburb entrance's T (expressway SB_ON_T, x 850);
* the old stretch (x 954 .. the pad) is gone, so `kogai_michi` no longer meets the dike: it stays at grade and runs on
  south as the suburb's spine into `kogai_loop`, a block-street loop inside (legs x 1013 / 1117, bottom z 984), the
  water resort inside it and 32 m of lots between every leg and the dike's land-side toe, the two resort hotels in the 68 m band along the bottom.
  NOTHING inside touches the dike, so nothing is ramped onto its crest (a 14.7 m crest needs 180 m of 5 % ramp).

Refuses to run twice (`kogai_loop` already in the record).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
PAD_MOUTH = "p_f78da859"                 # ring_kita__6's first station: its mouth on the ring_kita__5 / wangan_dori pad
OLD_R7 = ("p_f04f7dd5", "p_c945af94")    # ring_kita__7's stations at x 954 (the kogai_michi pad) and x 886
R7_NEXT = "p_619e2194"                   # ring_kita__7's station at x 834, which the joint links to
KOGAI_END = "p_bfbb99ab"                 # kogai_michi's end station on the old pad (x 966)
#: Godot (x, z) corners of the new dike stretch after the pad mouth, and the fillet radius at each
DIKE = [(1185.0, 660.0), (1185.0, 1085.0), (945.0, 1085.0), (945.0, 672.0), (860.0, 672.0)]
DIKE_R = [30.0, 60.0, 60.0, 50.0]
JOINT_X = 895.0
#: the suburb loop (Godot): the junction with kogai_michi, and the loop's corners from its first mouth to its last
#: the loop's west and east legs and its bottom; its top (and the junction, at its north-west corner) is where
#: kogai_michi's own line reaches the west leg, so kogai_michi runs on STRAIGHT into the junction (a kink there read as
#: a wiggle in a short street, user 2026-10-03)
LOOP_W, LOOP_E, LOOP_S = 1013.0, 1117.0, 984.0
MOUTH = 20.0
SPACING = 40.0
DIKE_SPACING = 30.0


def rec(p):
    return (p[0], -p[1])


def resample(poly, step):
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    n = max(1, int(math.ceil(cum[-1] / step)))
    out = []
    j = 0
    for k in range(n + 1):
        s = cum[-1] * k / n
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


def chain(net, road, pts, start=None):
    prev = start
    for q in pts:
        p = net.add_station(road, (q[0], q[1], 0.0))
        p.ground_z, p.has_ground_z = 0.0, True
        if prev is not None:
            net.link(prev.uid, p.uid)
        prev = p
    return prev


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    if "kogai_loop" in net.roads:
        raise SystemExit("island_suburb_dike: already applied (kogai_loop is in %s)" % path)
    r6, r7 = net.roads["ring_kita__6"], net.roads["ring_kita__7"]
    if r6.points[0] != PAD_MOUTH or r7.points[:2] != list(OLD_R7):
        raise SystemExit("island_suburb_dike: ring_kita__6/__7 are not the stations this was written against")
    # 1. the old stretch goes
    for u in list(r6.points[1:]) + list(OLD_R7):
        net.remove_point(u)
    # 2. the new ring_kita__6: pad mouth -> round the suburb -> the joint at JOINT_X
    a = net.points[PAD_MOUTH]
    corners = [(a.pos[0], -a.pos[1])] + DIKE
    # arcs keep their own stations (every 10 m) and straights get the planner's spacing: resampling the whole line
    # evenly put chords across every corner and the sweep bent between them
    plan = rg.rounded_polygon(corners, [0.0] + DIKE_R + [0.0], closed=False, arc_step=10.0)
    i = next(i for i in range(len(plan) // 2, len(plan))
             if abs(plan[i][1] - 672.0) < 0.5 and plan[i][0] <= JOINT_X + 0.5)
    plan = plan[:i] + [(JOINT_X, 672.0)]
    pts = [rec(q) for q in plan][1:]
    end6 = chain(net, r6, pts, start=a)
    # 3. ring_kita__7 starts at the joint
    j7 = pm.PointData(pos=(JOINT_X, -672.0, 0.0))
    for n in pm.DELTA_FIELDS:
        setattr(j7, n, getattr(r7.base, n))
    j7.lane_width = r7.base.lane_width
    j7.ground_z, j7.has_ground_z = 0.0, True
    net.add_point(j7)
    r7.points.insert(0, j7.uid)
    net.link(j7.uid, R7_NEXT)
    net.link(end6.uid, j7.uid)                              # the JOINT
    for u in (end6.uid, j7.uid):
        net.points[u].role = pm.SEGMENT
        rg.freeze(net, u, (-1.0, 0.0))
    # 4. kogai_michi runs on to the suburb loop's junction
    k = net.points[KOGAI_END]
    k.role = pm.SEGMENT
    k.traffic_light = False
    kr = net.roads["kogai_michi"]
    kx, ky = k.pos[0], -k.pos[1]
    q = net.points[kr.points[-2]]
    dx, dy = kx - q.pos[0], ky - (-q.pos[1])
    L = math.hypot(dx, dy)
    dx, dy = dx / L, dy / L
    jz = ky + dy * (LOOP_W - kx) / dx
    loop_j = (LOOP_W, jz)
    mouth_k = (LOOP_W - dx * MOUTH, jz - dy * MOUTH)
    LOOP = [(LOOP_W, jz + MOUTH), (LOOP_W, LOOP_S), (LOOP_E, LOOP_S), (LOOP_E, jz), (LOOP_W + MOUTH, jz)]
    mk = chain(net, kr, [rec(mouth_k)], start=k)
    # 5. the loop
    loop = net.add_road(pm.RoadData("kogai_loop", pm.PointData(uid=""), ()))
    import point_presets as pr
    pr.apply_preset(net, "kogai_loop", "block")
    # (user, 2026-10-03: "the resort road is not straight, the sidewalk pokes"): stations every 40 m along the whole
    # loop put a chord across each 18 m corner, and the kerb swept between them wobbled. Corners now carry their own
    # arc stations (every 6 m), straights a station every <= 60 m.
    lplan = rg.rounded_polygon(LOOP, 18.0, closed=False, arc_step=6.0)
    del loop_j
    first = None
    prev = None
    for q in lplan:
        p = net.add_station(loop, (q[0], -q[1], 0.0))
        p.ground_z, p.has_ground_z = 0.0, True
        if prev is not None:
            net.link(prev.uid, p.uid)
        first = first or p
        prev = p
    rg.make_junction(net, [mk.uid, first.uid, prev.uid], signal=False)
    pm.save_network(net, path)
    print("island_suburb_dike: ring_kita__6 %d station(s) round the suburb, joint at x %.0f; kogai_michi on to the "
          "loop's junction; kogai_loop %d station(s) -> %s" % (len(r6.points), JOINT_X, len(loop.points), path))


if __name__ == "__main__":
    main(sys.argv[1:])
