#!/usr/bin/env python3
"""island_layout.py -- the island's road LAYOUT, derived in one pass (PLAN.md 3.13).

    python3 tools/island_layout.py [--dry | --check]

The island's road record is two layers:

* `IslandRoads.arterials.roads.json` -- the INPUT: the arterials, the touge and the airport road as they were seeded
  and hand-fixed (W-series, 3.2d, 3.8). Edit the arterials HERE.
* `IslandRoads.roads.json` -- the OUTPUT, what Build, the zones and the game read. It is the input plus, in order:
    0. `island_coast_road.py add` -- the north-west coast road from its derived alignment (3.15);
    1. `island_touges.py add`  -- the mountain road (shrine touge, the summit straight, the east descent; 3.30 L2).
       The trunk grid is no longer a step: since the land redo it is part of the arterial layer
       (`island_network.py`, `island_plan.trunk_lines`);
    2. `island_streets.py`     -- the block streets and farm roads (step 4, 3.3);
    3. `island_expressway.py`  -- C1, the airport JCT and spur, the diamond (step 2; after the streets, so its pier
                                  pass sees them);
    4. `island_turnarounds.py` -- every road end a loop (3.3b);
    5. `roadkit_cli.py setback` -- every junction mouth solved;
    6. `island_grades.py smooth` -- every grade break rounded with a vertical curve (PLAN.md 0.7): each generator
                                  holds a LIMIT per span and says nothing about the CHANGE from one span to the
                                  next, so this is the one pass that owns it, over the arterials it did not
                                  generate as much as over the roads it did.
It then asserts the Road Kit gate (0 errors), a clean flow (0 broken / misjoined / unreached / orphaned / open ends),
that every road over another clears it by `roadkit_interchange.CLEARANCE` on the built surface, and that no ARTERIAL
climbs steeper than `ARTERIAL_GRADE` (`arterial_grades`). An arterial is pure DRAPE: nothing that builds it holds a
grade limit (a generated road does -- the touge's 10 %, a ramp's cone), so a terrain edit under one silently tilts it.
That is how the v16 junction on a 42 % slope hid. Pad grades are printed beside it (the gate's own `pad_grade` WARN,
on pads with an arterial mouth), not asserted: a pad's slope is a stop-line placement, fixed by moving a mouth.

A hand edit made to the OUTPUT in the editor is lost on the next run: make it in the input, or in the generator that
owns the road. After this: sample the ground (`write_roadkit_ground.gd`), `island_road_zones.py --split`, build, stamp,
the traffic zones and the road map (PLAN.md "Road Kit gate"). `--dry` derives into a temp dir and writes nothing; `--check` derives nothing and runs the asserts on the
committed output.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PIECES = os.path.join(ROOT, "assets", "world_source", "pieces")
INPUT = os.path.join(PIECES, "IslandRoads.arterials.roads.json")
OUTPUT = os.path.join(PIECES, "IslandRoads.roads.json")
CLI = os.path.join(ROOT, "blender", "tools", "roadkit_cli.py")
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402


ARTERIAL_GRADE = 0.06   # steepest an arterial may climb, over ARTERIAL_SPAN of road (a Japanese urban trunk road's
                        # design maximum is 5-6 % at 60 km/h; the island's arterials measure <= 2.4 % after v16)
ARTERIAL_SPAN = 20.0    # grades are measured over at least this much road, so a 1 m station pair cannot read as a
                        # wall from a millimetre of float noise


def arterial_names(record=INPUT):
    """The arterial layer's road names, with a zone split's `__<n>` suffixes stripped (the output record carries the
    same street as several roads)."""
    return {r["name"].split("__")[0] for r in json.load(open(record))["roads"]}


def arterial_grades(path, names):
    """[(grade, road, (x, y))] -- each arterial road's steepest climb over >= ARTERIAL_SPAN of road, steepest first."""
    net = pm.load_network(path)
    out = []
    for nm, road in net.roads.items():
        if nm.split("__")[0] not in names:
            continue
        ch = net.chain(road)
        best = (0.0, (0.0, 0.0))
        for i in range(len(ch)):
            d = 0.0
            for j in range(i + 1, len(ch)):
                d += math.dist(ch[j - 1].pos[:2], ch[j].pos[:2])
                if d >= ARTERIAL_SPAN:
                    g = abs(ch[j].pos[2] - ch[i].pos[2]) / d
                    if g > best[0]:
                        best = (g, (round(ch[i].pos[0]), round(ch[i].pos[1])))
                    break
        out.append((best[0], nm, best[1]))
    return sorted(out, reverse=True)


