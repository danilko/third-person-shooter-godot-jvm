"""point_zones.py -- which ZONE each part of a road network streams with (PLAN.md 3.1 B6).

A world is authored as ONE continuous network and the build cuts it: every zone that owns road
content gets its own piece (`Roads_<network>_<zone>`), wired to that `ZoneMarker`'s
`Zone.geometry_path`, so roads stream in and out with the neighbourhood they belong to. This module
is the ONE owner of that cut. `roadkit_cli.py pieces` (the lanes, plain python3) and
`point_build.build_network` (the meshes, Blender) both ask it, so a lane can never land in one piece
while the tarmac under it lands in another.

THE UNIT IS THE RUN, NOT THE ROAD. A run is the stretch between two junction gaps
(`point_model.road_runs`) -- the unit the sweep and the lane export already build -- so a long
arterial crossing three neighbourhoods is cut at its own crossings rather than streaming whole
with whichever neighbourhood held most of it. Cutting mid-run is not offered: a carriageway split
between two pieces opens a seam in the asphalt exactly where the player is standing when the second
one streams in.

The rules, each a single decision:

- A STATION's zone is the SMALLEST zone box containing it (a zone inside a zone is the inner one --
  `CLAUDE.md` "a cell inside a cell is just a zone inside a zone"), else the nearest zone CENTRE
  within that zone's `load_radius`, else none. Boxes are XY in the kit frame, the XZ footprint of
  `Zone.size` about the marker.
- A RUN's zone is its road's authored `zone_id` when that names a zone in the file, else the
  majority of its stations' zones (ties to the lexically first id). An authored id naming no zone is
  reported (`zone_id_unknown`) and derived instead -- a piece wired to no marker never streams.
- A PAD goes with the zone at its clique's centre, else the majority of its mouths' runs.
- A GORE goes with the RAMP's run -- it carries the ramp's section and style (8h.3), so it carries
  its zone too.
- Nothing in any zone goes to the zone "" -- the network's resident piece, `Roads_<network>`, which
  is exactly what a network with no zones builds today.
- A run or pad reaching farther from its zone's centre than that zone's `load_radius` is reported
  (`zone_beyond_load`). A zone streams IN only inside its load radius, so a player arriving at such a
  stretch from a NEIGHBOURING zone can be standing on it while its piece is still out -- driving onto
  road that is not there. Inside the load radius that cannot happen: being on the stretch loads it,
  and hysteresis keeps it until the unload radius. Fix it in the data (a larger load radius, or a
  zone nearer that end), and leave a lead for the streaming time a fast car closes.

The zones file (`<stem>.zones.json`) is written by the Godot plugin from the scene's ZoneMarkers:

    {"schema_ver": 1, "zones": [{"zone_id": "harbour", "centre": [x, y, z], "half": [hx, hy],
                                 "load_radius": 200.0, "unload_radius": 350.0}]}
"""

import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "lib"))

try:
    from . import point_model as pm
except ImportError:
    import point_model as pm                                                 # noqa: E402

SCHEMA_VER = 1
#: The resident piece's key. A real zone id is never empty (`Zone.zoneId`), so this cannot collide.
RESIDENT = ""


class ZoneBox(object):
    __slots__ = ("zone_id", "cx", "cy", "hx", "hy", "load_radius", "unload_radius")

    def __init__(self, zone_id, centre, half, load_radius=0.0, unload_radius=0.0):
        self.zone_id = str(zone_id)
        self.cx, self.cy = float(centre[0]), float(centre[1])
        self.hx, self.hy = abs(float(half[0])), abs(float(half[1]))
        self.load_radius = float(load_radius or 0.0)
        #: 0 = not stated, and then nothing is checked against it.
        self.unload_radius = float(unload_radius or 0.0)

    def contains(self, x, y):
        return abs(x - self.cx) <= self.hx and abs(y - self.cy) <= self.hy

    def area(self):
        return 4.0 * self.hx * self.hy

    def distance(self, x, y):
        return math.hypot(x - self.cx, y - self.cy)


def zones_from_dict(d):
    out, seen = [], set()
    for z in (d or {}).get("zones", ()):
        zid = str(z.get("zone_id", ""))
        if not zid or zid in seen:
            # A zone with no id cannot be wired, and two markers with one id would both claim the
            # same piece -- the first wins and the plugin reports the second.
            continue
        seen.add(zid)
        out.append(ZoneBox(zid, z.get("centre", (0, 0)), z.get("half", (0, 0)),
                           z.get("load_radius", 0.0), z.get("unload_radius", 0.0)))
    return out


