"""Road TYPES as presets: the one owner of what each class of road in the world is (PLAN.md 3.13 step 1).

    python3 point_presets.py          # self-test

A preset is the road's own fields (class, pedestrian access, barrier, median style, pier asset) plus its base
cross-section (`RoadData.base`). `apply_preset` writes both and sets every INHERIT station's lane counts (the
DELTA_FIELDS a station keeps for itself), so a road becomes the type in one gesture; an OVERRIDE station keeps
its own section and is reported. Sizes are Japanese, at the arcade lane width the world already uses (4.5 m,
CLAUDE.md "LANES ARE 4.5 m"):

* **expressway** (首都高-style): 2 lanes each way, a wall median, no footway, barriers both sides, on the
  `hammerhead` pier asset; 80 km/h.
* **trunk** (幹線道路): 3 lanes each way, a raised median, 4 m footways (道路構造令: >= 3.5 m where pedestrians are
  heavy); 60 km/h.
* **block** (区画道路): 1 lane each way, 2 m footways; 30 km/h.
* **lane** (生活道路 with a 路側帯): 1 lane each way, no footway and no kerb, only a painted edge line; 30 km/h.
* **farm** (農道): 1 lane each way at 3.5 m, no footway, no kerb; 40 km/h.
* **coast** (海岸道路, PLAN.md 3.15): 2 lanes each way on a bench cut into a cliff, a painted median, no footway,
  barriers both sides, the uphill face cut near vertical (`cut_batter` 10); 60 km/h. Rock sheds are per station
  (`PointData.shed`).

* **rail** (PLAN.md 3.25, R1): a DOUBLE TRACK -- 1 + 1 lanes whose centres are the track centres, 4.0 m apart (the
  Japanese 3.8-4.0 m), a 1 m ballast shoulder each side, no median / kerb / footway, fenced (`ped_access` off), on
  the `hammerhead` pier when elevated; 80 km/h. `point_mesh` sweeps it as a ballast bed + two rails a track, cut out
  at a level crossing; the lanekit carries `road_class` "rail", which the game keeps out of traffic and the GPS.

Ramps are made by `point_record_ops.branch_ramp` / `make_ramp` (class `ramp`), not by a preset.
"""
import point_model as pm

PRESETS = {
    "expressway": {
        "road": {"road_class": "expressway", "ped_access": False, "barrier_height": 1.1,
                 "median_style": pm.MED_WALL, "pillar_asset": "RKA_PIER_hammerhead",
                 # the world is compressed (CLAUDE.md "The merge taper is the metric standard x taper_factor"):
                 # half the book's taper, so an interchange fits between two city blocks
                 "taper_factor": 0.5, "median_strip": 0.2},
        # 道路構造令 第2種 (an URBAN expressway, 首都高): a 1.25 m outer shoulder outside the solid edge line (第1種, an
        # intercity expressway, has 2.5 m; a breakdown on 首都高 uses 非常駐車帯 bays). The median stays 1.0 m: the
        # 0.6 m wall plus a 0.2 m 側帯 each side, a solid line 0.2 m off the wall. MEASURED: a 0.75 m strip (median
        # 2.5 m) moves every lane 0.75 m out, and the layout then broke the ramp rule on 3 ramps and a crossing.
        "base": {"lanes_fwd": 2, "lanes_bwd": 2, "lane_width": 4.5, "median_width": 1.0,
                 "shoulder_left_width": 1.25, "shoulder_right_width": 1.25,
                 "left_walk_width": 0.0, "right_walk_width": 0.0, "design_speed": 80.0},
    },
    "trunk": {
        "road": {"road_class": "arterial", "ped_access": True, "barrier_height": 1.0, "median_style": pm.MED_RAISED,
                 "median_strip": 0.25},
        # a 0.5 m 路肩 inside each kerb and a 0.25 m 側帯 each side of the 2.0 m island (4種)
        "base": {"lanes_fwd": 3, "lanes_bwd": 3, "lane_width": 4.5, "median_width": 2.5,
                 "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                 "left_walk_width": 4.0, "right_walk_width": 4.0, "left_kerb_height": 0.15,
                 "right_kerb_height": 0.15, "design_speed": 60.0},
    },
    "block": {
        "road": {"road_class": "street", "ped_access": True, "barrier_height": 1.0, "median_style": pm.MED_NONE},
        "base": {"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 4.5, "median_width": 0.0,
                 "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                 "left_walk_width": 2.0, "right_walk_width": 2.0, "left_kerb_height": 0.15,
                 "right_kerb_height": 0.15, "design_speed": 30.0},
    },
    "lane": {
        "road": {"road_class": "street", "ped_access": True, "barrier_height": 1.0, "median_style": pm.MED_NONE},
        # the 路側帯: 0.75 m outside a solid white line, where a walker without a footway walks
        "base": {"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 4.5, "median_width": 0.0,
                 "shoulder_left_width": 0.75, "shoulder_right_width": 0.75,
                 "left_walk_width": 0.0, "right_walk_width": 0.0, "left_kerb_height": 0.0,
                 "right_kerb_height": 0.0, "design_speed": 30.0},
    },
    "farm": {
        "road": {"road_class": "farm", "ped_access": True, "barrier_height": 1.0, "median_style": pm.MED_NONE},
        "base": {"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 3.5, "median_width": 0.0,
                 "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                 "left_walk_width": 0.0, "right_walk_width": 0.0, "left_kerb_height": 0.0,
                 "right_kerb_height": 0.0, "design_speed": 40.0},
    },
    # A 2 + 2 AT-GRADE arterial with footways: buildings front it, so it is walkable and kerbed, and the barrier
    # rule (`point_solve.solve_road`) walls it only where it is off the ground or on piers. The `coast` preset is its
    # opposite -- a road cut into a cliff with no frontage, walled end to end.
    "arterial": {
        "road": {"road_class": "arterial", "ped_access": True, "barrier_height": 1.0, "median_style": pm.MED_PAINT},
        "base": {"lanes_fwd": 2, "lanes_bwd": 2, "lane_width": 4.5, "median_width": 0.5,
                 "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                 "left_walk_width": 4.0, "right_walk_width": 4.0, "left_kerb_height": 0.15,
                 "right_kerb_height": 0.15, "design_speed": 50.0},
    },
    "coast": {
        "road": {"road_class": "arterial", "ped_access": False, "barrier_height": 1.0, "median_style": pm.MED_PAINT,
                 "cut_batter": 10.0},
        "base": {"lanes_fwd": 2, "lanes_bwd": 2, "lane_width": 4.5, "median_width": 0.5,
                 "shoulder_left_width": 0.75, "shoulder_right_width": 0.75,
                 "left_walk_width": 0.0, "right_walk_width": 0.0, "left_kerb_height": 0.0,
                 "right_kerb_height": 0.0, "design_speed": 60.0},
    },
    "rail": {
        "road": {"road_class": "rail", "ped_access": False, "barrier_height": 1.2, "median_style": pm.MED_NONE,
                 "pillar_asset": "RKA_PIER_hammerhead"},
        "base": {"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 4.0, "median_width": 0.0,
                 "shoulder_left_width": 1.0, "shoulder_right_width": 1.0,
                 "left_walk_width": 0.0, "right_walk_width": 0.0, "left_kerb_height": 0.0,
                 "right_kerb_height": 0.0, "design_speed": 80.0},
    },
}


