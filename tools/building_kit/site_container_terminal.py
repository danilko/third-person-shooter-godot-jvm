#!/usr/bin/env python3
"""site_container_terminal.py -- the `ContainerTerminal` composite site (PLAN.md 3.8 step 5), written into
`assets/world_source/buildings/building_types.json` (replacing the entry of that id). Re-run after changing a number.

    python3 tools/building_kit/site_container_terminal.py

Site frame (Godot axes, the composite convention): X along the quay, +Z the front = the SEA. 364 x 218.4 m, ten by six
`Harbour_Apron` slabs. Sizes are real: the ISO boxes (`build_zombie_yard.ISO_*`), the ship-to-shore crane on a
30.48 m gauge with its seaside rail `QUAY_SETBACK` from the quay line, a yard of 40 ft stacks (Quaternius' containers,
`blender/tools/build_zombie_yard.py`; the yard clutter by the gate too) in blocks of 8 bays with
truck lanes between, one strip of 20 ft boxes, bollards every 20 m on the edge, light masts. Stacks are 1-3 high by a
fixed pattern, so a rebuild is identical. Placement on the island: `tools/island_sites.py`.
"""
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TYPES = os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")

W, D = 364.0, 218.4
EDGE = D / 2                     # the quay line, +Z
QUAY_SETBACK = 2.0               # seaside rail from the quay line
GAUGE = 30.48
BAY = 12.192 + 0.3               # a 40 ft box and the gap to the next one
ROW = 2.438 + 0.4
TIER = 2.591 + 0.01
COLOURS = ("Red", "Green")
Z = "quaternius_zombie_apocalypse:"   # the containers and the yard clutter are Quaternius' (CC0)
TIERS = (2, 3, 1, 2, 3, 2)       # rows' stack heights, repeated
# The crane's collider, in its own frame (Godot axes; library_procedural.harbour_crane): the four bogies and legs, the
# portal's sill and side beams at 18 m and the girders at 44 m -- NOT its bounds, which are mostly air: a truck or a
# character drives and walks under the portal. A detailed crane model replacing the placeholder brings its own boxes.
_G, _S = GAUGE / 2, 17.0 / 2
CRANE_BOXES = ([[sx * _S, 0.6, sz * _G, 2.0, 1.2, 3.0] for sx in (-1, 1) for sz in (-1, 1)]        # bogies
               + [[sx * _S, 23.1, sz * _G, 1.6, 43.8, 1.6] for sx in (-1, 1) for sz in (-1, 1)]   # legs
               + [[0.0, 19.0, sz * _G, 2 * _S + 1.6, 2.0, 1.6] for sz in (-1, 1)]                  # sill beams
               + [[sx * _S, 19.0, 0.0, 1.6, 2.0, 2 * _G + 1.6] for sx in (-1, 1)]                  # side beams
               + [[sx * _S, 44.0, -5.6, 1.6, 2.0, 43.28] for sx in (-1, 1)])                       # girders
MAST_BOXES = [[0.0, 0.2, 0.0, 1.2, 0.4, 1.2], [0.0, 15.2, 0.0, 0.7, 29.6, 0.7]]                    # base, pole


def entry():
    props = []
    crane_z = EDGE - QUAY_SETBACK - GAUGE / 2
    for x in (-120.0, -40.0, 40.0, 120.0):
        props.append({"piece": "library:Harbour_Crane", "at": [x, crane_z], "collide": {"boxes": CRANE_BOXES}})
    props.append({"piece": "library:Harbour_Bollard", "at": [-170.0, EDGE - 0.6], "repeat": [18, 20.0, 0.0]})
    for x in (-150.0, -50.0, 50.0, 150.0):
        for z in (20.0, -60.0):
            props.append({"piece": "library:Harbour_LightMast", "at": [x, z], "collide": {"boxes": MAST_BOXES}})
    # the 40 ft yard: two strips of three blocks, rows running along X
    blocks = (-163.9, -43.9, 76.1)
    k = 0
    for strip_z in (52.0, 2.0):
        for bx in blocks:
            for r in range(5):
                z = strip_z - r * ROW
                colour = COLOURS[(k + r) % len(COLOURS)]
                for t in range(TIERS[(k + r) % len(TIERS)]):
                    props.append({"piece": Z + "Container_40_%s" % colour, "at": [bx, z], "y": round(t * TIER, 3),
                                  "repeat": [8, BAY, 0.0]})
            k += 1
    # one strip of 20 ft boxes at the back
    for bx in (-160.0, -40.0, 80.0):
        for r in range(4):
            z = -40.0 - r * ROW
            colour = ("Red", "Green")[r % 2]
            for t in range(1 + (r % 2)):
                props.append({"piece": Z + "Container_20_%s" % colour, "at": [bx, z], "y": round(t * TIER, 3),
                              "repeat": [14, 6.058 + 0.3, 0.0]})
    # yard clutter by the gate (the land side, -Z): pallets, drums, cones along the gate lane, a barrier line
    props.append({"piece": Z + "Pallet", "at": [-172.0, -100.0], "repeat": [6, 1.4, 0.0]})
    props.append({"piece": Z + "Pallet", "at": [-172.0, -100.0], "y": 0.14, "repeat": [4, 1.4, 0.0]})
    props.append({"piece": Z + "Barrel", "at": [-160.0, -103.0], "repeat": [5, 0.9, 0.0]})
    props.append({"piece": Z + "TrafficCone", "at": [-120.0, -104.0], "repeat": [12, 6.0, 0.0], "collide": "none"})
    props.append({"piece": Z + "PlasticBarrier", "at": [100.0, -104.0], "repeat": [10, 1.1, 0.0]})
    props.append({"piece": Z + "TyreStack", "at": [170.0, -100.0], "repeat": [3, 0.8, 0.0]})
    return {
        "id": "ContainerTerminal",
        "footprint_m": [W, D],
        "jp": {"name": "コンテナターミナル",
               "note": "ISO boxes and a 30.48 m gauge ship-to-shore crane at real size; booms raised (idle berth)"},
        "use": "container terminal: four gantry cranes on the quay (+Z, the sea), a yard of 40 ft and 20 ft stacks with "
               "truck lanes, bollards on the edge, light masts",
        "parts": [],
        "props": props,
        "apron": "library:Harbour_Apron",
        "probe_xz": [0.0, -95.0],
        # under every crane's portal: a truck and a character pass (its collider is legs and beams, not its bounds)
        "clear_probes": [[x, EDGE - QUAY_SETBACK - GAUGE / 2] for x in (-120.0, -40.0, 40.0, 120.0)],
    }


def main():
    d = json.load(open(TYPES))
    d["composites"] = [c for c in d["composites"] if c.get("id") != "ContainerTerminal"] + [entry()]
    json.dump(d, open(TYPES, "w"), indent=1, ensure_ascii=False)
    open(TYPES, "a").write("\n")
    n = sum(p.get("repeat", [1])[0] for p in entry()["props"])
    print("site_container_terminal: %d props (%d placements) -> %s" % (len(entry()["props"]), n, TYPES))


if __name__ == "__main__":
    main()
