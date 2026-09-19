#!/usr/bin/env python3
"""island_sites.py -- place the island's composite sites and landmarks in World.tscn, from MEASURED facts
(PLAN.md 3.8 steps 5 and 8).

    python3 tools/island_sites.py [--check]

Nothing is typed in as a coordinate; each placement is derived, like `island_rainbow_bridge.py`'s:

* `ContainerTerminal` (`tools/building_kit/site_container_terminal.py`) -- its FRONT (+Z, the quay line with the
  cranes' seaside rails on it) is laid on the industrial harbour's east quay: the edge where the natural ground
  (`IslandRoads.ground.bin`) drops from the 4 m reclaimed land to the dredged water is sampled every 10 m over
  `QUAY_SPAN`, a line is least-squares fitted through it, and the site stands on the land side of that line, centred
  on the span, at the land's height.
* `ShuriCastle` (library_landmarks.shuri_castle) -- the hill-castle site the 3.8 note asks for: the ~140 m patch at
  the massif's foot whose ground stays within 2-60 m and within `CASTLE_RELIEF` of itself, has no road within
  `CASTLE_CLEAR`, and scores best on (mountain behind it to the north-west, near downtown); turned so its front (the
  Seiden's face) looks at downtown, standing on the patch's lowest ground (its platform takes up the slope).

Each site STREAMS: a `ZoneMarker` under `SiteZones` whose Zone places the building scene in world space
(`geometry_world_placed`, the island road pieces' mechanism), zone id `site_<name>`; the block is found by name and
replaced whole. The Road Kit dock leaves a site zone out of the road cut (`road_kit_zones.is_traffic_only`). `--check`
writes nothing and exits 1 if the scene would change. Building scenes: `tools/building_kit/build_buildings.sh`.
"""
import collections
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import Ground, densify, ROOT     # noqa: E402
import point_model as pm                             # noqa: E402

SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
BUILDINGS = "res://src/main/resources/com/openworld/world/buildings/"

QUAY_SPAN = (-1150.0, -1480.0)       # record y range of the terminal's quay (north end of the east quay)
QUAY_X_RANGE = (0.0, 400.0)          # where to look for the edge
TERMINAL_D = 218.4                   # site_container_terminal.D
DOWNTOWN = (725.0, 300.0)            # the trunk grid's centre (island_trunk_grid NS naka_hondori x ekimae_dori)
CASTLE_HALF = 70.0
CASTLE_RELIEF = 30.0
CASTLE_CLEAR = 85.0
TERMINAL_LOAD = 900.0                # streamed in within this of the site (unload + 300 m)
CASTLE_LOAD = 2000.0                 # a landmark on a hill is seen from across the city


