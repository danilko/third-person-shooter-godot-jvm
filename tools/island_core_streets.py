#!/usr/bin/env python3
"""island_core_streets.py -- AUTHORED streets the grid planner cannot make (PLAN.md tier-B batch, "the core's empty
blocks").

    python3 tools/island_core_streets.py <record> [--check]

The band between C1's north side and `nishi_dori` (record y 570-790, x 275-975) held two empty blocks, because
nothing the grid planner (`island_streets`) draws can live there:
* C1 above it is ELEVATED, so a line there meets only ONE ground road (the planner drops a line with one crossing);
* the diamond's two descent ramps (`shuto_d_bwd_off` / `_on`) land diagonally across the band at naka_hondori's
  junction (y ~665), so a line through the middle passes under a ramp at ~4.5 m, and a junction on naka_hondori
  between that one and nishi_dori's would be ~40 m from both;
* a street directly UNDER C1 would drop every C1 pier over it (`point_mesh.pier_on_road`).

So each block gets ONE L-shaped street, the 裏通り behind the expressway: a T on the trunk road beside it, along the
ramp's north side (clear of it by >= 10 m of kerb), then a T north onto nishi_dori, well away from nishi_dori's own
junctions. Both ends are Ts CUT into their roads (`island_roadgen.cut_road`, the street planner's own way of landing
one); the corner is rounded; the street drapes on the ground on the `block` preset. The setback solve later places
every mouth.

It runs in `island_layout` BEFORE `island_streets`, so the planner's lines can end on these.

Idempotent: a street already in the record is left alone. `--check` exits 1 if one is missing.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

MOUTH = 26.0          # a new mouth's first distance from its junction's centre (setback re-solves it)
SPACING = 40.0        # stations along the straights
CORNER_R = 18.0       # the corner fillet (a block street's kerb return; a car turns it at ~20 km/h)

#: name, the road the street leaves (T 1), the corners (record x, y; the first and last lie ON a road), the road it
#: ends on (T 2). The first corner is on the first road, the last on the second.
STREETS = [
    # WEST block (nishi_hondori x 275 .. naka_hondori x 600): the ramp shuto_d_bwd_off runs (305, 611) -> (583, 665)
    # at 11 -> 0 m; y 680 keeps 12 m of kerb from it at x 450, and nishi_hondori's own junction with nishi_dori (~738)
    # is 58 m away. The north leg lands on nishi_dori between its junctions at x 295 and x 580.
    dict(name="c1_ura_nishi", first="nishi_hondori", corners=[(275.0, 680.0), (450.0, 680.0), (450.0, 757.0)],
         last="nishi_dori"),
    # EAST block (naka_hondori x 600 .. higashi_hondori x 975): the ramp shuto_d_bwd_on runs (618, 666) -> (812, 590),
    # so y 690 is 55 m clear of it at x 730; higashi_hondori's junction with nishi_dori (~772) is 82 m away, and the
    # north leg lands on nishi_dori 110 m from its x 620 junction.
    dict(name="c1_ura_higashi", first="higashi_hondori", corners=[(975.0, 690.0), (730.0, 690.0), (730.0, 780.0)],
         last="nishi_dori"),
    # THE FARM'S FRAME (user, 2026-09-26: "re-add the farm land setup"). Since the ring became the dike (12 m crest)
    # the farm grid had nothing to end on: its north-south roads were drawn nishi_dori -> the coast ring, which is no
    # longer a crossing (a farm road would need a 240 m ramp onto the crest), and the dike's 側道 is only built between
    # two at-grade crossings -- there are none along the farm's shore. Every farm line then met ONE road and the
    # planner dropped them all: no farm roads, and (the seaward flood reaching every unroaded cell) no paddy either.
    # This U is the farm's frame, planned BEFORE island_streets so the farm rows (island_plan's `farm*` regions) end
    # on its legs: west leg x 510 from a T on nishi_dori, the 農道 along the dike's inland foot (45 m inside the ring's
    # straight reach, clear of its 28-32 m corridor; the north-west corner is squared off rather than following the
    # coast's diagonal, which made a 140 deg hairpin -- the triangle beyond it stays field), then the STATION-FRONT road x 1080 (駅前通り, 30 m west of the
    # Main line at x 1110) back south to the nishi_dori x teibo_sokudo junction, which it makes a crossroads.
    # (2026-09-28) the station-front leg moved x 1080 -> 1045: the kit stations' buildings and car parks reach x 1057
    # at Farm and Residential North (IslandRailReserve.json), and x 1080 ran through both (probe_road_clear). It now
    # meets nishi_dori in a T west of Residential North's building instead of at the teibo_sokudo junction.
    dict(name="nodo_waku", first="nishi_dori", corners=[(510.0, 762.0), (510.0, 1590.0), (1045.0, 1417.0),
                                                        (1045.0, 820.0), (1046.0, 762.0)],
         last="nishi_dori"),
    # THE INDUSTRY'S FRAME (2026-09-26, the rail batch): the industry grid (island_plan `industry`, 200 m plots) had
    # two anchors, chuo_dori on the west and the coast ring on the east -- and the ring is the 12 m dike now, no
    # crossing, while the Harbour line (x 185) and its Industry station take the east edge. Every line met ONE road and
    # the whole district was dropped (0 streets). This L is the frame the grid hangs off: a T on chuo_dori at y -800
    # (130 m from its junctions at -902 and -632), east to x 110 (75 m west of the track, so the Industry station's
    # car park at x ~150 fronts it), then north to a T on wangan_dori (144 m from its x 254 junction).
    dict(name="kojo_waku", first="chuo_dori", corners=[(-135.0, -800.0), (110.0, -800.0), (110.0, -429.0)],
         last="wangan_dori"),
    # THE SUBURB LOOP (PLAN.md, the plan's `kogai_michi` "suburb loop"): the suburb's land lies OUTSIDE the dike (the
    # waterfront between the ring and the south-east shore, y -700..-880), and nothing reached it -- kogai_michi ends
    # on the ring. A U off the ring's two junctions either side of it: down x 886, along y -800, up x 1160; the dike
    # stage ramps both legs up onto the crest (island_dike raise, 5 %). The legs are ramps, so the grid planner's rows
    # cannot T onto them: the suburb's buildings front the loop itself (its 270 m bottom leg, both sides).
    # The EAST leg bends south-east before it meets the ring (the (1215, -705) corner, 2026-09-29): straight north it
    # left the pad 40 deg from ring_kita__6's own arm, its mouth solved 46 m out, and the kerb corner between the two
    # lay across ring_kita__6_F1 (probe_road_clear). From the south-east the arm is ~70 deg from ring_kita__6 and ~125
    # from ring_kita__5; the elevated Main line (x 1250) passes over it 35 m on.
    dict(name="kogai_loop", first="ring_kita", corners=[(886.0, -672.0), (886.0, -800.0), (1160.0, -800.0),
                                                       (1215.0, -705.0), (1161.0, -610.0)],
         last="ring_kita"),
    # THE CENTRAL STATION'S 駅前ロータリー (user, 2026-09-28: the Tokyo Station placeholder is retired -- Central is the
    # kit's elevated hub -- and its forecourt gets "parking entrance / bus stop etc like a Japanese central hub"). A
    # ONE-WAY loop, two lanes, clockwise (Japan keeps left, so a rotary turns clockwise): in from ekimae_dori at x 690,
    # north, east along y 150 in front of the station, south, out at x 880. A one-way road lays its lanes on the LEFT
    # of its stations, so the stations are the loop's INNER edge and the 4 m outer footway is the kerb the buses and
    # taxis stop at (the bus berths on the station side, the taxi rank on the east leg). The inner island and the
    # plaza, car park and koban round it are the CentralForecourt composite (island_sites.forecourt_site).
    dict(name="ekimae_rotary", first="ekimae_dori", corners=[(690.0, 100.0), (690.0, 150.0), (880.0, 150.0),
                                                            (880.0, 100.0)],
         last="ekimae_dori", one_way=True, lanes=2, walks=(4.0, 2.0), spacing=10.0),
    # (north_e has no authored street: the strip between the Main line and the ring is 120 m wide and every road
    # into it lands on the ring's dike ramp -- an L off nishi_dori at x 1170 made a 43 % pad on the ramp.)
]
REUSE = 15.0          # an end within this of an existing junction mouth of its road JOINS that junction (a new arm)


def _mouth_head(net, members, toward):
    """The street's first station: MOUTH from the junction centre, toward `toward`."""
    cx = sum(net.points[u].pos[0] for u in members) / len(members)
    cy = sum(net.points[u].pos[1] for u in members) / len(members)
    dx, dy = toward[0] - cx, toward[1] - cy
    L = math.hypot(dx, dy)
    return (cx + dx / L * MOUTH, cy + dy / L * MOUTH)


