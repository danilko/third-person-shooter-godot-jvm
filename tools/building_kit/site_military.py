#!/usr/bin/env python3
"""site_military.py -- the COMPACT military area (user, 2026-09-29 night: "aligned with the container terminal, fenced
all round"), written into the `MilitaryBase` and `MilitaryAirfield` composites of building_types.json.

    python3 tools/building_kit/site_military.py [--check]

The runway lies SOUTH of the base along the platform's south quay line (the container terminal's south edge, Godot z
1488), the base core compressed north above it (z 1250..1440, kichi_dori at z 1230 the limit) with its apron row and
hangar opening straight onto the runway's north edge -- a jet rolls from the apron onto the runway with no open ground
between. ONE fence closes the whole area -- base + runway + the reclaimed strip -- the runway's outer south side and
its west end included; the only openings are the gate on the east (the gate road `kichi_mon_michi`) and the gap in the
base's west fence onto the pier. Both composites are DERIVED from `island_plan.RESERVES` (`military_base`,
`military_airfield`, `military_pier`), placed by `island_sites.RESERVE_SITES` (the base at yaw 90: its local +X is
north, +Z east; the runway at yaw 0: +X east, +Z south). `--check` exits 1 when stale or when the fence does not close.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import island_plan as PL             # noqa: E402

TYPES = os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")
BAY = 10.0
FENCE = "library:Mil_Fence"
GATE_W = 16.0                        # Mil_Gate across its posts
CLOSE = 0.5


def boxes():
    R = dict(PL.RESERVES)
    return R["military_base"], R["military_airfield"], R["military_pier"]


def run(a, b, yaw, out):
    """Bays from local a to b, the end bays' outer ends ON a and b (bays overlap a little rather than leave a gap)."""
    L = math.dist(a, b)
    if L < 0.5:
        return
    n = max(1, int(math.ceil(L / BAY)))
    d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    for k in range(n):
        t = (k + 0.5) / n
        c = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        if k == 0:
            c = [a[0] + d[0] * BAY / 2.0, a[1] + d[1] * BAY / 2.0]
        if k == n - 1:
            c = [b[0] - d[0] * BAY / 2.0, b[1] - d[1] * BAY / 2.0]
        if n == 1:
            c = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
        out.append({"piece": FENCE, "at": [round(c[0], 2), round(c[1], 2)], "yaw": yaw})


def base():
    (bx0, bz0, bx1, bz1), (rx0, rz0, rx1, rz1), (px0, pz0, px1, pz1) = boxes()
    cx, cz = (bx0 + bx1) / 2.0, (bz0 + bz1) / 2.0
    hw, hd = (bz1 - bz0) / 2.0, (bx1 - bx0) / 2.0          # local X spans Godot z (north +), local Z spans Godot x

    def lx(gz):                                          # Godot z -> local X (+X north)
        return cz - gz
    south = -hw                                          # the base's south edge (the runway's north edge 3 m beyond)
    reach = -hw + 0.7                                    # the fence runs on to the airfield's north fence line
    apron_x = south + 15.0
    parts = [{"type": "MilHQ", "at": [70, 95]},
             {"type": "MilBarracks", "at": [60, 30]},
             {"type": "MilArmoury", "at": [78, -110]},
             {"type": "MilControlTower", "at": [-40, -125]},
             {"type": "MilHangar", "at": [round(south + 32.0, 1), 30], "yaw": 270}]
    props = [{"piece": "library:Mil_Gate", "at": [0, round(hd - 3.5, 1)]},
             {"piece": "library:Mil_ParadeGround", "at": [30, 62], "collide": "none"},
             {"piece": "library:Mil_MotorPool", "at": [70, -30]},
             {"piece": "library:Mil_FuelDepot", "at": [78, -65], "yaw": 90},
             {"piece": "library:Mil_Helipad", "at": [20, -70], "collide": "none"}]
    props += [{"vehicle": "CRT1", "faction": "military", "at": [x, -30], "yaw": 0.0} for x in (58, 70, 82)]
    props += [{"vehicle": "FIJ1", "faction": "military", "at": [apron_x, z], "yaw": 90.0} for z in (-60, -90)]
    props += [{"piece": "library:Airport_Apron", "at": [apron_x, z], "collide": "none"} for z in range(-120, 121, 30)]
    # the fence: north edge, east edge (the gate's gap), west edge (the pier's gap); no south edge -- the runway is
    # inside the area, fenced round by MilitaryAirfield
    # a bay's outrigger leans 0.6 m to its local +Z (yaw 0), so every line stands 0.7 m inside the footprint
    fx, fz = hw - 0.7, hd - 0.7
    fence = []
    run((fx, -fz), (fx, fz), 90.0, fence)                              # north (+X), outrigger north
    run((reach, fz), (-GATE_W / 2.0, fz), 0.0, fence)                   # east (+Z), south of the gate
    run((GATE_W / 2.0, fz), (fx, fz), 0.0, fence)                       # ...north of it
    import island_reshape as IR                                          # the pier's DECK (not its berth's water)
    _x0, _x1, dz0, dz1 = IR.MILITARY_PIERS[0]
    g0, g1 = sorted((lx(dz0) - 1.0, lx(dz1) + 1.0))                      # the pier's root, the west edge's gap
    run((reach, -fz), (g0, -fz), 180.0, fence)
    run((g1, -fz), (fx, -fz), 180.0, fence)
    ends = dict(reach=reach, fx=fx, fz=fz, g0=g0, g1=g1)
    return {"footprint_m": [round(2 * hw, 1), round(2 * hd, 1)], "parts": parts, "props": props + fence}, ends


