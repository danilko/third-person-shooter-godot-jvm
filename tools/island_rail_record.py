#!/usr/bin/env python3
"""The island's RAIL as a Road Kit record (PLAN.md 3.25 / the rail rebuild batch, R2).

    python3 tools/island_rail_record.py [--layout tokyo_straight] [--out <record>] [--check]

`tools/island_rail_layout.py` is the PLAN: each line's alignment (filleted corners), its form per stretch (at
grade / elevated / on the Rainbow Bridge), its profile at the train's ruling grade, and every place it crosses a
road. This tool turns that plan into `assets/world_source/pieces/IslandRail.roads.json` -- a Road Kit network whose
every road is a `rail` preset double track (`point_presets`) -- so everything a road gets, the rail gets for free:
the swept bed, rails and piers (`point_mesh` "RAIL"), the zone cut and streaming (`island_road_zones.py --network
IslandRail`), the lanekit a train will follow (tier D; `road_class` "rail" keeps it out of traffic and the GPS).

What it decides, and nothing else:
  * STATIONS every `STEP` m along the plan's own 5 m polyline (curves stay curves: the kit sweeps a carrier through
    the stations, and a 160 m curve sampled at 20 m is 0.3 m off its chord at worst);
  * each station's height is the BED: the plan's rail head less the rail (`point_mesh.RAIL_H`), except at a LEVEL
    CROSSING, where the bed is the ROAD's surface (the rails lie flush -- `point_mesh` cuts the bed out there) and
    it eases back to the plan at the ruling grade;
  * `pillar_skip` on the stations the Rainbow Bridge carries (the lower deck is the rail, R7), by the bridge's own
    rule (`island_rainbow_bridge`).
Frozen facings, joints and zones are the zone tool's (`island_road_zones.py --split`), exactly as for the roads.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender/addons/road_kit_authoring"))
sys.path.insert(0, os.path.join(ROOT, "blender/lib"))

import point_model as pm            # noqa: E402
import point_presets as ppr         # noqa: E402
import point_mesh as pmsh           # noqa: E402

OUT = os.path.join(ROOT, "assets/world_source/pieces/IslandRail.roads.json")
STEP = 20.0                 # m between stations
EASE = 0.035                # the ruling grade the bed eases back to the plan at, around a level crossing
CROSS_HOLD = 12.0           # m either side of a level crossing held at the road's height (a road's half + margin)
ZONE_ID = "rail"            # the record's zone id before the cut (the zone tool re-assigns by cell)
#: A STATION'S PLATFORMS ARE THE RAIL'S OWN CROSS-SECTION (PLAN.md R3): over the platform's length every station is an
#: OVERRIDE section whose footways ARE the two side platforms (相対式ホーム) -- the kit sweeps them, kerbs them, fences
#: them and gives them collision, they follow the track through a curve, and they stream with the rail piece; no
#: separate placement can drift off the track. The track centres stay put: the carriageway narrows to
#: PLATFORM_LANE_W with a PLATFORM_MEDIAN between the tracks, so (median + lane) / 2 is still the base's 2.0 m and
#: the platform edge stands PLATFORM_EDGE from each track centre (a 2.9 m car body leaves ~5 cm, the Japanese gap).
#: One span either end ramps the platform down to the bed, the slope a Japanese platform end has.
PLATFORM_H = 1.1 + 0.16      # platform top over the BED: 1.1 m over the rail head (the 1100 mm conventional-line
                             # standard), the rail standing RAIL_H on the bed
#: a HUB's lines run 14 m apart (island_rail_layout, Central), so each line's two 3 m side platforms and their back
#: fences stand clear of the neighbour's gauge (at 10 m apart they overlapped: probe_rail_track, 2026-09-26)
#: a HUB's platforms are 3.45 m: its lines run 14 m apart (HUB_SPACING), so two neighbouring platforms meet edge to
#: edge at the mid line (1.55 + 2.0 + 3.45 = 7.0) and their fences come down there (`platform_open`): one island
#: platform serving both lines, walked straight across
PLATFORM_W = {"small": 3.0, "standard": 4.0, "large": 5.0, "junction": 5.0, "hub": 3.45}
PLATFORM_LANE_W = 3.1
PLATFORM_MEDIAN = 0.9
PLATFORM_EDGE = 1.55             # 1.5 left the kerb's mitre at a platform END 2-3 cm inside a 2.7 m train gauge
assert abs(PLATFORM_MEDIAN / 2 + PLATFORM_LANE_W - (PLATFORM_MEDIAN + PLATFORM_LANE_W) / 2 - PLATFORM_EDGE) < 1e-9, \
    "the platform edge is median/2 + lane - the track centre"
#: the section fields an OVERRIDE station carries verbatim (identity, shape and per-station state stay the point's)
SECTION_FIELDS = ("lanes_fwd", "lanes_bwd", "lane_width", "drop_side_fwd", "drop_side_bwd", "aux_fwd", "aux_bwd",
                  "aux_side", "shoulder_left_width", "shoulder_right_width", "parking_left_width",
                  "parking_right_width", "median_width", "left_kerb_height", "left_walk_width", "right_kerb_height",
                  "right_walk_width", "design_speed", "deck_thickness", "pillar_spacing")
NAMES = {"Main line": "rail_main", "Blue line": "rail_blue", "Harbour line": "rail_harbour",
         "Freight siding": "rail_freight"}


def true_alignment(line):
    """The line's alignment as stations ON its geometry: straights every <= STEP, each fillet an exact circular arc
    sampled at chords <= STEP (`island_roadgen.rounded_polygon`'s own fillet rule: radius shrunk to fit 0.45 of each
    span). The plan's own polyline samples an arc coarsely and interpolates between, which reads a 200 m curve as
    ~32 m from station to station -- the kit sweeps what it is handed, so it must be handed the arc."""
    import island_rail_layout as R
    C = [tuple(c) for c in line["corners"]]
    rads = R.radii(line)
    fil = {}
    for i in range(1, len(C) - 1):
        p0, p1, p2 = C[i - 1], C[i], C[i + 1]
        a = (p0[0] - p1[0], p0[1] - p1[1]); b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        a, b = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
        ang = math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))
        if ang > math.pi - 1e-3:
            continue
        t = min(rads[i] / math.tan(ang / 2.0), 0.45 * la, 0.45 * lb)
        r = t * math.tan(ang / 2.0)
        s_ = (p1[0] + a[0] * t, p1[1] + a[1] * t)
        e_ = (p1[0] + b[0] * t, p1[1] + b[1] * t)
        bis = (a[0] + b[0], a[1] + b[1]); lbis = math.hypot(*bis)
        d = r / math.sin(ang / 2.0)
        c = (p1[0] + bis[0] / lbis * d, p1[1] + bis[1] / lbis * d)
        fil[i] = (s_, e_, c, r)
    out = [C[0]]

    def line_to(q):
        p = out[-1]
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        k = max(1, int(math.ceil(L / STEP - 1e-9)))
        for j in range(1, k + 1):
            out.append((p[0] + (q[0] - p[0]) * j / k, p[1] + (q[1] - p[1]) * j / k))

    for i in range(1, len(C)):
        if i in fil:
            s_, e_, c, r = fil[i]
            line_to(s_)
            a0 = math.atan2(s_[1] - c[1], s_[0] - c[0]); a1 = math.atan2(e_[1] - c[1], e_[0] - c[0])
            da = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
            k = max(2, int(math.ceil(abs(da) * r / STEP)))
            for j in range(1, k + 1):
                aj = a0 + da * j / k
                out.append((c[0] + r * math.cos(aj), c[1] + r * math.sin(aj)))
        elif i < len(C) - 1:
            line_to(C[i])
        else:
            line_to(C[i])
    # drop a sliver a join left (two stations under a metre apart)
    clean = [out[0]]
    for q in out[1:]:
        if math.hypot(q[0] - clean[-1][0], q[1] - clean[-1][1]) > 1.0:
            clean.append(q)
    return clean


def bed_profile(L):
    """The bed height per plan point: rail head - RAIL_H, held at the road's surface over each level crossing and
    eased back to the plan at EASE either side (a crossing is never approached down a step)."""
    z = [h - pmsh.RAIL_H for h in L["z"]]
    cum = L["cum"]
    for c in L["crossings"]:
        if c["form"] != "level crossing":
            continue
        t = c["road_z"]
        for i in range(len(z)):
            d = max(0.0, abs(cum[i] - c["s"]) - CROSS_HOLD)
            lim = EASE * d
            z[i] = t + max(-lim, min(lim, z[i] - t))
    return z


def _at(cum, vals, s):
    """`vals` (per plan point) linearly at arc length `s`."""
    import bisect
    i = max(1, min(len(cum) - 1, bisect.bisect_left(cum, s)))
    t = (s - cum[i - 1]) / max(1e-9, cum[i] - cum[i - 1])
    return vals[i - 1] + (vals[i] - vals[i - 1]) * max(0.0, min(1.0, t))


#: a HUB serves every line that passes (or ends) within this of its centre, not only the line it is listed on:
#: Central is the Main line's, and the Blue and Harbour lines terminate beside it -- with no platform of their own
#: they ended in the open 10 m from a station (user, 2026-09-26: "if rail does end, ensure it is ending in a station")
HUB_SHARE = 25.0
#: the station kinds every passing line stops at: the hub (Central) and a junction (Bay, where the Harbour line leaves
#: the Main line 20 m beside it -- the layout lists Bay as the Harbour line's first station)
SHARED_KINDS = ("hub", "junction")


def platform_spans(res, line):
    """[(s0, s1, kind)] -- each station's platform on `line`, as plan arc length. A hub also gives a platform to every
    other line passing within HUB_SHARE of it, clipped to that line's own length."""
    import island_rail_layout as R
    out = [(st["s"] - st["platform_m"] / 2.0, st["s"] + st["platform_m"] / 2.0, st["kind"])
           for st in res["stations"].values() if st["line"] == line]
    L = res["lines"][line]
    for st in res["stations"].values():
        if st["line"] == line or st["kind"] not in SHARED_KINDS:
            continue
        s_, d = R.project(L["pts"], L["cum"], st["x"], st["y"])
        if d <= HUB_SHARE:
            a, b = max(0.0, s_ - st["platform_m"] / 2.0), min(L["cum"][-1], s_ + st["platform_m"] / 2.0)
            if b - a > 20.0:
                out.append((a, b, st["kind"]))
    return out


