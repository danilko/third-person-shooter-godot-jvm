#!/usr/bin/env python3
"""site_airport_fence.py -- the airport's AIRSIDE FENCE (user, 2026-09-29: "a fence round the whole airport airside, so
a character enters only through the terminal"), written into the `AirportAirside` composite of
`assets/world_source/buildings/building_types.json` (its fence and gate props replaced; everything else kept).

    python3 tools/building_kit/site_airport_fence.py [--check]

DERIVED from what it closes, so none of them can move without it: the `airport_airfield` reserve (`island_plan
.RESERVES`, the composite's footprint; placed at yaw 180 by `island_sites.RESERVE_SITES`, so the composite's +Z is
north, toward the terminal), and the terminal's frozen site (`IslandSites.json` `airport_terminal`: its width is the
one gap in the north fence -- the terminal's airside face is the only way through). The fence is `Mil_Fence` bays
(2.4 m chain-link with a barbed outrigger leaning OUT) along the south edge, both ends and the north edge either side
of the terminal, closed against the terminal's two end walls; `Airport_ServiceGate` (8 m, locked) stands in the north
fence where the service road `kuko_service` (island_site_access) meets it.

`--check` exits 1 when the composite is stale, or when the fence does not close: every corner and both terminal ends
must be met by a bay to within CLOSE (a character's width is 0.7 m).
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
SITES = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandSites.json")
ID = "AirportAirside"
BAY = 10.0                           # a Mil_Fence bay (library_civic.mil_fence), along its local X
INSET = 0.7                          # the fence line this far inside the footprint's edge
GATE_W = 8.6                         # Airport_ServiceGate across its posts
GATE_GX = 1130.0                     # Godot x of the gate: where kuko_service ends (island_site_access)
CLOSE = 0.5
FENCE_PIECES = ("library:Mil_Fence", "library:Airport_ServiceGate")
TOWER = {"type": "AirportControlTower", "at": [240.0, 72.0], "yaw": 0.0}


def frame():
    """(centre gx, centre gz, half width, half depth) of the airside reserve; the composite stands at yaw 180, so a
    local (x, z) is Godot (cx - x, cz - z)."""
    gx0, gz0, gx1, gz1 = dict(PL.RESERVES)["airport_airfield"]
    return (gx0 + gx1) / 2.0, (gz0 + gz1) / 2.0, (gx1 - gx0) / 2.0, (gz1 - gz0) / 2.0


def terminal_span():
    """The terminal's width along x (Godot), from its frozen site."""
    st = next(s for s in json.load(open(SITES))["sites"] if s["id"] == "airport_terminal")
    return st["x"] - st["size"][0] / 2.0, st["x"] + st["size"][0] / 2.0


def run(a, b, yaw, out):
    """Bays from local point a to b (along a straight edge), evenly spaced so the first and last bay's ends land on
    a and b exactly (bays overlap a little rather than leave a gap)."""
    L = math.dist(a, b)
    n = max(1, int(math.ceil(L / BAY)))
    for k in range(n):
        t = (k + 0.5) / n
        c = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        # a bay is BAY long; with n bays over L each is centred on its share, so the chain spans exactly [a, b]
        # when n * BAY >= L -- the ends are pulled in to a and b below
        out.append({"piece": "library:Mil_Fence", "at": [round(c[0], 2), round(c[1], 2)], "yaw": yaw})
    # the first and last bay stand with their outer ends ON a and b (a bay may overhang its share)
    for k, end in ((0, a), (n - 1, b)):
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        s = -1.0 if k == 0 else 1.0
        c = (end[0] - s * d[0] * BAY / 2.0, end[1] - s * d[1] * BAY / 2.0)
        out[len(out) - n + k]["at"] = [round(c[0], 2), round(c[1], 2)]


def fence():
    cx, cz, hw, hd = frame()
    X, Z = hw - INSET, hd - INSET
    t0, t1 = terminal_span()
    lt0, lt1 = sorted((cx - t1, cx - t0))            # the terminal's span in local x
    gx = cx - GATE_GX                                # the gate's centre in local x
    props = []
    run((-X, -Z), (X, -Z), 180.0, props)             # south edge (the runway side): outrigger south
    run((-X, -Z), (-X, Z), 270.0, props)             # the two ends (outrigger outward)
    run((X, -Z), (X, Z), 90.0, props)
    # north edge, either side of the terminal; the gate in the west (local +x) part
    run((-X, Z), (lt0, Z), 0.0, props)
    g0, g1 = gx - GATE_W / 2.0, gx + GATE_W / 2.0
    run((lt1, Z), (g0, Z), 0.0, props)
    run((g1, Z), (X, Z), 0.0, props)
    props.append({"piece": "library:Airport_ServiceGate", "at": [round(gx, 2), round(Z, 2)], "yaw": 0.0})
    return props, dict(X=X, Z=Z, lt0=lt0, lt1=lt1, g0=g0, g1=g1)


def closes(props, k):
    """Every corner, both terminal ends and both gate posts are met by a bay end (or the gate) within CLOSE."""
    ends = []
    for p in props:
        if p["piece"] != "library:Mil_Fence":
            continue
        a = math.radians(p["yaw"])
        dx, dz = math.cos(a) * BAY / 2.0, -math.sin(a) * BAY / 2.0
        ends += [(p["at"][0] - dx, p["at"][1] - dz), (p["at"][0] + dx, p["at"][1] + dz)]
    need = [(-k["X"], -k["Z"]), (k["X"], -k["Z"]), (-k["X"], k["Z"]), (k["X"], k["Z"]), (k["lt0"], k["Z"]),
            (k["lt1"], k["Z"]), (k["g0"], k["Z"]), (k["g1"], k["Z"])]
    return [q for q in need if min(math.dist(q, e) for e in ends) > CLOSE]


def main(argv):
    props, k = fence()
    t = json.load(open(TYPES))
    comp = next(c for c in t["composites"] if c["id"] == ID)
    new = [p for p in comp["props"] if p.get("piece") not in FENCE_PIECES] + props
    # the CIVIL CONTROL TOWER (user, 2026-09-29: "AirportControlTower, a part of AirportAirside, beside the apron"):
    # the walkable kits/interiors tower (32 x 22.8 m, the lift to its 36 m cab) on the apron's west end, inside the
    # fence, 10 m short of it
    parts = [p for p in comp["parts"] if p["type"] != "AirportControlTower"] + [TOWER]
    open_ = closes(props, k)
    if open_:
        print("%s: the fence does NOT close at %s" % (ID, open_))
        return 1
    if "--check" in argv:
        ok = comp["props"] == new and comp["parts"] == parts
        print("%s: fence %s (%d bays, the terminal gap x %.1f..%.1f local)" % (
            ID, "up to date" if ok else "STALE -- run without --check", len(props) - 1, k["lt0"], k["lt1"]))
        return 0 if ok else 1
    comp["props"] = new
    comp["parts"] = parts
    json.dump(t, open(TYPES, "w"), indent=1, ensure_ascii=False)
    open(TYPES, "a").write("\n")
    print("%s: %d fence bays + the service gate; the terminal's airside face (local x %.1f..%.1f) the only opening"
          % (ID, len(props) - 1, k["lt0"], k["lt1"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
