#!/usr/bin/env python3
"""island_footbridges.py -- 横断歩道橋 (pedestrian footbridges) over the widest junction arms, from MEASURED facts
(user, 2026-10-10: "Japan equips air bridges on some intersections ... on the bigger street intersections, ones with
more than 2 lanes, as a way for peds to pass / show more tightness").

    python3 tools/island_footbridges.py [--check]     # place the FROZEN bridges (IslandFootbridges.json) in World.tscn
    python3 tools/island_footbridges.py --resite      # search again (after a road or furniture rebuild), then place
    python3 tools/island_footbridges.py --list        # every qualifying junction and why an arm was refused

The pieces are kits/interiors/Footbridge30.blend / Footbridge23.blend (blender/tools/street_plans.py: the standard's
4.7 m clearance, 2 m walkway, 0.15 / 0.30 stairs), each a streamed zone of its own like a site. WHERE one may stand is
read, never assumed:
* the junction and its arms from the baked lane records (`Roads_IslandRoads_island_*.lanekit.json`): an arm with 3
  lanes one way takes Footbridge30, one with 2 and a median takes Footbridge23, and only when its measured kerb-to-kerb width is
  the piece's (within KERB_TOL) -- a bridge is never stretched over a road it was not drawn for;
* the span is set back from the junction pad until its piers and stairs stand clear of every piece of street
  furniture the road pieces placed (lamps, trees, planters, signals: the `mmesh_*` nodes of the baked glTF), the arm
  is straight and level under it, and nothing is overhead (a rail viaduct, an expressway deck or ramp);
* at most MAX_SPANS arms a junction, the widest first, opposite arms preferred (both sides of the wide road).
Frozen like the sites (R6): an ordinary run never moves a bridge; a road rebuild that moves furniture is followed by
`--resite`, and `--check` fails when the scene is stale.
"""
import glob
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import island_traffic_zones as itz                  # noqa: E402

SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
PIECES = os.path.join(ROOT, "assets/world_source/pieces")
BAKED = os.path.join(ROOT, "src/main/resources/com/openworld/world/pieces")
FROZEN = os.path.join(ROOT, "assets/world_source/buildings/IslandFootbridges.json")
BUILDINGS = "res://src/main/resources/com/openworld/world/buildings/"
HOLDER = "IslandFootbridges"
SUB_PREFIX = "Zone_footbridge_"
NODE_ID_BASE = 910021000

# the pieces' own numbers (blender/tools/street_plans.py; --check-piece compares them with the built scenes' size)
PIECE = {3: ("Footbridge30", 15.25), 2: ("Footbridge23", 11.35)}     # lanes one way -> (scene, kerb half-width)
KERB_BACK, STAIR_W, WALK_HALF = 0.45, 1.6, 1.1
STAIR_LEN = 13.5            # from the deck's far edge to the stair foot + the metre a walker steps off onto
CLEAR = 4.7                 # under the girder
OVERHEAD_MIN = 9.5          # a lane this far over the road clears the railing (6.6 m) with a deck's depth and headroom
SHOULDER = 0.5              # outer lane edge to the kerb face (road presets)
KERB_TOL = 0.3
MAX_SPANS = 2
SETBACK_MIN, SETBACK_STEP = 5.0, 1.0     # the deck's centre from the pad edge, searched outward
FURN_CLEAR = 0.7            # a pier / stair keeps this off a furniture point; TALL kinds keep off the whole deck
TALL = ("lamp", "tree", "signal")        # mmesh_<kind> prefixes that stand higher than the girder's underside
IGNORE = ("drain", "arrow", "median", "mark", "ped_signal")   # flat, or shorter than the deck and beside the pad
LOAD = 380.0
# the junctions: every signalised 4-arm crossing of two 3+3 roads comes from the RULE below; these are the extra ones
# asked for by hand (a 3+3 road meeting a 2+2 one in the core)
EXTRA = ("j5b941bdd", "j28ce1f30", "j4bf395de")


def load():
    lanes, junctions, others, furniture = {}, [], [], []
    for f in sorted(glob.glob(os.path.join(PIECES, "Roads_IslandRoads_island_*.lanekit.json"))
                    + glob.glob(os.path.join(PIECES, "Roads_IslandRail_rail_*.lanekit.json"))):
        d = json.load(open(f))
        for l in d["lanes"]:
            lanes[l["id"]] = l
        if "IslandRail" not in f:
            junctions += d["junctions"]
    for f in sorted(glob.glob(os.path.join(BAKED, "Roads_IslandRoads_island_*.gltf"))):
        for n in json.load(open(f))["nodes"]:
            nm = n.get("name", "")
            if not nm.startswith("mmesh_") or "translation" not in n:
                continue
            kind = nm[len("mmesh_"):]
            if kind.startswith(IGNORE):
                continue
            t = n["translation"]
            furniture.append((t[0], t[2], kind))
    return lanes, junctions, furniture