def open_air_reach():
    """How far past each end of an open-air station's platform its fence stands down: the end building
    (`station_layout.BUILDING_LEN`) plus a metre, so the rail's fence resumes against the building's street face."""
    import station_layout as SL
    return SL.BUILDING_LEN + 1.0


def _span_station(res, line, s0, s1):
    """The station a platform span of `line` belongs to: the one whose centre is nearest the span's middle (a hub or a
    junction gives a span to every line passing within HUB_SHARE, so it need not be the station's own line)."""
    L = res["lines"][line]
    x, y = point_at(L, 0.5 * (s0 + s1))[:2]
    return min(res["stations"].items(), key=lambda kv: math.hypot(kv[1]["x"] - x, kv[1]["y"] - y))[0]


def open_air_spans(res, line):
    """[(s0, s1, kind, station, form)] -- `line`'s platform spans that belong to a station laid out from the STATION
    KIT (`station_layout.KIT_FORMS`: the open-air form and the ground hub). Their platforms are the kit's, so the
    record keeps the track only there."""
    import station_layout as SL
    forms = {n: st.form for n, st in SL.stations(res, ends={}, entrances={}).items()}
    out = []
    for s0, s1, kind in platform_spans(res, line):
        n = _span_station(res, line, s0, s1)
        if forms.get(n) in SL.KIT_FORMS:
            out.append((s0, s1, kind, n, forms[n]))
    return out