def run(*cmd):
    r = subprocess.run([sys.executable] + list(cmd), capture_output=True, text=True)
    if r.returncode:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit("island_layout: %s failed" % os.path.basename(cmd[0]))
    return r.stdout


def derive(out):
    tmp = out + ".grid.json"
    sys.stdout.write(run(os.path.join(HERE, "island_coast_road.py"), "add", tmp, "--from", INPUT))
    sys.stdout.write(run(os.path.join(HERE, "island_touges.py"), "add", tmp))
    # the expressway BEFORE the streets (since the land redo): the streets must route round its interchanges, and
    # the order the other way round (for the old station-span pier pass) is retired -- the build drops each pier that
    # would stand on a road, column by column (`point_mesh.pier_on_road`)
    sys.stdout.write(run(os.path.join(HERE, "island_expressway.py"), out, "--from", tmp, "--fast"))
    os.remove(tmp)
    sys.stdout.write(run(os.path.join(HERE, "island_streets.py"), out))
    sys.stdout.write(run(os.path.join(HERE, "island_turnarounds.py"), out))
    moved = json.loads(run(CLI, "setback", out))
    print("island_layout: setback moved %d mouth(s)" % len(moved["moved"]))
    print("island_layout: " + tidy(out))
    sys.stdout.write(run(os.path.join(HERE, "island_grades.py"), "smooth", out))
    print("island_layout: " + weld_joints(out))


def joint_pairs(net):
    """Every JOINT: two stations of DIFFERENT roads, SEGMENT-linked, within 0.5 m in plan."""
    import point_model as pm
    road_of = {q: n for n, r in net.roads.items() for q in r.points}
    out = []
    for u, p in net.points.items():
        for l in p.links:
            v = l.target
            if l.type != pm.LINK_SEGMENT or v not in net.points or u >= v or road_of.get(u) == road_of.get(v):
                continue
            q = net.points[v]
            if ((p.pos[0] - q.pos[0]) ** 2 + (p.pos[1] - q.pos[1]) ** 2) ** 0.5 < 0.5:
                out.append((u, v))
    return out


def weld_joints(path):
    """A JOINT'S TWO STATIONS ARE ONE POINT, HEIGHT INCLUDED. The generators build joints coincident, but a later pass
    can move one half only -- measured: ring_kita met kaigan_machi 0.107 m apart in height, so the coast road's first
    metre stood above the ring's outer lane and the terrain stamp, taking the nearer surface, put the ground 2 cm OVER
    that lane (probe_road_stamp). Both take their mean. Run last, after the grade smoothing."""
    sys.path.insert(0, HERE)
    import island_roadgen  # noqa: F401  (the kit's path)
    import point_model as pm
    net = pm.load_network(path)
    n, worst = 0, 0.0
    for u, v in joint_pairs(net):
        a, b = net.points[u], net.points[v]
        dz = abs(a.pos[2] - b.pos[2])
        if dz > 1e-4:
            m = (a.pos[2] + b.pos[2]) / 2.0
            a.pos = (a.pos[0], a.pos[1], m)
            b.pos = (b.pos[0], b.pos[1], m)
            n += 1
            worst = max(worst, dz)
    pm.save_network(net, path)
    return "weld: %d joint(s) brought to one height (worst %.3f m apart)" % (n, worst)


