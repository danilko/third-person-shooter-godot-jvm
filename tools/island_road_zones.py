#!/usr/bin/env python3
"""Cut a world's Road Kit network into a 504 m grid of streaming zones (PLAN.md 3.10).

Before this the island's whole network was ONE zone (`IslandZone`, a 4608 m box) streaming ONE
piece, so every prop type was one island-wide MultiMesh that was never frustum-culled and never
unloaded, and the navmesh needed a world-sized bake. The cut itself already exists and is gated
(`point_zones`, CLAUDE.md "Zones (B6)"): a run goes with the zone holding most of its stations, a
pad with the zone at its clique centre, a gore with its ramp's run. What this tool supplies is the
ZONES, derived rather than dragged:

  1. every station falls in one cell of the world square cut `GRID_N` x `GRID_N`
     (`island_v3_geom`: 8 x 504 m about the origin -- the old district, and `NavBaker`'s
     `DISTRICT_HALF_EXTENT` is that cell's half);
  2. a cell becomes a zone only if the cut hands it something (partitioned to a fixed point: a cell
     that owns nothing is dropped and the cut re-run, because its stations then fall to a neighbour);
  3. each zone's radii are MEASURED from what it owns: `load = max(--load, reach + --lead)` where
     `reach` is the farthest station or mouth of its runs and pads from the cell centre -- a run is
     cut at crossings, never mid-carriageway, so a long run makes its cell reach far, and a zone that
     streams in only after the player is standing on its road is `zone_beyond_load`'s defect;
     `unload = load + --hysteresis`.

It writes the zones sidecar (`<stem>.zones.json`, exactly the shape the dock's Build writes) and the
scene's `ZoneMarker`s (`RoadZones/Road_<gx>_<gz>`, each `Zone.geometry_path` pointing at its piece and
placed in the network's frame), and removes the old single-zone marker (`--legacy`). The block is
identified by NAME, never by a comment, so re-running replaces it. Build the pieces afterwards:

    tools/island_road_zones.py assets/world_source/pieces/IslandRoads.roads.json \
        src/main/resources/com/openworld/world/World.tscn
    blender/tools/build_roads_piece.sh .../IslandRoads.roads.json Roads_IslandRoads \
        .../IslandRoads.zones.json .../IslandRoads.ground.json
    tools/island_road_zones.py ... --check       # exit 1 if the sidecar or the scene is stale

Cells are indexed in GODOT axes (the scene's): `gx` along +X, `gz` along +Z (south), both from the
world square's corner, so `island_0_0` is the north-west cell.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (REPO / "blender" / "lib", REPO / "blender" / "addons" / "road_kit_authoring", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import point_model as pm            # noqa: E402
import point_zones as pz            # noqa: E402
import island_v3_geom as geom       # noqa: E402
import island_traffic_zones as itz  # noqa: E402  (the .tscn section helpers)

ZONE_SCRIPT = itz.ZONE_SCRIPT
MARKER_SCRIPT = itz.MARKER_SCRIPT
PIECES_RES = "res://src/main/resources/com/openworld/world/pieces"
NODE_ID_BASE = 910013000          # a free block beside TrafficZones' 910012xxx
ZONE_PREFIX = "Zone_road_"
HOLDER = "RoadZones"


# ---------------------------------------------------------------------------- the grid

def cell_of(x: float, y: float, cell: float, origin: float) -> tuple[int, int]:
    """Kit (x east, y north) -> (gx, gz) in Godot axes (z = -y)."""
    return int(math.floor((x + origin) / cell)), int(math.floor((-y + origin) / cell))


def cell_centre(gx: int, gz: int, cell: float, origin: float) -> tuple[float, float]:
    """(gx, gz) -> kit (x, y) of the cell centre."""
    return (gx + 0.5) * cell - origin, -((gz + 0.5) * cell - origin)


def zone_id(prefix: str, gx: int, gz: int) -> str:
    return f"{prefix}_{gx}_{gz}"


def zone_box(zid, gx, gz, a, load=0.0, unload=0.0):
    cx, cy = cell_centre(gx, gz, a.cell, a.cell * a.grid / 2.0)
    return pz.ZoneBox(zid, (cx, cy), (a.cell / 2.0, a.cell / 2.0), load, unload)


def _bend(net, a_uid, b_uid, c_uid) -> float:
    a, b, c = (net.points[u].pos for u in (a_uid, b_uid, c_uid))
    h1 = math.atan2(b[1] - a[1], b[0] - a[0])
    h2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs((h2 - h1 + math.pi) % (2 * math.pi) - math.pi)


def split_plan(net, a):
    """Stations to split at (`point_record_ops.split_at_joint`) so no run crosses a cell boundary
    by more than `--min-piece`. The cut stays a RUN cut (`point_zones`); this only makes the runs
    short enough for it to follow the grid. Per run, walking its chain: where two neighbours sit
    in different cells, the station within one of the boundary with the smallest bend becomes a
    joint -- never a hairpin, never a mouth or a ramp -- and only if both the piece it closes and
    the rest of the run are at least `--min-piece` long, which is also what makes a second run of
    the tool a no-op: a joint already sits at every boundary it would pick."""
    origin = a.cell * a.grid / 2.0
    cuts = []
    for name in sorted(net.roads):
        for run in pm.road_runs(net, net.roads[name]):
            if len(run) < 3:
                continue
            s = [0.0]
            for u, v in zip(run, run[1:]):
                s.append(s[-1] + math.dist(net.points[u].pos[:2], net.points[v].pos[:2]))
            cell = [cell_of(*net.points[u].pos[:2], a.cell, origin) for u in run]
            last = 0.0
            for i in range(len(run) - 1):
                if cell[i] == cell[i + 1]:
                    continue
                best = None
                for j in range(max(1, i - 1), min(len(run) - 1, i + 3)):
                    p = net.resolved(run[j])
                    if (p.aux_fwd or p.aux_bwd or net.points[run[j]].targets(pm.LINK_AUX)
                            or net.points[run[j]].targets(pm.LINK_JUNCTION)):
                        continue
                    if s[j] - last < a.min_piece or s[-1] - s[j] < a.min_piece:
                        continue
                    bend = _bend(net, run[j - 1], run[j], run[j + 1])
                    if bend > math.radians(a.max_bend):
                        continue
                    if best is None or bend < best[0]:
                        best = (bend, j)
                if best is not None:
                    cuts.append((name, run[best[1]]))
                    last = s[best[1]]
    return cuts


def apply_splits(net, cuts):
    import point_record_ops as ro
    made = []
    for name, uid in cuts:
        road = net.road_of(uid)
        stem = re.sub(r"__\d+$", "", road.name)
        k = 2
        while f"{stem}__{k}" in net.roads:
            k += 1
        msg, extra = ro.split_at_joint(net, uid, f"{stem}__{k}")
        made.append(msg)
    return made


def derive(net, a):
    """-> (zones [(zid, gx, gz, load, unload, reach)], partition). Fixed point: drop cells that own
    nothing and re-cut until every zone left owns something."""
    origin = a.cell * a.grid / 2.0
    cells = {}
    for p in net.points.values():
        gx, gz = cell_of(p.pos[0], p.pos[1], a.cell, origin)
        cells[zone_id(a.prefix, gx, gz)] = (gx, gz)
    # The fall-back "nearest centre within load radius" only matters for a station in a DROPPED
    # cell; give it the widest radius a zone can end up with so it finds a neighbour, not "none".
    wide = a.cell * 4.0
    for _ in range(len(cells) + 1):
        boxes = [zone_box(z, gx, gz, a, wide, wide) for z, (gx, gz) in sorted(cells.items())]
        part = pz.partition(net, boxes)
        owned = set(part.pieces())
        owned.discard(pz.RESIDENT)
        if owned == set(cells):
            break
        cells = {z: c for z, c in cells.items() if z in owned}
    else:
        raise SystemExit("the zone cut did not settle")

    # Reach: every station of every run the zone owns, and every mouth of every pad.
    pts = {z: [] for z in cells}
    for name in sorted(net.roads):
        for uids in pm.road_runs(net, net.roads[name]):
            if uids:
                z = part.run_zone(uids)
                if z in pts:
                    pts[z] += [net.points[u].pos[:2] for u in uids]
    for comp in net.junction_cliques():
        z = part.pad_zone(comp)
        if z in pts:
            pts[z] += [net.points[u].pos[:2] for u in comp]
    out = []
    for z, (gx, gz) in sorted(cells.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        cx, cy = cell_centre(gx, gz, a.cell, origin)
        reach = max((math.hypot(x - cx, y - cy) for x, y in pts[z]), default=0.0)
        load = max(a.load, math.ceil((reach + a.lead) / 50.0) * 50.0)
        out.append((z, gx, gz, load, load + a.hysteresis, reach))
    # Re-cut with the real radii, so the findings this reports are the ones the build will see.
    part = pz.partition(net, [zone_box(z, gx, gz, a, l, u) for z, gx, gz, l, u, _ in out])
    return out, part


# ---------------------------------------------------------------------------- outputs

def sidecar(zones, a, net_y: float) -> dict:
    origin = a.cell * a.grid / 2.0
    rows = []
    for z, gx, gz, load, unload, _ in zones:
        cx, cy = cell_centre(gx, gz, a.cell, origin)
        # The marker stands at the network's own height, so its kit z in the network frame is 0.
        rows.append({"centre": [cx, cy, 0.0], "half": [a.cell / 2.0, a.cell / 2.0],
                     "load_radius": float(load), "marker": f"Road_{gx}_{gz}",
                     "unload_radius": float(unload), "zone_id": z})
    return {"schema_ver": pz.SCHEMA_VER, "zones": rows}


def sidecar_text(d: dict) -> str:
    return json.dumps(d, indent=1, sort_keys=True) + "\n"


def network_transform(sections, name: str) -> str:
    for header, body in sections:
        if header.startswith("[node") and itz.attr(header, "name") == name:
            m = re.search(r"transform = (Transform3D\([^)]*\))", body)
            return m.group(1) if m else "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)"
    raise SystemExit(f"no node named '{name}' in the scene")


def patch(text: str, zones, a) -> str:
    sections = itz.split_sections(text)
    zone_ext = itz.ext_resource_id(sections, ZONE_SCRIPT)
    marker_ext = itz.ext_resource_id(sections, MARKER_SCRIPT)
    if zone_ext is None or marker_ext is None:
        raise SystemExit("the scene has no Zone/ZoneMarker ext_resource -- add one marker by hand first")
    xf = network_transform(sections, a.network)
    offset = itz.network_offset(sections, a.network)
    origin = a.cell * a.grid / 2.0
    stem = Path(a.record).name.replace(".roads.json", "")

    sub, nodes = [], [f'[node name="{HOLDER}" type="Node" parent="." unique_id={NODE_ID_BASE}]\n\n']
    for i, (z, gx, gz, load, unload, _) in enumerate(zones):
        cx, cy = cell_centre(gx, gz, a.cell, origin)
        piece = pz.piece_name(f"Roads_{stem}", z)
        sub.append(f'[sub_resource type="Resource" id="{ZONE_PREFIX}{gx}_{gz}"]\n'
                   f'script = ExtResource("{zone_ext}")\n'
                   f'zone_id = "{z}"\n'
                   f'size = Vector3({a.cell:g}, 600, {a.cell:g})\n'
                   f'load_radius = {load:.1f}\n'
                   f'unload_radius = {unload:.1f}\n'
                   f'geometry_path = "{PIECES_RES}/{piece}.tscn"\n'
                   f'geometry_world_placed = true\n'
                   f'geometry_world_transform = {xf}\n\n')
        nodes.append(f'[node name="Road_{gx}_{gz}" type="Node3D" parent="{HOLDER}" '
                     f'unique_id={NODE_ID_BASE + 1 + i}]\n'
                     f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, '
                     f'{cx + offset[0]:.3f}, {offset[1]:.3f}, {-cy + offset[2]:.3f})\n'
                     f'script = ExtResource("{marker_ext}")\n'
                     f'zone = SubResource("{ZONE_PREFIX}{gx}_{gz}")\n'
                     f'show_debug_volume = false\n\n')

    def generated(header: str) -> bool:
        if header.startswith("[sub_resource"):
            rid = itz.attr(header, "id") or ""
            return rid.startswith(ZONE_PREFIX) or rid in a.legacy_sub
        if header.startswith("[node"):
            name, parent = itz.attr(header, "name"), itz.attr(header, "parent")
            return name == HOLDER or parent == HOLDER or (parent == "." and name in a.legacy_node)
        return False

    return itz.splice(sections, generated, sub, nodes)


# ---------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("record", help="<stem>.roads.json")
    ap.add_argument("scene", type=Path)
    ap.add_argument("--network", default="IslandRoads", help="the RoadKitNetwork node in the scene")
    ap.add_argument("--prefix", default="island", help="zone id prefix: <prefix>_<gx>_<gz>")
    ap.add_argument("--cell", type=float, default=geom.DISTRICT)
    ap.add_argument("--grid", type=int, default=geom.GRID_N, help="cells per side of the world square")
    ap.add_argument("--load", type=float, default=700.0, help="the smallest load radius, m")
    ap.add_argument("--lead", type=float, default=200.0,
                    help="load radius past a zone's farthest station (streaming time a fast car closes)")
    ap.add_argument("--hysteresis", type=float, default=300.0, help="unload - load, m")
    ap.add_argument("--legacy-node", dest="legacy_node", action="append", default=["IslandZone"])
    ap.add_argument("--legacy-sub", dest="legacy_sub", action="append", default=["Zone_island"])
    ap.add_argument("--min-piece", dest="min_piece", type=float, default=300.0,
                    help="shortest stretch a road is split into at a cell boundary, m")
    ap.add_argument("--max-bend", dest="max_bend", type=float, default=15.0,
                    help="largest bend (deg) at a station that may become a joint")
    ap.add_argument("--split", action="store_true",
                    help="write the joints into the RECORD (an authored change: review the diff)")
    ap.add_argument("--check", action="store_true", help="exit 1 if the sidecar or scene would change")
    a = ap.parse_args()

    net = pm.load_network(a.record)
    cuts = split_plan(net, a)
    if cuts:
        print(f"{len(cuts)} run(s) cross a cell boundary by more than {a.min_piece:.0f} m:")
        for msg in apply_splits(net, cuts):
            print("  " + msg)
        if a.check or not a.split:
            print("REFUSED: the record needs joints at those stations -- re-run with --split "
                  "(it rewrites the record), then rebuild the pieces.", file=sys.stderr)
            return 1
        pm.save_network(net, a.record)
        print(f"{a.record}: wrote {len(cuts)} joint(s)")
    zones, part = derive(net, a)
    for f in part.findings:
        print(f"  {f['severity']} {f['code']}: {f['message']}")
    counts = part.pieces()
    print(f"{len(net.points)} stations -> {len(zones)} zones of {a.cell:g} m "
          f"(grid {a.grid} x {a.grid}); resident: {counts.get(pz.RESIDENT, 'none')}")
    for z, gx, gz, load, unload, reach in zones:
        c = counts.get(z, {})
        print(f"  {z:12s} runs {c.get('runs', 0):3d} pads {c.get('pads', 0):2d} gores {c.get('gores', 0):2d}"
              f"  reach {reach:6.0f} m  load {load:5.0f}  unload {unload:5.0f}")
    bad = [f for f in part.findings if f["code"] in ("zone_beyond_load", "zone_none")]
    if bad or pz.RESIDENT in counts:
        print("REFUSED: every run and pad must stream with a zone whose load radius covers it.",
              file=sys.stderr)
        return 1

    side_path = Path(a.record.replace(".roads.json", ".zones.json"))
    side = sidecar_text(sidecar(zones, a, 0.0))
    text = a.scene.read_text()
    patched = patch(text, zones, a)
    stale = [p for p, new, old in ((side_path, side, side_path.read_text() if side_path.exists() else ""),
                                   (a.scene, patched, text)) if new != old]
    if a.check:
        if stale:
            print("STALE: " + ", ".join(str(p) for p in stale) + " -- re-run without --check.", file=sys.stderr)
            return 1
        print("up to date")
        return 0
    if side_path in stale:
        side_path.write_text(side)
    if a.scene in stale:
        a.scene.write_text(patched)
    print("wrote " + (", ".join(str(p) for p in stale) if stale else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
