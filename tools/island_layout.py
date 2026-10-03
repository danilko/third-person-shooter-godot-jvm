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
    2. `island_core_streets.py` -- the AUTHORED streets the grid cannot make (the farm's frame, the core's back streets);
       `island_streets.py`     -- the block streets and farm roads (step 4, 3.3);
       `island_site_access.py` -- each site's access road to its visitor car park (3.23, B8), a declared dead end;
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

Each generator step is replayed from a content-addressed cache when its input record, its code (the script and every
module it imports) and its data are what they were last time (`tools/layout_cache.py`): edit island_streets.py and the
coast road, touge, dike and expressway steps before it replay in seconds. `--no-cache` (or LAYOUT_CACHE=0) runs every
step.
"""
import json
import math
import os
import re
import shutil
import subprocess
import time
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


TIMES = {}     # step -> seconds, summed over the run (printed by main: which generator a slow layout is waiting on)


CACHE = os.environ.get("LAYOUT_CACHE", "1") != "0"     # `--no-cache` clears it (main); see tools/layout_cache.py
HITS = []


def run(*cmd):
    """One generator step, replayed from `layout_cache` when its record, its code and its data are what they were the
    last time it ran (a step's output record is its first `.json` argument; a read-only step restores the same
    bytes)."""
    t0 = time.monotonic()
    step = os.path.basename(cmd[0]).replace(".py", "") + ("" if len(cmd) < 2 or "/" in cmd[1] else " " + cmd[1])
    out = next((a for a in cmd[1:] if a.endswith(".json")), None)
    k = None
    if CACHE:
        import layout_cache as LC
        k = LC.key(cmd, out)
        hit = LC.get(k, out)
        if hit is not None:
            HITS.append(step)
            TIMES[step + " (cached)"] = TIMES.get(step + " (cached)", 0.0) + time.monotonic() - t0
            return hit
    r = subprocess.run([sys.executable] + list(cmd), capture_output=True, text=True)
    TIMES[step] = TIMES.get(step, 0.0) + time.monotonic() - t0
    if r.returncode:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit("island_layout: %s failed" % os.path.basename(cmd[0]))
    if k:
        LC.put(k, out, r.stdout)
    return r.stdout


def derive(out):
    tmp = out + ".grid.json"
    # the dike corridor is this run's own (island_dike.py raise writes it before the expressway): a stale one would
    # stand an old crest in the ground the coast road and the touge are derived on
    stale = os.path.join(ROOT, "assets", "world_source", "island_dike_line.json")
    if os.path.exists(stale):
        os.remove(stale)
    sys.stdout.write(run(os.path.join(HERE, "island_coast_road.py"), "add", tmp, "--from", INPUT))
    sys.stdout.write(run(os.path.join(HERE, "island_touges.py"), "add", tmp))
    # the ring road is the dike (user, 2026-09-26): its crest heights and the arterials' ramps BEFORE the streets,
    # which then keep off the embankment (island_dike.CORRIDOR) and never T into it
    sys.stdout.write(run(os.path.join(HERE, "island_dike.py"), "raise", tmp))
    # the 側道 along the embankment's town side, below the ramps: what the block streets end on now
    sys.stdout.write(run(os.path.join(HERE, "island_dike.py"), "sokudo", tmp))
    # the expressway BEFORE the streets (since the land redo): the streets must route round its interchanges, and
    # the order the other way round (for the old station-span pier pass) is retired -- the build drops each pier that
    # would stand on a road, column by column (`point_mesh.pier_on_road`)
    sys.stdout.write(run(os.path.join(HERE, "island_expressway.py"), out, "--from", tmp, "--fast"))
    os.remove(tmp)
    # the AUTHORED streets the grid planner cannot make (the farm's frame, the core's 裏通り behind C1): before the
    # planner, so its farm rows end on the frame's legs
    sys.stdout.write(run(os.path.join(HERE, "island_core_streets.py"), out))
    sys.stdout.write(run(os.path.join(HERE, "island_streets.py"), out))
    sys.stdout.write(run(os.path.join(HERE, "island_site_access.py"), out))
    sys.stdout.write(run(os.path.join(HERE, "island_turnarounds.py"), out))
    sys.stdout.write(run(os.path.join(HERE, "island_dike.py"), "raise", out))     # ramps for the later roads
    # a mouth past (or inside) the road it meets -- a road that overshot the crossing -- is moved back out first: the
    # setback solve slides a mouth along its own road and cannot recover one that crossed over (check_mouth_sides)
    # ...and again after each solve, which moves pad centres: until no mouth is wrong (at most 3 rounds)
    for rnd in range(3):
        fixed = run(os.path.join(HERE, "check_mouth_sides.py"), "--fix", out).splitlines()[0]
        print("island_layout: round %d: %s" % (rnd + 1, fixed.replace("check_mouth_sides: ", "")))
        moved = json.loads(run(CLI, "setback", out))
        print("island_layout: setback moved %d mouth(s)" % len(moved["moved"]))
        if subprocess.run([sys.executable, os.path.join(HERE, "check_mouth_sides.py"), out],
                          capture_output=True).returncode == 0:
            break
    else:
        # the solve keeps sliding a mouth back in (a T at a shallow angle): fix it once more and LOCK its setback
        fixed = run(os.path.join(HERE, "check_mouth_sides.py"), "--fix-lock", out).splitlines()[0]
        print("island_layout: locked: %s" % fixed.replace("check_mouth_sides: ", ""))
    # A MOUTH HELD SHORT OF ITS SOLVED SETBACK by the station behind it (the solve never slides a mouth over one)
    # leaves its cap -- kerb and footway -- inside the crossing road's carriageway: the "pavement poking into the road"
    # (user, 2026-09-26, postal 9-14: jokamachi_dori held at 4.5 m of a solved 15.9). That station goes and the
    # setback is solved again, until nothing is held (an end or a junction station is never removed; reported)
    for _ in range(4):
        held = [c for c in (moved.get("clamped") or []) if c.get("solved", 0.0) <= UNCLAMP_MAX]
        if not held:
            break
        n = unclamp(out, held)
        print("island_layout: setback held %d mouth(s) short; %d blocking station(s) removed" % (len(held), n))
        if not n:
            break
        moved = json.loads(run(CLI, "setback", out))
    if moved.get("clamped"):
        print("island_layout: WARN %d mouth(s) still held short of their setback: %s"
              % (len(moved["clamped"]), [(c["uid"], round(c["placed"], 1), round(c["solved"], 1))
                                         for c in moved["clamped"]][:8]))
    t0 = time.monotonic()
    print("island_layout: " + tidy(out))
    TIMES["tidy (in-process)"] = time.monotonic() - t0
    sys.stdout.write(run(os.path.join(HERE, "island_grades.py"), "smooth", out))
    sys.stdout.write(run(os.path.join(HERE, "island_dike.py"), "raise", out))     # the crest back after smoothing
    t0 = time.monotonic()
    print("island_layout: " + weld_joints(out))
    TIMES["weld (in-process)"] = time.monotonic() - t0


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
    # ...AND ONE FACING. A joint station takes its own road's chord, so two AUTO halves meeting at a bend (a side road
    # detoured round a station box put a 14 deg bend on teibo_sokudo_4's joint) cut their sections on different
    # planes and hand each lane over sideways (0.54 m, joint_gaps). Both are frozen on the bisector of their two
    # chords, each facing its OWN road's forward direction (a station's facing is its road's direction of travel).
    # A joint a generator already froze (the expressway's, the Wangan's split) is left as it is.
    import math
    road_of = {q: nm for nm, r in net.roads.items() for q in r.points}
    faced = 0
    for u, v in joint_pairs(net):
        a, b = net.points[u], net.points[v]
        if a.tangent_mode == pm.MANUAL or b.tangent_mode == pm.MANUAL:
            continue
        ds = []
        for q in (u, v):
            ch = net.roads[road_of[q]].points
            if len(ch) < 2:
                break
            i = ch.index(q)
            p0, p1 = (net.points[ch[i - 1]].pos, net.points[q].pos) if i == len(ch) - 1 else \
                (net.points[q].pos, net.points[ch[i + 1]].pos)
            L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            ds.append((((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)) if L > 1e-6 else None)
        if len(ds) < 2 or None in ds:
            continue
        (ax, ay), (bx, by) = ds
        s = 1.0 if ax * bx + ay * by >= 0.0 else -1.0
        tx, ty = ax + s * bx, ay + s * by
        L = math.hypot(tx, ty)
        if L < 1e-6:
            continue
        tx, ty = tx / L, ty / L
        a.tangent_mode, a.tangent = pm.MANUAL, (tx, ty, 0.0)
        b.tangent_mode, b.tangent = pm.MANUAL, (s * tx, s * ty, 0.0)
        faced += 1
    pm.save_network(net, path)
    return ("weld: %d joint(s) brought to one height (worst %.3f m apart), %d given one facing"
            % (n, worst, faced))


UNCLAMP_MAX = 40.0    # m: only a mouth whose solved setback is an ordinary one is freed (see `unclamp`)


def unclamp(path, held):
    """Remove each station that holds a mouth short of its solved setback (`roadkit_cli setback`'s "clamped"), if it
    is an interior, ordinary station of its road. Returns how many went."""
    sys.path.insert(0, HERE)
    import island_roadgen  # noqa: F401  (the kit's path)
    import point_model as pm
    net = pm.load_network(path)
    road_of = {q: n for n, r in net.roads.items() for q in r.points}
    gone = 0
    for c in held:
        if c.get("solved", 0.0) > UNCLAMP_MAX:          # a shallow-angle pad solving to hundreds of metres: not this
            continue
        st = c.get("station")
        if not st or st not in net.points or st not in road_of:
            continue
        r = net.roads[road_of[st]]
        k = r.points.index(st)
        p = net.points[st]
        if k == 0 or k == len(r.points) - 1 or str(p.role) != pm.SEGMENT or p.pillar_skip \
                or any(l.type != pm.LINK_SEGMENT for l in p.links):
            continue
        a, b = r.points[k - 1], r.points[k + 1]
        net.remove_point(st)
        if st in r.points:
            r.points.remove(st)
        net.link(a, b)
        gone += 1
    pm.save_network(net, path)
    return gone


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
    # a two-arm pad at a CORNER (two street segments that only meet each other, e.g. both cut short by a station box)
    # cannot be a joint -- a lane cannot hand over round a right angle at one station -- so BOTH segments go (generated
    # streets only; a street is one road per block, so this trims each back to its previous junction), which may leave
    # those pads with two arms: repeat until nothing changes
    removed = 0
    import math as _m
    while True:
        road_of = {q: n for n, r in net.roads.items() for q in r.points}
        gone = None
        # a generated segment an earlier removal left ending on NOTHING (its pad lost every other arm) goes too
        for name, r in net.roads.items():
            if not name.split("__")[0].startswith(GENERATED_STREETS) or len(r.points) < 2:
                continue
            ends = (net.points[r.points[0]], net.points[r.points[-1]])
            if any(not any(l.type == pm.LINK_JUNCTION or (l.type == pm.LINK_SEGMENT and road_of.get(l.target) != name)
                           for l in e.links) for e in ends):
                gone = {name}
                break
        for u, p in ([] if gone else net.points.items()):
            js = [l.target for l in p.links if l.type == pm.LINK_JUNCTION]
            if len(js) != 1 or len([l for l in net.points[js[0]].links if l.type == pm.LINK_JUNCTION]) != 1:
                continue
            v = js[0]
            dirs, lens = [], []
            for w in (u, v):
                ch = net.roads[road_of[w]].points
                nxt = ch[1] if ch[0] == w else ch[-2]
                a_, b_ = net.points[w].pos, net.points[nxt].pos
                dirs.append((b_[0] - a_[0], b_[1] - a_[1]))
                pts_ = [net.points[q].pos for q in ch]
                lens.append(sum(_m.dist(x[:2], y[:2]) for x, y in zip(pts_, pts_[1:])))
            (ax, ay), (bx, by) = dirs
            cos = (ax * bx + ay * by) / ((_m.hypot(ax, ay) * _m.hypot(bx, by)) or 1.0)
            if cos < -0.87:                               # nearly opposite: a straight joint
                continue
            names = {road_of[u], road_of[v]}
            if not all(n.split("__")[0].startswith(GENERATED_STREETS) for n in names):
                continue
            gone = names
            break
        if gone is None:
            break
        for name in gone:
            for q in list(net.roads[name].points):
                net.remove_point(q)
            del net.roads[name]
            removed += 1
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
    # only the check that reports it: the whole gate (`pv.validate`) spent 139 of tidy's 149 s fitting every lane's
    # curve (check_path_fidelity) for a finding it then threw away
    for f in pv.validate(net, checks=[pv.check_mouth_clearance]):
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
    return ("tidy: %d two-arm pad(s) made joints, %d corner street segment(s) removed, %d crowding station(s) removed"
            % (joints, removed, dropped))


GENERATED_STREETS = ("machi", "cho", "nishi_machi", "nishi_cho", "koba_", "kita_", "hata_", "kojo_", "kogai_",
                     "butsuryu_yoko", "teibo_sokudo")

FOLD_DEG = 120.0        # a chain turning back more than this at one station is a U-turn drawn as a road


JOINT_GAP = 0.25     # m: a lane handed across a road-to-road SEGMENT link should meet its successor this closely. REPORTED,
#                      not yet asserted: two older joints hand over 3.4 m (kaigan_machi / ring_kita, two cross-sections)
#                      and 3.0 m (nishi_machi_1160 / nishi_cho_495) sideways (PLAN.md, 2026-09-25)


def joint_gaps(path):
    """[(gap m, lane, successor)] for every lane handed to a DIFFERENT road's plain lane (a joint), worst first.
    `point_export.wire_joints` pairs a tail with the nearest head within 4.5 m, so a joint whose stations sit on the
    wrong side of each other (a divided road parting into two one-way roads half a median to the wrong side) is
    wired 1 m off and every other check still passes (the Wangan split, 2026-09-25)."""
    import point_model as pm
    import point_export as pe
    doc = pe.export_network(pm.load_network(path))
    by = {l["id"]: l for l in doc["lanes"]}
    out = []
    for l in doc["lanes"]:
        if l.get("kind") == "connector":
            continue
        for n in l.get("next", []):
            d = by.get(n)
            if d is None or d.get("kind") == "connector" or d.get("road_name") == l.get("road_name"):
                continue
            out.append((math.dist(l["points"][-1], d["points"][0]), l["id"], n))
    return sorted(out, reverse=True)


def chain_folds(path):
    """Every station where a road's chain turns BACK on itself (user, 2026-09-25, postal 14-14): a road that must
    come back to itself does so through a JUNCTION and a loop (`island_turnarounds`), never by folding its own chain,
    which lays its kerbs and footway across its own lanes. Returns [(road, uid, turn deg)]."""
    net = pm.load_network(path)
    out = []
    for name, r in net.roads.items():
        ps = [net.points[u].pos for u in r.points if u in net.points]
        for i in range(1, len(ps) - 1):
            u = (ps[i][0] - ps[i - 1][0], ps[i][1] - ps[i - 1][1])
            v = (ps[i + 1][0] - ps[i][0], ps[i + 1][1] - ps[i][1])
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 1e-6 or lv < 1e-6:
                continue
            turn = math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))))
            if turn > FOLD_DEG:
                out.append((name, r.points[i], turn))
    return out


PHASE2_ALONG = 60.0   # m: a road may cross the held phase-2 corridor (it will pass UNDER the elevated Wangan), not run in it


def phase2_intrusions(path):
    """What stands in the held PHASE-2 ground (island_plan.PHASE2_*, PLAN.md NEXT): [(what, name, detail)].
    * a road running ALONG the corridor or through the T's footprint for more than PHASE2_ALONG (a crossing is allowed:
      the Wangan will be elevated over it); the spur itself is the T's mainline and is allowed there;
    * a frozen site or a civic plot overlapping it."""
    import island_plan as PL
    import island_core_streets as CS
    authored = {st["name"] for st in CS.STREETS}           # the core's AUTHORED streets (the suburb loop) are there too
    net = pm.load_network(path)
    boxes = PL.phase2_boxes()

    def inside(x, y, box):
        cx, cy, c, s_, ha, hc = box
        u, v = (x - cx) * c + (y - cy) * s_, -(x - cx) * s_ + (y - cy) * c
        return abs(u) <= ha and abs(v) <= hc
    out = []
    for name, r in net.roads.items():
        # what may NOT stand in it is what a later layout can put there: a generated block street, or another
        # expressway road. The roads already there (the ring on its dike, the suburb loop, the arterials) pass UNDER
        # the elevated phase-2 Wangan and are its business to clear, as the spur's are today.
        # phase 2 is BUILT (2026-09-30, the complete Wangan): the corridor is the expressway's own, so no shuto_ road
        # is an intrusion
        if name.startswith("shuto_") \
                or not name.split("__")[0].startswith(GENERATED_STREETS + ("shuto_",)) \
                or name.split("__")[0] in authored:
            continue
        ps = [net.points[u].pos for u in r.points if u in net.points]
        for box in boxes:
            run = 0.0
            for a, b in zip(ps, ps[1:]):
                L = math.dist(a[:2], b[:2])
                n = max(1, int(L // 4.0))
                for k in range(n):
                    t = (k + 0.5) / n
                    if inside(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, box):
                        run += L / n
            if run > PHASE2_ALONG:
                out.append(("road", name, "%.0f m inside" % run))
                break
    for fn, key in (("IslandSites.json", "sites"), ("IslandCivicSites.json", "plots")):
        fp = os.path.join(ROOT, "assets", "world_source", "buildings", fn)
        if not os.path.exists(fp):
            continue
        for st in json.load(open(fp)).get(key, []):
            sx, sy = (st.get("size") or [0.0, 0.0])[:2]
            a = math.radians(st.get("yaw", 0.0))
            for gx in (-0.5, 0.0, 0.5):
                for gy in (-0.5, 0.0, 0.5):
                    lx, ly = gx * sx, gy * sy
                    x = st["x"] + lx * math.cos(a) - ly * math.sin(a)
                    y = st["y"] + lx * math.sin(a) + ly * math.cos(a)
                    if any(inside(x, y, b) for b in boxes):
                        out.append(("site", st.get("id", "?"), "at (%.0f, %.0f)" % (st["x"], st["y"])))
                        break
                else:
                    continue
                break
    return out


def one_way_stretches(path, near=25.0):
    """Every JOINT where a divided expressway parts into two one-way roads (a JCT's split): [(parallel m, divided road,
    one-way pair)] -- how far back from the joint the two one-way roads still run within `near` m of each other. The
    rule (user, 2026-09-29 night): "keep it one highway as soon as possible" -- a long parallel pair is two long ramps
    doing the divided road's job. REPORTED, not asserted."""
    net = pm.load_network(path)
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    out = []
    for u, p in net.points.items():
        n = road_of.get(u)
        if not n or not n.startswith("shuto_"):
            continue
        r = net.roads[n]
        if r.base.lanes_bwd == 0 or r.base.lanes_fwd == 0 or u not in (r.points[0], r.points[-1]):
            continue
        halves = [road_of[l.target] for l in p.links if l.type == pm.LINK_SEGMENT and road_of.get(l.target) != n]
        halves = [h for h in halves if net.roads[h].base.lanes_bwd == 0 or net.roads[h].base.lanes_fwd == 0]
        if len(halves) != 2:
            continue

        def poly(h):
            ch = net.roads[h].points
            ps = [net.points[q].pos[:2] for q in ch]
            return ps if math.dist(ps[0], p.pos[:2]) < math.dist(ps[-1], p.pos[:2]) else ps[::-1]
        A, B = poly(halves[0]), poly(halves[1])

        def dist_to(q, P):
            best = 1e18
            for a, b in zip(P, P[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy or 1e-9
                t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
                best = min(best, math.hypot(a[0] + dx * t - q[0], a[1] + dy * t - q[1]))
            return best
        run = 0.0
        for a, b in zip(A, A[1:]):
            L = math.dist(a, b)
            n_ = max(1, int(L // 4.0))
            stop = False
            for k in range(n_):
                t = (k + 0.5) / n_
                if dist_to((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), B) > near:
                    stop = True
                    break
                run += L / n_
            if stop:
                break
        out.append((run, n, tuple(sorted(halves))))
    return sorted(out, reverse=True)


def main(argv):
    global CACHE
    if "--no-cache" in argv:
        CACHE = False
    if "--dry" in argv:
        d = tempfile.mkdtemp()
        try:
            out = os.path.join(d, "IslandRoads.roads.json")
            derive(out)
            print("island_layout: derived %s" % out)
            print("island_layout: time " + ", ".join("%s %.0f s" % kv for kv in sorted(TIMES.items(), key=lambda kv: -kv[1])))
            print("island_layout: %d step(s) replayed from the cache" % len(HITS))
        finally:
            shutil.rmtree(d)
        return
    if "--check" not in argv:
        derive(OUTPUT)
    rep = json.loads(run(CLI, "validate", OUTPUT))
    flow = json.loads(run(CLI, "flow", OUTPUT))["report"]
    # a site's access road ends at its car park by design (island_site_access): its lanes are not open ends
    sys.path.insert(0, HERE)
    import island_site_access
    access = island_site_access.access_roads()
    flow["open_end"] = [e for e in flow["open_end"] if not any(str(e[0]).startswith(a + "_") for a in access)]
    bad = {k: len(flow[k]) for k in ("broken", "misjoined", "unreached", "ramp_orphans", "open_end")}
    print("island_layout: %d errors, %d warnings; flow %d lanes %s -> %s"
          % (rep["errors"], rep["warnings"], flow["lanes"], bad, OUTPUT))
    for k in ("broken", "misjoined", "unreached", "ramp_orphans", "open_end"):
        if flow[k]:
            print("island_layout: %s: %s" % (k, [str(e[0]) if isinstance(e, (list, tuple)) else str(e)
                                                  for e in flow[k]][:12]))
    # every road over another clears it, measured on the built surface (roadkit_interchange.crossings)
    sys.path.insert(0, HERE)
    import roadkit_interchange as ri
    t0 = time.monotonic()
    cross = ri.crossings(OUTPUT)
    TIMES["check: crossings"] = time.monotonic() - t0
    low = [c for c in cross if c[0] < ri.CLEARANCE]
    print("island_layout: %d grade-separated crossings, tightest %.1f m (%s over %s)%s"
          % (len(cross), cross[0][0], cross[0][1], cross[0][2], "" if not low else "; %d BELOW %.1f m: %s"
             % (len(low), ri.CLEARANCE, low)))
    names = arterial_names()
    t0 = time.monotonic()
    grades = arterial_grades(OUTPUT, names)
    TIMES["check: arterial grades"] = time.monotonic() - t0
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
    # every expressway ramp's profile, on its EXPORTED lanes: <= 7 % to the ground, <= 6 % between expressways, every
    # break a vertical curve of K >= 6 (NEXT PASS step 1; island_grades.ramp_curves is the half that makes it so)
    t0 = time.monotonic()
    import island_grades as IG
    import point_export as pe
    lk = tempfile.mkdtemp()
    try:
        lkf = os.path.join(lk, "IslandRoads.lanekit.json")
        pe.write(pm.load_network(OUTPUT), lkf)
        ramps = IG.ramp_report(OUTPUT, [lkf])
    finally:
        shutil.rmtree(lk)
    TIMES["check: ramp profiles"] = time.monotonic() - t0
    rbad = [r for r in ramps if r[3] > (IG.RAMP_GROUND_GRADE if r[1] == "ground" else IG.RAMP_JCT_GRADE) + 1e-4
            or r[4] < IG.RAMP_K]
    print("island_layout: %d ramp(s), steepest %.1f %% (%s), flattest curve K %.1f (%s)%s" % (
        len(ramps), max(r[3] for r in ramps) * 100, max(ramps, key=lambda r: r[3])[0], min(r[4] for r in ramps),
        min(ramps, key=lambda r: r[4])[0], "" if not rbad else "; %d OVER THE RAMP RULE: %s" % (
            len(rbad), ", ".join("%s %.1f %% K %.1f" % (r[0], r[3] * 100, r[4]) for r in rbad))))
    t0 = time.monotonic()
    folds = chain_folds(OUTPUT)
    TIMES["check: folds"] = time.monotonic() - t0
    print("island_layout: %d road(s) folding back on themselves%s" % (len(folds), "" if not folds else ": " + ", ".join(
        "%s at %s (%.0f deg)" % f for f in folds)))
    t0 = time.monotonic()
    gaps = joint_gaps(OUTPUT)
    TIMES["check: joint gaps"] = time.monotonic() - t0
    wide = [g for g in gaps if g[0] > JOINT_GAP]
    print("island_layout: %d lane hand-over(s) across a joint, worst %.3f m%s" % (
        len(gaps), gaps[0][0] if gaps else 0.0, "" if not wide else "; %d OVER %.2f m: %s" % (
            len(wide), JOINT_GAP, ", ".join("%s -> %s %.2f m" % (a, b, g) for g, a, b in wide[:6]))))
    t0 = time.monotonic()
    ows = one_way_stretches(OUTPUT)
    print("island_layout: %d expressway split(s); one-way pairs run parallel %s" % (
        len(ows), ", ".join("%.0f m (%s -> %s)" % (m, d, " / ".join(h)) for m, d, h in ows)))
    p2 = phase2_intrusions(OUTPUT)
    TIMES["check: expressway splits + phase 2"] = time.monotonic() - t0
    print("island_layout: phase-2 Wangan ground held%s" % ("" if not p2 else "; %d INTRUSION(S): %s" % (
        len(p2), ", ".join("%s %s %s" % x for x in p2[:10]))))
    print("island_layout: time " + ", ".join("%s %.0f s" % kv for kv in sorted(TIMES.items(), key=lambda kv: -kv[1])))
    print("island_layout: %d step(s) replayed from the cache%s" % (len(HITS), "" if not HITS else " (%s)" % ", ".join(HITS)))
    if rep["errors"] or any(bad.values()) or low or steep or folds or p2 or rbad:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