def open_air_fence(res, line, s_):
    """The sides ('left' / 'right' of the chain) whose rail fence stands down at arc length `s_`: both along a kit
    station's platform; past each end of an OPEN-AIR platform only on the side whose END BUILDING stands there
    (`station_layout`'s chosen `building_end`); elsewhere none. The platform-less end keeps its fence, so the bed is
    not opened to the street (a ground hub has no end building: its fence resumes at both platform ends)."""
    import station_layout as SL
    reach = open_air_reach()
    out = set()
    sls = SL.stations(res)
    for s0, s1, _k, n, form in open_air_spans(res, line):
        # a station within a metre BEFORE the platform's start counts as its start: `with_platform_ends` does not insert
        # a station that close to an existing one, and the one standing there holds the span the platform starts in
        if s0 - 1.0 <= s_ < s1 - 1e-3:
            out |= {"left", "right"}
        if form != "open_air":
            continue
        for side in ("left", "right"):
            end = sls[n].building_end.get(side, 1)
            if (end > 0 and s1 - 1e-3 <= s_ < s1 + reach - 1e-3) or (end < 0 and s0 - reach - 1e-3 <= s_ < s0 - 1e-3):
                out.add(side)
    return out


def _straight(idx, i):
    """The span idx[i-1] -> idx[i] and both its neighbours are one straight line: a station inserted on its chord is
    then ON the alignment (on an arc it would sit inside the curve and read as a kink)."""
    def heading(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])
    hs = [heading(idx[k - 1], idx[k]) for k in (i - 1, i, i + 1) if 1 <= k < len(idx)]
    return all(abs((h - hs[0] + math.pi) % (2.0 * math.pi) - math.pi) < math.radians(0.2) for h in hs)


