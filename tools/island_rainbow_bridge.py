#!/usr/bin/env python3
"""island_rainbow_bridge.py -- put the Rainbow Bridge on the island's airport crossing (PLAN.md 3.8 step 4).

    python3 tools/island_rainbow_bridge.py [--check]

The bridge's centre and heading are DERIVED from the road record, never typed in: the airport road's two shore
stations (`kuko_dori*`, the last station with natural ground at or above the water on each side of the water) give
the crossing's axis and its mid-point. Then:

* every `kuko_dori*` station on the deck within the suspension structure's length of the centre gets `pillar_skip`
  (the towers and anchorages carry the deck there; a Road Kit pier would stand in the main span);
* World.tscn gets (or updates) `Landmarks/RainbowBridge`, an instance of `world/buildings/RainbowBridge.tscn` at that
  centre, turned onto that axis, at the road network's height offset (IslandRoads' Y), so the model's lower road
  level (`library_landmarks.RB_ROAD_LOWER`) sits on the airport road's deck.

Idempotent; `--check` writes nothing and exits 1 if the record or the scene would change. Afterwards rebuild the
dirty island pieces (the airport road's piers change) with the pipeline in PLAN.md.
"""
import math
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
BRIDGE_SCENE = "res://src/main/resources/com/openworld/world/buildings/RainbowBridge.tscn"
HALF_LENGTH = 575.0 / 2 + 115.0 + 22.0      # library_landmarks: RB_MAIN / 2 + RB_SIDE + the anchorage block
DECK_MIN_Z = 20.0                            # a station "on the deck" (the crossing's deck is at 24 m)