def load_zones(path):
    with open(path) as fh:
        return zones_from_dict(json.load(fh))


def zone_at(zones, x, y):
    inside = [z for z in zones if z.contains(x, y)]
    if inside:
        return min(inside, key=lambda z: (z.area(), z.zone_id)).zone_id
    near = [(z.distance(x, y), z.zone_id) for z in zones if z.distance(x, y) <= z.load_radius]
    return min(near)[1] if near else RESIDENT


def _majority(ids):
    counts = {}
    for i in ids:
        if i != RESIDENT:
            counts[i] = counts.get(i, 0) + 1
    if not counts:
        return RESIDENT
    return min(counts, key=lambda k: (-counts[k], k))


def piece_name(prefix, zone_id):
    """`Roads_<network>` for the resident piece, `Roads_<network>_<zone>` otherwise. Anything that
    is not a filename-and-node-name-safe character becomes `_`. ONE owner: the build script, the
    Blender loop and the plugin's marker wiring all read the name from here."""
    if zone_id == RESIDENT:
        return prefix
    return "%s_%s" % (prefix, re.sub(r"[^A-Za-z0-9_]", "_", zone_id))


class Partition(object):
    """The cut. `run_zone(uids)`, `pad_zone(uids)`, `gore_zone(ramp_uid)`; `pieces()` lists the
    zones that received anything, resident included when it is not empty."""

    def __init__(self):
        self.runs = {}          # first uid of the run -> zone
        self.run_of_uid = {}    # uid -> first uid of its run
        self.run_road = {}      # first uid -> road name
        self.pads = {}          # min uid of the clique -> zone
        self.gores = {}         # ramp uid -> zone
        self.findings = []      # {"code", "severity", "obj", "message"}

    def run_zone(self, uids):
        return self.runs.get(uids[0], RESIDENT) if uids else RESIDENT

    def pad_zone(self, uids):
        return self.pads.get(min(uids), RESIDENT) if uids else RESIDENT

    def gore_zone(self, ramp_uid):
        first = self.run_of_uid.get(ramp_uid)
        return self.runs.get(first, RESIDENT) if first else RESIDENT

    def pieces(self):
        """`{zone: {"runs": n, "pads": n, "gores": n}}`, only zones that own something."""
        out = {}
        for z in self.runs.values():
            out.setdefault(z, {"runs": 0, "pads": 0, "gores": 0})["runs"] += 1
        for z in self.pads.values():
            out.setdefault(z, {"runs": 0, "pads": 0, "gores": 0})["pads"] += 1
        for z in self.gores.values():
            out.setdefault(z, {"runs": 0, "pads": 0, "gores": 0})["gores"] += 1
        return out


def _finding(part, code, severity, obj, message):
    part.findings.append({"code": code, "severity": severity, "obj": obj, "message": message})


def _beyond_load(part, by_id, zone, xys, obj, what):
    z = by_id.get(zone)
    if z is None or z.load_radius <= 0.0 or not xys:
        return
    far = max(z.distance(x, y) for x, y in xys)
    if far > z.load_radius:
        _finding(part, "zone_beyond_load", "WARN", obj,
                 "%s reaches %.0f m from zone '%s''s centre, past its %.0f m load radius -- a player "
                 "coming from a neighbouring zone can reach that end before it streams in"
                 % (what, far, zone, z.load_radius))