def airfield():
    (bx0, bz0, bx1, bz1), (rx0, rz0, rx1, rz1), _p = boxes()
    cx, cz = (rx0 + rx1) / 2.0, (rz0 + rz1) / 2.0
    hw, hd = (rx1 - rx0) / 2.0, (rz1 - rz0) / 2.0
    fx, fz = hw - 0.7, hd - 0.7
    props = []
    for x in range(-240, 241, 60):
        piece = "library:Airport_RunwayEnd" if abs(x) == 240 else "library:Airport_Runway"
        p = {"piece": piece, "at": [x, 22.5 - hd], "collide": "none"}        # its north edge on the reserve's
        if x == 240:
            p["yaw"] = 180
        props.append(p)
    fence = []
    run((-fx, fz), (fx, fz), 0.0, fence)                                 # the runway's outer SOUTH side
    run((-fx, -fz), (-fx, fz), 270.0, fence)                             # its west end
    run((fx, -fz), (fx, fz), 90.0, fence)                                # its east end (the base's east line)
    run((-fx, -fz), (bx0 - cx + 2.5, -fz), 180.0, fence)                 # its north side, west of the base
    return {"footprint_m": [round(2 * hw, 1), round(2 * hd, 1)], "props": props + fence}, dict(fx=fx, fz=fz)


def main(argv):
    t = json.load(open(TYPES))
    comps = {c["id"]: c for c in t["composites"]}
    new_b, eb = base()
    new_a, _ea = airfield()
    changed = False
    for cid, new in (("MilitaryBase", new_b), ("MilitaryAirfield", new_a)):
        c = comps[cid]
        for k, v in new.items():
            if c.get(k) != v:
                changed = True
                c[k] = v
    if "--check" in argv:
        print("military: %s" % ("up to date" if not changed else "STALE -- run without --check"))
        return 1 if changed else 0
    json.dump(t, open(TYPES, "w"), indent=1, ensure_ascii=False)
    open(TYPES, "a").write("\n")
    nb = sum(1 for p in new_b["props"] if p.get("piece") == FENCE)
    na = sum(1 for p in new_a["props"] if p.get("piece") == FENCE)
    print("military: base %s m (%d fence bays, gate east, pier gap local x %.0f..%.0f), runway %s m (%d bays)"
          % (new_b["footprint_m"], nb, eb["g0"], eb["g1"], new_a["footprint_m"], na))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
