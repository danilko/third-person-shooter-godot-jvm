#!/usr/bin/env python3
"""roadkit_interchange.py -- the INTERCHANGE template (PLAN.md 3.13 step 1): a diamond interchange as a Road Kit record.

    python3 tools/roadkit_interchange.py <out.roads.json> [--check] [--kind diamond|loop]

Two templates (PLAN.md 3.13):
* `diamond` (default): an EXPRESSWAY-TO-STREET interchange, the sketch's dark-blue exits (below).
* `loop`: an EXPRESSWAY-TO-EXPRESSWAY junction (JCT), the Shibaura-JCT shape that takes the elevated C1 loop onto the
  Rainbow Bridge (user, 2026-09-18): no ground junction at all. See `build_loop`.

An expressway (the `expressway` preset, 2 + 2 lanes, deck at `DECK_Z`) runs east-west over a north-south trunk road
(the `trunk` preset, at ground). Keep-left: the EASTBOUND carriageway (FWD, travelling +X) is the north one, so its
exit ramp (before the overpass) and entrance ramp (after it) land on a signalised junction NORTH of the overpass on
the trunk road; the westbound ramps land on one SOUTH of it. The expressway is split at the overpass
(`point_record_ops.split_at_joint`), so an exit and an entrance on the same carriageway sit on different runs and never
claim the same aux slot (`aux_slot_shared`). Every ramp is made with `branch_ramp` (aux slot, AUX link, gore) and then
runs down to its junction mouth; junction mouths are four-way cliques 20 m from the junction centre.

`--check` exits 1 unless the record passes the Road Kit gate (0 errors) and the lane flow has no broken or misjoined
lanes. This is the template later interchanges on the island are copied from (3.13 step 2).
"""
import json
import math
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402
import point_presets as pr      # noqa: E402
import point_record_ops as ro   # noqa: E402
import point_validate as pv     # noqa: E402

DECK_Z = 10.0          # the expressway deck: 10 m over the trunk road (>= 4.7 m clearance plus the deck)
HALF = 800.0           # the expressway runs x -HALF..HALF
RAMP_X = 300.0         # the eastbound ramps leave / join the expressway this far either side of the overpass
RAMP_X2 = 560.0        # ... and the westbound ones here: one ramp per station, so each takes its own carriageway's slot
# every span before a ramp station is >= 240 m: an aux lane opens over ONE span, and 80 km/h wants a 216 m taper
JCT_Y = 90.0           # the two junctions on the trunk road, north and south of the overpass
MOUTH = 22.0           # junction mouths this far from the junction centre


def road(net, name, pts):
    r = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
    prev = None
    for q in pts:
        p = net.add_station(r, q)
        if prev is not None:
            net.link(prev.uid, p.uid)
        prev = p
    return r


def junction(net, mouths):
    for i in range(len(mouths)):
        for j in range(i + 1, len(mouths)):
            net.link(mouths[i], mouths[j], pm.LINK_JUNCTION)
    for u in mouths:
        net.points[u].role = pm.INTERSECTION


def extend(net, road_name, pts):
    """Append stations to a road's chain (the ramp's run down to its junction)."""
    r = net.roads[road_name]
    prev = r.points[-1]
    for q in pts:
        p = net.add_station(r, q)
        net.link(prev, p.uid)
        prev = p.uid
    return prev