def on_straight(idx, svals, a, b):
    """[a, b] (plan arc length) lies inside one straight span of the alignment."""
    return any(_straight(idx, i) and svals[i - 1] + 1.0 < a and b < svals[i] - 1.0 for i in range(1, len(idx)))


def with_platform_ends(idx, svals, spans, cuts=()):
    """`idx` (the alignment's stations, with their plan arc lengths `svals`) plus a station at each platform END, so a
    platform is exactly its length, and at each of `cuts` (an exit's two edges): [(x, y, s)]."""
    ends = sorted({round(v, 3) for s0, s1, _k in spans for v in (s0, s1)} | {round(v, 3) for v in cuts})

    def straight(i):
        return _straight(idx, i)
    out = []
    for i, (q, sq) in enumerate(zip(idx, svals)):
        if i and straight(i):
            (px, py), sp = idx[i - 1], svals[i - 1]
            for e in ends:
                if sp + 1.0 < e < sq - 1.0:
                    t = (e - sp) / (sq - sp)
                    out.append((px + (q[0] - px) * t, py + (q[1] - py) * t, e))
        out.append((q[0], q[1], sq))
    return out


#: A PLATFORM EXIT (point_model.PLATFORM_EXITS): the fence opens over EXIT_W of platform and a stair goes down to the
#: ground there (point_mesh.platform_stairs) -- how a player gets from the station building onto the train
#: (user, 2026-09-26: "character cannot walk up to connect to train"). One per station, at its building's position
#: along the platform (the platform's middle where it has none), on each platform whose outside is free: a side
#: with another line's platform within NEIGHBOUR_REACH is OPENED instead (`platform_open`, no stair), a hub's island.
EXIT_W = 3.0
NEIGHBOUR_REACH = 9.0
RESERVE_FILE = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")