def quay_line(g):
    """(point on the line, unit direction along the quay (south), unit normal to the SEA) from the ground edge."""
    pts = []
    y = QUAY_SPAN[0]
    while y >= QUAY_SPAN[1]:
        last = None
        x = QUAY_X_RANGE[0]
        while x <= QUAY_X_RANGE[1]:
            z = g.z(x, y)
            if z is not None and z < 0.0 and last is not None and last > 1.0:
                pts.append((x - 1.0, y))
                break
            last = z
            x += 2.0
        y -= 10.0
    n = len(pts)
    my = sum(p[1] for p in pts) / n
    mx = sum(p[0] for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    k = sxy / syy                                  # x = mx + k (y - my)
    u = (k, 1.0)
    L = math.hypot(*u)
    u = (-u[0] / L, -u[1] / L)                     # southward along the quay
    sea = (-u[1], u[0]) if (-u[1]) > 0 else (u[1], -u[0])   # the normal pointing east (+x), to the water
    resid = max(abs(p[0] - (mx + k * (p[1] - my))) for p in pts)
    return (mx, my), u, sea, n, resid


def castle_site(g, net):
    road = []
    for r in net.roads.values():
        road += densify([net.points[v].pos[:2] for v in r.points], 10.0)
    grid = collections.defaultdict(list)
    for x, y in road:
        grid[(int(x // 50), int(y // 50))].append((x, y))

    def near(x, y, R):
        for i in range(int((x - R) // 50), int((x + R) // 50) + 1):
            for j in range(int((y - R) // 50), int((y + R) // 50) + 1):
                if any(abs(p[0] - x) < R and abs(p[1] - y) < R for p in grid.get((i, j), ())):
                    return True
        return False
    best = None
    H = CASTLE_HALF
    for cx in range(-1500, 600, 20):
        for cy in range(-500, 1500, 20):
            zs = [g.z(cx + dx, cy + dy) for dx in range(-int(H), int(H) + 1, 20) for dy in range(-int(H), int(H) + 1, 20)]
            if any(z is None for z in zs):
                continue
            lo, hi = min(zs), max(zs)
            if lo < 2.0 or hi > 60.0 or hi - lo > CASTLE_RELIEF or near(cx, cy, CASTLE_CLEAR):
                continue
            back = g.z(cx - 250, cy + 250) or 0.0
            d = math.hypot(cx - DOWNTOWN[0], cy - DOWNTOWN[1])
            score = d * 0.01 - back * 0.02 + (hi - lo) * 0.3
            if best is None or score < best[0]:
                best = (score, cx, cy, lo, hi, back)
    return best


SITE_ID_BASE = 910015000
HOLDER = "SiteZones"
SUB_PREFIX = "Zone_site_"


def site_xf(pos, yaw_deg):
    """The Godot Transform3D literal for a scene at record-frame `pos` (x, y, height), its +Z turned to `yaw_deg`."""
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return "Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)" % (c, s, -s, c, pos[0], pos[2], -pos[1])


def yaw_to(dx_g, dz_g):
    """The yaw (deg about +Y) that turns +Z onto the Godot direction (dx, dz)."""
    return math.degrees(math.atan2(dx_g, dz_g))


def main(argv):
    g = Ground()
    net = pm.load_network(RECORD)
    text = open(SCENE).read()
    ny = float(re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
               .group(1).split(",")[10])
    # the terminal
    (qx, qy), u, sea, n, resid = quay_line(g)
    cy = (QUAY_SPAN[0] + QUAY_SPAN[1]) / 2
    cx = qx + (u[0] / u[1]) * (cy - qy) if abs(u[1]) > 1e-9 else qx
    centre = (cx - sea[0] * TERMINAL_D / 2, cy - sea[1] * TERMINAL_D / 2)
    land = g.z(*centre)
    t_yaw = yaw_to(sea[0], -sea[1])                  # record (x, y) -> Godot (x, -y)
    print("island_sites: quay fitted through %d edge samples (worst %.1f m off the line); terminal at (%.1f, %.1f), "
          "ground %.2f m, front facing (%.3f, %.3f)" % (n, resid, centre[0], centre[1], land, sea[0], sea[1]))
    # the castle
    site = castle_site(g, net)
    if site is None:
        raise SystemExit("island_sites: no castle site passes (relief %.0f m, road clearance %.0f m)"
                         % (CASTLE_RELIEF, CASTLE_CLEAR))
    _s, kx, ky, lo, hi, back = site
    c_yaw = yaw_to(DOWNTOWN[0] - kx, -(DOWNTOWN[1] - ky))
    print("island_sites: castle at (%d, %d), ground %.1f-%.1f m under it, the mountain %.0f m behind, facing downtown"
          % (kx, ky, lo, hi, back))
    # each site STREAMS: a ZoneMarker whose Zone places the building scene in world space (the island's road pieces'
    # mechanism, `Zone.geometry_world_placed`), so a 900-box terminal exists only near the harbour
    sites = (("container_terminal", "ContainerTerminal", (centre[0], centre[1], ny + land), t_yaw, (364.0, 218.4),
              TERMINAL_LOAD),
             ("shuri_castle", "ShuriCastle", (kx, ky, ny + lo), c_yaw, (158.0, 128.0), CASTLE_LOAD))
    import island_traffic_zones as itz
    sections = itz.split_sections(text)
    zone_ext = itz.ext_resource_id(sections, itz.ZONE_SCRIPT)
    marker_ext = itz.ext_resource_id(sections, itz.MARKER_SCRIPT)
    sub, nodes = [], ['[node name="%s" type="Node" parent="." unique_id=%d]\n\n' % (HOLDER, SITE_ID_BASE)]
    for i, (zid, scene, pos, yaw, size, load) in enumerate(sites):
        sub.append('[sub_resource type="Resource" id="%s%s"]\n'
                   'script = ExtResource("%s")\n'
                   'zone_id = "site_%s"\n'
                   'size = Vector3(%g, 120, %g)\n'
                   'load_radius = %.1f\n'
                   'unload_radius = %.1f\n'
                   'geometry_path = "%s%s.tscn"\n'
                   'geometry_world_placed = true\n'
                   'geometry_world_transform = %s\n\n'
                   % (SUB_PREFIX, zid, zone_ext, zid, max(size), max(size), load, load + 300.0, BUILDINGS, scene,
                      site_xf(pos, yaw)))
        nodes.append('[node name="%s" type="Node3D" parent="%s" unique_id=%d]\n'
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                     'script = ExtResource("%s")\n'
                     'zone = SubResource("%s%s")\n'
                     'show_debug_volume = false\n\n'
                     % (scene, HOLDER, SITE_ID_BASE + 1 + i, pos[0], pos[2], -pos[1], marker_ext, SUB_PREFIX, zid))

    def generated(header):
        if header.startswith("[sub_resource"):
            return (itz.attr(header, "id") or "").startswith(SUB_PREFIX)
        if header.startswith("[node"):
            name, parent = itz.attr(header, "name"), itz.attr(header, "parent")
            return name == HOLDER or parent == HOLDER
        return False
    new = itz.splice(sections, generated, sub, nodes)
    print("island_sites: scene %s" % ("changes" if new != text else "unchanged"))
    if "--check" in argv:
        sys.exit(1 if new != text else 0)
    if new != text:
        open(SCENE, "w").write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