class Grid:
    def __init__(self, pts, cell=20.0):
        self.cell, self.g = cell, {}
        for p in pts:
            self.g.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)

    def near(self, x, z, r):
        c = self.cell
        for i in range(int((x - r) // c), int((x + r) // c) + 1):
            for j in range(int((z - r) // c), int((z + r) // c) + 1):
                for p in self.g.get((i, j), ()):
                    yield p


def arm_frame(arm, lanes):
    """(centre point at the pad edge (x, y, z), unit direction AWAY from the junction (ux, uz), lanes one way,
    measured kerb half-width, the shortest through lane's length) or None when the arm's lanes are not in the record."""
    ins = [lanes[i] for i in arm["in_lanes"] if i in lanes]
    outs = [lanes[i] for i in arm["out_lanes"] if i in lanes]
    if not ins or not outs or len(ins) != len(outs):
        return None
    ends = [l["points"][-1] for l in ins] + [l["points"][0] for l in outs]
    cx = sum(p[0] for p in ends) / len(ends)
    cy = sum(p[1] for p in ends) / len(ends)
    cz = sum(p[2] for p in ends) / len(ends)
    a, b = ins[0]["points"][-1], ins[0]["points"][-2]
    L = math.hypot(b[0] - a[0], b[2] - a[2])
    ux, uz = (b[0] - a[0]) / L, (b[2] - a[2]) / L
    half = max(abs((p[0] - cx) * -uz + (p[2] - cz) * ux) for p in ends) + ins[0]["lane_width"] / 2 + SHOULDER
    length = min(sum(math.hypot(q[0] - p[0], q[2] - p[2]) for p, q in zip(l["points"], l["points"][1:]))
                 for l in ins + outs)
    return (cx, cy, cz), (ux, uz), len(ins), half, length, ins + outs


def straight_level(frame, t0, t1):
    """True when every lane of the arm is straight and level between t0 and t1 m from the pad edge."""
    (cx, cy, cz), (ux, uz), _n, _half, _len, ls = frame
    for l in ls:
        for p in l["points"]:
            t = (p[0] - cx) * ux + (p[2] - cz) * uz
            if t0 - 2.0 <= t <= t1 + 2.0 and abs(p[1] - cy) > 0.1:
                return False
        pts = [p for p in l["points"] if t0 - 2.0 <= (p[0] - cx) * ux + (p[2] - cz) * uz <= t1 + 2.0]
        lat = [(p[0] - cx) * -uz + (p[2] - cz) * ux for p in pts]
        if lat and max(lat) - min(lat) > 0.1:
            return False
    return True


def rects(half, t):
    """The bridge's plan with its deck centred `t` m from the pad edge, in the arm's (lateral, along) frame:
    ([pier / stair rectangles], the deck rectangle); each (lat0, lat1, along0, along1)."""
    s0, s1 = half + KERB_BACK, half + KERB_BACK + STAIR_W
    solid = []
    for s in (-1, 1):
        a, b = sorted((s * s0, s * s1))
        solid.append((a, b, t - 0.5, t + WALK_HALF + STAIR_LEN))        # the pier and the stair behind it
    if half > 12.0:
        solid.append((-0.5, 0.5, t - 0.5, t + 0.5))                    # the median pier
    deck = (-(s1 + 0.2), s1 + 0.2, t - WALK_HALF, t + WALK_HALF)
    return solid, deck


def conflict(frame, t, furn, over, own):
    """Why a bridge may NOT stand with its deck centred `t` m from this arm's pad edge, or None when it may.
    A reason starting with '!' holds for the whole arm (something overhead), not only for this slot."""
    (cx, cy, cz), (ux, uz), _n, half, _length, _ls = frame
    solid, deck = rects(half, t)
    if not straight_level(frame, t - WALK_HALF, t + WALK_HALF + STAIR_LEN):
        return "not straight and level"
    mx, mz = cx + ux * (t + 6.0), cz + uz * (t + 6.0)
    for p in furn.near(mx, mz, half + 14.0):
        lat = (p[0] - cx) * -uz + (p[1] - cz) * ux
        al = (p[0] - cx) * ux + (p[1] - cz) * uz
        for r in solid:
            if r[0] - FURN_CLEAR < lat < r[1] + FURN_CLEAR and r[2] - FURN_CLEAR < al < r[3] + FURN_CLEAR:
                return "%s in a pier / stair" % p[2]
        if p[2].startswith(TALL) and deck[0] - 1.0 < lat < deck[1] + 1.0 and deck[2] - 1.5 < al < deck[3] + 1.5:
            return "%s under the deck" % p[2]
    for p in over.near(mx, mz, half + 14.0):
        if p[3] in own:
            continue
        lat = (p[0] - cx) * -uz + (p[1] - cz) * ux
        al = (p[0] - cx) * ux + (p[1] - cz) * uz
        if abs(lat) < half + 8.0 and t - 6.0 < al < t + STAIR_LEN + 6.0 and 3.0 < p[2] - cy < OVERHEAD_MIN:
            return "!%s overhead (+%.0f m)" % (p[3].split("__")[0], p[2] - cy)
    return None


def place_arm(frame, furn, over, own):
    """The setback (m from the pad edge to the deck's centre) of the first clear slot on this arm, or a reason."""
    _c, _u, n, half, length, _ls = frame
    if n not in PIECE:
        return None, "%d lanes one way" % n
    if abs(half - PIECE[n][1]) > KERB_TOL:
        return None, "kerb half %.2f m is not the piece's %.2f" % (half, PIECE[n][1])
    t = SETBACK_MIN
    why = "the arm is %.0f m long: no room" % length
    while t + WALK_HALF + STAIR_LEN + 4.0 <= length:
        bad = conflict(frame, t, furn, over, own)
        if bad is None:
            return t, ""
        if bad.startswith("!"):
            return None, bad[1:]
        why = bad
        t += SETBACK_STEP
    return None, why


def own_lanes(j, lanes):
    """A junction's own lanes (its arms and its turn connectors): never "overhead" of it."""
    own = {l for a in j["arms"] for l in a["in_lanes"] + a["out_lanes"]}
    return own | {lid for lid in lanes if lid.startswith("c" + j["id"])}


REBIND_M = 60.0             # a frozen row's arm is looked for this near the row when its junction id is gone


def junction_of(r, byid, junctions, lanes):
    """The junction a FROZEN row stands at. Its recorded id first; when that id is gone, the junction with an arm of
    the row's road whose pad edge is within REBIND_M of the bridge. A junction's id is `j` + one of its mouths' uids
    (the smallest), and a GENERATED street's stations get new uids at every layout run: when such a mouth's new uid
    sorts first the junction is renamed and nothing else about it has changed (2026-10-13: `j4bf395de`, four mouths in
    the same places, read "its junction arm is gone" after a rebuild that touched nothing near it)."""
    j = byid.get(r["junction"])
    if j is not None:
        return j
    best = None
    for q in junctions:
        arm = next((a for a in q["arms"] if a["road"] == r["road"]), None)
        f = arm_frame(arm, lanes) if arm else None
        if f is None:
            continue
        d = math.hypot(f[0][0] - r["x"], f[0][2] - r["z"])
        if d < REBIND_M and (best is None or d < best[0]):
            best = (d, q)
    return best[1] if best else None


def verify(rows):
    """Every FROZEN bridge against TODAY's records: [(id, why)] for the ones that no longer fit (the road moved, a
    lamp or a tree now stands in a stair, something was built overhead). Run by --check."""
    lanes, junctions, furniture = load()
    furn = Grid(furniture)
    over = Grid([(p[0], p[2], p[1], l["id"]) for l in lanes.values() for p in l["points"]], cell=40.0)
    byid = {j["id"]: j for j in junctions}
    bad = []
    for r in rows:
        j = junction_of(r, byid, junctions, lanes)
        arm = next((a for a in (j["arms"] if j else ()) if a["road"] == r["road"]), None)
        f = arm_frame(arm, lanes) if arm else None
        if f is None:
            bad.append((r["id"], "its junction arm is gone from the lane records"))
            continue
        if f[2] not in PIECE or PIECE[f[2]][0] != r["scene"] or abs(f[3] - PIECE[f[2]][1]) > KERB_TOL:
            bad.append((r["id"], "the arm is no longer the piece's width"))
            continue
        (cx, _cy, cz), (ux, uz), _n, _half, _len, _ls = f
        t = (r["x"] - cx) * ux + (r["z"] - cz) * uz
        if abs((r["x"] - cx) * -uz + (r["z"] - cz) * ux) > 0.2:
            bad.append((r["id"], "it is off the road's centreline"))
            continue
        why = conflict(f, t, furn, over, own_lanes(j, lanes))
        if why:
            bad.append((r["id"], why.lstrip("!")))
    return bad


#: Where the road build reads the bridges' piers and stairs from (`roadkit_cli --keep-out`, beside the car parks'):
#: nothing that stands up is placed in one. A kerb-long ガードレール (2026-10-11) is why -- a bridge is sited where no
#: lamp or tree stands, but a rail runs the whole kerb, so the rail must yield to the bridge, not the bridge move.
KEEPOUT = os.path.join(ROOT, "assets/world_source/pieces/IslandFootbridges.keepout.json")
RAIL_HALF = 2.0             # half a guardrail module: a module is refused by its CENTRE


def write_keepout(rows):
    """Each frozen bridge's pier / stair rectangles (`rects`), grown by FURN_CLEAR (and half a rail module along the
    kerb), as keep-out boxes in the Godot frame: [x, z, ux, uz, half across, half deep], u the arm's direction."""
    lanes, junctions, _furniture = load()
    byid = {j["id"]: j for j in junctions}
    boxes = []
    for r in rows:
        j = junction_of(r, byid, junctions, lanes)
        arm = next((a for a in (j["arms"] if j else ()) if a["road"] == r["road"]), None)
        f = arm_frame(arm, lanes) if arm else None
        if f is None:
            continue
        (cx, _cy, cz), (ux, uz), _n, half, _len, _ls = f
        t = (r["x"] - cx) * ux + (r["z"] - cz) * uz
        for lat0, lat1, al0, al1 in rects(half, t)[0]:
            lat, al = 0.5 * (lat0 + lat1), 0.5 * (al0 + al1)
            boxes.append([round(cx + ux * al - uz * lat, 3), round(cz + uz * al + ux * lat, 3), round(ux, 5),
                          round(uz, 5), round(0.5 * (lat1 - lat0) + FURN_CLEAR + 0.05, 3),
                          round(0.5 * (al1 - al0) + FURN_CLEAR + RAIL_HALF, 3)])
    text = json.dumps({"notes": "Written by tools/island_footbridges.py: the 横断歩道橋 piers and stairs road furniture "
                                "keeps out of (roadkit_cli --keep-out). Godot frame [x, z, ux, uz, half across, "
                                "half deep].", "boxes": boxes}, indent=1, ensure_ascii=False) + "\n"
    if not os.path.exists(KEEPOUT) or open(KEEPOUT).read() != text:
        open(KEEPOUT, "w").write(text)
        print("island_footbridges: wrote %s (%d boxes)" % (os.path.relpath(KEEPOUT, ROOT), len(boxes)))


def search(listing=False):
    lanes, junctions, furniture = load()
    furn = Grid(furniture)
    over = Grid([(p[0], p[2], p[1], l["id"]) for l in lanes.values() for p in l["points"]], cell=40.0)
    rows = []
    for j in sorted(junctions, key=lambda j: j["id"]):
        frames = [(a, arm_frame(a, lanes)) for a in j["arms"]]
        frames = [(a, f) for a, f in frames if f is not None]
        wide = [f for _a, f in frames if f[2] >= 3]
        if not (j["id"] in EXTRA or (len(frames) == 4 and len(wide) == 4 and j.get("traffic_light"))):
            continue
        own = own_lanes(j, lanes)
        # the widest arms first, then opposite pairs: sort by lanes, then by bearing so a pair stays together
        frames.sort(key=lambda af: (-af[1][2], af[0]["bearing"] % 180.0, af[0]["bearing"]))
        got = []
        for a, f in frames:
            if f[2] not in PIECE or (got and f[2] < got[0][1][2]):
                continue
            t, why = place_arm(f, furn, over, own)
            if listing:
                print("  %s arm %-28s %d+%d kerb half %.2f len %.0f -> %s" % (
                    j["id"], a["road"], f[2], f[2], f[3], f[4], "setback %.0f m" % t if t is not None else "REFUSED: " + why))
            if t is None:
                continue
            got.append((a, f, t))
        # two arms: an opposite pair when there is one (both sides of one road), else the first two
        pick = got[:MAX_SPANS]
        for i in range(len(got)):
            for k in range(i + 1, len(got)):
                d = abs((got[i][0]["bearing"] - got[k][0]["bearing"] + 180.0) % 360.0 - 180.0)
                if abs(d - 180.0) < 20.0 and got[i][1][2] == got[0][1][2] and len(pick) == MAX_SPANS \
                        and not abs(abs((pick[0][0]["bearing"] - pick[1][0]["bearing"] + 180.0) % 360.0 - 180.0) - 180.0) < 20.0:
                    pick = [got[i], got[k]]
        for a, f, t in pick:
            (cx, cy, cz), (ux, uz), n, _half, _len, _ls = f
            x, z = cx + ux * t, cz + uz * t
            rows.append({"id": "%s_%s" % (j["id"], a["road"].split("__")[0] + ("%+04d" % round(a["bearing"]))),
                         "junction": j["id"], "road": a["road"], "scene": PIECE[n][0],
                         "x": round(x, 3), "z": round(z, 3), "y": round(cy, 3),
                         # +Z of the scene looks back at the junction; the stairs come down away from it
                         "yaw": round(math.degrees(math.atan2(-ux, -uz)), 4), "setback": t})
    return rows


def main(argv):
    if "--list" in argv:
        rows = search(listing=True)
        print("island_footbridges: %d bridge(s) would be placed" % len(rows))
        return
    frozen = json.load(open(FROZEN))["bridges"] if os.path.exists(FROZEN) else []
    if "--resite" in argv or not frozen:
        frozen = search()
        if "--check" not in argv:
            doc = {"notes": "Written by tools/island_footbridges.py --resite: each 横断歩道橋's Godot (x, z), the road "
                            "surface's lanekit height y (the IslandRoads node's own height is added when placed) and "
                            "yaw, FROZEN. An ordinary run only places them. Hand-edit a row (or delete one) freely; "
                            "--resite searches again and overwrites this file.",
                   "bridges": frozen}
            text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
            if not os.path.exists(FROZEN) or open(FROZEN).read() != text:
                open(FROZEN, "w").write(text)
                print("island_footbridges: wrote %s (%d bridges)" % (os.path.relpath(FROZEN, ROOT), len(frozen)))
    if "--check" not in argv:
        write_keepout(frozen)
    text = open(SCENE).read()
    ny = float(re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
               .group(1).split(",")[10])
    sections = itz.split_sections(text)
    zone_ext = itz.ext_resource_id(sections, itz.ZONE_SCRIPT)
    marker_ext = itz.ext_resource_id(sections, itz.MARKER_SCRIPT)
    sub, nodes = [], ['[node name="%s" type="Node" parent="." unique_id=%d]\n\n' % (HOLDER, NODE_ID_BASE)]
    for i, r in enumerate(frozen):
        a = math.radians(r["yaw"])
        c, s = math.cos(a), math.sin(a)
        y = ny + r["y"]
        sub.append('[sub_resource type="Resource" id="%s%s"]\n'
                   'script = ExtResource("%s")\n'
                   'zone_id = "footbridge_%s"\n'
                   'size = Vector3(40, 20, 40)\n'
                   'load_radius = %.1f\n'
                   'unload_radius = %.1f\n'
                   'geometry_path = "%s%s.tscn"\n'
                   'geometry_world_placed = true\n'
                   'geometry_world_transform = Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)\n\n'
                   % (SUB_PREFIX, r["id"], zone_ext, r["id"], LOAD, LOAD + 80.0, BUILDINGS, r["scene"],
                      c, s, -s, c, r["x"], y, r["z"]))
        nodes.append('[node name="Footbridge_%s" type="Node3D" parent="%s" unique_id=%d]\n'
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                     'script = ExtResource("%s")\n'
                     'zone = SubResource("%s%s")\n'
                     'show_debug_volume = false\n\n'
                     % (r["id"], HOLDER, NODE_ID_BASE + 1 + i, r["x"], y, r["z"], marker_ext, SUB_PREFIX, r["id"]))

    def generated(header):
        if header.startswith("[sub_resource"):
            return (itz.attr(header, "id") or "").startswith(SUB_PREFIX)
        if header.startswith("[node"):
            return itz.attr(header, "name") == HOLDER or itz.attr(header, "parent") == HOLDER
        return False
    new = itz.splice(sections, generated, sub, nodes)
    print("island_footbridges: %d bridge(s); scene %s" % (len(frozen), "changes" if new != text else "unchanged"))
    if "--check" in argv:
        stale = verify(frozen)
        for bid, why in stale:
            print("island_footbridges: STALE %s: %s (run --resite, or move / delete its row)" % (bid, why))
        sys.exit(1 if new != text or stale else 0)
    if new != text:
        open(SCENE, "w").write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