def point_at(L, s):
    """(x, y, tx, ty) of line `L` at plan arc length `s`."""
    pts, cum = L["pts"], L["cum"]
    s = max(0.0, min(cum[-1], s))
    i = max(1, next((k for k in range(1, len(cum)) if cum[k] >= s), len(cum) - 1))
    a, b = pts[i - 1], pts[i]
    seg = (cum[i] - cum[i - 1]) or 1e-9
    t = (s - cum[i - 1]) / seg
    tl = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (b[0] - a[0]) / tl, (b[1] - a[1]) / tl


def neighbour_platform(res, line, x, y):
    """Another line whose PLATFORM stands within NEIGHBOUR_REACH of plan point (x, y)."""
    import island_rail_layout as R
    for other, L in res["lines"].items():
        if other == line:
            continue
        s_, d = R.project(L["pts"], L["cum"], x, y)
        if d <= NEIGHBOUR_REACH and any(s0 <= s_ <= s1 for s0, s1, _k in platform_spans(res, other)):
            return other
    return None


def side_free(res, line, L, s_):
    """{'left': bool, 'right': bool}: which of `line`'s platforms at `s_` have their outside free (no neighbouring
    line's platform just beyond the fence). Left is the left of the line's chain direction."""
    x, y, tx, ty = point_at(L, s_)
    out = {}
    for side, sg in (("left", 1.0), ("right", -1.0)):
        nx, ny = -ty * sg, tx * sg
        out[side] = neighbour_platform(res, line, x + nx * 8.0, y + ny * 8.0) is None
    return out


def exit_plan(res, line, idx=None, svals=None, spans=None):
    """[(s_centre, kind)] -- each platform of `line`'s exit centre: at the station building (the rail reserve's
    `building:<Station>` box, or for the hub its landmark site) projected onto the line, kept EXIT_W inside the
    platform."""
    import island_rail_layout as R
    boxes = {}
    if os.path.exists(RESERVE_FILE):
        boxes = {b["id"]: b for b in json.load(open(RESERVE_FILE))["boxes"]}
    L = res["lines"][line]
    out = []
    for s0, s1, kind in (platform_spans(res, line) if spans is None else spans):
        mid = 0.5 * (s0 + s1)
        st = min(res["stations"].items(), key=lambda kv: math.hypot(*(lambda p: (p[0] - kv[1]["x"], p[1] - kv[1]["y"]))(
            point_at(L, mid)[:2])))
        b = boxes.get("building:" + st[0])
        s_ = R.project(L["pts"], L["cum"], b["x"], b["y"])[0] if b else mid
        s_ = max(s0 + EXIT_W, min(s1 - EXIT_W, s_))
        if idx is not None and not on_straight(idx, svals, s_ - EXIT_W / 2.0, s_ + EXIT_W / 2.0):
            # on a curve a station cannot be inserted without a kink: slide the exit along its platform to the
            # nearest straight stretch
            cand = [s_ + sg * d for d in range(1, int(s1 - s0)) for sg in (1.0, -1.0)]
            s_ = next((c for c in cand if s0 + EXIT_W <= c <= s1 - EXIT_W
                       and on_straight(idx, svals, c - EXIT_W / 2.0, c + EXIT_W / 2.0)), s_)
        out.append((s_, kind))
    return out


BUILDING_HALF_DEPTH = 7.28 / 2.0      # the StationBuilding type's depth across the track, halved
YARD_MAX = 10.0                       # a building further than this behind a platform is not that platform's


def platform_outer(kind):
    """How far a platform's outer edge stands from the line's centre (make_platform's section)."""
    return PLATFORM_MEDIAN / 2.0 + PLATFORM_LANE_W + PLATFORM_W.get(kind, PLATFORM_W["standard"])


