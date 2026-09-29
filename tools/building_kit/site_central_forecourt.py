#!/usr/bin/env python3
"""site_central_forecourt.py -- the `CentralForecourt` composite (the central station's 駅前広場, user 2026-09-28),
written into `assets/world_source/buildings/building_types.json` (replacing the entry of that id).

    python3 tools/building_kit/site_central_forecourt.py [--check]

DERIVED from the two facts it dresses, so neither can move without it: the `central_forecourt` reserve
(`island_plan.RESERVES`, the site's footprint) and the one-way `ekimae_rotary` (`island_core_streets.STREETS`: its
corners and its lanes / footways). The rotary runs clockwise (Japan keeps left): in from ekimae_dori up the WEST leg,
east along the TOP leg in front of the station, out down the EAST leg. A one-way road lays its lanes on the LEFT of its
stations, so the stations are the loop's inner edge and the lanes + the 4 m outer footway lie outboard.

What stands where, the Japanese hub layout (Tokyo 八重洲口 / Shinjuku 西口 in miniature):
* the BUS berths on the top leg's outer (station-side) kerb, four shelters + signs, a covered walk (屋根付き歩道)
  behind them to the station's doors;
* the TAXI rank on the east leg's outer kerb (タクシーのりば), the taxis queue in its kerb lane;
* the 立体駐車場 in the west zone, its ramp mouth facing the west leg (cars turn LEFT into it, the easy turn);
* the 交番 and a 駐輪場 in the east zone, another 駐輪場 by the car park;
* the plaza along the station face: the clock, benches; the rotary's inner island is planted.
Nothing stands on the roads: every prop is checked against the rotary's own paved bands before it is written.

Composite frame (the building convention): X along the station (record x), +Z the FRONT = south (record -y), origin
at the reserve's centre. Record (x, y) -> local (x - cx, -(y - cy)).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import island_plan as PL             # noqa: E402
import island_core_streets as CS     # noqa: E402

TYPES = os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")
ID = "CentralForecourt"
LANE_W = 4.5
N = "quaternius_stylized_nature:"


def frame():
    x0, z0, x1, z1 = dict(PL.RESERVES)["central_forecourt"]
    rot = next(s for s in CS.STREETS if s["name"] == "ekimae_rotary")
    return (x0, z0, x1, z1), rot


def entry():
    (x0, z0, x1, z1), rot = frame()
    W, D = x1 - x0, z1 - z0
    cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0            # Godot centre; record y = -z

    def L(rx, ry):                                       # record (x, y) -> local (x, z)
        return rx - cx, -ry - cz
    c = rot["corners"]
    walk_out, walk_in = rot["walks"]
    lanes = rot["lanes"] * LANE_W
    xw, _ = L(c[1][0], 0.0)                              # the west leg's station line (local x)
    xe, _ = L(c[2][0], 0.0)                              # the east leg's
    _, zt = L(0.0, c[1][1])                              # the top leg's (local z)
    # the rotary's paved bands (lanes + both footways), local [x0, z0, x1, z1]: west leg's lanes WEST of its line,
    # the top leg's NORTH (-z) of it, the east leg's EAST of it
    bands = [(xw - lanes - walk_out, zt - lanes - walk_out, xw + walk_in, D / 2),
             (xw - lanes - walk_out, zt - lanes - walk_out, xe + lanes + walk_out, zt + walk_in),
             (xe - walk_in, zt - lanes - walk_out, xe + lanes + walk_out, D / 2)]
    kerb_top = zt - lanes - walk_out                     # the top leg's outer (station-side) footway edge
    plaza = (-W / 2, -D / 2, W / 2, kerb_top)            # between that edge and the station face
    props, keep = [], []

    def put(piece, at, yaw=0.0, collide=None, half=(0.5, 0.5), **kw):
        """A prop, refused if its footprint (`half`, local x/z half sizes after its yaw) touches a band -- except a
        kerbside prop (`kerb=True`, a sign or a shelter post on a footway) which may stand on the footway itself."""
        kerb = kw.pop("kerb", False)
        hx, hz = half
        for b in bands:
            if kerb:
                break
            if at[0] + hx > b[0] and at[0] - hx < b[2] and at[1] + hz > b[1] and at[1] - hz < b[3]:
                raise SystemExit("%s: %s at %s stands on the rotary" % (ID, piece, at))
        if not (-W / 2 <= at[0] - hx and at[0] + hx <= W / 2 and -D / 2 <= at[1] - hz and at[1] + hz <= D / 2):
            raise SystemExit("%s: %s at %s leaves the footprint" % (ID, piece, at))
        p = {"piece": piece, "at": [round(at[0], 3), round(at[1], 3)]}
        if yaw:
            p["yaw"] = yaw
        if collide is not None:
            p["collide"] = collide
        p.update(kw)
        props.append(p)
        keep.append((piece, at))

    # the 立体駐車場, west zone, its mouth (+Z) turned east to the west leg (yaw 90), 40 m along x once turned
    wz0 = -W / 2
    wz1 = xw - lanes - walk_out
    park_x = (wz0 + wz1) / 2.0 - 1.0                     # 9-10 m of apron between its mouth and the footway
    put("library:Parking_Multistorey", (park_x, 2.0), yaw=90.0, half=(20.0, 15.0))
    put("library:Plaza_BikeRack", (park_x - 12.4, D / 2 - 5.0), half=(3.0, 1.0), repeat=[4, 6.2, 0])
    # the BUS berths: four shelters on the plaza edge behind the top leg's outer footway, a sign at each on the kerb
    for i, bx in enumerate((-72.0, -48.0, -24.0, 0.0)):
        put("library:BusStop_Shelter", (bx, kerb_top - 1.2), half=(2.0, 0.8))
        put("library:BusStop_Sign", (bx + 3.0, kerb_top + 0.6), kerb=True, half=(0.1, 0.3))
    # the covered walk from the berths to the station face: 10 m bays, posts on the kerb side
    put("library:Plaza_Canopy", (-80.0, kerb_top - 4.5), half=(5.0, 2.0), collide="none", repeat=[9, 10.0, 0])
    # the TAXI rank: the sign on the east leg's outer footway, the taxis queue in its kerb lane
    put("library:Taxi_Sign", (xe + lanes + walk_out / 2, zt + 8.0), yaw=90.0, kerb=True, half=(0.4, 0.4))
    put("library:Station_Bench", (xe + lanes + walk_out + 2.0, zt + 12.0), yaw=90.0, half=(0.3, 0.7))
    # the 交番 (its 8 x 10 m plot) facing the plaza, and a 駐輪場 in the east zone
    ez0 = xe + lanes + walk_out
    put("library:Civic_Koban", ((ez0 + W / 2) / 2.0, -D / 2 + 7.0), half=(4.0, 5.0))
    put("library:Plaza_BikeRack", (ez0 + 12.0, D / 2 - 5.0), half=(3.0, 1.0), repeat=[4, 6.2, 0])
    # the plaza: the clock, benches, vending machines by the car park
    put("library:Plaza_Clock", (40.0, (plaza[1] + plaza[3]) / 2.0), half=(0.6, 0.6))
    for bx in (20.0, 55.0, 70.0):
        put("library:Station_Bench", (bx, (plaza[1] + plaza[3]) / 2.0), half=(0.7, 0.3))
    put("library:Station_VendingMachine", (wz1 - 2.0, -D / 2 + 4.0), yaw=90.0, half=(0.4, 0.5), repeat=[3, 0, 1.1])
    # the rotary's inner island, planted: a row of trees down its middle
    iz0, iz1 = zt + walk_in, D / 2
    for tx in range(int(xw + walk_in + 20), int(xe - walk_in - 19), 22):     # clear of the pads' kerb returns
        put(N + "CommonTree_3", (float(tx), (iz0 + iz1) / 2.0), collide="none", half=(0.4, 0.4))
    return {
        "id": ID, "footprint_m": [round(W, 3), round(D, 3)],
        "jp": {"name": "駅前広場 (セントラル駅)",
               "note": "The central station's forecourt round the one-way ekimae_rotary: bus berths under a covered "
                       "walk on the station-side kerb, the taxi rank on the east leg, the 立体駐車場, the 交番, "
                       "駐輪場, the clock. PLACEHOLDER props (library_civic.py plaza_*). Written by "
                       "tools/building_kit/site_central_forecourt.py -- edit that, not this entry."},
        "use": "the central station's 駅前広場, derived from the central_forecourt reserve and the ekimae_rotary",
        "parts": [], "placeholder": True, "reserve": True,
        # the plaza's ground collider only (the rotary's own paving is the road's); the block-ground stage fills the
        # terrain under the rest (island_sites LEVELLED_RESERVES)
        "ground_box": [round(plaza[0], 3), round(plaza[1], 3), round(plaza[2], 3), round(plaza[3], 3)],
        "probe_xz": [60.0, round((plaza[1] + plaza[3]) / 2.0, 3)],
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
