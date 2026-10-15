#!/usr/bin/env python3
"""island_road_gap.py -- TWO ROADS THAT DO NOT MEET MUST NOT TOUCH (S16 review A1, 2026-10-14).

    python3 -u tools/island_road_gap.py [--record <IslandRoads.roads.json>] [--land <f32>] [--baseline <json> | --no-baseline]
        [--write-baseline <json>]

WHY. The committed kita_touge's first ~560 m ran along the slope directly above kaigan_dori: 10-30 m apart in plan
while already 14-47 m higher -- two carves on one verge, a wall on the coast road's shoulder. Nothing gated it: the
layout checks a road against its own grade and radius, never against a road it does not join.

THE RULE. Two roads with no link between them (segment, junction or aux, directly or through one junction pad: exempt only within 60 m of the node they share; a
ramp's aux pair along its whole length) keep
their DECKS (the full section, footways included, from the solved cross-section) >= `GAP` m apart in plan -- unless one
passes OVER the other with >= `OVER` m between their surfaces ON A STRUCTURE (the upper surface >= `CLEAR_UNDER` over
its own ground; a road up the cut slope beside another is not one). Every pair that breaks it is one finding:
its worst slack, how long it is in breach, and where.

BASELINE. HEAD may carry old pairs; `--write-baseline` lists them, and the gate then fails only on a pair that is NEW or
WORSE (by > 0.5 m of slack or > 20 m of length). The baseline is a list of known defects, never a loosening of the rule.
"""
import collections
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
for p in (HERE, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"), os.path.join(ROOT, "blender", "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import point_model as pm                                                      # noqa: E402
import point_solve as ps                                                      # noqa: E402

REC = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.roads.json")
#: HEAD's pairs at the gate's birth (a dry layout of a1d8f5a7's code, S16 J0): expressway twin ramps on one deck and
#: flyover crossings whose nearest samples read a few cm under OVER -- less kaigan_dori x kita_touge, the defect it was
#: built for. Rewrite it only on purpose, after reading every pair.
BASELINE = os.path.join(HERE, "island_road_gap.baseline.json")
GAP = 3.0            # m of plan clearance between two decks that do not meet
OVER = 6.5           # m between surfaces that make it a structure (one passes over the other)
CELL = 40.0
GODOT_Y = 5.6       # island_roadgen.NET_Y: a record height is the Godot height less this (since the land raise)
CLEAR_UNDER = 4.7   # m: the upper road's surface over its own ground for it to count as a deck (CLEAR_ROAD_UNDER)
NODE_EXEMPT = 60.0  # m round a shared node where two joined roads may close up (pad corners, a Y's splay)


def base(n):
    return re.sub(r"(__x?\d+)+$", "", str(n))


def joined_pairs(net):
    """{frozenset(a, b): [(x, y), ...] the nodes they share} -- roads linked directly (a segment joint, a junction, a
    ramp's aux), or members of one junction pad. An AUX pair (a ramp beside its mainline over the taper) maps to None:
    exempt along its whole length. Any other pair is exempt only within `NODE_EXEMPT` of a node it shares, because a
    road that JOINS another can still run along its verge for 500 m (kita_touge at its foot -- the defect this gates)."""
    owner = {u: n for n, r in net.roads.items() for u in r.points}
    out = {}

    def add(a, b, xy):
        k = frozenset((a, b))
        if out.get(k, 0) is None:
            return
        out.setdefault(k, []).append(xy)
    for u, p in net.points.items():
        a = owner.get(u)
        for l in p.links:
            b = owner.get(l.target)
            if a is None or b is None or a == b:
                continue
            if l.type == pm.LINK_AUX:
                out[frozenset((a, b))] = None
            else:
                add(a, b, p.pos[:2])
    for clique in net.junction_cliques():
        mem = [u for u in clique if u in owner and u in net.points]
        if not mem:
            continue
        c = (sum(net.points[u].pos[0] for u in mem) / len(mem), sum(net.points[u].pos[1] for u in mem) / len(mem))
        names = {owner[u] for u in mem}
        for a in names:
            for b in names:
                if a < b:
                    add(a, b, c)
    return out


def land_fn(path=None):
    """ground(x, y) in the RECORD frame from the land stage's 2 m Godot height grid (the pre-carve land the layout
    reads): a dry record's `ground_z` is stale until the build samples it, so it cannot say what stands on a deck."""
    import island_reshape as RS
    h = RS.load(path or RS.LAND)

    def ground(x, y):
        i, j = int(round((x - RS.X0) / RS.STEP)), int(round((-y - RS.Z0) / RS.STEP))
        if not (0 <= i < RS.N and 0 <= j < RS.N):
            return -30.0
        return max(float(h[j, i]), 0.0) - GODOT_Y
    return ground


def road_samples(net, ground):
    """{road: [(x, y, z, half, lift)]} from the solved runs: `half` = the deck's widest side from the centreline, `lift`
    = the surface over the land below it -- how far it stands on a structure (or a fill)."""
    out = collections.defaultdict(list)
    for name, solves in ps.solve_network(net).items():
        for s in solves:
            for sm, v in zip(s.samples, s.values):
                half = v["rka_deck_w"] + abs(v["rka_deck_c"])
                out[name].append((sm.pos[0], sm.pos[1], sm.pos[2], half, sm.pos[2] - ground(sm.pos[0], sm.pos[1])))
    return out


def measure(net, ground):
    joined = joined_pairs(net)
    samples = road_samples(net, ground)
    grid = collections.defaultdict(list)
    for name, ss in samples.items():
        for i, (x, y, z, h, _l) in enumerate(ss):
            grid[(int(x // CELL), int(y // CELL))].append((name, i))
    maxh = max((t[3] for ss in samples.values() for t in ss), default=0.0)
    reach = 2 * maxh + GAP
    found = {}           # pair -> {worst slack, idx set of a, xy}
    for name, ss in samples.items():
        for i, (x, y, z, h, lift) in enumerate(ss):
            ci, cj = int(x // CELL), int(y // CELL)
            r = int(math.ceil(reach / CELL))
            for gi in range(ci - r, ci + r + 1):
                for gj in range(cj - r, cj + r + 1):
                    for other, k in grid.get((gi, gj), ()):
                        if other <= name:
                            continue
                        ox, oy, oz, oh, olift = samples[other][k]
                        d = math.hypot(ox - x, oy - y)
                        slack = d - h - oh - GAP
                        if slack >= 0.0:
                            continue
                        # a structure: the upper one is >= OVER above the lower AND stands on a deck there. A road on
                        # the slope above another is NOT one -- kita_touge 5 m beside kaigan_dori, 11 m up its cut
                        if abs(oz - z) >= OVER and (olift if oz > z else lift) >= CLEAR_UNDER:
                            continue
                        nodes = joined.get(frozenset((name, other)), ())
                        if nodes is None or any(math.hypot(x - nx, y - ny) < NODE_EXEMPT or
                                                math.hypot(ox - nx, oy - ny) < NODE_EXEMPT for nx, ny in nodes):
                            continue
                        f = found.setdefault((name, other), {"slack": 0.0, "a": set(), "xy": None, "dz": 0.0})
                        f["a"].add(i)
                        if slack < f["slack"]:
                            f["slack"], f["xy"], f["dz"] = slack, ((x + ox) / 2, (y + oy) / 2), abs(oz - z)
    rows = {}
    for (a, b), f in found.items():
        a, b = sorted((a, b))
        key = (base(a), base(b))
        r = rows.get(key)
        ln = len(f["a"]) * ps.rp.SAMPLE_STEP
        if r is None:
            rows[key] = r = {"a": key[0], "b": key[1], "slack": 0.0, "length": 0.0, "x": 0.0, "y": 0.0, "dz": 0.0,
                             "names": []}
        r["length"] += ln
        r["names"].append("%s/%s" % (a, b))
        if f["slack"] < r["slack"]:
            r.update(slack=round(f["slack"], 2), x=round(f["xy"][0], 1), y=round(f["xy"][1], 1), dz=round(f["dz"], 1))
    out = sorted(rows.values(), key=lambda r: r["slack"])
    for r in out:
        r["names"].sort()
    return out


def main(argv):
    rec = argv[argv.index("--record") + 1] if "--record" in argv else REC
    net = pm.load_network(rec)
    rows = measure(net, land_fn(argv[argv.index("--land") + 1] if "--land" in argv else None))
    known = {}
    bpath = argv[argv.index("--baseline") + 1] if "--baseline" in argv else BASELINE
    if "--write-baseline" not in argv and "--no-baseline" not in argv:
        for r in json.load(open(bpath))["pairs"]:
            known[(r["a"], r["b"])] = r
    new = []
    for r in rows:
        k = known.get((r["a"], r["b"]))
        tag = "known"
        if k is None:
            tag = "NEW"
        elif r["slack"] < k["slack"] - 0.5 or r["length"] > k["length"] + 20.0:
            tag = "WORSE"
        if tag != "known":
            new.append(r)
        print("  %-5s %-22s %-22s slack %6.2f m over %4.0f m  dz %5.1f  at (%.0f, %.0f)" % (
            tag, r["a"], r["b"], r["slack"], r["length"], r["dz"], r["x"], r["y"]))
    if "--write-baseline" in argv:
        json.dump({"rule": "deck gap >= %.1f m unless dz >= %.1f m" % (GAP, OVER), "pairs": rows},
                  open(argv[argv.index("--write-baseline") + 1], "w"), indent=1)
    print("road gap: %d pair(s) closer than %.1f m (deck to deck, not joined, dz < %.1f m); %d new or worse" % (
        len(rows), GAP, OVER, len(new)))
    return 1 if (rows if "--no-baseline" in argv else new) and "--write-baseline" not in argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