def _resample(poly, step):
    """Stations along a polyline every <= `step` m, keeping its first and last point."""
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    n = max(1, int(math.ceil(cum[-1] / step)))
    out = []
    for k in range(n + 1):
        s = cum[-1] * k / n
        j = max(i for i in range(len(cum) - 1) if cum[i] <= s) if s < cum[-1] else len(cum) - 2
        f = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


def _tee(net, prefix, at):
    """The junction an end lands on: the clique of an existing junction mouth of a `prefix*` road within REUSE of
    `at` (the street is a new arm of it), else a T CUT into the road there (`cut_road`)."""
    best = None
    for n, r in net.roads.items():
        if not n.startswith(prefix):
            continue
        for u in r.points:
            p = net.points[u]
            d = math.hypot(p.pos[0] - at[0], p.pos[1] - at[1])
            if d <= REUSE and any(l.type == pm.LINK_JUNCTION for l in p.links) and (best is None or d < best[0]):
                best = (d, u)
    if best:
        u = best[1]
        return [u] + [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION]
    return list(cut_road(net, at, prefix, MOUTH))


def add(net, s, ground):
    c = s["corners"]
    t1 = _tee(net, s["first"], c[0])
    t2 = _tee(net, s["last"], c[-1])
    head = _mouth_head(net, t1, c[1])
    tail = _mouth_head(net, t2, c[-2])
    plan = rg.rounded_polygon([head] + list(c[1:-1]) + [tail], CORNER_R, closed=False)
    # the fillet samples its arc every ARC_STEP (30 m): resample the straights too, so a 90 deg corner is not a chord
    step = s.get("spacing", SPACING)
    pts = _resample(plan, step) if len(plan) < 4 else _resample(rg.densify(plan, 4.0), step)
    pts3 = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
    road = chain_road(net, s["name"], pts3, preset="block", one_way=s.get("one_way", False))
    if s.get("one_way"):
        # a ONE-WAY street (the station rotary): all its lanes run with the chain, on every station (a station's lane
        # counts are its own, not the base's), and its outer (left) footway is the kerb a bus stops at
        road.base.lanes_fwd, road.base.lanes_bwd = s.get("lanes", 2), 0
        road.base.left_walk_width, road.base.right_walk_width = s.get("walks", (4.0, 2.0))
        for u in road.points:
            net.points[u].lanes_fwd, net.points[u].lanes_bwd = s.get("lanes", 2), 0
    make_junction(net, t1 + [road.points[0]])
    make_junction(net, t2 + [road.points[-1]])
    for u in road.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True
    return road


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    missing = [s for s in STREETS if s["name"] not in net.roads]
    if "--check" in argv:
        print("island_core_streets: %d of %d authored streets present" % (len(STREETS) - len(missing), len(STREETS)))
        return 1 if missing else 0
    if not missing:
        print("island_core_streets: every authored street already present")
        return 0
    ground = rg.Ground()
    for s in missing:
        road = add(net, s, ground)
        L = sum(math.dist(net.points[a].pos[:2], net.points[b].pos[:2]) for a, b in zip(road.points, road.points[1:]))
        print("island_core_streets: %s: %d stations, %.0f m, T on %s and on %s"
              % (s["name"], len(road.points), L, s["first"], s["last"]))
    pm.save_network(net, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