class PresetError(Exception):
    pass


#: The shoulders by road CLASS, for a road whose section was written before shoulders existed (the island's arterials
#: input, PLAN.md "edge lines"). (outer each side, median 側帯). A road already carrying a shoulder keeps it.
CLASS_SHOULDERS = {"arterial": (0.5, 0.25), "street": (0.5, 0.0), "farm": (0.5, 0.0)}


def add_shoulders(net, road_name):
    """Give `road_name` its class's 路肩 and 側帯 (`CLASS_SHOULDERS`) without touching its lanes, its kerbs or its
    footways: the shoulders are paved INSIDE the kerb, so the kerb, the footway and everything beyond move out by the
    shoulder; the lanes stay where they are. Idempotent. Returns True if anything changed."""
    road = net.roads[road_name]
    rule = CLASS_SHOULDERS.get(road.road_class)
    if rule is None:
        return False
    outer, strip = rule
    changed = False
    b = road.base
    for f in ("shoulder_left_width", "shoulder_right_width"):
        if float(getattr(b, f)) <= 0.0:
            setattr(b, f, outer)
            changed = True
    if (strip > 0.0 and road.median_style in (pm.MED_RAISED, pm.MED_WALL) and float(road.median_strip) <= 0.0
            and float(b.median_width) > 0.0):
        road.median_strip = strip
        b.median_width = float(b.median_width) + 2.0 * strip     # the island keeps its width; the strips are added
        changed = True
    return changed


def make_one_way(road, lanes=None):
    """Turn a two-way base into ONE carriageway: no reverse lanes, no median, and the median's 側帯 becomes the
    carriageway's RIGHT shoulder (the median side), so two one-way halves leaving a divided road at a joint each keep
    the strip they had and their paved bands do not overlap."""
    b = road.base
    if lanes is not None:
        b.lanes_fwd = lanes
    b.lanes_bwd = 0
    b.median_width = 0.0
    b.shoulder_right_width = float(getattr(road, "median_strip", 0.0) or 0.0)
    road.median_strip = 0.0


