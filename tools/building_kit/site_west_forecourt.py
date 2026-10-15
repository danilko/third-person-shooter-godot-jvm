#!/usr/bin/env python3
"""site_west_forecourt.py -- the `WestForecourt` composite (S16 E [I5], user 2026-10-14: "B. Bays + plaza"): the 駅前広場
of the west sub-centre's station (西副都心, the rail reserve's `Residential`), written into
`assets/world_source/buildings/building_types.json` (replacing the entry of that id).

    python3 tools/building_kit/site_west_forecourt.py [--check]

DERIVED from the `west_station_forecourt` reserve (`island_plan.RESERVES`, the site's footprint): the ground between the
station's east face, its front street (the planner's y -413 line, `nishi_cho_413`), the 商店街 (x -650) and the
station mall. A rotary does not fit there (two mouths on the front street overlap the 踏切 and the x -650 junction), so
the buses and taxis stop at the KERB of the front street:
* the BUS stops on the plaza's north edge behind the front street's footway (shelters, a sign at each, a covered walk
  toward the station's north entrance);
* the TAXI rank past them, east along the same kerb;
* the plaza: the clock, benches, trees, bike racks by the mall.

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
ID = "WestForecourt"
N = "quaternius_stylized_nature:"


def entry():
    gx0, gz0, gx1, gz1 = dict(PL.RESERVES)["west_station_forecourt"]
    W, D = gx1 - gx0, gz1 - gz0
    props = []

    def put(piece, at, yaw=0.0, collide=None, half=(0.5, 0.5), **kw):
        hx, hz = half
        if not (-W / 2 <= at[0] - hx and at[0] + hx <= W / 2 and -D / 2 <= at[1] - hz and at[1] + hz <= D / 2):
            raise SystemExit("%s: %s at %s leaves the footprint" % (ID, piece, at))
        p = {"piece": piece, "at": [round(at[0], 3), round(at[1], 3)]}
        if yaw:
            p["yaw"] = yaw
        if collide is not None:
            p["collide"] = collide
        p.update(kw)
        props.append(p)

    kerb = -D / 2                                        # the north edge: the front street's footway is just beyond it
    west, east = -W / 2, W / 2                           # the station's east face side, the 商店街 side
    # the BUS stops: three shelters facing the street (north), the sign at each on the plaza's kerb edge
    for bx in (west + 8.0, west + 22.0, west + 36.0):
        put("library:BusStop_Shelter", (bx, kerb + 2.2), yaw=180.0, half=(2.0, 0.8))
        put("library:BusStop_Sign", (bx + 3.0, kerb + 0.5), half=(0.1, 0.3))
    # the covered walk from the stops to the station's north entrance (west edge), posts on the plaza side
    put("library:Plaza_Canopy", (west + 5.0, kerb + 6.0), half=(5.0, 2.0), collide="none", repeat=[4, 10.0, 0])
    # the TAXI rank: east of the bus stops along the same kerb
    put("library:Taxi_Sign", (east - 14.0, kerb + 0.6), half=(0.4, 0.4))
    put("library:Station_Bench", (east - 10.0, kerb + 2.0), yaw=180.0, half=(0.7, 0.3))
    # the plaza: the clock in its middle, benches round it, a row of trees, bike racks by the mall (south edge)
    cz = 4.0
    put("library:Plaza_Clock", (0.0, cz), half=(0.6, 0.6))
    for bx, bz in ((-8.0, cz), (8.0, cz), (0.0, cz - 8.0), (0.0, cz + 8.0)):
        put("library:Station_Bench", (bx, bz), half=(0.7, 0.3))
    for tx in (west + 10.0, west + 26.0, east - 26.0, east - 10.0):
        put(N + "CommonTree_3", (tx, cz + 4.0), collide="none", half=(0.4, 0.4))
    put("library:Plaza_BikeRack", (west + 10.0, D / 2 - 3.0), half=(3.0, 1.0), repeat=[4, 6.2, 0])
    put("library:Station_VendingMachine", (east - 3.0, D / 2 - 6.0), yaw=270.0, half=(0.4, 0.5), repeat=[3, 0, 1.1])
    put("library:Station_Bin", (west + 4.0, cz), half=(0.3, 0.3))
    return {
        "id": ID, "footprint_m": [round(W, 3), round(D, 3)],
        "jp": {"name": "駅前広場 (西副都心駅)",
               "note": "The west sub-centre station's forecourt between the station, its front street, the 商店街 and "
                       "the station mall: bus stops and the taxi rank on the front street's kerb (no rotary: it does "
                       "not fit between the 踏切 and the x -650 junction), the plaza with the clock, benches, trees and "
                       "bike racks. PLACEHOLDER props. Written by tools/building_kit/site_west_forecourt.py -- edit "
                       "that, not this entry."},
        "use": "the west sub-centre station's 駅前広場, derived from the west_station_forecourt reserve",
        "parts": [], "placeholder": True, "reserve": True,
        # the whole plaza is paved ground (its collider over the footprint)
        "ground_box": [round(-W / 2, 3), round(-D / 2, 3), round(W / 2, 3), round(D / 2, 3)],
        "probe_xz": [0.0, round(cz + 20.0, 3)],
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