def tidy(path):
    """What the generators leave that only the whole network shows, fixed once:
      * a PAD OF TWO ARMS -- a street cut a road to land a junction and was then dropped, leaving the road's two halves
        on a pad (`junction_too_small`). It becomes a JOINT: the two mouths meet at their midpoint, SEGMENT-linked;
      * a station within a solved mouth's clear distance (`station_crowds_mouth`): the setback moved the mouth over it.
        The station goes; its chain neighbours are linked."""
    sys.path.insert(0, HERE)
    import island_roadgen  # noqa: F401  (the kit's path)
    import point_model as pm
    import point_validate as pv
    net = pm.load_network(path)
    joints = 0
    seen = set()
    for u, p in list(net.points.items()):
        js = [l.target for l in p.links if l.type == pm.LINK_JUNCTION]
        if len(js) != 1 or u in seen:
            continue
        v = js[0]
        if len([l for l in net.points[v].links if l.type == pm.LINK_JUNCTION]) != 1:
            continue
        seen |= {u, v}
        a, b = net.points[u], net.points[v]
        mid = tuple((a.pos[k] + b.pos[k]) / 2 for k in range(3))
        net.unlink(u, v)
        a.pos = b.pos = mid
        a.role = b.role = pm.SEGMENT
        a.traffic_light = b.traffic_light = False
        net.link(u, v)
        joints += 1
    road_of = {q: n for n, r in net.roads.items() for q in r.points}
    dropped = 0
    for f in pv.validate(net):
        if f.code != "station_crowds_mouth" or f.obj not in net.points:
            continue
        r = net.roads[road_of[f.obj]]
        k = r.points.index(f.obj)
        if k == 0 or k == len(r.points) - 1:
            continue
        a, b = r.points[k - 1], r.points[k + 1]
        net.remove_point(f.obj)
        if f.obj in r.points:
            r.points.remove(f.obj)
        net.link(a, b)
        dropped += 1
    pm.save_network(net, path)
    return "tidy: %d two-arm pad(s) made joints, %d crowding station(s) removed" % (joints, dropped)


def main(argv):
    if "--dry" in argv:
        d = tempfile.mkdtemp()
        try:
            out = os.path.join(d, "IslandRoads.roads.json")
            derive(out)
            print("island_layout: derived %s" % out)
        finally:
            shutil.rmtree(d)
        return
    if "--check" not in argv:
        derive(OUTPUT)
    rep = json.loads(run(CLI, "validate", OUTPUT))
    flow = json.loads(run(CLI, "flow", OUTPUT))["report"]
    bad = {k: len(flow[k]) for k in ("broken", "misjoined", "unreached", "ramp_orphans", "open_end")}
    print("island_layout: %d errors, %d warnings; flow %d lanes %s -> %s"
          % (rep["errors"], rep["warnings"], flow["lanes"], bad, OUTPUT))
    # every road over another clears it, measured on the built surface (roadkit_interchange.crossings)
    sys.path.insert(0, HERE)
    import roadkit_interchange as ri
    cross = ri.crossings(OUTPUT)
    low = [c for c in cross if c[0] < ri.CLEARANCE]
    print("island_layout: %d grade-separated crossings, tightest %.1f m (%s over %s)%s"
          % (len(cross), cross[0][0], cross[0][1], cross[0][2], "" if not low else "; %d BELOW %.1f m: %s"
             % (len(low), ri.CLEARANCE, low)))
    names = arterial_names()
    grades = arterial_grades(OUTPUT, names)
    steep = [g for g in grades if g[0] > ARTERIAL_GRADE]
    print("island_layout: %d arterial road(s), steepest %.1f %% (%s at %s)%s"
          % (len(grades), grades[0][0] * 100, grades[0][1], grades[0][2], "" if not steep else
             "; %d OVER %.0f %%: %s" % (len(steep), ARTERIAL_GRADE * 100,
                                         ", ".join("%s %.1f %% at %s" % (n, g * 100, p) for g, n, p in steep))))
    owner = {u: nm for nm, r in pm.load_network(OUTPUT).roads.items() for u in r.points}
    for f in rep["findings"]:
        if f["code"] == "pad_grade":
            roads = [owner.get(u, u) for u in re.findall(r"p_[0-9a-f]{8}", f["message"])]
            if any(r.split("__")[0] in names for r in roads):
                print("island_layout: pad_grade on an arterial pad (%s): %s" % (" / ".join(roads), f["message"][:60]))
    if rep["errors"] or any(bad.values()) or low or steep:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