def partition(net, zones):
    part = Partition()
    known = {z.zone_id for z in zones}
    by_id = {z.zone_id: z for z in zones}
    for name in sorted(net.roads):
        road = net.roads[name]
        authored = str(road.zone_id or "")
        if authored and authored not in known and zones:
            _finding(part, "zone_id_unknown", "WARN", name,
                     "road %s names zone '%s', which no ZoneMarker in the scene has -- placed by "
                     "its stations instead" % (name, authored))
        for uids in pm.road_runs(net, road):
            if not uids:
                continue
            if authored in known:
                zone = authored
            else:
                zone = _majority([zone_at(zones, *net.points[u].pos[:2]) for u in uids])
            part.runs[uids[0]] = zone
            part.run_road[uids[0]] = name
            for u in uids:
                part.run_of_uid[u] = uids[0]
            _beyond_load(part, by_id, zone, [net.points[u].pos[:2] for u in uids], uids[0],
                           "a run of road %s" % name)
            if zones and zone == RESIDENT:
                _finding(part, "zone_none", "WARN", uids[0],
                         "a run of road %s lies in no zone -- it goes to the resident piece, which "
                         "no ZoneMarker streams" % name)
    for comp in net.junction_cliques():
        cx = sum(net.points[u].pos[0] for u in comp) / len(comp)
        cy = sum(net.points[u].pos[1] for u in comp) / len(comp)
        zone = zone_at(zones, cx, cy)
        if zone == RESIDENT:
            zone = _majority([part.gore_zone(u) for u in comp])
        part.pads[min(comp)] = zone
        _beyond_load(part, by_id, zone, [net.points[u].pos[:2] for u in comp], min(comp),
                       "the junction pad at %s" % min(comp))
    for _main, ramp in net.aux_pairs():
        part.gores[ramp] = part.gore_zone(ramp)
    return part


# ------------------------------------------------------------------------------- lane documents

def stamp_lanes(doc, part, net):
    """Rewrite a whole `.lanekit.json` document's `zone_id`s from the cut: a run's lanes take their
    run's zone, a connector and its junction take the pad's. Called on `point_export.export_network`'s
    output, which still names each lane's run by `road_name` + arm -- so this reads the ARM, never
    the lane id's spelling."""
    arm_first = {}
    for name in sorted(net.roads):
        runs = pm.road_runs(net, net.roads[name])
        for i, uids in enumerate(runs):
            if uids:
                arm_first[_arm_name(name, i, len(runs))] = uids[0]
    for j in doc.get("junctions", ()):
        j["zone_id"] = part.pad_zone([a["point"] for a in j.get("arms", ())])
    jzone = {j["id"]: j["zone_id"] for j in doc.get("junctions", ())}
    for lane in doc.get("lanes", ()):
        if lane.get("junction_id") and lane.get("kind") == "connector":
            lane["zone_id"] = jzone.get(lane["junction_id"], RESIDENT)
        else:
            lane["zone_id"] = part.runs.get(arm_first.get(lane.get("from_arm")), RESIDENT)
    return doc


def _arm_name(road_name, run_index, n_runs):
    try:
        from . import point_export as pe
    except ImportError:
        import point_export as pe                                            # noqa: E402
    return pe.arm_name(road_name, run_index, n_runs)


def split_doc(doc, zone):
    """The piece of a stamped document that streams with `zone`: its lanes, its junctions, and the
    arms and roads they name. Successor names are kept as they are -- the runtime lane registry is
    global, so a `next` into a neighbouring zone's piece resolves once that piece is loaded."""
    lanes = [l for l in doc.get("lanes", ()) if l.get("zone_id", RESIDENT) == zone]
    arms_used = {l.get("from_arm") for l in lanes}
    roads_used = {l.get("road_name") for l in lanes}
    return dict(doc, lanes=lanes,
                junctions=[j for j in doc.get("junctions", ()) if j.get("zone_id") == zone],
                arms=[a for a in doc.get("arms", ()) if a.get("name") in arms_used],
                roads=[r for r in doc.get("roads", ()) if r.get("name") in roads_used])


def cross_zone_report(doc):
    """`(cross, dangling)`: successor edges that leave their lane's zone, and successor names no
    lane in the WHOLE document carries. Dangling is a defect; cross is the expected cost of a cut
    and is what `probe_road_zones.gd` resolves at runtime."""
    zone = {l["id"]: l.get("zone_id", RESIDENT) for l in doc.get("lanes", ())}
    cross, dangling = [], []
    for l in doc.get("lanes", ()):
        for n in l.get("next", ()):
            if n not in zone:
                dangling.append((l["id"], n))
            elif zone[n] != zone[l["id"]]:
                cross.append((l["id"], n))
    return cross, dangling


# ------------------------------------------------------------------------------- self-test