def build():
    net = pm.NetworkData()
    # the expressway: a station at each ramp point and the overpass, split at the overpass
    xs = [-HALF, -RAMP_X2, -RAMP_X, 0.0, RAMP_X, RAMP_X2, HALF]
    exp = road(net, "expressway", [(float(x), 0.0, DECK_Z) for x in xs])
    pr.apply_preset(net, "expressway", "expressway")
    at = {net.points[u].pos[0]: u for u in exp.points}
    ro.split_at_joint(net, at[0.0], name="expressway_e")
    # the trunk road in three pieces between the two junctions, and the two junction centres
    s = road(net, "trunk_s", [(0.0, y, 0.0) for y in (-700.0, -400.0, -JCT_Y - MOUTH)])
    m = road(net, "trunk_mid", [(0.0, -JCT_Y + MOUTH, 0.0), (0.0, 0.0, 0.0), (0.0, JCT_Y - MOUTH, 0.0)])
    n = road(net, "trunk_n", [(0.0, JCT_Y + MOUTH, 0.0), (0.0, 400.0, 0.0), (0.0, 700.0, 0.0)])
    for r in ("trunk_s", "trunk_mid", "trunk_n"):
        pr.apply_preset(net, r, "trunk")
    # ramps. Eastbound (FWD, the north carriageway): exit at -RAMP_X down to the north junction's west mouth,
    # entrance from its east mouth up to +RAMP_X. Westbound (BWD, south): exit at +RAMP_X down to the south
    # junction's east mouth, entrance from its west mouth up to -RAMP_X.
    mouths_n, mouths_s = [n.points[0], m.points[-1]], [s.points[-1], m.points[0]]
    ramps = (("eb_off", at[-RAMP_X], "FWD", False, -1, JCT_Y, mouths_n),
             ("eb_on", at[RAMP_X], "FWD", True, 1, JCT_Y, mouths_n),
             ("wb_off", at[RAMP_X2], "BWD", False, 1, -JCT_Y, mouths_s),
             ("wb_on", at[-RAMP_X2], "BWD", True, -1, -JCT_Y, mouths_s))
    for name, uid, cw, ent, side, jy, mouths in ramps:
        _msg, info = ro.branch_ramp(net, uid, name=name, aux_lanes=2, carriageway=cw, entrance=ent, length=90.0,
                                    spread=12.0, drop=-2.0)
        far = net.points[info["far"]].pos
        sy = 1.0 if jy > 0 else -1.0
        # down and in to the junction mouth, approaching along -side x (towards the trunk road)
        pts = [((far[0] + side * MOUTH) / 2.0, (far[1] + jy) / 2.0 + sy * 6.0, (far[2] + 0.0) / 2.0),
               (side * (MOUTH + 70.0), jy, 0.5), (side * MOUTH, jy, 0.0)]
        mouth = extend(net, name, pts)
        mouths.append(mouth)
    junction(net, mouths_n)
    junction(net, mouths_s)
    return net


def arc(cx, cy, r, a0, a1, z0, z1, n):
    """Points on a circle of radius r about (cx, cy) from angle a0 to a1 (degrees, counter-clockwise positive), the
    height rising linearly from z0 to z1 (the first point excluded)."""
    out = []
    for k in range(1, n + 1):
        t = k / n
        a = math.radians(a0 + (a1 - a0) * t)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a), z0 + (z1 - z0) * t))
    return out


C1_Z = 10.0            # the C1 loop's deck
BRIDGE_Z = 32.0        # the Rainbow Bridge's UPPER deck (the expressway spur); its lower deck carries the airport road