def paid_yards(res, line, L, s_, kind):
    """{side: (yard depth, building shift)} for the station buildings (`building:` / `building_far:` in the reserve)
    beside `line`'s platform at arc length `s_`: the yard reaches from the platform's outer edge to the building's
    back wall, and the building's centre stands `shift` along the chain from the exit's centre."""
    import island_rail_layout as R
    if not os.path.exists(RESERVE_FILE):
        return {}
    boxes = json.load(open(RESERVE_FILE))["boxes"]
    x, y, tx, ty = point_at(L, s_)
    st = min(res["stations"].items(), key=lambda kv: math.hypot(x - kv[1]["x"], y - kv[1]["y"]))[0]
    out = {}
    for b in boxes:
        kind_, _c, nm = b["id"].partition(":")
        if kind_ not in ("building", "building_far") or nm != st:
            continue
        across = (b["x"] - x) * -ty + (b["y"] - y) * tx
        side = "left" if across > 0 else "right"
        depth = abs(across) - BUILDING_HALF_DEPTH - platform_outer(kind)
        if depth < 0.5:
            print("rail record: %s's %s building stands on its platform (yard %.2f m)" % (st, side, depth))
            continue
        if depth > YARD_MAX:
            # another line's building (a junction's platforms serve two lines; the building stands behind the
            # station's OWN line) -- a yard to it would cross that line's tracks
            continue
        shift = R.project(L["pts"], L["cum"], b["x"], b["y"])[0] - s_
        out[side] = (depth, shift)
    return out


def side_enum(sides):
    left, right = "left" in sides, "right" in sides
    return pm.EXIT_BOTH if left and right else pm.EXIT_LEFT if left else pm.EXIT_RIGHT if right else pm.EXIT_NONE


def make_platform(net, road, p, kind):
    """Station `p` an OVERRIDE platform section (see PLATFORM_H): the road's base, the carriageway narrowed to the
    platform edge, side platforms both sides."""
    b = road.base
    for f in SECTION_FIELDS:
        setattr(p, f, getattr(b, f))
    p.profile_mode = pm.OVERRIDE
    p.lane_width, p.median_width = PLATFORM_LANE_W, PLATFORM_MEDIAN
    p.shoulder_left_width = p.shoulder_right_width = 0.0
    w = PLATFORM_W.get(kind, PLATFORM_W["standard"])
    p.left_walk_width = p.right_walk_width = w
    p.left_kerb_height = p.right_kerb_height = PLATFORM_H


