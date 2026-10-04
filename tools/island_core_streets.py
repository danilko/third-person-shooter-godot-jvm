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
import re
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
    # THE BLOCKS BEHIND THE BUILDINGS (user, 2026-10-03: "reduce large vacancy behind buildings, each building facing a
    # street, add streets if needed"). Measured with a deep-vacancy scan (flat land > 48 m from any street a building
    # can front): these three were the largest built-up pockets the grid planner cannot reach (one road only, or a
    # junction too near). nishi_ura: the foothill triangle north of rinkai_dori, west of nishi_dori's bend -- a U from a
    # T on rinkai_dori up the west side, across the foot and down onto nishi_dori.
    # (its T on nishi_dori is at x -790: at x -720 the turn into it ran past the Blue line's 踏切 unit at x -723)
    dict(name="nishi_ura", first="rinkai_dori", corners=[(-1060.0, -313.6), (-1060.0, -210.0), (-900.0, -125.0),
                                                        (-790.0, -125.0), (-790.0, -204.6)], last="nishi_dori"),
    # yamasoi: the strip between nishi_dori__3 and the massif's foot, 70 m inside nishi_dori, parallel to it, from a T
    # on nishi_dori__3 (clear of the clinic and fire branch plots there) to a T on nishi_dori__4 north of the touge's
    dict(name="yamasoi", first="nishi_dori", corners=[(-300.0, -124.3), (-331.0, -61.0), (-250.0, 110.0),
                                                     (-235.0, 190.0), (-149.0, 180.0)], last="nishi_dori"),
    # (kojo_minami, a U off kojo_waku into the industry south of it, went 2026-10-04: the dike's side road runs through
    # that block and gives it frontage, and the U crossed it twice with no junction)
    # (kojo_ura, the `after` street east of the old campus plot, went 2026-10-03: the campus is its real 260 x 220 now
    # and fills that block. The `after` mechanism stays for the next street that must hang off the grid.)
    # (THE SUBURB LOOP that stood here -- a U outside the dike whose legs were ramps onto the crest -- went 2026-10-03:
    # the dike swings south round the suburb now, and `kogai_loop` is in the arterials input, inside it, at grade;
    # tools/island_suburb_dike.py)
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
    # VACANT BLOCKS (user, 2026-10-03: "add more streets around vacant blocks"): frames the grid planner's lines hang
    # off (island_plan `koba_w`, `city_n`).
    # Inside C1's north half the two blocks between yamate_dori (y ~295) and the viaduct had no street: C1 above is
    # elevated, so a line there met one road. An east-west street at y 465 across the three trunk roads, in two halves
    # meeting naka_hondori at one crossroads (the second half REUSEs the first's junction); 68 m south of the diamond's
    # junction on naka_hondori (y ~533), 160 m north of yamate_dori's.
    dict(name="c1_naka_yoko", first="nishi_hondori", corners=[(275.0, 465.0), (600.0, 465.0)], last="naka_hondori"),
    dict(name="c1_naka_yoko_e", first="naka_hondori", corners=[(600.0, 465.0), (975.0, 465.0)],
         last="higashi_hondori"),
    # the west industrial block (x -1050..-500 between nishi_cho_413 y -413 and the dike, the Blue line down x -800,
    # Residential station y -419..-603, Light Industry station y -883..): ~20 ha with no street. When this runs only
    # kichi_dori exists there (nishi_cho_413 is the planner's, the dike's side road comes later), so the frame is a U
    # off kichi_dori: west along y -655 across the track (52 m south of Residential's platform), down x -960, and back
    # along y -783 -- the legs in line with the koba rows east of kichi_dori. The koba_w lines hang off it.
    dict(name="koba_waku_w", first="kichi_dori", corners=[(-500.0, -655.0), (-960.0, -655.0), (-960.0, -783.0),
                                                         (-500.0, -783.0)], last="kichi_dori"),
    # THE STATION 商店街 (the second review, 2026-10-03): one local shopping street off each housing station's front,
    # a short block street the shops line both sides of (island_buildings.STREET_MIXES keys the shop-house mix on the
    # "eki_ginza" name). Castle Town's is its 参道, jokamachi_sando (island_site_access), keyed the same way.
    # Suburb: west of the station (x 834..926), from rinkai_dori south to wangan_dori at the station's front
    dict(name="eki_ginza_suburb", first="rinkai_dori", corners=[(775.0, -270.0), (775.0, -440.0)],   # the crossroads' centre, the Suburb exit's (island_suburb_kogai.py)
         last="wangan_dori"),        # (ekimae_suburb, the station's own street, is built later -- island_site_access)
    # Residential North: west off the farm frame's leg (nodo_waku x 1045) level with the station, then south to nishi_dori
    dict(name="eki_ginza_res_north", first="nodo_waku", corners=[(1045.0, 850.0), (960.0, 850.0), (960.0, 779.0)],
         last="nishi_dori"),
    # (Residential's is the planner's x -650 line east of the station, koba_machi_w_650 -- an authored leg here sat 50 m
    # from the koba x -650 line and took the whole koba grid down with it)
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
            if not any(l.type == pm.LINK_JUNCTION for l in p.links):
                continue
            # the mouth itself, or its junction's CENTRE (a street ending where another authored street's T already
            # cut the road -- c1_naka_yoko's two halves -- finds the mouths MOUTH m out, past REUSE)
            mem = [u] + [l.target for l in p.links if l.type == pm.LINK_JUNCTION]
            cx = sum(net.points[m].pos[0] for m in mem) / len(mem)
            cy = sum(net.points[m].pos[1] for m in mem) / len(mem)
            d = min(math.hypot(p.pos[0] - at[0], p.pos[1] - at[1]), math.hypot(cx - at[0], cy - at[1]))
            if d <= REUSE and (best is None or d < best[0]):
                best = (d, u)
    if best:
        u = best[1]
        return [u] + [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION]
    return list(cut_road(net, at, prefix, MOUTH))