def self_test():
    ok = 0

    # zone_at: the inner of two nested boxes wins; outside every box the nearest centre within its
    # load radius; past every radius, none.
    outer = ZoneBox("city", (0, 0), (500, 500), 800)
    inner = ZoneBox("carpark", (100, 100), (20, 20), 60)
    far = ZoneBox("farm", (2000, 0), (100, 100), 300)
    zs = [outer, inner, far]
    assert zone_at(zs, 105, 95) == "carpark"
    assert zone_at(zs, -300, 0) == "city"
    assert zone_at(zs, 1750, 0) == "farm"
    assert zone_at(zs, 1000, 0) == RESIDENT          # past city's 800 m and farm's 300 m
    ok += 1
    assert zone_at([far], 1000, 0) == RESIDENT
    ok += 1
    assert _majority(["a", "b", "b", RESIDENT, RESIDENT, RESIDENT]) == "b"
    assert _majority(["b", "a"]) == "a"
    assert _majority([RESIDENT]) == RESIDENT
    ok += 1
    assert piece_name("Roads_X", RESIDENT) == "Roads_X"
    assert piece_name("Roads_X", "old town/2") == "Roads_X_old_town_2"
    ok += 1

    # A cross of two roads: split the world down x = 0 and check a run, its pad and its lanes.
    net = pm.NetworkData()
    ew = pm.RoadData("ew")
    net.add_road(ew)
    ns = pm.RoadData("ns")
    net.add_road(ns)
    xs = [-300, -150, -20, 20, 150, 300]
    e = [net.add_station(ew, (x, 0, 0)) for x in xs]
    n = [net.add_station(ns, (5, y, 0)) for y in xs]
    for chain in (e, n):
        for a, b in zip(chain, chain[1:]):
            if not (a is chain[2] and b is chain[3]):
                net.link(a.uid, b.uid, pm.LINK_SEGMENT)
    mouths = [e[2].uid, e[3].uid, n[2].uid, n[3].uid]
    for i, a in enumerate(mouths):
        for b in mouths[i + 1:]:
            net.link(a, b, pm.LINK_JUNCTION)
    west = ZoneBox("west", (-200, 0), (200, 400), 0)
    east = ZoneBox("east", (200, 0), (200, 400), 0)
    part = partition(net, [west, east])
    runs = {part.run_road[f] + "@" + f: z for f, z in part.runs.items()}
    assert part.run_zone([e[0].uid]) == "west" and part.run_zone([e[3].uid]) == "east", runs
    # The north-south road runs at x = 5: both its runs are EAST by majority, whatever their y.
    assert part.run_zone([n[0].uid]) == "east" and part.run_zone([n[3].uid]) == "east", runs
    ok += 1
    # The pad's centre is (2.5, 0) -> east.
    assert part.pad_zone(mouths) == "east"
    assert set(part.pieces()) == {"west", "east"} and not part.findings, (part.pieces(), part.findings)
    ok += 1
    # An authored zone_id wins when it names a zone, and is reported and ignored when it does not.
    ew.zone_id = "west"
    part = partition(net, [west, east])
    assert part.run_zone([e[3].uid]) == "west"
    ew.zone_id = "nowhere"
    part = partition(net, [west, east])
    assert part.run_zone([e[3].uid]) == "east"
    assert [f["code"] for f in part.findings] == ["zone_id_unknown"]
    ew.zone_id = ""
    ok += 1
    # A zone whose load radius the run outreaches is reported; a generous one is not.
    tight = ZoneBox("west", (-200, 0), (200, 400), 150, 600)
    part = partition(net, [tight, east])
    assert [f["code"] for f in part.findings] == ["zone_beyond_load"], part.findings
    assert not partition(net, [ZoneBox("west", (-200, 0), (200, 400), 400, 600), east]).findings
    ok += 1
    # No zones at all: everything is resident and nothing is reported -- today's one-piece build.
    part = partition(net, [])
    assert set(part.pieces()) == {RESIDENT} and not part.findings
    ok += 1

    # The lane documents: stamp, split, and every successor either stays or crosses -- none dangle.
    try:
        from . import point_export as pe
    except ImportError:
        import point_export as pe                                            # noqa: E402
    part = partition(net, [west, east])
    doc = stamp_lanes(pe.export_network(net), part, net)
    by_zone = {z: split_doc(doc, z) for z in part.pieces()}
    assert sum(len(d["lanes"]) for d in by_zone.values()) == len(doc["lanes"]) > 0
    assert all(l["zone_id"] in ("west", "east") for l in doc["lanes"])
    assert all(c["zone_id"] == "east" for c in doc["lanes"] if c.get("kind") == "connector")
    cross, dangling = cross_zone_report(doc)
    assert cross and not dangling, (len(cross), dangling)
    ok += 1
    print("point_zones self-test: %d group(s) OK" % ok)


if __name__ == "__main__":
    self_test()
