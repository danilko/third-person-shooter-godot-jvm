#!/usr/bin/env python3
"""site_airport_forecourt.py -- the `AirportForecourt` composite (the airport's 駅前 / curb forecourt, user 2026-09-29:
"forecourt like central station"), written into `assets/world_source/buildings/building_types.json` (replacing the
entry of that id).

    python3 tools/building_kit/site_airport_forecourt.py [--check]

DERIVED from what it dresses, so neither can move without it: the `airport_forecourt` reserve (`island_plan.RESERVES`,
the site's footprint) and the one-way loop `kuko_rotary` (`island_expressway.FORE_BOX`: its stations are the loop's
INNER edge; a one-way road lays its two lanes and its 4 m outer footway on its LEFT, i.e. outboard). The loop runs
clockwise round an inner island, between the Airport station's west wall (its east leg) and the terminal's curb canopy
(its south leg):
* the BUS stops on the south leg's outer footway, under the terminal's canopy edge (two shelters, three signs);
* the TAXI rank on the east leg's outer footway, beside the station's west entrances;
* the inner island planted, with the clock.
Nothing stands on the loop's lanes: every prop is checked against them before it is written.

Composite frame (the building convention): X = record x, +Z = Godot z (south), origin at the reserve's centre.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import island_plan as PL             # noqa: E402

TYPES = os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")
ID = "AirportForecourt"
LANES = 2 * 4.5                      # the loop's two lanes (island_expressway kuko_rotary)
WALK_OUT, WALK_IN = 4.0, 2.0
N = "quaternius_stylized_nature:"


def fore_box():
    """island_expressway.FORE_BOX (record x0, y0, x1, y1), read from its source so this needs none of its imports."""
    import re
    src = open(os.path.join(ROOT, "tools", "island_expressway.py")).read()
    m = re.search(r"FORE_BOX = \(([^)]*)\)", src)
    return tuple(float(v) for v in m.group(1).split(","))


def entry():
    gx0, gz0, gx1, gz1 = dict(PL.RESERVES)["airport_forecourt"]
    W, D = gx1 - gx0, gz1 - gz0
    cx, cz = (gx0 + gx1) / 2.0, (gz0 + gz1) / 2.0

    def L(rx, ry):                                       # record (x, y) -> local (x, z)
        return rx - cx, -ry - cz
    x0, y0, x1, y1 = fore_box()
    xw, zs = L(x0, y0)                                   # west station line, south station line (local)
    xe, zn = L(x1, y1)                                   # east, north
    # the loop's LANES (local [x0, z0, x1, z1]), outboard of each leg's station line
    lanes = [(xw - LANES, zn - LANES, xw, zs + LANES), (xw - LANES, zn - LANES, xe + LANES, zn),
             (xe, zn - LANES, xe + LANES, zs + LANES), (xw - LANES, zs, xe + LANES, zs + LANES)]
    props = []

    def put(piece, at, yaw=0.0, collide=None, half=(0.5, 0.5), **kw):
        hx, hz = half
        for b in lanes:
            if at[0] + hx > b[0] and at[0] - hx < b[2] and at[1] + hz > b[1] and at[1] - hz < b[3]:
                raise SystemExit("%s: %s at %s stands on the loop's lanes" % (ID, piece, at))
        if not (-W / 2 <= at[0] - hx and at[0] + hx <= W / 2 and -D / 2 <= at[1] - hz and at[1] + hz <= D / 2):
            raise SystemExit("%s: %s at %s leaves the footprint" % (ID, piece, at))
        p = {"piece": piece, "at": [round(at[0], 3), round(at[1], 3)]}
        if yaw:
            p["yaw"] = yaw
        if collide is not None:
            p["collide"] = collide
        p.update(kw)
        props.append(p)

    # the bus stops: the south leg's outer footway (zs + LANES .. + WALK_OUT), the terminal's curb
    zf = zs + LANES + WALK_OUT / 2.0
    for bx in (xw + 25.0, xw + 55.0):
        put("library:BusStop_Shelter", (bx, zf + 0.8), yaw=180.0, half=(2.0, 0.8))
    for bx in (xw + 29.0, xw + 59.0, xw + 89.0):
        put("library:BusStop_Sign", (bx, zs + LANES + 0.5), half=(0.1, 0.3))
    # the taxi rank: the east leg's outer footway, beside the station's west entrances
    xf = xe + LANES + WALK_OUT / 2.0
    put("library:Taxi_Sign", (xf, zn + 20.0), yaw=90.0, half=(0.4, 0.4))
    put("library:Station_Bench", (xf + 0.8, zn + 26.0), yaw=90.0, half=(0.3, 0.7))
    # the inner island: planted, the clock
    iz0, iz1 = zn + WALK_IN, zs - WALK_IN
    ix0, ix1 = xw + WALK_IN, xe - WALK_IN
    for tx in range(int(ix0 + 18), int(ix1 - 17), 22):
        put(N + "CommonTree_3", (float(tx), (iz0 + iz1) / 2.0 - 12.0), collide="none", half=(0.4, 0.4))
        put(N + "CommonTree_3", (float(tx) + 11.0, (iz0 + iz1) / 2.0 + 12.0), collide="none", half=(0.4, 0.4))
    put("library:Plaza_Clock", ((ix0 + ix1) / 2.0, (iz0 + iz1) / 2.0), half=(0.6, 0.6))
    return {
        "id": ID, "footprint_m": [round(W, 3), round(D, 3)],
        "jp": {"name": "空港 駅前 / 車寄せ (placeholder)",
               "note": "The airport's forecourt round the one-way kuko_rotary, between the Airport station and the "
                       "terminal's curb: bus stops on the terminal kerb, the taxi rank on the station kerb, the inner "
                       "island planted. PLACEHOLDER props. Written by tools/building_kit/site_airport_forecourt.py -- "
                       "edit that, not this entry."},
        "use": "the airport's forecourt, derived from the airport_forecourt reserve and the kuko_rotary loop",
        "parts": [], "placeholder": True, "reserve": True,
        # the inner island's ground collider only (the loop's own paving is the road's); the block-ground stage fills
        # the terrain under the rest (island_sites LEVELLED_RESERVES)
        "ground_box": [round(ix0, 3), round(iz0, 3), round(ix1, 3), round(iz1, 3)],
        "probe_xz": [round((ix0 + ix1) / 2.0 + 30.0, 3), round((iz0 + iz1) / 2.0, 3)],
        "props": props,
    }


def main(argv):
    e = entry()
    t = json.load(open(TYPES))
    old = next((c for c in t["composites"] if c["id"] == ID), None)
    if "--check" in argv:
        ok = old == e
        print("%s: %s" % (ID, "up to date" if ok else "STALE -- run without --check"))
        return 0 if ok else 1
    t["composites"] = [c for c in t["composites"] if c["id"] != ID] + [e]
    json.dump(t, open(TYPES, "w"), indent=1, ensure_ascii=False)
    open(TYPES, "a").write("\n")
    print("%s: %d props on %.0f x %.0f m" % (ID, len(e["props"]), e["footprint_m"][0], e["footprint_m"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