def _family(name):
    """A GENERATED road's number is not stable: island_dike numbers its side roads in build order, so a piece that is
    not built shifts every one after it, and a frozen record naming `teibo_sokudo_2` (IslandBlockSplits.json) would
    find another road or none. Such a name is matched as its family prefix -- the nearest side road at the corner."""
    m = re.match(r"^(teibo_sokudo_)\d+$", name)
    return m.group(1) if m else name


#: a street crossing another ground road this close to either of its own ends is the end's business (its T), not a
#: crossing to cut; and a crossing whose two roads stand further apart in height than AT_GRADE passes over or under
CROSS_END_CLEAR = 2.0 * MOUTH
AT_GRADE = 4.0
#: kojo_waku is cut at its crossings with the dike's side road (2026-10-04); the Industry station's access
#: (island_rail_layout HUB_ACCESS) joins that crossroads rather than cutting its own T 14 m from it.
CUT_CROSSINGS = True


def _arc(poly):
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def _slice(poly, cum, s0, s1):
    """The polyline between arc lengths s0 and s1."""
    def at(s):
        k = max(j for j in range(len(cum) - 1) if cum[j] <= s) if s < cum[-1] else len(cum) - 2
        f = (s - cum[k]) / max(1e-9, cum[k + 1] - cum[k])
        return (poly[k][0] + (poly[k + 1][0] - poly[k][0]) * f, poly[k][1] + (poly[k + 1][1] - poly[k][1]) * f)
    return [at(s0)] + [poly[j] for j in range(len(poly)) if s0 < cum[j] < s1] + [at(s1)]


def crossings(net, poly, ground, skip=()):
    """[(arc length along `poly`, (x, y), road name)] -- every at-grade ground road the planned street crosses between
    its ends (2026-10-04: `kojo_waku` was laid across the dike's side road, built earlier in the layout, and crossed it
    with no junction -- the corner kerbs of a nearby pad then stood on the side road's carriageway)."""
    cum = _arc(poly)
    out = []
    for name, r in net.roads.items():
        if name in skip or r.road_class == "rail" or name.startswith("shuto_"):
            continue
        ch = [net.points[u] for u in r.points if u in net.points]
        for a, b in zip(ch, ch[1:]):
            if not a.has_link(b.uid, pm.LINK_SEGMENT):
                continue
            for k in range(len(poly) - 1):
                p, q = poly[k], poly[k + 1]
                d = (q[0] - p[0]) * (b.pos[1] - a.pos[1]) - (q[1] - p[1]) * (b.pos[0] - a.pos[0])
                if abs(d) < 1e-9:
                    continue
                t = ((a.pos[0] - p[0]) * (b.pos[1] - a.pos[1]) - (a.pos[1] - p[1]) * (b.pos[0] - a.pos[0])) / d
                u = ((a.pos[0] - p[0]) * (q[1] - p[1]) - (a.pos[1] - p[1]) * (q[0] - p[0])) / d
                if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
                    continue
                x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                zr = a.pos[2] + (b.pos[2] - a.pos[2]) * u
                if abs(zr - max(0.0, ground.z(x, y) or 0.0)) > AT_GRADE:
                    continue
                sarc = cum[k] + (cum[k + 1] - cum[k]) * t
                if CROSS_END_CLEAR < sarc < cum[-1] - CROSS_END_CLEAR:
                    out.append((sarc, (x, y), name))
    return sorted(out)