def crossing_plan():
    """(centre (x, y) record, unit axis (x, y)) of the final plan's crossing (PLAN.md 3.29 v9): the water gap along
    `island_plan.BRIDGE_X`, measured on the land grid, its axis north -> south. The spur (upper deck) and the rail
    (lower deck, R7) cross there; the airport road does not any more."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import island_plan as PL
    from island_roadgen import Ground
    g = Ground()
    y0, y1 = PL.BRIDGE_SEARCH_Y
    wet = [y for y in [y0 - k * 2.0 for k in range(int((y0 - y1) / 2.0))] if (g.z(PL.BRIDGE_X, y) or -99.0) < -1.0]
    if not wet:
        raise SystemExit("island_rainbow_bridge: no water along x %.0f" % PL.BRIDGE_X)
    a, b = max(wet), min(wet)
    return (PL.BRIDGE_X, (a + b) / 2.0), (0.0, -1.0)


def crossing(net):
    """(centre (x, y) in the network frame, unit axis (x, y)) of the airport crossing, from the record."""
    chain = []
    for name in sorted(n for n in net.roads if n.startswith("kuko_dori")):
        for u in net.roads[name].points:
            if not chain or chain[-1] != u:
                chain.append(u)
    pts = [net.points[u] for u in chain]
    wet = [i for i, p in enumerate(pts) if p.has_ground_z and p.ground_z < -1.0]
    if not wet:
        raise SystemExit("island_rainbow_bridge: kuko_dori crosses no water in the record")
    a, b = pts[max(0, wet[0] - 1)], pts[min(len(pts) - 1, wet[-1] + 1)]   # the two shore stations
    dx, dy = b.pos[0] - a.pos[0], b.pos[1] - a.pos[1]
    n = math.hypot(dx, dy)
    return ((a.pos[0] + b.pos[0]) / 2, (a.pos[1] + b.pos[1]) / 2), (dx / n, dy / n), pts


def network_y(scene_text):
    m = re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', scene_text)
    return float(m.group(1).split(",")[10]) if m else 0.0


def scene_block(centre, axis, y):
    # the model's +X (Godot) onto the crossing axis. kit (x, y) -> Godot (x, -y): axis_g = (ax, -ay); a yaw of theta
    # about +Y takes +X to (cos theta, 0, -sin theta), so theta = atan2(-axis_g.z, axis_g.x) = atan2(ay, ax)
    gx, gz = axis[0], -axis[1]
    c, s = gx, -gz                          # cos, sin of the yaw
    basis = "%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f" % (c, s, -s, c)
    return ('[node name="Landmarks" type="Node3D" parent="." unique_id=910014000]\n\n'
            '[node name="RainbowBridge" parent="Landmarks" unique_id=910014001 instance=ExtResource("rb_bridge")]\n'
            'transform = Transform3D(%s, %.3f, %.3f, %.3f)\n' % (basis, centre[0], y, -centre[1]))


CORRIDOR = 15.0          # library_landmarks: the clear road corridor, |local z| < 15
ROAD_LOWER = 32.0        # library_landmarks.RB_ROAD_UPPER: the SPUR's deck (the lower deck, 24 m, is rail -- R7)
SPAN = 575.0 / 2 + 115.0 # the suspension span, towers to anchorages


def alignment(centre, axis, y):
    """Walk every airport-road lane's baked curve (the lanekit sidecars) through the bridge's own frame: inside the
    suspension span each lane, with its half width, must lie within the clear corridor, at the lower road level.
    Returns (lane samples checked, worst corridor overlap m, worst height error m)."""
    import glob
    import json
    gx, gz = axis[0], -axis[1]
    ox, oz = centre[0], -centre[1]
    n, worst_side, worst_h = 0, -1e9, 0.0
    for f in glob.glob(os.path.join(ROOT, "assets/world_source/pieces/Roads_IslandRoads_island_*.lanekit.json")):
        for lane in json.load(open(f))["lanes"]:
            if not lane.get("road_name", "").startswith("shuto_spur"):
                continue
            half = float(lane.get("lane_width", 4.5)) / 2
            for c in lane["curve"]:
                px, py, pz = c["p"]
                dx, dz = px - ox, pz - oz
                lx = dx * gx + dz * gz                 # along the bridge
                lz = -dx * gz + dz * gx                # across it
                if abs(lx) > SPAN:
                    continue
                n += 1
                worst_side = max(worst_side, abs(lz) + half - CORRIDOR)
                worst_h = max(worst_h, abs((py + y) - (y + ROAD_LOWER)))
    return n, worst_side, worst_h


def main(argv):
    check = "--check" in argv
    net = pm.load_network(RECORD)
    centre, axis = crossing_plan()
    pts = []
    changed = []

    def along(p):
        return (p.pos[0] - centre[0]) * axis[0] + (p.pos[1] - centre[1]) * axis[1]
    # a station's flag holds until the NEXT station (point_solve._bool_field), so a station skips its piers only when
    # the whole span it starts lies inside the structure; a span reaching past an anchorage keeps its piers
    for i, p in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        want = (nxt is not None and abs(along(p)) <= HALF_LENGTH and abs(along(nxt)) <= HALF_LENGTH
                and p.pos[2] >= DECK_MIN_Z and nxt.pos[2] >= DECK_MIN_Z)
        if bool(p.pillar_skip) != want:
            p.pillar_skip = want
            changed.append(p.uid)
    text = open(SCENE).read()
    block = scene_block(centre, axis, network_y(text))
    new = re.sub(r'\[node name="Landmarks"[^\n]*\n\n\[node name="RainbowBridge"[^\n]*\ntransform = [^\n]*\n', "",
                 text)
    if '[ext_resource type="PackedScene" path="%s" id="rb_bridge"]' % BRIDGE_SCENE not in new:
        head, rest = new.split("\n\n", 1)
        new = head + '\n\n[ext_resource type="PackedScene" path="%s" id="rb_bridge"]\n' % BRIDGE_SCENE + rest
    new = new.rstrip("\n") + "\n\n" + block
    print("island_rainbow_bridge: centre (%.1f, %.1f) axis (%.3f, %.3f), %d station(s) change pillar_skip, scene %s"
          % (centre[0], centre[1], axis[0], axis[1], len(changed), "changes" if new != text else "unchanged"))
    n, side, h = alignment(centre, axis, network_y(text))
    fit = n > 0 and side <= 0.0 and h <= 0.5
    print("island_rainbow_bridge: %d airport-road lane samples in the span; worst %.2f m %s the corridor edge, worst "
          "height error %.2f m -> %s" % (n, abs(side), "inside" if side <= 0 else "PAST", h, "fits" if fit else "DOES NOT FIT"))
    if check:
        sys.exit(1 if (changed or new != text or not fit) else 0)
    if changed:
        pm.save_network(net, RECORD)
    if new != text:
        open(SCENE, "w").write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
