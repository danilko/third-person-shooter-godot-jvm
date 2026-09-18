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

    # PLAN.md 3.6b step 6 -- proportion rules. `attached`: sides that stand against a neighbour are one blank
    # party-wall row all the way up (no windows, no doors, no AC units -- there is no outside to hang them on).
    attached = set(t.get("attached", []))
    if not attached <= set(SIDES):
        raise SystemExit(f"{t['id']}: attached names an unknown side ({sorted(attached)})")
    for side in attached & set(doors):
        if doors[side]:
            raise SystemExit(f"{t['id']}: a door on the attached {side} side opens into the neighbour")
    for side in attached & set((t.get("ac_units") or {}).get("sides", [])):
        raise SystemExit(f"{t['id']}: AC units hung on the attached {side} side")

    def row_for(group, side):
        if side not in attached:
            return row_of(group, side)
        # the party wall matches the storey's height: banded when the storey's open sides are
        free = [sd for sd in SIDES if sd not in attached]
        banded = bool(free) and bool(rows[row_of(group, free[0])].get("band"))
        return kit["party_wall_row"]["banded" if banded else "plain"]

    # storeys, bottom up
    storeys = []
    for g in t["floors"]:
        for _ in range(g["count"]):
            banded = [bool(rows[row_for(g, sd)].get("band")) for sd in SIDES]
            if len(set(banded)) != 1:
                raise SystemExit(f"{t['id']}: a storey mixes banded and unbanded rows, so its sides "
                                 f"would stop at different heights")
            storeys.append((g, storey + (band_h if banded[0] else 0.0)))
    wall_top = sum(h for _, h in storeys)

    # `setback`: the top storeys step back from the street (the stepped top of a Japanese mid-rise, 道路斜線).
    # The front wall of a set-back storey stands `modules` modules in; the strip it leaves is a terrace at the
    # height the setback starts, edged with the parapet piece.
    sb = t.get("setback")
    k0 = len(storeys)
    sbd = 0.0
    if sb:
        if not 0 < sb["storeys"] < len(storeys):
            raise SystemExit(f"{t['id']}: setback storeys {sb['storeys']} must leave at least one full storey")
        if not 0 < sb["modules"] < nd / 2:
            raise SystemExit(f"{t['id']}: setback of {sb['modules']} modules must be under half the depth ({nd})")
        k0 = len(storeys) - sb["storeys"]
        sbd = sb["modules"] * m
    h_low = sum(h for _, h in storeys[:k0])          # the terrace level; == wall_top with no setback

    def geom(side, back):
        """(yaw, normal, start, along, n) of one side, with the front `back` metres in from the street."""
        yaw, nrm, start, along = side_frame(side, W, D)
        n = nw if side in ("front", "back") else nd
        if back:
            if side == "front":
                start = (start[0], start[1] - back)
            elif side == "right":
                start = (start[0], start[1] - back)
                n -= int(round(back / m))
            elif side == "left":
                n -= int(round(back / m))
        return yaw, nrm, start, along, n

    def at(g, i):
        return (g[2][0] + g[3][0] * m * (i + 0.5), g[2][1] + g[3][1] * m * (i + 0.5))

    base = 0.0
    for k, (g, h) in enumerate(storeys):
        back_k = sbd if k >= k0 else 0.0
        for side in SIDES:
            row = rows[row_for(g, side)]
            gm = geom(side, back_k)
            yaw = gm[0]
            door_idx = set(doors.get(side, [])) if k == 0 else set()
            if door_idx and not row.get("door"):
                raise SystemExit(f"{t['id']}: row {row_for(g, side)} has no door piece for the {side} door")
            for i in range(gm[4]):
                c = at(gm, i)
                name = row["door"] if i in door_idx else row["pieces"][i % len(row["pieces"])]
                put(name, (c[0], base, c[1]), yaw)
                if row.get("band"):
                    put(row["band"], (c[0], base + storey, c[1]), yaw)
                if row.get("rail"):
                    put(row["rail"], (c[0], base, c[1]), yaw)
            if row.get("corner"):
                put(row["corner"], (gm[2][0], base, gm[2][1]), 0.0)
        base += h

    # ac units on upper storeys
    ac = t.get("ac_units")
    if ac:
        base = storeys[0][1]
        for k in range(1, len(storeys)):
            for side in ac["sides"]:
                gm = geom(side, sbd if k >= k0 else 0.0)
                for i in range(gm[4]):
                    if (i + k) % ac["every"] == 0:
                        c = at(gm, i)
                        put(kit["ac_unit"], (c[0], base + 0.35, c[1]), gm[0])
            base += storeys[k][1]

    # floors: the ground slab, a ceiling over the ground storey (the only storey one can enter), and the roof --
    # at the wall top, or at the terrace level over a setback strip
    roof = pieces["pieces"][kit["roof_tile"]]
    for j in range(nd):
        for i in range(nw):
            x, z = -W / 2 + m * (i + 0.5), -D / 2 + m * (j + 0.5)
            put(kit["floor_tile"], (x, 0.0, z), 0.0)
            if len(storeys) > 1:
                put(kit["floor_tile"], (x, storeys[0][1], z), 0.0)
            level = h_low if z > D / 2 - sbd else wall_top
            put(kit["roof_tile"], (x, level - roof["max"][1], z), 0.0)

    # parapet (+ cornice) all round the top; the terrace gets the parapet piece along its open edges
    par = kit["parapets"][t["parapet"]]
    par_h = pieces["pieces"][par["piece"]]["size"][1]
    top = wall_top + par_h
    for side in SIDES:
        gm = geom(side, sbd)
        for i in range(gm[4]):
            c = at(gm, i)
            put(par["piece"], (c[0], wall_top, c[1]), gm[0])
            if par.get("cornice"):
                put(par["cornice"], (c[0], top, c[1]), gm[0])
    terrace = []                                    # (side, first module, last module + 1) of the terrace edge
    if sbd:
        s_mod = sb["modules"]
        terrace = [("front", 0, nw), ("right", 0, s_mod), ("left", nd - s_mod, nd)]
        for side, i0, i1 in terrace:
            gm = geom(side, 0.0)
            for i in range(i0, i1):
                c = at(gm, i)
                put(par["piece"], (c[0], h_low, c[1]), gm[0])
    total = top + (pieces["pieces"][par["cornice"]]["size"][1] if par.get("cornice") else 0.0)

    # `stair_house` (塔屋): every flat roof over three storeys has one, where the stair comes out. A block of
    # `kit.stair_house` at the back-left corner of the top roof, its door facing the roof. The declared height
    # (`jp.height_m`, the roofline) excludes it, as Japanese height rules do for a small roof structure; the
    # mesh height includes it.
    sh = kit.get("stair_house")
    stair_top = 0.0
    sh_box = None
    if sh and t.get("stair_house", len(storeys) > 3):
        sw_, sd_ = sh["modules"]
        srow = rows[sh["row"]]
        sh_h = storey + (band_h if srow.get("band") else 0.0)
        ox, oz = -W / 2 + m, -D / 2 + m               # one module in from the parapet on both sides
        SW, SD = sw_ * m, sd_ * m
        cx, cz = ox + SW / 2, oz + SD / 2
        for side in SIDES:
            yaw, nrm, start, along = side_frame(side, SW, SD)
            n = sw_ if side in ("front", "back") else sd_
            for i in range(n):
                c = (cx + start[0] + along[0] * m * (i + 0.5), cz + start[1] + along[1] * m * (i + 0.5))
                name = srow["door"] if (side == "front" and i == 0) else srow["pieces"][i % len(srow["pieces"])]
                put(name, (c[0], wall_top, c[1]), yaw)
                if srow.get("band"):
                    put(srow["band"], (c[0], wall_top + storey, c[1]), yaw)
        for j in range(sd_):
            for i in range(sw_):
                put(kit["roof_tile"], (ox + m * (i + 0.5), wall_top + sh_h - roof["max"][1], oz + m * (j + 0.5)), 0.0)
        stair_top = wall_top + sh_h
        sh_box = ((cx, wall_top + sh_h / 2, cz), (SW, sh_h, SD))
        out["stair_house"] = {"center": [round(cx, 5), round(wall_top, 5), round(cz, 5)],
                              "size": [round(SW, 5), round(sh_h, 5), round(SD, 5)]}

    # roof units: on the top roof, clear of the stair house and of the roof's centre (where the probe looks)
    for u in range(t.get("roof_units", 0)):
        x = -W / 2 + W * (u + 1) / (t["roof_units"] + 1)
        z = -D / 4 if sh_box is None else ((-D / 2 + m + sh_box[1][2]) + (D / 2 - sbd)) / 2
        put(kit["ac_unit"], (x, wall_top, z), 0.0)

    # collision: one box per side (split round the ground storey's door openings); with a setback the side's
    # lower part runs full length to the terrace and its upper part stands back, and the terrace edge has its own
    thick = pieces["pieces"][rows[row_for(storeys[0][0], "front")]["pieces"][0]]["size"][2]
    thick = max(thick, 0.18)
    hw, dh = kit["door_opening"][0] * s, kit["door_opening"][1] * s
    h0 = storeys[0][1]

    def box(side, a0, a1, y0, y1, back=0.0):
        if y1 - y0 <= 1e-9 or a1 - a0 <= 1e-9:
            return
        yaw, nrm, start, along, _n = geom(side, back)
        mid = (a0 + a1) / 2
        cx = start[0] + along[0] * mid - nrm[0] * thick / 2
        cz = start[1] + along[1] * mid - nrm[1] * thick / 2
        length = a1 - a0
        sx = abs(along[0]) * length + abs(nrm[0]) * thick
        sz = abs(along[1]) * length + abs(nrm[1]) * thick
        out["boxes"].append({"center": [round(cx, 5), round((y0 + y1) / 2, 5), round(cz, 5)],
                             "size": [round(sx, 5), round(y1 - y0, 5), round(sz, 5)]})

    low_top = top if not sbd else h_low             # the full-length part of every side
    for side in SIDES:
        n = nw if side in ("front", "back") else nd
        length = n * m
        yaw, nrm, start, along = side_frame(side, W, D)
        idx = sorted(doors.get(side, []))
        if sbd:
            gm = geom(side, sbd)
            a0 = 0.0 if side != "left" else 0.0
            box(side, a0, gm[4] * m, h_low, top, sbd)
        if not idx:
            box(side, 0.0, length, 0.0, low_top)
            continue
        box(side, 0.0, length, h0, low_top)
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
    for side in SIDES:
        n = nw if side in ("front", "back") else nd
        idx = sorted(doors.get(side, []))
        if not idx:
            continue
        yaw, nrm, start, along = side_frame(side, W, D)
        solid = next(i for i in range(n) if i not in idx)
        c = m * (solid + 0.5)
        out["solid_probes"].append({"side": side, "module": solid,
                                    "center": [round(start[0] + along[0] * c, 5), 0.0,
                                               round(start[1] + along[1] * c, 5)],
                                    "outward": [nrm[0], 0, nrm[1]]})
    for side, i0, i1 in terrace:
        box(side, i0 * m, i1 * m, h_low, h_low + par_h)
    out["boxes"].append({"center": [0, -0.05, 0], "size": [round(W, 5), 0.1, round(D, 5)]})
    out["boxes"].append({"center": [0, round(wall_top - 0.1, 5), round(-sbd / 2, 5)],
                         "size": [round(W, 5), 0.2, round(D - sbd, 5)]})
    if sbd:
        out["boxes"].append({"center": [0, round(h_low - 0.1, 5), round(D / 2 - sbd / 2, 5)],
                             "size": [round(W, 5), 0.2, round(sbd, 5)]})
    if sh_box is not None:
        out["boxes"].append({"center": [round(v, 5) for v in sh_box[0]], "size": [round(v, 5) for v in sh_box[1]]})

    out["wall_top_m"] = round(wall_top, 4)
    out["roofline_m"] = round(total, 4)
    out["height_m"] = round(max(total, stair_top), 4)
    out["terrace_m"] = round(h_low, 4) if sbd else None
    out["setback_m"] = round(sbd, 4)
    out["storeys"] = [round(h, 4) for _, h in storeys]

    jp = t.get("jp", {})
    for key, got, tol in (("frontage_m", W, m), ("depth_m", D, m), ("height_m", total, storey)):  # roofline
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

    def covered(pt, boxes):
        return any(all(abs(pt[i] - bx["center"][i]) <= bx["size"][i] / 2 + 1e-6 for i in range(3)) for bx in boxes)

    b = by["PencilBuilding"]
    check(abs(b["footprint_m"][0] - 4 * 1.82) < 1e-6 and abs(b["footprint_m"][1] - 7 * 1.82) < 1e-6,
          f"pencil footprint {b['footprint_m']}")
    check(abs(b["wall_top_m"] - (3.64 + 6 * 2.73)) < 1e-6, f"pencil wall top {b['wall_top_m']}")
    check(len(b["doors"]) == 1 and b["doors"][0]["side"] == "front", "pencil has one front door by default")
    # every exterior wall piece's origin lies on the footprint boundary
    W, D = b["footprint_m"]
    walls = [p for p in b["pieces"] if p["yaw"] in (0.0, 180.0) and "Floor" not in p["piece"]
             and "Roof" not in p["piece"] and "Column" not in p["piece"] and "ACUnit" not in p["piece"]]
    below = [p for p in walls if p["pos"][1] < b["wall_top_m"] - 1e-6]      # the stair house stands on the roof
    back_rows = {round(-D / 2, 4), round(D / 2, 4), round(D / 2 - b["setback_m"], 4)}
    check(all(round(p["pos"][2], 4) in back_rows for p in below),
          "front/back wall pieces sit on z = -D/2, +D/2, or +D/2 - setback")
    # PLAN.md 3.6b step 6. setback: the top storey's front wall stands one module in; the terrace is its own roof
    terrace = b["terrace_m"]
    par_piece = json.load(open(os.path.join(KITS_DIR, b["kit"], "kit.json")))["parapets"]["metal"]["piece"]
    fronts_top = [p for p in below if p["yaw"] == 0.0 and p["pos"][1] >= terrace - 1e-6
                  and p["piece"] != par_piece]      # the terrace's parapet stands on the street line on purpose
    check(terrace is not None and fronts_top and all(abs(p["pos"][2] - (D / 2 - 1.82)) < 1e-4 for p in fronts_top),
          f"pencil top storey stands 1.82 m back from the street (terrace at {terrace})")
    air = [0.0, terrace + 1.5, D / 2 - 0.9]           # over the terrace, inside the parapet: open sky
    check(not covered(air, b["boxes"]), "nothing stands over the terrace")
    slab = [0.0, terrace - 0.1, D / 2 - 0.9]
    check(covered(slab, b["boxes"]), "the terrace is a floor")
    upper = [0.0, terrace + 1.0, D / 2 - 1.82 - 0.05]
    check(covered(upper, b["boxes"]), "the set-back front wall blocks")
    # attached: the party walls carry nothing but the kit's party-wall rows, and no AC unit
    kit = json.load(open(os.path.join(KITS_DIR, b["kit"], "kit.json")))
    party = {p for r in kit["party_wall_row"].values() for p in kit["rows"][r]["pieces"]}
    sides = [p for p in b["pieces"] if p["yaw"] in (90.0, 270.0) and p["pos"][1] < b["wall_top_m"] - 1e-6
             and abs(abs(p["pos"][0]) - W / 2) < 1e-4 and "Column" not in p["piece"]]
    check(sides and all(p["piece"] in party or "FirstFloor_Wall_1" in p["piece"] or "Plain_1" in p["piece"]
                        for p in sides), "pencil's attached sides are blank party walls")
    # stair house: on the >3-storey flat roofs, counted in the mesh height and NOT in the roofline
    check("stair_house" in b and b["height_m"] > b["roofline_m"], f"pencil has a stair house "
          f"(roofline {b['roofline_m']}, height {b['height_m']})")
    check("stair_house" not in by["Konbini"] and by["Konbini"]["height_m"] == by["Konbini"]["roofline_m"],
          "a one-storey konbini has none")
    hit = [0.0, b["wall_top_m"] + 0.5, 0.0]           # the probe's roof ray lands on open roof, not the stair house
    check(not covered(hit, b["boxes"]), "the stair house leaves the roof centre clear")
    for bad_key, bad_val, why in (("doors", {"left": [2]}, "opens into the neighbour"),
                                  ("setback", {"storeys": 7, "modules": 1}, "at least one full storey"),
                                  ("setback", {"storeys": 1, "modules": 4}, "under half the depth")):
        bad = json.loads(json.dumps(next(x for x in json.load(open(TYPES_PATH))["types"] if x["id"] == "PencilBuilding")))
        bad[bad_key] = bad_val
        try:
            layout_type(bad, KITS_DIR)
            check(False, f"refused: {why}")
        except SystemExit as e:
            check(why in str(e), f"refused: {why}")
    # door gap: no collision box covers the door centre at 1 m height; a box covers the solid probe
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