def add(net, s, ground):
    c = s["corners"]
    t1 = _tee(net, _family(s["first"]), c[0])
    t2 = _tee(net, _family(s["last"]), c[-1])
    head = _mouth_head(net, t1, c[1])
    tail = _mouth_head(net, t2, c[-2])
    plan = rg.rounded_polygon([head] + list(c[1:-1]) + [tail], CORNER_R, closed=False)
    # A CROSSING IS A JUNCTION: the street is cut at every at-grade road it crosses between its ends (each piece ends
    # MOUTH short of the crossing), and the crossed road is cut there too, the two pieces and its two halves one pad
    dense = rg.densify(plan, 4.0) if len(plan) >= 4 else plan
    cum = _arc(dense)
    cross = crossings(net, dense, ground) if CUT_CROSSINGS else []
    kept, last = [], 0.0
    for sarc, xy, name in cross:
        if sarc - last < 2.0 * MOUTH + 10.0 or cum[-1] - sarc < MOUTH + 10.0:
            print("island_core_streets: %s crosses %s at (%.0f, %.0f) too near another junction to cut it -- left"
                  % (s["name"], name, xy[0], -xy[1]))
            continue
        kept.append((sarc, xy, name))
        last = sarc
    bounds = [0.0] + [v for sarc, _xy, _n in kept for v in (sarc - MOUTH, sarc + MOUTH)] + [cum[-1]]
    step = s.get("spacing", SPACING)
    pieces = []
    for i in range(0, len(bounds), 2):
        part = _slice(dense, cum, bounds[i], bounds[i + 1])
        pts = _resample(part, step)
        pts3 = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
        pieces.append(chain_road(net, s["name"] + ("__c%d" % (i // 2) if i else ""), pts3, preset="block",
                                 one_way=s.get("one_way", False)))
    for k, (sarc, xy, name) in enumerate(kept):
        members = list(cut_road(net, xy, name.split("__")[0], MOUTH))
        make_junction(net, members + [pieces[k].points[-1], pieces[k + 1].points[0]])
        print("island_core_streets: %s crosses %s at (%.0f, %.0f) -- a crossroads" % (s["name"], name, xy[0], -xy[1]))
    for road in pieces[1:]:
        for u in road.points:
            q = net.points[u]
            q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True
    road = pieces[0]
    last_road = pieces[-1]
    if s.get("one_way"):
        # a ONE-WAY street (the station rotary): all its lanes run with the chain, on every station (a station's lane
        # counts are its own, not the base's), and its outer (left) footway is the kerb a bus stops at
        road.base.lanes_fwd, road.base.lanes_bwd = s.get("lanes", 2), 0
        road.base.left_walk_width, road.base.right_walk_width = s.get("walks", (4.0, 2.0))
        for r_ in pieces:
            r_.base.lanes_fwd, r_.base.lanes_bwd = s.get("lanes", 2), 0
            r_.base.left_walk_width, r_.base.right_walk_width = s.get("walks", (4.0, 2.0))
            for u in r_.points:
                net.points[u].lanes_fwd, net.points[u].lanes_bwd = s.get("lanes", 2), 0
    make_junction(net, t1 + [road.points[0]])
    make_junction(net, t2 + [last_road.points[-1]])
    for u in road.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True
    return road


#: the block splits (tools/island_block_split.py, derived once and frozen): `after` streets across the big blocks
SPLITS = os.path.join(rg.ROOT, "assets", "world_source", "pieces", "IslandBlockSplits.json")


def all_streets():
    out = list(STREETS)
    if os.path.exists(SPLITS):
        import json
        for s_ in json.load(open(SPLITS))["splits"]:
            out.append(dict(s_, corners=[tuple(c) for c in s_["corners"]], after=True))
    return out


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    STREETS_ = all_streets()
    missing = [s for s in STREETS_ if s["name"] not in net.roads]
    if "--check" not in argv:
        # `after` streets hang off the grid planner's streets: they are added by a second run, `--after`
        missing = [s for s in missing if bool(s.get("after")) == ("--after" in argv)]
    if "--check" in argv:
        print("island_core_streets: %d of %d authored streets present" % (len(STREETS_) - len(missing), len(STREETS_)))
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
