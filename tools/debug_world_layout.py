#!/usr/bin/env python3
"""debug_world_layout.py -- DebugWorld, DERIVED: the compact test world with one of every system (user, 2026-09-28:
"redo debug world ... the traffic circle around entire island square like, a konbini, and train stations on the west,
expanded to fit two stations with a curved rail between them to test the enter / exit and the zone behaviour").

    python3 tools/debug_world_layout.py [--check]

The one owner of DebugWorld's layout. It writes, and nothing downstream is edited by hand:

  * `assets/world_source/terrain/debug_world.f32`  the terrain heights (Godot axes, 2 m, x/z -512..512), applied by
    `tools/godot/apply_height_grid.gd` into `assets/terrain3d/debug_world`;
  * `pieces/DebugRoads.roads.json`                 the roads: a rounded-square ARTERIAL RING round each island, an
    inner N-S and E-W street on the west crossing at a signalised junction, and the E-W street carried across the
    west ring and over the water as the BRIDGE to the east ring;
  * `pieces/DebugRail.roads.json`                  the rail: one line from station A (north-west, running east) round
    a 160 m curve to station B (south-east, running south), crossing both inner streets at level crossings (79 and
    72 deg, each > 60 m from a junction), cut at a JOINT mid-curve so it streams as two zones;
  * `pieces/DebugRoads.zones.json`, `pieces/DebugRail.zones.json`  the zone boxes the build cuts pieces with;
  * `assets/world_source/debug_world_layout.json`  what the scene gets (`tools/debug_world_scene.py` writes it in):
    the two stations (the kit's open-air Farm station scene, reused), the konbini and its weapon pads (the island's
    own `KONBINI_PADS`), the spawn, the parked cars, the zone markers and the world bounds.

Record frame throughout (the Road Kit's): x = Godot x, y = -Godot z, z = Godot y. Both networks sit at the origin.
Idempotent: the same inputs write the same files (uids are derived from names, not random).
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
sys.path.insert(0, os.path.join(ROOT, "blender", "lib"))
import point_model as pm          # noqa: E402
import point_presets as pr        # noqa: E402
import point_record_ops as ro     # noqa: E402
import island_roadgen as rg       # noqa: E402

PIECES = os.path.join(ROOT, "assets", "world_source", "pieces")
TERRAIN = os.path.join(ROOT, "assets", "world_source", "terrain", "debug_world.f32")
LAYOUT = os.path.join(ROOT, "assets", "world_source", "debug_world_layout.json")
GRID_X0, GRID_N, GRID_STEP = -512.0, 513, 2.0

PLAIN = 5.6            # the islands' flat ground (Godot Y): the big island's plain, and where paint_terrain turns
                       # sand into grass (GRASS_TOP 5.5)
ROAD_Z = PLAIN + 0.1   # every at-grade road station: draped 0.10 m over the plain (the stamp's clearance)
BED_Z = PLAIN + 0.1    # the rail bed; flush with the roads, so a level crossing needs no ramp
SEABED = -20.0

# (x0, x1, z0, z1, corner radius) in Godot axes
WEST_LAND = (-485.0, -35.0, -265.0, 265.0, 100.0)
EAST_LAND = (45.0, 415.0, -185.0, 185.0, 90.0)
# the rings' centrelines, RECORD frame (x0, x1, y0, y1, corner radius)
WEST_RING = (-445.0, -75.0, -225.0, 225.0, 45.0)
EAST_RING = (85.0, 375.0, -145.0, 145.0, 45.0)
NS_X = -260.0          # the west's inner N-S street
EW_Y = 0.0             # the west's inner E-W street, continued as the bridge
HUMP_Y = (-40.0, -190.0)  # record y span of the N-S street's embankment (south of the centre junction)
HUMP_H = 1.8
HILL = (230.0, 0.0, 12.0, 35.0)   # east island: a hill inside its ring (x, z, height, sigma)
# the CAUSEWAY each island runs out to a quay on the channel between them, so the bridge lands on FLAT ground and
# spans only water: on a sloping beach its abutments were FILL the stamp could not carry (probe_road_stamp)
CHANNEL = (-10.0, 20.0)           # Godot x of the two quay faces
CAUSEWAY_HALF = 30.0              # flat for |z| <= this, then down to the seabed over CAUSEWAY_EDGE
CAUSEWAY_EDGE = 15.0
QUAY_DROP = 4.0                   # the quay face: from the plain to the seabed over this many metres
MOUTH = 18.0           # a junction mouth's first guess from the crossing road's centreline (the setback solves it)
STEP = 25.0            # station spacing along a straight
BOUNDS = 510.0         # WorldBounds half extent: inside the terrain data (+/-512 m); the west ring's outer paving
                       # edge (463 m) stays outside its 40 m warning band

# the rail, RECORD frame
RAIL_A_Y = 110.0                  # station A's line (runs east)
RAIL_START_X = -420.0             # 20 m of track past A's west platform end
# A's centre; its platform is x -410 .. -320, its end buildings east of that and their entrance RAMPS (2026-09-28) to x
# ~-275, where the curve begins -- the buildings and ramps stand beside STRAIGHT track (a 3.0 m train measured on the
# old -290 start touched the east building's track wall where the line had begun to curve under it)
STATION_A = (-365.0, RAIL_A_Y)
ARC_START_X = -275.0
ARC_R = 160.0                     # the curve to B (metro minimum 160 m)
RAIL_B_X = ARC_START_X + ARC_R    # B's line (runs south): x -130
STATION_B = (RAIL_B_X, -120.0)    # B's centre; platform y -75 .. -165, end buildings south of that
RAIL_END_Y = -185.0               # 20 m past B's platform end
PLATFORM_M = 90.0                 # the Farm station's platform
STATION_SCENE = "res://src/main/resources/com/openworld/world/buildings/Station_Farm_Shop.tscn"
KONBINI_SCENE = "res://src/main/resources/com/openworld/world/buildings/KonbiniS_Shop.tscn"
KONBINI = (-330.0, 24.0, 180.0)   # Godot x, z, yaw (deg): on the E-W street's south side, facing it


# ------------------------------------------------------------------------------------------------ helpers
def uid_for(tag):
    """A stable uid per station: the record diffs only where the layout changed."""
    return "p_" + hashlib.sha1(tag.encode()).hexdigest()[:8]


def rrect_sdf(x, z, box):
    x0, x1, z0, z1, r = box
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx, hz = (x1 - x0) / 2 - r, (z1 - z0) / 2 - r
    dx, dz = abs(x - cx) - hx, abs(z - cz) - hz
    out = math.hypot(max(dx, 0.0), max(dz, 0.0))
    return out + min(max(dx, dz), 0.0) - r


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ground_at(x, z):
    """The natural ground: a flat plain inside each island, a beach, then the seabed."""
    h = SEABED
    for box in (WEST_LAND, EAST_LAND):
        d = rrect_sdf(x, z, box)
        if d < -18.0:
            v = PLAIN
        elif d < 12.0:
            v = PLAIN + (0.3 - PLAIN) * smooth((d + 18.0) / 30.0)     # the beach
        else:
            v = 0.3 + (SEABED - 0.3) * smooth((d - 12.0) / 80.0)
        h = max(h, v)
    if abs(z) < CAUSEWAY_HALF + CAUSEWAY_EDGE and WEST_LAND[1] - 20.0 < x < EAST_LAND[0] + 20.0:
        dx = max(CHANNEL[0] - x, x - CHANNEL[1])          # > 0 on the causeway, < 0 in the channel
        hc = PLAIN if dx >= 0 else PLAIN + (SEABED - PLAIN) * smooth(-dx / QUAY_DROP)
        wz = 1.0 - smooth((abs(z) - CAUSEWAY_HALF) / CAUSEWAY_EDGE)
        h = max(h, SEABED + (hc - SEABED) * wz)
    hx, hz, hh, hs = HILL
    h += hh * math.exp(-((x - hx) ** 2 + (z - hz) ** 2) / (2 * hs * hs))
    return h


def rrect_path(box, step=STEP, arc_step=10.0):
    """The rounded rectangle's centreline, counter-clockwise from a fifth of the way along its SOUTH side (record
    frame): the seam where the closed road starts and ends must not be where a junction goes (mid-side is)."""
    x0, x1, y0, y1, r = box
    pts = []

    def line(a, b):
        n = max(1, int(round(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
        for i in range(n):
            t = i / n
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))

    def arc(cx, cy, a0, a1):
        n = max(2, int(round(abs(a1 - a0) * r / arc_step)))
        for i in range(n):
            a = a0 + (a1 - a0) * i / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    mx = x0 + r + 0.2 * (x1 - x0 - 2 * r)
    line((mx, y0), (x1 - r, y0))
    arc(x1 - r, y0 + r, -math.pi / 2, 0.0)
    line((x1, y0 + r), (x1, y1 - r))
    arc(x1 - r, y1 - r, 0.0, math.pi / 2)
    line((x1 - r, y1), (x0 + r, y1))
    arc(x0 + r, y1 - r, math.pi / 2, math.pi)
    line((x0, y1 - r), (x0, y0 + r))
    arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
    line((x0 + r, y0), (mx, y0))
    return pts


def add_chain(net, name, pts3, preset, closed=False):
    road = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
    pr.apply_preset(net, name, preset)
    prev = None
    first = None
    for i, q in enumerate(pts3):
        p = net.add_station(road, (round(q[0], 3), round(q[1], 3), round(q[2], 3)), uid=uid_for("%s/%d" % (name, i)))
        if prev is not None:
            net.link(prev.uid, p.uid)
        first = first or p
        prev = p
    if closed:
        # a closed road ends ON its first station (a JOINT: coincident, same facing), as `island_roadgen.ring` does --
        # two stations a span apart linked across the seam export as two dead ends
        q = pts3[0]
        p = net.add_station(road, (round(q[0], 3), round(q[1], 3), round(q[2], 3)), uid=uid_for("%s/end" % name))
        net.link(prev.uid, p.uid)
        prev = p
        net.link(prev.uid, first.uid)
        rg.freeze(net, first.uid, (pts3[1][0] - pts3[-1][0], pts3[1][1] - pts3[-1][1]))
        rg.freeze(net, prev.uid, (pts3[1][0] - pts3[-1][0], pts3[1][1] - pts3[-1][1]))
    return road


def straight(a, b, z, step=STEP):
    n = max(1, int(round(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, z) for i in range(n + 1)]


# ------------------------------------------------------------------------------------------------ roads
def build_roads():
    net = pm.NetworkData()
    add_chain(net, "w_ring", [(x, y, ROAD_Z) for x, y in rrect_path(WEST_RING)], "arterial", closed=True)
    add_chain(net, "e_ring", [(x, y, ROAD_Z) for x, y in rrect_path(EAST_RING)], "arterial", closed=True)
    wx0, wx1, wy0, wy1, _r = WEST_RING
    ex0 = EAST_RING[0]
    # the inner N-S street, T into the ring at both ends
    # ... with an EMBANKMENT on its south half (nothing else is there): a 1.8 m hump over the flat ground, the fill
    # `probe_road_stamp` checks the stamp carries (the level causeway bridge has none)
    ns = straight((NS_X, wy1 - MOUTH), (NS_X, wy0 + MOUTH), ROAD_Z)
    h0, h1 = HUMP_Y
    ns = [(x, y, z + (HUMP_H * math.sin(math.pi * (y - h0) / (h1 - h0)) if h1 < y < h0 else 0.0)) for x, y, z in ns]
    add_chain(net, "w_ns", ns, "block")
    # the E-W street: from a T on the ring's west side to the centre, and from the centre to the ring's east side
    add_chain(net, "w_ew", straight((wx0 + MOUTH, EW_Y), (NS_X - MOUTH, EW_Y), ROAD_Z), "block")
    add_chain(net, "w_ew_e", straight((NS_X + MOUTH, EW_Y), (wx1 - MOUTH, EW_Y), ROAD_Z), "block")
    # the bridge: from the west ring's east side along the causeway, LEVEL over the channel, to the east ring
    xa, xb = wx1 + MOUTH, ex0 - MOUTH
    br = straight((xa, EW_Y), (xb, EW_Y), ROAD_Z, step=16.0)
    add_chain(net, "link", br, "arterial")

    def first(road):
        return net.roads[road].points[0]

    def last(road):
        return net.roads[road].points[-1]

    # junctions: cut the rings, then join the mouths
    a, b = rg.cut_road(net, (NS_X, wy1), "w_ring", MOUTH)
    rg.make_junction(net, [a, b, first("w_ns")])
    a, b = rg.cut_road(net, (NS_X, wy0), "w_ring", MOUTH)
    rg.make_junction(net, [a, b, last("w_ns")])
    a, b = rg.cut_road(net, (wx0, EW_Y), "w_ring", MOUTH)
    rg.make_junction(net, [a, b, first("w_ew")])
    a, b = rg.cut_road(net, (wx1, EW_Y), "w_ring", MOUTH)
    rg.make_junction(net, [a, b, last("w_ew_e"), first("link")])
    a, b = rg.cut_road(net, (ex0, EW_Y), "e_ring", MOUTH)
    rg.make_junction(net, [a, b, last("link")])
    a, b = rg.cut_road(net, (NS_X, EW_Y), "w_ns", MOUTH)
    rg.make_junction(net, [a, b, last("w_ew"), first("w_ew_e")])
    return net


# ------------------------------------------------------------------------------------------------ rail
def rail_plan():
    """[(x, y, s)] along the line: a straight east, a quarter circle south, a straight south."""
    pts = [(x, RAIL_A_Y) for x in linspace(RAIL_START_X, ARC_START_X, 20.0)]
    cx, cy = ARC_START_X, RAIL_A_Y - ARC_R
    n = 16
    for i in range(1, n + 1):
        t = (math.pi / 2) * i / n
        pts.append((cx + ARC_R * math.sin(t), cy + ARC_R * math.cos(t)))
    pts += [(RAIL_B_X, y) for y in linspace(cy, RAIL_END_Y, 20.0)[1:]]
    out, s = [], 0.0
    for i, p in enumerate(pts):
        if i:
            s += math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
        out.append((p[0], p[1], s))
    return out


def linspace(a, b, step):
    """a .. b inclusive, evenly, no gap longer than `step`."""
    n = max(1, int(math.ceil(abs(b - a) / step - 1e-9)))
    return [a + (b - a) * i / n for i in range(n + 1)]


def build_rail():
    import island_rail_record as IRR
    import station_layout as SL
    plan = rail_plan()
    s_of = lambda x, y: min(plan, key=lambda q: math.hypot(q[0] - x, q[1] - y))[2]
    reach = SL.BUILDING_LEN + 1.0
    spans = []
    for (sx, sy) in (STATION_A, STATION_B):
        sc = s_of(sx, sy)
        spans.append((sc - PLATFORM_M / 2, sc + PLATFORM_M / 2 + reach))
    # a station exactly where each span starts and ends, so the fence stands down over exactly the platform + building
    marks = [v for sp in spans for v in sp]
    pts = []
    for i, (x, y, s) in enumerate(plan):
        if i:
            px, py, ps = plan[i - 1]
            for m in marks:
                if ps + 0.5 < m < s - 0.5:
                    t = (m - ps) / (s - ps)
                    pts.append((px + (x - px) * t, py + (y - py) * t, m))
        pts.append((x, y, s))
    net = pm.NetworkData()
    road = net.add_road(pm.RoadData("rail_a", pm.PointData(uid=""), ()))
    prev = None
    made = []
    for i, (x, y, s) in enumerate(pts):
        p = net.add_station(road, (round(x, 3), round(y, 3), BED_Z), uid=uid_for("rail/%d" % i))
        made.append((p, s))
        if prev is not None:
            net.link(prev.uid, p.uid)
        prev = p
    pr.apply_preset(net, "rail_a", "rail")
    for p, s in made:
        if any(s0 - 1e-3 <= s < s1 - 1e-3 for s0, s1 in spans):
            p.platform_open = pm.EXIT_BOTH
    # the JOINT mid-curve: the line streams as two zones
    mid = min(made, key=lambda ps: abs(ps[1] - (s_of(*STATION_A) + s_of(*STATION_B)) / 2))[0]
    ro.split_at_joint(net, mid.uid, name="rail_b")
    return net, IRR


# ------------------------------------------------------------------------------------------------ outputs
def zones_doc(zones):
    return {"schema_ver": 1, "zones": [
        {"centre": [c[0], c[1], c[2]], "half": [h, h], "load_radius": lr, "marker": m, "unload_radius": ur,
         "zone_id": z} for z, m, c, h, lr, ur in zones]}


ROAD_ZONES = [("debug_a", "ZoneA", (-260.0, 0.0, PLAIN), 40.0, 500.0, 700.0),
              ("debug_b", "ZoneB", (230.0, 0.0, PLAIN), 40.0, 400.0, 600.0)]
RAIL_ZONES = [("rail_a", "RailA", (STATION_A[0], STATION_A[1], PLAIN), 40.0, 250.0, 350.0),
              ("rail_b", "RailB", (STATION_B[0], STATION_B[1], PLAIN), 40.0, 250.0, 350.0)]


def layout_doc():
    import island_buildings as IB
    import station_layout as SL
    stations = []
    for name, (sx, sy), u in (("DebugStationA", STATION_A, (1.0, 0.0)), ("DebugStationB", STATION_B, (0.0, -1.0))):
        stations.append({"name": name, "scene": STATION_SCENE, "pos": [sx, BED_Z, -sy],
                         "yaw_deg": math.degrees(SL.godot_yaw(*u))})
    kx, kz, kyaw = KONBINI
    ky = PLAIN + 0.02
    a = math.radians(kyaw)
    pads = [{"weapon": w, "pos": [round(kx + lx * math.cos(a) + lz * math.sin(a), 3), round(ky + 0.1, 3),
                                  round(kz - lx * math.sin(a) + lz * math.cos(a), 3)]}
            for w, lx, lz in IB.KONBINI_PADS["KonbiniS"]]
    zm = lambda zs, net, prefix: [{"name": m, "zone_id": z, "pos": [c[0], c[2], -c[1]], "load": lr, "unload": ur,
                                   "piece": "res://src/main/resources/com/openworld/world/pieces/Roads_%s_%s.tscn"
                                            % (net, z)} for z, m, c, h, lr, ur in zs]
    return {
        "note": "GENERATED by tools/debug_world_layout.py; tools/debug_world_scene.py writes it into DebugWorld.tscn",
        "bounds_half_extent": BOUNDS,
        "stations": stations,
        "konbini": {"scene": KONBINI_SCENE, "pos": [kx, ky, kz], "yaw_deg": kyaw, "pads": pads},
        "spawn": [-330.0, PLAIN + 0.5, 10.0],
        "cars": {"VehicleRoot": [-395.0, PLAIN + 0.9, 40.0], "KET1": [-395.0, PLAIN + 0.9, 50.0],
                 "POC1": [-395.0, PLAIN + 0.9, 60.0]},
        "pickups_offset": [-150.0, PLAIN - 14.0 + 1.0, 100.0],
        "ammo_refill": [-400.0, PLAIN + 0.75, 100.0],
        "road_zones": zm(ROAD_ZONES, "DebugRoads", ""),
        "rail_zones": zm(RAIL_ZONES, "DebugRail", ""),
    }


def terrain_bytes():
    import array
    out = array.array("f")
    for j in range(GRID_N):
        z = GRID_X0 + j * GRID_STEP
        for i in range(GRID_N):
            out.append(ground_at(GRID_X0 + i * GRID_STEP, z))
    return out.tobytes()


def seeded_uids(tag):
    """`point_model.new_uid` draws a random uid for every station a gesture makes (a junction mouth); seeded, a re-run
    writes the same record."""
    import itertools
    counter = itertools.count()
    pm.new_uid = lambda: uid_for("%s/gen/%d" % (tag, next(counter)))


def outputs():
    seeded_uids("roads")
    roads = build_roads()
    seeded_uids("rail")
    rail, _irr = build_rail()
    return {
        TERRAIN: terrain_bytes(),
        os.path.join(PIECES, "DebugRoads.roads.json"): roads,
        os.path.join(PIECES, "DebugRail.roads.json"): rail,
        os.path.join(PIECES, "DebugRoads.zones.json"): json.dumps(zones_doc(ROAD_ZONES), indent=1, sort_keys=True) + "\n",
        os.path.join(PIECES, "DebugRail.zones.json"): json.dumps(zones_doc(RAIL_ZONES), indent=1, sort_keys=True) + "\n",
        LAYOUT: json.dumps(layout_doc(), indent=1, sort_keys=True) + "\n",
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if a file would change")
    args = ap.parse_args(argv)
    stale = []
    for path, data in outputs().items():
        if isinstance(data, pm.NetworkData):
            tmp = path + ".new"
            pm.save_network(data, tmp)
            data = open(tmp).read()
            os.remove(tmp)
        mode = "wb" if isinstance(data, bytes) else "w"
        old = open(path, "rb" if mode == "wb" else "r").read() if os.path.exists(path) else None
        if old == data:
            continue
        stale.append(os.path.relpath(path, ROOT))
        if not args.check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, mode) as fh:
                fh.write(data)
    print("debug_world_layout: %s %s" % ("stale" if args.check else "wrote", stale or "nothing"))
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