def build(res):
    net = pm.NetworkData()
    report = []
    for line, L in res["lines"].items():
        name = NAMES.get(line, "rail_" + line.lower().replace(" ", "_"))
        bed = bed_profile(L)
        road = net.add_road(pm.RoadData(name, pm.PointData(uid=""), (), zone_id=ZONE_ID))
        prev = None
        import island_rail_layout as R
        idx = true_alignment(R.LINES[line])
        svals = [R.project(L["pts"], L["cum"], x, y)[0] for x, y in idx]
        # AN OPEN-AIR STATION'S PLATFORMS ARE ITS OWN SCENE (PLAN.md step 3: the station kit, `station_layout`): over
        # its span the record keeps the TRACK only -- no platform section, no exits -- and stands its fence and car
        # wall down from one end building to the other, where the kit's platforms and buildings take their place
        oa = open_air_spans(res, line)
        spans = [sp for sp in platform_spans(res, line) if not any(abs(sp[0] - o[0]) < 1e-6 for o in oa)]
        exits = exit_plan(res, line, idx, svals, spans)
        reach = open_air_reach()
        oa_open = [(s0 - (reach if f == "open_air" else 1.0), s1 + (reach if f == "open_air" else 0.0))
                   for s0, s1, _k, _n, f in oa]
        stations = with_platform_ends(idx, svals, spans,
                                      [v for e, _k in exits for v in (e - EXIT_W / 2.0, e + EXIT_W / 2.0)]
                                      + [v for o in oa_open for v in o] + [v for s0, s1, _k, _n, _f in oa for v in (s0, s1)])
        made = []
        for x, y, s_ in stations:
            p = net.add_station(road, (round(x, 3), round(y, 3), round(_at(L["cum"], bed, s_), 3)))
            made.append((p, s_))
            if prev is not None:
                net.link(prev.uid, p.uid)
            prev = p
        ppr.apply_preset(net, name, "rail")
        nplat = 0
        for p, s_ in made:
            k = next((k for s0, s1, k in spans if s0 - 1e-3 <= s_ <= s1 + 1e-3), None)
            if k is not None:
                make_platform(net, road, p, k)
                nplat += 1
        # the exits: a stair on each platform whose outside is free; the fence OPENED (no stair) on a side that meets a
        # neighbouring line's platform, along the whole platform
        nexit, nopen, skipped = 0, 0, []
        for e, k_ in exits:
            first = next((p for p, s_ in made if abs(s_ - (e - EXIT_W / 2.0)) < 0.01), None)
            last = next((p for p, s_ in made if abs(s_ - (e + EXIT_W / 2.0)) < 0.01), None)
            free = side_free(res, line, L, e)
            if first is None or last is None:
                skipped.append(round(e))
                continue
            # THE PAID AREA: a side whose station building stands beside it gets the stair, into a fenced yard up to
            # the building's back door (the gates are inside it); a free side with NO building of its own gets no
            # stair -- it is reached by a footbridge from the side that has one. A station with no buildings at all
            # (the hub: 3.36) keeps a stair on every free side.
            yards = paid_yards(res, line, L, e, k_)
            if yards:
                stair = [sd for sd in yards if free.get(sd)]
                first.platform_exit = side_enum(stair)
                for sd, (depth, shift) in yards.items():
                    setattr(first, "yard_" + sd, round(depth, 3))
                    setattr(first, "yard_shift_" + sd, round(shift, 3))
                first.footbridge = bool(stair) and any(ok and sd not in yards for sd, ok in free.items())
                report.append("%-13s exit at s %.0f: building %s%s" % (name, e, "+".join(sorted(yards)),
                                                                    ", footbridge" if first.footbridge else ""))
            else:
                first.platform_exit = side_enum([sd for sd, ok in free.items() if ok])
            nexit += 1
        for i, (p, s_) in enumerate(made[:-1]):
            if not any(s0 - 1e-3 <= s_ <= s1 + 1e-3 for s0, s1, _k in spans) or \
                    not any(s0 - 1e-3 <= made[i + 1][1] <= s1 + 1e-3 for s0, s1, _k in spans):
                continue
            free = side_free(res, line, L, 0.5 * (s_ + made[i + 1][1]))
            shut = [sd for sd, ok in free.items() if not ok]
            if shut:
                p.platform_open = side_enum(shut)
                nopen += 1
        nopen_oa = 0
        for p, s_ in made:
            if any(o0 - 1e-3 <= s_ < o1 - 1e-3 for o0, o1 in oa_open):
                p.platform_open = side_enum(open_air_fence(res, line, s_))
                nopen_oa += 1
        if oa:
            report.append("%-13s %d kit station(s): track only, fence down over %d span(s)"
                          % (name, len(oa), nopen_oa))
        report.append("%-13s %d platform exit(s)%s, %d span(s) opened onto a neighbouring platform"
                      % (name, nexit, (" (SKIPPED, not on a straight: s %s)" % skipped) if skipped else "", nopen))
        nlx = sum(1 for c in L["crossings"] if c["form"] == "level crossing")
        report.append("%-13s %6.0f m  %3d stations  %2d level crossing(s)  %d platform(s) over %d station(s)"
                      % (name, L["length_m"], len(stations), nlx, len(spans), nplat))
    skipped = bridge_skip(net)
    report.append("pillar_skip on %d station(s) the Rainbow Bridge carries" % skipped)
    return net, report


