#!/usr/bin/env python3
"""debug_world_scene.py -- write `assets/world_source/debug_world_layout.json` into DebugWorld.tscn.

    python3 tools/debug_world_scene.py [--check]

`tools/debug_world_layout.py` owns the layout; this tool only writes it into the scene, by NODE NAME, so a second run
rewrites the same nodes instead of adding more (idempotent). What it does:

  * removes the hand-placed CSG blockout under `NavigationRegion3D` (every child but `Terrain3D`) and its
    sub-resources, and empties the world navmesh that was baked over it (the road pieces carry their own);
  * moves the spawn, the player, the parked cars, the ammo refill and the pickup row onto the new ground;
  * sets the world bounds, the two road zone markers (`ZoneA` / `ZoneB`) and their radii;
  * adds (or rewrites) the `DebugRail` Road Kit network, its zone markers (`RailZones/RailA|RailB`), the two stations
    (`Stations/DebugStationA|B`) and the konbini with its weapon pads (`Konbini`, `KonbiniPads`).
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/DebugWorld.tscn")
LAYOUT = os.path.join(ROOT, "assets/world_source/debug_world_layout.json")
PAD_SCRIPT = "res://src/main/java/com/openworld/item/WeaponPad.java"
RAIL_RECORD = "res://assets/world_source/pieces/DebugRail.roads.json"


def split(text):
    """[(header line, body text)] -- one per `[...]` section, in order."""
    out = []
    for m in re.finditer(r"^\[.*?(?=^\[|\Z)", text, re.S | re.M):
        block = m.group(0)
        head, _, body = block.partition("\n")
        out.append([head, body])
    return out


def join(secs):
    return "".join(h + "\n" + b for h, b in secs)


def attr(head, key):
    m = re.search(r'\b%s="([^"]*)"' % key, head)
    return m.group(1) if m else None


def node_path(head):
    name, parent = attr(head, "name"), attr(head, "parent")
    if parent is None:
        return ""
    return name if parent == "." else parent + "/" + name


def xform(x, y, z, yaw_deg=0.0):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    # a .tscn Transform3D lists the basis ROWS: a yaw a is [[c, 0, s], [0, 1, 0], [-s, 0, c]] (it sends +X to (c, 0, -s))
    return "Transform3D(%.6g, 0, %.6g, 0, 1, 0, %.6g, 0, %.6g, %.4f, %.4f, %.4f)" % (c, s, -s, c, x, y, z)


def set_prop(body, key, value):
    if re.search(r"^%s = " % re.escape(key), body, re.M):
        return re.sub(r"^%s = .*$" % re.escape(key), "%s = %s" % (key, value), body, count=1, flags=re.M)
    return "%s = %s\n" % (key, value) + body


def get_origin(body):
    m = re.search(r"^transform = Transform3D\(([^)]*)\)", body, re.M)
    if not m:
        return None
    v = [float(t) for t in m.group(1).split(",")]
    return v[:9], v[9:]


def set_origin(body, pos):
    o = get_origin(body)
    basis = o[0] if o else [1, 0, 0, 0, 1, 0, 0, 0, 1]
    t = "Transform3D(%s, %.4f, %.4f, %.4f)" % (", ".join("%.6g" % b for b in basis), *pos)
    if o:
        return re.sub(r"^transform = Transform3D\([^)]*\)", "transform = " + t, body, count=1, flags=re.M)
    return "transform = %s\n" % t + body


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    L = json.load(open(LAYOUT))
    text = open(SCENE).read()
    secs = split(text)

    # ---- the CSG blockout: every node under NavigationRegion3D but Terrain3D, and the sub-resources only it used
    drop = [s for s in secs if s[0].startswith("[node") and (attr(s[0], "parent") or "").startswith("NavigationRegion3D")
            and not (attr(s[0], "parent") == "NavigationRegion3D" and attr(s[0], "name") == "Terrain3D")]
    secs = [s for s in secs if s not in drop]
    used = set(re.findall(r'SubResource\("([^"]+)"\)', join(secs)))
    secs = [s for s in secs if not (s[0].startswith("[sub_resource") and attr(s[0], "type") in
                                    ("ConcavePolygonShape3D", "StandardMaterial3D") and attr(s[0], "id") not in used)]
    # ... and the world navmesh baked over it: kept (its cell settings), emptied
    for s in secs:
        if s[0].startswith("[sub_resource") and attr(s[0], "id") == "NavigationMesh_world":
            s[1] = re.sub(r"^vertices = .*\n", "", s[1], flags=re.M)
            s[1] = re.sub(r"^polygons = .*\n", "", s[1], flags=re.M)

    # ---- generated blocks from a previous run: removed, then written again below
    GEN = ("DebugRail", "RailZones", "Stations", "Konbini", "KonbiniPads")
    secs = [s for s in secs if not (s[0].startswith("[node") and
                                    any(node_path(s[0]) == g or node_path(s[0]).startswith(g + "/") for g in GEN))]
    secs = [s for s in secs if not (s[0].startswith("[sub_resource") and (attr(s[0], "id") or "").startswith("RailZone_"))]
    secs = [s for s in secs if not (s[0].startswith("[ext_resource") and (attr(s[0], "id") or "").startswith("dbg_"))]

    # ---- moves
    nodes = {node_path(s[0]): s for s in secs if s[0].startswith("[node")}
    nodes["PlayerSpawn"][1] = set_origin(nodes["PlayerSpawn"][1], L["spawn"])
    nodes["Characters/Player"][1] = set_origin(nodes["Characters/Player"][1], L["spawn"])
    for n, p in L["cars"].items():
        nodes[n][1] = set_origin(nodes[n][1], p)
    nodes["AmmoRefill"][1] = set_origin(nodes["AmmoRefill"][1], L["ammo_refill"])
    off = L["pickups_offset"]
    base = [-250.0, 14.0, 0.0]          # the pickup row's old anchor: each pickup keeps its place in the row
    for path, s in nodes.items():
        if path.startswith("Pickups/") and path.count("/") == 1:
            o = get_origin(s[1])
            if o:
                p = o[1]
                if abs(p[0] - base[0]) < 60 and abs(p[2] - base[2]) < 60:
                    s[1] = set_origin(s[1], [p[0] + off[0], p[1] + off[1], p[2] + off[2]])
    nodes["WorldBounds"][1] = set_prop(nodes["WorldBounds"][1], "half_extent", "%.1f" % L["bounds_half_extent"])
    zsub = {}
    for z in L["road_zones"]:
        nodes["Zones/" + z["name"]][1] = set_origin(nodes["Zones/" + z["name"]][1], z["pos"])
    for s in secs:
        if s[0].startswith("[sub_resource") and attr(s[0], "type") == "Resource":
            m = re.search(r'^zone_id = "([^"]+)"', s[1], re.M)
            if m:
                zsub[m.group(1)] = s
    for z in L["road_zones"]:
        s = zsub[z["zone_id"]]
        s[1] = set_prop(s[1], "load_radius", "%.1f" % z["load"])
        s[1] = set_prop(s[1], "unload_radius", "%.1f" % z["unload"])

    # ---- new ext resources + sub resources, inserted before the first sub_resource / node
    ext = ['[ext_resource type="PackedScene" path="%s" id="dbg_station"]' % L["stations"][0]["scene"],
           '[ext_resource type="PackedScene" path="%s" id="dbg_konbini"]' % L["konbini"]["scene"],
           '[ext_resource type="Script" path="%s" id="dbg_pad"]' % PAD_SCRIPT]
    subs = []
    for z in L["rail_zones"]:
        subs.append(('[sub_resource type="Resource" id="RailZone_%s"]' % z["zone_id"],
                     'script = ExtResource("3_zone")\nzone_id = "%s"\nsize = Vector3(80, 12, 80)\nload_radius = %.1f\n'
                     'unload_radius = %.1f\ngeometry_path = "%s"\ngeometry_world_placed = true\n\n'
                     % (z["zone_id"], z["load"], z["unload"], z["piece"])))
    first_sub = next(i for i, s in enumerate(secs) if s[0].startswith("[sub_resource") or s[0].startswith("[node"))
    last_ext = max(i for i, s in enumerate(secs) if s[0].startswith("[ext_resource"))
    secs[last_ext][1] = secs[last_ext][1].rstrip("\n") + "\n"
    for e in reversed(ext):
        secs.insert(last_ext + 1, [e, ""])
    secs[last_ext + len(ext)][1] = "\n"
    first_node = next(i for i, s in enumerate(secs) if s[0].startswith("[node"))
    for h, b in reversed(subs):
        secs.insert(first_node, [h, b])

    # ---- new nodes, appended before the connections
    add = []
    add.append(('[node name="DebugRail" type="Node3D" parent="."]',
                'script = ExtResource("rk_net")\nrecord_path = "%s"\n\n' % RAIL_RECORD))
    add.append(('[node name="RailZones" type="Node" parent="."]', "\n"))
    for z in L["rail_zones"]:
        add.append(('[node name="%s" type="Node3D" parent="RailZones"]' % z["name"],
                    "transform = %s\nscript = ExtResource(\"3_zmark\")\nzone = SubResource(\"RailZone_%s\")\n\n"
                    % (xform(*z["pos"]), z["zone_id"])))
    add.append(('[node name="Stations" type="Node3D" parent="."]', "\n"))
    for st in L["stations"]:
        add.append(('[node name="%s" parent="Stations" instance=ExtResource("dbg_station")]' % st["name"],
                    "transform = %s\n\n" % xform(*st["pos"], st["yaw_deg"])))
    k = L["konbini"]
    add.append(('[node name="Konbini" parent="." instance=ExtResource("dbg_konbini")]',
                "transform = %s\n\n" % xform(*k["pos"], k["yaw_deg"])))
    add.append(('[node name="KonbiniPads" type="Node3D" parent="."]', "\n"))
    for pad in k["pads"]:
        add.append(('[node name="Pad_%s" type="Area3D" parent="KonbiniPads"]' % pad["weapon"],
                    'transform = %s\nscript = ExtResource("dbg_pad")\nweapon_id = "%s"\n\n' % (xform(*pad["pos"]),
                                                                                           pad["weapon"])))
    conn = next((i for i, s in enumerate(secs) if s[0].startswith("[connection")), len(secs))
    if conn and not secs[conn - 1][1].endswith("\n\n"):
        secs[conn - 1][1] = secs[conn - 1][1].rstrip("\n") + "\n\n"
    for h, b in reversed(add):
        secs.insert(conn, [h, b])

    out = join(secs)
    out = re.sub(r"\n{3,}", "\n\n", out)
    if args.check:
        print("debug_world_scene: %s" % ("stale" if out != text else "up to date"))
        return 1 if out != text else 0
    open(SCENE, "w").write(out)
    print("debug_world_scene: wrote %s (removed %d blockout node(s))" % (os.path.relpath(SCENE, ROOT), len(drop)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