def apply_preset(net, road_name, preset):
    """Make road `road_name` the `preset` type: its fields, its base section, and every INHERIT station's lane
    counts. Returns (message, {road, preset, overridden: [uids]})."""
    if preset not in PRESETS:
        raise PresetError("unknown road type %r (one of %s)" % (preset, ", ".join(sorted(PRESETS))))
    road = net.roads.get(road_name)
    if road is None:
        raise PresetError("no road %r" % road_name)
    spec = PRESETS[preset]
    for k, v in spec["road"].items():
        if not hasattr(road, k):
            raise PresetError("road field %s does not exist" % k)
        setattr(road, k, v)
    for k, v in spec["base"].items():
        setattr(road.base, k, v)
    overridden = []
    for uid in road.points:
        p = net.points[uid]
        if p.profile_mode == pm.OVERRIDE:
            overridden.append(uid)
            continue
        p.lanes_fwd = spec["base"]["lanes_fwd"]
        p.lanes_bwd = spec["base"]["lanes_bwd"]
    msg = "%s is now a %s road (%d stations%s)" % (
        road_name, preset, len(road.points),
        "; %d OVERRIDE station(s) kept their own section" % len(overridden) if overridden else "")
    return msg, {"road": road_name, "preset": preset, "overridden": overridden}


def self_test():
    import point_record_ops as ro
    import point_validate as pv
    ok = 0

    def straight(net, name, pts):
        r = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
        prev = None
        for q in pts:
            p = net.add_station(r, q)
            if prev is not None:
                net.link(prev.uid, p.uid)
            prev = p
        return r

    # every preset alone passes the gate, and its fields and lanes landed
    for name, spec in PRESETS.items():
        net = pm.NetworkData()
        straight(net, "r", [(0, 0, 0.0), (200, 0, 0.0), (400, 0, 0.0)])
        apply_preset(net, "r", name)
        errs = pv.errors(pv.validate(net))
        assert not errs, (name, [(f.code, f.message) for f in errs])
        res = net.resolved(net.roads["r"].points[1])
        assert res.lanes_fwd == spec["base"]["lanes_fwd"] and abs(res.lane_width - spec["base"]["lane_width"]) < 1e-9
        assert net.roads["r"].road_class == spec["road"]["road_class"]
        # every style a preset names resolves in the KIT: the expressway preset wrote the bare "hammerhead" where the
        # kit's pier is `RKA_PIER_hammerhead`, and every expressway on the island stood on plain boxes for it, reported
        # only as a `missing_style` build line nobody read (2026-09-25)
        import point_kit as pk
        miss = pk.resolve(net.roads["r"], pk.load()).missing()
        assert not miss, (name, miss)
        ok += 1

    # a T junction: a trunk road through, a block street ending on it
    net = pm.NetworkData()
    straight(net, "west", [(-300, 0, 0.0), (-150, 0, 0.0), (-40, 0, 0.0)])
    straight(net, "east", [(40, 0, 0.0), (150, 0, 0.0), (300, 0, 0.0)])
    straight(net, "side", [(0, -300, 0.0), (0, -150, 0.0), (0, -40, 0.0)])
    for r in ("west", "east"):
        apply_preset(net, r, "trunk")
    apply_preset(net, "side", "block")
    mouths = [net.roads["west"].points[-1], net.roads["east"].points[0], net.roads["side"].points[-1]]
    for i in range(3):
        for j in range(i + 1, 3):
            net.link(mouths[i], mouths[j], pm.LINK_JUNCTION)
    for u in mouths:
        net.points[u].role = pm.INTERSECTION
    errs = pv.errors(pv.validate(net))
    assert not errs, [(f.code, f.message) for f in errs]
    ok += 1

    # an expressway exit and entrance on the preset (the interchange's two ramps)
    net = pm.NetworkData()
    straight(net, "hwy", [(x, 0, 12.0) for x in (0, 300, 600, 900, 1200)])
    apply_preset(net, "hwy", "expressway")
    ro.branch_ramp(net, net.roads["hwy"].points[1], name="off", drop=-6.0)
    ro.branch_ramp(net, net.roads["hwy"].points[3], name="on", carriageway="BWD", entrance=True, drop=-6.0)
    errs = pv.errors(pv.validate(net))
    assert not errs, [(f.code, f.message) for f in errs]
    ok += 1

    # an OVERRIDE station keeps its own section and is reported; an unknown type is refused
    net = pm.NetworkData()
    r = straight(net, "r", [(0, 0, 0.0), (200, 0, 0.0), (400, 0, 0.0)])
    net.points[r.points[1]].profile_mode = pm.OVERRIDE
    net.points[r.points[1]].lanes_fwd = 1
    _msg, extra = apply_preset(net, "r", "trunk")
    assert extra["overridden"] == [r.points[1]] and net.points[r.points[1]].lanes_fwd == 1
    try:
        apply_preset(net, "r", "motorway")
        raise AssertionError("unknown preset accepted")
    except PresetError:
        ok += 2
    print("point_presets.py: %d checks PASS" % ok)


if __name__ == "__main__":
    self_test()
