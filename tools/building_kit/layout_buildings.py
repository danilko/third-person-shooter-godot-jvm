#!/usr/bin/env python3
"""layout_buildings.py -- where every piece of every building type goes. Pure python, no engine.

    python3 tools/building_kit/layout_buildings.py assets/world_source/buildings/building_types.json <out.json>
    python3 tools/building_kit/layout_buildings.py --self-test

Reads the building types and each kit's `kit.json` (rows, parapets) and `pieces.json` (measured,
normalised pieces), and writes one layout per type: piece placements, collision boxes, and the facts
a probe checks (footprint, wall top, total height, doors and a solid module per door side).
`tools/godot/build_building_scenes.gd` turns a layout into a scene and changes nothing in it.

Frame (BLENDER_CONVENTIONS.md "Asset"): Godot axes, +Y up, the origin at the footprint centre on the
ground, the FRONT facing +Z. A side's pieces are the kit's wall pieces turned about Y so their exterior
face (+Z in the piece) faces out of that side:

    side    yaw   exterior   modules run (left to right seen from outside)
    front     0   +Z         x from -W/2
    right    90   +X         z from +D/2
    back    180   -Z         x from +W/2
    left    270   -X         z from -D/2
"""
import json
import math
import os
import sys

SIDES = ("front", "right", "back", "left")
KITS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "world_source", "kits"))
TYPES_PATH = os.path.normpath(os.path.join(KITS_DIR, "..", "buildings", "building_types.json"))
YAW = {"front": 0.0, "right": 90.0, "back": 180.0, "left": 270.0}


def load_kit(root, kit_id):
    kit_dir = os.path.join(root, kit_id)
    kit = json.load(open(os.path.join(kit_dir, "kit.json")))
    pieces = json.load(open(os.path.join(kit_dir, "pieces.json")))
    if abs(pieces["module_scale"] - kit["module_scale"]) > 1e-9:
        raise SystemExit(f"{kit_id}: pieces.json is stale (module_scale {pieces['module_scale']} "
                         f"!= kit.json {kit['module_scale']}); run normalize_kit.py")
    return kit_dir, kit, pieces


def side_frame(side, W, D):
    """(yaw, outward normal, point at module 0's left end, along vector) for one side, in metres."""
    if side == "front":
        return 0.0, (0, 1), (-W / 2, D / 2), (1, 0)
    if side == "right":
        return 90.0, (1, 0), (W / 2, D / 2), (0, -1)
    if side == "back":
        return 180.0, (0, -1), (W / 2, -D / 2), (-1, 0)
    return 270.0, (-1, 0), (-W / 2, -D / 2), (0, 1)


def row_of(group, side):
    if side in group:
        return group[side]
    if side in ("left", "right") and "sides" in group:
        return group["sides"]
    raise SystemExit(f"floor group {group} names no row for side {side}")