def bridge_skip(net):
    """The rail rides the Rainbow Bridge's LOWER deck (R7): inside the structure the bridge carries it, so its
    stations there are `pillar_skip`, by the bridge's own rule (as `island_expressway.bridge_skip` for the spur)."""
    import island_rainbow_bridge as irb
    centre, axis = irb.crossing_plan()
    n = 0
    for r in net.roads.values():
        pts = [net.points[u] for u in r.points]
        for i, p in enumerate(pts):
            nxt = pts[i + 1] if i + 1 < len(pts) else None
            along = lambda q: (q.pos[0] - centre[0]) * axis[0] + (q.pos[1] - centre[1]) * axis[1]
            want = (nxt is not None and abs(along(p)) <= irb.HALF_LENGTH and abs(along(nxt)) <= irb.HALF_LENGTH
                    and p.pos[2] >= irb.DECK_MIN_Z and nxt.pos[2] >= irb.DECK_MIN_Z)
            p.pillar_skip = want
            n += 1 if want else 0
    return n


SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
NODE = """[node name="IslandRail" type="Node3D" parent="." unique_id=910011022]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, %s, 0)
script = ExtResource("rk_net")
record_path = "res://assets/world_source/pieces/IslandRail.roads.json"
generated = true

"""


def ensure_node(scene):
    """World.tscn's `IslandRail` RoadKitNetwork node (the rail's frame: the SAME as IslandRoads', so a rail station and
    a road station at one record position are at one world position), added once beside IslandRoads."""
    import re
    text = open(scene).read()
    if '[node name="IslandRail"' in text:
        return False
    m = re.search(r'\[node name="IslandRoads"[^\]]*\]\ntransform = Transform3D\(([^)]*)\)', text)
    y = m.group(1).split(",")[10].strip() if m else "0"
    at = text.index('[node name="IslandRoadsArterials"')
    open(scene, "w").write(text[:at] + NODE % y + text[at:])
    return True


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", default="tokyo_straight")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="exit 1 if the record would change")
    ap.add_argument("--scene", default=SCENE, help="the world scene the IslandRail network node goes in ('' = none)")
    a = ap.parse_args(argv)
    import island_rail_layout as R
    R.LAYOUT_NAME = a.layout
    R.use_layout(a.layout)
    res = R.analyse()
    net, report = build(res)
    for line in report:
        print("  " + line)
    import point_validate as pv
    findings = pv.validate(net)
    errs = pv.errors(findings)
    for f in findings:
        if f.code.startswith("rail") or f.severity == pv.ERROR:
            print("  [%s] %s %s: %s" % (f.severity, f.code, f.obj, f.message))
    text = json.dumps(pm.network_to_dict(net), indent=1, sort_keys=True) + "\n"
    if a.check:
        old = open(a.out).read() if os.path.exists(a.out) else ""
        # uids are fresh every run: compare the geometry, not the text
        same = old and _shape(json.loads(old)) == _shape(json.loads(text))
        print("island_rail_record: %s" % ("up to date" if same else "STALE"))
        return 0 if same and not errs else 1
    if errs:
        print("island_rail_record: REFUSED, %d gate error(s)" % len(errs))
        return 1
    if a.scene and ensure_node(a.scene):
        print("island_rail_record: added the IslandRail network node to %s" % os.path.relpath(a.scene, ROOT))
    if os.path.exists(a.out) and _shape(json.load(open(a.out))) == _shape(json.loads(text)):
        print("island_rail_record: %s unchanged" % os.path.relpath(a.out, ROOT))
        return 0
    pm.save_network(net, a.out)
    print("island_rail_record: wrote %s (%d roads, %d stations)" % (os.path.relpath(a.out, ROOT), len(net.roads),
                                                                    len(net.points)))
    return 0


def _shape(doc):
    """The record without its uids: every road's stations in chain order, rounded."""
    P = {p["uid"]: p for p in doc["points"]}
    return sorted((r["name"], tuple(tuple(round(c, 2) for c in P[u]["pos"])
                                    + (P[u].get("profile_mode", ""), P[u].get("left_walk_width", 0.0))
                                    for u in r["points"]))
                  for r in doc["roads"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