def build_loop():
    """C1 runs east-west at C1_Z (keep-left: eastbound = FWD on the north side, westbound = BWD on the south side). The
    bridge spur leaves south as two one-way roads side by side: `spur_out` (southbound, the east side) and `spur_in`
    (northbound, the west side), climbing to BRIDGE_Z. Keep-left also decides every merge: a ramp joins a road from
    that road's LEFT. Four ramps, all grade-separated:
    * `wb_out`: westbound C1 -> spur_out, off the south side, becoming spur_out at a joint;
    * `eb_loop`: eastbound C1 -> spur_out: the 270-degree LOOP north of C1 and east of the spur (it climbs over its own
      entry and over C1, the Shibaura loop), merging into spur_out from its east side;
    * `in_wb`: spur_in -> westbound C1, down the south side, as an entrance;
    * `in_eb`: spur_in -> eastbound C1: leaves spur_in, flies over C1 west of the loop, runs east north of it and
      comes down onto eastbound C1.
    C1 is split at x = 0 so no exit and entrance share a run's aux slot."""
    net = pm.NetworkData()
    xs = [-1000.0, -750.0, -500.0, -250.0, -100.0, 0.0, 400.0, 650.0, 900.0, 1150.0]
    c1 = road(net, "c1", [(x, 0.0, C1_Z) for x in xs])
    pr.apply_preset(net, "c1", "expressway")
    at = {net.points[u].pos[0]: u for u in c1.points}
    ro.split_at_joint(net, at[0.0], name="c1_e")

    def one_way(name, pts, lanes=2, cls="expressway"):
        r = road(net, name, pts)
        pr.apply_preset(net, name, "expressway")
        r.road_class = cls
        r.base.lanes_bwd = 0
        r.base.median_width = 0.0
        for u in r.points:
            net.points[u].lanes_fwd, net.points[u].lanes_bwd = lanes, 0
        return r
    spur_out = one_way("spur_out", [(10.0, -140.0, 18.0), (10.0, -420.0, 26.0), (10.0, -720.0, BRIDGE_Z),
                                    (10.0, -1000.0, BRIDGE_Z)])
    spur_in = one_way("spur_in", [(-10.0, -1000.0, BRIDGE_Z), (-10.0, -720.0, BRIDGE_Z), (-10.0, -440.0, 27.0),
                                  (-10.0, -140.0, 18.0)])
    # wb_out: westbound exit at +400, curving south-west to become spur_out
    ro.branch_ramp(net, at[400.0], name="wb_out", aux_lanes=2, carriageway="BWD", length=90.0, spread=10.0, drop=0.5)
    # a JOINT: wb_out's last station sits exactly on spur_out's first, SEGMENT-linked (point_export.wire_joints)
    # (a joint must be TANGENTIAL -- both sides heading the same way -- or its lanes land beside each other)
    end = extend(net, "wb_out", [(150.0, -60.0, 14.0), (40.0, -80.0, 16.0), (10.0, -110.0, 17.0), (10.0, -140.0, 18.0)])
    net.link(end, spur_out.points[0])
    # eb_loop: eastbound exit at -100, east to the loop (centre (150, 125), r 80), 270 degrees counter-clockwise,
    # south over its own entry and over C1 at x ~ 70, then down the east side of spur_out to merge into it
    ro.branch_ramp(net, at[-100.0], name="eb_loop", aux_lanes=2, carriageway="FWD", length=80.0, spread=8.0, drop=0.5)
    pts = [(150.0, 45.0, 11.0)] + arc(150.0, 125.0, 80.0, -90.0, 180.0, 11.0, 20.0, 9)
    pts += [(70.0, 40.0, 21.0), (70.0, -110.0, 24.0), (40.0, -300.0, 25.5), (28.0, -420.0, 26.0)]
    extend(net, "eb_loop", pts)
    ro.make_ramp(net, spur_out.points[1], net.roads["eb_loop"].points[-1], lanes=2)
    # in_wb: spur_in becomes a ramp that joins westbound C1 as an entrance at -250
    r = one_way("in_wb", [(-10.0, -140.0, 18.0), (-10.0, -110.0, 17.0), (-40.0, -70.0, 14.0), (-110.0, -40.0, 12.5),
                          (-160.0, -22.0, 11.5)], cls="ramp")
    net.link(spur_in.points[-1], r.points[0])            # a joint at (-10, -140), as wb_out -> spur_out
    ro.make_ramp(net, at[-250.0], r.points[-1], lanes=2)
    # in_eb: leaves spur_in at -440, north over C1 at x -60, east north of the loop, down onto eastbound C1 at +650
    ro.branch_ramp(net, spur_in.points[2], name="in_eb", aux_lanes=2, carriageway="FWD", length=80.0, spread=8.0,
                   drop=-0.5)
    extend(net, "in_eb", [(-40.0, -240.0, 23.0), (-60.0, 0.0, 20.5), (-40.0, 240.0, 17.0), (150.0, 260.0, 15.5),
                          (420.0, 200.0, 13.0), (560.0, 45.0, 11.0)])
    ro.make_ramp(net, at[650.0], net.roads["in_eb"].points[-1], lanes=2)
    return net