def layout_type(t, root):
    kit_dir, kit, pieces = load_kit(root, t["kit"])
    s = kit["module_scale"]
    m = pieces["module_m"]
    storey = kit["source_storey_m"] * s
    band_h = 1.0 * s
    rows = kit["rows"]
    res = "res://" + os.path.relpath(kit_dir, _project_root()).replace(os.sep, "/")

    def piece_path(name):
        if name not in pieces["pieces"]:
            raise SystemExit(f"{t['id']}: piece {name} is not in {t['kit']}")
        return res + "/" + pieces["pieces"][name]["path"]

    nw, nd = t["modules"]
    W, D = nw * m, nd * m
    out = {"id": t["id"], "kit": t["kit"], "use": t.get("use", ""), "jp": t.get("jp", {}),
           "module_m": m, "modules": [nw, nd], "footprint_m": [round(W, 4), round(D, 4)],
           "pieces": [], "boxes": [], "doors": [], "solid_probes": []}
    place = out["pieces"]

    def put(name, pos, yaw):
        place.append({"piece": name, "path": piece_path(name), "pos": [round(v, 5) for v in pos],
                      "yaw": yaw})

    doors = t.get("doors", {"front": [nw // 2]})
    for side, idx in doors.items():
        n = nw if side in ("front", "back") else nd
        for i in idx:
            if not 0 <= i < n:
                raise SystemExit(f"{t['id']}: door module {i} is off the {side} side ({n} modules)")

    # storeys, bottom up
    storeys = []
    for g in t["floors"]:
        for _ in range(g["count"]):
            banded = [bool(rows[row_of(g, sd)].get("band")) for sd in SIDES]
            if len(set(banded)) != 1:
                raise SystemExit(f"{t['id']}: a storey mixes banded and unbanded rows, so its sides "
                                 f"would stop at different heights")
            storeys.append((g, storey + (band_h if banded[0] else 0.0)))
    wall_top = sum(h for _, h in storeys)

    base = 0.0
    for k, (g, h) in enumerate(storeys):
        for side in SIDES:
            row = rows[row_of(g, side)]
            yaw, nrm, start, along = side_frame(side, W, D)
            n = nw if side in ("front", "back") else nd
            door_idx = set(doors.get(side, [])) if k == 0 else set()
            if door_idx and not row.get("door"):
                raise SystemExit(f"{t['id']}: row {row_of(g, side)} has no door piece for the {side} door")
            for i in range(n):
                c = (start[0] + along[0] * m * (i + 0.5), start[1] + along[1] * m * (i + 0.5))
                name = row["door"] if i in door_idx else row["pieces"][i % len(row["pieces"])]
                put(name, (c[0], base, c[1]), yaw)
                if row.get("band"):
                    put(row["band"], (c[0], base + storey, c[1]), yaw)
                if row.get("rail"):
                    put(row["rail"], (c[0], base, c[1]), yaw)
            if row.get("corner"):
                put(row["corner"], (start[0], base, start[1]), 0.0)
        base += h

    # ac units on upper storeys
    ac = t.get("ac_units")
    if ac:
        base = storeys[0][1]
        for k in range(1, len(storeys)):
            for side in ac["sides"]:
                yaw, nrm, start, along = side_frame(side, W, D)
                n = nw if side in ("front", "back") else nd
                for i in range(n):
                    if (i + k) % ac["every"] == 0:
                        c = (start[0] + along[0] * m * (i + 0.5), start[1] + along[1] * m * (i + 0.5))
                        put(kit["ac_unit"], (c[0], base + 0.35, c[1]), yaw)
            base += storeys[k][1]

    # floors: the ground slab, and a ceiling over the ground storey (the only storey one can enter)
    for j in range(nd):
        for i in range(nw):
            x, z = -W / 2 + m * (i + 0.5), -D / 2 + m * (j + 0.5)
            put(kit["floor_tile"], (x, 0.0, z), 0.0)
            if len(storeys) > 1:
                put(kit["floor_tile"], (x, storeys[0][1], z), 0.0)
            roof = pieces["pieces"][kit["roof_tile"]]
            put(kit["roof_tile"], (x, wall_top - roof["max"][1], z), 0.0)

    # parapet (+ cornice) all round
    par = kit["parapets"][t["parapet"]]
    par_h = pieces["pieces"][par["piece"]]["size"][1]
    top = wall_top + par_h
    for side in SIDES:
        yaw, nrm, start, along = side_frame(side, W, D)
        n = nw if side in ("front", "back") else nd
        for i in range(n):
            c = (start[0] + along[0] * m * (i + 0.5), start[1] + along[1] * m * (i + 0.5))
            put(par["piece"], (c[0], wall_top, c[1]), yaw)
            if par.get("cornice"):
                put(par["cornice"], (c[0], top, c[1]), yaw)
    total = top + (pieces["pieces"][par["cornice"]]["size"][1] if par.get("cornice") else 0.0)

    # roof units
    for u in range(t.get("roof_units", 0)):
        x = -W / 2 + W * (u + 1) / (t["roof_units"] + 1)
        put(kit["ac_unit"], (x, wall_top, -D / 4), 0.0)

    # collision: one box per side, split round the ground storey's door openings
    thick = pieces["pieces"][rows[row_of(storeys[0][0], "front")]["pieces"][0]]["size"][2]
    thick = max(thick, 0.18)
    hw, dh = kit["door_opening"][0] * s, kit["door_opening"][1] * s
    h0 = storeys[0][1]

    def box(side, a0, a1, y0, y1):
        yaw, nrm, start, along = side_frame(side, W, D)
        mid = (a0 + a1) / 2
        cx = start[0] + along[0] * mid - nrm[0] * thick / 2
        cz = start[1] + along[1] * mid - nrm[1] * thick / 2
        length = a1 - a0
        sx = abs(along[0]) * length + abs(nrm[0]) * thick
        sz = abs(along[1]) * length + abs(nrm[1]) * thick
        out["boxes"].append({"center": [round(cx, 5), round((y0 + y1) / 2, 5), round(cz, 5)],
                             "size": [round(sx, 5), round(y1 - y0, 5), round(sz, 5)]})

    for side in SIDES:
        n = nw if side in ("front", "back") else nd
        length = n * m
        yaw, nrm, start, along = side_frame(side, W, D)
        idx = sorted(doors.get(side, []))
        if not idx:
            box(side, 0.0, length, 0.0, top)
            continue
        box(side, 0.0, length, h0, top)
        cursor = 0.0
        for i in idx:
            c = m * (i + 0.5)
            box(side, cursor, c - hw, 0.0, h0)
            box(side, c - hw, c + hw, dh, h0)
            cursor = c + hw
            p = (start[0] + along[0] * c, start[1] + along[1] * c)
            out["doors"].append({"side": side, "module": i, "center": [round(p[0], 5), 0.0, round(p[1], 5)],
                                 "outward": [nrm[0], 0, nrm[1]], "width": round(2 * hw, 5), "height": round(dh, 5)})
        box(side, cursor, length, 0.0, h0)
        solid = next(i for i in range(n) if i not in idx)
        c = m * (solid + 0.5)
        out["solid_probes"].append({"side": side, "module": solid,
                                    "center": [round(start[0] + along[0] * c, 5), 0.0,
                                               round(start[1] + along[1] * c, 5)],
                                    "outward": [nrm[0], 0, nrm[1]]})
    out["boxes"].append({"center": [0, -0.05, 0], "size": [round(W, 5), 0.1, round(D, 5)]})
    out["boxes"].append({"center": [0, round(wall_top - 0.1, 5), 0], "size": [round(W, 5), 0.2, round(D, 5)]})

    out["wall_top_m"] = round(wall_top, 4)
    out["height_m"] = round(total, 4)
    out["storeys"] = [round(h, 4) for _, h in storeys]

    jp = t.get("jp", {})
    for key, got, tol in (("frontage_m", W, m), ("depth_m", D, m), ("height_m", total, storey)):
        if key in jp and abs(jp[key] - got) > tol:
            raise SystemExit(f"{t['id']}: built {key} {got:.2f} m misses the declared {jp[key]} m "
                             f"by more than {tol:.2f}")
    return out


def layout_example(e, root):
    kit_dir, kit, pieces = load_kit(root, e["kit"])
    p = pieces["pieces"][e["piece"]]
    res = "res://" + os.path.relpath(kit_dir, _project_root()).replace(os.sep, "/")
    lo, hi = p["min"], p["max"]
    pos = [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2]
    return {"id": e["id"], "kit": e["kit"], "use": "kit example (re-scaled only)", "example": True,
            "pieces": [{"piece": e["piece"], "path": res + "/" + p["path"],
                        "pos": [round(v, 5) for v in pos], "yaw": 0.0}],
            "footprint_m": [p["size"][0], p["size"][2]], "height_m": p["size"][1], "wall_top_m": p["size"][1],
            "boxes": [], "doors": [], "solid_probes": [], "collision": "trimesh"}


def _project_root():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def layout_all(types_path):
    root = KITS_DIR
    doc = json.load(open(types_path))
    ids = [t["id"] for t in doc["types"]] + [e["id"] for e in doc.get("examples", [])]
    if len(ids) != len(set(ids)):
        raise SystemExit("building ids must be unique")
    return {"generated_by": "tools/building_kit/layout_buildings.py",
            "buildings": [layout_type(t, root) for t in doc["types"]] +
                         [layout_example(e, root) for e in doc.get("examples", [])]}


def self_test():
    doc = layout_all(TYPES_PATH)
    by = {b["id"]: b for b in doc["buildings"]}
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok &= bool(cond)

    b = by["PencilBuilding"]
    check(abs(b["footprint_m"][0] - 4 * 1.82) < 1e-6 and abs(b["footprint_m"][1] - 7 * 1.82) < 1e-6,
          f"pencil footprint {b['footprint_m']}")
    check(abs(b["wall_top_m"] - (3.64 + 6 * 2.73)) < 1e-6, f"pencil wall top {b['wall_top_m']}")
    check(len(b["doors"]) == 1 and b["doors"][0]["side"] == "front", "pencil has one front door by default")
    # every exterior wall piece's origin lies on the footprint boundary
    W, D = b["footprint_m"]
    walls = [p for p in b["pieces"] if p["yaw"] in (0.0, 180.0) and "Floor" not in p["piece"]
             and "Roof" not in p["piece"] and "Column" not in p["piece"] and "ACUnit" not in p["piece"]]
    check(all(abs(abs(p["pos"][2]) - D / 2) < 1e-4 for p in walls), "front/back wall pieces sit on z = +-D/2")
    # door gap: no collision box covers the door centre at 1 m height; a box covers the solid probe
    def covered(pt, boxes):
        return any(all(abs(pt[i] - bx["center"][i]) <= bx["size"][i] / 2 + 1e-6 for i in range(3)) for bx in boxes)
    for bid in ("PencilBuilding", "Konbini", "Warehouse", "Apartment"):
        bb = by[bid]
        for d in bb["doors"]:
            inside = [d["center"][0] - d["outward"][0] * 0.09, 1.0, d["center"][2] - d["outward"][2] * 0.09]
            check(not covered(inside, bb["boxes"]), f"{bid} {d['side']} door {d['module']} is open")
        for sp in bb["solid_probes"]:
            inside = [sp["center"][0] - sp["outward"][0] * 0.09, 1.0, sp["center"][2] - sp["outward"][2] * 0.09]
            check(covered(inside, bb["boxes"]), f"{bid} {sp['side']} module {sp['module']} is walled")
    check(len(by["Warehouse"]["doors"]) == 4, "warehouse has 3 front doors + 1 left")
    try:
        bad = json.loads(json.dumps(json.load(open(TYPES_PATH))["types"][0]))
        bad["jp"]["height_m"] = 60
        layout_type(bad, KITS_DIR)
        check(False, "a type whose height misses its declared metres is refused")
    except SystemExit as e:
        check("misses the declared" in str(e), "a type whose height misses its declared metres is refused")
    print("RESULT", "PASS" if ok else "FAIL")
    return ok


def main():
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(0 if self_test() else 1)
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    doc = layout_all(sys.argv[1])
    json.dump(doc, open(sys.argv[2], "w"), indent=1)
    for b in doc["buildings"]:
        print(f"{b['id']:18s} {len(b['pieces']):5d} pieces  {b['footprint_m'][0]:6.2f} x {b['footprint_m'][1]:6.2f} m"
              f"  wall top {b['wall_top_m']:6.2f}  total {b['height_m']:6.2f}  doors {len(b['doors'])}")


if __name__ == "__main__":
    main()
