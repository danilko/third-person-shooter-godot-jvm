#!/usr/bin/env python3
"""island_suburb_kogai.py -- a ONE-SHOT edit of the arterials input (2026-10-03 night): kogai_michi meets wangan_dori
at the Suburb station's T, and the Suburb exit lands on wangan_dori.

    python3 tools/island_suburb_kogai.py [<arterials record>]

probe_road_clear found turn connectors running through two junction pads by Suburb station. kogai_michi left
wangan_dori at 34 deg (record (806, -422) -> (838, -467)), so the setback solve spread that T's mouths ~200 m apart
(x 730..937); the dike side road, running 20-40 m from wangan_dori, crossed kogai_michi 45 m further on, and that
junction -- where the Suburb exit landed -- sat INSIDE the first pad. eki_ginza_suburb, ending within REUSE of it,
became a fourth arm and made it worse. Moving the side road away from wangan_dori was tried (island_dike.SIDE_EXTRA
60 -> 25) and costs the exit 60 m of run: it then fell 12 m in 190 m (12 %).

So, three changes, of which this tool makes the first two:
* wangan_dori's junction at record x 775 loses its kogai_michi arm: its two mouths stay, a 2-arm pad that the Suburb exit
  joins at the expressway step as its south arm (island_plan.SB_JUNCTION) and eki_ginza_suburb at the street step as its
  north arm (island_core_streets: its last corner is the pad's centre);
* kogai_michi leaves wangan_dori at a new T cut at record (929, -492) -- where Suburb station's own street, ekimae_suburb
  (island_site_access), lands from the north, so that is a crossroads -- runs due south, and curves onto its old heading
  into the suburb loop's junction;
* the side road's piece by the suburb is not built (island_dike.SIDE_DROP).

Refuses to run twice (kogai_michi's first station is no longer on the x 775 pad).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
W2_END = "p_bd9ab77f"     # wangan_dori__2's last station: its mouth on the old kogai_michi T
W3_START = "p_eac9105d"   # wangan_dori__3's first station: the same T
K_MOUTH = "p_71ffdc82"    # kogai_michi's first station: its mouth on that T (removed)
K_END = "p_57fba595"      # kogai_michi's last station: its mouth on the suburb loop's junction (kept)
#: the 2-arm pad's mouths (the setback solve moves each along its own road); its centre is island_plan.SB_JUNCTION
MOUTHS = {W2_END: (761.0, -432.0), W3_START: (789.0, -441.0)}
T_AT = (929.0, -492.0)    # the new T (island_rail_layout.HUB_ACCESS["Suburb"]["at"], ekimae_suburb's)
MOUTH = 22.0              # island_streets.MOUTH
STEP = 40.0


def bezier(p0, p1, p2, p3, n=400):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def resample(poly, step):
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    n = max(1, int(round(cum[-1] / step)))
    out, j = [], 0
    for k in range(n + 1):
        s = cum[-1] * k / n
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    kr = net.roads["kogai_michi"]
    if kr.points[0] != K_MOUTH or kr.points[-1] != K_END:
        raise SystemExit("island_suburb_kogai: already applied, or kogai_michi is not the road this was written against")
    for u, (x, y) in MOUTHS.items():
        p = net.points[u]
        p.pos = (x, y, p.pos[2])
        p.setback_locked = False
    # kogai_michi's old stations go, all but its end on the loop's junction
    end = net.points[K_END]
    prev = net.points[kr.points[-2]]
    ex, ey = end.pos[0], end.pos[1]
    tx, ty = ex - prev.pos[0], ey - prev.pos[1]
    tl = math.hypot(tx, ty)
    tx, ty = tx / tl, ty / tl
    for u in list(kr.points[:-1]):
        net.remove_point(u)
    # the new T on wangan_dori, and kogai_michi off it: due south, then a cubic onto its old heading into the loop
    mouths = list(rg.cut_road(net, T_AT, "wangan_dori", MOUTH))
    m = (T_AT[0], T_AT[1] - MOUTH)
    a = (m[0], m[1] - 30.0)
    curve = [m] + bezier(a, (a[0], a[1] - 80.0), (ex - tx * 80.0, ey - ty * 80.0), (ex, ey))
    pts = resample(curve, STEP)[:-1]
    first = None
    before = None
    for i, (x, y) in enumerate(pts):
        p = net.add_station(kr, (x, y, 0.0))
        p.ground_z, p.has_ground_z = 0.0, True
        kr.points.remove(p.uid)
        kr.points.insert(i, p.uid)
        if before is not None:
            net.link(before.uid, p.uid)
        first = first or p
        before = p
    net.link(before.uid, end.uid)
    rg.make_junction(net, mouths + [first.uid])
    pm.save_network(net, path)
    print("island_suburb_kogai: kogai_michi off wangan_dori at (%.0f, %.0f), %d station(s) on to the loop; the x 775 "
          "pad keeps 2 arms for the Suburb exit -> %s" % (T_AT[0], T_AT[1], len(kr.points), path))


if __name__ == "__main__":
    main(sys.argv[1:])