CLEARANCE = 5.5        # road surface over road surface: 4.7 m clearance + a 0.8 m deck


def crossings(record):
    """[(separation m, upper road, lower road, (x, z))] wherever two DIFFERENT roads' built surfaces overlap in plan
    within 4 m at heights more than 1 m apart (a crossing, not a merge), the tightest per road pair. Measured on the
    mesh Build makes (`roadkit_cli.py mesh`), so it is the real deck, not the station heights."""
    import collections
    import subprocess
    d = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "blender", "tools", "roadkit_cli.py"), "mesh",
                                   record], capture_output=True, text=True).stdout)["objects"]
    grid = collections.defaultdict(list)
    for name, mats in d.items():
        if "surface" not in name:
            continue
        road = name.split("__")[0]
        for m, f in mats.items():
            if "Asphalt" not in m:                       # the road surface only, not piers, kerbs or paint
                continue
            for i in range(0, len(f), 9):
                ux, uy, uz = f[i + 3] - f[i], f[i + 4] - f[i + 1], f[i + 5] - f[i + 2]
                vx, vy, vz = f[i + 6] - f[i], f[i + 7] - f[i + 1], f[i + 8] - f[i + 2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                n = math.sqrt(nx * nx + ny * ny + nz * nz)
                if n < 1e-9 or abs(ny) / n < 0.7:           # a driving surface faces up (either winding)
                    continue
                x, y, z = (f[i] + f[i + 3] + f[i + 6]) / 3, (f[i + 1] + f[i + 4] + f[i + 7]) / 3, (f[i + 2] + f[i + 5] + f[i + 8]) / 3
                grid[(int(x // 6), int(z // 6))].append((road, x, z, y))
    best = {}
    for pts in grid.values():
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                a, b = pts[i], pts[j]
                if math.hypot(a[1] - b[1], a[2] - b[2]) > 4.0:
                    continue
                sep = abs(a[3] - b[3])
                # a merge is at one height; a road over ITSELF (the loop over its own entry) counts too, once the
                # gap is more than a slope's rise over 4 m could explain
                if sep <= (2.0 if a[0] == b[0] else 1.0):
                    continue
                up, lo = (a, b) if a[3] > b[3] else (b, a)
                key = (up[0], lo[0])
                if key not in best or sep < best[key][0]:
                    best[key] = (sep, up[0], lo[0], (round(up[1]), round(up[2])))
    return sorted(best.values())


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out = argv[0]
    net = build_loop() if ("--kind" in argv and argv[argv.index("--kind") + 1] == "loop") else build()
    findings = pv.validate(net)
    errs = pv.errors(findings)
    for f in findings:
        print("  %s %s: %s" % (f.severity, f.code, f.message[:160]))
    pm.save_network(net, out)
    print("roadkit_interchange: %d roads, %d stations, %d errors -> %s" % (len(net.roads), len(net.points), len(errs), out))
    import subprocess
    flow = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "blender", "tools", "roadkit_cli.py"), "flow", out],
                                     capture_output=True, text=True).stdout)["report"]
    bad = {k: len(flow[k]) for k in ("broken", "misjoined", "unreached", "ramp_orphans")}
    print("roadkit_interchange: flow %d lanes, %d junctions, %s" % (flow["lanes"], flow["junctions"], bad))
    tight = []
    for sep, up, lo, at in crossings(out):
        ok = sep >= CLEARANCE
        print("roadkit_interchange: %-10s over %-10s at %s: %.1f m %s" % (up, lo, at, sep, "ok" if ok else "TOO LOW"))
        if not ok:
            tight.append((up, lo))
    if "--check" in argv and (errs or any(bad.values()) or tight):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
